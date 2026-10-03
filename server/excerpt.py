"""The printed words behind a figure.

A citation says where a figure came from: "Form 16 Part B.pdf#10(f)". That is a
claim, and until now checking it meant finding the file, opening it and hunting
for the number. This finds the line itself -- the text the reader was given,
with the lines either side of it -- so the claim can be checked where the
figure is shown.

It searches the same text the engine read: the conversions in the cache,
keyed by the document's content hash. That matters. An excerpt lifted from
anything else would be evidence about a different reading of the document.

It finds a figure by its digits, however the document groups them (314363,
3,14,363, 314,363.00), and allows for one thing extraction is told to do: round
paise to the nearest rupee. It does not guess beyond that. A figure that is not
printed -- a total the document never states, an amount read off a page image
-- is reported as not found, with the reason, rather than matched to something
that merely looks close.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import convert, paths, sources

TEXT_SUFFIXES = {".txt", ".csv", ".tsv"}
PAGE_MARK = re.compile(r"^--- page (\d+) of (\d+) ---\s*$")
PAGE_HINT = re.compile(r"(?:^|[\s#(,])p(?:age)?\.?\s*(\d+)", re.I)

# Below this a figure matches dates, serial numbers and page counts as readily
# as itself, and an excerpt that is probably the wrong line is worse than none.
MIN_SEARCHABLE = 100
CONTEXT = 2          # lines shown either side
MAX_MATCHES = 4
MAX_LINE = 320       # a spreadsheet row can run to thousands of characters

_HASHES: dict[tuple, str] = {}


def _sha(path: Path) -> str:
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _HASHES:
        _HASHES[key] = sources.sha256_file(path)
    return _HASHES[key]


def split_cite(cite: str) -> tuple[str, str]:
    """('01_salary/Form 16.pdf', '10(f)') from '01_salary/Form 16.pdf#10(f)'."""
    name, _, hint = str(cite or "").partition("#")
    return name.replace("\\", "/").strip().strip("/"), hint.strip()


def locate(ay: str, name: str) -> tuple[dict | None, str]:
    """The document a citation names, and the member inside it if it is an archive.

    A citation is written by the engine from what it was shown, so it may carry
    the whole relative path, only the tail of it, or only the file name. All
    three are accepted, most specific first. Nothing here ever turns the cited
    text into a path: it is only ever compared with documents already known.
    """
    if not name:
        return None, ""
    docs = sources.all_documents(ay)
    by_path = {d["path"]: d for d in docs}
    if name in by_path:
        return by_path[name], ""

    # 'invoices.zip/Benq_monitor.pdf': the archive is the document.
    parts = name.split("/")
    for i in range(len(parts) - 1, 0, -1):
        head = "/".join(parts[:i])
        hit = by_path.get(head) or next(
            (d for d in docs if d["path"].endswith("/" + head)
             or d["path"].rsplit("/", 1)[-1] == head), None)
        if hit and hit.get("is_archive"):
            return hit, "/".join(parts[i:])

    tail = [d for d in docs if d["path"].endswith("/" + name)]
    if tail:
        return tail[0], ""
    base = name.rsplit("/", 1)[-1]
    named = [d for d in docs if d["path"].rsplit("/", 1)[-1] == base]
    return (named[0], "") if named else (None, "")


def texts_for(ay: str, doc: dict, member: str = "") -> tuple[list[Path], bool]:
    """The readable text of a document, and whether it was read as images."""
    src = Path(doc["abs"])
    if src.suffix.lower() in TEXT_SUFFIXES:
        return [src], False
    cache = convert.derived_root(ay) / _sha(src)[:16]
    if not cache.is_dir():
        return [], False
    made = sorted(p for p in cache.iterdir() if p.is_file())
    texts = [p for p in made if p.suffix.lower() in TEXT_SUFFIXES]
    if member:
        stem = Path(member).stem.lower()
        chosen = [p for p in texts if p.stem.lower() == stem or p.stem.lower().startswith(stem)]
        texts = chosen or texts
    images = any(p.suffix.lower() == ".png" for p in made)
    return texts, images and not texts


def pattern_for(amount) -> re.Pattern | None:
    """A figure, however it is grouped, and as it stood before rounding."""
    text = str(amount if amount is not None else "").replace(",", "").strip().lstrip("-+")
    m = re.fullmatch(r"(\d+)(?:\.(\d+))?", text)
    if not m:
        return None
    whole, frac = m.group(1).lstrip("0") or "0", m.group(2) or ""
    if int(whole) < MIN_SEARCHABLE:
        return None
    grouped = ",?".join(whole)
    if frac.strip("0"):
        # Stated to the paisa or the cent: match that, not a rounding of it.
        alternatives = [grouped + r"\." + frac.rstrip("0") + "0*"]
    else:
        alternatives = [grouped + r"(?:\.\d+)?",
                        # 314363 extracted from a printed 314362.54
                        ",?".join(str(int(whole) - 1)) + r"\.[5-9]\d*"]
    return re.compile(r"(?<![\d,])(?<!\d\.)(?:" + "|".join(alternatives) + r")(?!\d)(?!,\d)")


def _trim(line: str, start: int, end: int) -> tuple[str, int, int]:
    """A long row cut down around the figure, with the cut marked."""
    if len(line) <= MAX_LINE:
        return line, start, end
    lo = max(0, start - MAX_LINE // 2)
    hi = min(len(line), lo + MAX_LINE)
    lo = max(0, hi - MAX_LINE)
    text = ("…" if lo else "") + line[lo:hi] + ("…" if hi < len(line) else "")
    shift = lo - (1 if lo else 0)
    return text, start - shift, end - shift


def despace(line: str) -> str:
    """'7 9 6 8 6 6 9  T o t a l' -> '7968669 Total'.

    Some PDFs position every glyph separately, and their text comes out with a
    space between each character and two between words. Nothing can be found
    in that, and nobody can read it. Only a line that is plainly letter-spaced
    is touched: the test is that nearly every token is a single character.
    """
    tokens = line.split(" ")
    solid = [t for t in tokens if t]
    if len(solid) < 6 or sum(1 for t in solid if len(t) == 1) < 0.8 * len(solid):
        return line
    return re.sub(r" {2,}", " ", re.sub(r"(?<=\S) (?=\S)", "", line)).strip()


def indian(amount) -> str | None:
    """7968669 as the return prints it: 79,68,669. None below a thousand."""
    text = str(amount if amount is not None else "").replace(",", "").strip().lstrip("-+")
    if not re.fullmatch(r"\d+", text) or len(text) < 4:
        return None
    head, tail = text[:-3], text[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + groups + [tail])


def search(path: Path, pattern: re.Pattern, grouped: str | None = None) -> list[dict]:
    try:
        raw = path.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    lines = [despace(line) for line in raw]
    out, page = [], None
    pages = {}
    for i, line in enumerate(lines):
        mark = PAGE_MARK.match(line)
        if mark:
            page = int(mark.group(1))
        pages[i] = page
    for i, line in enumerate(lines):
        if PAGE_MARK.match(line):
            continue
        m = pattern.search(line)
        if not m and grouped and line != raw[i]:
            # A letter-spaced line has lost the gaps between its columns, so a
            # line number runs straight into the amount beside it: "6" and
            # "79,68,669" come out as "679,68,669". The figure's edges cannot
            # be tested there. Its commas can: the grouping the return prints
            # is specific enough to stand on its own.
            m = re.search(re.escape(grouped), line)
        if not m:
            continue
        text, start, end = _trim(line, m.start(), m.end())

        def near(j):
            return [lines[k][:MAX_LINE] for k in j
                    if 0 <= k < len(lines) and not PAGE_MARK.match(lines[k]) and lines[k].strip()]

        out.append({
            "file": path.name, "page": pages.get(i), "line": i + 1,
            "text": text, "start": start, "end": end,
            "before": near(range(i - CONTEXT, i)),
            "after": near(range(i + 1, i + 1 + CONTEXT)),
        })
    return out


def find(ay: str, cite: str, amount=None, source: str = "") -> dict:
    name, hint = split_cite(cite)
    doc, member = locate(ay, name)
    if doc is None and source:
        doc, member = locate(ay, split_cite(source)[0])
    result = {"found": False, "cite": cite, "document": doc["path"] if doc else None,
              "member": member, "matches": [], "why": ""}
    page_hint = PAGE_HINT.search(" " + hint)
    result["page"] = int(page_hint.group(1)) if page_hint else None

    if doc is None:
        result["why"] = (f"No document named {name.rsplit('/', 1)[-1]!r} is among this "
                         f"return's documents." if name else "This figure carries no citation.")
        return result

    texts, images_only = texts_for(ay, doc, member)
    if not texts:
        result["why"] = ("This document was read as page images, so there is no text to quote. "
                         "Open the document to see the figure."
                         if images_only else
                         "This document has not been converted to text yet. It is converted the "
                         "first time a schedule reads it.")
        return result

    pattern = pattern_for(amount)
    if pattern is None:
        result["why"] = ("The amount is too small to pick out reliably: it would match dates and "
                         "serial numbers as readily as itself. Open the document at the cited "
                         "place." if amount not in (None, "") else
                         "There is no amount to look for.")
        return result

    grouped = indian(amount)
    matches = []
    for path in texts:
        matches.extend(search(path, pattern, grouped))
    if not matches:
        result["why"] = ("These digits are not printed in the document's text. The figure may be "
                         "a total the document does not state, or be printed in another form.")
        return result

    wanted = result["page"]
    matches.sort(key=lambda m: (0 if wanted and m["page"] == wanted else 1))
    result.update(found=True, total=len(matches), matches=matches[:MAX_MATCHES])
    return result


def original(ay: str, path: str) -> Path | None:
    """The document itself, for opening -- only if it is one of this return's."""
    doc, member = locate(ay, str(path or "").replace("\\", "/").strip().strip("/"))
    if doc is None:
        return None
    src = Path(doc["abs"])
    root = paths.source_root(ay).resolve()
    try:
        src.resolve().relative_to(root)
    except ValueError:
        return None
    if member:
        # A member of an archive: the copy unpacked for reading, if there is one.
        cache = convert.derived_root(ay) / _sha(src)[:16]
        wanted = Path(member).name.lower()
        for p in sorted(cache.glob("*")) if cache.is_dir() else []:
            if p.name.lower() == wanted:
                return p
    return src if src.is_file() else None
