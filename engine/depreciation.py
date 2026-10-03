"""Depreciation under section 32, computed rather than asked for.

An asset is not an expense. It is bought once and relieved over its life, and
the Act does that by blocks: every asset attracting the same rate is pooled,
the pool is written down each year, and what a particular asset is "worth" on
its own is never a figure the return carries.

So the only facts a document can give are what was bought, when it was put to
use, and what it cost. Everything after that is arithmetic, and arithmetic is
done here rather than asked of an engine reading an invoice:

  * the rate comes from the block the asset falls in (Appendix I to the
    Income-tax Rules);
  * an asset put to use for less than 180 days in the year it was acquired
    gets half the rate for that year, and the full rate thereafter (the second
    proviso to section 32(1));
  * the written-down value rolls forward year by year from the year of
    acquisition to the year being filed, so an asset bought in an earlier year
    arrives at this return with an opening WDV that was computed, not typed.

That last point is what makes a prior-year invoice usable at all. A monitor
bought in November 2024 cannot be an addition in the 2025-26 return, but it
can be -- and is -- an opening balance, and the only honest way to produce
that balance is to run the earlier year first.
"""

from __future__ import annotations

import datetime as dt
import re

# Appendix I rates, as fractions. Only the blocks a personal trading business
# is likely to hold; anything else is reported under its stated rate.
BLOCKS = {
    "computer": {"label": "Computers, including computer software", "rate": 0.40,
                 "schedule": "Schedule DPM"},
    "plant": {"label": "Plant and machinery, general rate", "rate": 0.15,
              "schedule": "Schedule DPM"},
    "furniture": {"label": "Furniture and fittings", "rate": 0.10,
                  "schedule": "Schedule DOA"},
    "building": {"label": "Buildings, other than residential", "rate": 0.10,
                 "schedule": "Schedule DOA"},
    "intangible": {"label": "Intangible assets", "rate": 0.25,
                   "schedule": "Schedule DOA"},
}

# What the description has to look like to fall in a block. A monitor, a
# keyboard or a docking station is part of the computer block: the block is
# defined by the rate the Rules give, not by whether the thing computes.
PATTERNS = [
    ("computer", r"comput|laptop|desktop|monitor|display|printer|scanner|server|"
                 r"router|modem|keyboard|mouse|docking|ups|hard disk|ssd|software|"
                 r"tablet|ipad|macbook|benq|dell|lenovo|hp "),
    ("furniture", r"chair|desk|table|cabinet|shelf|furnitur|fitting"),
    ("intangible", r"licence|license|patent|trademark|goodwill|copyright"),
    ("building", r"building|premises|office space"),
    ("plant", r"machine|equipment|plant|phone|mobile|handset|camera"),
]

HALF_YEAR_DAYS = 180


def block_for(description: str) -> str:
    text = (description or "").lower()
    for key, pattern in PATTERNS:
        if re.search(pattern, text):
            return key
    return "plant"


def fy_of(day: dt.date) -> str:
    """The previous year a date falls in: 2024-11-26 -> '2024-25'."""
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def fy_end(fy: str) -> dt.date:
    return dt.date(int(fy[:4]) + 1, 3, 31)


def fy_next(fy: str) -> str:
    start = int(fy[:4]) + 1
    return f"{start}-{str(start + 1)[-2:]}"


def previous_year_of(ay: str) -> str:
    """'2026-27' -> '2025-26'. The year whose income the return reports."""
    start = int(str(ay)[:4]) - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _date(value) -> dt.date | None:
    if not value:
        return None
    text = str(value).strip()
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text[:10], pattern).date()
        except ValueError:
            continue
    return None


def _amount(node) -> int:
    if isinstance(node, dict):
        return int(round(float(node.get("amount") or 0)))
    try:
        return int(round(float(node or 0)))
    except (TypeError, ValueError):
        return 0


def roll_forward(cost: int, put_to_use: dt.date, rate: float, upto_fy: str) -> list[dict]:
    """One asset, written down year by year up to and including `upto_fy`."""
    rows: list[dict] = []
    first = fy_of(put_to_use)
    if first > upto_fy:
        return rows

    wdv, fy = cost, first
    while fy <= upto_fy:
        days = (fy_end(fy) - put_to_use).days + 1 if fy == first else 366
        halved = fy == first and days < HALF_YEAR_DAYS
        applied = rate / 2 if halved else rate
        charge = int(round(wdv * applied))
        rows.append({
            "fy": fy, "opening": wdv, "addition": cost if fy == first else 0,
            "rate": applied, "full_rate": rate, "half_year": halved,
            "days_in_use": days if fy == first else None,
            "depreciation": charge, "closing": wdv - charge,
        })
        wdv -= charge
        fy = fy_next(fy)
    return rows


def _assets_from(doc, field: str) -> list[dict]:
    return ((doc or {}).get("data") or {}).get(field) or []


def build(dep_doc: dict | None, books_doc: dict | None, ay: str = "2026-27") -> dict:
    """Schedule DEP for this year, with the working that produced it.

    Assets come from the Depreciation tab's own documents and from the capital
    items the Books extraction found on invoices -- a laptop on a business
    expense invoice is an asset wherever the invoice happened to be filed.
    """
    year = previous_year_of(ay)
    raw = list(_assets_from(dep_doc, "assets")) + list(_assets_from(books_doc, "assets_acquired"))

    assets, ignored = [], []
    for item in raw:
        cost = _amount(item.get("cost") or item.get("amount"))
        day = _date(item.get("put_to_use_on") or item.get("invoice_date")
                    or item.get("acquired_on") or item.get("date"))
        description = item.get("description") or item.get("head") or "(unnamed asset)"
        if cost <= 0 or day is None:
            ignored.append({"description": description, "why":
                            "no cost" if cost <= 0 else "no date it was put to use"})
            continue
        key = item.get("block") if item.get("block") in BLOCKS else block_for(description)
        block = BLOCKS[key]
        rate = float(item.get("rate_percent") or 0) / 100 or block["rate"]
        rows = roll_forward(cost, day, rate, year)
        if not rows:
            ignored.append({"description": description, "why":
                            f"put to use in {fy_of(day)}, after the year being filed"})
            continue
        current = next((r for r in rows if r["fy"] == year), None)
        assets.append({
            "description": description, "block": key, "block_label": block["label"],
            "schedule": block["schedule"], "rate_percent": round(rate * 100, 2),
            "cost": cost, "put_to_use_on": day.isoformat(), "acquired_in": fy_of(day),
            "working": rows,
            "opening_wdv": current["opening"] if current else 0,
            "addition_this_year": current["addition"] if current else 0,
            "depreciation": current["depreciation"] if current else 0,
            "closing_wdv": current["closing"] if current else 0,
            "source": item.get("source") or (item.get("cost") or {}).get("cite"),
        })

    blocks: dict[str, dict] = {}
    for a in assets:
        b = blocks.setdefault(a["block"], {
            "block": a["block"], "description": a["block_label"],
            "schedule": a["schedule"], "rate_percent": a["rate_percent"],
            "opening_wdv": 0, "additions_180_days_or_more": 0,
            "additions_less_than_180_days": 0, "deductions": 0,
            "depreciation_allowable": 0, "closing_wdv": 0, "assets": [],
            "depreciation_full_rate": 0, "depreciation_half_rate": 0,
        })
        current = next((r for r in a["working"] if r["fy"] == year), None)
        if a["addition_this_year"]:
            key = ("additions_less_than_180_days" if current and current["half_year"]
                   else "additions_180_days_or_more")
            b[key] += a["addition_this_year"]
        else:
            b["opening_wdv"] += a["opening_wdv"]
        b["depreciation_allowable"] += a["depreciation"]
        half = bool(current and current["half_year"])
        b["depreciation_half_rate" if half else "depreciation_full_rate"] += a["depreciation"]
        b["closing_wdv"] += a["closing_wdv"]
        b["assets"].append(a)

    total = sum(b["depreciation_allowable"] for b in blocks.values())
    return {
        "previous_year": year,
        "blocks": sorted(blocks.values(), key=lambda b: -b["rate_percent"]),
        "assets": assets,
        "ignored": ignored,
        "total_depreciation": total,
        "verify": ("Rates are those in Appendix I to the Income-tax Rules. An asset put to "
                   "use for under 180 days in the year it was bought bears half the rate "
                   "that year, under the second proviso to section 32(1)."),
    }
