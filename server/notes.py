"""What a person decided, and what they have already entered.

Two small records that belong to the return and to nobody's extraction.

**Decisions.** Every schedule raises things only a person can settle: a
question the documents do not answer, a credit of unknown nature set aside, a
difference from the department's record that nothing accounts for. Settling one
is a judgement, and a judgement with no reason attached is worth nothing in
three years' time -- so each is stored with the reason, and nothing is ever
removed. Reopening a decision adds an entry; it does not delete the earlier
one. The log is the audit trail, and the current state is read off the end of
it.

An item is identified by what it says, not by where it sat in a list, because
a re-run reorders lists. If a re-run words a question differently it comes back
as open, which is the safe direction to fail in: the earlier decision stays in
the record, marked as about something no longer raised.

**Entered.** The rows of each schedule that have been typed into the utility,
with what each row said at the time, so a figure that changes afterwards can
be pointed at instead of quietly diverging from what was filed.

Neither is ever written by an extraction, for the same reason overrides are
not: a run must not be able to discard a judgement already made.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from . import paths

LOCK = threading.Lock()

CHOICES = {
    "no_change": "Settled, no change to the return",
    "left_out": "Correctly left out",
    "elsewhere": "Already on another schedule",
    "accepted": "Difference accepted",
    "will_correct": "To be corrected in the figures",
    "department": "The department's record is wrong",
    "not_relevant": "Not relevant to this return",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def decisions_path(ay: str):
    return paths.data_root(ay) / "review" / "decisions.json"


def entered_path(ay: str):
    return paths.data_root(ay) / "review" / "entered.json"


# ---------------------------------------------------------------- decisions
def load_decisions(ay: str) -> dict:
    """{'current': {id: entry}, 'log': [entry, ...]}, newest last."""
    doc = paths.read_json(decisions_path(ay), {"ay": ay, "log": []})
    log = doc.get("log") or []
    current: dict[str, dict] = {}
    for entry in log:
        if entry.get("action") == "reopen":
            current.pop(entry.get("id"), None)
        else:
            current[entry["id"]] = entry
    return {"current": current, "log": log}


def settle(ay: str, item: dict, choice: str, reason: str) -> dict:
    if choice not in CHOICES:
        raise ValueError(f"unknown choice {choice!r}")
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("a decision needs its reason: it is the audit trail")
    if not item.get("id"):
        raise ValueError("no item to settle")
    entry = {
        "action": "settle",
        "id": str(item["id"]),
        "tab": item.get("tab") or "",
        "kind": item.get("kind") or "",
        # The words are kept with the decision. Once a re-run rephrases the
        # item, this is the only record of what was actually decided.
        "text": str(item.get("text") or "")[:2000],
        "amount": item.get("amount"),
        "choice": choice,
        "choice_label": CHOICES[choice],
        "reason": reason,
        "at": _now(),
    }
    _append(ay, entry)
    return entry


def reopen(ay: str, item_id: str, reason: str = "") -> dict:
    entry = {"action": "reopen", "id": str(item_id), "reason": (reason or "").strip(),
             "at": _now()}
    _append(ay, entry)
    return entry


def _append(ay: str, entry: dict) -> None:
    with LOCK:
        path = decisions_path(ay)
        doc = paths.read_json(path, {"ay": ay, "log": []})
        doc.setdefault("log", []).append(entry)
        paths.write_json(path, doc)


# ------------------------------------------------------------------ entered
def load_entered(ay: str) -> dict:
    return (paths.read_json(entered_path(ay), {"ay": ay, "entered": {}}) or {}).get("entered") or {}


def mark_entered(ay: str, rows: list[dict], entered: bool = True) -> dict:
    """Mark or unmark rows. Each is {'key': 'sheet|row', 'stamp': 'what it said'}."""
    with LOCK:
        path = entered_path(ay)
        doc = paths.read_json(path, {"ay": ay, "entered": {}})
        marks = doc.setdefault("entered", {})
        for row in rows or []:
            key = str(row.get("key") or "")
            if not key:
                continue
            if entered:
                marks[key] = {"stamp": str(row.get("stamp") or ""), "at": _now()}
            else:
                marks.pop(key, None)
        paths.write_json(path, doc)
        return marks
