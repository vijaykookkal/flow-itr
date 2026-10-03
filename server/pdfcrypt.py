"""The PDF standard security handler, in the standard library only.

Most of the documents that matter here arrive encrypted, and not because
anyone meant to keep them secret from their owner: the income-tax portal ships
the AIS and TIS encrypted, and brokerages commonly ship tax forms and
statements encrypted. They open in any viewer without a prompt,
because the user password is empty and only the *owner* password -- the one
that controls printing and copying -- is set.

A reader that ignores this does not fail loudly. It decodes the streams, gets
random bytes, finds no text, and reports the document as scanned. That is the
worst possible outcome for a tax tool: a silently empty schedule.

So the handler is implemented: RC4 for /V 1 and 2, AES-CBC for /V 4 and 5.
Both ciphers are small enough to write out, and hashlib already has the MD5,
SHA-256, SHA-384 and SHA-512 the key derivations need.

Where a real user password is set -- the portal's own AIS download asks for
PAN in lower case followed by the date of birth as ddmmyyyy -- `open_document`
takes candidate passwords and reports which one worked.
"""

from __future__ import annotations

import hashlib
import struct

# The 32-byte padding string from the PDF specification, used to stretch (or
# truncate) any password to exactly 32 bytes.
PAD = bytes([
    0x28, 0xBF, 0x4E, 0x5E, 0x4E, 0x75, 0x8A, 0x41, 0x64, 0x00, 0x4E, 0x56,
    0xFF, 0xFA, 0x01, 0x08, 0x2E, 0x2E, 0x00, 0xB6, 0xD0, 0x68, 0x3E, 0x80,
    0x2F, 0x0C, 0xA9, 0xFE, 0x64, 0x53, 0x69, 0x7A,
])


# ---------------------------------------------------------------------------
# RC4
# ---------------------------------------------------------------------------


def rc4(key: bytes, data: bytes) -> bytes:
    s = list(range(256))
    j = 0
    klen = len(key)
    if klen == 0:
        return data
    for i in range(256):
        j = (j + s[i] + key[i % klen]) & 0xFF
        s[i], s[j] = s[j], s[i]
    out = bytearray(len(data))
    i = j = 0
    for n, byte in enumerate(data):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        out[n] = byte ^ s[(s[i] + s[j]) & 0xFF]
    return bytes(out)


# ---------------------------------------------------------------------------
# AES
# ---------------------------------------------------------------------------

SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16")
INV_SBOX = bytearray(256)
for _i, _v in enumerate(SBOX):
    INV_SBOX[_v] = _i
RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36,
        0x6C, 0xD8, 0xAB, 0x4D, 0x9A]


def _xtime(a: int) -> int:
    a <<= 1
    return (a ^ 0x1B) & 0xFF if a & 0x100 else a


def _mul(a: int, b: int) -> int:
    out = 0
    for _ in range(8):
        if b & 1:
            out ^= a
        b >>= 1
        a = _xtime(a)
    return out


def _expand_key(key: bytes) -> list[list[int]]:
    nk = len(key) // 4
    rounds = nk + 6
    words = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (rounds + 1)):
        t = list(words[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [SBOX[b] for b in t]
            t[0] ^= RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [SBOX[b] for b in t]
        words.append([words[i - nk][j] ^ t[j] for j in range(4)])
    return words


def _decrypt_block(block: bytes, words: list[list[int]], rounds: int) -> bytes:
    state = [list(block[i::4]) for i in range(4)]  # column-major -> rows

    def add_round_key(rnd: int) -> None:
        for c in range(4):
            w = words[rnd * 4 + c]
            for r in range(4):
                state[r][c] ^= w[r]

    add_round_key(rounds)
    for rnd in range(rounds - 1, -1, -1):
        for r in range(1, 4):  # inverse ShiftRows
            state[r] = state[r][-r:] + state[r][:-r]
        for r in range(4):  # inverse SubBytes
            state[r] = [INV_SBOX[b] for b in state[r]]
        add_round_key(rnd)
        if rnd:  # inverse MixColumns
            for c in range(4):
                a = [state[r][c] for r in range(4)]
                state[0][c] = _mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9)
                state[1][c] = _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13)
                state[2][c] = _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11)
                state[3][c] = _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)

    out = bytearray(16)
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = state[r][c]
    return bytes(out)


def _encrypt_block(block: bytes, words: list[list[int]], rounds: int) -> bytes:
    state = [list(block[i::4]) for i in range(4)]

    def add_round_key(rnd: int) -> None:
        for c in range(4):
            w = words[rnd * 4 + c]
            for r in range(4):
                state[r][c] ^= w[r]

    add_round_key(0)
    for rnd in range(1, rounds + 1):
        for r in range(4):
            state[r] = [SBOX[b] for b in state[r]]
        for r in range(1, 4):
            state[r] = state[r][r:] + state[r][:r]
        if rnd != rounds:
            for c in range(4):
                a = [state[r][c] for r in range(4)]
                state[0][c] = _mul(a[0], 2) ^ _mul(a[1], 3) ^ a[2] ^ a[3]
                state[1][c] = a[0] ^ _mul(a[1], 2) ^ _mul(a[2], 3) ^ a[3]
                state[2][c] = a[0] ^ a[1] ^ _mul(a[2], 2) ^ _mul(a[3], 3)
                state[3][c] = _mul(a[0], 3) ^ a[1] ^ a[2] ^ _mul(a[3], 2)
        add_round_key(rnd)

    out = bytearray(16)
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = state[r][c]
    return bytes(out)


def aes_cbc_decrypt(key: bytes, data: bytes, iv: bytes | None = None,
                    unpad: bool = True) -> bytes:
    """CBC decryption. In a PDF the IV is the first 16 bytes of the stream."""
    if iv is None:
        if len(data) < 16:
            return b""
        iv, data = data[:16], data[16:]
    words = _expand_key(key)
    rounds = len(key) // 4 + 6
    out = bytearray()
    prev = iv
    for i in range(0, len(data) - 15, 16):
        block = data[i:i + 16]
        plain = _decrypt_block(block, words, rounds)
        out.extend(bytes(a ^ b for a, b in zip(plain, prev)))
        prev = block
    if unpad and out:
        n = out[-1]
        if 1 <= n <= 16 and len(out) >= n:
            del out[-n:]
    return bytes(out)


def aes_cbc_encrypt_nopad(key: bytes, data: bytes, iv: bytes) -> bytes:
    """Only needed for the revision-6 password hash."""
    words = _expand_key(key)
    rounds = len(key) // 4 + 6
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        block = bytes(a ^ b for a, b in zip(data[i:i + 16].ljust(16, b"\x00"), prev))
        prev = _encrypt_block(block, words, rounds)
        out.extend(prev)
    return bytes(out)


# ---------------------------------------------------------------------------
# key derivation
# ---------------------------------------------------------------------------


def _pad_password(password: bytes) -> bytes:
    return (password + PAD)[:32]


def file_key(password: bytes, o_entry: bytes, p: int, id0: bytes,
             revision: int, key_bytes: int, encrypt_metadata: bool) -> bytes:
    """Algorithm 2: the file encryption key, for revisions 2 to 4."""
    h = hashlib.md5()
    h.update(_pad_password(password))
    h.update(o_entry[:32])
    h.update(struct.pack("<i", p & 0xFFFFFFFF if p >= 0 else p))
    h.update(id0)
    if revision >= 4 and not encrypt_metadata:
        h.update(b"\xff\xff\xff\xff")
    key = h.digest()
    n = 5 if revision == 2 else max(5, min(16, key_bytes))
    if revision >= 3:
        for _ in range(50):
            key = hashlib.md5(key[:n]).digest()
    return key[:n]


def _hash_r6(password: bytes, salt: bytes, extra: bytes) -> bytes:
    """The iterated hash that revision 6 uses in place of plain SHA-256."""
    k = hashlib.sha256(password + salt + extra).digest()
    i = 0
    while True:
        k1 = (password + k + extra) * 64
        e = aes_cbc_encrypt_nopad(k[:16], k1, k[16:32])
        k = {0: hashlib.sha256, 1: hashlib.sha384, 2: hashlib.sha512}[
            sum(e[:16]) % 3](e).digest()
        i += 1
        if i >= 64 and e[-1] <= i - 32:
            return k[:32]


def check_user_password(password: bytes, enc: dict, id0: bytes):
    """Does this password open the document? Returns the file key, or None."""
    revision = int(enc.get("R", 2))
    o_entry = enc.get("O", b"")
    u_entry = enc.get("U", b"")
    p = int(enc.get("P", 0))
    length = int(enc.get("Length", 40))
    encrypt_metadata = enc.get("EncryptMetadata", True)

    if revision >= 5:
        salt = u_entry[32:40]
        if revision == 6:
            digest = _hash_r6(password, salt, b"")
        else:
            digest = hashlib.sha256(password + salt).digest()
        if digest != u_entry[:32]:
            return None
        key_salt = u_entry[40:48]
        inter = (_hash_r6(password, key_salt, b"") if revision == 6
                 else hashlib.sha256(password + key_salt).digest())
        return aes_cbc_decrypt(inter, enc.get("UE", b""), iv=b"\x00" * 16, unpad=False)

    key = file_key(password, o_entry, p, id0, revision, length // 8, encrypt_metadata)
    if revision == 2:
        ok = rc4(key, PAD) == u_entry[:32]
    else:
        h = hashlib.md5(PAD + id0).digest()
        data = rc4(key, h)
        for i in range(1, 20):
            data = rc4(bytes(b ^ i for b in key), data)
        ok = data[:16] == u_entry[:16]
    return key if ok else None


class Decryptor:
    """Per-object decryption, which is what the PDF format actually requires:
    every string and stream is encrypted with a key derived from the file key
    plus its own object and generation number."""

    def __init__(self, key: bytes, method: str, revision: int) -> None:
        self.key, self.method, self.revision = key, method, revision

    def _object_key(self, num: int, gen: int) -> bytes:
        if self.revision >= 5:
            return self.key  # AES-256 uses the file key unchanged
        extra = struct.pack("<I", num)[:3] + struct.pack("<I", gen)[:2]
        salt = b"sAlT" if self.method == "AESV2" else b""
        return hashlib.md5(self.key + extra + salt).digest()[:min(len(self.key) + 5, 16)]

    def decrypt(self, data: bytes, num: int, gen: int) -> bytes:
        if self.method == "Identity" or not data:
            return data
        key = self._object_key(num, gen)
        if self.method in ("AESV2", "AESV3"):
            return aes_cbc_decrypt(key, data)
        return rc4(key, data)


def method_of(enc: dict, resolve) -> str:
    """Which cipher the document uses for streams and strings."""
    v = int(resolve(enc.get("V", 0)) or 0)
    if v < 4:
        return "RC4"
    name = resolve(enc.get("StmF")) or "StdCF"
    filters = resolve(enc.get("CF")) or {}
    spec = resolve(filters.get(str(name))) if isinstance(filters, dict) else None
    cfm = resolve(spec.get("CFM")) if isinstance(spec, dict) else None
    return str(cfm) if cfm else ("AESV3" if v == 5 else "RC4")
