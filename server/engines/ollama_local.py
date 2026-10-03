"""An open model on this computer, through Ollama.

Nothing leaves the machine: the documents are read by a model running locally,
which is the one engine for which that is true. The price is that the model is
smaller than Claude's or GPT's and runs on whatever this computer has -- often
just its processor -- so it is slower and makes more mistakes on messy
statements. Everything downstream is unchanged: the runner validates the answer
against the schedule's schema, asks for a repair when it does not fit, and the
reconciliation with the AIS, TIS and Form 26AS still catches what slipped.

How it differs from the command-line engines:

  * **It cannot open files.** Claude Code and Codex are agents that read the
    documents themselves. A model behind Ollama only sees text it is sent, so
    the documents are sent: the text Flow already makes of every PDF,
    spreadsheet and Word file (server/convert.py), with the original's name on
    it so citations still point at the document you hold. A scanned PDF with no
    text layer therefore cannot be read here.

  * **Its window is finite and set here.** Ollama only gives a model as much
    context as it is asked for. If a schedule's documents do not fit, the run
    stops and says so, rather than quietly dropping the rows that did not fit:
    a missing sale is worse than an error. Sorting is the exception -- it only
    needs the start of each document to tell what it is.

  * **Its answer is held to the schema by the server.** Ollama can constrain
    the reply to a JSON schema. The schedule's schema is passed when the server
    accepts it, and plain JSON mode otherwise.

Configured in config/tabs.json under "ollama" (host, model, num_ctx, think), or
with OLLAMA_HOST, ITR_OLLAMA_MODEL and ITR_OLLAMA_NUM_CTX.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import secrets
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from . import EngineError, Reply, Request

LABEL = "Ollama"
NOTE = ("Reads with an open model through Ollama, so no document leaves this computer. Slower and "
        "less accurate than Claude or Codex on messy statements, and it cannot read scanned PDFs "
        "that have no text.")
SELECTABLE = True
# It sees only the text Flow sends it: the tightest confinement of any engine.
CONFINES_READS = True

# Tried in order when no model is configured: light mixture-of-experts models
# first, because only a few billion parameters work per token and a laptop
# processor can keep up with that.
PREFERRED = ["gpt-oss:20b", "qwen3:30b-a3b", "qwen3:30b", "qwen3:14b", "qwen3:8b",
             "gemma3:12b", "qwen2.5:14b", "llama3.1:8b"]

TEXT_SUFFIXES = {".txt", ".csv", ".tsv", ".json", ".md", ".xml", ".html", ".htm"}
CHARS_PER_TOKEN = 3.2           # conservative for statements full of figures
_SESSIONS: dict[str, list[dict]] = {}
_MODELS: dict = {"at": 0.0, "names": []}


# --------------------------------------------------------------------------
# settings and what is installed
# --------------------------------------------------------------------------
def settings(model: str | None = None) -> dict:
    """Ollama's settings; with a model, that model's own window and reasoning
    laid over the shared ones. Models differ: a large window suits one and
    exhausts another's memory, and gpt-oss reasons in levels where others
    only switch reasoning on or off."""
    try:
        from server import settings as user_settings
        conf = dict(user_settings.get("ollama") or {})
    except Exception:  # noqa: BLE001
        conf = {}
    if model:
        own = (conf.get("models") or {}).get(model) or {}
        conf.update({k: v for k, v in own.items() if v is not None})
    host = os.environ.get("OLLAMA_HOST") or conf.get("host") or "http://127.0.0.1:11434"
    if not host.startswith("http"):
        host = "http://" + host
    return {
        "host": host.rstrip("/"),
        "model": os.environ.get("ITR_OLLAMA_MODEL") or conf.get("model") or "",
        "num_ctx": int(os.environ.get("ITR_OLLAMA_NUM_CTX") or conf.get("num_ctx") or 65536),
        "think": conf.get("think", False),
        # Seconds one request may take; the general limit for Ollama when
        # not set here (time_limits_minutes, two hours by default).
        "timeout": int(conf.get("timeout") or 0) or _limit(),
    }


def _limit() -> int:
    from . import time_limit_for
    return time_limit_for("ollama")


def models() -> list[str]:
    """Models installed in the local Ollama, or none if it is not running."""
    if time.time() - _MODELS["at"] < 20:
        return _MODELS["names"]
    names: list[str] = []
    try:
        with urllib.request.urlopen(settings()["host"] + "/api/tags", timeout=1.5) as r:
            names = [m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])]
    except (OSError, ValueError, KeyError):
        names = []
    # Embedding models cannot answer a question.
    names = [n for n in names if "embed" not in n.lower()]
    _MODELS.update(at=time.time(), names=names)
    return names


def available() -> bool:
    return bool(models())


def model_list() -> list[dict]:
    """Every model installed in Ollama, each a reader of its own."""
    return [{"id": name, "label": name, "note": "An open model on this computer."} for name in models()]


def default_model() -> str:
    installed = models()
    chosen = settings()["model"]
    if chosen and (chosen in installed or f"{chosen}:latest" in installed):
        return chosen
    for want in PREFERRED:
        if want in installed or f"{want}:latest" in installed:
            return want
    return installed[0] if installed else (chosen or PREFERRED[0])


# --------------------------------------------------------------------------
# what the model is sent
# --------------------------------------------------------------------------
def _read(path: Path) -> str | None:
    """A document's text, with the runs of spaces a PDF uses for layout cut
    to two: columns stay apart, and a long statement costs less window."""
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return None
    try:
        text = path.read_text("utf-8", errors="replace")
    except OSError:
        return None
    return re.sub(r"\n[ \t]*\n+", "\n", re.sub(r"[ \t]{3,}", "  ", text))


def _documents(req: Request, on_event) -> list[tuple[str, str]]:
    """(name, text) for every document, as text a model can read."""
    files = list(req.files)
    if req.schedule == "_classify":
        # Sorting is handed the originals. Their text is made the same way a
        # reading makes it, and cached by content, so it is made once.
        from server import convert, sources
        files = [{**f, "sha256": f.get("sha256") or sources.sha256_file(Path(f["abs"]))} for f in files
                 if not f.get("is_archive")]
        files, _dirs, _left = convert.ensure_readable(req.ay, files, on_event)

    converted = {f["converted_from"] for f in files if f.get("converted_from")}
    # A table-plan prompt already carries the head of every spreadsheet: the
    # model maps columns from that and code reads the rows, so only the
    # documents it was told to read itself need sending.
    previewed = set()
    if "## Documents, with previews of the tabular ones" in req.prompt:
        # Spreadsheets only: a PDF's text is previewed too, but its rows are
        # read by the model, which needs all of it.
        previewed = {name for name in re.findall(r"^### (.+)$", req.prompt, re.M)
                     if name.lower().endswith(".csv")}
    out: list[tuple[str, str]] = []
    for f in files:
        if Path(f["abs"]).name in previewed:
            continue
        if f.get("converted_from"):
            text = _read(Path(f["abs"]))
            if text is not None:
                out.append((f"{f['converted_from']} (its text: {Path(f['abs']).name})", text))
            continue
        if f["path"] in converted:
            continue                    # represented by its text above
        text = _read(Path(f["abs"]))
        if text is None:
            on_event({"phase": "note", "detail": f"{f['path']}: no text a local model can read"})
            continue
        out.append((f["path"], text))
    return out


def _skills(prompt: str) -> list[tuple[str, str]]:
    """The document-reading notes the prompt points at, which an agent would
    open itself."""
    found = []
    for path in dict.fromkeys(re.findall(r"`([^`]+?prompts/skills/[^`]+?\.md)`", prompt)):
        try:
            found.append((Path(path).name, Path(path).read_text("utf-8")))
        except OSError:
            pass
    return sorted(found, key=lambda s: len(s[1]))


def _schema_from(prompt: str):
    """The JSON schema the prompt asks the reply to follow: its last json block."""
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", prompt, re.S)
    for block in reversed(blocks):
        try:
            schema = json.loads(block)
        except ValueError:
            continue
        if isinstance(schema, dict) and ("properties" in schema or "type" in schema):
            return schema
    return None


def _tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1


def _first_message(req: Request, on_event, num_ctx: int) -> str:
    if req.schedule == "fx_rates":
        raise EngineError(
            "Looking up exchange rates needs an engine that can read the rate archive, which a "
            "local model cannot. Enter the rate by hand on the Capital gains page, or look it up "
            "with Claude or Codex.")
    docs = _documents(req, on_event)
    reserve = max(4096, num_ctx // 4)          # room for the answer
    budget = num_ctx - reserve - _tokens(req.prompt) - 400
    need = sum(_tokens(t) for _, t in docs)

    if need > budget:
        if req.schedule != "_classify":
            raise EngineError(
                f"The documents for this schedule come to about {need:,} tokens, and the local "
                f"model has room for about {max(budget, 0):,} (num_ctx {num_ctx:,}). Nothing was "
                f"cut short, because a dropped row would be a silent error. Raise ollama.num_ctx in "
                f"config/tabs.json if this computer has the memory, split the documents, or read "
                f"this schedule with Claude or Codex.")
        # Sorting needs only enough of each document to tell what it is.
        share = max(600, int(budget * CHARS_PER_TOKEN / max(1, len(docs))))
        docs = [(name, text[:share] + ("\n[... the rest of this document is not shown ...]"
                                       if len(text) > share else "")) for name, text in docs]
        on_event({"phase": "note", "detail": f"sorting from the first {share:,} characters of each document"})
        need = sum(_tokens(t) for _, t in docs)

    parts = [req.prompt, "",
             "## The documents' text",
             "",
             "You cannot open files. Every document named above is given here as text, under its "
             "own name. Where the instructions say to Read a file, read it here. Cite a document by "
             "the name shown in its heading, without the part in brackets."]
    for name, text in docs:
        parts += ["", f"### {name}", "```", text.strip(), "```"]

    spare = budget - need
    skills = []
    for name, text in _skills(req.prompt):
        if _tokens(text) + 50 < spare:
            skills.append((name, text))
            spare -= _tokens(text) + 50
    if skills:
        parts += ["", "## Document skills referred to above", ""]
        for name, text in skills:
            parts += [f"### {name}", text.strip(), ""]
    return "\n".join(parts)


# --------------------------------------------------------------------------
# the call
# --------------------------------------------------------------------------
class _Refused(Exception):
    """Ollama answered with an HTTP error: a request it cannot serve as asked."""

    def __init__(self, code: int, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def _chat(conf: dict, model: str, messages: list[dict], fmt, on_event, req: Request) -> tuple[str, dict]:
    body = {"model": model, "messages": messages, "stream": True,
            "options": {"temperature": 0, "num_ctx": conf["num_ctx"]}}
    if fmt is not None:
        body["format"] = fmt
    think = conf["think"]
    if think is not None:
        # gpt-oss takes a level and cannot switch reasoning off; the others take a yes or no.
        body["think"] = ("low" if not think else think) if model.startswith("gpt-oss") else bool(think)

    # A plain connection rather than urlopen, so the watcher can cut it even
    # while Ollama is still reading the prompt and has sent nothing back.
    # Ollama stops working on a request whose connection has gone.
    url = urlparse(conf["host"])
    conn = http.client.HTTPConnection(url.hostname or "127.0.0.1", url.port or 11434)

    def cut() -> None:
        try:
            if conn.sock is not None:
                conn.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        conn.close()

    from . import Watch
    watch = Watch(req, cut, conf["timeout"])
    text, last, tokens, final = [], time.time(), 0, {}
    try:
        conn.request("POST", "/api/chat", body=json.dumps(body).encode("utf-8"),
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status >= 400:
            raise _Refused(resp.status, resp.read().decode("utf-8", "replace")[:300])
        while True:
            raw = resp.readline()
            if not raw:
                break
            if not raw.strip():
                continue
            chunk = json.loads(raw.decode("utf-8"))
            if chunk.get("error"):
                raise EngineError(f"Ollama: {chunk['error']}")
            piece = (chunk.get("message") or {}).get("content") or ""
            if piece:
                text.append(piece)
                tokens += 1
            if time.time() - last > 15:
                on_event({"phase": "progress", "detail": f"{model}: {tokens:,} pieces of the answer so far"})
                last = time.time()
            if chunk.get("done"):
                final = chunk
                break
    except (OSError, http.client.HTTPException, ValueError) as exc:
        watch.finish()
        watch.raise_if_ended()          # cut on purpose: say so, not "connection reset"
        raise EngineError(f"Ollama could not be reached at {conf['host']}: {exc}") from exc
    finally:
        watch.finish()
        conn.close()
    watch.raise_if_ended()
    if not final:
        raise EngineError("Ollama ended the answer before it was complete")
    return "".join(text), final


def run(req: Request, on_event, model: str | None = None, timeout: int | None = None) -> Reply:
    if not models():
        raise EngineError(
            f"Ollama is not answering at {settings()['host']}, or has no model. Install Ollama from "
            f"ollama.com, then add a model on the Reading engines page.")
    model = model or default_model()
    conf = settings(model)
    if timeout:
        conf["timeout"] = timeout

    if req.is_repair and req.session_id in _SESSIONS:
        messages = _SESSIONS[req.session_id] + [{"role": "user", "content": req.repair_prompt}]
        session_id = req.session_id
    else:
        on_event({"phase": "spawn", "detail": f"Ollama {model} on this computer, window {conf['num_ctx']:,} tokens"})
        messages = [
            {"role": "system", "content": "You read Indian income-tax documents and answer with one JSON "
                                          "document only, exactly in the shape asked for."},
            {"role": "user", "content": _first_message(req, on_event, conf["num_ctx"])},
        ]
        session_id = secrets.token_hex(4)

    schema = _schema_from(req.prompt)
    started = time.time()
    attempts = [schema, "json"] if schema else ["json"]
    last_error = None
    for fmt in attempts:
        try:
            text, final = _chat(conf, model, messages, fmt, on_event, req)
            break
        except _Refused as exc:
            last_error = f"Ollama refused the request ({exc.code}): {exc.detail}"
            if "think" in exc.detail.lower() and conf["think"] is not None:
                conf["think"] = None    # a model that does not think: ask again without it
                text, final = _chat(conf, model, messages, fmt, on_event, req)
                break
            continue                    # a schema the server cannot use: plain JSON next
    else:
        raise EngineError(last_error or "Ollama did not answer")

    seconds = time.time() - started
    on_event({"phase": "session", "detail": (
        f"{model}: read {final.get('prompt_eval_count', 0):,} tokens and wrote "
        f"{final.get('eval_count', 0):,} in {seconds:,.0f}s")})
    _SESSIONS[session_id] = messages + [{"role": "assistant", "content": text}]
    return Reply(text=text, session_id=session_id, model=f"ollama:{model}")
