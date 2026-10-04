"""The year as it is likely to turn out: what has been read so far, and what is
expected for the rest of it.

A return is computed from evidence, and a plan cannot wait for the evidence: in
October the Form 16 is months away. But the salary slips so far, the sales
already made and a note of what is coming are enough to see where the year is
heading, while there is still time to act on it.

So this takes the schedules read so far and adds to them, as entries clearly
labelled as expected, what is still to come: from the planning notes, from
scaling the months the documents cover, or as typed on the Planning page. The
result is computed by the return's own engine (compute.tax_for_regime), so
every rate, cap, set-off and relief is the return's own and nothing here has a
tax rule of its own. The expected entries live only inside a projection; they
are never written into a schedule.
"""

from __future__ import annotations

import copy
import re
from datetime import date

from . import compute
from .planning import planning_rates, tax_at

REGIMES = ("new", "old")
PLANNED = "Planning: expected for the rest of the year"

# Where a gain or loss still to be booked is placed, as one of four kinds the
# person can recognise. Each becomes a ledger row the engine then rates and
# sets off like any other: an asset class and a holding period on either side
# of that class's threshold.
BUCKETS = {
    "equity_short": {"label": "Listed shares and equity funds, short-term",
                     "asset_class": "equity_stt", "held_months": 6},
    "equity_long": {"label": "Listed shares and equity funds, long-term",
                    "asset_class": "equity_stt", "held_months": 36},
    "other_short": {"label": "Foreign shares and other assets, short-term",
                    "asset_class": "foreign_shares", "held_months": 6},
    "other_long": {"label": "Foreign shares and other assets, long-term",
                   "asset_class": "foreign_shares", "held_months": 36},
}

# Advance tax: the share of the year's tax due by each date (section 211),
# and the share below which interest under section 234C begins.
INSTALMENTS = ((6, 15, 0.15, 0.12), (9, 15, 0.45, 0.36), (12, 15, 0.75, 0.75), (3, 15, 1.00, 1.00))
ADVANCE_TAX_FLOOR = 10_000          # section 208: less than this, none is due
CARRY_FORWARD_YEARS = 8             # sections 74 and 72

MONTH_NAMES = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def _amt(node) -> int:
    if isinstance(node, dict):
        return int(node.get("amount") or 0)
    return int(node or 0)


def _cite(node) -> str:
    return (node.get("cite") or "") if isinstance(node, dict) else ""


# --------------------------------------------------------------------------
# the year and its months
# --------------------------------------------------------------------------
def fy_bounds(ay: str) -> tuple[date, date]:
    start = int(ay[:4]) - 1
    return date(start, 4, 1), date(start + 1, 3, 31)


def months_gone(today: date, start: date, end: date) -> int:
    """Whole months of the year already over: in October, six (April to September)."""
    if today < start:
        return 0
    if today > end:
        return 12
    return (today.year - start.year) * 12 + today.month - start.month


def _dates_in(text: str) -> list[date]:
    """Every date a period string mentions, in the forms documents use."""
    found = []
    for y, m, d in re.findall(r"(\d{4})-(\d{1,2})-(\d{1,2})", text):
        found.append((int(y), int(m), int(d)))
    for d, m, y in re.findall(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", text):
        found.append((int(y), int(m), int(d)))
    for name, y in re.findall(r"\b([A-Za-z]{3,9})[ ,'\-]*(\d{4})\b", text):
        month = MONTH_NAMES.get(name[:3].lower())
        if month:
            found.append((int(y), month, 1))
    out = []
    for y, m, d in found:
        try:
            out.append(date(y, m, max(1, min(d, 28))))
        except ValueError:
            continue
    return out


def _month_set(first: date, last: date, start: date, end: date) -> set[tuple[int, int]]:
    out, y, m = set(), first.year, first.month
    while (y, m) <= (last.year, last.month):
        if start <= date(y, m, 1) <= end:
            out.add((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def salary_months(salary_doc: dict | None, start: date, end: date) -> int | None:
    """How many months of the year the salary documents cover, from the period
    each employer's entry states. None when any entry does not say."""
    employers = ((salary_doc or {}).get("data") or {}).get("employers") or []
    if not employers:
        return None
    months: set[tuple[int, int]] = set()
    for e in employers:
        dates = _dates_in(str(e.get("period") or ""))
        if not dates:
            return None
        months |= _month_set(min(dates), max(dates), start, end)
    return len(months) or None


def _month_count(from_month: str | None, to_month: str | None, start: date, end: date) -> int:
    """Months of the year between two YYYY-MM marks, either end open."""
    def parse(text, default):
        match = re.match(r"^(\d{4})-(\d{2})", str(text or ""))
        return date(int(match.group(1)), int(match.group(2)), 1) if match else default
    first = parse(from_month, start)
    last = parse(to_month, end)
    return len(_month_set(max(first, start), min(last, end), start, end))


# --------------------------------------------------------------------------
# the planning notes
# --------------------------------------------------------------------------
def read_notes(plan_doc: dict | None, start: date, end: date, rates=None) -> dict:
    """What the planning notes expect, turned into amounts for the year.

    The notes are transcribed as stated -- "Rs 3.5 lakh a month from April",
    "a bonus of Rs 4 lakh in June" -- and the arithmetic is done here, so it
    can be checked."""
    out = {"salary": [], "other": [], "tds": [], "deductions": [],
           "gains": {key: [] for key in BUCKETS}, "unused": []}
    for e in (((plan_doc or {}).get("data") or {}).get("expectations") or []):
        node = e.get("amount")
        entry = {"kind": e.get("kind"), "description": e.get("description", ""),
                 "cite": _cite(node), "per": e.get("per")}
        if isinstance(node, dict) and "amount" not in node:
            out["unused"].append({**entry, "why": "stated only in a foreign currency"})
            continue
        amount = _amt(node)
        if e.get("per") == "month":
            months = _month_count(e.get("from_month"), e.get("to_month"), start, end)
            entry.update(year=amount * months, how=f"{inr(amount)} a month for {months} months")
        else:
            entry.update(year=amount, how=inr(amount) + (" for the year" if e.get("per") == "year" else ""))
        kind = e.get("kind")
        if kind in ("salary", "bonus"):
            out["salary"].append(entry)
        elif kind in ("interest", "dividend", "other_income"):
            out["other"].append(entry)
        elif kind == "tds":
            out["tds"].append(entry)
        elif kind == "deduction":
            if e.get("section"):
                out["deductions"].append({**entry, "section": e["section"]})
            else:
                out["unused"].append({**entry, "why": "no section of Chapter VI-A is named"})
        elif kind == "capital_gain":
            term = e.get("term") or _term_from_dates(e, rates)
            if term not in ("short", "long"):
                out["unused"].append({**entry, "why": "it gives neither the term nor the dates to work it out"})
                continue
            listed = e.get("asset_class") == "equity_stt"
            bucket = f"{'equity' if listed else 'other'}_{term}"
            sign = -1 if e.get("direction") == "loss" else 1
            out["gains"][bucket].append({**entry, "year": sign * abs(entry["year"])})
        else:
            out["unused"].append({**entry, "why": "not a kind of figure a plan uses yet"})
    return out


def _term_from_dates(e: dict, rates) -> str | None:
    """Short or long, from when it was bought and when it is to be sold, by
    the engine's own holding periods. None when a date is missing."""
    if rates is None:
        return None
    asset = e.get("asset_class") or "other"
    if asset in rates.ALWAYS_SHORT_TERM:
        return "short"
    bought, sold = _dates_in(str(e.get("acquired_on") or "")), _dates_in(str(e.get("on") or ""))
    if not bought or not sold:
        return None
    from .capital_gains import months_between
    held = months_between(bought[0], sold[0])
    return "long" if held >= rates.HOLDING_PERIOD_MONTHS.get(asset, 24) else "short"


# --------------------------------------------------------------------------
# the expected entries
# --------------------------------------------------------------------------
def with_expected(docs: dict, salary: int = 0, other: int = 0, gains: dict | None = None,
                  deductions: list | None = None, on: date | None = None) -> dict:
    """The schedules read so far, with the expected amounts added as entries
    of their own. The originals are not touched."""
    on = on or date.today()
    out = dict(docs)
    if salary > 0:
        doc = copy.deepcopy(docs.get("salary") or {"data": {"employers": []}})
        doc.setdefault("data", {}).setdefault("employers", []).append({
            "name": PLANNED, "tan": None, "period": "expected",
            "gross_salary": {"amount": int(salary), "basis": PLANNED}})
        out["salary"] = doc
    if other > 0:
        doc = copy.deepcopy(docs.get("other_sources") or {"data": {"items": []}})
        doc.setdefault("data", {}).setdefault("items", []).append({
            "payer": PLANNED, "category": "interest_other", "received_on": on.isoformat(),
            "amount": {"amount": int(other), "basis": PLANNED}})
        out["other_sources"] = doc
    rows = []
    for key, amount in (gains or {}).items():
        if not amount or key not in BUCKETS:
            continue
        b = BUCKETS[key]
        # Any cost will do: the gain is what matters, and a cost well above it
        # keeps the sale value positive for a loss.
        cost = abs(int(amount)) + 1_000_000
        acquired = _months_before(on, b["held_months"])
        rows.append({"asset_class": b["asset_class"], "description": f"{PLANNED}: {b['label']}",
                     "acquired_on": acquired.isoformat(), "transferred_on": on.isoformat(),
                     "full_value": {"amount": cost + int(amount)},
                     "cost_of_acquisition": {"amount": cost}})
    if rows:
        doc = copy.deepcopy(docs.get("capital_gains") or {"data": {"disposals": []}})
        doc.setdefault("data", {}).setdefault("disposals", []).extend(rows)
        out["capital_gains"] = doc
    if deductions:
        doc = copy.deepcopy(docs.get("deductions") or {"data": {"claims": []}})
        doc.setdefault("data", {}).setdefault("claims", []).extend(
            {"section": section, "description": PLANNED, "amount": {"amount": int(amount)}}
            for section, amount in deductions if amount)
        out["deductions"] = doc
    return out


def _months_before(day: date, months: int) -> date:
    y, m = day.year, day.month - months
    while m <= 0:
        m, y = m + 12, y - 1
    return date(y, m, min(day.day, 28))


def _totals(regime: dict) -> dict:
    t = regime["cascade"]["totals"]
    keys = ("gross_total_income", "total_income", "slab_income", "special_total", "tax_at_slab",
            "tax_at_special", "rebate_87a", "surcharge", "cess", "total_tax_liability",
            "relief_90", "net_tax_liability")
    return {k: t.get(k, 0) for k in keys}


def _net(regime: dict) -> int:
    return regime["cascade"]["totals"]["net_tax_liability"]


# --------------------------------------------------------------------------
# the projection
# --------------------------------------------------------------------------
def build(ay: str, docs: dict, plan_doc: dict | None = None, inputs: dict | None = None,
          profile: dict | None = None, today: date | None = None) -> dict:
    """Everything the Planning page shows, worked out from the schedules read
    so far, the planning notes and what was typed on the page."""
    profile = profile or {}
    inputs = inputs or {}
    rates, assumed = planning_rates(ay)
    start, end = fy_bounds(ay)
    today = today or date.today()
    gone = months_gone(today, start, end)
    year_state = "past" if today > end else "future" if today < start else "current"
    # Where an expected sale is dated: today, kept inside the year.
    on = min(max(today, start), end)
    docs = {k: v for k, v in (docs or {}).items() if k != "filed_return"}

    actual = {r: compute.tax_for_regime(docs, rates, r, profile) for r in REGIMES}
    notes = read_notes(plan_doc, start, end, rates)
    split = compute.taxes_paid_split(docs)
    tax_data = ((docs.get("taxes_paid") or {}).get("data") or {})
    salary_tds = sum(_amt(r.get("tds")) for r in tax_data.get("tds_salary", []))

    salary_so_far = actual["new"]["heads"]["salary"]["gross"]
    other_so_far = actual["new"]["heads"]["other_sources"]["gross"]
    tds_so_far = split["tds"] + split["tcs"]
    covered = salary_months(docs.get("salary"), start, end)

    def typed(key):
        value = inputs.get(key)
        return None if value in (None, "") else int(value)

    # Salary for the whole year: as typed, as the notes expect, scaled from
    # the months the documents cover, or as read.
    salary = {"so_far": salary_so_far}
    if typed("salary_year") is not None:
        salary.update(year=typed("salary_year"), source="typed", basis="as you typed it")
    elif notes["salary"]:
        salary.update(year=sum(e["year"] for e in notes["salary"]), source="notes",
                      basis="; ".join(f"{e['description'] or e['kind']}: {e['how']}" for e in notes["salary"]))
    elif covered and covered < 12 and year_state != "past" and salary_so_far:
        salary.update(year=round(salary_so_far * 12 / covered), source="scaled",
                      basis=f"{inr(salary_so_far)} over {covered} months of documents, scaled to 12")
    else:
        salary.update(year=salary_so_far, source="documents",
                      basis="as read" if salary_so_far else "nothing read or expected yet")
    salary["more"] = max(0, salary["year"] - salary_so_far)

    other = {"so_far": other_so_far}
    if typed("other_income_year") is not None:
        other.update(year=typed("other_income_year"), source="typed", basis="as you typed it")
    elif notes["other"]:
        other.update(year=sum(e["year"] for e in notes["other"]), source="notes",
                     basis="; ".join(f"{e['description'] or e['kind']}: {e['how']}" for e in notes["other"]))
    else:
        other.update(year=other_so_far, source="documents",
                     basis="as read" if other_so_far else "nothing read or expected yet")
    other["more"] = max(0, other["year"] - other_so_far)

    typed_gains = inputs.get("gains") or {}
    gains = {}
    for key, b in BUCKETS.items():
        value = typed_gains.get(key)
        if value not in (None, ""):
            gains[key] = {"amount": int(value), "source": "typed", "basis": "as you typed it"}
        elif notes["gains"][key]:
            gains[key] = {"amount": sum(e["year"] for e in notes["gains"][key]), "source": "notes",
                          "basis": "; ".join(e["description"] or e["how"] for e in notes["gains"][key])}
        else:
            gains[key] = {"amount": 0, "source": "none", "basis": ""}
        gains[key]["label"] = b["label"]

    # Tax deducted for the whole year: as typed, as the notes say, or the
    # salary's TDS so far carried on in step with the salary still to come.
    tds = {"so_far": tds_so_far}
    if typed("tds_year") is not None:
        tds.update(year=typed("tds_year"), source="typed", basis="as you typed it")
    elif notes["tds"]:
        tds.update(year=sum(e["year"] for e in notes["tds"]), source="notes",
                   basis="; ".join(e["description"] or e["how"] for e in notes["tds"]))
    elif salary["more"] and salary_tds and salary_so_far:
        more = round(salary_tds * salary["more"] / salary_so_far)
        tds.update(year=tds_so_far + more, source="scaled",
                   basis=f"{inr(salary_tds)} deducted from salary so far, continued for the salary still to come")
    else:
        tds.update(year=tds_so_far, source="documents", basis="as read")
    tds["more"] = max(0, tds["year"] - tds_so_far)

    expected = {"salary": salary["more"], "other": other["more"],
                "gains": {k: v["amount"] for k, v in gains.items()},
                "deductions": [(e["section"], e["year"]) for e in notes["deductions"]], "on": on}
    projected_docs = with_expected(docs, **expected)
    projected = {r: compute.tax_for_regime(projected_docs, rates, r, profile) for r in REGIMES}

    elected = profile.get("regime", "compare")
    lower = "new" if _net(projected["new"]) <= _net(projected["old"]) else "old"
    chosen = elected if elected in REGIMES else lower

    def tax_with(regime="", extra_gains=None, extra_deduction=0, without_gains=False):
        """The chosen regime's tax on the projection with something changed."""
        regime = regime or chosen
        if without_gains:
            d = {k: v for k, v in projected_docs.items() if k != "capital_gains"}
        elif extra_gains:
            merged = dict(expected["gains"])
            for k, v in extra_gains.items():
                merged[k] = merged.get(k, 0) + v
            d = with_expected(docs, **{**expected, "gains": merged})
        else:
            d = projected_docs
        return _net(compute.tax_for_regime(d, rates, regime, profile, extra_deduction=extra_deduction))

    heads = [
        {"key": "salary", "label": "Salary, before deductions", "so_far": salary_so_far,
         "expected": salary["more"], "projected": salary_so_far + salary["more"]},
        {"key": "other", "label": "Interest, dividends and other income", "so_far": other_so_far,
         "expected": other["more"], "projected": other_so_far + other["more"]},
        {"key": "gains", "label": "Capital gains, before set-off and exemption",
         "so_far": _gain_total(actual[chosen]), "expected": sum(expected["gains"].values()),
         "projected": _gain_total(projected[chosen])},
        {"key": "gti", "label": "Gross total income",
         "so_far": _totals(actual[chosen])["gross_total_income"], "expected": None,
         "projected": _totals(projected[chosen])["gross_total_income"]},
        {"key": "total", "label": "Total income, after deductions",
         "so_far": _totals(actual[chosen])["total_income"], "expected": None,
         "projected": _totals(projected[chosen])["total_income"]},
        {"key": "tax", "label": "Tax, after rebate, with surcharge and cess",
         "so_far": _net(actual[chosen]), "expected": None, "projected": _net(projected[chosen])},
    ]

    payload = {
        "ay": ay, "fy": f"{start.year}-{str(start.year + 1)[-2:]}",
        "today": today.isoformat(), "year_state": year_state, "months_gone": gone,
        "year_ends": end.isoformat(),
        "rates": {"assumed": bool(assumed), "fy": rates.FY},
        "salary_months": covered,
        "read_so_far": sorted(k for k in docs if not k.startswith("_")),
        "inputs": {"salary_year": salary, "other_income_year": other, "tds_year": tds, "gains": gains},
        "notes": {"used": [e for k in ("salary", "other", "tds", "deductions") for e in notes[k]]
                          + [e for k in BUCKETS for e in notes["gains"][k]],
                  "unused": notes["unused"],
                  # What the reading could not settle, for a person to answer.
                  "questions": [q for q in ((plan_doc or {}).get("questions") or [])
                                if isinstance(q, str) and q.strip()]},
        "heads": heads,
        "regimes": {r: {"so_far": _totals(actual[r]), "projected": _totals(projected[r]),
                        "marginal_rate": projected[r]["marginal_rate"]} for r in REGIMES},
        "chosen": chosen, "lower": lower, "elected": elected in REGIMES,
        "age_band": profile.get("age_band") or "below_60",
    }
    payload["regime"] = _regime_card(projected, tax_with, chosen, lower, actual)
    payload["gains"] = _gains_card(docs, actual, projected, chosen, rates, tax_with, expected, ay)
    payload["advance_tax"] = _advance_tax(projected[chosen], tds, split, tax_data, start, today,
                                          profile, docs)
    payload["lots"] = foreign_lots(docs.get("foreign_special"), today)
    payload["you"] = {r: _position(projected[r], rates, r, profile) for r in REGIMES}
    payload["hints"] = hints(payload, docs, projected, rates, ay)
    return payload


def _gain_total(regime: dict) -> int:
    return sum(b["gain"] for b in (regime["capital_gains"].get("buckets") or {}).values())


def _position(regime: dict, rates, name: str, profile: dict) -> dict:
    """The projected income on the take-home curve: the curve's tax at it, and
    the projection's own, which differs where income is taxed at special rates."""
    t = regime["cascade"]["totals"]
    at = tax_at(int(t["total_income"]), rates, name, profile.get("age_band") or "below_60")
    return {"income": int(t["total_income"]), "tax": at["tax"], "surcharge": at["surcharge"],
            "cess": at["cess"], "special_total": int(t.get("special_total") or 0),
            "actual_tax": int(t["total_tax_liability"])}


# --------------------------------------------------------------------------
# the cards
# --------------------------------------------------------------------------
def _regime_card(projected: dict, tax_with, chosen: str, lower: str, actual: dict) -> dict:
    new, old = _net(projected["new"]), _net(projected["old"])
    out = {"new": new, "old": old, "lower": lower, "difference": abs(new - old),
           "claimed_old": [line for line in projected["old"]["chapter_via"]["lines"]
                           if line.get("section") != "Planning"],
           "break_even": None, "break_even_possible": None}
    if old > new:
        # How much more the old regime would need in deductions to cost no
        # more than the new: found by asking the engine, so every cap and the
        # rule that deductions never reduce special-rate income are its own.
        ordinary = projected["old"]["cascade"]["totals"]["slab_income"]
        if tax_with("old", extra_deduction=ordinary) > new:
            out["break_even_possible"] = False
        else:
            lo, hi = 0, max(ordinary, 1)
            while hi - lo > 500:
                mid = (lo + hi) // 2
                if tax_with("old", extra_deduction=mid) <= new:
                    hi = mid
                else:
                    lo = mid
            out["break_even"] = int(-(-hi // 1000) * 1000)
            out["break_even_possible"] = True
    return out


def _gains_card(docs, actual, projected, chosen, rates, tax_with, expected, ay) -> dict:
    cg = projected[chosen]["capital_gains"]
    buckets = cg.get("buckets") or {}
    gain_112a = (buckets.get("112A_long") or {}).get("gain", 0)
    exemption = rates.EXEMPTION_112A
    with_gains = _net(projected[chosen])
    tax_on_gains = with_gains - tax_with(without_gains=True)
    lakh = 100_000
    st_saving = with_gains - tax_with(extra_gains={"equity_short": -lakh})
    lt_saving = with_gains - tax_with(extra_gains={"equity_long": -lakh})
    # The exemption's unused part, checked by asking the engine whether a gain
    # of that size really costs nothing.
    unused = max(0, exemption - max(0, gain_112a))
    if unused and tax_with(extra_gains={"equity_long": unused}) > with_gains:
        unused = 0

    def rows(regime):
        return [{"key": key, "section": b["section"], "term": b["term"], "rate": b.get("rate"),
                 "gain": b["gain"], "exemption": b.get("exemption", 0), "count": b.get("rows", 0)}
                for key, b in sorted((regime["capital_gains"].get("buckets") or {}).items())]

    so_far_rows = [r for r in actual[chosen]["capital_gains"].get("rows", [])]
    bf = []
    start_year = int(ay[:4])
    for loss in (((docs.get("setoff_cfl") or {}).get("data") or {}).get("brought_forward") or []):
        origin = str(loss.get("ay_of_origin") or "")
        last = None
        if re.match(r"^\d{4}-\d{2}$", origin):
            y = int(origin[:4]) + CARRY_FORWARD_YEARS
            last = f"{y}-{str(y + 1)[-2:]}"
        bf.append({"kind": loss.get("kind"), "ay_of_origin": origin, "amount": _amt(loss.get("amount")),
                   "last_ay": last, "last_year_now": bool(last and int(last[:4]) == start_year)})
    return {
        "so_far": rows(actual[chosen]), "projected": rows(projected[chosen]),
        "planned": expected["gains"],
        "tax_on_gains": tax_on_gains,
        "exemption_112a": exemption, "gain_112a": gain_112a, "exemption_unused": unused,
        "saving_per_lakh": {"short": st_saving, "long": lt_saving},
        "short_term_foreign": sum(r["gain"] for r in so_far_rows
                                  if r.get("asset_class") == "foreign_shares" and r["term"] == "short"
                                  and r["gain"] > 0),
        "asset_classes": sorted({r.get("asset_class") for r in so_far_rows if r.get("asset_class")}),
        "brought_forward": bf,
    }


def _advance_tax(regime: dict, tds: dict, split: dict, tax_data: dict, start: date,
                 today: date, profile: dict, docs: dict) -> dict:
    """What advance tax the projected year calls for, and how much was paid by
    each date (sections 208, 211 and 234C)."""
    liability = _net(regime)
    credits = tds["year"]
    due = max(0, liability - credits)
    challans = [c for c in tax_data.get("taxes_paid_challans", [])
                if "advance" in str(c.get("kind") or "").lower()]

    def paid_by(day: date | None) -> int:
        total = 0
        for c in challans:
            when = _dates_in(str(c.get("date_of_deposit") or ""))
            if day is None or (when and when[0] <= day):
                total += _amt(c.get("amount"))
        return total

    senior = (profile.get("age_band") or "") in ("senior", "super_senior")
    exempt_207 = senior and not docs.get("books")
    rows, nxt = [], None
    for month, day, share, floor in INSTALMENTS:
        when = date(start.year + (1 if month < 4 else 0), month, day)
        required = round(due * share)
        past = when < today
        paid = paid_by(when) if past else paid_by(None)
        shortfall = max(0, required - paid) if past else 0
        months = 1 if share == 1.0 else 3
        interest = round(shortfall * 0.01 * months) if past and paid < due * floor else 0
        row = {"date": when.isoformat(), "share": share, "required": required, "paid": paid,
               "past": past, "shortfall": shortfall, "interest_234c": interest}
        if not past and nxt is None:
            nxt = {**row, "to_pay": max(0, required - paid)}
        rows.append(row)
    return {"liability": liability, "credits": credits, "due": due,
            "needed": due >= ADVANCE_TAX_FLOOR and not exempt_207, "exempt_207": exempt_207,
            "floor": ADVANCE_TAX_FLOOR, "paid_so_far": paid_by(None), "instalments": rows,
            "next": nxt}


def foreign_lots(fa_doc: dict | None, today: date) -> list[dict]:
    """Foreign shares still held, lot by lot, and when each becomes long-term.

    Schedule FA lists each acquisition (a vest, a purchase) and each sale with
    the lot it came from, so what is left of a lot is its quantity less what
    was sold from it. Shares listed abroad are long-term only once held for
    more than 24 months."""
    data = (fa_doc or {}).get("data") or {}
    out = []
    for entity in ((data.get("schedule_fa") or {}).get("a3_equity_and_debt") or []):
        sold: dict[str, float] = {}
        for s in entity.get("sales") or []:
            lot = s.get("lot_acquired_on")
            if lot:
                sold[lot] = sold.get(lot, 0) + float(s.get("quantity") or 0)
        for a in entity.get("acquisitions") or []:
            dates = _dates_in(str(a.get("on") or ""))
            quantity = float(a.get("quantity") or 0)
            if not dates or quantity <= 0:
                continue
            left = quantity - sold.get(a.get("on"), 0)
            if left <= 0:
                continue
            acquired = dates[0]
            try:
                turns = acquired.replace(year=acquired.year + 2)
            except ValueError:                  # 29 February
                turns = acquired.replace(year=acquired.year + 2, day=28)
            days = (turns - today).days
            out.append({"entity": entity.get("entity_name", ""), "acquired_on": acquired.isoformat(),
                        "quantity": left, "long_term_after": turns.isoformat(),
                        "status": "long" if days < 0 else "soon" if days <= 183 else "later",
                        "days": days})
    return sorted(out, key=lambda lot: lot["long_term_after"])


# --------------------------------------------------------------------------
# hints
# --------------------------------------------------------------------------
def inr(n: int) -> str:
    """Rupees the Indian way, as the page writes them: Rs 1,18,630, Rs 50,00,000."""
    sign, digits = ("-" if n < 0 else ""), str(abs(int(n)))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        digits = ",".join(([head] if head else []) + groups) + "," + tail
    return f"{sign}₹{digits}"


def hints(p: dict, docs: dict, projected: dict, rates, ay: str) -> list[dict]:
    """Things worth knowing, chosen by what is in this return.

    Each says why it is shown. A hint about acting before 31 March is shown
    only while the year is still running."""
    out = []
    current = p["year_state"] != "past"
    chosen = p["chosen"]
    marginal = p["regimes"][chosen]["marginal_rate"]
    g = p["gains"]
    classes = set(g["asset_classes"])
    fa = ((docs.get("foreign_special") or {}).get("data") or {})
    holds_foreign = bool(p["lots"]) or "foreign_shares" in classes or bool(
        (fa.get("schedule_fa") or {}).get("a3_equity_and_debt"))

    def add(hint_id, kind, title, text, card=None):
        if kind == "act" and not current:
            return
        out.append({"id": hint_id, "kind": kind, "title": title, "text": text, "card": card})

    if p["rates"]["assumed"]:
        add("rates", "know", f"FY {p['fy']} rates are not built in yet",
            f"This plan uses the FY {p['rates']['fy']} rates, slabs and thresholds. If the Finance Act "
            f"for FY {p['fy']} changed them, the figures here will be off by that much.")

    nxt = p["advance_tax"]["next"]
    if p["advance_tax"]["needed"] and nxt and nxt["to_pay"] > 0:
        add("advance", "act", f"{inr(nxt['to_pay'])} of advance tax is due by {_long_date(nxt['date'])}",
            "On the projected figures, tax not covered by TDS needs paying in instalments. "
            "Interest under section 234C runs on any shortfall.", "advance")

    r = p["regime"]
    if r["difference"] and (p["elected"] and r["lower"] != chosen):
        add("regime", "act", f"The {r['lower']} regime would cost {inr(r['difference'])} less",
            f"On the projected figures your return is set to the {chosen} regime, which costs more. "
            "The choice is made when the return is filed.", "regime")

    if holds_foreign:
        text = ("Shares listed abroad, such as RSUs from a US employer, are not listed in India, so "
                "they become long-term only when held for more than 24 months, not 12 as for Indian "
                "listed shares. Sold sooner, the gain is taxed at your slab rate"
                + (f", about {marginal * 100:.1f}% at your projected income with surcharge and cess"
                   if marginal else "")
                + "; held longer, at 12.5% plus surcharge and cess.")
        if g["short_term_foreign"]:
            text += f" {inr(g['short_term_foreign'])} of this year's foreign-share gains so far are short-term."
        add("foreign-24", "know", "Foreign shares are long-term only after 24 months", text, "gains")
        soon = [lot for lot in p["lots"] if lot["status"] == "soon"]
        if soon:
            add("lots-soon", "act",
                f"{len(soon)} lot{'s' if len(soon) != 1 else ''} of foreign shares "
                f"turn{'' if len(soon) != 1 else 's'} long-term within six months",
                "Selling them after that date rather than before moves the gain from your slab rate "
                "to 12.5%. The dates are on the Capital gains card.", "gains")

    equity = "equity_stt" in classes or g["gain_112a"]
    if equity and g["exemption_unused"]:
        add("harvest-112a", "act", f"{inr(g['exemption_unused'])} of equity gains can still be booked tax-free",
            f"Long-term gains on listed shares and equity funds are exempt up to {inr(g['exemption_112a'])} "
            "a year. Selling holdings kept for more than 12 months with up to that much gain, and buying "
            "them back, costs no tax this year and raises their cost for later.", "gains")

    s, l = g["saving_per_lakh"]["short"], g["saving_per_lakh"]["long"]
    if s or l:
        add("harvest-loss", "act", "Booking a loss before 31 March saves tax",
            f"At this year's projected figures, each {inr(100_000)} of short-term loss saves about {inr(s)}"
            + (f", and each {inr(100_000)} of long-term loss about {inr(l)}. " if l else
               "; a long-term loss would save nothing, because your long-term gains are already "
               "untaxed or absorbed. ")
            + "A short-term loss can be set against any capital gain; a long-term loss only against "
              "long-term gains.", "gains")

    expiring = [b for b in g["brought_forward"] if b["last_year_now"] and b["amount"]]
    if expiring:
        total = sum(b["amount"] for b in expiring)
        add("expiring", "act", f"{inr(total)} of losses brought forward can be used this year for the last time",
            "A loss is carried forward for eight years. Gains booked this year use it up; after this "
            "year it is gone.", "gains")
    if g["brought_forward"] or any(b["gain"] < 0 for b in g["projected"]):
        add("file-on-time", "know", "A capital loss carries forward only if the return is on time",
            "To carry a capital loss into later years, the return for the year of the loss has to be "
            "filed by the due date under section 139(1).", "gains")

    if classes & {"debt_mf_specified", "debt_mf_other"}:
        add("debt-funds", "know", "Debt funds bought since April 2023 are taxed at your slab rate",
            "Units of a debt fund bought on or after 1 April 2023 are short-term however long they are "
            "held (section 50AA). Units bought before then become long-term after 24 months and, since "
            "23 July 2024, are taxed at 12.5% without indexation.")

    if holds_foreign:
        add("schedule-fa", "know", "Every foreign holding goes in Schedule FA",
            f"Schedule FA covers calendar year {int(ay[:4]) - 1}: every foreign account and share held "
            "at any time in it, including shares sold during it. Leaving one out can draw a penalty of "
            "Rs 10 lakh under the Black Money Act.")

    foreign_tax = any(_amt(i.get("tax_withheld_outside_india"))
                      for i in (((docs.get("other_sources") or {}).get("data") or {}).get("items") or []))
    if foreign_tax or projected[chosen]["cascade"]["totals"].get("relief_90"):
        add("form-67", "know", "Tax paid abroad needs Form 67",
            "Tax withheld abroad, on US dividends for instance, is credited against Indian tax only if "
            "Form 67 is filed: at the latest by the end of the assessment year, and most simply "
            "before the return.")

    you = p["you"][chosen]
    zones = _zones(rates, chosen, p["age_band"])
    for z in zones:
        if z["kind"] != "surcharge":
            continue
        gap = z["from"] - you["income"]
        if 0 < gap <= 300_000:
            add("threshold", "act", f"Your projected income is {inr(gap)} below {inr(z['from'])}",
                f"A {z['rate'] * 100:g}% surcharge begins there, and just past it marginal relief takes "
                f"every extra rupee as tax until {inr(z['to'])}. Income that can wait for next year, "
                "or a loss booked now, keeps you below it.", "take-home")
        elif z["from"] < you["income"] < z["keeps_less_until"]:
            add("threshold", "act", f"Your projected income is just past {inr(z['from'])}",
                f"Up to {inr(z['keeps_less_until'])} you take home less than you would at "
                f"{inr(z['from'])}: the surcharge that begins there costs more than the income above "
                "it. Deferring income or booking a loss could bring you back under.", "take-home")

    reb = rates.REBATE_87A_NEW if chosen == "new" else rates.REBATE_87A_OLD
    special_tax = projected[chosen]["cascade"]["totals"].get("tax_at_special") or 0
    if you["income"] <= reb["income_ceiling"] and special_tax:
        add("rebate-cg", "know", "The rebate does not reach tax on capital gains at special rates",
            f"Your projected income is within the {inr(reb['income_ceiling'])} rebate limit, but the "
            f"rebate cannot reduce tax on gains taxed at special rates: {inr(special_tax)} of it remains.")

    claims = (((docs.get("deductions") or {}).get("data") or {}).get("claims") or [])
    if chosen == "new" and p["heads"][0]["projected"] and not any(c.get("section") == "80CCD(2)" for c in claims):
        add("nps", "know", "Your employer's NPS contribution is deductible in the new regime",
            "Under section 80CCD(2), what your employer pays into NPS for you is deductible up to 14% of "
            "basic pay and dearness allowance, even in the new regime"
            + (f": each rupee moved there saves about {marginal * 100:.1f}% at your projected income"
               if marginal else "")
            + ". Employer contributions to NPS, provident fund and superannuation above Rs 7.5 lakh a "
              "year in all are taxed as a perquisite.", "regime")

    if holds_foreign and equity and current:
        add("sequence", "know", "Book the gains you cannot time first, and harvest last",
            "Sell what you must (vested foreign shares, say) earlier in the year, then use the last "
            "quarter to book losses or use the equity exemption against those gains, once the year's "
            "gains are known. Tax on a capital gain that arises after an advance-tax date can be paid "
            "with the next instalment without interest.", "gains")
    return out


def _zones(rates, regime: str, age_band: str) -> list[dict]:
    from .planning import relief_zones
    return relief_zones(rates, regime, age_band, top=50_000_000)


def _long_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B')} {d.year}"
