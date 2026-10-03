"""The engine contract.

An engine is anything that can be handed a prompt plus a set of documents and
return a JSON document as text. Everything that makes the result trustworthy --
schema validation, the repair loop, provenance stamping, the three-layer merge --
lives in runner.py and applies identically whichever engine ran.

That split is the point. Engines differ in what they can do and how much you
can trust them to stay inside their folder; the checks must not.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path


class EngineError(RuntimeError):
    """The engine could not do the job at all.

    Distinct from a bad answer. A malformed JSON reply is worth retrying,
    because the model can be told what was wrong and try again. A missing
    binary, a rejected command line, or a file format the engine cannot read
    will fail identically every time, so the runner stops immediately rather
    than burning three attempts and a minute on the same error.
    """


class Stopped(EngineError):
    """The run was ended on purpose: by the person, or by its time limit.

    An EngineError, so a runner stops at once instead of retrying, but its own
    kind, so the page can say "stopped" rather than "failed"."""


# Minutes one request to an engine may take before it is ended. A laptop
# reading with a local model is slow by nature, so it gets longer. Each can be
# set in config/tabs.json under "time_limits_minutes".
DEFAULT_LIMITS = {"claude": 30, "codex": 30, "ollama": 120, "mock": 5}


def time_limit_for(engine_name: str) -> int:
    """Seconds, for an engine name such as "claude" or "ollama:gpt-oss:20b"."""
    base = (engine_name or "").split(":", 1)[0]
    try:
        from server import settings
        conf = settings.get("time_limits_minutes") or {}
    except Exception:  # noqa: BLE001
        conf = {}
    minutes = conf.get(base) or DEFAULT_LIMITS.get(base) or 30
    return int(float(minutes) * 60)


class Watch:
    """Ends an engine call that is stopped or runs past its limit.

    A thread waits beside the call; when the person stops the run or the time
    is up, it calls `kill` -- end the process, close the connection -- which
    makes the call's own blocking read return. The engine then calls
    `raise_if_ended()` to turn that into a Stopped error with the reason.
    Checked while the call runs, so a stream that hangs half way is ended too.
    """

    def __init__(self, req: "Request", kill, limit_seconds: int):
        self.reason: str | None = None
        self.limit = int(req.time_limit or limit_seconds)
        self._done = threading.Event()
        self._cancel = req.cancel
        self._kill = kill
        threading.Thread(target=self._wait, daemon=True).start()

    def _wait(self) -> None:
        deadline = time.monotonic() + self.limit
        while not self._done.wait(0.5):
            if self._cancel is not None and self._cancel.is_set():
                self.reason = "stopped"
            elif time.monotonic() > deadline:
                self.reason = "time"
            else:
                continue
            try:
                self._kill()
            except Exception:  # noqa: BLE001 -- already gone is fine
                pass
            return

    def finish(self) -> None:
        self._done.set()

    def raise_if_ended(self) -> None:
        if self.reason == "stopped":
            raise Stopped("Stopped by you before it finished. Nothing from this run was saved; "
                          "what was there before is unchanged.")
        if self.reason == "time":
            took = f"{self.limit // 60} minutes" if self.limit >= 60 else f"{self.limit} seconds"
            raise Stopped(f"Stopped after {took}, the time limit for this engine. "
                          f"Nothing from this run was saved. The limit can be raised in "
                          f"config/tabs.json under time_limits_minutes.")


@dataclass
class Request:
    """Everything an engine needs for one attempt."""

    schedule: str
    ay: str
    files: list[dict]
    prompt: str
    cwd: Path
    add_dirs: list[Path] = field(default_factory=list)
    attempt: int = 1
    session_id: str | None = None
    repair_prompt: str | None = None
    # Set by the server when the person presses Stop; and how long, in
    # seconds, this one request may take (None: the engine's own default).
    cancel: threading.Event | None = None
    time_limit: int | None = None

    @property
    def is_repair(self) -> bool:
        """A repair only means anything if there is a session to repair within."""
        return self.attempt > 1 and self.session_id is not None and self.repair_prompt is not None

    @property
    def text(self) -> str:
        return self.repair_prompt if self.is_repair else self.prompt


@dataclass
class Reply:
    text: str
    session_id: str | None = None
    model: str = "unknown"


def registry() -> dict:
    """Engine id -> module. Each module exposes available(), run(req, on_event)
    and the metadata below."""
    from . import claude_cli, codex_cli, mock, ollama_local

    return {"claude": claude_cli, "codex": codex_cli, "ollama": ollama_local, "mock": mock}


class _Bound:
    """An engine with its model chosen: "claude:sonnet", "ollama:qwen3:8b".
    The model is part of the name, so it is part of every run's fingerprint
    and of what each output records."""

    def __init__(self, module, model: str):
        self._module, self.model = module, model

    def __getattr__(self, name):
        return getattr(self._module, name)

    def run(self, req, on_event):
        return self._module.run(req, on_event, model=self.model)


def split(ref: str) -> tuple[str, str]:
    """"ollama:gpt-oss:20b" -> ("ollama", "gpt-oss:20b"); "claude" -> ("claude", "")."""
    engine, _, model = (ref or "").partition(":")
    return engine, model


def get(name: str):
    engines = registry()
    base, model = split(name)
    if base not in engines:
        raise EngineError(f"unknown engine {name!r}; available: {', '.join(engines)}")
    return _Bound(engines[base], model) if model else engines[base]


def describe() -> list[dict]:
    """Every engine, with the models it offers and honest capability notes.

    An engine is how Flow talks to a reader: a command-line tool, or Ollama's
    API on this computer. A model is the reader itself."""
    out = []
    for name, mod in registry().items():
        available = mod.available()
        models = mod.model_list() if hasattr(mod, "model_list") else []
        default = mod.default_model() if hasattr(mod, "default_model") and models else ""
        out.append({
            "id": name,
            "label": getattr(mod, "LABEL", name),
            "note": getattr(mod, "NOTE", ""),
            "selectable": getattr(mod, "SELECTABLE", True),
            "confines_reads": getattr(mod, "CONFINES_READS", False),
            "available": available,
            "default_model": default,
            "models": [{**m, "ref": f"{name}:{m['id']}"} for m in models],
        })
    return out


def choices(listed: list[dict] | None = None) -> list[dict]:
    """Every engine-and-model a return may read with, grouped by engine."""
    out = []
    for e in listed if listed is not None else describe():
        if not e["selectable"]:
            continue
        for m in e["models"]:
            out.append({"value": m["ref"], "engine": e["id"], "group": e["label"], "label": m["label"],
                        "note": m.get("note", ""), "available": e["available"]})
    return out


def canonical(ref: str, listed: list[dict] | None = None) -> str:
    """A bare engine name stands for that engine's default model."""
    base, model = split(ref)
    if model:
        return ref
    for e in listed if listed is not None else describe():
        if e["id"] == base and e.get("default_model"):
            return f"{base}:{e['default_model']}"
    return ref


def label_of(ref: str, listed: list[dict] | None = None) -> str:
    """"claude:opus" -> "Claude Code · Opus"."""
    listed = listed if listed is not None else describe()
    ref = canonical(ref, listed)
    base, model = split(ref)
    for e in listed:
        if e["id"] == base:
            m = next((m for m in e["models"] if m["id"] == model), None)
            return f"{e['label']} · {m['label'] if m else model}"
    return ref
