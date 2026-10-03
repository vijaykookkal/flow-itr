"""Restart the local server and prove that it restarted.

Python imports a module once. A server started before an edit goes on running
the code it started with, and the symptom is not an error -- it is a correct
answer to the wrong question: an extraction that still reports a document as
unreadable after the reader was fixed, a computation that still shows the old
line numbers. The figures look plausible, so the stale process is believed.

Killing the old process and starting a new one is not enough on its own,
because the port takes a moment to be released and a new process that cannot
bind simply dies, leaving the old one serving. Then everything looks fine and
nothing has changed. So this waits for the port, starts the server, waits for
it to answer, and prints the old and new process ids for comparison. If they
are not different, it says so and exits non-zero.

    python tools/restart_server.py
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import paths  # noqa: E402
HOST, PORT = "127.0.0.1", 8787


def listening_pid() -> int | None:
    """The pid holding the port, via netstat -- no dependencies."""
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TCP" and parts[1].endswith(f":{PORT}") \
                and parts[3].upper() == "LISTENING":
            try:
                return int(parts[4])
            except ValueError:
                return None
    return None


def port_free(timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex((HOST, PORT)) != 0:
                return True
        time.sleep(0.3)
    return False


def answers(timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{PORT}/", timeout=3) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    old = listening_pid()
    print(f"  was: {old if old else 'nothing listening'}")

    if old:
        subprocess.run(["taskkill", "/PID", str(old), "/F"],
                       capture_output=True, text=True)
        if not port_free():
            print(f"  FAIL port {PORT} is still held after the kill; "
                  f"nothing was started, so the old server is still the one running")
            return 1

    log = paths.state_dir() / "server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = log.open("ab")
    subprocess.Popen([sys.executable, "-m", "server", "--no-browser"],
                     cwd=str(ROOT), stdout=handle, stderr=handle,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))

    if not answers():
        print(f"  FAIL the new server never answered on {HOST}:{PORT}; see {log}")
        return 1

    new = listening_pid()
    print(f"  now: {new}")
    if old and new == old:
        print("  FAIL same process id -- the old server is still serving, "
              "and your edits are not loaded")
        return 1
    print(f"  ok   restarted, logging to {log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
