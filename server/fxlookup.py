"""Finding the exchange rates a return needs, at runtime, with the engine.

The rate is published data, so the engine finds it -- guided by a prompt and
the sbi-tt-rates skill, the same way it reads documents -- and applies the
rule for which date and which card. What code does is the plumbing and the
check:

  * it downloads the archive the skill names (its `archive_url`), because the
    engine's own web tool truncates a file that long and cannot read the
    compressed daily PDFs. The engine then reads the archive locally, with no
    internet access at all and none of the taxpayer's documents -- only the
    archive and a list of currencies and dates;
  * it checks every answer: the engine must quote the exact archive row, and
    code confirms the row is there, says what the engine reported, and that no
    nearer earlier date was skipped.

Changing where rates come from is an edit to the skill, not to this file.
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
import urllib.request
import pathlib
from datetime import date, datetime, timezone

from . import engines, paths
from engine import fx

MAX_DAYS_BACK = 7
SKILL = "sbi-tt-rates"


def archive_dir() -> pathlib.Path:
    """Looked up each time, not once at import: the home can move (see
    paths.move_legacy_home) after this module is loaded."""
    return paths.state_dir() / "fx_archive"


def _skill_text() -> str:
    path = paths.PROMPTS / "skills" / f"{SKILL}.md"
    return path.read_text("utf-8") if path.exists() else ""


def archive_url(currency: str) -> str:
    """The skill says where its archive is; code only fills in the currency."""
    m = re.search(r"^archive_url:\s*(\S+)", _skill_text(), re.M)
    if not m:
        raise ValueError(f"skill {SKILL} names no archive_url")
    return m.group(1).replace("{CUR}", currency.upper())


def allowed_hosts() -> tuple[str, ...]:
    """Only the host the skill names may be fetched from, by code."""
    return (urllib.parse.urlsplit(archive_url("USD")).hostname,)

SCHEMA = {
    "type": "object",
    "required": ["rates", "questions"],
    "properties": {
        "rates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["currency", "date_needed", "date_used", "rate",
                             "source_url", "source_row"],
                "properties": {
                    "currency": {"type": "string"},
                    "date_needed": {"type": "string"},
                    "date_used": {"type": "string"},
                    "rate": {"type": "number"},
                    "source_url": {"type": "string"},
                    "source_row": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
        },
        "questions": {"type": "array", "items": {"type": "string"}},
    },
}


def build_prompt(needs: list[dict], archives: dict[str, pathlib.Path]) -> str:
    wanted = "\n".join(f"  - {n['currency']} on {n['date']}" for n in needs)
    files = "\n".join(f"  - {cur}: `{path}` (archive_url {archive_url(cur)})"
                      for cur, path in sorted(archives.items()))
    rules = (paths.PROMPTS / "_fx_rates.md").read_text("utf-8")
    return f"""{rules}

{_skill_text()}

## Rates needed

{wanted}

## Archive files

{files}

## Required output

Reply with a single JSON document and nothing else, in a ```json fenced block,
validating against:

```json
{json.dumps(SCHEMA, indent=2)}
```
"""


# ---------------------------------------------------------------- the check

_fetched: dict[str, str] = {}


def _fetch(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in allowed_hosts():
        raise ValueError(f"not an allowed rate source: {url}")
    if url not in _fetched:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - host checked above
            _fetched[url] = resp.read().decode("utf-8", "replace")
    return _fetched[url]


def verify(entry: dict) -> tuple[bool, str]:
    """Is the reported rate really in the quoted row of the quoted source?"""
    try:
        needed = date.fromisoformat(entry["date_needed"])
        used = date.fromisoformat(entry["date_used"])
    except (KeyError, ValueError):
        return False, "dates are not in YYYY-MM-DD form"
    if used > needed:
        return False, f"used {used}, which is after the date needed ({needed})"
    if (needed - used).days > MAX_DAYS_BACK:
        return False, f"used {used}, more than {MAX_DAYS_BACK} days before {needed}"

    try:
        text = _fetch(entry["source_url"])
    except Exception as exc:  # noqa: BLE001
        return False, f"could not fetch the source to check it: {exc}"

    row = entry["source_row"].strip()
    lines = [ln.strip() for ln in text.splitlines()]
    if row not in lines:
        return False, "the quoted row is not in the source"

    header = next(csv.reader(io.StringIO(lines[0])))
    values = next(csv.reader(io.StringIO(row)))
    record = dict(zip(header, values))
    if not record.get("DATE", "").startswith(used.isoformat()):
        return False, f"the quoted row is dated {record.get('DATE')}, not {used}"
    try:
        printed = float(record["TT BUY"])
    except (KeyError, ValueError):
        return False, "the quoted row has no TT BUY value"
    if printed <= 0:
        return False, "the source shows no TT BUY rate for that date"
    if abs(printed - float(entry["rate"])) > 1e-9:
        return False, f"the source row says {printed}, not {entry['rate']}"

    # Nothing earlier in the gap may have been skipped: the rule wants the
    # nearest earlier date, so a published rate between the two is a mistake.
    for ln in lines[1:]:
        cells = ln.split(",", 1)
        try:
            d = date.fromisoformat(cells[0][:10])
        except ValueError:
            continue
        if used < d <= needed:
            return False, f"the source has a rate for {d}, nearer to {needed} than {used}"
    return True, "checked against the source"


# --------------------------------------------------------------------- run

def run(needs: list[dict], engine_name: str, on_event, cancel=None) -> dict:
    """Look up every needed rate, keep the ones that check out."""
    if not needs:
        return {"saved": [], "rejected": [], "questions": []}

    engine = engines.get(engine_name)

    # Download each archive the skill names; the engine reads the local copy.
    _fetched.clear()
    archive = archive_dir()
    archive.mkdir(parents=True, exist_ok=True)
    archives: dict[str, pathlib.Path] = {}
    for cur in sorted({n["currency"].upper() for n in needs}):
        url = archive_url(cur)
        on_event({"phase": "fetch", "detail": url})
        target = archive / f"{cur}.csv"
        target.write_text(_fetch(url), encoding="utf-8")
        archives[cur] = target

    on_event({"phase": "ask", "detail": "looking up " + ", ".join(
        f"{n['currency']} {n['date']}" for n in needs)})
    reply = engine.run(
        engines.Request(schedule="fx_rates", ay="", files=[], prompt=build_prompt(needs, archives),
                        cancel=cancel, time_limit=engines.time_limit_for(engine_name),
                        cwd=archive, add_dirs=[archive]),
        on_event,
    )
    name = engine_name

    from .runner import _extract_json
    from . import jsonschema_lite as jsl

    answer = _extract_json(reply.text)
    bad = jsl.validate(answer, SCHEMA)
    if bad:
        raise engines.EngineError("rate lookup returned an invalid answer: " + jsl.format_errors(bad)[:300])

    saved, rejected = [], []
    for entry in answer["rates"]:
        ok, why = verify(entry)
        if not ok:
            rejected.append({**entry, "why": why})
            on_event({"phase": "note", "detail": f"rejected {entry.get('currency')} {entry.get('date_used')}: {why}"})
            continue
        fx.save_rate(entry["currency"], entry["date_used"], entry["rate"], source={
            "url": entry["source_url"], "row": entry["source_row"], "note": entry.get("note", ""),
            "looked_up_by": name, "for_date": entry["date_needed"],
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        saved.append(entry)
        on_event({"phase": "rate", "detail": f"{entry['currency']} {entry['date_used']} = {entry['rate']} (verified)"})
    return {"saved": saved, "rejected": rejected, "questions": answer.get("questions", [])}
