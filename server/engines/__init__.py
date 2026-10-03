"""The engine contract.

An engine is anything that can be handed a prompt plus a set of documents and
return a JSON document as text. Everything that makes the result trustworthy --
schema validation, the repair loop, provenance stamping, the three-layer merge --
lives in runner.py and applies identically whichever engine ran.

That split is the point. Engines differ in what they can do and how much you
can trust them to stay inside their folder; the checks must not.
"""

from __future__ import annotations

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
    from . import claude_cli, codex_cli, mock

    return {"codex": codex_cli, "claude": claude_cli, "mock": mock}


def get(name: str):
    engines = registry()
    if name not in engines:
        raise EngineError(f"unknown engine {name!r}; available: {', '.join(engines)}")
    return engines[name]


def describe() -> list[dict]:
    """What the UI needs to offer a choice, including honest capability notes."""
    out = []
    for name, mod in registry().items():
        out.append({
            "id": name,
            "label": getattr(mod, "LABEL", name),
            "note": getattr(mod, "NOTE", ""),
            "selectable": getattr(mod, "SELECTABLE", True),
            "confines_reads": getattr(mod, "CONFINES_READS", False),
            "available": mod.available(),
        })
    return out
