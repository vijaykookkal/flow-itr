"""Schedule 112A, from the capital gains ledger.

The return lists long-term sales of listed equity shares, equity-oriented fund
units and business trust units on which STT was paid on a schedule of their
own, and carries its total into Schedule CG. This builds that schedule in the
form's own columns, 1 to 14.

**Scrip by scrip only where it changes the answer.** For a share acquired on
or before 31 January 2018 the cost is replaced by the higher of the actual cost
and the lower of (fair market value on that day, sale value) -- section
55(2)(ac). That is worked out share by share, so each such lot gets its own row
with its ISIN, quantity and the 31 January 2018 price. For everything acquired
after that date nothing is worked out per scrip, and the form's instructions
let those sales be entered as one consolidated row: column 1a "After 31st
January 2018", ISIN `INNOTREQUIRD`, name `CONSOLIDATED`, and the totals. That
is what is produced here, with the lots it adds up kept beside it so the row
can be checked.

**Derived, not read.** Every figure is a row of the Capital Gains ledger,
already computed in capital_gains.py. The alternative -- reading the same
broker files a second time for this schedule -- gives two answers that round
differently, and these two must agree to the rupee because one is carried into
the other.

Column 8 is the cost of acquisition: the purchase value and the charges paid
on the purchase. Column 12 is the expenditure on the transfer. Securities
transaction tax is in neither. The exemption of the first Rs 1,25,000 of these
gains is applied where the tax is computed, not on this schedule.
"""

from __future__ import annotations

from datetime import date

from .capital_gains import _amt, _d

# "Acquired on or before 31st January 2018" is the form's own dividing line.
LAST_GRANDFATHERED_DAY = date(2018, 1, 31)

CONSOLIDATED_ISIN = "INNOTREQUIRD"
CONSOLIDATED_NAME = "CONSOLIDATED"

# The form's columns, as it numbers and words them. `key` is the field a row
# carries; `money` marks a rupee column. `label` is the heading in full, as the
# form prints it; `short` is the same heading without its conditions, for a
# table that has to fit fifteen columns on a screen.
COLUMNS = [
    {"no": "1", "key": "sl", "short": "Sl. No.", "label": "Sl. No."},
    {"no": "1a", "key": "acquired", "short": "Share/Unit acquired",
     "label": "Share/Unit acquired (on or before / after 31st Jan 2018)"},
    {"no": "2", "key": "isin", "short": "ISIN Code", "label": "ISIN Code"},
    {"no": "3", "key": "name", "short": "Name of the Share/Unit", "label": "Name of the Share/Unit"},
    {"no": "4", "key": "quantity", "short": "No. of Shares/ Units", "label": "No. of Shares/Units"},
    {"no": "5", "key": "sale_price_per_unit", "short": "Sale-price per Share/ Unit",
     "label": "Sale-price per Share/Unit"},
    {"no": "6", "key": "full_value", "money": True, "short": "Full value of consideration",
     "label": "Full value of consideration: if shares/units are acquired on or before 31st "
              "January 2018, Total Sale Value (4*5); if acquired after 31st January 2018, "
              "enter the full value of consideration"},
    {"no": "7", "key": "cost_without_indexation", "money": True,
     "short": "Cost of acquisition without indexation (higher of 8 or 9)",
     "label": "Cost of acquisition without indexation (higher of 8 or 9)"},
    {"no": "8", "key": "cost_of_acquisition", "money": True, "short": "Cost of acquisition",
     "label": "Cost of acquisition"},
    {"no": "9", "key": "lower_of_6_and_11", "money": True,
     "short": "If acquired before 01.02.2018, lower of 6 & 11",
     "label": "If the long term capital asset was acquired before 01.02.2018, lower of 6 & 11"},
    {"no": "10", "key": "fmv_per_unit", "short": "Fair Market Value per share/ unit on 31st January 2018",
     "label": "Fair Market Value per share/unit as on 31st January 2018"},
    {"no": "11", "key": "fmv_total", "money": True, "short": "Total Fair Market Value (4*10)",
     "label": "Total Fair Market Value of capital asset as per section 55(2)(ac) (4*10)"},
    {"no": "12", "key": "expenditure", "money": True, "short": "Expenditure in connection with transfer",
     "label": "Expenditure wholly and exclusively in connection with transfer"},
    {"no": "13", "key": "total_deductions", "money": True, "short": "Total deductions (7+12)",
     "label": "Total deductions (7+12)"},
    {"no": "14", "key": "balance", "money": True, "short": "Balance (6-13)",
     "label": "Balance (6-13), to item 4(a) of the long-term capital gains part of Schedule CG"},
]

SUMMED = ("full_value", "cost_without_indexation", "cost_of_acquisition", "lower_of_6_and_11",
          "fmv_total", "expenditure", "total_deductions", "balance")


def _lot(row: dict, raw: dict) -> dict:
    """One sale of the ledger, in this schedule's columns."""
    proceeds = row["proceeds"]
    actual = row.get("cost_stated", row["cost"]) + row.get("purchase_expenses", 0)
    acquired = _d(row.get("acquired_on"))
    before = bool(acquired and acquired <= LAST_GRANDFATHERED_DAY)
    fmv_total = _amt(raw.get("fmv_31jan2018")) if raw.get("fmv_31jan2018") else 0
    quantity = raw.get("quantity")
    lower = min(proceeds, fmv_total) if before and fmv_total else 0
    return {
        "acquired": ("unknown" if acquired is None else "on_or_before" if before else "after"),
        "isin": raw.get("isin") or "",
        "name": row.get("description") or raw.get("description") or "",
        "quantity": quantity,
        "sale_price_per_unit": round(proceeds / quantity, 2) if quantity else None,
        "full_value": proceeds,
        # What the ledger used: the actual cost, or the grandfathered value.
        "cost_without_indexation": row["cost"],
        "cost_of_acquisition": actual,
        "lower_of_6_and_11": lower,
        "fmv_per_unit": round(fmv_total / quantity, 2) if quantity and fmv_total and before else None,
        "fmv_total": fmv_total if before else 0,
        "expenditure": row["expenses"],
        "total_deductions": row["cost"] + row["expenses"],
        "balance": row["gain"],
        "acquired_on": row.get("acquired_on"),
        "transferred_on": row.get("transferred_on"),
        "ledger_row": row.get("index"),
    }


def build(cg: dict | None, cg_doc: dict | None) -> dict:
    """Schedule 112A's rows and totals, from the computed ledger."""
    raw_rows = ((cg_doc or {}).get("data") or {}).get("disposals") or []
    lots = []
    for row in (cg or {}).get("rows") or []:
        if row.get("section") != "112A" or row.get("term") != "long":
            continue
        index = row.get("index")
        raw = raw_rows[index] if isinstance(index, int) and index < len(raw_rows) else {}
        lots.append(_lot(row, raw))

    # A lot with no acquisition date cannot be put on either side of the line,
    # and the consolidated row is only for lots known to be after it.
    scrip_wise = [lot for lot in lots if lot["acquired"] != "after"]
    after = [lot for lot in lots if lot["acquired"] == "after"]

    rows = []
    for lot in scrip_wise:
        rows.append({**lot, "sl": len(rows) + 1, "lots": []})
    if after:
        consolidated = {key: sum(lot[key] or 0 for lot in after) for key in SUMMED}
        rows.append({
            "sl": len(rows) + 1,
            "acquired": "after",
            "isin": CONSOLIDATED_ISIN,
            "name": CONSOLIDATED_NAME,
            "quantity": None,
            "sale_price_per_unit": None,
            "fmv_per_unit": None,
            **consolidated,
            # Columns 9 and 11 do not apply to anything acquired after the day.
            "lower_of_6_and_11": 0,
            "fmv_total": 0,
            "lots": after,
        })

    totals = {key: sum(r[key] or 0 for r in rows) for key in SUMMED}

    notes = []
    if after:
        notes.append(
            f"{len(after)} sale(s) of shares or units acquired after 31 January 2018 are entered "
            f"as one consolidated row, as the form's instructions allow: column 1a 'After 31st "
            f"January 2018', ISIN {CONSOLIDATED_ISIN}, name {CONSOLIDATED_NAME}. Nothing is worked "
            f"out scrip by scrip for them, so nothing is lost by adding them up. Open the row to "
            f"see each sale.")
    grandfathered = [lot for lot in scrip_wise if lot["acquired"] == "on_or_before"]
    if grandfathered:
        notes.append(
            f"{len(grandfathered)} sale(s) of shares or units acquired on or before 31 January "
            f"2018 are entered scrip by scrip, because their cost may be replaced by the fair "
            f"market value on that day and that is worked out share by share.")
        missing = [lot for lot in grandfathered if not lot["fmv_total"]]
        if missing:
            notes.append(
                f"{len(missing)} of those carry no fair market value for 31 January 2018, so the "
                f"actual cost is used and the relief may be understated: "
                + "; ".join(lot["name"][:40] for lot in missing[:6]) + ".")
    undated = [lot for lot in scrip_wise if lot["acquired"] == "unknown"]
    if undated:
        notes.append(
            f"{len(undated)} sale(s) have no acquisition date, so it cannot be said which side of "
            f"31 January 2018 they fall on. They are listed on their own until the date is known: "
            + "; ".join(lot["name"][:40] for lot in undated[:6]) + ".")
    if lots:
        notes.append(
            "Column 8 is the purchase value plus the charges paid on purchase; column 12 is the "
            "charges on the sale. Securities transaction tax is in neither: section 48 allows no "
            "deduction for it.")
        notes.append(
            "The exemption of the first Rs 1,25,000 of these gains is applied where the tax is "
            "computed, not on this schedule.")

    return {
        "columns": COLUMNS,
        "rows": rows,
        "totals": totals,
        "sales": len(lots),
        "carried_to": "Schedule CG, long-term capital gains, item 4(a)",
        "notes": notes,
        "verify": ("Column numbers and wording follow Schedule 112A of the ITR-3 as printed for "
                   "this assessment year. Check them, and that consolidated entry is still "
                   "offered, against the utility you file with."),
    }
