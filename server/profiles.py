"""Profiles: named working sets, defined entirely by you.

A profile is whatever combination you want to work on -- a person, a financial
year, a regime, a document folder -- and the application always operates on
exactly one of them. Selecting one decides which documents are read, where
results are written, and which declarations apply.

Three rules shape this:

  * **Outside the program.** The profile list and every profile's folders live
    in the Flow home (see paths.py), never in the repository: they hold a PAN,
    a date of birth and a year of someone's finances. By convention a profile
    called X keeps its documents in `<home>/X/documents` and everything
    produced from them in `<home>/X/results`. Documents may be pointed
    elsewhere; results always follow the return name.

  * **Flat, never nested.** An earlier version nested one profile inside
    another's folder, which meant one person's documents could be read into
    another's return.

  * **Several profiles may share one `source_dir`.** That is the useful case:
    the same documents computed under the old regime and the new, side by side,
    each keeping its own results.

  * **No two profiles may share a `data_dir`.** Sharing documents is a feature;
    sharing output is a silent overwrite of one return by another, so it is
    refused.

Names, years, document folders and settings are all yours to choose. The
results folder follows the return name so each return's output stays together.
"""

from __future__ import annotations

import errno
import os
import re
import shutil
from datetime import datetime, timezone

from . import paths

def store_path():
    """The profile list. In the home, so it is found whichever clone is run."""
    return paths.home() / "profiles.json"


# The tool prepares returns for residents and ordinarily residents only. Rules
# that differ for non-residents or RNOR are not implemented or offered, so there
# is nothing to choose here: every computation assumes ROR.
RESIDENTIAL_STATUS = "ror"

FIELDS = {
    "regime": {
        "label": "Regime",
        "default": "compare",
        "options": [
            {"value": "compare", "label": "Compare both",
             "note": "Compute both and recommend the lower. The safe default."},
            {"value": "new", "label": "New - 115BAC(1A)",
             "note": "The statutory default since AY 2024-25."},
            {"value": "old", "label": "Old",
             "note": "Requires opting out; Form 10-IEA is needed when you have business income."},
        ],
    },
    "age_band": {
        "label": "Age",
        "default": "below_60",
        "options": [
            {"value": "below_60", "label": "Below 60", "note": "80TTA applies; basic exemption Rs 2.5L (old regime)."},
            {"value": "senior", "label": "60 to 79", "note": "80TTB replaces 80TTA; basic exemption Rs 3L (old regime)."},
            {"value": "super_senior", "label": "80 and above", "note": "Basic exemption Rs 5L (old regime)."},
        ],
    },
    "sex": {
        "label": "Sex",
        "default": "",
        "options": [
            {"value": "male", "label": "Male",
             "note": "Part A-GEN records it. The slabs have been the same for every sex since "
                     "AY 2013-14, so it changes no figure in the computation."},
            {"value": "female", "label": "Female",
             "note": "Part A-GEN records it. The slabs have been the same for every sex since "
                     "AY 2013-14, so it changes no figure in the computation."},
            {"value": "transgender", "label": "Transgender",
             "note": "Part A-GEN offers this option; it changes no figure in the computation."},
        ],
    },
    "dob": {
        "label": "Date of birth",
        "default": "",
        "kind": "date",
        "note": "Needed to open the AIS and TIS: the portal encrypts them with the "
                "PAN in lower case followed by the date of birth as ddmmyyyy.",
        "options": [],
    },
    "audit_44ab": {
        "label": "Tax audit",
        "default": "no",
        "options": [
            {"value": "no", "label": "Not applicable", "note": "Turnover below the section 44AB thresholds."},
            {"value": "yes", "label": "Required u/s 44AB", "note": "Form 3CA/3CB-3CD must be filed before the return."},
        ],
    },
    "engine": {
        "label": "Reading engine",
        "default": "",
        "kind": "engine",
        "note": "Which command-line assistant reads this return's documents. The choices are "
                "the engines the program knows; one that is not installed is marked.",
        # Filled in from the engine registry when the page asks: see describe_fields().
        "options": [],
    },
    "excel_export": {
        "label": "Export results to Excel",
        "default": "manual",
        "options": [
            {"value": "manual", "label": "Only when asked",
             "note": "results.xlsx is written when you press Export to Excel on the "
                     "Hand-off page."},
            {"value": "auto", "label": "After every computation",
             "note": "Keeps results.xlsx in step with the figures."},
        ],
    },
}

FY_RE = re.compile(r"^\d{4}-\d{2}$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
# Either order, since a browser date input gives yyyy-mm-dd and a person
# writing it by hand almost always gives dd-mm-yyyy.
DATE_RE = re.compile(r"^(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})$")

DEFAULT_NAME = "DEFAULT"
DEFAULT_FY = "2025-26"

INPUT_README = """Put every document for this return in this folder.

Form 16, salary slips, broker and bank statements, the AIS, the TIS, Form 26AS,
loan and insurance certificates, invoices for a business: whatever you were
given for the year. Sub-folders are fine and nothing needs sorting by hand.
Then open Flow ITR, go to Documents and press "Sort documents again".

A date or period in a file name helps: HDFC_savings_2025-04_to_2026-03.pdf.
This file is ignored; it is not read as a document.
"""


def defaults() -> dict:
    return {k: v["default"] for k, v in FIELDS.items()}


def ay_for(fy: str) -> str:
    """FY 2025-26 is filed as AY 2026-27. Rate tables are keyed by AY."""
    start = int(fy[:4]) + 1
    return f"{start}-{str(start + 1)[-2:]}"


def fy_for(ay: str) -> str:
    start = int(ay[:4]) - 1
    return f"{start}-{str(start + 1)[-2:]}"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "profile"


def default_dirs(name: str, fy: str = "") -> tuple[str, str]:
    """The conventional documents and results folders for a return."""
    return paths.default_dirs(name)


def ensure_folders(profile: dict) -> None:
    """Make a profile's two folders, so there is somewhere to put documents.

    Never fails a request: a folder that cannot be made (a drive that is not
    plugged in, a cloud folder not yet synced) is reported when it is used.
    """
    for key in ("source_dir", "data_dir"):
        try:
            paths.resolve_dir(profile[key]).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    try:
        readme = paths.resolve_dir(profile["source_dir"]) / "README.md"
        if not readme.exists() and not any(paths.resolve_dir(profile["source_dir"]).iterdir()):
            readme.write_text(INPUT_README, "utf-8")
    except OSError:
        pass


def describe(profile: dict) -> dict:
    """A profile with its folders resolved for this machine, for the page."""
    out = dict(profile)
    for key, label in (("source_dir", "source_path"), ("data_dir", "data_path")):
        resolved = paths.resolve_dir(profile.get(key, ""))
        out[label] = str(resolved)
        out[label + "_exists"] = resolved.is_dir()
    if profile.get("name"):
        # What the name says the folders are, and whether they are: a rename
        # moves what is in the conventional ones along with the name.
        src, data = default_dirs(profile["name"])
        folder = paths.resolve_dir(paths.folder_name(profile["name"]))
        out["folder_path"] = str(folder)
        out["folder_path_exists"] = folder.is_dir()
        out["conventional_source_path"] = str(paths.resolve_dir(src))
        out["conventional_data_path"] = str(paths.resolve_dir(data))
        out["source_conventional"] = _same(profile.get("source_dir", "")) == _same(src)
        out["data_conventional"] = _same(profile.get("data_dir", "")) == _same(data)
    return out


def _has_files(folder) -> bool:
    try:
        return folder.is_dir() and any(folder.iterdir())
    except OSError:
        return False


# --------------------------------------------------------------------------
# store
# --------------------------------------------------------------------------
def load_all() -> dict:
    store = paths.read_json(store_path(), None)
    if not store or not store.get("profiles"):
        store = _bootstrap()
    if store.get("active") not in {p["id"] for p in store["profiles"]}:
        store["active"] = store["profiles"][0]["id"] if store["profiles"] else None
    return store


def _bootstrap() -> dict:
    """First run: one profile called DEFAULT, and nothing else assumed."""
    store = {"active": None, "profiles": []}
    profile = _new(DEFAULT_NAME, DEFAULT_FY)
    store["profiles"].append(profile)
    store["active"] = profile["id"]
    paths.write_json(store_path(), store)
    ensure_folders(profile)
    return store


def save_all(store: dict) -> dict:
    paths.write_json(store_path(), store)
    return store


def get(profile_id: str) -> dict | None:
    return next((p for p in load_all()["profiles"] if p["id"] == profile_id), None)


def active() -> dict | None:
    store = load_all()
    return next((p for p in store["profiles"] if p["id"] == store["active"]), None)


def set_active(profile_id: str) -> dict:
    store = load_all()
    if not any(p["id"] == profile_id for p in store["profiles"]):
        raise ValueError(f"no return {profile_id!r}")
    store["active"] = profile_id
    return save_all(store)


def settings_for(_ay: str | None = None) -> dict:
    """Settings of the active profile. The year is not a lookup key: several
    profiles may share one, so only the active profile can answer this."""
    return {**defaults(), **(active() or {}).get("settings", {})}


def active_ay() -> str:
    a = active()
    return a["ay"] if a else ay_for(DEFAULT_FY)


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------
def _validate(name: str, fy: str, pan: str):
    if not (name or "").strip():
        raise ValueError("a return needs a name")
    if not FY_RE.match(fy or ""):
        raise ValueError(f"financial year must look like 2025-26, got {fy!r}")
    if pan and not PAN_RE.match(pan.upper()):
        raise ValueError(f"{pan!r} is not a valid PAN (AAAAA9999A)")


def _check_data_dir(data_dir: str, store: dict, profile_id: str | None):
    """Sharing documents is deliberate; sharing output would be one profile
    silently overwriting another's return."""
    # Compared where they resolve to, so a relative and an absolute spelling
    # of one folder are still seen as the same folder.
    wanted = _same(data_dir)
    clash = next((p for p in store["profiles"]
                  if p["id"] != profile_id and _same(p["data_dir"]) == wanted), None)
    if clash:
        raise ValueError(
            f"data folder {data_dir!r} is already used by the return {clash['name']!r}. "
            "Returns may share documents but must each keep their own results."
        )


def _same(folder: str) -> str:
    """A folder's identity: where it resolves to, case-folded for Windows."""
    try:
        return str(paths.resolve_dir(folder).resolve()).lower()
    except OSError:
        return str(paths.resolve_dir(folder)).lower()


def _new(name: str, fy: str, pan: str = "", source_dir: str = "",
         settings: dict | None = None) -> dict:
    _validate(name, fy, pan)
    src, data = default_dirs(name, fy)
    return {
        "id": slug(name),
        "name": name.strip(),
        "fy": fy,
        "ay": ay_for(fy),
        "pan": (pan or "").upper(),
        "source_dir": paths.portable_dir(source_dir) or src,
        "data_dir": data,
        "settings": {**defaults(), **(settings or {})},
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def create(name: str, fy: str = "", pan: str = "", source_dir: str = "",
           settings: dict | None = None, activate: bool = True, **_) -> dict:
    store = load_all()
    profile = _new(name, fy, pan, source_dir, settings)
    if any(p["id"] == profile["id"] for p in store["profiles"]):
        raise ValueError(f"a return named {name!r} already exists")
    _check_data_dir(profile["data_dir"], store, None)

    store["profiles"].append(profile)
    if activate:
        store["active"] = profile["id"]
    save_all(store)
    ensure_folders(profile)
    return profile


def update(profile_id: str, patch: dict) -> dict:
    store = load_all()
    profile = next((p for p in store["profiles"] if p["id"] == profile_id), None)
    if not profile:
        raise ValueError(f"no return {profile_id!r}")

    name = patch.get("name", profile["name"])
    fy = patch.get("fy", profile["fy"])
    pan = patch.get("pan", profile["pan"])
    _validate(name, fy, pan)

    source_dir = ""
    if patch.get("source_dir"):
        wanted = paths.resolve_dir(patch["source_dir"].replace("\\", "/"))
        if not wanted.is_dir():
            raise ValueError(f"there is no folder at {wanted}. Check the path, or create the folder first.")
        source_dir = paths.portable_dir(patch["source_dir"].replace("\\", "/"))

    # The return's folder follows its name, so a rename is a move of that
    # folder and is refused unless the move was asked for: the page warns
    # first. Every refusal comes before anything on disk is touched.
    if _same(default_dirs(name)[1]) != _same(default_dirs(profile["name"])[1]):
        if not patch.get("move_folder"):
            raise ValueError("renaming a return moves its folder to the new name; "
                             "confirm the move to rename it")
        _follow_name(store, profile, name, carry_documents=not source_dir)

    profile.update({
        "name": name.strip(),
        "fy": fy,
        "ay": ay_for(fy),
        "pan": (pan or "").upper(),
    })
    if source_dir:
        profile["source_dir"] = source_dir

    for key, value in (patch.get("settings") or {}).items():
        field = FIELDS.get(key)
        if not field:
            continue
        if field["options"]:
            if any(o["value"] == value for o in field["options"]):
                profile["settings"][key] = value
        elif field.get("kind") == "engine":
            # Blank means "whatever the program defaults to".
            if value in {o["value"] for o in engine_options()}:
                profile["settings"][key] = value
        elif field.get("kind") == "date":
            # Stored as written; an empty value simply means "not supplied".
            text = str(value or "").strip()
            if not text or DATE_RE.match(text):
                profile["settings"][key] = text
        else:
            profile["settings"][key] = str(value or "").strip()

    profile["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_all(store)
    return profile


def _follow_name(store: dict, profile: dict, name: str, carry_documents: bool = True) -> None:
    """Move a return's folder to where `name` puts it, and point every return
    that used what moved at the new place.

    The results always go. The documents go too when they are in the
    return's own folder; another return reading them is pointed there as
    well, so the old folder is not left behind. Documents kept elsewhere
    stay where they are. Refused, with nothing touched, if a folder that
    would be written to already holds something.
    """
    new_source, new_data = default_dirs(name)
    if _same(profile["data_dir"]) == _same(new_data):
        return
    _check_data_dir(new_data, store, profile["id"])

    moves = [("data_dir", profile["data_dir"], new_data)]
    source = profile["source_dir"]
    if (carry_documents
            and _same(source) == _same(default_dirs(profile["name"])[0])
            and _same(source) != _same(new_source)):
        moves.append(("source_dir", source, new_source))
    for _, _, target in moves:
        if _has_files(paths.resolve_dir(target)):
            raise ValueError(
                f"{paths.resolve_dir(target)} already has files in it. Move or rename that "
                "folder first, so nothing in it is mixed up with this return's.")

    readers = [p for p in store["profiles"] if _same(p["source_dir"]) == _same(source)]
    _move_folders(moves)
    profile["data_dir"] = new_data
    if len(moves) > 1:
        for reader in readers:
            reader["source_dir"] = new_source
    _make_results_folder(profile)


def _move_folders(moves: list[tuple[str, str, str]]) -> None:
    """All or nothing. Each folder moves in one rename where it can, so a file
    held open (results.xlsx in Excel, a PDF in a viewer) stops the change
    instead of splitting a folder in two; if a later move fails, the earlier
    ones are put back."""
    done = []
    try:
        for _, old, new in moves:
            _move_folder(paths.resolve_dir(old), paths.resolve_dir(new))
            done.append((old, new))
    except OSError as exc:
        for old, new in reversed(done):
            try:
                _move_folder(paths.resolve_dir(new), paths.resolve_dir(old))
            except OSError:
                pass
        raise ValueError(
            f"{exc.filename or 'a folder'} could not be moved ({exc.strerror or exc}). "
            "Close anything open from it and try again. Nothing was changed.") from exc
    for old, _ in done:
        _remove_if_empty(paths.resolve_dir(old).parent)


def _move_folder(old, new) -> None:
    if not old.exists():
        return
    if new.exists():
        new.rmdir()                     # only ever empty: checked before anything moved
    new.parent.mkdir(parents=True, exist_ok=True)
    _relocate(old, new)


def _relocate(src, dst) -> None:
    """Move a file or folder without ever leaving it half in each place.

    On one disk, a rename: it happens entirely or not at all, and a folder
    holding a file that is open (results.xlsx in Excel) is refused, which is
    the right answer. shutil.move instead falls back to copying when a rename
    is refused, and then fails to delete the original halfway through, leaving
    two partial folders. Only a move to another disk, where no rename is
    possible, copies: all of it first, and the original goes only once the copy
    is whole. If the original cannot all be removed, what is left is a spare;
    the copy is the one in use."""
    try:
        os.rename(src, dst)
        return
    except OSError as exc:
        if not (exc.errno == errno.EXDEV or getattr(exc, "winerror", None) == 17):
            raise
    if src.is_dir():
        shutil.copytree(src, dst)
        shutil.rmtree(src, ignore_errors=True)
    else:
        shutil.copy2(src, dst)
        try:
            src.unlink()
        except OSError:
            pass


def _make_results_folder(profile: dict) -> None:
    """So the new results folder is there to open straight away."""
    try:
        paths.resolve_dir(profile["data_dir"]).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _remove_if_empty(folder) -> None:
    """A return folder in the home emptied by a rename goes too; anything
    still in it, or any folder outside the home, is left alone."""
    try:
        home = paths.home().resolve()
        if folder.resolve() != home and folder.resolve().is_relative_to(home) \
                and not any(folder.iterdir()):
            folder.rmdir()
    except OSError:
        pass


def use_conventional_results(profile_id: str) -> dict:
    """Move a results folder kept elsewhere (as earlier versions allowed)
    into the return's own folder."""
    store = load_all()
    profile = next((p for p in store["profiles"] if p["id"] == profile_id), None)
    if not profile:
        raise ValueError(f"no return {profile_id!r}")
    previous = profile["data_dir"]
    if _same(previous) == _same(default_dirs(profile["name"])[1]):
        return {"moved": False, "reason": "already in the return's folder"}
    _follow_name(store, profile, profile["name"])
    profile["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_all(store)
    return {"moved": True, "from": previous, "to": profile["data_dir"]}


def delete(profile_id: str) -> dict:
    """Removes the profile only. Documents and extracted data stay on disk:
    losing a year of tax work to a mistyped name is not a thing this should do."""
    store = load_all()
    profile = next((p for p in store["profiles"] if p["id"] == profile_id), None)
    if not profile:
        raise ValueError(f"no return {profile_id!r}")
    if len(store["profiles"]) == 1:
        raise ValueError("this is the only return; create another before removing it")
    store["profiles"] = [p for p in store["profiles"] if p["id"] != profile_id]
    if store["active"] == profile_id:
        store["active"] = store["profiles"][0]["id"]
    save_all(store)
    return {"deleted": profile_id, "kept_on_disk": [profile["source_dir"], profile["data_dir"]]}


def move_dir(profile_id: str, field: str, target: str) -> dict:
    """Point a profile at a different folder, taking its contents along.

    Contents are moved, never copied and never deleted. If another profile
    shares this source folder, the move is refused -- it would silently
    relocate their documents too.
    """
    if field != "source_dir":
        raise ValueError("only the documents folder can be moved")
    store = load_all()
    profile = next((p for p in store["profiles"] if p["id"] == profile_id), None)
    if not profile:
        raise ValueError(f"no return {profile_id!r}")

    target = paths.portable_dir(target.strip().replace("\\", "/"))
    current = profile[field]
    if _same(current) == _same(target):
        return {"moved": False, "reason": "already there"}

    if field == "source_dir":
        sharers = [p["name"] for p in store["profiles"]
                   if p["id"] != profile_id and _same(p["source_dir"]) == _same(current)]
        if sharers:
            raise ValueError(
                f"{', '.join(sharers)} also use this document folder. "
                "Point them elsewhere first, or change this return's folder without moving files."
            )
    old, new = paths.resolve_dir(current), paths.resolve_dir(target)
    if old.exists():
        _move_contents(old, new, target)

    profile[field] = target
    profile["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_all(store)
    return {"moved": True, "field": field, "from": current, "to": target}


def _move_contents(old, new, target: str) -> None:
    if new.exists() and any(new.iterdir()):
        raise ValueError(f"{target} already exists and is not empty")
    if not old.exists():
        return
    new.parent.mkdir(parents=True, exist_ok=True)
    new.mkdir(exist_ok=True)
    for child in list(old.iterdir()):
        if child.resolve() == new.resolve():
            continue
        _relocate(child, new / child.name)


def engine_options() -> list[dict]:
    """What a return may read with: every engine's models, grouped by engine.
    Built from the engines themselves, so adding one touches no file here."""
    from . import engines
    from . import settings as user_settings

    listed = engines.describe()
    default = engines.canonical(user_settings.default_engine(), listed)
    return [{"value": "", "label": f"The default ({engines.label_of(default, listed)})",
             "note": "Whichever engine and model are set as the default on the Reading engines page."}] + [
        {"value": c["value"], "group": c["group"],
         "label": c["label"] + ("" if c["available"] else " (not found)"),
         "note": c["note"]}
        for c in engines.choices(listed)]


def engine_for(profile: dict | None = None) -> str:
    """What this return reads with, as "engine:model": its own choice, else
    the default, else the first engine and model that is installed."""
    from . import engines
    from . import settings as user_settings

    listed = engines.describe()
    ready = [c["value"] for c in engines.choices(listed) if c["available"]]
    known = {e["id"]: e for e in listed}

    def usable(ref: str) -> bool:
        base, _ = engines.split(ref)
        return bool(ref) and base in known and known[base]["available"] and \
            (engines.canonical(ref, listed) in ready or base in ("claude", "codex"))

    chosen = (((profile or active() or {}).get("settings") or {}).get("engine") or "")
    if usable(chosen):
        return engines.canonical(chosen, listed)
    default = user_settings.default_engine()
    if usable(default):
        return engines.canonical(default, listed)
    return ready[0] if ready else engines.canonical(default, listed)


def describe_fields() -> dict:
    return {k: {"label": v["label"],
                "options": engine_options() if v.get("kind") == "engine" else v["options"],
                "default": v["default"],
                "kind": v.get("kind", "choice"), "note": v.get("note", "")}
            for k, v in FIELDS.items()}
