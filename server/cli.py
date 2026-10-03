"""Command-line access to the same operations the web UI calls.

Useful for testing the pipeline without a browser, and for the day the UI is
broken and you still need the numbers.

    python -m server.cli run     --tab salary [--engine claude] [--force]
    python -m server.cli run-all
    python -m server.cli compute
    python -m server.cli override --tab salary --pointer /data/... --value 123 --reason "..."
    python -m server.cli status
"""

from __future__ import annotations

import argparse
import json
import sys

from . import merge, paths, profiles, runner
from . import engines as engine_registry


def _default_engine() -> str:
    return profiles.engine_for()


def _event(e):
    print(f"  [{e['phase']:<8}] {e.get('detail', '')}", file=sys.stderr)


def cmd_run(args):
    result = runner.run(args.ay, args.tab, engine_name=args.engine,
                        force=args.force, on_event=_event)
    print(f"\n{args.tab}: {result['status']}  run_id={result.get('run_id')}")
    if result["status"] == "failed":
        print(result["errors"])
        return 1
    doc = result["document"]
    if doc.get("questions"):
        print(f"\n  {len(doc['questions'])} question(s) need review:")
        for q in doc["questions"]:
            print(f"    - {q}")
    if doc.get("unmapped"):
        print(f"\n  {len(doc['unmapped'])} unmapped item(s):")
        for u in doc["unmapped"]:
            print(f"    - {u['text']}  ({u['why'][:70]})")
    return 0


def cmd_run_all(args):
    rc = 0
    for tab in paths.load_tabs()["tabs"]:
        if tab["kind"] != "extract" or not tab.get("implemented"):
            continue
        print(f"\n=== {tab['title']} ===", file=sys.stderr)
        args.tab = tab["id"]
        rc |= cmd_run(args)
    return rc


def cmd_compute(args):
    from engine import compute

    docs, missing = {}, []
    for tab in paths.load_tabs()["tabs"]:
        if tab["kind"] != "extract":
            continue
        doc = paths.read_json(paths.resolved(args.ay, tab["id"]))
        if doc:
            docs[tab["id"]] = doc
        elif tab.get("implemented"):
            missing.append(tab["id"])
        else:
            missing.append(tab["id"])

    summary = compute.summarise(args.ay, docs, missing, profiles.settings_for())
    paths.write_json(paths.data_root(args.ay) / "resolved" / "summary.json", summary)
    print(json.dumps(summary, indent=2)[:400] + "\n...")
    print(f"\nwrote {paths.data_root(args.ay) / 'resolved' / 'summary.json'}")
    return 0


def cmd_override(args):
    value = json.loads(args.value) if args.json else int(args.value)
    entry = merge.add_override(args.ay, args.tab, args.pointer, value, args.reason)
    merge.resolve(args.ay, args.tab)
    print(json.dumps(entry, indent=2))
    return 0


def cmd_classify(args):
    from . import classify

    result = classify.run(args.ay, engine_name=args.engine, on_event=_event)
    print()
    for d in result["documents"]:
        flag = "  <-- LOW CONFIDENCE" if d["confidence"] == "low" else ""
        print(f"  {', '.join(d['tabs']) or '(no tab)':<34} {d['path'][-58:]}{flag}")
    if result["notes"]:
        print("\n  notes:")
        for n in result["notes"]:
            print(f"    - {n}")
    return 0


def cmd_profiles(args):
    store = profiles.load_all()
    for p in store["profiles"]:
        mark = "*" if p["id"] == store["active"] else " "
        print(f" {mark} {p['name']:<20} FY {p['fy']}  AY {p['ay']}  regime={p['settings']['regime']}")
        print(f"     {paths.resolve_dir(p['source_dir'])}  ->  {paths.resolve_dir(p['data_dir'])}")
    print("\n  * = active")
    print(f"  home: {paths.home()}  ({paths.home_source()})")
    return 0


def cmd_status(args):
    current = profiles.active()
    if current:
        print(f"return: {current['name']} (FY {current['fy']})  settings={current['settings']}")
    for e in engine_registry.describe():
        print(f"  engine {e['id']:<8} {'available' if e['available'] else 'NOT FOUND':<10} "
              f"reads confined: {e['confines_reads']}")
    print(f"source root: {paths.source_root(args.ay)}")
    print()
    for tab in paths.load_tabs()["tabs"]:
        doc = paths.read_json(paths.resolved(args.ay, tab["id"]))
        if doc:
            state = doc.get("status", "?")
            extra = f"  {len(doc.get('questions', []))}q"
        elif not tab.get("implemented"):
            state, extra = "not built", ""
        else:
            state, extra = "empty", ""
        print(f"  {tab['no']:>2}. {tab['title']:<26} {tab['kind']:<8} {state}{extra}")

    from . import sources
    orphans = sources.unassigned(args.ay)
    if orphans:
        print(f"\n  {len(orphans)} document(s) NO TAB WILL READ:")
        for o in orphans:
            print(f"     {o['path']}" + ("   (archive)" if o["is_archive"] else ""))
        print("  Add a matching spec to config/tabs.json, or move the file.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m server.cli")
    p.add_argument("--ay", default=profiles.active_ay())
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--tab", required=True)
    r.add_argument("--engine", default=_default_engine(), choices=["codex", "claude", "mock"])
    r.add_argument("--force", action="store_true")
    r.set_defaults(func=cmd_run)

    ra = sub.add_parser("run-all")
    ra.add_argument("--engine", default=_default_engine(), choices=["codex", "claude", "mock"])
    ra.add_argument("--force", action="store_true")
    ra.set_defaults(func=cmd_run_all)

    sub.add_parser("compute").set_defaults(func=cmd_compute)

    o = sub.add_parser("override")
    o.add_argument("--tab", required=True)
    o.add_argument("--pointer", required=True)
    o.add_argument("--value", required=True)
    o.add_argument("--reason", required=True)
    o.add_argument("--json", action="store_true", help="parse --value as JSON, not an integer")
    o.set_defaults(func=cmd_override)

    c = sub.add_parser("classify", help="route documents to schedules with an AI pass")
    c.add_argument("--engine", default=_default_engine(), choices=["codex", "claude", "mock"])
    c.set_defaults(func=cmd_classify)

    sub.add_parser("profiles").set_defaults(func=cmd_profiles)
    sub.add_parser("status").set_defaults(func=cmd_status)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
