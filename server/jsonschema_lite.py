"""A small JSON Schema validator.

Deliberately not a full draft-07 implementation. It supports exactly the
keywords used by schemas/ -- type, required, properties, additionalProperties,
items, enum, const, pattern, minimum, maximum, and local $ref -- and it reports
every error with a JSON Pointer, because those pointers are fed back to the
model as repair instructions.

Keeping this in-tree rather than depending on `jsonschema` means the project
runs on a bare Python install, which matters for something you will come back
to once a year.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


class ValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(f"{len(errors)} schema violation(s)")


def _type_ok(value, expected):
    names = [expected] if isinstance(expected, str) else expected
    for name in names:
        py = _TYPES.get(name)
        if py is None:
            continue
        # bool is a subclass of int in Python; tax data never wants that conflation.
        if name in ("integer", "number") and isinstance(value, bool):
            continue
        if name == "integer" and isinstance(value, float) and value.is_integer():
            return True
        if isinstance(value, py):
            return True
    return False


def _resolve(ref, root):
    if not ref.startswith("#/"):
        raise ValueError(f"only local refs are supported, got {ref!r}")
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def _validate(value, schema, root, pointer, errors):
    if "$ref" in schema:
        target = _resolve(schema["$ref"], root)
        merged = {k: v for k, v in schema.items() if k != "$ref"}
        merged.update(target)
        schema = merged

    if "anyOf" in schema:
        branches = []
        for branch in schema["anyOf"]:
            trial: list = []
            _validate(value, branch, root, pointer, trial)
            if not trial:
                break
            branches.append(trial)
        else:
            errors.append((pointer or "/", "matches none of the allowed forms: "
                           + " | ".join(m for trial in branches for _p, m in trial[:1])))
            return

    if "const" in schema and value != schema["const"]:
        errors.append((pointer, f"must be {schema['const']!r}, got {value!r}"))
        return

    if "enum" in schema and value not in schema["enum"]:
        errors.append((pointer, f"must be one of {schema['enum']}, got {value!r}"))
        return

    if "type" in schema and not _type_ok(value, schema["type"]):
        errors.append(
            (pointer, f"expected type {schema['type']}, got {type(value).__name__}")
        )
        return

    if isinstance(value, str):
        pattern = schema.get("pattern")
        if pattern and not re.search(pattern, value):
            errors.append((pointer, f"{value!r} does not match /{pattern}/"))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append((pointer, f"{value} is below minimum {schema['minimum']}"))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append((pointer, f"{value} is above maximum {schema['maximum']}"))

    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append((pointer or "/", f"missing required property {key!r}"))
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(
                        (f"{pointer}/{key}", "property is not allowed by the schema")
                    )
        for key, sub in props.items():
            if key in value:
                _validate(value[key], sub, root, f"{pointer}/{key}", errors)

    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _validate(item, schema["items"], root, f"{pointer}/{i}", errors)


def compose(schedule: str) -> dict:
    """Envelope + the schedule's data subschema, as one document.

    $defs lives on the envelope, so a data schema can say {"$ref": "#/$defs/money"}
    and have it resolve after composition.
    """
    envelope = json.loads((SCHEMA_DIR / "_envelope.schema.json").read_text("utf-8"))
    data_path = SCHEMA_DIR / f"{schedule}.data.schema.json"
    if not data_path.exists():
        raise FileNotFoundError(f"no data schema for schedule {schedule!r}")
    envelope["properties"]["data"] = json.loads(data_path.read_text("utf-8"))
    envelope["properties"]["schedule"] = {"const": schedule}
    return envelope


def validate(instance, schema) -> list:
    """Return a list of (pointer, message). Empty list means valid."""
    errors: list = []
    _validate(instance, schema, schema, "", errors)
    return errors


def format_errors(errors) -> str:
    return "\n".join(f"  {ptr or '/'}: {msg}" for ptr, msg in errors)
