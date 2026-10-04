"""Local models: what Ollama has, downloading more, removing them.

The page manages models through Ollama's own HTTP API on this machine, the
same one the reading engine uses, so nothing here needs a terminal. A download
runs in a thread of this server and its progress is kept in memory, so the
page can be closed and reopened while a large model arrives; it is lost only if
the server itself is restarted, and Ollama then resumes from where it was the
next time the same model is asked for.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request

from .engines import ollama_local

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*(:[a-z0-9._-]+)?$", re.I)

# Offered on the page. Sizes are the download, roughly; "fits" is a plain
# statement of the machine each suits, without a graphics card.
RECOMMENDED = [
    {"name": "gpt-oss:20b", "size": "about 13 GB",
     "note": "Recommended. Quick on a laptop processor, reliable at filling in the exact shape Flow ITR asks for, "
             "reads long documents. Suits 16 GB of memory, comfortable with 32 GB."},
    {"name": "qwen3:30b-a3b", "size": "about 19 GB",
     "note": "Very good with tables and figures, equally quick per word. Needs 32 GB of memory."},
    {"name": "qwen3:14b", "size": "about 9 GB",
     "note": "A capable middle size. Slower per word than the two above on a processor."},
    {"name": "qwen3:8b", "size": "about 5 GB",
     "note": "For 16 GB machines. Less accurate on messy statements."},
    {"name": "qwen3:4b", "size": "about 2.5 GB",
     "note": "The lightest worth trying. Good for sorting documents, weak at reading them."},
]

PULLS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _url(path: str) -> str:
    return ollama_local.settings()["host"] + path


def _call(method: str, path: str, body: dict | None = None, timeout: float = 5):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(_url(path), data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else {}


def status() -> dict:
    """What the page shows: whether Ollama answers, what is installed, what is arriving."""
    out = {"host": ollama_local.settings()["host"], "running": False, "version": None,
           "installed": [], "recommended": RECOMMENDED, "pulls": {}}
    try:
        out["version"] = _call("GET", "/api/version", timeout=1.5).get("version")
        out["running"] = True
        tags = _call("GET", "/api/tags", timeout=3).get("models", [])
        out["installed"] = [{
            "name": m.get("name"),
            "bytes": m.get("size", 0),
            "modified": m.get("modified_at"),
            "parameters": (m.get("details") or {}).get("parameter_size"),
            "family": (m.get("details") or {}).get("family"),
            "quantization": (m.get("details") or {}).get("quantization_level"),
            "embedding": "embed" in (m.get("name") or "").lower(),
        } for m in tags]
    except (OSError, ValueError):
        pass
    with _LOCK:
        out["pulls"] = {k: dict(v) for k, v in PULLS.items()}
    return out


def _pull(name: str) -> None:
    entry = PULLS[name]
    try:
        req = urllib.request.Request(_url("/api/pull"), method="POST",
                                     data=json.dumps({"model": name, "stream": True}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60 * 60 * 6) as resp:
            for raw in resp:
                if not raw.strip():
                    continue
                chunk = json.loads(raw.decode("utf-8"))
                with _LOCK:
                    if chunk.get("error"):
                        entry.update(error=chunk["error"], done=True)
                        return
                    entry["status"] = chunk.get("status", entry.get("status"))
                    if chunk.get("total"):
                        entry["total"] = chunk["total"]
                        entry["completed"] = chunk.get("completed", 0)
                    entry["at"] = time.time()
        with _LOCK:
            entry.update(done=True, status="ready")
    except urllib.error.HTTPError as exc:
        with _LOCK:
            entry.update(done=True, error=exc.read().decode("utf-8", "replace")[:300] or str(exc))
    except Exception as exc:  # noqa: BLE001 -- reported on the page, never raised into the server
        with _LOCK:
            entry.update(done=True, error=str(exc))
    finally:
        ollama_local._MODELS["at"] = 0.0        # the engine list sees the new model at once


def pull(name: str) -> dict:
    name = (name or "").strip()
    if not NAME_RE.match(name) or len(name) > 120:
        raise ValueError(f"{name!r} does not look like an Ollama model name, such as qwen3:8b")
    with _LOCK:
        current = PULLS.get(name)
        if current and not current.get("done"):
            return current
        PULLS[name] = {"status": "starting", "completed": 0, "total": 0, "done": False,
                       "error": None, "started": time.time()}
    threading.Thread(target=_pull, args=(name,), daemon=True).start()
    return PULLS[name]


def remove(name: str) -> None:
    if not NAME_RE.match(name or ""):
        raise ValueError("no such model")
    _call("DELETE", "/api/delete", {"model": name}, timeout=30)
    with _LOCK:
        PULLS.pop(name, None)
    ollama_local._MODELS["at"] = 0.0
