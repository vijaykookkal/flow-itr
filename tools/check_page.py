"""Open every place on the page in a real browser and report what broke.

`check_js.py` reads the scripts; this runs them. A scanner cannot see a fault
that only happens when a renderer meets real data -- a method called on a row
that turned out to have no children, a field that changed shape -- and those
are the faults that leave one page blank while the rest looks fine.

It drives the browser already on the machine (Edge or Chrome) headless, opens
each place by its address (`/#overview`, `/#salary/reconciliation`), and looks
for three things: an error in the browser's console, the "could not be drawn"
card the page shows when a layout fails, and a page with no heading at all.
The server must be running.

    python tools/check_page.py                  # every area, every schedule
    python tools/check_page.py --all            # ...and every tab of every schedule
    python tools/check_page.py salary review    # just these
    python tools/check_page.py --shots DIR      # also save a screenshot of each
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import paths  # noqa: E402
BASE = "http://127.0.0.1:8787"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]
AREAS = ["overview", "documents", "schedules", "review", "reconcile", "reconcile/filed", "handoff",
         "home", "_profiles", "about", "about/changes", "about/about", "engines"]
SCHEDULE_TABS = ["ledger", "reconciliation", "documents", "decisions", "history"]


def browser() -> str | None:
    return next((b for b in BROWSERS if Path(b).exists()), None)


def tab_ids() -> list[str]:
    token = (paths.state_dir() / "token").read_text("utf-8").strip()
    req = urllib.request.Request(f"{BASE}/api/state", headers={"X-ITR-Token": token})
    with urllib.request.urlopen(req, timeout=60) as r:
        state = json.loads(r.read().decode("utf-8"))
    return [t["id"] for t in state.get("tabs", []) if t.get("implemented", True)]


def run(exe: str, route: str, extra: list[str]) -> tuple[str, str]:
    # Its own profile folder, so several can run at once without one waiting
    # on another's lock -- and so nothing here touches the real browser profile.
    with tempfile.TemporaryDirectory(prefix="flow-check-") as profile:
        done = subprocess.run(
            [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--disable-extensions",
             f"--user-data-dir={profile}", "--enable-logging=stderr", "--v=0",
             "--virtual-time-budget=25000", *extra, f"{BASE}/#{route}"],
            capture_output=True, timeout=180)
    return done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")


def check(exe: str, route: str, shots: Path | None) -> list[str]:
    problems = inspect(exe, route)
    if any("nothing was drawn" in p for p in problems):
        # Several browsers starting at once can leave one of them looking at a
        # page that has not finished loading. A blank page is only a finding
        # if it is blank twice.
        problems = inspect(exe, route)
    if shots:
        name = re.sub(r"[^a-z0-9_]+", "-", route.lower()).strip("-") or "root"
        run(exe, route, [f"--screenshot={shots / (name + '.png')}", "--window-size=1440,1100",
                         "--hide-scrollbars"])
    return problems


def inspect(exe: str, route: str) -> list[str]:
    dom, log = run(exe, route, ["--dump-dom"])
    problems = []
    for line in log.splitlines():
        if "CONSOLE" in line and "chrome-extension" not in line and re.search(
                r"Uncaught|SyntaxError|TypeError|ReferenceError|RangeError", line):
            problems.append(line.split("CONSOLE", 1)[1][:300].strip(":] "))
    m = re.search(r'id="render-error"[^>]*>(.*?)</pre>', dom, re.S)
    if m:
        problems.append("could not be drawn: " + html.unescape(m.group(1)).splitlines()[0])
    panel = re.search(r'<main[^>]*id="panel"[^>]*>(.*)</main>', dom, re.S)
    if not panel or "<h1" not in panel.group(1):
        problems.append("nothing was drawn at all (no heading on the page)")
    if "Could not reach the local agent" in dom:
        problems.append("the page could not reach the server")
    # replaceChildren() and append() print a null as the word "null"; a page
    # showing one has passed a missing node to the DOM.
    if panel and re.search(r">\s*(null|undefined)\s*<", panel.group(1)):
        problems.append('the page prints "null" or "undefined" where a node was missing')
    return problems


def main() -> int:
    exe = browser()
    if not exe:
        print("no Edge or Chrome found to run the page in")
        return 2

    args = sys.argv[1:]
    shots = None
    if "--shots" in args:
        at = args.index("--shots")
        shots = Path(args[at + 1]).resolve()
        shots.mkdir(parents=True, exist_ok=True)
        del args[at:at + 2]
    every = "--all" in args
    args = [a for a in args if a != "--all"]

    try:
        tabs = tab_ids()
    except OSError as exc:
        print(f"the server is not answering on {BASE}: {exc}")
        return 2

    routes = args or (AREAS + tabs + (
        [f"{t}/{s}" for t in tabs for s in SCHEDULE_TABS] if every else []))

    failed = False
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda r: (r, check(exe, r, shots)), routes))
    for route, problems in results:
        if problems:
            failed = True
            print(f"  FAIL {route}")
            for p in problems:
                print(f"         {p}")
        else:
            print(f"  ok   {route}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
