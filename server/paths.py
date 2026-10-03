"""Where things live: the code here, everything that is yours somewhere else.

A clone of this repository holds the program and nothing personal. Profiles,
documents, results, looked-up exchange rates, the conversion cache and this
machine's token all live in one folder outside it -- the *Flow home*:

    <home>/
      profiles.json                 who files what, and where their folders are
      fx_rates.json                 SBI TT rates looked up or typed in
      <profile>/input-docs/         the documents for that return
      <profile>/results/            what was read from them, your corrections and
                                    decisions, the computation, the Excel workbook
      .state/                       this machine's working files: token, log,
                                    conversions of documents into readable text

The home is, in order: the `FLOW_HOME` environment variable; the folder named
in `flow.local.json` beside this repository (ignored by git); otherwise a
folder called `flow` in the user's own home directory. That default exists on
every machine and needs no rights a normal account lacks, which is what lets
someone clone the repository and start.

A profile's two folders are stored relative to the home when they are inside
it, so the whole home can be moved, backed up or synced as one piece. They may
equally be absolute paths anywhere else -- a synced Google Drive folder, an
external disk -- because nothing below this module cares where a folder is.

Every path inside a profile is still keyed by assessment year where it matters:
carry-forward losses and depreciation block values make last year's output
this year's input.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CONFIG = ROOT / "config"
SCHEMAS = ROOT / "schemas"
PROMPTS = ROOT / "prompts"
WEB = ROOT / "web"

HOME_ENV = "FLOW_HOME"
# A clone can be pointed at a home without touching the environment. Ignored by
# git: it says something about this machine, not about the program.
HOME_POINTER = ROOT / "flow.local.json"
HOME_FOLDER = "flow"

INPUT_FOLDER = "input-docs"
OUTPUT_FOLDER = "results"

AY_RE = re.compile(r"^\d{4}-\d{2}$")


def check_ay(ay: str) -> str:
    if not AY_RE.match(ay or ""):
        raise ValueError(f"malformed assessment year: {ay!r}")
    return ay


# --------------------------------------------------------------------------
# the home
# --------------------------------------------------------------------------
def home() -> Path:
    """The folder that holds everything personal. Never inside the repository
    unless someone points it there on purpose."""
    explicit = os.environ.get(HOME_ENV)
    if explicit:
        return Path(explicit).expanduser()
    try:
        pointed = json.loads(HOME_POINTER.read_text("utf-8")).get("home")
    except (OSError, ValueError, AttributeError):
        pointed = None
    if pointed:
        return Path(pointed).expanduser()
    return Path.home() / HOME_FOLDER


def home_source() -> str:
    """Which of the three decided where the home is, for the page to say."""
    if os.environ.get(HOME_ENV):
        return f"the {HOME_ENV} environment variable"
    try:
        if json.loads(HOME_POINTER.read_text("utf-8")).get("home"):
            return f"{HOME_POINTER.name} beside the program"
    except (OSError, ValueError, AttributeError):
        pass
    return "the default: a folder called flow in your user folder"


def state_dir() -> Path:
    """This machine's working files: nothing here is part of a return, and
    all of it can be deleted and rebuilt."""
    return home() / ".state"


def cache_dir() -> Path:
    """Documents converted into text the engine can read, keyed by content."""
    return state_dir() / "cache"


def resolve_dir(text: str) -> Path:
    """A folder as a profile stores it -> where it is on this machine."""
    path = Path(str(text or "").strip()).expanduser()
    return path if path.is_absolute() else home() / path


def portable_dir(text: str) -> str:
    """How a folder is stored: relative to the home when it is inside it, so
    the home can move as one piece; absolute, with forward slashes, when not."""
    text = str(text or "").strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(home().resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def folder_name(name: str) -> str:
    """A profile's name as a folder name: itself, less what a file system refuses."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(name or "")).strip(" .")
    return re.sub(r"\s+", " ", cleaned) or "profile"


def default_dirs(name: str) -> tuple[str, str]:
    """The convention: <home>/<profile>/input-docs and .../results."""
    folder = folder_name(name)
    return f"{folder}/{INPUT_FOLDER}", f"{folder}/{OUTPUT_FOLDER}"


def cloud_roots() -> list[dict]:
    """Synced cloud folders found on this machine, for the page to offer.

    Google Drive for desktop makes a Drive an ordinary folder -- a drive letter
    with "My Drive" in it on Windows, a folder under ~/Library/CloudStorage on
    a Mac. Pointing a profile there needs nothing special: this program and
    the engine read it like any other folder, and Drive does the syncing.
    Nothing here talks to Google.
    """
    found: list[dict] = []
    seen: set[str] = set()

    def add(kind: str, path: Path) -> None:
        try:
            if path.is_dir() and str(path.resolve()).lower() not in seen:
                seen.add(str(path.resolve()).lower())
                found.append({"kind": kind, "path": path.as_posix()})
        except OSError:
            pass

    user = Path.home()
    if sys.platform.startswith("win"):
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            add("Google Drive", Path(f"{letter}:/My Drive"))
    for candidate in (user / "My Drive", user / "Google Drive" / "My Drive", user / "Google Drive",
                      Path("/Volumes/GoogleDrive/My Drive")):
        add("Google Drive", candidate)
    storage = user / "Library" / "CloudStorage"
    if storage.is_dir():
        for entry in sorted(storage.glob("GoogleDrive-*")):
            add("Google Drive", entry / "My Drive")
    return found


# --------------------------------------------------------------------------
# the active profile's folders
# --------------------------------------------------------------------------
def _profile_dir(key: str) -> Path | None:
    """The active profile's directory.

    Deliberately not keyed by year: several profiles may share a financial
    year, so only the active profile can say which folder is meant.

    Imported lazily -- profiles.py reads config through this module, and a
    top-level import would close the loop.
    """
    from . import profiles

    profile = profiles.active()
    if not profile or not profile.get(key):
        return None
    return resolve_dir(profile[key])


def source_root(ay: str) -> Path:
    """Where raw documents live.

    The active profile decides, so two people filing for the same year keep
    separate document trees. ITR_SOURCE_ROOT still wins, which is what keeps
    fixture runs isolated from real ones.
    """
    override = os.environ.get("ITR_SOURCE_ROOT")
    if override:
        return Path(override) / f"AY{check_ay(ay)}"
    check_ay(ay)
    return _profile_dir("source_dir") or resolve_dir(default_dirs("DEFAULT")[0])


def data_root(ay: str) -> Path:
    """Where extracted data is written.

    Reading from a different source root ALWAYS writes to a matching data root.
    Otherwise a fixture run quietly overwrites a schedule of the real return
    with invented figures -- the same contamination twice, from the other end.
    An explicit ITR_DATA_ROOT still wins, but forgetting it cannot hurt you.
    """
    explicit = os.environ.get("ITR_DATA_ROOT")
    if explicit:
        return Path(explicit) / f"AY{check_ay(ay)}"
    if os.environ.get("ITR_SOURCE_ROOT"):
        return Path(os.environ["ITR_SOURCE_ROOT"]) / "_data" / f"AY{check_ay(ay)}"
    check_ay(ay)
    return _profile_dir("data_dir") or resolve_dir(default_dirs("DEFAULT")[1])


def extracted(ay: str, schedule: str) -> Path:
    return data_root(ay) / "extracted" / f"{schedule}.json"


def overrides(ay: str, schedule: str) -> Path:
    return data_root(ay) / "overrides" / f"{schedule}.json"


def resolved(ay: str, schedule: str) -> Path:
    return data_root(ay) / "resolved" / f"{schedule}.json"


def run_manifest(ay: str, run_id: str) -> Path:
    return data_root(ay) / "_runs" / f"{run_id}.json"


def load_tabs() -> dict:
    return json.loads((CONFIG / "tabs.json").read_text("utf-8"))


def tab(tab_id: str) -> dict:
    for t in load_tabs()["tabs"]:
        if t["id"] == tab_id:
            return t
    raise KeyError(f"unknown tab {tab_id!r}")


def write_json(path: Path, payload) -> None:
    """Atomic-ish write: never leave a half-written schedule file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique per writer: two runs finishing together both rewrite the summary,
    # and a shared temp name lets one truncate the file the other is renaming.
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", "utf-8")
    tmp.replace(path)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text("utf-8"))
