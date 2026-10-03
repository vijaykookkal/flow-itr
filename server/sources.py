"""Resolving a tab to its documents, and fingerprinting them.

A tab does not own a folder. It owns a list of *specs*, each of which is a
directory (scanned recursively) or a glob. That matters because real document
folders are not organised by ITR schedule: an export from a drive tends to put
capital gains, dividends and bank statements in one folder, and three different
schedules need three different subsets of it. Globs let a tab take exactly the
files it should see without anyone reorganising their documents.

Specs may start with an alias defined in config/tabs.json `roots`, so a long
export path appears once rather than in every tab.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from . import paths

IGNORED_NAMES = {".gitkeep", "Thumbs.db", ".DS_Store", "README.md", "desktop.ini"}
# .gdoc and its kin are pointers Google Drive leaves for online-only files.
IGNORED_SUFFIXES = {".tmp", ".crdownload", ".part", ".lnk", ".gdoc", ".gsheet", ".gslides"}

# Containers. A .zip is unpacked by convert.py like any other conversion, so
# it goes to the engine as its contents; the rest we can see but not read
# into, and those are reported rather than skipped in silence, because "no
# business expenses found" and "your invoices are inside a .rar" are very
# different statements.
ARCHIVE_SUFFIXES = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz"}
READABLE_ARCHIVES = {".zip"}
OPAQUE_ARCHIVES = ARCHIVE_SUFFIXES - READABLE_ARCHIVES


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expand_spec(spec: str, roots: dict) -> str:
    """`drive:Form16/*.pdf` -> `<roots['drive']>/Form16/*.pdf`"""
    if ":" in spec:
        alias, _, rest = spec.partition(":")
        if alias in roots:
            return f"{roots[alias].rstrip('/')}/{rest.lstrip('/')}" if rest else roots[alias]
    return spec


def tab_specs(tab_id: str) -> list[str]:
    config = paths.load_tabs()
    roots = config.get("roots", {})
    tab = paths.tab(tab_id)
    specs = tab.get("sources") or ([tab["folder"]] if tab.get("folder") else [])
    return [expand_spec(s, roots) for s in specs]


def foreign_dirs(ay: str) -> list[Path]:
    """Other profiles' document directories.

    Nothing belonging to another person may enter this profile's scans. That
    has to hold as an invariant rather than as a consequence of the folder
    layout, because layouts get reorganised and one person's Form 16 landing in
    another person's return is not a mistake you would notice on screen.
    """
    from . import profiles

    mine = profiles.active()
    my_dir = paths.source_root(ay).resolve()
    out = []
    for p in profiles.load_all()["profiles"]:
        if mine and p["id"] == mine["id"]:
            continue
        d = paths.resolve_dir(p["source_dir"]).resolve()
        # Sharing a document folder is a supported, useful arrangement -- the
        # same papers under two regimes. Only a folder nested INSIDE mine is a
        # leak, and with the flat layout that should never arise anyway.
        if d == my_dir:
            continue
        try:
            d.relative_to(my_dir)
        except ValueError:
            continue
        out.append(d)
    return out


def _belongs_to_another_profile(path: Path, foreign: list[Path]) -> bool:
    for d in foreign:
        try:
            path.relative_to(d)
            return True
        except ValueError:
            continue
    return False


def _iter_matches(base: Path, spec: str):
    target = base / spec
    if target.is_dir():
        yield from (p for p in target.rglob("*") if p.is_file())
        return
    # Not a directory, so treat it as a glob relative to the source root.
    yield from (p for p in base.glob(spec) if p.is_file())


def scan(ay: str, tab_id: str) -> list[dict]:
    """Every document this tab is allowed to see, deduplicated by content.

    Deduplication is not cosmetic. People copy the same Form 16 into a curated
    folder and leave it in the original export too; if both specs match it, the
    model sees the same employer twice and has every reason to report two.
    """
    base = paths.source_root(ay)
    if not base.exists():
        return []

    # Two ways a document reaches a tab, unioned: an explicit spec in
    # tabs.json, and the committed classification map. Specs are for routing
    # you want pinned regardless of what a model thinks; the map covers
    # everything else and is what grows as documents arrive.
    from . import classify

    mapped = [p for p in classify.paths_for_tab(ay, tab_id) if (base / p).is_file()]
    foreign = foreign_dirs(ay)
    # A return already filed is there to be compared against, never computed
    # from. Whatever a folder rule or a glob happens to match, it is handed to
    # the Filed Return tab and to no other.
    walled = set() if tab_id == "filed_return" else {
        (base / p).resolve() for p in classify.paths_for_tab(ay, "filed_return")}

    by_hash: dict[str, dict] = {}
    for spec in tab_specs(tab_id) + mapped:
        for p in sorted(_iter_matches(base, spec)):
            if p.name in IGNORED_NAMES or p.suffix.lower() in IGNORED_SUFFIXES:
                continue
            if _belongs_to_another_profile(p, foreign):
                continue
            if p.suffix.lower() in OPAQUE_ARCHIVES:
                continue
            if p.resolve() in walled:
                continue
            digest = sha256_file(p)
            rel = p.relative_to(base).as_posix()
            if digest in by_hash:
                # A folder rule and the classifier often name the same file.
                # That is one document found twice, not a second copy of it.
                first = by_hash[digest]
                if rel != first["path"] and rel not in first.get("duplicates", []):
                    first.setdefault("duplicates", []).append(rel)
                continue
            by_hash[digest] = {
                "path": rel,
                "abs": str(p),
                "sha256": digest,
                "bytes": p.stat().st_size,
            }
    return sorted(by_hash.values(), key=lambda f: f["path"])


def archives(ay: str, tab_id: str) -> list[str]:
    """Archives this tab was meant to read, which nothing can read inside.

    Both routes count -- a file-name rule and the classifier's own routing.
    The classifier can only guess at an archive from its name, and it says so;
    but a zip it routed here is still a document nobody has read, and a return
    that never mentions it is the worst of both.
    """
    from . import classify

    base = paths.source_root(ay)
    if not base.exists():
        return []
    found = set()
    foreign = foreign_dirs(ay)
    for spec in tab_specs(tab_id):
        for p in _iter_matches(base, spec):
            if _belongs_to_another_profile(p, foreign):
                continue
            if p.suffix.lower() in OPAQUE_ARCHIVES:
                found.add(p.relative_to(base).as_posix())
    for rel in classify.paths_for_tab(ay, tab_id):
        if Path(rel).suffix.lower() in OPAQUE_ARCHIVES and (base / rel).is_file():
            found.add(rel)
    return sorted(found)


def scan_dirs(ay: str, tab_id: str) -> list[Path]:
    """Directories to grant the engine read access to.

    Derived from the files actually matched, not from the specs: a spec may be
    a glob, and the engine needs directories. Parents are collapsed so a tab
    matching ten files in one folder grants that folder once.
    """
    base = paths.source_root(ay)
    dirs = {Path(f["abs"]).parent for f in scan(ay, tab_id)}
    # Drop any directory already covered by an ancestor in the set.
    keep = []
    for d in sorted(dirs, key=lambda p: len(p.parts)):
        if not any(str(d).startswith(str(k) + "\\") or str(d).startswith(str(k) + "/") for k in keep):
            keep.append(d)
    return keep or [base]


def all_documents(ay: str) -> list[dict]:
    """Every file under the AY's source root, whatever any tab claims."""
    base = paths.source_root(ay)
    if not base.exists():
        return []
    foreign = foreign_dirs(ay)
    out = []
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.name in IGNORED_NAMES or p.suffix.lower() in IGNORED_SUFFIXES:
            continue
        if _belongs_to_another_profile(p, foreign):
            continue
        out.append({
            "path": p.relative_to(base).as_posix(),
            "abs": str(p),
            "bytes": p.stat().st_size,
            "is_archive": p.suffix.lower() in ARCHIVE_SUFFIXES,
        })
    return out


def unassigned(ay: str) -> list[dict]:
    """Documents no tab will ever read.

    Source specs are patterns, so a document whose name does not match one is
    not rejected -- it is simply never looked at. Silence is the dangerous
    outcome here: a rent receipt dropped in the wrong place produces a return
    that is wrong in a way nothing on screen would show. This is what makes
    that visible.
    """
    from . import classify

    claimed: set[str] = set()
    # A document the classifier deliberately routed to no tab is a decision,
    # not an oversight, so it is not reported as unassigned.
    claimed.update(d["path"] for d in classify.load_map(ay).get("documents", []))
    for tab in paths.load_tabs()["tabs"]:
        claimed.update(f["path"] for f in scan(ay, tab["id"]))
        for f in scan(ay, tab["id"]):
            claimed.update(f.get("duplicates", []))
        claimed.update(archives(ay, tab["id"]))
    return [d for d in all_documents(ay) if d["path"] not in claimed]


def fingerprint(files: list[dict], prompt_version: str, engine: str = "") -> str:
    """Identity of a run's inputs.

    Includes the prompt version, so changing how we ask is treated as changing
    the question -- otherwise a prompt fix would silently fail to re-run.

    Includes the engine for a blunter reason: mock output must never satisfy a
    request for a real extraction. Without this, switching from mock to claude
    hits the cache and quietly hands back the stub's numbers.
    """
    h = hashlib.sha256()
    h.update(prompt_version.encode())
    h.update(b"\x00" + engine.encode())
    for f in sorted(files, key=lambda x: x["path"]):
        h.update(f["path"].encode())
        h.update(f["sha256"].encode())
    return "sha256:" + h.hexdigest()
