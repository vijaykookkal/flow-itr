"""OpenAI Codex CLI as an extraction engine, on a ChatGPT subscription.

Codex works differently from Claude Code and the difference is worth stating
plainly, because it changes what this system can promise:

  * Codex has no document-reading tool. It reads a PDF by executing a shell
    command (pdftotext, Python, and so on). Shell access is not optional here --
    it is how the agent does everything.
  * `-s read-only` sandboxes WRITES. It does not confine READS. An extraction
    pointed at the salary folder can still read elsewhere on disk, and in
    practice does: it reads its own plugin cache to load skills.

So with Codex, "the salary run cannot see your broker statements" is a request
made in the prompt, not a property the runtime enforces. With Claude Code it is
enforced, because no shell tool exists and --add-dir is the whole world.

Neither engine is trusted with correctness regardless: schema validation, the
repair loop and provenance stamping live in runner.py and run identically for
both. That is what makes swapping engines safe.
"""

from __future__ import annotations

import json
import re
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import EngineError, Reply, Request

LABEL = "codex"
NOTE = "ChatGPT subscription. Reads documents by running shell commands; reads are not confined to the tab's folder."
SELECTABLE = True
CONFINES_READS = False

_CODEX_HOME = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
_INSTALL_ROOT = Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin"


def find_binary() -> str | None:
    if os.environ.get("ITR_CODEX_BIN"):
        return os.environ["ITR_CODEX_BIN"]
    found = shutil.which("codex")
    if found:
        return found
    if _INSTALL_ROOT.exists():
        hits = sorted(_INSTALL_ROOT.glob("*/codex.exe")) or sorted(_INSTALL_ROOT.glob("*/codex"))
        if hits:
            return str(hits[-1])
    return None


def available() -> bool:
    return find_binary() is not None


def auth_mode() -> str | None:
    """'chatgpt' means subscription; 'apikey' means you are paying per token."""
    try:
        return json.loads((_CODEX_HOME / "auth.json").read_text("utf-8")).get("auth_mode")
    except (OSError, ValueError):
        return None


def _readable(command) -> str:
    """Strip the `powershell.exe -Command` wrapper so the log shows what the
    agent actually ran, not the same 60-character prefix every time."""
    text = " ".join(str(command).split())
    text = re.sub(r'^.*?(?:powershell\.exe|cmd\.exe|bash)"?\s+(?:-Command|-c)\s+', "", text, flags=re.I)
    text = text.replace("\\\\", "\\").strip("'\" ")
    return text[:110]


def run(req: Request, on_event, model: str | None = None, timeout: int = 1800) -> Reply:
    binary = find_binary()
    if not binary:
        raise EngineError(
            "codex CLI not found. Set ITR_CODEX_BIN, or add it to PATH, "
            "or choose the claude engine."
        )

    cmd = [binary, "exec", "--json", "--skip-git-repo-check", "-s", "read-only", "-C", str(req.cwd)]
    if model:
        cmd += ["-m", model]

    # Resume the same thread for a repair so the model still has the documents
    # and its own previous answer in context. `exec resume` is a different
    # subcommand with a much smaller flag set -- it inherits the sandbox, model
    # and working directory from the session, and rejects -s, -C and -m.
    if req.is_repair:
        cmd = [binary, "exec", "resume", req.session_id, "--json", "--skip-git-repo-check"]

    # The final message goes to a file rather than being scraped out of the
    # event stream; the stream is for progress only.
    with tempfile.TemporaryDirectory() as tmp:
        last = Path(tmp) / "last_message.txt"
        cmd += ["-o", str(last), "-"]  # '-': read the prompt from stdin

        on_event({"phase": "spawn", "detail": f"codex exec ({auth_mode() or 'unknown auth'})"})

        proc = subprocess.Popen(
            cmd, cwd=str(req.cwd),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
        try:
            proc.stdin.write(req.text)  # type: ignore[union-attr]
            proc.stdin.close()  # type: ignore[union-attr]
        except (BrokenPipeError, OSError):
            pass

        thread_id = req.session_id
        streamed = ""
        # Codex reports quota exhaustion, auth failure and the like as an event
        # in the stream, not on stderr. Without this the engine fails with an
        # empty message and the real reason -- "you have hit your usage limit"
        # -- never reaches you.
        failure = ""
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue

            kind = evt.get("type")
            if kind == "thread.started":
                thread_id = evt.get("thread_id", thread_id)
                on_event({"phase": "session", "detail": f"thread {str(thread_id)[:8]}"})
            elif kind == "item.started":
                item = evt.get("item", {})
                if item.get("type") == "command_execution":
                    # Surfaced deliberately: with this engine you are watching
                    # shell commands run, and you should be able to see them.
                    on_event({"phase": "shell", "detail": _readable(item.get("command", ""))})
            elif kind == "item.completed":
                item = evt.get("item", {})
                if item.get("type") == "agent_message":
                    streamed = item.get("text", "") or streamed
            elif kind in ("error", "turn.failed"):
                message = evt.get("message") or (evt.get("error") or {}).get("message") or ""
                failure = message or failure
                if message:
                    on_event({"phase": "error", "detail": message[:200]})
            elif kind == "turn.completed":
                usage = evt.get("usage", {})
                if usage:
                    on_event({"phase": "usage",
                              "detail": f"{usage.get('input_tokens', 0):,} in / "
                                        f"{usage.get('output_tokens', 0):,} out"})

        stderr = proc.stderr.read() if proc.stderr else ""
        proc.wait(timeout=timeout)

        text = last.read_text("utf-8") if last.exists() else streamed

    if failure:
        raise EngineError(f"codex: {failure}")
    if proc.returncode != 0 and not text:
        raise EngineError(f"codex exited {proc.returncode}: {stderr[:800].strip() or 'no error text'}")
    if not text:
        raise EngineError("codex produced no final message")

    return Reply(text=text, session_id=thread_id, model=model or "codex-default")
