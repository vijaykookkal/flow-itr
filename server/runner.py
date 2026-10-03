"""One extraction run: scan, ask, validate, repair, write, re-merge.

The ordering here is the safety property. Nothing reaches data/extracted/ that
has not passed its schema, so a malformed or hallucinated-shape answer fails
loudly instead of quietly landing in your return.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import jsonschema_lite as jsl
from . import tabular
from . import convert, merge, paths, sources
from . import engines
from .engines import EngineError

MAX_REPAIRS = 2


SHARED_PROMPTS = ("_common.md", "_exclusions.md", "_table_plan.md")


def prompt_version(schedule: str) -> str:
    """The schedule prompt's declared version, plus a digest of the shared
    prompts every schedule includes -- editing the exclusion rules changes
    what every schedule should return, so it has to invalidate every cache."""
    path = paths.PROMPTS / f"{schedule}.md"
    if not path.exists():
        return f"{schedule}@0"
    head = path.read_text("utf-8")[:400]
    m = re.search(r"^version:\s*(\S+)", head, re.M)
    own = m.group(1) if m else f"{schedule}@0"
    shared = hashlib.sha256()
    for name in SHARED_PROMPTS:
        p = paths.PROMPTS / name
        if p.exists():
            shared.update(p.read_bytes())
    for p in sorted(skills_dir().glob("*.md")):
        shared.update(p.name.encode() + p.read_bytes())
    return f"{own}+{shared.hexdigest()[:8]}"


SKILLS_DIR_NAME = "skills"


def skills_dir() -> Path:
    return paths.PROMPTS / SKILLS_DIR_NAME


def _front_matter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    meta = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta


def skill_catalogue(schedule: str) -> str:
    """The list of document skills, for the engine to open when one fits.

    Only the name and the "use when" line go in the prompt. The engine decides
    at runtime which documents a skill describes and reads its file then, so
    the prompt stays short however many issuers are covered, and a renamed
    file is recognised by its contents rather than matched on its name."""
    entries = []
    for path in sorted(skills_dir().glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        meta = _front_matter(path.read_text("utf-8"))
        if not meta.get("name"):
            continue
        scope = meta.get("schedules", "")
        if scope and schedule not in scope:
            continue
        entries.append(f"- `{path.as_posix()}` -- {meta.get('use_when', '')}")
    if not entries:
        return ""
    return ("## Document skills\n\n"
            "Notes on specific kinds of statement, written from real ones. When a "
            "document fits one of these, Read the skill file before reading the "
            "document; it says where the transactions are and what the layout's traps "
            "are. Recognise a document by its contents, not its file name. A skill "
            "never overrides what the document in front of you actually says -- if they "
            "disagree, follow the document and say so in questions[].\n\n"
            + "\n".join(entries) + "\n")


def exclusion_rules(left_out: list[dict] | None = None) -> str:
    """The shared rules for leaving documents out, plus the ones already left out.

    The rules are prompt text, not code: which document duplicates which, and
    which belongs to another schedule, is judgement that has to be made fresh
    on every year's dump. The only thing code decides is what could not be
    opened at all, and it says so here rather than hiding the file.
    """
    path = paths.PROMPTS / "_exclusions.md"
    rules = path.read_text("utf-8") if path.exists() else ""
    if left_out:
        listed = "\n".join(f"  - {f['path']}\n      {f['left_out']}" for f in left_out)
        rules += ("\n\n## Left out before you saw them\n\n"
                  "These documents are routed to this schedule but could not be "
                  "opened, so they are not in your file list:\n\n" + listed + "\n")
    return rules


def build_prompt(schedule: str, ay: str, files: list[dict], specs: list[str],
                 left_out: list[dict] | None = None) -> str:
    common = paths.PROMPTS / "_common.md"
    preamble = common.read_text("utf-8") + "\n\n" if common.exists() else ""
    instructions = (preamble + exclusion_rules(left_out) + "\n\n"
                    + skill_catalogue(schedule) + "\n"
                    + (paths.PROMPTS / f"{schedule}.md").read_text("utf-8"))
    schema = json.dumps(jsl.compose(schedule), indent=2)
    manifest = "\n".join(
        f"  - {f['path']}  ({f['bytes']:,} bytes)"
        + (f"\n      a readable conversion of {f['converted_from']} -- cite the ORIGINAL, not this file"
           if f.get("converted_from") else "")
        for f in files
    )
    return f"""{instructions}

## This run

Assessment year: {ay}
The documents folder for this return is {paths.source_root(ay).as_posix()}
Inside it, the folders you may read, and the only ones you may read:
{chr(10).join("  " + s for s in specs)}

Those folders may hold documents belonging to OTHER schedules. Extract only what
belongs to this one, and list anything else you see in unmapped[].

Documents available:
{manifest}

## Required output

Reply with a single JSON document and nothing else -- no prose before or after,
no explanation. Wrap it in a ```json fenced block. It must validate against
this schema exactly:

```json
{schema}
```
"""


def rows_field(schedule: str) -> str:
    """Which array in a schedule's data the tabular rows belong to.

    Read from the schema rather than hardcoded: Schedule CG calls its rows
    `disposals` and Schedule 112A calls them `scrips`, and a tabular path that
    assumes one of them silently builds the wrong document for the other.
    """
    data_schema = json.loads((paths.SCHEMAS / f"{schedule}.data.schema.json").read_text("utf-8"))
    props = data_schema.get("properties", {})
    for name in data_schema.get("required", []):
        if props.get(name, {}).get("type") == "array":
            return name
    raise ValueError(f"{schedule} has no required array for tabular rows")


def empty_for(sub: dict):
    """A neutral value of the right type, for the other required fields."""
    return {"object": {}, "array": [], "string": "", "integer": 0,
            "number": 0, "boolean": False}.get(sub.get("type"), None)


def build_plan_prompt(schedule: str, ay: str, files: list[dict], left_out: list[dict] | None = None) -> str:
    """Stage one of tabular extraction: map columns, do not transcribe rows."""
    from . import tabular

    rows = rows_field(schedule)

    common = ((paths.PROMPTS / "_table_plan.md").read_text("utf-8")
              + "\n\n" + exclusion_rules(left_out)
              + "\n\n" + skill_catalogue(schedule))
    specifics = (paths.PROMPTS / f"{schedule}.md").read_text("utf-8")
    plan_schema = json.loads((paths.SCHEMAS / "table_plan.schema.json").read_text("utf-8"))
    # The row shape with its shared definitions (money, citation) resolved into
    # the same document, because rows are now written as well as mapped to.
    composed = jsl.compose(schedule)
    data_schema = json.dumps({
        "row": json.loads((paths.SCHEMAS / f"{schedule}.data.schema.json").read_text("utf-8"))
               ["properties"][rows]["items"],
        "$defs": composed.get("$defs", {}),
    }, indent=2)

    previews = []
    for f in files:
        p = Path(f["abs"])
        if p.suffix.lower() not in (".csv", ".txt"):
            previews.append(f"### {p.name}\n  (read it yourself)")
            continue
        previews.append(f"### {p.name}\n{tabular.preview(p)}")

    return f"""{common}

## The schedule you are mapping to

{specifics}

Fields available to map to, from this schedule's row shape:

```json
{data_schema}
```

`read_directly[].rows` entries take this row shape exactly. In `tables`, the
`columns` keys are field names inside one such row.

## Documents, with previews of the tabular ones

Assessment year {ay}.

{chr(10).join(previews)}

## Required output

Reply with a single JSON document and nothing else, in a ```json fenced block,
validating against this schema:

```json
{json.dumps(plan_schema, indent=2)}
```
"""


def _extract_json(text: str):
    """Pull the JSON document out of a model reply."""
    fenced = re.search(r"```json\s*(.*?)```", text, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("no JSON object found in the reply")
        candidate = text[start : end + 1]
    return json.loads(candidate)



def run(ay: str, tab_id: str, engine_name: str = "mock", force: bool = False,
        on_event=None, cancel=None) -> dict:
    on_event = on_event or (lambda e: None)
    tab = paths.tab(tab_id)
    schedule = tab["id"]

    if tab["kind"] != "extract":
        raise ValueError(f"tab {tab_id!r} is a {tab['kind']} tab; it has no extraction step")
    if not tab.get("implemented"):
        raise ValueError(f"tab {tab_id!r} is registered but not built yet")

    specs = sources.tab_specs(tab_id)
    on_event({"phase": "scan", "detail": f"{len(specs)} source spec(s)"})
    files = sources.scan(ay, tab_id)
    if not files:
        # Two quite different situations produce this, and the fix differs:
        # nothing has been routed here yet, or there is genuinely nothing to
        # read. Saying which saves the reader from guessing.
        where = ", ".join(specs) or "(none configured)"
        raise ValueError(
            f"no documents matched any source for this tab: {where}. Either no document has "
            f"been routed to it yet -- press Classify documents, which is what decides where "
            f"each file goes -- or put the file in a folder named {specs[0] if specs else where} "
            f"inside the source folder. A document can also be assigned to this tab by hand "
            f"from the Documents panel."
        )
    dupes = sum(len(f.get("duplicates", [])) for f in files)
    on_event({"phase": "scan",
              "detail": f"{len(files)} document(s)" + (f", {dupes} duplicate(s) skipped" if dupes else "")})
    for archive in sources.archives(ay, tab_id):
        # Loud, because "nothing found" and "it is inside a zip" look identical
        # in the output otherwise.
        on_event({"phase": "note", "detail": f"cannot read inside archive: {archive}"})

    # Formats the engine cannot open are converted server-side rather than by
    # giving the model a shell. The fingerprint stays keyed to the ORIGINALS,
    # so a conversion-cache miss never looks like changed input.
    engine_files, derived_dirs, left_out = convert.ensure_readable(ay, files, on_event)

    pv = prompt_version(schedule)
    fp = sources.fingerprint(files, pv, engine_name)

    previous = paths.read_json(paths.extracted(ay, schedule))
    if previous and previous.get("input_fingerprint") == fp and not force:
        on_event({"phase": "cached", "detail": "inputs unchanged since last run"})
        return {"status": "cached", "run_id": previous.get("run_id"), "document": previous}

    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{schedule}-{secrets.token_hex(2)}"
    schema = jsl.compose(schedule)

    # Two shapes of extraction. For document-shaped sources the model returns
    # the data. For spreadsheet-shaped ones it returns a column mapping and we
    # read the rows, because these sheets are far too long to transcribe.
    tabular_mode = tab.get("extraction") == "tabular"
    if tabular_mode:
        prompt = build_plan_prompt(schedule, ay, engine_files, left_out)
        target_schema = json.loads((paths.SCHEMAS / "table_plan.schema.json").read_text("utf-8"))
    else:
        prompt = build_prompt(schedule, ay, engine_files, sources.tab_specs(tab_id),
                              left_out)
        target_schema = schema

    attempts: list[dict] = []
    session_id = None
    document = None
    errors: list = []
    reply = engines.Reply(text="")

    engine = engines.get(engine_name)
    add_dirs = sources.scan_dirs(ay, tab_id) + derived_dirs + [skills_dir()]

    stopped = False
    limit = engines.time_limit_for(engine_name)
    for attempt in range(1, MAX_REPAIRS + 2):
        if cancel is not None and cancel.is_set():
            stopped = True
            break
        on_event({"phase": "ask", "detail": f"attempt {attempt} via {engine_name}"})
        try:
            # One call shape for every engine. Which engine ran changes nothing
            # about what happens to its answer below.
            reply = engine.run(
                engines.Request(
                    schedule=schedule,
                    ay=ay,
                    files=engine_files,
                    prompt=prompt,
                    cwd=paths.ROOT,
                    add_dirs=add_dirs,
                    attempt=attempt,
                    session_id=session_id,
                    repair_prompt=_repair_prompt(errors) if errors else None,
                    cancel=cancel,
                    time_limit=limit,
                ),
                on_event,
            )
            session_id = reply.session_id or session_id
            candidate = _extract_json(reply.text)
        except engines.Stopped as exc:
            # Ended on purpose. Nothing is retried and nothing is written.
            stopped = True
            errors = [("", str(exc))]
            attempts.append({"attempt": attempt, "outcome": "stopped", "errors": str(exc)})
            on_event({"phase": "stopped", "detail": str(exc)[:400]})
            break
        except EngineError as exc:
            # The engine cannot do this job. Retrying produces the same error
            # three times over and buries the real message, so stop here.
            errors = [("", str(exc))]
            attempts.append({"attempt": attempt, "outcome": "engine_unavailable",
                             "errors": str(exc)})
            on_event({"phase": "failed", "detail": str(exc)[:400]})
            break
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            errors = [("", f"{type(exc).__name__}: {exc}")]
            attempts.append({"attempt": attempt, "outcome": "engine_error",
                             "errors": jsl.format_errors(errors),
                             "trace": traceback.format_exc(limit=3)})
            on_event({"phase": "invalid", "detail": str(exc)[:160]})
            continue

        errors = jsl.validate(candidate, target_schema)
        if not errors:
            document = candidate
            attempts.append({"attempt": attempt, "outcome": "valid"})
            on_event({"phase": "valid", "detail": "schema ok"})
            break

        attempts.append({"attempt": attempt, "outcome": "schema_invalid",
                         "errors": jsl.format_errors(errors)})
        on_event({"phase": "invalid", "detail": f"{len(errors)} schema violation(s)"})
        # Park the rejected output so a persistent failure is inspectable.
        paths.write_json(
            paths.data_root(ay) / "_runs" / f"{run_id}.attempt{attempt}.rejected.json",
            candidate,
        )

    manifest = {
        "run_id": run_id,
        "ay": ay,
        "schedule": schedule,
        "engine": engine_name,
        "model": reply.model if reply.text else None,
        "prompt_version": pv,
        "input_fingerprint": fp,
        "sources": [{"path": f["path"], "sha256": f["sha256"], "bytes": f["bytes"]} for f in files],
        "attempts": attempts,
        "started_at": run_id.split("-")[0],
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "result": "ok" if document else "stopped" if stopped else "failed",
    }
    paths.write_json(paths.run_manifest(ay, run_id), manifest)

    # Turn an accepted plan into the schedule document by reading the rows.
    if document is not None and tabular_mode:
        plan = document
        field = rows_field(schedule)
        row_schema = json.loads(
            (paths.SCHEMAS / f"{schedule}.data.schema.json").read_text("utf-8")
        )["properties"][field].get("items", {})

        # Long tables the engine chose to map: code reads every row.
        rows, problems, notes, stats = tabular.build(plan, engine_files, row_schema)
        complaints = tabular.plan_complaints(stats)
        if plan.get("tables"):
            on_event({"phase": "rows",
                      "detail": f"{len(rows)} row(s) read from {len(plan['tables'])} mapped table(s)"})

        # Everything else the engine read and transcribed itself -- whatever
        # the document's format or issuer. Each row is checked on its own, so
        # one malformed row is reported rather than sinking the whole schedule.
        direct_schema = {"$defs": schema.get("$defs", {}), **row_schema}
        direct = 0
        for entry in plan.get("read_directly", []):
            for i, row in enumerate(entry.get("rows") or []):
                bad = jsl.validate(row, direct_schema)
                if bad:
                    problems.append(
                        f"row {i + 1} from {entry['file']} was not used because it does not "
                        f"fit the schedule: {jsl.format_errors(bad)[:300]}")
                    continue
                rows.append(row)
                direct += 1
        if plan.get("read_directly"):
            on_event({"phase": "rows",
                      "detail": f"{direct} row(s) transcribed from "
                                f"{len(plan['read_directly'])} document(s) read directly"})

        # Every document has to be accounted for, by name, in one of the three
        # lists. A conversion stands for its original. Nothing here reads the
        # engine's prose: what was done with a document is its list and kind.
        def names_of(f: dict) -> set[str]:
            out = {Path(f["abs"]).name, f["path"], Path(f["path"]).name}
            if f.get("converted_from"):
                out |= {f["converted_from"], Path(f["converted_from"]).name}
            return out

        accounted = ({t["file"] for t in plan.get("tables", [])}
                     | {e["file"] for e in plan.get("read_directly", [])}
                     | {e["file"] for e in plan.get("excluded", [])})
        covered_originals = set()
        for f in engine_files:
            if names_of(f) & accounted:
                covered_originals.add(f.get("converted_from") or f["path"])
        unaccounted = [f["path"] for f in engine_files
                       if not f.get("converted_from") and f["path"] not in covered_originals]
        for u in unaccounted:
            problems.append(
                f"{Path(u).name} was NOT READ: the engine did not report reading it or "
                f"leaving it out, so nothing in it reached the return.")
        if unaccounted:
            on_event({"phase": "note",
                      "detail": f"{len(unaccounted)} document(s) not accounted for"})

        # An unreadable document is a gap, not a choice; the rest are choices,
        # recorded with their kind so a reviewer can check each one.
        unmapped = []
        for e in plan.get("excluded", []):
            if e.get("kind") == "unreadable":
                problems.append(f"{Path(e['file']).name} was NOT READ: {e['why']}")
            else:
                unmapped.append({"source": e["file"],
                                 "text": f"left out ({e.get('kind', 'unspecified')})",
                                 "why": e["why"]})

        # The rows go into whichever array this schedule's schema requires, and
        # its other required fields get a neutral value of the right type.
        data_schema = json.loads(
            (paths.SCHEMAS / f"{schedule}.data.schema.json").read_text("utf-8"))
        data = {field: rows}
        for name in data_schema.get("required", []):
            if name != field:
                data[name] = empty_for(data_schema["properties"].get(name, {}))
        for problem in problems[:8]:
            on_event({"phase": "note", "detail": problem})
        document = {
            "schema_version": "1.0.0",
            "ay": ay,
            "schedule": schedule,
            "status": "needs_review",
            "data": data,
            "unmapped": unmapped,
            "questions": notes + list(plan.get("notes") or []) + problems,
        }
        paths.write_json(paths.data_root(ay) / "_runs" / f"{run_id}.plan.json", plan)
        errors = jsl.validate(document, schema) + complaints
        if errors:
            on_event({"phase": "invalid", "detail": f"rows built from the plan do not validate: {len(errors)}"})
            document = None

    if document is None:
        if stopped:
            return {"status": "stopped", "run_id": run_id, "errors": jsl.format_errors(errors),
                    "manifest": manifest}
        on_event({"phase": "failed", "detail": f"gave up after {len(attempts)} attempt(s)"})
        return {"status": "failed", "run_id": run_id, "errors": jsl.format_errors(errors),
                "manifest": manifest}

    document["run_id"] = run_id
    document["input_fingerprint"] = fp
    document["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    document["engine"] = {"model": manifest["model"] or engine_name, "prompt_version": pv}
    # Provenance is the server's to state, not the model's. We scanned and
    # hashed these files; asking the model to report them back adds a chance
    # to get it wrong or, as happened, to omit them entirely.
    document["sources"] = manifest["sources"]

    # A document that could not be opened is a gap in this schedule, and the
    # reviewer has to see it on the document itself, not only in the run log.
    if left_out:
        document["questions"] = [
            f"{Path(f['path']).name} was NOT READ: {f['left_out']}. Supply a readable "
            f"copy if it holds anything for this schedule."
            for f in left_out] + list(document.get("questions") or [])
        if document.get("status") == "ok":
            document["status"] = "needs_review"

    paths.write_json(paths.extracted(ay, schedule), document)
    on_event({"phase": "write", "detail": f"extracted/{schedule}.json"})

    resolved = merge.resolve(ay, schedule)
    on_event({"phase": "merge", "detail": f"{len(resolved.get('overrides_applied', []))} override(s) re-applied"})

    return {"status": "ok", "run_id": run_id, "document": resolved, "manifest": manifest}


def _repair_prompt(errors) -> str:
    return f"""Your previous JSON did not validate. These are the exact violations,
as JSON Pointers into the document you produced:

{jsl.format_errors(errors)}

Reply with the corrected JSON document only, in a ```json fenced block.
Do not change any extracted value in order to satisfy the schema -- if a value
genuinely cannot be represented, put it in unmapped[] and explain why there.
"""
