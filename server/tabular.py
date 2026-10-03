"""Reading spreadsheet rows against a plan the model produced.

The division of labour here is deliberate. Deciding that a column headed
"Exit Date" means `transferred_on`, and that the F&O sheet is business income
rather than capital gains, is judgement -- a model does it well. Transcribing
four and a half thousand trade rows is not judgement; it is clerical work that
a model does slowly, expensively and with silent omissions.

So the model produces a small plan, and this reads every row against it. The
count is exact, the values are the file's own, and a row that cannot be parsed
is reported rather than dropped.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

MONEY_RE = re.compile(r"^-?[\d,]+(\.\d+)?([eE]-?\d+)?$")
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def preview(path: Path, rows: int = 14) -> str:
    """The first rows of a CSV, for the model to read headers from."""
    out = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for i, row in enumerate(csv.reader(fh), 1):
            if i > rows:
                break
            # Wide enough to reach the charge columns: broker sheets put
            # brokerage, GST and STT after the dozen columns of the trade
            # itself, and a preview that stops short hides them from the plan.
            cells = [c[:28] for c in row[:24]]
            out.append(f"  {i:>3}: " + " | ".join(cells))
    return "\n".join(out)


def to_number(text: str) -> float | None:
    """A cell as a number, paise and all. None when it is not one."""
    text = (text or "").strip().replace("₹", "").replace(",", "")
    if not text or not MONEY_RE.match(text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_rupees(text: str) -> int | None:
    """Rupees as an integer. Broker sheets carry paise; ITR is rupee-rounded."""
    value = to_number(text)
    return None if value is None else int(round(value))


def to_date(text: str) -> str | None:
    """Broker exports carry ISO dates, sometimes with a time. Keep the date."""
    m = DATE_RE.match((text or "").strip())
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def field_kinds(row_schema: dict) -> tuple[set, set, set]:
    """Which fields are money, dates and numbers, read from the row schema.

    These were once hardcoded lists built around Schedule CG, which meant
    Schedule 112A's `sale_value` was stored as a string and its rows failed
    validation. The schedule's own schema is the only thing that knows.
    """
    props = (row_schema or {}).get("properties", {})
    money, dates, numbers = set(), set(), set()
    for name, sub in props.items():
        if sub.get("$ref") == "#/$defs/money" or "amount" in sub.get("properties", {}):
            money.add(name)
        elif "pattern" in sub and "[0-9]{4}" in sub["pattern"]:
            dates.add(name)
        elif sub.get("type") in ("number", "integer") or "number" in (sub.get("type") or []):
            numbers.add(name)
    return money, dates, numbers


def _names(column) -> list[str]:
    """The headers a field is mapped to: one, or several to be added together."""
    if isinstance(column, (list, tuple)):
        return [str(c) for c in column if c]
    return [column] if column else []


def read_table(path: Path, spec: dict, cite: str,
               row_schema: dict | None = None) -> tuple[list[dict], list[str], dict]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        raw = list(csv.reader(fh))

    header_idx = spec["header_row"] - 1
    if header_idx >= len(raw):
        return ([], [f"{path.name}: header row {spec['header_row']} is past the end of the file"],
                {"kept": 0, "skipped": 0})

    row_schema = row_schema or {}
    required = row_schema.get("required", [])
    MONEY_FIELDS, DATE_FIELDS, NUMBER_FIELDS = field_kinds(row_schema)
    allows = set((row_schema.get("properties") or {}).keys())

    headers = [h.strip() for h in raw[header_idx]]
    index = {h: i for i, h in enumerate(headers) if h}
    columns = spec.get("columns", {})

    missing = [c for column in columns.values() for c in _names(column) if c not in index]
    problems = [f"{path.name}: column {c!r} named in the plan is not in the header row"
                for c in missing]
    # Adding columns up is arithmetic on money. Asked of anything else it is a
    # mistake in the plan, and taking the first column would hide it.
    for field, column in columns.items():
        if isinstance(column, (list, tuple)) and field not in MONEY_FIELDS:
            problems.append(f"{path.name}: {field!r} is mapped to several columns, which only a "
                            f"money field can add up; the first was used")

    rows, skipped = [], 0
    missing_counts: list[str] = []
    for raw_row in raw[header_idx + 1:]:
        cells = [c.strip() for c in raw_row]
        if not any(cells):
            if spec.get("stop_at_blank"):
                break
            continue

        # Sub-tables in these exports sit directly against each other with no
        # blank line, so a boundary has to be recognised rather than declared:
        # a row carrying a single label is the next sub-table's heading, and a
        # row identical to the header is that sub-table's own header. Reading
        # past either one interprets different columns through this mapping.
        filled = [c for c in cells if c]
        if len(filled) == 1 and filled[0] not in headers:
            break
        if cells[: len(headers)] == headers:
            break

        def cell(name: str) -> str:
            i = index.get(name, -1)
            return cells[i] if 0 <= i < len(cells) else ""

        # Named `must_have` rather than `required`: the plan's column names and
        # the schema's field names are different vocabularies, and reusing one
        # variable for both silently checked rows against the wrong list.
        must_have = spec.get("require_columns") or []
        if must_have and not all(cell(c) for c in must_have):
            skipped += 1
            continue

        row: dict = {}
        for field, column in columns.items():
            names = _names(column)
            if not names:
                continue
            if field in MONEY_FIELDS and len(names) > 1:
                # One figure the table spreads over several columns -- selling
                # charges over brokerage, exchange charges and GST. The columns
                # are added to the paisa and rounded once: rounding each first
                # turns eight charges of a few paise into nothing, or into
                # eight rupees.
                parts = [(n, to_number(cell(n))) for n in names]
                stated = [(n, v) for n, v in parts if v is not None]
                if not stated:
                    continue
                total = sum(v for _n, v in stated)
                row[field] = {
                    "amount": abs(int(round(total))) if field != "stated_gain" else int(round(total)),
                    "cite": cite,
                    "basis": "columns added together: "
                             + " + ".join(f"{n} {v:g}" for n, v in stated)
                             + f" = {total:.2f}",
                }
                continue

            value = cell(names[0])
            if not value:
                continue
            if field in MONEY_FIELDS:
                amount = to_rupees(value)
                if amount is not None:
                    row[field] = {"amount": abs(amount) if field != "stated_gain" else amount,
                                  "cite": cite, "basis": f"column {names[0]!r}, stated as {value}"}
            elif field in DATE_FIELDS:
                parsed = to_date(value)
                if parsed:
                    row[field] = parsed
            elif field in NUMBER_FIELDS:
                try:
                    row[field] = float(value.replace(",", ""))
                except ValueError:
                    pass
            else:
                row[field] = value

        # Only schedules that actually have an asset class get one. Schedule
        # 112A does not, and injecting it made every row fail validation.
        if "asset_class" in allows:
            if spec.get("asset_class_column"):
                row["asset_class"] = cell(spec["asset_class_column"]) or spec.get("asset_class") or "other"
            else:
                row["asset_class"] = spec.get("asset_class") or "other"

        # Which fields a row must have comes from the schedule's own schema,
        # never from this module. Schedule CG rows need a transfer date;
        # Schedule 112A rows have no such field at all, and hardcoding one here
        # rejected every row of a perfectly good table.
        absent = [f for f in (required or []) if f not in row]
        if absent:
            missing_counts.append(absent[0])
            continue
        rows.append(row)

    if skipped:
        problems.append(f"{path.name}: {skipped} row(s) skipped for missing "
                        f"{', '.join(spec.get('require_columns') or [])}")
    if missing_counts:
        from collections import Counter
        for field, n in Counter(missing_counts).most_common():
            problems.append(f"{path.name}: {n} row(s) dropped because the schedule "
                            f"requires {field!r} and no mapped column supplied it")
    return rows, problems, {"kept": len(rows), "skipped": skipped,
                            "require_columns": spec.get("require_columns") or [],
                            "file": path.name}


def build(plan: dict, files: list[dict],
          row_schema: dict | None = None) -> tuple[list[dict], list[str], list[str], list[dict]]:
    """Apply the plan. Returns (rows, problems, notes, per-table stats)."""
    by_name = {Path(f["abs"]).name: f for f in files}
    rows, problems, stats = [], [], []

    for spec in plan.get("tables", []):
        entry = by_name.get(spec["file"])
        if not entry:
            problems.append(f"plan names {spec['file']!r}, which is not among this tab's documents")
            continue
        cite = entry.get("converted_from") or entry["path"]
        got, issues, stat = read_table(Path(entry["abs"]), spec, cite, row_schema)
        rows.extend(got)
        problems.extend(issues)
        stats.append(stat)

    # What was left out, and why, is reported by the caller from the plan's
    # explicit `kind` -- never inferred here from the wording of a reason.
    notes: list[str] = []
    return rows, problems, notes, stats


def plan_complaints(stats: list[dict]) -> list[tuple[str, str]]:
    """Plans that throw most of the file away are almost always wrong.

    The usual cause is `require_columns` naming an optional column -- a charge,
    a tax, a remark -- that only some rows carry. Silently keeping the handful
    of rows that happen to have it would understate the return, so this is fed
    back as a correctable error rather than accepted.
    """
    out = []
    for s in stats:
        total = s["kept"] + s["skipped"]
        if total and s["skipped"] > s["kept"]:
            out.append((
                f"/tables/{s['file']}",
                f"kept only {s['kept']} of {total} rows; {s['skipped']} were skipped because "
                f"require_columns {s['require_columns']} named a column those rows leave blank. "
                f"require_columns must list ONLY columns every genuine row carries -- an identity "
                f"column and a date. Never a money, charge or tax column."
            ))
    return out
