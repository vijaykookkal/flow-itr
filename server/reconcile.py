"""Comparing a schedule against what was reported to the department.

Two sides, produced two different ways, on purpose:

  * **Reported** is read at runtime out of the AIS, the TIS, Form 26AS and any
    broker summary. Only a reader can tell which line of a statement is which,
    and next year's statement will look different.
  * **Ours** is computed in code (engine/measures.py) from the ledger, by name.
    If the engine supplied both sides the comparison would only show that it
    agrees with itself.

The engine maps each reported line to one named measure and explains any
difference. Code then does the subtraction and decides the status, so a
difference cannot be talked away in prose.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import classify, convert, engines, jsonschema_lite as jsl, paths, runner, sources
from engine import measures

# Below this, a difference is the two sides rounding differently rather than a
# transaction missing: reporting is in whole rupees, broker files carry paise.
ROUNDING_TOLERANCE = 100


def schema() -> dict:
    return json.loads((paths.SCHEMAS / "reconciliation.schema.json").read_text("utf-8"))


def stored(ay: str, schedule: str):
    return paths.data_root(ay) / "reconciliation" / f"{schedule}.json"


def build_prompt(schedule: str, ay: str, files: list[dict], available: list[dict]) -> str:
    rules = (paths.PROMPTS / "_reconcile.md").read_text("utf-8")
    listed = "\n".join(
        f"  - {f['path']}  ({f['bytes']:,} bytes)"
        + (f"\n      a readable conversion of {f['converted_from']} -- cite the ORIGINAL"
           if f.get("converted_from") else "")
        for f in files)
    computed = "\n".join(
        f"  - `{m['key']}` -- {m['label']}: "
        + (f"{m['amount']:,}" if m.get("is_count") else f"Rs {m['amount']:,}")
        + f"\n      {m['basis']}"
        for m in available)
    return f"""{rules}

{runner.skill_catalogue("reconcile")}

## This schedule

{schedule} for assessment year {ay}.

## The figures this return computes

Match lines to these by `key`. They are computed from the ledger; take them as
given.

{computed}

## Documents

{listed}

## Required output

Reply with a single JSON document and nothing else, in a ```json fenced block,
validating against:

```json
{json.dumps(schema(), indent=2)}
```
"""


def _verdict(reported: int, ours: int, accounted: list[dict]) -> dict:
    """Compare two figures, and check any explanation adds up to the gap.

    An explanation is only an explanation if its parts account for the whole
    difference. Prose that sounds convincing but leaves rupees unaccounted for
    is exactly what a reconciliation exists to catch, so the arithmetic decides
    the status, not the wording."""
    difference = reported - ours
    claimed = sum(int(a.get("amount") or 0) for a in accounted or [])
    if difference == 0:
        return {"status": "matches", "difference": 0, "unaccounted": 0}
    if abs(difference) <= ROUNDING_TOLERANCE:
        return {"status": "rounding", "difference": difference, "unaccounted": 0}
    unaccounted = difference - claimed
    if accounted and abs(unaccounted) <= ROUNDING_TOLERANCE:
        return {"status": "explained", "difference": difference, "unaccounted": unaccounted}
    return {"status": "unexplained", "difference": difference, "unaccounted": unaccounted}


def compare(lines: list[dict], available: list[dict]) -> tuple[list[dict], list[dict]]:
    """(lines with their verdicts, one group per measure with components).

    A figure reported per broker or per depository is a component: comparing
    any one of them against the whole ledger produces a difference that means
    nothing. Components are therefore added up and the total compared once.
    """
    by_key = {m["key"]: m for m in available}
    out, groups = [], {}

    for line in lines:
        key = line.get("measure")
        measure = by_key.get(key) if key else None
        reported = int((line.get("reported") or {}).get("amount") or 0)
        relation = line.get("relation") or ("equals" if measure else "none")

        if measure is None or relation == "none":
            out.append({**line, "status": "not_comparable", "difference": None, "ours": None})
            continue

        if relation == "part_of":
            group = groups.setdefault(key, {"measure": key, "label": measure["label"],
                                            "ours": int(measure["amount"]), "reported": 0,
                                            "rows": measure["rows"], "components": [],
                                            "accounted_by": []})
            group["reported"] += reported
            group["components"].append(line.get("category", ""))
            group["accounted_by"].extend(line.get("accounted_by") or [])
            out.append({**line, "status": "component", "difference": None,
                        "ours": int(measure["amount"]), "measure_label": measure["label"],
                        "rows": measure["rows"]})
            continue

        verdict = _verdict(reported, int(measure["amount"]), line.get("accounted_by"))
        out.append({**line, **verdict, "ours": int(measure["amount"]),
                    "measure_label": measure["label"], "rows": measure["rows"]})

    grouped = []
    for group in groups.values():
        grouped.append({**group, **_verdict(group["reported"], group["ours"], group["accounted_by"])})
    return out, grouped


def _tally(lines: list[dict], groups: list[dict], available: list[dict]) -> tuple[list[dict], dict]:
    """(what the return holds that nothing was reported against, counts by verdict)."""
    # A measure nothing reported against is worth seeing too: it is where the
    # department has not been told about something, which is the riskier gap.
    reported_keys = {ln.get("measure") for ln in lines}
    unreported = [
        {"key": m["key"], "label": m["label"], "amount": m["amount"], "rows": m["rows"]}
        for m in available
        if m["key"] not in reported_keys and not m.get("is_count") and m["amount"]
    ]
    counts: dict[str, int] = {}
    for item in lines + groups:
        if item["status"] == "component":
            continue                      # counted through its group
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return unreported, counts


# What compare() adds to a line. Taken off again before a line is compared
# afresh, so a verdict is never carried over from figures that have moved.
VERDICT_KEYS = ("status", "difference", "ours", "unaccounted", "measure_label", "rows")


def refresh(ay: str, tab_id: str) -> dict | None:
    """The same reported lines, against this return's figures as they now stand.

    A comparison is two halves. What the department was told is read out of
    documents by the engine and does not change until the documents do. What
    this return computes changes every time a schedule is read again or a
    figure is corrected -- and the verdict is only arithmetic between the two.
    So when the figures move the arithmetic is simply done again, here, with no
    engine. A stored verdict that still showed last week's figure would be the
    one place on the page where a difference could be wrong without anyone
    having made a mistake.

    What cannot be refreshed this way is the engine's own prose: its questions
    and the explanations it offered for a difference were written against the
    earlier figures. Those are left as they are and the comparison is marked,
    so the page can say it should be run again for a fresh reading.
    """
    path = stored(ay, tab_id)
    document = paths.read_json(path)
    if not document:
        return None
    summary = paths.read_json(paths.data_root(ay) / "resolved" / "summary.json") or {}
    available = measures.for_schedule(tab_id, summary, paths.read_json(paths.resolved(ay, tab_id)))
    if not available:
        return document

    before = [(g.get("measure"), g.get("ours"), g.get("status")) for g in document.get("groups", [])] \
        + [(ln.get("category"), ln.get("ours"), ln.get("status")) for ln in document.get("lines", [])]
    known = {m["key"] for m in available}
    stripped = []
    for line in document.get("lines", []):
        line = {k: v for k, v in line.items() if k not in VERDICT_KEYS}
        if line.get("measure") and line["measure"] not in known:
            line = {**line, "measure": None, "relation": "none"}
        stripped.append(line)
    lines, groups = compare(stripped, available)
    after = [(g.get("measure"), g.get("ours"), g.get("status")) for g in groups] \
        + [(ln.get("category"), ln.get("ours"), ln.get("status")) for ln in lines]
    if after == before:
        return document

    unreported, counts = _tally(lines, groups, available)
    document.update(lines=lines, groups=groups, unreported=unreported, measures=available,
                    counts=counts,
                    # The figures on our side as of this computation; the
                    # reported side is still as read at `generated_at`.
                    figures_as_of=summary.get("computed_at"))
    paths.write_json(path, document)
    return document


def refresh_all(ay: str) -> list[str]:
    """Every stored comparison, brought up to the current figures."""
    changed = []
    folder = paths.data_root(ay) / "reconciliation"
    if not folder.is_dir():
        return changed
    for path in sorted(folder.glob("*.json")):
        before = path.read_bytes()
        try:
            refresh(ay, path.stem)
        except Exception:  # noqa: BLE001 - a comparison that cannot be redone is left as it was
            continue
        if path.read_bytes() != before:
            changed.append(path.stem)
    return changed


def run(ay: str, tab_id: str, engine_name: str, on_event, cancel=None) -> dict:
    on_event = on_event or (lambda e: None)
    summary = paths.read_json(paths.data_root(ay) / "resolved" / "summary.json") or {}
    # Capital Gains measures come from the computed ledger (foreign amounts are
    # converted there); every other schedule measures its own resolved data.
    doc = paths.read_json(paths.resolved(ay, tab_id))
    available = measures.for_schedule(tab_id, summary, doc)
    if not available:
        raise ValueError(f"{tab_id} has no measures to reconcile against yet")

    # The schedule's own documents, plus the department's records wherever they
    # are filed. The AIS and TIS are routed to Taxes Paid, so a schedule that
    # relied on its own routing would reconcile against half the evidence.
    files = sources.scan(ay, tab_id)
    base = paths.source_root(ay)
    seen = {f["sha256"] for f in files}
    extra = []
    for path in classify.reported_summaries(ay):
        full = base / path
        if not full.is_file():
            continue
        digest = sources.sha256_file(full)
        if digest in seen:          # already here, or a second copy of it
            continue
        seen.add(digest)
        extra.append({"path": path, "abs": str(full), "bytes": full.stat().st_size,
                      "sha256": digest})
    if extra:
        on_event({"phase": "note",
                  "detail": "also reading the department's own records: "
                            + ", ".join(f["path"].rsplit("/", 1)[-1] for f in extra)})
    files = files + extra

    engine_files, derived_dirs, left_out = convert.ensure_readable(ay, files, on_event)
    on_event({"phase": "scan", "detail": f"{len(files)} document(s), {len(available)} computed figure(s)"})

    engine = engines.get(engine_name)
    reply = engine.run(
        engines.Request(schedule=tab_id, ay=ay, files=engine_files,
                        cancel=cancel, time_limit=engines.time_limit_for(engine_name),
                        prompt=build_prompt(tab_id, ay, engine_files, available),
                        cwd=paths.ROOT,
                        add_dirs=sources.scan_dirs(ay, tab_id) + derived_dirs
                                 + [Path(f["abs"]).parent for f in extra] + [runner.skills_dir()]),
        on_event,
    )
    answer = runner._extract_json(reply.text)
    bad = jsl.validate(answer, schema())
    if bad:
        raise engines.EngineError("reconciliation did not validate: " + jsl.format_errors(bad)[:400])

    known = {m["key"] for m in available}
    cleaned = []
    for line in answer.get("lines", []):
        if line.get("measure") and line["measure"] not in known:
            line = {**line, "why": f"[named an unknown figure {line['measure']!r}] " + line.get("why", ""),
                    "measure": None, "relation": "none"}
        cleaned.append(line)
    lines, groups = compare(cleaned, available)
    unreported, counts = _tally(lines, groups, available)

    document = {
        "ay": ay,
        "schedule": tab_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": {"model": reply.model or engine_name},
        "about": measures.about(tab_id),
        # The documents this comparison actually drew on, for the card to name.
        "against": sorted({(ln.get("source") or "").rsplit("/", 1)[-1]
                           for ln in lines if ln.get("source")}),
        "lines": lines,
        "groups": groups,
        "unreported": unreported,
        "measures": available,
        "questions": list(answer.get("questions", []))
                     + [f"{f['path']} was NOT READ for reconciliation: {f['left_out']}" for f in left_out],
        "counts": counts,
    }
    paths.write_json(stored(ay, tab_id), document)
    on_event({"phase": "write", "detail": f"reconciliation/{tab_id}.json"})
    for ln in lines:
        on_event({"phase": "line",
                  "detail": f"{ln['status']}: {ln['category']} reported "
                            f"{(ln.get('reported') or {}).get('amount', 0):,}"
                            + (f", ours {ln['ours']:,}, difference {ln['difference']:,}"
                               if ln.get("difference") is not None else "")})
    for g in groups:
        on_event({"phase": "group",
                  "detail": f"{g['status']}: {g['label']} -- {len(g['components'])} reported line(s) "
                            f"total {g['reported']:,} against {g['ours']:,}, difference {g['difference']:,}"
                            + (f", {g['unaccounted']:,} unaccounted" if g["unaccounted"] else "")})
    return document
