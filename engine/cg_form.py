"""Schedule CG laid out as the ITR-3 form numbers it.

The ledger in capital_gains.py answers "what was sold and what is the gain".
This answers the different question the form asks: which numbered line does each
gain belong on, and what are its Sell Value, Buy Value, Expenses and Gain
columns. Those are not the same question -- one disposal contributes to exactly
one lettered item, and which item depends on asset class and term together.

Item numbers follow the ITR-3 Schedule CG structure. VERIFY THEM against the
released utility for the assessment year before filing: the numbering has moved
between years, and a correct amount on the wrong line is still a defective
return.
"""

from __future__ import annotations

from datetime import date

# Advance-tax periods, used for the quarterly break-up that drives section 234C.
# The last one is five days long, which is not a mistake -- the fourth period
# ends on 15 March and the year ends on 31 March.
QUARTERS = [
    ("q1", "1 Apr to 15 Jun", (4, 1), (6, 15)),
    ("q2", "16 Jun to 15 Sep", (6, 16), (9, 15)),
    ("q3", "16 Sep to 15 Dec", (9, 16), (12, 15)),
    ("q4", "16 Dec to 15 Mar", (12, 16), (3, 15)),
    ("q5", "16 Mar to 31 Mar", (3, 16), (3, 31)),
]

# Which Schedule CG line a disposal lands on, by asset class and term.
ITEMS = {
    ("immovable_property", "short"): "A1",
    ("equity_stt", "short"): "A3",
    ("equity_unlisted", "short"): "A6",
    ("debt_mf_specified", "short"): "A6",
    ("debt_mf_other", "short"): "A6",
    ("bonds_debentures", "short"): "A6",
    ("gold_jewellery", "short"): "A6",
    ("foreign_shares", "short"): "A6",
    ("other", "short"): "A6",
    ("immovable_property", "long"): "B1",
    ("bonds_debentures", "long"): "B2",
    ("equity_stt", "long"): "B4",
    ("equity_unlisted", "long"): "B9",
    ("debt_mf_other", "long"): "B9",
    ("gold_jewellery", "long"): "B9",
    ("foreign_shares", "long"): "B9",
    ("other", "long"): "B9",
}

# The non-resident lines (A4, A5, B5 to B7) stay so every item keeps its number
# as the utility prints it; this tool is for residents, so they are never used.
LABELS = {
    "A1": "From sale of land or building or both",
    "A2": "From slump sale",
    "A3": "From sale of equity share or unit of equity oriented Mutual Fund or unit of a "
          "business trust on which STT is paid under section 111A or 115AD(1)(ii) proviso",
    "A4": "For a non-resident, from sale of shares or debentures of an Indian company",
    "A5": "For a non-resident, from sale of securities by an FII under section 115AD",
    "A6": "From sale of assets other than at A1 or A2 or A3 or A4 or A5 above",
    "A7": "Amount deemed to be short term capital gains",
    "A8": "Amount included in A1 to A7 but not chargeable, or chargeable at a special rate under a DTAA",
    "A9": "Deduction under sections 54B, 54D, 54G, 54GA",
    "A10": "Total short term capital gain",
    "B1": "From sale of land or building or both",
    "B2": "From sale of bonds or debentures",
    "B3": "From sale of listed securities, units or zero coupon bonds",
    "B4": "From sale of equity share in a company or unit of equity oriented fund or unit of a "
          "business trust on which STT is paid under section 112A",
    "B5": "For a non-resident, from sale of shares or debentures of an Indian company",
    "B6": "For a non-resident, from sale of securities by an FII",
    "B7": "For a non-resident, from sale of assets under sections 115AB, 115AC, 115ACA",
    "B8": "From slump sale",
    "B9": "From sale of assets where B1 to B8 above are not applicable",
    "B10": "Amount deemed to be long term capital gains",
    "B11": "Amount included in B1 to B10 but not chargeable, or chargeable at a special rate under a DTAA",
    "B12": "Deduction under sections 54, 54B, 54EC, 54F, 54GB",
    "B13": "Total long term capital gain chargeable under the Act",
    "C1": "Sum of capital gain income",
}

SHORT_ITEMS = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10"]
LONG_ITEMS = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10", "B11", "B12", "B13"]


def _d(value):
    if not value:
        return None
    try:
        y, m, dd = (int(p) for p in str(value)[:10].split("-"))
        return date(y, m, dd)
    except ValueError:
        return None


def quarter_of(transferred: date | None, fy_start_year: int) -> str | None:
    """Which advance-tax period a transfer falls in."""
    if not transferred:
        return None
    for key, _label, (sm, sd), (em, ed) in QUARTERS:
        start_year = fy_start_year if sm >= 4 else fy_start_year + 1
        end_year = fy_start_year if em >= 4 else fy_start_year + 1
        if date(start_year, sm, sd) <= transferred <= date(end_year, em, ed):
            return key
    return None


def _blank_row(code: str) -> dict:
    return {"item": code, "label": LABELS.get(code, code),
            "sell_value": 0, "buy_value": 0, "expenses": 0, "gain": 0, "rows": 0}


def build(cg: dict, ay: str, deductions: list | None = None) -> dict:
    """Schedule CG as the form lays it out, from the computed ledger."""
    fy_start_year = int(ay[:4]) - 1
    items = {code: _blank_row(code) for code in SHORT_ITEMS + LONG_ITEMS}

    # Quarterly break-up is for the taxable categories only, and never negative:
    # a loss in one period does not reduce another period's advance-tax liability.
    quarters = {key: {"stcg_111a": 0, "stcg_other": 0, "ltcg_112a": 0, "ltcg_other": 0}
                for key, *_ in QUARTERS}
    unassigned_quarter = 0

    for row in cg.get("rows", []):
        code = ITEMS.get((row["asset_class"], row["term"]))
        if not code:
            code = "A6" if row["term"] == "short" else "B9"
        target = items[code]
        target["sell_value"] += row["proceeds"]
        target["buy_value"] += row["cost"]
        target["expenses"] += row["expenses"]
        target["gain"] += row["gain"]
        target["rows"] += 1

        q = quarter_of(_d(row.get("transferred_on")), fy_start_year)
        if q is None:
            unassigned_quarter += max(0, row["gain"])
            continue
        if row["term"] == "short":
            key = "stcg_111a" if code == "A3" else "stcg_other"
        else:
            key = "ltcg_112a" if code == "B4" else "ltcg_other"
        quarters[q][key] += row["gain"]

    # Deductions claimed under 54-series reduce the long-term total at B12, and
    # the 54B/54D/54G/54GA subset reduces the short-term total at A9.
    short_sections = {"54B", "54D", "54G", "54GA"}
    for d in deductions or []:
        amount = (d.get("amount") or {}).get("amount", 0)
        code = "A9" if d.get("section") in short_sections else "B12"
        items[code]["gain"] += amount
        items[code]["rows"] += 1

    items["A10"]["sell_value"] = sum(items[c]["sell_value"] for c in SHORT_ITEMS[:7])
    items["A10"]["buy_value"] = sum(items[c]["buy_value"] for c in SHORT_ITEMS[:7])
    items["A10"]["expenses"] = sum(items[c]["expenses"] for c in SHORT_ITEMS[:7])
    items["A10"]["gain"] = (sum(items[c]["gain"] for c in SHORT_ITEMS[:7])
                            - items["A8"]["gain"] - items["A9"]["gain"])

    items["B13"]["sell_value"] = sum(items[c]["sell_value"] for c in LONG_ITEMS[:10])
    items["B13"]["buy_value"] = sum(items[c]["buy_value"] for c in LONG_ITEMS[:10])
    items["B13"]["expenses"] = sum(items[c]["expenses"] for c in LONG_ITEMS[:10])
    items["B13"]["gain"] = (sum(items[c]["gain"] for c in LONG_ITEMS[:10])
                            - items["B11"]["gain"] - items["B12"]["gain"])

    c1 = _blank_row("C1")
    for key in ("sell_value", "buy_value", "expenses", "gain"):
        c1[key] = items["A10"][key] + items["B13"][key]

    # The form does not accept a negative in the quarterly table.
    quarter_rows = []
    for key, label, *_ in QUARTERS:
        row = {"quarter": key, "label": label}
        for name, value in quarters[key].items():
            row[name] = max(0, value)
        quarter_rows.append(row)

    return {
        "short_term": [items[c] for c in SHORT_ITEMS],
        "long_term": [items[c] for c in LONG_ITEMS],
        "total": c1,
        "quarters": quarter_rows,
        "quarter_notes": (
            ["Negative period totals are shown as nil: a loss in one period does not "
             "reduce another period's advance-tax liability."]
            + ([f"Rs {unassigned_quarter:,} of gains could not be placed in a period "
                "because the transfer date is missing or outside the year."]
               if unassigned_quarter else [])
        ),
        "verify": ("Item numbers follow the ITR-3 Schedule CG structure and must be checked "
                   "against the released utility for this assessment year."),
    }
