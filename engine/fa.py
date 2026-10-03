"""Schedule FA, sections A1 to A3: the rupee columns worked out from dated facts.

Schedule FA is a disclosure for the CALENDAR year, and every column is in
rupees at the State Bank of India telegraphic transfer buying rate on the date
of that figure itself -- the day of the peak, 31 December for the closing
balance, the day of acquisition for the initial value. That is not Rule 115,
which fixes income at the last day of the preceding month.

Where the form leaves a choice open, the choice made here stands on the form
itself or on published practice, and is stated on the row it affects:

  * A3 gives each row ONE date of acquiring the interest and ONE initial
    value, so each acquisition is its own row. Sixteen vests are sixteen rows;
    merging them would need a date and a cost that belong to no transaction;
  * an account row (A1, A2) lists every kind of amount credited -- the form's
    own list of natures is interest, dividend, proceeds from sale or
    redemption, and other income;
  * the peak is the highest value the documents state for the year: statement
    dates, the day a lot was acquired, the day it was sold. A true peak needs
    a price for every day, so this can understate, and the row says so;
  * a peak can never be below the closing value, so the closing value is the
    floor;
  * a dividend is shared between lots by the shares each held on the day it
    was paid, and a sale is taken from the lot the document names, or
    first-in, first-out where it names none.

A document that already states a finished rupee figure -- a broker's own
Schedule FA report -- is taken as stated. A return that was already filed is
never an input here; it is not even reachable from this module.
"""

from __future__ import annotations

import datetime as dt

from . import fx

RULE = "Schedule FA, rate on the date itself"
ACCOUNT_SECTIONS = ("a1_depository_accounts", "a2_custodial_accounts")


def _d(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class _Converter:
    """Rupees for a stated amount on a date, remembering what it could not do."""

    def __init__(self, rates: dict, year: int) -> None:
        self.rates, self.year = rates, year
        self.needed: dict[tuple[str, str], dict] = {}

    def in_year(self, on) -> bool:
        day = _d(on)
        return bool(day and day.year == self.year)

    def rupees(self, node, on) -> tuple[int | None, dict | None]:
        if node is None:
            return None, None
        if not isinstance(node, dict):
            return int(node or 0), None
        if "amount" in node:                       # already in rupees, as stated
            return int(node["amount"] or 0), None
        if not fx.is_foreign(node):
            return None, None
        if not float(node["amount_foreign"]):
            return 0, None
        day = _d(on)
        currency = str(node["currency"]).upper()
        if day is None:
            return None, {"why": f"{currency} amount with no date to fix the rate"}
        value, why = fx.convert(node, day, self.rates, RULE)
        if value is None:
            self.needed[(currency, day.isoformat())] = {"currency": currency,
                                                       "date": day.isoformat()}
            return None, {"why": why}
        return value, fx.working(node, day, self.rates, RULE)

    def total(self, entries, label: str, steps: list) -> tuple[int, bool]:
        """Sum of dated amounts in the year; False when any could not convert."""
        total, complete = 0, True
        for e in entries or []:
            if not self.in_year(e.get("on")):
                continue
            value, work = self.rupees(e.get("amount"), e.get("on"))
            if value is None:
                complete = False
                steps.append({"label": label, "on": e.get("on"), "rupees": None,
                              "why": (work or {}).get("why")})
                continue
            total += value
            steps.append({"label": e.get("nature") or label, "on": e.get("on"),
                          "rupees": value, "working": work})
        return total, complete


def _peak_and_closing(conv: _Converter, item: dict, steps: list, notes: list
                      ) -> tuple[int | None, int | None]:
    year_end = dt.date(conv.year, 12, 31)
    values = []
    for v in item.get("valuations") or []:
        if not conv.in_year(v.get("on")):
            continue
        rupees, work = conv.rupees(v.get("amount"), v.get("on"))
        steps.append({"label": "Value stated", "on": v.get("on"), "rupees": rupees,
                      "working": work, "why": (work or {}).get("why") if rupees is None else None})
        if rupees is not None:
            values.append((rupees, _d(v.get("on"))))

    closing, _ = conv.rupees(item.get("closing_value"), year_end.isoformat())
    if closing is None:
        at_end = [r for r, day in values if day == year_end]
        closing = at_end[0] if at_end else None
        if closing is None and (item.get("closing_value") or values):
            notes.append("No value is stated for 31 December, so the closing balance "
                         "cannot be fixed.")

    peak, _ = conv.rupees(item.get("peak_value"), None)
    stated_peak = peak is not None
    if peak is None and values:
        peak = max(r for r, _ in values)
        notes.append(f"Peak is the highest of {len(values)} value(s) the statements state "
                     f"for the year. The true peak may fall between statement dates.")
    if closing is not None and (peak is None or peak < closing):
        if peak is not None and stated_peak:
            notes.append("The stated peak was below the closing balance; the closing "
                         "balance is used, since a peak cannot be lower.")
        peak = closing
    return peak, closing


def _account(conv: _Converter, item: dict) -> dict:
    steps, notes = [], []
    peak, closing = _peak_and_closing(conv, item, steps, notes)

    by_nature: dict[str, int] = {}
    complete = True
    for c in item.get("credits") or []:
        if not conv.in_year(c.get("on")):
            continue
        nature = c.get("nature") or "Other income"
        value, work = conv.rupees(c.get("amount"), c.get("on"))
        steps.append({"label": nature, "on": c.get("on"), "rupees": value, "working": work,
                      "why": (work or {}).get("why") if value is None else None})
        if value is None:
            complete = False
            continue
        by_nature[nature] = by_nature.get(nature, 0) + value
    if not (item.get("credits") or []):
        stated, work = conv.rupees(item.get("gross_credited"),
                                   dt.date(conv.year, 12, 31).isoformat())
        if stated:
            by_nature[item.get("nature_of_amount") or "Other income"] = stated
            if work:
                notes.append("The amount credited is stated as one undated total, so it is "
                             "converted at the 31 December rate rather than credit by credit.")
    if not complete:
        notes.append("Some credits could not be converted; the amounts shown leave them out.")
    return {
        "country_code": item.get("country_code"), "country": item.get("country"),
        "institution_name": item.get("institution_name"),
        "institution_address": item.get("institution_address"), "zip_code": item.get("zip_code"),
        "account_number": item.get("account_number"), "status": item.get("status"),
        "opened_on": item.get("opened_on"),
        "peak_value": peak, "closing_value": closing,
        "credited": [{"nature": k, "amount": v} for k, v in by_nature.items()],
        "nature_of_amount": ", ".join(by_nature) or None,
        "gross_credited": sum(by_nature.values()),
        "steps": steps, "notes": notes,
    }


def _entity_fields(item: dict) -> dict:
    return {"country_code": item.get("country_code"), "country": item.get("country"),
            "entity_name": item.get("entity_name"), "entity_address": item.get("entity_address"),
            "zip_code": item.get("zip_code"), "nature_of_entity": item.get("nature_of_entity")}


def _single_row(conv: _Converter, item: dict) -> dict:
    """A holding the documents give as one figure -- one purchase, or a
    broker's own finished Schedule FA line."""
    steps, notes = [], []
    initial, _ = conv.rupees(item.get("initial_value"), item.get("acquired_on"))
    lots = item.get("acquisitions") or []
    if initial is None and lots:
        initial = 0
        for lot in lots:
            value, work = conv.rupees(lot.get("amount"), lot.get("on"))
            steps.append({"label": "Acquired", "on": lot.get("on"), "rupees": value,
                          "working": work})
            initial += value or 0
    peak, closing = _peak_and_closing(conv, item, steps, notes)
    year_end = dt.date(conv.year, 12, 31).isoformat()
    credited, _ = conv.total(item.get("credits"), "Dividend", steps)
    if not (item.get("credits") or []):
        credited = conv.rupees(item.get("gross_amount_credited"), year_end)[0] or 0
    proceeds, _ = conv.total(item.get("sales"), "Sale", steps)
    if not (item.get("sales") or []):
        proceeds = conv.rupees(item.get("gross_proceeds_on_sale"), year_end)[0] or 0
    first = min([d for d in [_d(item.get("acquired_on"))] + [_d(l.get("on")) for l in lots] if d],
                default=None)
    return {"acquired_on": first.isoformat() if first else None, "quantity": None,
            "initial_value": initial, "peak_value": peak, "closing_value": closing,
            "gross_amount_credited": credited, "gross_proceeds_on_sale": proceeds,
            "steps": steps, "notes": notes}


def _lot_rows(conv: _Converter, item: dict, notes: list) -> list[dict] | None:
    """One row per acquisition, or None when the lots cannot be told apart."""
    raw = item.get("acquisitions") or []
    if len(raw) < 2:
        return None
    lots = []
    for a in raw:
        day, qty = _d(a.get("on")), a.get("quantity")
        if day is None or not qty:
            notes.append("A lot has no date or no quantity, so the holding cannot be split "
                         "into its acquisitions and is shown as one row.")
            return None
        lots.append({"on": day, "qty": float(qty), "cost": a.get("amount"), "sold": []})
    lots.sort(key=lambda l: l["on"])

    year_start, year_end = dt.date(conv.year, 1, 1), dt.date(conv.year, 12, 31)

    def held(lot, day) -> float:
        if lot["on"] > day:
            return 0.0
        return lot["qty"] - sum(x["qty"] for x in lot["sold"] if x["on"] <= day)

    # Sales: from the lot the document names, else first-in, first-out.
    for sale in sorted(item.get("sales") or [], key=lambda x: str(x.get("on"))):
        day, qty = _d(sale.get("on")), float(sale.get("quantity") or 0)
        rupees, work = conv.rupees(sale.get("amount"), sale.get("on"))
        if day is None or not qty:
            notes.append(f"A sale on {sale.get('on')} states no quantity, so it could not be "
                         f"set against any lot and is left out of the rows below.")
            continue
        named = _d(sale.get("lot_acquired_on"))
        pool = [l for l in lots if l["on"] <= day]
        pool.sort(key=lambda l: (0 if named and l["on"] == named else 1, l["on"]))
        left = qty
        for lot in pool:
            take = min(left, held(lot, day))
            if take <= 0:
                continue
            lot["sold"].append({"on": day, "qty": take, "work": work,
                                "rupees": None if rupees is None else rupees * take / qty,
                                "price": None if rupees is None else rupees / qty})
            left -= take
            if left <= 1e-9:
                break
        if left > 1e-9:
            notes.append(f"{left:g} of the shares sold on {day} match no lot listed here.")

    # A price per share on each date the documents value the holding.
    prices = []
    for v in item.get("valuations") or []:
        day = _d(v.get("on"))
        if day is None or day.year != conv.year:
            continue
        rupees, _w = conv.rupees(v.get("amount"), v.get("on"))
        total = sum(held(l, day) for l in lots)
        if rupees is not None and total > 0:
            prices.append((day, rupees / total))

    credits = []
    for c in item.get("credits") or []:
        day = _d(c.get("on"))
        if day is None or day.year != conv.year:
            continue
        rupees, work = conv.rupees(c.get("amount"), c.get("on"))
        credits.append((day, rupees, work, sum(held(l, day) for l in lots)))

    rows = []
    for lot in lots:
        if lot["on"] > year_end or (lot["on"] < year_start
                                    and held(lot, year_start - dt.timedelta(days=1)) <= 0):
            continue                                   # not held at any time in the year
        steps = []
        initial, work = conv.rupees(lot["cost"], lot["on"].isoformat())
        steps.append({"label": f"Acquired {lot['qty']:g}", "on": lot["on"].isoformat(),
                      "rupees": initial, "working": work,
                      "why": (work or {}).get("why") if initial is None else None})

        stated = []
        if lot["on"].year == conv.year and initial is not None:
            stated.append(initial)
        for day, price in prices:
            have = held(lot, day)
            if have > 0:
                value = int(round(have * price))
                stated.append(value)
                steps.append({"label": f"Value of {have:g} held", "on": day.isoformat(),
                              "rupees": value})
        proceeds = 0
        for x in lot["sold"]:
            if x["on"].year != conv.year or x["rupees"] is None:
                continue
            before = held(lot, x["on"]) + x["qty"]
            stated.append(int(round(before * x["price"])))
            proceeds += x["rupees"]
            steps.append({"label": f"Sold {x['qty']:g}", "on": x["on"].isoformat(),
                          "rupees": int(round(x["rupees"])), "working": None})

        at_end = held(lot, year_end)
        end_price = next((p for d, p in prices if d == year_end), None)
        closing = 0 if at_end <= 0 else (int(round(at_end * end_price))
                                         if end_price is not None else None)
        peak = max(stated + [closing or 0]) if (stated or closing is not None) else None

        dividends = 0
        for day, rupees, cwork, total in credits:
            have = held(lot, day)
            if rupees is None or total <= 0 or have <= 0:
                continue
            share = rupees * have / total
            dividends += share
            steps.append({"label": f"Dividend on {have:g} of {total:g} shares",
                          "on": day.isoformat(), "rupees": int(round(share))})

        rows.append({"acquired_on": lot["on"].isoformat(), "quantity": lot["qty"],
                     "initial_value": initial, "peak_value": peak, "closing_value": closing,
                     "gross_amount_credited": int(round(dividends)),
                     "gross_proceeds_on_sale": int(round(proceeds)),
                     "steps": steps, "notes": []})
    if closing_missing := [r for r in rows if r["closing_value"] is None]:
        notes.append(f"No value is stated for 31 December, so {len(closing_missing)} lot(s) "
                     f"have no closing value.")
    notes.append("Peak is the highest value the documents state for each lot: on statement "
                 "dates, on the day it was acquired, on the day it was sold. The true peak "
                 "may fall between those dates.")
    return rows


def _holding(conv: _Converter, item: dict) -> dict:
    notes: list[str] = []
    rows = _lot_rows(conv, item, notes)
    if rows is None:
        single = _single_row(conv, item)
        notes.extend(single.pop("notes"))
        rows = [{**single, "notes": []}]

    def total(key):
        values = [r[key] for r in rows if r[key] is not None]
        return sum(values) if values else None

    return {**_entity_fields(item), "lots": rows, "notes": notes,
            "totals": {"initial_value": total("initial_value"),
                       "closing_value": total("closing_value"),
                       "gross_amount_credited": total("gross_amount_credited"),
                       "gross_proceeds_on_sale": total("gross_proceeds_on_sale")}}


def build(doc: dict | None, rates: dict) -> dict | None:
    """Sections A1 to A3 with their rupee columns, or None when there are none."""
    data = (doc or {}).get("data") or {}
    fa = data.get("schedule_fa") or {}
    if not any(fa.get(k) for k in (*ACCOUNT_SECTIONS, "a3_equity_and_debt")):
        return None
    try:
        year = int(str(data.get("calendar_year"))[:4])
    except (TypeError, ValueError):
        return {"error": "The calendar year Schedule FA covers is not stated, so no rate "
                         "date can be fixed. Re-run the Foreign Income tab.",
                "rates_needed": []}

    conv = _Converter(rates, year)
    out = {key: [_account(conv, item) for item in fa.get(key) or []]
           for key in ACCOUNT_SECTIONS}
    out["a3_equity_and_debt"] = [_holding(conv, item) for item in fa.get("a3_equity_and_debt") or []]
    out["calendar_year"] = year
    out["rates_needed"] = list(conv.needed.values())
    out["verify"] = ("Each figure is converted at the SBI telegraphic transfer buying rate on "
                     "its own date. One row per acquisition. The peak is the highest value "
                     "the documents state, not a daily peak.")
    return out
