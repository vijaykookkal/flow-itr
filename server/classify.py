"""Deciding which schedule each document belongs to, with an AI pass.

Hand-written glob rules only work when you already know your filenames. This
asks a model to look at the whole document tree and route it instead.

The important design choice is that classification **produces a committed
artefact, it does not run during extraction**. The model proposes a mapping,
you review it, and the profile's `document_map.json` is what every later run
reads. It lives in the profile's data directory rather than in config/, because
which document belongs to which schedule is a fact about one person's folder in
one year, not a setting of the application.
Routing therefore stays identical between runs, shows up in `git diff` when it
changes, and can be corrected by hand without arguing with a model.

That is the same shape as the extracted/overrides/resolved split used for the
figures themselves: the machine proposes, you decide, git records.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import engines, jsonschema_lite as jsl, paths, sources

MAX_REPAIRS = 2


def map_path(ay: str):
    """Per profile, not global: which documents belong to which schedule is a
    fact about one person's folder, not about the application."""
    return paths.data_root(ay) / "document_map.json"


def overrides_path(ay: str):
    return paths.data_root(ay) / "document_map.overrides.json"


def schema() -> dict:
    return json.loads((paths.SCHEMAS / "classification.schema.json").read_text("utf-8"))


def load_map(ay: str) -> dict:
    """The committed mapping with your corrections applied on top."""
    base = paths.read_json(map_path(ay), {})
    if base.get("ay") != ay:
        base = {"ay": ay, "documents": []}

    by_path = {d["path"]: dict(d) for d in base.get("documents", [])}
    for ov in paths.read_json(overrides_path(ay), {}).get("documents", []):
        entry = by_path.setdefault(ov["path"], {"path": ov["path"], "kind": "", "why": ""})
        entry.update({k: v for k, v in ov.items() if k != "path"})
        entry["source"] = "you"
    return {**base, "documents": list(by_path.values())}


def tabs_for(ay: str, path: str) -> list[str]:
    for d in load_map(ay).get("documents", []):
        if d["path"] == path:
            return d.get("tabs", [])
    return []


def paths_for_tab(ay: str, tab_id: str) -> list[str]:
    """Document paths the committed mapping assigns to this tab."""
    return [d["path"] for d in load_map(ay).get("documents", []) if tab_id in d.get("tabs", [])]


def reported_summaries(ay: str) -> list[str]:
    """Documents that hold what was reported TO the department -- AIS, TIS,
    Form 26AS. Every schedule's reconciliation is given these, whichever tabs
    they are routed to.

    Until a classification has run with the flag, fall back to the documents
    routed to Taxes Paid, which is where the department's own records land."""
    documents = load_map(ay).get("documents", [])
    flagged = [d["path"] for d in documents if d.get("reported_summary")]
    if flagged:
        return flagged
    return [d["path"] for d in documents if "taxes_paid" in d.get("tabs", [])]


def assign(ay: str, path: str, tabs: list[str], why: str = "") -> dict:
    """Record a manual routing correction. Never edits the AI's own output."""
    doc = paths.read_json(overrides_path(ay), {"ay": ay, "documents": []})
    doc["documents"] = [d for d in doc.get("documents", []) if d["path"] != path]
    entry = {
        "path": path,
        "tabs": tabs,
        "confidence": "high",
        "why": why or "Assigned by hand.",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    doc["documents"].append(entry)
    doc["documents"].sort(key=lambda d: d["path"])
    paths.write_json(overrides_path(ay), doc)
    return entry


ARCHIVE_LISTED_MEMBERS = 40     # members named under an archive in the listing
ARCHIVE_EXCERPTS = 12           # of which this many also show their opening text
EXCERPT_CHARS = 280


def archive_contents(ay: str, documents: list[dict], on_event=None) -> tuple[dict[str, str], list]:
    """What is inside each zip in the listing, for the router to see.

    Routing used to see an archive only by its name, and the instructions said
    an archive belongs to no schedule -- so a zip of business-expense invoices
    was never read unless something else had happened to unpack it first.
    Now each zip is unpacked here (into the same content-keyed cache the
    extraction uses, so the work is not repeated) and listed member by member,
    with the opening lines of each member's text, and with any member that is
    the same file as a document already in the folder marked as such, which is
    how a download of the whole folder shows itself to be a duplicate.

    Returns ({archive path: text placed under it in the listing}, folders the
    engine may read)."""
    from . import convert

    on_event = on_event or (lambda e: None)
    zips = [d for d in documents if Path(d["path"]).suffix.lower() in sources.READABLE_ARCHIVES]
    if not zips:
        return {}, []
    loose = {sources.sha256_file(Path(d["abs"])): d["path"] for d in documents
             if not d["is_archive"]}
    out, dirs = {}, []
    for z in zips:
        doc = {"path": z["path"], "abs": z["abs"], "bytes": z["bytes"],
               "sha256": sources.sha256_file(Path(z["abs"]))}
        try:
            files, extra, left = convert.ensure_readable(ay, [doc], on_event)
        except Exception as exc:  # noqa: BLE001 -- shown in the listing, never fatal
            out[z["path"]] = f"      (could not be unpacked: {type(exc).__name__}: {exc})"
            continue
        if left:
            out[z["path"]] = f"      (could not be unpacked: {left[0].get('left_out', '')})"
            continue
        dirs.extend(extra)
        # The members as the archive itself lists them; the cache supplies
        # only their text, matched by name.
        texts = sorted((Path(f["abs"]) for f in files if f.get("converted_from") == z["path"]
                        and Path(f["abs"]).suffix.lower() in (".txt", ".csv")), key=lambda p: p.name)
        with zipfile.ZipFile(z["abs"]) as zf:
            members = [(m.filename, m.file_size, hashlib.sha256(zf.read(m)).hexdigest())
                       for m in zf.infolist() if not m.is_dir()]
        same = sum(1 for _, _, digest in members if digest in loose)
        lines, shown = [], 0
        for name, size, digest in members[:ARCHIVE_LISTED_MEMBERS]:
            twin = loose.get(digest)
            lines.append(f"      - {name}  [{size:,} bytes]" + (f"  (the same file as {twin})" if twin else ""))
            stem = Path(name).stem
            text = next((t for t in texts if t.stem == stem or t.name.startswith(stem)), None)
            if text and not twin and shown < ARCHIVE_EXCERPTS:
                head = " ".join(text.read_text("utf-8", errors="replace")[:EXCERPT_CHARS].split())
                if head:
                    lines.append(f"          begins: {head}")
                    shown += 1
        more = len(members) - ARCHIVE_LISTED_MEMBERS
        if more > 0:
            lines.append(f"      ... and {more} more member(s)")
        summary = f"      contains {len(members)} file(s)"
        if same:
            summary += f", {same} of them the same as documents already in this listing"
        out[z["path"]] = "\n".join([summary + ":", *lines])
    return out, dirs


def build_prompt(ay: str, documents: list[dict], contents: dict[str, str] | None = None) -> str:
    instructions = (paths.PROMPTS / "_classify.md").read_text("utf-8")
    contents = contents or {}
    tabs = [
        f"  - {t['id']:<22} {t['title']} ({', '.join(t['schedules'])})"
        # A derived schedule is computed from other schedules and reads no
        # document of its own, so nothing is ever routed to it.
        for t in paths.load_tabs()["tabs"] if t.get("kind") != "derive"
    ]
    listing = "\n".join(
        f"  {d['path']}  [{d['bytes']:,} bytes]" + ("  (archive)" if d["is_archive"] else "")
        + (f"\n{contents[d['path']]}" if d["path"] in contents else "")
        for d in documents
    )
    return f"""{instructions}

## Tabs you may assign to

{chr(10).join(tabs)}

Use these exact ids in `tabs`. Assigning to a tab that is not yet built is
correct and useful -- it records where the document belongs for when it is.

## The documents

Root: {paths.source_root(ay).as_posix()}
You may read anything under that root. Paths below are relative to it.

{listing}

## Required output

Reply with a single JSON document and nothing else, in a ```json fenced block,
validating against this schema:

```json
{json.dumps(schema(), indent=2)}
```
"""


def run(ay: str, engine_name: str = "claude", on_event=None, cancel=None) -> dict:
    on_event = on_event or (lambda e: None)

    documents = sources.all_documents(ay)
    if not documents:
        raise ValueError(f"no documents in {paths.source_root(ay)}. Put them there, or point the "
                         f"profile at the folder that holds them.")
    on_event({"phase": "scan", "detail": f"{len(documents)} document(s) to route"})

    contents, archive_dirs = archive_contents(ay, documents, on_event)
    prompt = build_prompt(ay, documents, contents)
    sch = schema()
    engine = engines.get(engine_name)
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-classify"

    result, errors, session_id = None, [], None
    for attempt in range(1, MAX_REPAIRS + 2):
        on_event({"phase": "ask", "detail": f"attempt {attempt} via {engine_name}"})
        reply = engine.run(
            engines.Request(
                schedule="_classify", ay=ay, files=documents, prompt=prompt,
                cwd=paths.ROOT, add_dirs=[paths.source_root(ay), *archive_dirs],
                cancel=cancel, time_limit=engines.time_limit_for(engine_name),
                attempt=attempt, session_id=session_id,
                repair_prompt=(
                    "Your previous JSON did not validate:\n"
                    + jsl.format_errors(errors)
                    + "\nReply with the corrected JSON only."
                ) if errors else None,
            ),
            on_event,
        )
        session_id = reply.session_id or session_id
        from .runner import _extract_json

        candidate = _extract_json(reply.text)
        errors = jsl.validate(candidate, sch)
        if not errors:
            result = candidate
            on_event({"phase": "valid", "detail": "schema ok"})
            break
        on_event({"phase": "invalid", "detail": f"{len(errors)} violation(s)"})

    if result is None:
        raise ValueError("classification failed schema validation:\n" + jsl.format_errors(errors))

    # The model answers about the listing it was given; anything it invented or
    # skipped is a routing error and must be visible, not quietly absorbed.
    listed = {d["path"] for d in documents}
    answered = {d["path"] for d in result["documents"]}
    notes = list(result.get("notes", []))
    for missing in sorted(listed - answered):
        result["documents"].append({
            "path": missing, "kind": "unknown", "tabs": [], "confidence": "low",
            "why": "The classifier did not return an answer for this document.",
        })
        notes.append(f"No classification returned for {missing}; left unassigned.")
    for invented in sorted(answered - listed):
        notes.append(f"Classifier returned a path that is not in the listing: {invented}")
    result["documents"] = [d for d in result["documents"] if d["path"] in listed]

    known_tabs = {t["id"] for t in paths.load_tabs()["tabs"]}
    for d in result["documents"]:
        bad = [t for t in d.get("tabs", []) if t not in known_tabs]
        if bad:
            notes.append(f"{d['path']}: dropped unknown tab id(s) {bad}")
            d["tabs"] = [t for t in d["tabs"] if t in known_tabs]

    payload = {
        "ay": ay,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": {"id": engine_name, "model": reply.model, "prompt_version": "classify@2"},
        "documents": sorted(result["documents"], key=lambda d: d["path"]),
        "notes": notes,
    }
    paths.write_json(map_path(ay), payload)
    on_event({"phase": "write", "detail": map_path(ay).name})

    low = [d["path"] for d in payload["documents"] if d["confidence"] == "low"]
    unrouted = [d["path"] for d in payload["documents"] if not d["tabs"]]
    on_event({"phase": "done",
              "detail": f"{len(payload['documents'])} routed, {len(low)} low confidence, "
                        f"{len(unrouted)} assigned to no tab"})
    return payload
