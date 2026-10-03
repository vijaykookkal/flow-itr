"""Engine settings: the program's defaults, and the person's own choices.

`config/tabs.json` ships with the program and holds the defaults. What a person
changes on the Reading engines page is theirs, not the program's, so it is kept
in `settings.json` in the Flow home and laid over the defaults. That way a
`git pull` never overwrites a choice, and a push never publishes one.

    default_engine          the engine a return uses when it names none
    time_limits_minutes     per engine: how long one request may take
    claude.model            opus, sonnet, haiku, or "" for Claude Code's own default
    codex.model             any Codex model name, or "" for Codex's own default
    ollama.host / num_ctx / think / model
"""

from __future__ import annotations

import copy
import re

from . import paths

CLAUDE_MODELS = [
    {"value": "opus", "label": "Opus", "note": "The most careful reader. Uses your plan's allowance fastest."},
    {"value": "sonnet", "label": "Sonnet", "note": "Faster and lighter on your allowance; very good on clean documents."},
    {"value": "haiku", "label": "Haiku", "note": "Fastest and lightest. Best kept for sorting documents."},
    {"value": "default", "label": "Claude Code's own default", "note": "Whatever model your Claude Code is set to."},
]
THINK_LEVELS = [
    {"value": "off", "label": "Off", "note": "Fastest. gpt-oss still reasons a little."},
    {"value": "low", "label": "Low", "note": "A short think before answering."},
    {"value": "medium", "label": "Medium", "note": "More careful, noticeably slower on a laptop."},
    {"value": "high", "label": "High", "note": "Most careful, slowest."},
]
WINDOWS = [16384, 32768, 65536, 131072]


def _path():
    return paths.home() / "settings.json"


def _defaults() -> dict:
    tabs = paths.load_tabs()
    ollama = {k: v for k, v in (tabs.get("ollama") or {}).items() if not k.startswith("_")}
    limits = {k: v for k, v in (tabs.get("time_limits_minutes") or {}).items() if not k.startswith("_")}
    return {
        "default_engine": tabs.get("default_engine", "claude"),
        "time_limits_minutes": {"claude": 30, "codex": 30, "ollama": 120, **limits},
        "claude": {"model": "opus"},
        "codex": {"model": ""},
        "ollama": {"host": "http://127.0.0.1:11434", "model": "", "num_ctx": 65536, "think": False, **ollama},
    }


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def own() -> dict:
    """Only what the person has changed."""
    return paths.read_json(_path(), {}) or {}


def load() -> dict:
    """The settings in force: defaults with the person's choices on top."""
    return _merge(_defaults(), own())


def get(*keys, default=None):
    node = load()
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def default_engine() -> str:
    return get("default_engine", default="claude") or "claude"


def _check(patch: dict) -> dict:
    """Refuse anything that is not a sensible value, with a reason."""
    clean: dict = {}
    if "default_engine" in patch:
        value = str(patch["default_engine"] or "")
        if not re.fullmatch(r"(claude|codex|ollama)(:[\w.:/-]+)?", value):
            raise ValueError(f"{value!r} is not an engine")
        clean["default_engine"] = value
    if "time_limits_minutes" in patch:
        clean["time_limits_minutes"] = {}
        for name, minutes in (patch["time_limits_minutes"] or {}).items():
            if name not in ("claude", "codex", "ollama"):
                continue
            try:
                minutes = int(minutes)
            except (TypeError, ValueError):
                raise ValueError(f"the time limit for {name} must be a whole number of minutes") from None
            if not 1 <= minutes <= 600:
                raise ValueError(f"the time limit for {name} must be between 1 and 600 minutes")
            clean["time_limits_minutes"][name] = minutes
    if "claude" in patch:
        model = str((patch["claude"] or {}).get("model", "opus"))
        if model not in {m["value"] for m in CLAUDE_MODELS} | {""}:
            raise ValueError(f"{model!r} is not one of the Claude models offered")
        clean["claude"] = {"model": model}
    if "codex" in patch:
        codex = patch["codex"] or {}
        clean["codex"] = {}
        if "model" in codex:
            model = str(codex.get("model") or "").strip()
            if model and not re.fullmatch(r"[\w.:-]{1,60}", model):
                raise ValueError(f"{model!r} does not look like a Codex model name")
            clean["codex"]["model"] = model
        if "models" in codex:
            # Model names the person has added for Codex to offer.
            names = [str(n).strip() for n in (codex.get("models") or []) if str(n).strip()]
            for n in names:
                if not re.fullmatch(r"[\w.:-]{1,60}", n):
                    raise ValueError(f"{n!r} does not look like a Codex model name")
            clean["codex"]["models"] = list(dict.fromkeys(names))
    if "ollama" in patch:
        o = patch["ollama"] or {}
        ollama: dict = {}
        if "host" in o:
            host = str(o["host"]).strip().rstrip("/")
            if not re.fullmatch(r"https?://[\w.-]+(:\d{2,5})?", host):
                raise ValueError(f"{host!r} is not an address such as http://127.0.0.1:11434")
            ollama["host"] = host
        if "num_ctx" in o:
            if int(o["num_ctx"]) not in WINDOWS:
                raise ValueError("the window must be one of " + ", ".join(f"{w:,}" for w in WINDOWS))
            ollama["num_ctx"] = int(o["num_ctx"])
        if "think" in o:
            level = o["think"]
            if level not in {t["value"] for t in THINK_LEVELS} | {False}:
                raise ValueError(f"{level!r} is not a reasoning level")
            ollama["think"] = False if level in ("off", False) else level
        if "model" in o:
            ollama["model"] = str(o["model"] or "").strip()
        if "models" in o:
            # Each model's own window and reasoning; a value left out follows
            # the shared one.
            ollama["models"] = {}
            for name, own in (o["models"] or {}).items():
                if not re.fullmatch(r"[\w.:/-]{1,120}", str(name)):
                    raise ValueError(f"{name!r} is not a model name")
                entry = {}
                if (own or {}).get("num_ctx") not in (None, ""):
                    if int(own["num_ctx"]) not in WINDOWS:
                        raise ValueError(f"the window for {name} must be one of "
                                         + ", ".join(f"{w:,}" for w in WINDOWS))
                    entry["num_ctx"] = int(own["num_ctx"])
                if (own or {}).get("think") not in (None, ""):
                    if own["think"] not in {t["value"] for t in THINK_LEVELS} | {False}:
                        raise ValueError(f"{own['think']!r} is not a reasoning level")
                    entry["think"] = False if own["think"] in ("off", False) else own["think"]
                ollama["models"][str(name)] = entry
        clean["ollama"] = ollama
    return clean


def save(patch: dict) -> dict:
    """Lay a change over the person's own settings and keep it."""
    merged = _merge(own(), _check(patch))
    paths.write_json(_path(), merged)
    return load()


def describe() -> dict:
    """What the Reading engines page needs: the settings in force, the
    defaults beside them, and the choices offered."""
    return {
        "current": load(),
        "defaults": _defaults(),
        "changed": own(),
        "stored_at": str(_path()),
        "choices": {"claude_models": CLAUDE_MODELS, "think": THINK_LEVELS, "windows": WINDOWS},
    }
