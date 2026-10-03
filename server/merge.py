"""extracted + overrides -> resolved.

The rule that matters: an AI run may only ever write `extracted/`. Your
corrections live in `overrides/` and are re-applied on top after every run, so
re-extracting can never silently discard a judgement you already made.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

from . import paths


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def pointer_get(doc, pointer: str):
    """RFC 6901 lookup. Returns the sentinel MISSING rather than raising, since
    an override that points at nothing is a reportable condition, not a crash."""
    if pointer in ("", "/"):
        return doc
    node = doc
    for token in pointer.lstrip("/").split("/"):
        token = _unescape(token)
        if isinstance(node, dict):
            if token not in node:
                return MISSING
            node = node[token]
        elif isinstance(node, list):
            try:
                node = node[int(token)]
            except (ValueError, IndexError):
                return MISSING
        else:
            return MISSING
    return node


class _Missing:
    def __repr__(self):
        return "MISSING"

    def __bool__(self):
        return False


MISSING = _Missing()


def pointer_set(doc, pointer: str, value) -> None:
    """Sets a value, creating intermediate dicts as needed. Appends to a list
    when the final token is '-'."""
    tokens = [_unescape(t) for t in pointer.lstrip("/").split("/")]
    node = doc
    for token in tokens[:-1]:
        if isinstance(node, list):
            node = node[int(token)]
        else:
            if token not in node or not isinstance(node[token], (dict, list)):
                node[token] = {}
            node = node[token]
    last = tokens[-1]
    if isinstance(node, list):
        if last == "-":
            node.append(value)
        else:
            node[int(last)] = value
    else:
        node[last] = value


def empty_envelope(ay: str, schedule: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "ay": ay,
        "schedule": schedule,
        "run_id": None,
        "generated_at": None,
        "input_fingerprint": None,
        "sources": [],
        "status": "needs_review",
        "unmapped": [],
        "questions": [],
        "data": {},
    }


def resolve(ay: str, schedule: str) -> dict:
    """Build resolved/<schedule>.json and write it."""
    extracted = paths.read_json(paths.extracted(ay, schedule))
    override_doc = paths.read_json(paths.overrides(ay, schedule), {"overrides": []})

    doc = copy.deepcopy(extracted) if extracted else empty_envelope(ay, schedule)
    applied = []

    for ov in override_doc.get("overrides", []):
        pointer = ov["pointer"]
        current = pointer_get(doc, pointer)
        if current is not MISSING and current == ov["value"]:
            # The extractor now agrees with you. Keep the record, flag it as
            # no longer doing any work, but never delete it -- the reason text
            # is the audit trail.
            state = "stale"
        elif current is MISSING:
            # The override addresses something this extraction does not contain.
            # That happens legitimately on declare-style fields, and illegitimately
            # when documents have been replaced and the pointer now means nothing.
            # Creating the path blindly would inject a figure into a document that
            # has no basis for it, so a path that cannot be built is reported as
            # orphaned and left unapplied rather than forced in.
            try:
                pointer_set(doc, pointer, ov["value"])
                state = "manual"
            except (IndexError, ValueError, KeyError, TypeError):
                state = "orphaned"
        else:
            state = "applied"
            pointer_set(doc, pointer, ov["value"])
        applied.append(
            {
                "pointer": pointer,
                "state": state,
                "value": ov["value"],
                "was": None if current is MISSING else current,
                "reason": ov.get("reason", ""),
                "at": ov.get("at"),
            }
        )

    doc["overrides_applied"] = applied
    doc["resolved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    paths.write_json(paths.resolved(ay, schedule), doc)
    return doc


def add_override(ay: str, schedule: str, pointer: str, value, reason: str, by: str = "user") -> dict:
    path = paths.overrides(ay, schedule)
    doc = paths.read_json(path, {"schedule": schedule, "ay": ay, "overrides": []})

    extracted = paths.read_json(paths.extracted(ay, schedule))
    was = pointer_get(extracted, pointer) if extracted else MISSING

    entry = {
        "pointer": pointer,
        "value": value,
        "was": None if was is MISSING else was,
        "reason": reason,
        "by": by,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    # One override per pointer; the newest wins and git keeps the history.
    doc["overrides"] = [o for o in doc["overrides"] if o["pointer"] != pointer]
    doc["overrides"].append(entry)
    doc["overrides"].sort(key=lambda o: o["pointer"])
    paths.write_json(path, doc)
    return entry
