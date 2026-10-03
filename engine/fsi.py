"""Schedules FSI and TR, computed from the receipts rather than transcribed.

The first version of this asked the extraction to fill in Schedule FSI, and it
came back all zeros -- correctly. Column (c) is defined by the form as the
foreign income *already included in Part B-TI*, and column (f) is the lower of
(d) and (e). Neither is in any document: (c) is the rupee figure after Rule 115
has been applied to each receipt on its own date, and (e) is Indian tax. The
extraction cannot know either, and the one thing worse than a blank column (f)
is a guessed one, because (f) is a claim for money.

So the documents supply what documents can supply -- each receipt, its date,
its currency, and the tax withheld on it -- and this builds the schedules:

  * every foreign receipt converts at its own Rule 115 date, and so does the
    withholding on it, because a year's withholding converted at one rate is
    wrong by the amount the rupee moved;
  * head v is Other Sources, head iv is Capital Gains, and a receipt lands in
    the head the rest of the return already put it in;
  * relief is the lower of the foreign tax and the Indian tax on the same
    income (s.90(2)), computed per country;
  * Schedule TR is FSI summed by country, which is all it is.
"""

from __future__ import annotations

import datetime as dt

from . import fx

# The article of the India-US treaty each head of income falls under. Only the
# ones this tool actually meets; anything else is left for a person to state.
DTAA_ARTICLES = {("2", "Other Sources"): "10"}     # dividends

HEADS = [("i", "Salary"), ("ii", "House Property"), ("iii", "Business or Profession"),
         ("iv", "Capital Gains"), ("v", "Other Sources")]

# Where a document does not name the country, a US broker is the overwhelming
# majority of what this tool sees, and the code is stated so it can be corrected.
DEFAULT_COUNTRY = ("2", "United States of America")


def _amount(node) -> int:
    if isinstance(node, dict):
        return int(node.get("amount") or 0)
    try:
        return int(node or 0)
    except (TypeError, ValueError):
        return 0


def _is_foreign(node) -> bool:
    return isinstance(node, dict) and bool(node.get("currency"))


def _country_of(payer: str, stated: str | None) -> tuple[str, str]:
    if stated:
        return ("", stated)
    return DEFAULT_COUNTRY


def _date(value):
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _convert(node, when, rates: dict, why: str) -> tuple[int, dict | None]:
    """A stated foreign amount in rupees, at its own Rule 115 date.

    Rule 115 fixes the rate at the last day of the month BEFORE the receipt, so
    the date the money arrived is not the date the rate comes from. fx does
    that shift; passing the raw receipt date straight through would silently
    use the wrong month.
    """
    if not _is_foreign(node):
        return _amount(node), None
    day = _date(when)
    if day is None:
        return 0, {"why": "no date of receipt, so Rule 115 cannot fix a rate for it"}
    rate_date = fx.rule115_date(day)
    rupees, reason = fx.convert(node, rate_date, rates, why)
    if rupees is None:
        return 0, {"why": reason}
    return int(rupees), fx.working(node, rate_date, rates, why)


def build(docs: dict, rates: dict, indian_tax_rate: float = 0.0) -> dict | None:
    """Schedules FSI and TR, or None when nothing was earned outside India.

    `indian_tax_rate` is the marginal rate the foreign income actually bore in
    this return. Relief is capped by the Indian tax on the same income, so a
    rate of zero produces nil relief -- which is the honest answer before the
    computation that supplies it has run.
    """
    os_doc = docs.get("other_sources") or {}
    items = (os_doc.get("data") or {}).get("items") or []

    countries: dict[str, dict] = {}
    unconverted: list[dict] = []

    def row(code: str, name: str, head: str) -> dict:
        c = countries.setdefault(code or name, {
            "country_code": code, "country": name,
            "taxpayer_identification_number": None,
            "heads": {h: {"item": i, "head": h, "income": 0, "tax_paid": 0,
                          "receipts": []} for i, h in HEADS},
        })
        return c["heads"][head]

    for item in items:
        node = item.get("amount")
        withheld = item.get("tax_withheld_outside_india")
        if not _is_foreign(node) and not _is_foreign(withheld):
            continue
        when = item.get("received_on")
        code, name = _country_of(item.get("payer", ""), item.get("country"))
        head = row(code, name, "Other Sources")

        income, work = _convert(node, when, rates, "foreign receipt, Rule 115")
        tax, tax_work = _convert(withheld, when, rates, "foreign tax withheld, Rule 115")
        if _is_foreign(node) and not income:
            unconverted.append({"payer": item.get("payer"), "received_on": when,
                                "why": (work or {}).get("why") or "no rate for this date"})
            continue
        head["income"] += income
        head["tax_paid"] += tax
        head["receipts"].append({
            "payer": item.get("payer"), "received_on": when,
            "stated": node if _is_foreign(node) else None, "income": income,
            "withheld_stated": withheld if _is_foreign(withheld) else None, "tax_paid": tax,
            "working": work, "tax_working": tax_work,
        })

    if not countries:
        return None

    out_countries = []
    for c in countries.values():
        heads = []
        for item, name in HEADS:
            h = c["heads"][name]
            # The Indian tax on this slice, which is what caps the relief.
            payable = int(round(h["income"] * indian_tax_rate))
            relief = min(h["tax_paid"], payable)
            heads.append({
                "item": item, "head": name,
                "income_outside_india": h["income"],
                "tax_paid_outside_india": h["tax_paid"],
                "tax_payable_in_india": payable,
                "relief_available": relief,
                "dtaa_article": DTAA_ARTICLES.get((c["country_code"], name)),
                "receipts": h["receipts"],
            })
        out_countries.append({**{k: v for k, v in c.items() if k != "heads"}, "heads": heads,
                              "total_income": sum(h["income_outside_india"] for h in heads),
                              "total_tax_paid": sum(h["tax_paid_outside_india"] for h in heads),
                              "total_payable": sum(h["tax_payable_in_india"] for h in heads),
                              "total_relief": sum(h["relief_available"] for h in heads)})

    tr = [{
        "country_code": c["country_code"], "country": c["country"],
        "taxpayer_identification_number": c.get("taxpayer_identification_number"),
        "total_taxes_paid_outside": c["total_tax_paid"],
        "total_relief_available": c["total_relief"],
        "relief_section": "90" if c["country_code"] else None,
    } for c in out_countries]

    notes = []
    if not indian_tax_rate:
        notes.append(
            "Relief is nil because the Indian tax on this income has not been worked out "
            "yet. Section 90(2) caps relief at the Indian tax on the same income, so until "
            "that is known the only honest figure is nil.")
    withheld_total = sum(c["total_tax_paid"] for c in out_countries)
    if not withheld_total:
        notes.append(
            "No foreign tax withheld is recorded against any receipt, so there is nothing "
            "to claim relief on. If tax WAS withheld -- a Form 1042-S or an 'NRA tax' line "
            "on a broker statement -- re-run Other Sources: the withholding is recorded "
            "receipt by receipt there, and Schedule FSI is built from it.")
    if not any(h["income_outside_india"] for c in out_countries
               for h in c["heads"] if h["head"] == "Salary"):
        notes.append(
            "Head i, Salary, is nil, and for an RSU or ESOP vest that is correct. The "
            "perquisite under section 17(2)(vi) is Indian salary -- the employer is Indian "
            "and the employment was exercised in India -- so it belongs in Schedule S and "
            "nowhere else. The shares being a foreign company's does not make the income "
            "foreign, and no tax is withheld abroad on a vest, so there is nothing to claim. "
            "It would be different only if part of the vesting period was worked in the "
            "other country and that country taxed it.")
    notes.append(
        "Relief under section 90, 90A or 91 requires Form 67 filed BEFORE the return. "
        "Nothing in this tool files it.")

    return {
        "schedule_fsi": out_countries,
        "schedule_tr": {"countries": tr,
                        "treaty_relief": sum(t["total_relief_available"] for t in tr
                                             if str(t["relief_section"] or "").startswith("90")),
                        "non_treaty_relief": sum(t["total_relief_available"] for t in tr
                                                 if t["relief_section"] == "91")},
        "total_relief": sum(t["total_relief_available"] for t in tr),
        "unconverted": unconverted,
        "notes": notes,
        "verify": ("Each receipt and the tax withheld on it are converted at that receipt's "
                   "own Rule 115 date. Columns (e) and (f) are computed: (f) is the lower of "
                   "(d) and (e), under section 90(2)."),
    }
