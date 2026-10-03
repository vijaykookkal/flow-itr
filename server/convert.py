"""Converting formats the engine cannot read into ones it can.

The engine is deliberately restricted to Read, Glob and Grep -- no shell, no
code execution -- so it cannot open a spreadsheet. But broker tax P&L reports,
bank statements and consolidated foreign-income reports arrive as .xlsx more
often than not, and those carry the numbers that matter most.

Rather than hand the model a shell, the server converts here. Both .xlsx and
.docx are zip archives of XML, so this needs nothing beyond the standard
library, and the conversion is a pure function of the file's content hash --
so it is cached, and a document that has not changed is never re-converted.

Conversions are written to the cache in the Flow home and that directory is granted to the
engine alongside the originals. The derived CSV is a faithful transcription,
never a summary: no rows are dropped, merged or reformatted beyond turning
Excel date serials into ISO dates.
"""

from __future__ import annotations

import csv
import threading
import shutil
import os
import datetime as dt
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

from . import paths, pdfread, pdfrender, profiles

CONVERTIBLE = {".xlsx", ".xlsm", ".docx", ".pdf", ".zip"}

_NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_NS_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_NS_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Built-in Excel number-format ids that mean "this is a date".
_BUILTIN_DATE_FMTS = set(range(14, 23)) | set(range(45, 48)) | {27, 30, 36, 50, 57}
_EXCEL_EPOCH = dt.date(1899, 12, 30)  # Excel's off-by-two-days 1900 system


class Unopenable(ValueError):
    """The document cannot be opened at all, as opposed to a conversion that
    went wrong. The first is a property of the file and is reported to the
    engine; the second is a bug and is reported to the person."""


def derived_root(ay: str) -> Path:
    # In the home's working files, not beside the program: the conversions
    # are the text of someone's documents.
    return paths.cache_dir() / f"AY{paths.check_ay(ay)}"


# --------------------------------------------------------------------------
# xlsx
# --------------------------------------------------------------------------
def _col_index(ref: str) -> int:
    """'BC12' -> 54. Needed because empty cells are simply absent from the XML,
    so a row must be rebuilt by column reference or the columns shift left."""
    letters = re.match(r"[A-Z]+", ref or "A").group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _date_format_ids(zf: zipfile.ZipFile) -> set[int]:
    """Which cell-style indices render as dates."""
    try:
        styles = ET.fromstring(zf.read("xl/styles.xml"))
    except KeyError:
        return set()

    custom_dates = set()
    for fmt in styles.iter(f"{_NS_MAIN}numFmt"):
        code = (fmt.get("formatCode") or "").lower()
        # Strip literals and colour/condition blocks before sniffing for d/m/y.
        stripped = re.sub(r'\[[^\]]*\]|"[^"]*"', "", code)
        if re.search(r"[dmy]", stripped) and "h" not in stripped.replace("h:mm", ""):
            custom_dates.add(int(fmt.get("numFmtId")))

    date_styles = set()
    xfs = styles.find(f"{_NS_MAIN}cellXfs")
    if xfs is not None:
        for i, xf in enumerate(xfs):
            num_fmt = int(xf.get("numFmtId") or 0)
            if num_fmt in _BUILTIN_DATE_FMTS or num_fmt in custom_dates:
                date_styles.add(i)
    return date_styles


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out = []
    for si in root.iter(f"{_NS_MAIN}si"):
        out.append("".join(t.text or "" for t in si.iter(f"{_NS_MAIN}t")))
    return out


def _sheets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """[(sheet name, zip path)] in workbook order."""
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    by_id = {r.get("Id"): r.get("Target") for r in rels.iter(f"{_NS_PKG_REL}Relationship")}

    out = []
    for sheet in wb.iter(f"{_NS_MAIN}sheet"):
        target = by_id.get(sheet.get(f"{_NS_REL}id"), "")
        if not target:
            continue
        target = target.lstrip("/")
        out.append((sheet.get("name") or "Sheet", target if target.startswith("xl/") else f"xl/{target}"))
    return out


def _cell_text(cell, strings, date_styles) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{_NS_MAIN}t"))
    value = cell.find(f"{_NS_MAIN}v")
    if value is None or value.text is None:
        return ""
    raw = value.text
    if kind == "s":
        try:
            return strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    if kind in ("str", "e", "b"):
        return raw
    # Numeric. It may really be a date.
    style = cell.get("s")
    if style is not None and int(style) in date_styles:
        try:
            serial = float(raw)
            if serial > 0:
                return (_EXCEL_EPOCH + dt.timedelta(days=int(serial))).isoformat()
        except ValueError:
            pass
    return raw


def xlsx_to_csv(src: Path, out_dir: Path) -> list[Path]:
    written = []
    with zipfile.ZipFile(src) as zf:
        strings = _shared_strings(zf)
        date_styles = _date_format_ids(zf)
        for name, zpath in _sheets(zf):
            try:
                sheet = ET.fromstring(zf.read(zpath))
            except KeyError:
                continue
            rows = []
            for row in sheet.iter(f"{_NS_MAIN}row"):
                cells = {}
                for c in row.iter(f"{_NS_MAIN}c"):
                    cells[_col_index(c.get("r", "A"))] = _cell_text(c, strings, date_styles)
                if not cells:
                    continue
                width = max(cells) + 1
                rows.append([cells.get(i, "") for i in range(width)])
            if not rows:
                continue
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "Sheet"
            target = out_dir / f"{src.stem}__{safe}.csv"
            with target.open("w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerows(rows)
            written.append(target)
    return written


# --------------------------------------------------------------------------
# docx
# --------------------------------------------------------------------------
def docx_to_text(src: Path, out_dir: Path) -> list[Path]:
    with zipfile.ZipFile(src) as zf:
        try:
            body = ET.fromstring(zf.read("word/document.xml"))
        except KeyError:
            return []
    lines = []
    for para in body.iter(f"{_NS_WORD}p"):
        text = "".join(t.text or "" for t in para.iter(f"{_NS_WORD}t"))
        lines.append(text)
    target = out_dir / f"{src.stem}.txt"
    target.write_text("\n".join(lines), encoding="utf-8")
    return [target]


# --------------------------------------------------------------------------
# pdf
# --------------------------------------------------------------------------
# A page image is handed to the engine as a file of its own, so it has to be
# small enough to open. Two megabytes of JPEG is a full page at reading
# resolution and well inside every engine's limit.
MAX_PAGE_IMAGES = 150

# Drawing a page costs a second or two, so a long document is bounded rather
# than left to run. A statement that runs past this says so in the folder.
MAX_RENDERED_PAGES = 40


def pdf_passwords() -> list[bytes]:
    """Passwords to try, in order, on an encrypted PDF.

    The income-tax portal encrypts the AIS and the TIS with the taxpayer's own
    PAN in lower case followed by the date of birth as ddmmyyyy; TRACES
    protects Form 26AS with the date of birth alone; the depositories' monthly
    statements, and a mutual fund statement whose password was set that way,
    use the PAN alone. None of these is a secret being broken -- each is the
    password the issuer tells the taxpayer to use, rebuilt from the return's
    details so nobody has to type it per document.
    """
    out = [b""]
    try:
        profile = profiles.active()
    except Exception:  # noqa: BLE001
        return out
    pan = str(profile.get("pan") or "").strip()
    dob = str((profile.get("settings") or {}).get("dob") or "").strip()
    if pan and dob:
        digits = re.sub(r"[^0-9]", "", dob)
        forms = []
        if len(digits) == 8:
            if dob[:4].isdigit() and len(dob) >= 10 and dob[4] in "-/":
                y, m, d = digits[:4], digits[4:6], digits[6:8]   # yyyy-mm-dd
            else:
                d, m, y = digits[:2], digits[2:4], digits[4:8]   # dd-mm-yyyy
            forms = [d + m + y, y + m + d]
        for form in forms:
            out.append((pan.lower() + form).encode("utf-8"))
            out.append((pan.upper() + form).encode("utf-8"))
        for form in forms:
            out.append(form.encode("utf-8"))
    if pan:
        out.append(pan.upper().encode("utf-8"))
        out.append(pan.lower().encode("utf-8"))
    return out


def pdf_to_text(src: Path, out_dir: Path) -> list[Path]:
    """A PDF as text, or -- when it has no text -- as its page images.

    These are two genuinely different documents wearing the same extension.
    Most statements store characters and come out as text. A scanned one
    stores a photograph of each page and has no characters at all, so no
    amount of text extraction will ever produce a number from it; what it does
    have is page images, and those can be handed over as images. The wrong
    move is to return an empty .txt, because a schedule built from that looks
    complete and is not.
    """
    raw = src.read_bytes()
    doc = pdfread.Document(raw, passwords=pdf_passwords())
    if doc.locked:
        raise Unopenable(
            "password-protected, and the password is not available (the AIS "
            "and TIS open once the profile's date of birth is set)")

    pages = doc.pages()
    chunks = []
    for number, page in enumerate(pages, 1):
        try:
            body = pdfread.text_of_page(doc, page).strip()
        except Exception:  # noqa: BLE001
            body = ""
        if body:
            chunks.append(f"--- page {number} of {len(pages)} ---\n{body}")

    made: list[Path] = []
    characters = sum(len(c) for c in chunks)
    if characters >= pdfread.MIN_TEXT_PER_PAGE * max(1, len(pages)):
        target = out_dir / f"{src.stem}.txt"
        target.write_text("\n\n".join(chunks), encoding="utf-8")
        made.append(target)
        return made

    # No usable text: fall back to the page images, which is what a scan is.
    count = 0
    for number, ext, blob in pdfread.images_of_doc(doc, limit=MAX_PAGE_IMAGES):
        count += 1
        target = out_dir / f"{src.stem}_page{number:03d}_{count:02d}.{ext}"
        target.write_bytes(blob)
        made.append(target)

    if made:
        return made

    # Still nothing. The remaining case is a PDF whose characters are drawn as
    # outlines: no text to extract and no image to hand over either, because
    # there is no image in the file at all. There are, however, instructions
    # for drawing one, so we follow them and produce the page ourselves. The
    # engine then reads it the way it reads any other page image.
    pages_with_ink = [p for p in pages if pdfrender.has_drawing(doc, p)]
    if pages_with_ink:
        for number, blob in pdfrender.pages_as_png(doc, limit=MAX_RENDERED_PAGES):
            target = out_dir / f"{src.stem}_page{number:03d}_rendered.png"
            target.write_bytes(blob)
            made.append(target)
    if made:
        if len(pages) > MAX_RENDERED_PAGES:
            note = out_dir / f"{src.stem}_rendering_note.txt"
            note.write_text(
                f"{src.name} has {len(pages)} pages and the first {MAX_RENDERED_PAGES} "
                f"were drawn. Pages {MAX_RENDERED_PAGES + 1} to {len(pages)} are NOT in "
                f"this folder, so anything on them is missing from this schedule.\n",
                encoding="utf-8")
            made.append(note)
        return made

    raise Unopenable(
        "no readable content: this PDF has no text operators, no page-sized scan, and no "
        "drawing operators either -- there is nothing in it to read or to draw")


# --------------------------------------------------------------------------
# archives
# --------------------------------------------------------------------------
# A folder of invoices arrives as one .zip, and an archive nobody opens is a
# document nobody reads: the classifier can only guess from the filename, and
# the guess is recorded as fact. So an archive is unpacked like any other
# conversion -- into the same content-hashed cache, read-only, once.
MAX_ARCHIVE_MEMBERS = 300
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024


def _safe_name(name: str, used: set[str]) -> str:
    """A flat, collision-free filename for an archive member.

    Archive members can name any path they like, including `..` and absolute
    ones, and writing those where they ask is how an archive escapes the
    folder it was supposed to unpack into. Only the basename is ever used.
    """
    base = PurePosixPath(name).name or "member"
    base = re.sub(r"[^A-Za-z0-9._ +()-]", "_", base)[:120] or "member"
    stem, dot, suffix = base.rpartition(".")
    candidate, n = base, 2
    while candidate.lower() in used:
        candidate = f"{stem}_{n}{dot}{suffix}" if dot else f"{base}_{n}"
        n += 1
    used.add(candidate.lower())
    return candidate


def zip_to_files(src: Path, out_dir: Path) -> list[Path]:
    """Every member of an archive, unpacked and then made readable itself.

    A PDF inside the archive gets the same treatment as one outside it, which
    is the whole point: the invoices in a zip are no less evidence than the
    ones sitting loose in the folder.
    """
    made: list[Path] = []
    used: set[str] = set()
    budget = MAX_ARCHIVE_BYTES
    skipped: list[str] = []

    with zipfile.ZipFile(src) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()][:MAX_ARCHIVE_MEMBERS]
        for info in members:
            if info.file_size > budget:
                skipped.append(f"{info.filename} (would exceed the unpacking budget)")
                continue
            target = out_dir / _safe_name(info.filename, used)
            try:
                with zf.open(info) as fh:
                    target.write_bytes(fh.read())
            except RuntimeError as exc:          # an encrypted member
                skipped.append(f"{info.filename} ({exc})")
                continue
            except Exception as exc:             # noqa: BLE001
                skipped.append(f"{info.filename} ({type(exc).__name__})")
                continue
            budget -= info.file_size
            made.append(target)

    # Now make each member readable in turn. One level only: an archive inside
    # an archive is left as it is rather than followed, because that is how a
    # small file becomes an unbounded one.
    for member in list(made):
        suffix = member.suffix.lower()
        if suffix not in CONVERTIBLE or suffix == ".zip":
            continue
        try:
            kind = sniff(member)
            if kind == "pdf":
                made.extend(pdf_to_text(member, out_dir))
            elif kind == "zip" and suffix in (".xlsx", ".xlsm"):
                made.extend(xlsx_to_csv(member, out_dir))
            elif kind == "zip" and suffix == ".docx":
                made.extend(docx_to_text(member, out_dir))
        except Unopenable as exc:
            skipped.append(f"{member.name} ({exc})")
        except Exception as exc:                 # noqa: BLE001
            skipped.append(f"{member.name} ({type(exc).__name__}: {exc})")

    if skipped:
        note = out_dir / f"{src.stem}_not_unpacked.txt"
        note.write_text(
            "These members of " + src.name + " were not unpacked or not converted, so "
            "nothing in them is in this schedule:\n\n"
            + "\n".join("  - " + x for x in skipped) + "\n",
            encoding="utf-8")
        made.append(note)

    if not made:
        raise Unopenable("the archive is empty, or nothing in it could be unpacked")
    return sorted(set(made))


# --------------------------------------------------------------------------
# what this file actually is
# --------------------------------------------------------------------------
# A broker's "download as Excel" often writes something else entirely and
# names it .xlsx: a tab-separated text file, or an HTML table. Trusting the
# extension there produces "File is not a zip file" and the document is lost,
# so the format is decided by looking at the first bytes.
def sniff(src: Path) -> str:
    """One of: zip, html, xml, delimited, text."""
    with src.open("rb") as fh:
        head = fh.read(4096)
    if head[:2] == b"PK":
        return "zip"
    if head[:5] == b"%PDF-":
        return "pdf"
    # A PDF is not always at the start of its own file. The income-tax
    # e-filing portal hands back the filed return wrapped in a Java-serialised
    # object stream -- the file opens with ACED0005 and the %PDF- header sits a
    # couple of hundred bytes in. The PDF specification expects a reader to
    # look for the header rather than assume it is at byte zero, and the reader
    # in this project scans for objects anyway, so finding it here is enough.
    if b"%PDF-" in head:
        return "pdf"
    start = head.lstrip()[:200].lower()
    if start.startswith(b"<!doctype html") or start.startswith(b"<html") or b"<table" in head.lower():
        return "html"
    if start.startswith(b"<?xml") or start.startswith(b"<"):
        return "xml"
    text = head.decode("utf-8", "replace")
    first = text.splitlines()[0] if text.splitlines() else ""
    for sep in ("\t", ",", ";", "|"):
        if first.count(sep) >= 2:
            return "delimited"
    return "text"


def delimiter_of(text: str) -> str:
    """The separator that carves the most rows into the same shape."""
    lines = [ln for ln in text.splitlines()[:40] if ln.strip()]
    best, best_score = "\t", -1
    for sep in ("\t", ",", ";", "|"):
        counts = [ln.count(sep) for ln in lines if ln.count(sep)]
        if not counts:
            continue
        score = len(counts) * max(counts)          # many rows, many columns
        if score > best_score:
            best, best_score = sep, score
    return best


def delimited_to_csv(src: Path, out_dir: Path) -> list[Path]:
    """A delimited text export written as proper CSV, row for row.

    Nothing is dropped or reshaped: heading rows, sub-totals and the footer
    notes all survive, because deciding which of them are data is the
    engine's job, not this one's."""
    raw = (src.read_bytes().decode("utf-8-sig", "replace")
           .replace("\r\n", "\n").replace("\r", "\n"))
    sep = delimiter_of(raw)
    target = out_dir / f"{src.stem}.csv"
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for line in raw.split("\n"):
            cells = [c.strip() for c in line.split(sep)]
            while cells and cells[-1] == "":
                cells.pop()
            writer.writerow(cells)
    return [target]


class _Tables(HTMLParser):
    """Every <table> as rows of cell text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self.tables:
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def html_to_csv(src: Path, out_dir: Path) -> list[Path]:
    """Each HTML table as its own CSV, in the order they appear."""
    text = src.read_bytes().decode("utf-8", "replace")
    parser = _Tables()
    parser.feed(text)
    made = []
    for i, rows in enumerate([t for t in parser.tables if t], 1):
        target = out_dir / (f"{src.stem}.csv" if len(parser.tables) == 1 else f"{src.stem}__table{i}.csv")
        with target.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(rows)
        made.append(target)
    if not made:
        # An HTML page with no table is still text worth reading.
        stripped = re.sub(r"<[^>]+>", " ", text)
        target = out_dir / f"{src.stem}.txt"
        target.write_text("\
".join(ln.strip() for ln in stripped.splitlines() if ln.strip()), encoding="utf-8")
        made.append(target)
    return made


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def ensure_readable(ay: str, files: list[dict], on_event=None
                    ) -> tuple[list[dict], list[Path], list[dict]]:
    """Return (files the engine should see, extra directories to grant,
    documents left out because they cannot be opened).

    Originals stay in the list. A converted file is added beside its original
    and labelled with where it came from, so a citation can always be traced
    back to the document you actually hold.

    The one thing decided here rather than by the engine is a document that
    cannot be opened at all -- a PDF whose password is not available. Handing
    it over only invites the engine to guess at it from its name. It leaves the
    file list and is returned separately, with its reason, so the prompt can
    say it exists and the reviewer can see it was not read.
    """
    on_event = on_event or (lambda e: None)
    out = list(files)
    extra_dirs: set[Path] = set()
    left_out: list[dict] = []

    for f in files:
        src = Path(f["abs"])
        if src.suffix.lower() not in CONVERTIBLE:
            continue

        # Keyed by content hash: same bytes, same conversion, done once.
        cache = derived_root(ay) / f["sha256"][:16]
        made = sorted(cache.glob("*")) if cache.exists() else []
        if not made:
            # Two schedules often convert the same document at the same moment
            # -- one broker workbook feeds both Capital Gains and Books. Each
            # converts into its own scratch folder and renames it into place,
            # so the cache folder only ever appears complete.
            scratch = cache.with_name(f"{cache.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            shutil.rmtree(scratch, ignore_errors=True)
            scratch.mkdir(parents=True)
            try:
                kind = sniff(src)
                if kind == "zip":
                    if src.suffix.lower() == ".docx":
                        docx_to_text(src, scratch)
                    elif src.suffix.lower() == ".zip":
                        zip_to_files(src, scratch)
                    else:
                        xlsx_to_csv(src, scratch)
                elif kind == "pdf":
                    pdf_to_text(src, scratch)
                elif kind == "html":
                    html_to_csv(src, scratch)
                elif kind == "delimited":
                    delimited_to_csv(src, scratch)
                else:
                    raise Unopenable(
                        f"named {src.suffix} but its contents are {kind}, which this "
                        f"tool cannot turn into rows")
                try:
                    scratch.rename(cache)
                except OSError:
                    shutil.rmtree(scratch, ignore_errors=True)  # another run won
                made = sorted(cache.glob("*"))
            except Unopenable as exc:
                shutil.rmtree(scratch, ignore_errors=True)
                on_event({"phase": "note", "detail": f"left out {src.name}: {exc}"})
                out.remove(f)
                left_out.append({**f, "left_out": str(exc)})
                continue
            except Exception as exc:  # noqa: BLE001
                shutil.rmtree(scratch, ignore_errors=True)
                on_event({"phase": "note",
                          "detail": f"could not convert {src.name}: {type(exc).__name__}: {exc}"})
                continue

        if not made:
            on_event({"phase": "note", "detail": f"{src.name} converted to nothing readable"})
            continue

        on_event({"phase": "convert",
                  "detail": f"{src.name} -> {len(made)} file(s) the engine can read"})
        extra_dirs.add(cache)
        for m in made:
            out.append({
                "path": f"[converted] {m.name}",
                "abs": str(m),
                "sha256": f["sha256"],       # provenance points at the ORIGINAL
                "bytes": m.stat().st_size,
                "converted_from": f["path"],
            })

    return out, sorted(extra_dirs), left_out
