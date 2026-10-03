"""Click through the page in a real browser and save a screenshot of the result.

`check_page.py` opens each place and reports what broke on arrival. Some things
only exist after an action -- the evidence panel beside a figure, a search, a
row opened to its decision form -- and there is no Node here to drive a browser
with. This does it with what the machine already has: it puts a small harness
page beside the app for the length of the run, which loads the app in a frame,
performs the steps, and leaves the result on screen for headless Edge or Chrome
to photograph. The harness is removed afterwards.

    python tools/probe_page.py OUT.png ROUTE "STEPS" [--size 1440x1100] [--report]

STEPS are separated by semicolons:

    click:<css selector>@<n>   click the n-th match (0 if omitted)
    key:<key>                  press a key on the document (k is sent with Ctrl)
    type:<text>                set the focused field's value
    wait:<ms>
    theme:dark | theme:light
    scroll:<y>
    eval:<javascript>          its value is reported with --report

    python tools/probe_page.py ev.png salary "click:.money@0;wait:2000"
    python tools/probe_page.py find.png overview "key:k;type:314363"

Two things worth knowing. The steps really run: a click on "Settle" settles, so
point this at things that are safe to do. And with --report the page is loaded
a second time to read the results back, so the steps run twice.

A step's text cannot itself contain a semicolon.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8787"
# The underscore keeps it out of the page's own version fingerprint, so a page
# left open does not announce that it has been updated while this runs.
HARNESS = ROOT / "web" / "_probe.html"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]

HARNESS_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>probe</title>
<style>html,body{margin:0;height:100%;overflow:hidden}iframe{border:0;width:100%;height:100%;display:block}</style>
</head><body><iframe id="f"></iframe>
<script>
const p = new URLSearchParams(location.search);
const f = document.getElementById('f');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(sel, ms = 20000) {
  const t = Date.now();
  while (Date.now() - t < ms) {
    const n = f.contentDocument.querySelectorAll(sel);
    if (n.length) return n;
    await sleep(100);
  }
  return [];
}
f.onload = async () => {
  if (f.dataset.ran) return;
  f.dataset.ran = '1';
  await waitFor('#panel h1');
  const log = [];
  for (const step of (p.get('steps') || '').split(';').filter(Boolean)) {
    const [verb, ...rest] = step.split(':');
    const arg = rest.join(':');
    const doc = f.contentDocument;
    const win = f.contentWindow;
    try {
      if (verb === 'click') {
        const [sel, n] = arg.split('@');
        const nodes = await waitFor(sel);
        log.push(verb + ' ' + sel + ': ' + nodes.length + ' found');
        if (nodes[Number(n || 0)]) nodes[Number(n || 0)].click();
      } else if (verb === 'key') {
        doc.dispatchEvent(new win.KeyboardEvent('keydown', { key: arg, ctrlKey: arg === 'k', bubbles: true }));
      } else if (verb === 'type') {
        doc.activeElement.value = arg;
        doc.activeElement.dispatchEvent(new win.Event('input', { bubbles: true }));
      } else if (verb === 'wait') {
        await sleep(Number(arg));
      } else if (verb === 'theme') {
        doc.documentElement.dataset.theme = arg;
      } else if (verb === 'scroll') {
        win.scrollTo(0, Number(arg));
      } else if (verb === 'eval') {
        log.push(String(win.eval(arg)));
      }
    } catch (err) {
      log.push(step + ' FAILED: ' + err.message);
    }
    await sleep(350);
  }
  const out = document.createElement('pre');
  out.id = 'probe-report';
  out.hidden = true;
  out.textContent = log.join('\\n');
  document.body.append(out);
};
f.src = '/#' + (p.get('route') || 'overview');
</script></body></html>
"""


def browser() -> str | None:
    return next((b for b in BROWSERS if Path(b).exists()), None)


def run(exe: str, url: str, extra: list[str]) -> tuple[str, str]:
    with tempfile.TemporaryDirectory(prefix="flow-probe-") as profile:
        done = subprocess.run(
            [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--disable-extensions",
             f"--user-data-dir={profile}", "--enable-logging=stderr", "--v=0",
             "--virtual-time-budget=40000", *extra, url],
            capture_output=True, timeout=240)
    return done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")


def main() -> int:
    args = sys.argv[1:]
    report = "--report" in args
    args = [a for a in args if a != "--report"]
    size = "1440x1100"
    if "--size" in args:
        at = args.index("--size")
        size = args[at + 1]
        del args[at:at + 2]
    if len(args) < 2:
        print(__doc__)
        return 2
    shot, route = Path(args[0]).resolve(), args[1]
    steps = args[2] if len(args) > 2 else ""
    exe = browser()
    if not exe:
        print("no Edge or Chrome found to run the page in")
        return 2

    window = f"--window-size={size.replace('x', ',')}"
    url = f"{BASE}/_probe.html?" + urllib.parse.urlencode({"route": route, "steps": steps})
    shot.parent.mkdir(parents=True, exist_ok=True)
    HARNESS.write_text(HARNESS_HTML, encoding="utf-8")
    try:
        _dom, log = run(exe, url, [f"--screenshot={shot}", window, "--hide-scrollbars"])
        for line in log.splitlines():
            if "CONSOLE" in line and re.search(r"Uncaught|Error", line):
                print("  console:", line.split("CONSOLE", 1)[1][:300].strip(":] "))
        if report:
            dom, _log = run(exe, url, ["--dump-dom", window])
            found = re.search(r'<pre id="probe-report"[^>]*>(.*?)</pre>', dom, re.S)
            import html
            print(html.unescape(found.group(1)) if found else "(the steps did not finish)")
    finally:
        HARNESS.unlink(missing_ok=True)
    print(f"  saved {shot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
