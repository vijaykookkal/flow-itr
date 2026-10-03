"""Remove conversions whose source document is no longer there.

Conversions live in `<home>/.state/cache/AY<year>/<first 16 of the source sha256>/`, which
makes them a pure function of the bytes they came from and means an unchanged
document is never converted twice. The cost of that design is that nothing ever
tells the cache a document has been deleted: the folder stays, keyed by a hash
no document has any more, and it is still a readable directory the engine has
been granted. A 31-page scan that was removed for being a duplicate can leave
50 MB of page images behind and re-enter a run through them.

So this prunes. A cache folder survives only if some document currently in the
profile's source folder still hashes to its name.

    python tools/prune_derived.py            # say what would go
    python tools/prune_derived.py --delete   # actually remove it
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import convert, paths, profiles, sources  # noqa: E402


def megabytes(folder: Path) -> float:
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) / 1048576


def main() -> int:
    delete = "--delete" in sys.argv
    ay = profiles.active_ay()
    root = convert.derived_root(ay)
    if not root.is_dir():
        print(f"no conversions yet for AY {ay}")
        return 0

    # all_documents does not hash (it is used for listings), so hash here:
    # the cache folder name is what has to be matched, not the path.
    live = {sources.sha256_file(Path(f["abs"]))[:16]
            for f in sources.all_documents(ay) if not f["is_archive"]}
    orphans = [d for d in sorted(root.iterdir()) if d.is_dir() and d.name not in live]

    if not orphans:
        print(f"AY {ay}: every conversion still has its source document")
        return 0

    total = 0.0
    for folder in orphans:
        size = megabytes(folder)
        total += size
        first = next((f.name for f in sorted(folder.iterdir())), "(empty)")
        print(f"  {size:7.1f} MB  {folder.name}  {first}")
        if delete:
            shutil.rmtree(folder, ignore_errors=True)

    verb = "removed" if delete else "would remove"
    print(f"\n{verb} {len(orphans)} orphaned conversion(s), {total:.1f} MB")
    if not delete:
        print("re-run with --delete to remove them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
