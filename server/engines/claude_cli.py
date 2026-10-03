"""Drives Claude Code headlessly as the extraction engine.

Two properties are enforced here rather than trusted to the prompt:

  * The model gets read-only tools. It cannot write into the repo -- it returns
    JSON on stdout and `runner.py` is what writes the file.
  * --add-dir grants only the directories this tab's sources actually matched,
    so the salary extraction cannot reach your broker statements at all.

The second guarantee is only as tight as the tab's source specs. Pointing a tab
at a folder that mixes schedules -- as document exports usually do -- widens
what the model can see, which is why specs support globs: they narrow it back
down to the files that belong to the schedule.
"""

from __future__ import annotations

import json
import re
import os
import shutil
import subprocess
from pathlib import Path

from . import EngineError, Reply, Request

LIMIT_RE = re.compile(r"(usage|session|rate|weekly|daily) limit|limit reached|"
                      r"resets (at )?\d|out of (extra )?usage", re.I)

LABEL = "claude"
NOTE = "Claude subscription. Reads documents natively with no shell; reads are confined to the tab's folders."
SELECTABLE = True
CONFINES_READS = True

READ_ONLY_TOOLS = ["Read", "Glob", "Grep"]
DENIED_TOOLS = ["Write", "Edit", "NotebookEdit", "Bash", "WebFetch", "WebSearch", "Task"]

_VSCODE_EXT = Path.home() / ".vscode" / "extensions"


def find_binary() -> str | None:
    """PATH first, then the VSCode extension's bundled binary."""
    if os.environ.get("ITR_CLAUDE_BIN"):
        return os.environ["ITR_CLAUDE_BIN"]
    found = shutil.which("claude")
    if found:
        return found
    if _VSCODE_EXT.exists():
        hits = sorted(_VSCODE_EXT.glob("anthropic.claude-code-*/resources/native-binary/claude.exe"))
        if hits:
            return str(hits[-1])
        hits = sorted(_VSCODE_EXT.glob("anthropic.claude-code-*/resources/native-binary/claude"))
        if hits:
            return str(hits[-1])
    return None


def available() -> bool:
    return find_binary() is not None


def run(req: Request, on_event, model: str = "opus", timeout: int = 1800) -> Reply:
    add_dirs = [Path(d) for d in req.add_dirs]
    cwd = req.cwd
    binary = find_binary()
    if not binary:
        raise EngineError(
            "claude CLI not found. Set ITR_CLAUDE_BIN, or add it to PATH, "
            "or run with --engine mock."
        )

    cmd = [
        binary,
        "-p",
        "--output-format", "stream-json",
        "--verbose",
        # --restricted drops the code-running tools and WebFetch outright, which
        # is the guarantee we actually want. It refuses to coexist with
        # bypassPermissions, so permissions are handled by dontAsk instead:
        # anything outside --allowed-tools is denied rather than prompted for,
        # which is the only sane behaviour with no terminal attached.
        "--restricted",
        "--allowed-tools", *READ_ONLY_TOOLS,
        "--disallowed-tools", *DENIED_TOOLS,
        "--permission-mode", "dontAsk",
        "--add-dir", *[str(d) for d in add_dirs],
        "--model", model,
    ]
    if req.is_repair:
        cmd += ["--resume", req.session_id]

    where = ", ".join(d.name for d in add_dirs) or "(none)"
    on_event({"phase": "spawn", "detail": f"{Path(binary).name} on {where}"})
    return _stream(cmd, cwd, req, on_event, model, timeout, binary)


def _stream(cmd, cwd, req: Request, on_event, model, timeout, binary) -> Reply:
    """Run the CLI and read its event stream -- shared by both request shapes."""

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # The prompt goes over stdin, not argv: schedule prompts plus a schema
    # comfortably exceed the Windows command-line length limit.
    assert proc.stdin is not None
    try:
        proc.stdin.write(req.text)
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        # The process rejected its arguments and exited before reading stdin.
        # Its stderr is the useful diagnostic, so fall through and report that
        # rather than masking it with a pipe error.
        pass

    result_text = ""
    session_id = None
    for line in proc.stdout:  # type: ignore[union-attr]
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = evt.get("type")
        if kind == "system" and evt.get("subtype") == "init":
            session_id = evt.get("session_id")
            on_event({"phase": "session", "detail": f"session {str(session_id)[:8]}"})
        elif kind == "assistant":
            for block in evt.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    name = block.get("name")
                    inp = block.get("input", {})
                    target = inp.get("file_path") or inp.get("pattern") or inp.get("url") or ""
                    shown = target if str(target).startswith("http") else Path(str(target)).name
                    on_event({"phase": "tool", "detail": f"{name} {shown}".strip()})
        elif kind == "result":
            result_text = evt.get("result", "") or ""
            session_id = evt.get("session_id", session_id)
            if evt.get("subtype") != "success":
                on_event({"phase": "error", "detail": str(evt.get("subtype"))})

    stderr = proc.stderr.read() if proc.stderr else ""
    proc.wait(timeout=timeout)

    if proc.returncode != 0 and not result_text:
        raise EngineError(f"claude exited {proc.returncode}: {stderr[:800].strip()}")

    # A subscription that has run out does not fail: it replies, in prose, with
    # the reset time. Passed on as an answer, that surfaces much later as "no
    # JSON object found", which sends everyone looking for a parsing bug.
    if LIMIT_RE.search(result_text[:400]) and "{" not in result_text:
        raise EngineError(f"claude: {result_text.strip()[:300]}")

    return Reply(text=result_text, session_id=session_id, model=model)
