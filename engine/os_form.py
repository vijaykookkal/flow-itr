"""Schedule OS laid out as the ITR-3 numbers it, from the other-sources ledger.

The ledger answers "who paid what". The form asks a different question: which
numbered line does each receipt belong on, and what is the total of each. One
savings account and fifty dividend credits collapse into two lines of the
return -- but a person checking it needs to see which bank and which company
made up each line, so every item carries its payers underneath.

Item numbers follow the ITR-3 Schedule OS structure. VERIFY THEM against the
released utility for the assessment year: numbering has moved between years,
and a correct amount on the wrong line is still a defective return.
"""

from __future__ import annotations

from datetime import date

from . import fx

# Which Schedule OS line each ledger category belongs on.
ITEMS = {
    "dividend": "1a",
    "interest_savings": "1b(i)",
    "interest_deposits": "1b(ii)",
    "interest_income_tax_refund": "1b(iii)",
    "interest_other": "1b(v)",
    "rental_machinery": "1c",
    "gifts_56_2_x": "1d",
    "family_pension": "1e",
    "other": "1e",
    "winnings_115BB": "2a",
}

LABELS = {
    "1a": "Dividends, gross",
    "1b(i)": "Interest from savings account",
    "1b(ii)": "Interest from deposits (bank, post office, co-operative)",
    "1b(iii)": "Interest on an income-tax refund",
    "1b(iv)": "Interest in the nature of pass-through income",
    "1b(v)": "Other interest",
    "1c": "Rental income from machinery, plant or furniture",
    "1d": "Income referred to in section 56(2)(x)",
    "1e": "Any other income",
    "1": "Gross income chargeable at normal rates",
    "2a": "Winnings from lotteries, crossword puzzles, games",
    "2": "Income chargeable at special rates",
    "3": "Deductions under section 57",
    "6": "Net income from other sources",
}

ORDER = ["1a", "1b(i)", "1b(ii)", "1b(iii)", "1b(iv)", "1b(v)", "1c", "1d", "1e"]

# Rule 115 fixes the conversion date by the kind of income. For a dividend it
# is the last day of the month before the month it was declared, distributed or
# paid; interest from a foreign source follows the same shape.
FOREIGN_RULE = "Rule 115: last day of the month before the month of receipt"


def _d(value):
    if not value:
        return None
    try:
        y, m, d = (int(p) for p in str(value)[:10].split("-"))
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def _rupees(node, received_on, fx_rates):
    """(rupees, working, need). `need` is set when a rate is missing."""
    if not isinstance(node, dict):
        return int(node or 0), None, None
    if not fx.is_foreign(node):
        return int(node.get("amount") or 0), None, None

    when = _d(received_on)
    currency = str(node["currency"]).upper()
    if when is None:
        return None, None, {"currency": currency, "date": None,
                            "why": f"{currency} amount with no date of receipt, so Rule 115 "
                                   f"cannot fix a rate for it"}
    rate_date = fx.rule115_date(when)
    rupees, why = fx.convert(node, rate_date, fx_rates, FOREIGN_RULE)
    if rupees is None:
        return None, None, {"currency": currency, "date": rate_date.isoformat(), "why": why}
    return rupees, fx.working(node, rate_date, fx_rates, FOREIGN_RULE), None


def build(os_doc: dict, ay: str, fx_rates: dict | None = None) -> dict:
    """Schedule OS as the form lays it out, with each line's payers beneath it."""
    fx_rates = fx.load_rates() if fx_rates is None else fx_rates
    data = (os_doc or {}).get("data") or {}
    items = data.get("items") or []

    lines: dict[str, dict] = {}
    pending: list[dict] = []
    needed: dict[tuple, int] = {}

    for entry in items:
        category = entry.get("category") or "other"
        code = ITEMS.get(category, "1e")
        rupees, working, need = _rupees(entry.get("amount"), entry.get("received_on"), fx_rates)
        payer = entry.get("payer") or "(not named)"
        foreign = fx.is_foreign(entry.get("amount"))

        if need:
            pending.append({"item": code, "payer": payer, "category": category,
                            "currency": need["currency"], "why": need["why"],
                            "amount_foreign": (entry.get("amount") or {}).get("amount_foreign")})
            if need["date"]:
                needed[(need["currency"], need["date"])] = needed.get((need["currency"], need["date"]), 0) + 1
            continue

        line = lines.setdefault(code, {"item": code, "label": LABELS.get(code, code),
                                       "amount": 0, "payers": {}, "foreign": 0})
        line["amount"] += rupees
        if foreign:
            line["foreign"] += rupees
        p = line["payers"].setdefault(payer, {"payer": payer, "amount": 0, "count": 0,
                                              "account": entry.get("account_ref"),
                                              "foreign": False, "receipts": []})
        p["amount"] += rupees
        p["count"] += 1
        p["foreign"] = p["foreign"] or foreign
        # Every receipt is kept, not just their total. A converted one has its
        # own date and therefore its own rate, and a rate is derived data: it
        # has to be checkable receipt by receipt, the way a disposal is.
        p["receipts"].append({"received_on": entry.get("received_on"), "amount": rupees,
                              "working": working,
                              "stated": (entry.get("amount") or {}) if foreign else None})

    for line in lines.values():
        for p in line["payers"].values():
            p["receipts"].sort(key=lambda r: r["received_on"] or "")
        line["payers"] = sorted(line["payers"].values(), key=lambda p: -p["amount"])

    normal = [lines[c] for c in ORDER if c in lines]
    special = [lines[c] for c in lines if c.startswith("2")]
    gross_normal = sum(line["amount"] for line in normal)
    special_total = sum(line["amount"] for line in special)

    deductions_57 = data.get("deductions_57")
    d57 = int((deductions_57 or {}).get("amount") or 0) if isinstance(deductions_57, dict) \
        else int(deductions_57 or 0)

    return {
        "normal": normal,
        "special": special,
        "gross_normal": gross_normal,
        "special_total": special_total,
        "deductions_57": d57,
        "net": gross_normal - d57,
        "stated_gross": int(((data.get("gross_income_from_os") or {}) or {}).get("amount") or 0)
                        if isinstance(data.get("gross_income_from_os"), dict)
                        else int(data.get("gross_income_from_os") or 0),
        "pending": pending,
        "rates_needed": [{"currency": c, "date": d, "rows": n} for (c, d), n in sorted(needed.items())],
        "verify": ("Item numbers follow the ITR-3 Schedule OS structure and must be checked "
                   "against the released utility for this assessment year."),
    }
