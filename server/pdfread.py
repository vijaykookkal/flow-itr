"""Reading PDFs with nothing but the standard library.

A PDF is not one kind of document, and the difference decides everything:

  * A *text* PDF stores glyph codes plus a font that maps them back to
    characters. Most statements, tax forms and payslips are like this, and
    their text can be recovered exactly.

  * A *scanned* PDF stores a photograph of each page and nothing else. The
    a statement that was printed and rescanned is like this: pages with not a
    single font between them. No text
    extractor in existence can pull text out of one, because there is no text
    to pull -- pypdf, pdfminer and pdftotext all return empty strings.

So this module does two different things. For a text PDF it returns the text.
For a scanned PDF it returns the *page images*, which are already inside the
file and can be sliced out byte for byte -- a DCTDecode stream is literally a
.jpg. The engine then reads those images the way it reads any other image,
which is how a file too large for any reader to open becomes page images
that every reader can.

Nothing here needs poppler, ghostscript, OCR or a pip install.
"""

from __future__ import annotations

import base64
import re
import struct
import zlib
from typing import Any

from . import pdfcrypt

# ---------------------------------------------------------------------------
# object model
# ---------------------------------------------------------------------------


class Name(str):
    """A PDF /Name. Subclasses str so it compares and hashes like one, but
    stays distinguishable from a PDF string literal."""

    __slots__ = ()


class Ref:
    __slots__ = ("num", "gen")

    def __init__(self, num: int, gen: int = 0) -> None:
        self.num, self.gen = num, gen

    def __repr__(self) -> str:  # pragma: no cover - debugging only
        return "Ref(%d)" % self.num


class Stream:
    __slots__ = ("dict", "raw", "doc", "num", "gen")

    def __init__(self, d: dict, raw: bytes, doc) -> None:
        self.dict, self.raw, self.doc = d, raw, doc
        self.num = self.gen = 0  # filled in by Document.get, for decryption

    def body(self) -> bytes:
        """The stream's bytes, decrypted but still filtered."""
        doc = self.doc
        crypt = getattr(doc, "decryptor", None) if doc is not None else None
        if crypt is None or self.dict.get("Type") == "XRef":
            return self.raw
        return crypt.decrypt(self.raw, self.num, self.gen)

    def data(self) -> bytes:
        return decode_stream(self.dict, self.body(), self.doc)


DELIM = b"()<>[]{}/%"
WS = b"\x00\t\n\x0c\r "
BACKSLASH = 0x5C


class Lexer:
    """Just enough of the PDF grammar to read objects."""

    def __init__(self, buf: bytes, pos: int = 0) -> None:
        self.buf, self.pos = buf, pos

    def skip(self) -> None:
        b = self.buf
        while self.pos < len(b):
            c = b[self.pos]
            if c in WS:
                self.pos += 1
            elif c == 0x25:  # '%' -- comment runs to end of line
                nl = b.find(b"\n", self.pos)
                self.pos = len(b) if nl < 0 else nl + 1
            else:
                return

    def token(self):
        self.skip()
        b = self.buf
        if self.pos >= len(b):
            return None
        c = b[self.pos]
        if c in b"[]{}":
            self.pos += 1
            return bytes([c])
        if c == 0x3C:  # '<'
            if b[self.pos + 1:self.pos + 2] == b"<":
                self.pos += 2
                return b"<<"
            self.pos += 1
            return b"<"
        if c == 0x3E:  # '>'
            if b[self.pos + 1:self.pos + 2] == b">":
                self.pos += 2
                return b">>"
            self.pos += 1
            return b">"
        if c in b"(/":
            self.pos += 1
            return bytes([c])
        start = self.pos
        while self.pos < len(b) and b[self.pos] not in WS and b[self.pos] not in DELIM:
            self.pos += 1
        if self.pos == start:
            self.pos += 1
        return b[start:self.pos]

    # -- literals ----------------------------------------------------------
    def read_name(self) -> Name:
        b = self.buf
        start = self.pos
        while self.pos < len(b) and b[self.pos] not in WS and b[self.pos] not in DELIM:
            self.pos += 1
        raw = b[start:self.pos]
        if b"#" in raw:
            raw = re.sub(rb"#([0-9A-Fa-f]{2})",
                         lambda m: bytes([int(m.group(1), 16)]), raw)
        return Name(raw.decode("latin-1"))

    def read_literal_string(self) -> bytes:
        b = self.buf
        out = bytearray()
        depth = 1
        escapes = {0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}
        while self.pos < len(b):
            c = b[self.pos]
            self.pos += 1
            if c == BACKSLASH:
                if self.pos >= len(b):
                    break
                n = b[self.pos]
                self.pos += 1
                if n in escapes:
                    out.append(escapes[n])
                elif n in (0x28, 0x29, BACKSLASH):
                    out.append(n)
                elif 0x30 <= n <= 0x37:  # octal escape, one to three digits
                    digits = chr(n)
                    while len(digits) < 3 and self.pos < len(b) and 0x30 <= b[self.pos] <= 0x37:
                        digits += chr(b[self.pos])
                        self.pos += 1
                    out.append(int(digits, 8) & 0xFF)
                elif n == 10:
                    pass  # line continuation
                elif n == 13:
                    if b[self.pos:self.pos + 1] == b"\n":
                        self.pos += 1
                else:
                    out.append(n)
            elif c == 0x28:
                depth += 1
                out.append(c)
            elif c == 0x29:
                depth -= 1
                if depth == 0:
                    break
                out.append(c)
            else:
                out.append(c)
        return bytes(out)

    def read_hex_string(self) -> bytes:
        b = self.buf
        end = b.find(b">", self.pos)
        if end < 0:
            end = len(b)
        digits = re.sub(rb"[^0-9A-Fa-f]", b"", b[self.pos:end])
        self.pos = end + 1
        if len(digits) % 2:
            digits += b"0"
        return bytes.fromhex(digits.decode("ascii"))

    def object(self, doc=None) -> Any:
        self.skip()
        b = self.buf
        if self.pos >= len(b):
            return None
        c = b[self.pos]

        if c == 0x2F:  # '/'
            self.pos += 1
            return self.read_name()
        if c == 0x28:  # '('
            self.pos += 1
            return self.read_literal_string()
        if c == 0x3C:  # '<' or '<<'
            if b[self.pos + 1:self.pos + 2] == b"<":
                self.pos += 2
                return self.dictionary(doc)
            self.pos += 1
            return self.read_hex_string()
        if c == 0x5B:  # '['
            self.pos += 1
            items = []
            while True:
                self.skip()
                if self.pos >= len(b):
                    break
                if b[self.pos] == 0x5D:
                    self.pos += 1
                    break
                before = self.pos
                items.append(self.object(doc))
                if self.pos == before:
                    self.pos += 1  # cannot advance; do not spin
            return items

        tok = self.token()
        if tok is None:
            return None
        if tok == b"true":
            return True
        if tok == b"false":
            return False
        if tok == b"null":
            return None
        if re.fullmatch(rb"[+-]?\d+", tok):
            # "N G R" is an indirect reference; anything else is an integer
            saved = self.pos
            t2 = self.token()
            if t2 is not None and re.fullmatch(rb"\d+", t2):
                if self.token() == b"R":
                    return Ref(int(tok), int(t2))
            self.pos = saved
            return int(tok)
        if re.fullmatch(rb"[+-]?(\d*\.\d*|\d+)", tok):
            try:
                return float(tok)
            except ValueError:
                return 0.0
        return Name(tok.decode("latin-1", "replace"))

    def dictionary(self, doc) -> Any:
        d: dict = {}
        b = self.buf
        while True:
            self.skip()
            if self.pos >= len(b):
                break
            if b[self.pos:self.pos + 2] == b">>":
                self.pos += 2
                break
            if b[self.pos] != 0x2F:
                if self.token() is None:  # malformed; skip so we cannot spin
                    break
                continue
            self.pos += 1
            key = self.read_name()
            d[key] = self.object(doc)

        # A dictionary immediately followed by `stream` is a stream object.
        saved = self.pos
        self.skip()
        if b[self.pos:self.pos + 6] == b"stream":
            self.pos += 6
            if b[self.pos:self.pos + 2] == b"\r\n":
                self.pos += 2
            elif b[self.pos:self.pos + 1] in (b"\n", b"\r"):
                self.pos += 1
            start = self.pos
            length = doc.resolve(d.get("Length")) if doc else d.get("Length")
            end = -1
            if isinstance(length, int) and 0 <= length <= len(b) - start:
                end = start + length
                if b"endstream" not in b[end:end + 20]:
                    end = -1  # /Length lied; fall back to searching
            if end < 0:
                end = b.find(b"endstream", start)
                if end < 0:
                    end = len(b)
                while end > start and b[end - 1] in (10, 13):
                    end -= 1
            after = b.find(b"endstream", end)
            self.pos = len(b) if after < 0 else after + 9
            return Stream(d, b[start:end], doc)
        self.pos = saved
        return d


# ---------------------------------------------------------------------------
# stream filters
# ---------------------------------------------------------------------------


def png_predictor(data: bytes, colors: int, bpc: int, columns: int) -> bytes:
    """Undo the PNG row filters that xref and ObjStm streams often use."""
    bpp = max(1, (colors * bpc + 7) // 8)
    row_len = (columns * colors * bpc + 7) // 8
    out = bytearray()
    prev = bytearray(row_len)
    pos = 0
    while pos < len(data):
        ft = data[pos]
        row = bytearray(data[pos + 1:pos + 1 + row_len])
        if len(row) < row_len:
            row.extend(b"\x00" * (row_len - len(row)))
        pos += 1 + row_len
        if ft == 1:
            for i in range(bpp, row_len):
                row[i] = (row[i] + row[i - bpp]) & 0xFF
        elif ft == 2:
            for i in range(row_len):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(row_len):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(row_len):
                a = row[i - bpp] if i >= bpp else 0
                bb = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + bb - c
                pa, pb, pc = abs(p - a), abs(p - bb), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (bb if pb <= pc else c)
                row[i] = (row[i] + pr) & 0xFF
        out.extend(row)
        prev = row
    return bytes(out)


def lzw_decode(data: bytes, early: int = 1) -> bytes:
    out = bytearray()
    table = [bytes([i]) for i in range(256)] + [b"", b""]
    prev = None
    width, buf, nbits = 9, 0, 0
    for byte in data:
        buf = (buf << 8) | byte
        nbits += 8
        while nbits >= width:
            nbits -= width
            code = (buf >> nbits) & ((1 << width) - 1)
            if code == 256:
                table = [bytes([i]) for i in range(256)] + [b"", b""]
                width, prev = 9, None
                continue
            if code == 257:
                return bytes(out)
            if prev is None:
                if code >= len(table):
                    return bytes(out)
                entry = table[code]
            elif code < len(table):
                entry = table[code]
                table.append(prev + entry[:1])
            else:
                entry = prev + prev[:1]
                table.append(entry)
            out.extend(entry)
            prev = entry
            if len(table) + early >= (1 << width) and width < 12:
                width += 1
    return bytes(out)


def ascii85_decode(data: bytes) -> bytes:
    data = re.sub(rb"\s", b"", data)
    if data.startswith(b"<~"):
        data = data[2:]
    end = data.find(b"~>")
    if end >= 0:
        data = data[:end]
    try:
        return base64.a85decode(data)
    except Exception:  # noqa: BLE001
        return b""


def inflate(data: bytes) -> bytes:
    """zlib, forgiving of the truncated and mislabelled streams real PDFs hold."""
    try:
        return zlib.decompress(data)
    except zlib.error:
        pass
    try:
        return zlib.decompressobj().decompress(data)      # truncated but usable
    except zlib.error:
        pass
    try:
        return zlib.decompressobj(-15).decompress(data[1:])  # missing header
    except zlib.error:
        return b""


# Filters whose output is an image, not bytes that mean anything here.
IMAGE_FILTERS = {"DCTDecode", "DCT", "JPXDecode", "JBIG2Decode", "CCITTFaxDecode", "CCF"}


def decode_stream(d: dict, raw: bytes, doc) -> bytes:
    res = doc.resolve if doc is not None else (lambda x: x)
    filters = res(d.get("Filter"))
    if filters is None:
        return raw
    if not isinstance(filters, list):
        filters = [filters]
    parms = res(d.get("DecodeParms"))
    if parms is None:
        parms = res(d.get("DP"))
    if not isinstance(parms, list):
        parms = [parms] * len(filters)

    data = raw
    for i, f in enumerate(filters):
        f = res(f)
        pm = res(parms[i]) if i < len(parms) else None
        pm = pm if isinstance(pm, dict) else {}
        if f in ("FlateDecode", "Fl"):
            data = inflate(data)
        elif f in ("LZWDecode", "LZW"):
            data = lzw_decode(data, int(res(pm.get("EarlyChange", 1)) or 1))
        elif f in ("ASCIIHexDecode", "AHx"):
            hx = re.sub(rb"[^0-9A-Fa-f]", b"", data.split(b">")[0])
            if len(hx) % 2:
                hx += b"0"
            data = bytes.fromhex(hx.decode("ascii"))
        elif f in ("ASCII85Decode", "A85"):
            data = ascii85_decode(data)
        elif f in ("RunLengthDecode", "RL"):
            out, pos = bytearray(), 0
            while pos < len(data):
                n = data[pos]
                pos += 1
                if n == 128:
                    break
                if n < 128:
                    out.extend(data[pos:pos + n + 1])
                    pos += n + 1
                else:
                    if pos < len(data):
                        out.extend(bytes([data[pos]]) * (257 - n))
                    pos += 1
            data = bytes(out)
        elif f in IMAGE_FILTERS:
            return data  # the caller deals with this as an image

        pred = res(pm.get("Predictor", 1)) or 1
        if isinstance(pred, (int, float)) and pred >= 10:
            data = png_predictor(data,
                                 int(res(pm.get("Colors", 1)) or 1),
                                 int(res(pm.get("BitsPerComponent", 8)) or 8),
                                 int(res(pm.get("Columns", 1)) or 1))
    return data


# ---------------------------------------------------------------------------
# document
# ---------------------------------------------------------------------------

OBJ_RE = re.compile(rb"(?<![0-9])(\d{1,10})\s+(\d{1,5})\s+obj\b")


class Document:
    """A PDF read by scanning for objects rather than trusting the xref table.

    Real-world PDFs are routinely produced by tools that get the cross-reference
    offsets wrong, and a reader that insists on the xref simply fails on them.
    Scanning finds every object that is physically present; later definitions
    win, which is also what an incremental update means.
    """

    def __init__(self, raw: bytes, passwords: list[bytes] | None = None) -> None:
        self.raw = raw
        self.offsets: dict[int, int] = {}
        self.gens: dict[int, int] = {}
        self.cache: dict[int, Any] = {}
        self.compressed: dict[int, tuple[int, int]] = {}
        self.decryptor = None
        self.encrypted = False
        self.locked = False  # encrypted, and none of the passwords fit

        for m in OBJ_RE.finditer(raw):
            num = int(m.group(1))
            self.offsets[num] = m.end()
            self.gens[num] = int(m.group(2))
        self._setup_encryption(passwords or [b""])
        self._index_object_streams()

    # -- object access -----------------------------------------------------
    def get(self, num: int) -> Any:
        if num in self.cache:
            return self.cache[num]
        self.cache[num] = None  # guard against reference cycles
        obj = None
        if num in self.offsets:
            obj = Lexer(self.raw, self.offsets[num]).object(self)
        elif num in self.compressed:
            stm_num, index = self.compressed[num]
            obj = self._from_objstm(stm_num, index)
        if isinstance(obj, Stream):
            obj.num, obj.gen = num, self.gens.get(num, 0)
        self.cache[num] = obj
        return obj

    def _setup_encryption(self, passwords: list[bytes]) -> None:
        """Find the /Encrypt dictionary and work out the file key.

        This runs before anything else is decoded, because an encrypted stream
        that is merely inflated produces noise, and noise looks exactly like a
        document with no text in it."""
        enc_ref = None
        id0 = b""
        for m in re.finditer(rb"/Encrypt\b", self.raw):
            # The trailer holding /Encrypt also holds the /ID the key needs.
            start = self.raw.rfind(b"<<", max(0, m.start() - 4000), m.start())
            lex = Lexer(self.raw, start if start >= 0 else m.start())
            try:
                trailer = lex.object(None)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(trailer, Stream):
                trailer = trailer.dict
            if not isinstance(trailer, dict) or "Encrypt" not in trailer:
                continue
            enc_ref = trailer["Encrypt"]
            ids = trailer.get("ID")
            if isinstance(ids, list) and ids and isinstance(ids[0], bytes):
                id0 = ids[0]
            break
        if enc_ref is None:
            return

        self.encrypted = True
        enc = enc_ref
        if isinstance(enc, Ref) and enc.num in self.offsets:
            enc = Lexer(self.raw, self.offsets[enc.num]).object(None)
        if isinstance(enc, Stream):
            enc = enc.dict
        if not isinstance(enc, dict):
            self.locked = True
            return

        method = pdfcrypt.method_of(enc, lambda x: x)
        revision = int(enc.get("R", 2) or 2)
        for password in passwords:
            key = pdfcrypt.check_user_password(password, enc, id0)
            if key:
                self.decryptor = pdfcrypt.Decryptor(key, method, revision)
                return
        self.locked = True

    def resolve(self, obj: Any, depth: int = 0) -> Any:
        while isinstance(obj, Ref) and depth < 32:
            obj = self.get(obj.num)
            depth += 1
        return obj

    def dget(self, d: Any, *keys: str, default: Any = None) -> Any:
        """Resolve d[key] for the first key present, following references."""
        d = self.resolve(d)
        if isinstance(d, Stream):
            d = d.dict
        if not isinstance(d, dict):
            return default
        for k in keys:
            if k in d:
                return self.resolve(d[k])
        return default

    def _index_object_streams(self) -> None:
        for num in list(self.offsets):
            try:
                obj = Lexer(self.raw, self.offsets[num]).object(self)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, Stream) and obj.dict.get("Type") == "ObjStm":
                obj.num, obj.gen = num, self.gens.get(num, 0)
                self.cache[num] = obj
                try:
                    n = int(self.resolve(obj.dict.get("N")) or 0)
                except (TypeError, ValueError):
                    continue
                self._register_objstm(num, obj, n)

    def _register_objstm(self, stm_num: int, stm: Stream, n: int) -> None:
        try:
            data = stm.data()
        except Exception:  # noqa: BLE001
            return
        header = data[:int(self.resolve(stm.dict.get("First")) or 0)]
        nums = re.findall(rb"(\d+)\s+(\d+)", header)
        for i, (obj_num, _off) in enumerate(nums[:n]):
            num = int(obj_num)
            if num not in self.offsets:
                self.compressed[num] = (stm_num, i)

    def _from_objstm(self, stm_num: int, index: int) -> Any:
        stm = self.cache.get(stm_num)
        if not isinstance(stm, Stream):
            return None
        data = stm.data()
        first = int(self.resolve(stm.dict.get("First")) or 0)
        pairs = re.findall(rb"(\d+)\s+(\d+)", data[:first])
        if index >= len(pairs):
            return None
        return Lexer(data, first + int(pairs[index][1])).object(self)

    # -- page tree ---------------------------------------------------------
    def trailer_root(self) -> Any:
        for m in re.finditer(rb"trailer", self.raw):
            lex = Lexer(self.raw, m.end())
            d = lex.object(self)
            if isinstance(d, dict) and "Root" in d:
                cat = self.resolve(d["Root"])
                if isinstance(cat, dict):
                    return cat
        # xref-stream files have no `trailer` keyword; the catalog is an object
        for num in list(self.offsets) + list(self.compressed):
            obj = self.get(num)
            if isinstance(obj, Stream) and obj.dict.get("Type") == "XRef" and "Root" in obj.dict:
                cat = self.resolve(obj.dict["Root"])
                if isinstance(cat, dict):
                    return cat
        for num in list(self.offsets) + list(self.compressed):
            obj = self.resolve(self.get(num))
            if isinstance(obj, dict) and obj.get("Type") == "Catalog":
                return obj
        return None

    INHERITED = ("Resources", "MediaBox", "CropBox", "Rotate")

    def pages(self) -> list[dict]:
        """Page dictionaries in reading order, with inherited keys filled in."""
        root = self.trailer_root()
        out: list[dict] = []
        seen: set[int] = set()

        def walk(node: Any, inherited: dict, depth: int) -> None:
            node = self.resolve(node)
            if not isinstance(node, dict) or depth > 64 or len(out) > 5000:
                return
            passed = dict(inherited)
            for key in self.INHERITED:
                if key in node:
                    passed[key] = node[key]
            kids = self.resolve(node.get("Kids"))
            if node.get("Type") == "Page" or (kids is None and "Contents" in node):
                page = dict(passed)
                page.update(node)
                out.append(page)
                return
            for kid in kids or []:
                key = kid.num if isinstance(kid, Ref) else id(kid)
                if key in seen:
                    continue
                seen.add(key)
                walk(kid, passed, depth + 1)

        if isinstance(root, dict):
            walk(root.get("Pages"), {}, 0)
        if out:
            return out

        # No usable page tree: fall back to every object that looks like a page.
        for num in sorted(set(self.offsets) | set(self.compressed)):
            obj = self.resolve(self.get(num))
            if isinstance(obj, dict) and obj.get("Type") == "Page":
                out.append(obj)
        return out

    def content_of(self, page: dict) -> bytes:
        contents = self.resolve(page.get("Contents"))
        parts = []
        for item in (contents if isinstance(contents, list) else [contents]):
            item = self.resolve(item)
            if isinstance(item, Stream):
                try:
                    parts.append(item.data())
                except Exception:  # noqa: BLE001
                    continue
        return b"\n".join(parts)


# ---------------------------------------------------------------------------
# text
# ---------------------------------------------------------------------------


def parse_tounicode(data: bytes) -> dict[int, str]:
    """The font's own code-to-character table, which is the only reliable one.

    Subset fonts renumber their glyphs, so without this a statement comes out
    as plausible-looking gibberish -- which is far worse than coming out empty,
    because nobody notices."""
    table: dict[int, str] = {}

    def text_of(tok: bytes) -> str:
        try:
            raw = bytes.fromhex(tok.decode("ascii"))
        except ValueError:
            return ""
        if len(raw) % 2:
            raw += b"\x00"
        return raw.decode("utf-16-be", "replace")

    for block in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
        for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            table[int(src, 16)] = text_of(dst)
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", data, re.S):
        for lo, hi, dst in re.findall(
                rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            start, end, base = int(lo, 16), int(hi, 16), int(dst, 16)
            for i in range(min(end - start, 65535) + 1):
                table[start + i] = chr(base + i) if base + i < 0x110000 else ""
        for lo, _hi, arr in re.findall(
                rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", block, re.S):
            start = int(lo, 16)
            for i, dst in enumerate(re.findall(rb"<([0-9A-Fa-f]+)>", arr)):
                table[start + i] = text_of(dst)
    return table


class Font:
    __slots__ = ("two_byte", "table")

    def __init__(self, two_byte: bool, table: dict[int, str]) -> None:
        self.two_byte, self.table = two_byte, table

    def decode(self, raw: bytes) -> str:
        if self.two_byte:
            codes = [int.from_bytes(raw[i:i + 2], "big") for i in range(0, len(raw) - 1, 2)]
        else:
            codes = list(raw)
        if self.table:
            return "".join(self.table.get(c, "") for c in codes)
        if self.two_byte:
            return raw.decode("utf-16-be", "replace")
        return raw.decode("latin-1", "replace")


def fonts_of(doc: Document, page: dict) -> dict[str, Font]:
    out: dict[str, Font] = {}
    res = doc.dget(page, "Resources", default={})
    table = doc.dget(res, "Font", default={})
    if not isinstance(table, dict):
        return out
    for key, ref in table.items():
        font = doc.resolve(ref)
        if not isinstance(font, dict):
            continue
        two_byte = font.get("Subtype") == "Type0"
        enc = doc.resolve(font.get("Encoding"))
        if isinstance(enc, Name) and "Identity" in enc:
            two_byte = True
        mapping: dict[int, str] = {}
        tu = doc.resolve(font.get("ToUnicode"))
        if isinstance(tu, Stream):
            try:
                mapping = parse_tounicode(tu.data())
            except Exception:  # noqa: BLE001
                mapping = {}
        out[str(key)] = Font(two_byte, mapping)
    return out


SHOW_OPS = {b"Tj", b"TJ", b"'", b'"'}


def text_of_page(doc: Document, page: dict) -> str:
    """Text of one page, laid out by where the page actually puts it.

    A PDF has no lines and no words -- only glyphs at coordinates. Statements
    in particular set every cell of every table with its own positioning
    operator, so a reader that starts a new line at each one turns a table into
    a column of single words and loses the row structure that makes it a table.
    What decides a line break is therefore the *vertical* position: text that
    stays on the same baseline stays on the same line, separated by a space.
    """
    content = doc.content_of(page)
    if not content:
        return ""
    fonts = fonts_of(doc, page)
    current = Font(False, {})
    lex = Lexer(content)
    stack: list = []
    pieces: list[str] = []
    lines: list[tuple[float, str]] = []

    # Text state: the translation part of the text and line matrices, plus the
    # leading used by T* and the quote operators.
    x = y = 0.0
    line_x = line_y = 0.0
    leading = 0.0
    baseline = None

    def flush() -> None:
        nonlocal baseline
        text = "".join(pieces).rstrip()
        if text:
            lines.append((baseline if baseline is not None else 0.0, text))
        pieces.clear()
        baseline = None

    def move_to(nx: float, ny: float) -> None:
        """Account for a jump to a new position before more text is shown."""
        nonlocal baseline
        if baseline is None:
            baseline = ny
        elif abs(ny - baseline) > 1.6:      # a genuinely different baseline
            flush()
            baseline = ny
        elif pieces and not "".join(pieces).endswith(" "):
            pieces.append(" ")              # same line, new cell

    def number(v) -> float:
        return float(v) if isinstance(v, (int, float)) else 0.0

    while True:
        lex.skip()
        if lex.pos >= len(content):
            break
        c = content[lex.pos]
        if c in b"/(<[" or (0x30 <= c <= 0x39) or c in b"+-.":
            before = lex.pos
            stack.append(lex.object(doc))
            if lex.pos == before:
                lex.pos += 1
            if len(stack) > 64:
                del stack[:-32]
            continue

        op = lex.token()
        if op is None:
            break

        if op == b"Tf" and len(stack) >= 2:
            current = fonts.get(str(stack[-2]), current)
        elif op == b"TL" and stack:
            leading = number(stack[-1])
        elif op == b"BT":
            flush()
            x = y = line_x = line_y = 0.0
        elif op == b"ET":
            flush()
        elif op == b"Tm" and len(stack) >= 6:
            line_x, line_y = number(stack[-2]), number(stack[-1])
            x, y = line_x, line_y
            move_to(x, y)
        elif op in (b"Td", b"TD") and len(stack) >= 2:
            if op == b"TD":
                leading = -number(stack[-1])
            line_x += number(stack[-2])
            line_y += number(stack[-1])
            x, y = line_x, line_y
            move_to(x, y)
        elif op == b"T*":
            line_y -= leading
            x, y = line_x, line_y
            move_to(x, y)
        elif op in SHOW_OPS:
            if op in (b"'", b'"'):
                line_y -= leading
                x, y = line_x, line_y
                move_to(x, y)
            if baseline is None:
                baseline = y
            if op == b"TJ" and stack and isinstance(stack[-1], list):
                for part in stack[-1]:
                    if isinstance(part, bytes):
                        pieces.append(current.decode(part))
                    elif isinstance(part, (int, float)) and part < -180:
                        pieces.append(" ")   # a wide kern is a word gap
            else:
                for part in reversed(stack):
                    if isinstance(part, bytes):
                        pieces.append(current.decode(part))
                        break
        stack.clear()

    flush()

    # Content streams are drawn in whatever order the producer chose, which is
    # not always top to bottom; sorting by baseline restores reading order and
    # rejoins cells that were emitted as separate runs.
    merged: list[tuple[float, str]] = []
    for baseline_y, text in sorted(lines, key=lambda r: -r[0]):
        if merged and abs(merged[-1][0] - baseline_y) <= 1.6:
            merged[-1] = (merged[-1][0], merged[-1][1] + " " + text)
        else:
            merged.append((baseline_y, text))
    return "\n".join(text for _y, text in merged)


# ---------------------------------------------------------------------------
# images
# ---------------------------------------------------------------------------


def _png(width: int, height: int, colour_type: int, bpc: int, pixels: bytes) -> bytes:
    """Wrap raw samples as a PNG. zlib is in the standard library, and PNG is
    just a header plus zlib-compressed rows, so no imaging library is needed."""
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[colour_type]
    row_len = (width * channels * bpc + 7) // 8
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # filter: none
        rows.extend(pixels[y * row_len:(y + 1) * row_len].ljust(row_len, b"\x00"))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, bpc, colour_type, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
            + chunk(b"IEND", b""))


def image_of(doc: Document, stream: Stream):
    """One XObject image as (extension, bytes), or None if unsupported.

    A DCTDecode stream is a complete JPEG file already, so it is copied out
    verbatim -- no decoding, no re-encoding, no loss."""
    d = stream.dict
    filters = doc.resolve(d.get("Filter"))
    if not isinstance(filters, list):
        filters = [filters] if filters else []
    filters = [doc.resolve(f) for f in filters]

    if any(f in ("DCTDecode", "DCT") for f in filters):
        blob = stream.body()
        for f in filters:
            if f in ("ASCII85Decode", "A85"):
                blob = ascii85_decode(blob)
        start = blob.find(b"\xff\xd8")
        return ("jpg", blob[start:] if start >= 0 else blob)
    if any(f == "JPXDecode" for f in filters):
        return ("jp2", stream.body())
    if any(f in ("JBIG2Decode", "CCITTFaxDecode", "CCF") for f in filters):
        return None  # fax/JBIG2 decoding needs more than a tax tool should carry

    width = int(doc.dget(d, "Width", "W", default=0) or 0)
    height = int(doc.dget(d, "Height", "H", default=0) or 0)
    bpc = int(doc.dget(d, "BitsPerComponent", "BPC", default=8) or 8)
    if width <= 0 or height <= 0 or bpc not in (1, 2, 4, 8):
        return None

    space = doc.dget(d, "ColorSpace", "CS")
    if isinstance(space, list) and space:
        space = doc.resolve(space[0])
    name = str(space) if space is not None else ""
    if name in ("DeviceGray", "G", "CalGray") or doc.dget(d, "ImageMask", "IM") is True:
        colour_type = 0
    elif name in ("DeviceRGB", "RGB", "CalRGB"):
        colour_type = 2
    else:
        return None  # indexed, CMYK and separation images need a palette pass

    try:
        pixels = stream.data()
    except Exception:  # noqa: BLE001
        return None
    if not pixels:
        return None
    return ("png", _png(width, height, colour_type, bpc, pixels))


def page_images(doc: Document, page: dict) -> list[Stream]:
    """Image XObjects used by a page, in resource order."""
    res = doc.dget(page, "Resources", default={})
    xobjects = doc.dget(res, "XObject", default={})
    out: list[Stream] = []
    if not isinstance(xobjects, dict):
        return out
    for _key, ref in xobjects.items():
        obj = doc.resolve(ref)
        if isinstance(obj, Stream) and doc.dget(obj.dict, "Subtype", "S") == "Image":
            out.append(obj)
    return out


# ---------------------------------------------------------------------------
# the part the rest of the server uses
# ---------------------------------------------------------------------------

# Below this, a "text layer" is too thin to be the document's real content --
# a scanned page often carries a few characters of header furniture.
MIN_TEXT_PER_PAGE = 40


def read(raw: bytes, passwords: list[bytes] | None = None) -> dict:
    """What is in this PDF, and in what form.

    Returns {"pages": [{"text": str, "images": [(ext, bytes)]}, ...],
             "scanned": bool}. `scanned` is True when the file carries
    essentially no text, which is the case that needs page images.
    """
    doc = Document(raw, passwords)
    pages = doc.pages()
    out = []
    total_text = 0
    for page in pages:
        try:
            text = text_of_page(doc, page)
        except Exception:  # noqa: BLE001
            text = ""
        total_text += len(text.strip())
        out.append({"text": text, "page": page, "doc": doc})
    scanned = bool(pages) and total_text < MIN_TEXT_PER_PAGE * len(pages)
    return {"pages": out, "scanned": scanned, "doc": doc, "page_count": len(pages)}


def text(raw: bytes, passwords: list[bytes] | None = None) -> str:
    """All the text in a PDF, page by page. Empty for a scanned document."""
    got = read(raw, passwords)
    chunks = []
    for i, page in enumerate(got["pages"], 1):
        body = page["text"].strip()
        if body:
            chunks.append("--- page %d ---\n%s" % (i, body))
    return "\n\n".join(chunks)


# A scan of a page is a large raster. Anything much smaller is a logo, a rule,
# a signature or -- in the statements that are built to resist copying -- a
# one-glyph bitmap, and a page assembled from those tells the reader nothing.
MIN_PAGE_IMAGE_PIXELS = 500


def is_page_sized(doc: "Document", stream: Stream) -> bool:
    width = doc.dget(stream.dict, "Width", "W", default=0) or 0
    height = doc.dget(stream.dict, "Height", "H", default=0) or 0
    try:
        width, height = int(width), int(height)
    except (TypeError, ValueError):
        return False
    return width >= MIN_PAGE_IMAGE_PIXELS and height >= MIN_PAGE_IMAGE_PIXELS


def images(raw: bytes, limit: int = 200,
           passwords: list[bytes] | None = None) -> list[tuple[int, str, bytes]]:
    """Page images as (page number, extension, bytes), in page order."""
    return images_of_doc(Document(raw, passwords), limit)


def images_of_doc(doc: "Document", limit: int = 200) -> list[tuple[int, str, bytes]]:
    """Page images of an already-parsed document.

    A scanned page is usually one big image, but some producers slice a page
    into strips, so every image on the page is returned and the caller keeps
    them in order."""
    out: list[tuple[int, str, bytes]] = []
    for number, page in enumerate(doc.pages(), 1):
        for stream in page_images(doc, page):
            if not is_page_sized(doc, stream):
                continue
            got = image_of(doc, stream)
            if got is None:
                continue
            out.append((number, got[0], got[1]))
            if len(out) >= limit:
                return out
    return out
