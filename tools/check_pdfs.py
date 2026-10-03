"""Report what the PDF reader can and cannot get out of the source documents.

A PDF that yields nothing is not a bug you find by reading code -- it is a
property of the file, and it changes when a bank redesigns its statement. So
this is a survey, not a pass/fail test: run it after adding documents and read
the last column.

    python tools/check_pdfs.py                  # the active profile's folder
    python tools/check_pdfs.py <folder>

"text" means every number in the document is recoverable. "scan" means the file
is a photograph of its pages and the engine will be given those images. "drawn"
means the file has no text and no image either -- its characters are outlines --
so the page was rendered from its own drawing instructions and the engine reads
the picture. "unreadable" means none of that worked.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import convert, paths, profiles  # noqa: E402


def folder() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    return paths.resolve_dir(profiles.active()["source_dir"])


def main() -> int:
    where = folder()
    if not where.is_dir():
        print(f"not a folder: {where}")
        return 2

    scratch = Path(tempfile.mkdtemp(prefix="itr_pdfcheck_"))
    unreadable = []
    counts = {"text": 0, "scan": 0, "drawn": 0, "unreadable": 0}
    seen: set[str] = set()

    try:
        for pdf in sorted(where.rglob("*.pdf")):
            if pdf.name in seen:
                continue
            seen.add(pdf.name)
            out = scratch / str(len(seen))
            out.mkdir(parents=True, exist_ok=True)
            try:
                made = convert.pdf_to_text(pdf, out)
            except Exception as exc:  # noqa: BLE001
                counts["unreadable"] += 1
                unreadable.append((pdf.name, str(exc)))
                print(f"  {'unreadable':<14} {'':>8}  {pdf.name}")
                continue
            if made[0].suffix == ".txt":
                kind = "text"
            elif "_rendered" in made[0].stem:
                kind = "drawn"
            else:
                kind = "scan"
            counts[kind] += 1
            size = sum(m.stat().st_size for m in made) // 1024
            detail = f"{size} KB" if kind == "text" else f"{len(made)} pages"
            print(f"  {kind:<14} {detail:>8}  {pdf.name}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print(f"\n{counts['text']} readable as text, {counts['scan']} as scanned pages, "
          f"{counts['drawn']} drawn from outlines, {counts['unreadable']} not "
          f"readable at all")
    for name, why in unreadable:
        print(f"\n  {name}\n    {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
