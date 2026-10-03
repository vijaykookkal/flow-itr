"""Schedule CG, computed from the disposal ledger.

The extraction reports what each contract note says. Everything that decides
the tax is worked out here:

  * whether a disposal is short-term or long-term, from the dates and the asset
    class -- not from whatever the broker's statement called it;
  * the section 112A cost substitution for equity bought before 01-02-2018;
  * what comes off the sale value under section 48: the cost of acquisition,
    which includes the charges paid on purchase, and the expenditure on the
    transfer itself -- and what does not, securities transaction tax;
  * which rate applies, which depends on the transfer date because the rules
    changed on 23 July 2024;
  * the set-off order for losses, where short-term losses may be set against any
    capital gain but long-term losses only against long-term gains.

Every one of those is a rule with a citation, which is exactly the kind of thing
that should be in tested code rather than in a prompt.
"""

from __future__ import annotations

from datetime import date

from . import fx


def _d(value: str | None) -> date | None:
    if not value:
        return None
    try:
        y, m, d = (int(p) for p in value.split("-"))
        return date(y, m, d)
    except (ValueError, AttributeError):
        return None


def _amt(node, default: int = 0) -> int:
    if node is None:
        return default
    if isinstance(node, dict):
        return int(node.get("amount") or 0)
    return int(node)


def months_between(start: date, end: date) -> int:
    """Whole months, the way a holding period is counted."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months


def term_of(row: dict, rates) -> tuple[str, str]:
    """('short'|'long', why). The dates decide, never the document's label."""
    asset = row.get("asset_class", "other")
    if asset in rates.ALWAYS_SHORT_TERM:
        return "short", "Specified mutual fund under section 50AA - short-term regardless of holding period"

    acquired, transferred = _d(row.get("acquired_on")), _d(row.get("transferred_on"))
    if not acquired or not transferred:
        return "short", "No acquisition date, so the holding period cannot be established - treated as short-term pending review"

    threshold = rates.HOLDING_PERIOD_MONTHS.get(asset, 24)
    held = months_between(acquired, transferred)
    if held >= threshold:
        return "long", f"Held {held} months, at or beyond the {threshold}-month threshold for {asset}"
    return "short", f"Held {held} months, short of the {threshold}-month threshold for {asset}"


def cost_for(row: dict, term: str, rates) -> tuple[int, str]:
    """Cost of acquisition, with the section 112A substitution where it applies.

    The actual cost is what was paid to acquire the asset: the purchase value
    and the charges paid on the purchase -- brokerage, stamp duty, exchange and
    SEBI charges, GST. A document that states those charges beside the purchase
    value is stating part of the cost, and leaving them out overstates the
    gain. Securities transaction tax is not among them: section 48 allows no
    deduction for it, so it is never added to cost.

    For listed equity acquired before 01-02-2018 the cost becomes the higher of
    actual cost and the lower of (31-Jan-2018 FMV, sale consideration). The
    effect is that gains accrued up to 31-Jan-2018 are not taxed.
    """
    stated = _amt(row.get("cost_of_acquisition"))
    charges = _amt(row.get("purchase_expenses"))
    cost = stated + charges
    actual = (f"Purchase value Rs {stated:,} plus Rs {charges:,} of charges paid on the purchase"
              if charges else "Actual cost")
    if row.get("asset_class") != "equity_stt" or term != "long":
        return cost, actual

    acquired = _d(row.get("acquired_on"))
    fmv = _amt(row.get("fmv_31jan2018")) if row.get("fmv_31jan2018") else 0
    if not acquired or acquired >= date(2018, 2, 1):
        return cost, f"{actual} - acquired on or after 01-02-2018, so grandfathering does not apply"
    if not fmv:
        return cost, (f"{actual}, but this was acquired before 01-02-2018 and no "
                      "31-Jan-2018 fair market value was supplied - grandfathering may reduce the gain")

    substituted = max(cost, min(fmv, _amt(row.get("full_value"))))
    if substituted == cost:
        return cost, "Grandfathering considered; actual cost was already higher"
    return substituted, (f"Section 112A grandfathering: cost substituted from Rs {cost:,} "
                         f"to Rs {substituted:,} using the 31-Jan-2018 value")


# A document's gain and the one computed here are each built from figures
# rounded to the rupee -- sale value, cost, the two sets of charges -- so they
# can part by a rupee or two with nothing wrong.
STATED_GAIN_TOLERANCE = 3


def stated_gain_basis(stated: int | None, gain: int, proceeds: int, stated_cost: int,
                      improvement: int, transfer: int) -> str | None:
    """Which gain the document was stating: 'after charges', 'before charges'
    or 'after selling charges' -- or None when it matches none of them, which
    is a disagreement worth a person's attention.

    Brokers differ. One nets both sets of charges into its profit column;
    another prints sale value less purchase value and lists the charges beside
    it. Neither is wrong, and a document stating its gain before charges does
    not disagree with a computation that takes them off.
    """
    if stated is None:
        return None
    before = proceeds - stated_cost - improvement
    for name, value in (("after charges", gain), ("before charges", before),
                        ("after selling charges", before - transfer)):
        if abs(stated - value) <= STATED_GAIN_TOLERANCE:
            return name
    return None


def compute_row(row: dict, rates) -> dict:
    term, term_why = term_of(row, rates)
    cost, cost_why = cost_for(row, term, rates)

    proceeds = _amt(row.get("full_value"))
    transfer = _amt(row.get("transfer_expenses"))
    improvement = _amt(row.get("cost_of_improvement"))
    # Section 48: sale value, less expenditure on the transfer, less the cost
    # of acquisition and of improvement. STT is in none of them.
    expenses = transfer + improvement
    gain = proceeds - cost - expenses

    asset = row.get("asset_class", "other")
    table = rates.CG_RATES.get(asset, rates.CG_RATES["default"])[term]

    transferred = _d(row.get("transferred_on"))
    changeover = _d(rates.CG_CHANGEOVER)
    post = bool(transferred and changeover and transferred >= changeover)

    stated = _amt(row.get("stated_gain")) if row.get("stated_gain") else None
    stated_term = row.get("stated_term")
    stated_as = stated_gain_basis(stated, gain, proceeds, _amt(row.get("cost_of_acquisition")),
                                  improvement, transfer)

    return {
        "description": row.get("description", ""),
        "asset_class": asset,
        "acquired_on": row.get("acquired_on"),
        "transferred_on": row.get("transferred_on"),
        "term": term,
        "term_reason": term_why,
        "proceeds": proceeds,
        "cost": cost,
        "cost_reason": cost_why,
        "cost_stated": _amt(row.get("cost_of_acquisition")),
        "purchase_expenses": _amt(row.get("purchase_expenses")),
        "expenses": expenses,
        # Seen, and deliberately deducted nowhere.
        "stt": _amt(row.get("stt")),
        "gain": gain,
        "stated_gain_is": stated_as,
        "section": table["section"],
        "rate": table.get("rate"),
        "post_changeover": post,
        "disagreements": [
            d for d in (
                (f"Document states a gain of Rs {stated:,}; computed Rs {gain:,}, and the "
                 f"difference is not the charges on either trade"
                 if stated is not None and stated_as is None else None),
                (f"Document classified this as {stated_term}-term; the dates make it {term}"
                 if stated_term and stated_term != term else None),
                ("No acquisition date, so the holding period is unverified"
                 if not row.get("acquired_on") else None),
            ) if d
        ],
    }


MONEY_FIELDS = ("full_value", "cost_of_acquisition", "purchase_expenses", "cost_of_improvement",
                "transfer_expenses", "stt", "fmv_31jan2018", "stated_gain")


# How a foreign disposal is converted. This tool is for residents, and a
# resident is taxed on the RUPEE gain: the sale value at the Rule 115 rate (last
# day of the month before the transfer), the cost at the rate on the day the
# asset was acquired, and the difference -- currency movement included. Working
# the gain out in foreign currency and converting once is the relief the first
# proviso to section 48 gives non-residents only, so it is not offered.
#
# A cost the documents already state in rupees -- such as the perquisite value
# of RSU shares under section 49(2AA) -- is used as stated.
COST_FIELDS = ("cost_of_acquisition", "purchase_expenses", "cost_of_improvement")


def in_rupees(row: dict, fx_rates: dict
              ) -> tuple[dict | None, list[str], set[tuple[str, str, str]]]:
    """The row with every foreign amount converted, plus how each was converted.

    Returns (row, how, needs), where needs holds (currency, date, message) for
    every rate still missing. When any amount cannot be converted the row is
    None: a disposal with rupee proceeds and a dollar cost, or the reverse,
    would produce a gain that is simply wrong."""
    how: list[str] = []
    needs: set[tuple[str, str, str]] = set()
    out = dict(row)
    transferred = _d(row.get("transferred_on"))
    acquired = _d(row.get("acquired_on"))
    sale_date = fx.rule115_date(transferred) if transferred else None

    for field in MONEY_FIELDS:
        node = row.get(field)
        if not fx.is_foreign(node):
            continue
        if field == "stated_gain":
            # A gain stated in dollars is a different quantity from a rupee gain
            # with each side at its own rate; comparing them would only report
            # the exchange movement as a disagreement.
            out[field] = None
            continue
        if field in COST_FIELDS:
            when, label = acquired, "rate on the acquisition date"
        else:
            when, label = sale_date, "Rule 115: last day of the month before the sale"
        rupees, why = fx.convert(node, when, fx_rates, label)
        if rupees is None:
            needs.add((str(node["currency"]).upper(), when.isoformat() if when else "", why))
            continue
        out[field] = {**node, "amount": rupees, "basis": why,
                      "fx": fx.working(node, when, fx_rates, label)}
        how.append(f"{field}: {why}")
    return (None if needs else out), how, needs


def summarise(cg_doc: dict, rates, fx_rates: dict | None = None) -> dict:
    """Schedule CG's boxes, derived from the ledger."""
    if not cg_doc:
        return {"rows": [], "buckets": {}, "net": {}, "total_taxable": 0,
                "disagreements": [], "unconverted": [], "rates_needed": []}

    fx_rates = fx.load_rates() if fx_rates is None else fx_rates
    rows, unconverted = [], []
    needed: dict[tuple[str, str], int] = {}
    for index, raw in enumerate(cg_doc.get("data", {}).get("disposals", [])):
        row, how, needs = in_rupees(raw, fx_rates)
        if row is None:
            unconverted.append({"index": index, "description": raw.get("description", ""),
                                "transferred_on": raw.get("transferred_on"),
                                "needs": sorted({msg for _c, _d2, msg in needs})})
            # Counted once per disposal, not once per dollar field in it.
            for key in {(c, d2) for c, d2, _m in needs if d2}:
                needed[key] = needed.get(key, 0) + 1
            continue
        computed = compute_row(row, rates)
        computed["index"] = index      # the ledger row this came from
        if how:
            computed["converted"] = how
            # Each converted amount's working, for the ledger to show.
            computed["fx"] = {f: row[f]["fx"] for f in MONEY_FIELDS
                              if isinstance(row.get(f), dict) and row[f].get("fx")}
        rows.append(computed)

    buckets: dict[str, dict] = {}
    for r in rows:
        key = f"{r['section']}_{r['term']}"
        b = buckets.setdefault(key, {"section": r["section"], "term": r["term"],
                                     "rate": r["rate"], "gain": 0, "rows": 0})
        b["gain"] += r["gain"]
        b["rows"] += 1

    # Section 112A's Rs 1.25 lakh exemption applies once across all 112A gains.
    exemption_used = 0
    if "112A_long" in buckets and buckets["112A_long"]["gain"] > 0:
        exemption_used = min(buckets["112A_long"]["gain"], rates.EXEMPTION_112A)
        buckets["112A_long"]["exemption"] = exemption_used
        buckets["112A_long"]["taxable"] = buckets["112A_long"]["gain"] - exemption_used

    short_total = sum(b["gain"] for b in buckets.values() if b["term"] == "short")
    long_total = sum(b.get("taxable", b["gain"]) for b in buckets.values() if b["term"] == "long")

    deductions = sum(_amt(d.get("amount"))
                     for d in cg_doc.get("data", {}).get("deductions", []))

    stated = cg_doc.get("data", {}).get("totals", {})
    disagreements = [d for r in rows for d in r["disagreements"]]
    # A foreign disposal with no rate is kept OUT of every figure above, and
    # said so here -- counting it at zero would understate a loss or a gain.
    for u in unconverted:
        disagreements.append(
            f"{u['description']} (transferred {u['transferred_on']}) is not in these "
            f"totals: {'; '.join(u['needs'])}. Look it up or enter it on the Capital Gains page.")
    for key, computed in (("stated_short_term", short_total), ("stated_long_term", long_total)):
        if stated.get(key) is not None:
            said = _amt(stated[key])
            if said != computed:
                disagreements.append(
                    f"Document states {key.replace('stated_', '').replace('_', '-')} of "
                    f"Rs {said:,}; the ledger computes Rs {computed:,}"
                )

    return {
        "rows": rows,
        "buckets": buckets,
        "exemption_112a_used": exemption_used,
        "net": {"short_term": short_total, "long_term": long_total},
        "deductions_claimed": deductions,
        "total_taxable": max(0, short_total + long_total - deductions),
        "disagreements": disagreements,
        "unconverted": unconverted,
        # One entry per rate still to be entered, so the page can ask for each.
        "rates_needed": [{"currency": c, "date": d, "rows": n}
                         for (c, d), n in sorted(needed.items())],
    }
