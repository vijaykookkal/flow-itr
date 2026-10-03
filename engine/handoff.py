"""What gets typed into the utility, schedule by schedule.

This tool files nothing. The last thing it does is hand its figures to a person
who enters them somewhere else, and that copying is where a correct computation
still goes wrong: a line skipped, two digits swapped, a deduction entered with
the sign this tool happens to show it in.

So each schedule is laid out here once more, as a sheet to copy from: the line
the form prints, its wording, and the amount in the form the utility expects.
Every row has a key, so the page can remember which rows have been entered and
say so when a figure changes afterwards -- a row marked done whose amount has
since moved is the most useful warning this screen can give.

Nothing is computed here. Each sheet restates figures another module already
produced, which is the point: there is one place a number comes from, and this
is only a second way of reading it.
"""

from __future__ import annotations

import re


def _n(node) -> int:
    """A money object's rupees, or a plain number, or nil."""
    if isinstance(node, dict):
        return int(node.get("amount") or 0)
    try:
        return int(node or 0)
    except (TypeError, ValueError):
        return 0


def _row(key, item, label, values, kind=""):
    return {"key": str(key), "item": str(item or ""), "label": str(label or ""),
            "values": list(values), "kind": kind}


def _sheet(sheet_id, title, tab, columns, rows, note=""):
    return {"id": sheet_id, "title": title, "tab": tab, "columns": columns,
            "rows": rows, "note": note}


AMOUNT = [{"t": "Amount", "num": True}]

# A line such as 3ii or 12a sits under the one above it; the form indents it.
SUB_LINE = re.compile(r"^\d+[a-z]", re.I)
TOTAL_LINE = re.compile(
    r"^(Total income|Gross Total income|Gross tax liability|Net tax liability|"
    r"Aggregate liability|Amount payable|Refund|Total Taxes Paid|Total of Head Wise Income)",
    re.I)


def _part_b(stages: list[dict], code: str) -> list[dict]:
    rows = []
    for stage in stages or []:
        table = stage.get("table") or {}
        if stage.get("code") != code or table.get("columns", [None])[0] != "Line":
            continue
        for line in table.get("rows") or []:
            if len(line) < 3 or not isinstance(line[2], (int, float)):
                continue
            item, label = str(line[0]), str(line[1])
            # The form takes no negative entry on these two parts: a loss is
            # "enter nil" and a deduction is the amount being deducted. This
            # tool shows a deduction as negative while it is subtracting it,
            # which is right on screen and wrong in the utility.
            kind = "total" if TOTAL_LINE.match(label) else "sub" if SUB_LINE.match(item) else ""
            rows.append(_row(item, item, label, [abs(int(line[2]))], kind))
    return rows


def _salary(doc: dict | None, head: dict | None) -> list[dict]:
    data = (doc or {}).get("data") or {}
    employers = data.get("employers") or []
    if not employers:
        return []
    rows = []
    many = len(employers) > 1
    for i, e in enumerate(employers):
        tag = f"e{i}:"
        if many:
            rows.append(_row(f"{tag}name", "", e.get("name") or f"Employer {i + 1}", [None], "head"))
        rows += [
            _row(f"{tag}1a", "1a", "Salary as per section 17(1)", [_n(e.get("salary_17_1"))], "sub"),
            _row(f"{tag}1b", "1b", "Value of perquisites as per section 17(2)",
                 [_n(e.get("perquisites_17_2"))], "sub"),
            _row(f"{tag}1c", "1c", "Profit in lieu of salary as per section 17(3)",
                 [_n(e.get("profits_in_lieu_17_3"))], "sub"),
            _row(f"{tag}1", "1", "Gross Salary (1a + 1b + 1c)", [_n(e.get("gross_salary"))], "total"),
        ]
    # The rest is the head as computed, because which exemptions and section 16
    # deductions survive depends on the regime, and only the computation knows
    # which regime is in use.
    d16 = data.get("deductions_16") or {}
    h = head or {}
    gross = h.get("gross", sum(_n(e.get("gross_salary")) for e in employers))
    exempt = h.get("exempt", 0)
    other = h.get("other_16", 0)
    entertainment = _n(d16.get("entertainment_16_ii")) if other else 0
    professional = _n(d16.get("professional_tax_16_iii")) if other else 0
    rows += [
        _row("2", "2", "Less: allowances to the extent exempt under section 10", [exempt]),
        _row("3", "3", "Net Salary (1 - 2)", [gross - exempt], "total"),
        _row("4a", "4a", "Standard deduction under section 16(ia)",
             [h.get("standard_deduction", _n(d16.get("standard_16_ia")))], "sub"),
        _row("4b", "4b", "Entertainment allowance under section 16(ii)", [entertainment], "sub"),
        _row("4c", "4c", "Tax on employment under section 16(iii)", [professional], "sub"),
        _row("5", "5", "Total deductions under section 16 (4a + 4b + 4c)",
             [h.get("deductions_16", 0)]),
        _row("6", "6", "Income chargeable under the head ‘Salaries’ (3 - 5)",
             [h.get("net", _n(data.get("income_chargeable")))], "total"),
    ]
    return rows


def _other_sources(form: dict | None) -> list[dict]:
    if not form or not (form.get("normal") or form.get("special")):
        return []
    rows = [_row(line["item"], line["item"], line["label"], [line["amount"]], "sub")
            for line in form.get("normal") or []]
    rows.append(_row("1", "1", "Gross income chargeable at normal rates",
                     [form.get("gross_normal", 0)], "total"))
    rows += [_row(line["item"], line["item"], line["label"], [line["amount"]])
             for line in form.get("special") or []]
    rows.append(_row("3", "3", "Less: deductions under section 57", [form.get("deductions_57", 0)]))
    rows.append(_row("6", "6", "Net income from other sources", [form.get("net", 0)], "total"))
    return rows


def _capital_gains(form: dict | None) -> list[dict]:
    if not form:
        return []

    def line(r, kind=""):
        return _row(r["item"], r["item"], r["label"],
                    [r.get("sell_value", 0), r.get("buy_value", 0),
                     r.get("expenses", 0), r.get("gain", 0)], kind)

    rows = []
    for part, total in (("short_term", "A10"), ("long_term", "B13")):
        for r in form.get(part) or []:
            if r.get("rows") or r.get("item") == total:
                rows.append(line(r, "total" if r.get("item") == total else ""))
    if form.get("total"):
        rows.append(line(form["total"], "total"))
    return rows if any(any(r["values"]) for r in rows) else []


def _taxes_paid(doc: dict | None) -> list[dict]:
    """Schedules TDS1, TDS2, TCS and IT: rows of particulars, not lines."""
    data = (doc or {}).get("data") or {}
    sheets = []

    salary = data.get("tds_salary") or []
    if salary:
        sheets.append(_sheet(
            "schedule_tds1", "Schedule TDS1: tax deducted on salary", "taxes_paid",
            [{"t": "TAN of employer"}, {"t": "Income chargeable", "num": True},
             {"t": "Tax deducted", "num": True}],
            [_row(f"{i}:{r.get('tan') or ''}", i + 1, r.get("deductor"),
                  [r.get("tan") or "", _n(r.get("income_paid")), _n(r.get("tds"))])
             for i, r in enumerate(salary)]))

    other = data.get("tds_other") or []
    if other:
        sheets.append(_sheet(
            "schedule_tds2", "Schedule TDS2: tax deducted on other income", "taxes_paid",
            [{"t": "TAN or PAN"}, {"t": "Section"}, {"t": "Gross amount", "num": True},
             {"t": "Tax deducted", "num": True}],
            [_row(f"{i}:{r.get('tan_or_pan') or ''}", i + 1, r.get("deductor"),
                  [r.get("tan_or_pan") or "", r.get("section") or "",
                   _n(r.get("gross_amount")), _n(r.get("tds"))])
             for i, r in enumerate(other)]))

    tcs = data.get("tcs") or []
    if tcs:
        sheets.append(_sheet(
            "schedule_tcs", "Schedule TCS: tax collected at source", "taxes_paid",
            [{"t": "TAN of collector"}, {"t": "Tax collected", "num": True}],
            [_row(f"{i}:{r.get('tan') or ''}", i + 1, r.get("collector") or r.get("deductor"),
                  [r.get("tan") or "", _n(r.get("tcs"))])
             for i, r in enumerate(tcs)]))

    challans = data.get("taxes_paid_challans") or []
    if challans:
        sheets.append(_sheet(
            "schedule_it", "Schedule IT: advance tax and self-assessment tax", "taxes_paid",
            [{"t": "BSR code"}, {"t": "Date of deposit"}, {"t": "Challan serial no."},
             {"t": "Amount", "num": True}],
            [_row(f"{c.get('bsr_code')}:{c.get('date_of_deposit')}:{c.get('challan_no')}", i + 1,
                  str(c.get("kind") or "").replace("_", " ").capitalize(),
                  [c.get("bsr_code") or "", c.get("date_of_deposit") or "",
                   c.get("challan_no") or "", _n(c.get("amount"))])
             for i, c in enumerate(challans)]))
    return sheets


def _foreign(foreign: dict | None) -> list[dict]:
    sheets = []
    foreign = foreign or {}

    rows = []
    for i, country in enumerate(foreign.get("schedule_fsi") or []):
        place = f"{country.get('country_code')} - {country.get('country')}"
        rows.append(_row(f"{i}:country", i + 1, place, [None, None, None, None, ""], "head"))
        for h in country.get("heads") or []:
            values = [_n(h.get("income_outside_india")), _n(h.get("tax_paid_outside_india")),
                      _n(h.get("tax_payable_in_india")), _n(h.get("relief_available"))]
            rows.append(_row(f"{i}:{h.get('item')}", h.get("item"), h.get("head"),
                             values + [h.get("dtaa_article") or ""], "sub"))
    if rows:
        sheets.append(_sheet(
            "schedule_fsi", "Schedule FSI: income from outside India and tax relief",
            "foreign_special",
            [{"t": "(c) Income from outside India", "num": True},
             {"t": "(d) Tax paid outside India", "num": True},
             {"t": "(e) Tax payable in India", "num": True},
             {"t": "(f) Relief available", "num": True}, {"t": "Article"}],
            rows, "Column (f) is the lower of (d) and (e)."))

    tr = foreign.get("schedule_tr") or {}
    countries = tr.get("countries") or []
    if countries:
        rows = [_row(f"{i}:{c.get('country_code')}", i + 1,
                     f"{c.get('country_code')} - {c.get('country')}",
                     [_n(c.get("total_taxes_paid_outside")), _n(c.get("total_relief_available")),
                      f"Section {c.get('relief_section')}" if c.get("relief_section") else ""])
                for i, c in enumerate(countries)]
        rows.append(_row("2", "2", "Total tax relief available where DTAA is applicable "
                                   "(section 90 / 90A)", [None, _n(tr.get("treaty_relief")), ""]))
        rows.append(_row("3", "3", "Total tax relief available where DTAA is not applicable "
                                   "(section 91)", [None, _n(tr.get("non_treaty_relief")), ""]))
        sheets.append(_sheet(
            "schedule_tr", "Schedule TR: tax relief claimed for taxes paid outside India",
            "foreign_special",
            [{"t": "(c) Taxes paid outside India", "num": True},
             {"t": "(d) Relief available", "num": True}, {"t": "(e) Relief claimed under"}],
            rows, "Relief stands only if Form 67 was filed before the return."))
    return sheets


def _foreign_assets(fa: dict | None) -> list[dict]:
    sheets = []
    fa = fa or {}
    year = fa.get("calendar_year")
    note = f"Calendar year {year}, 1 January to 31 December." if year else ""

    for key, code, title in (("a1_depository_accounts", "A1", "Foreign depository accounts"),
                             ("a2_custodial_accounts", "A2", "Foreign custodial accounts")):
        accounts = fa.get(key) or []
        if not accounts:
            continue
        sheets.append(_sheet(
            f"schedule_fa_{code.lower()}", f"Schedule FA {code}: {title}", "foreign_special",
            [{"t": "(7) Account number"}, {"t": "(8) Status"}, {"t": "(9) Opened"},
             {"t": "(10) Peak balance", "num": True}, {"t": "(11) Closing balance", "num": True},
             {"t": "(12) Gross amount credited", "num": True}],
            [_row(f"{i}:{x.get('account_number')}", i + 1, x.get("institution_name"),
                  [x.get("account_number") or "", x.get("status") or "", x.get("opened_on") or "",
                   x.get("peak_value"), x.get("closing_value"), x.get("gross_credited")])
             for i, x in enumerate(accounts)], note))

    rows, serial = [], 0
    for x in fa.get("a3_equity_and_debt") or []:
        for lot in x.get("lots") or []:
            serial += 1
            rows.append(_row(
                f"{x.get('entity_name')}:{lot.get('acquired_on')}:{lot.get('quantity')}:{serial}",
                serial, x.get("entity_name"),
                [lot.get("acquired_on") or "", lot.get("initial_value"), lot.get("peak_value"),
                 lot.get("closing_value"), lot.get("gross_amount_credited"),
                 lot.get("gross_proceeds_on_sale")]))
    if rows:
        sheets.append(_sheet(
            "schedule_fa_a3", "Schedule FA A3: foreign equity and debt interest",
            "foreign_special",
            [{"t": "(8) Date acquired"}, {"t": "(9) Initial value", "num": True},
             {"t": "(10) Peak value", "num": True}, {"t": "(11) Closing value", "num": True},
             {"t": "(12) Gross amount credited", "num": True},
             {"t": "(13) Gross sale proceeds", "num": True}],
            rows, note + " One row for each acquisition."))
    return sheets


def _depreciation(dep: dict | None) -> list[dict]:
    blocks = (dep or {}).get("blocks") or []
    if not blocks:
        return []
    def name(b):
        rate = b.get("rate_percent")
        at = f" at {rate:g}%" if isinstance(rate, (int, float)) else ""
        return f"{b.get('description')}{at} ({b.get('schedule')})"

    rows = [_row(f"{b.get('schedule')}:{b.get('block')}:{b.get('rate_percent')}", i + 1, name(b),
                 [b.get("opening_wdv", 0), b.get("additions_180_days_or_more", 0),
                  b.get("additions_less_than_180_days", 0), b.get("depreciation_allowable", 0),
                  b.get("closing_wdv", 0)])
            for i, b in enumerate(blocks)]
    rows.append(_row("total", "", "Total depreciation, to Schedule BP",
                     [None, None, None, (dep or {}).get("total_depreciation", 0), None], "total"))
    return rows


def build(summary: dict | None, docs: dict | None) -> list[dict]:
    """Every sheet there is something to enter on, in the order of the return."""
    summary, docs = summary or {}, docs or {}
    regime = (summary.get("regimes") or {}).get(summary.get("recommended_regime")) or {}
    cascade = regime.get("cascade") or {}
    stages = cascade.get("stages") or []
    heads = regime.get("heads") or {}
    sheets: list[dict] = []

    def add(sheet_id, title, tab, columns, rows, note=""):
        if rows:
            sheets.append(_sheet(sheet_id, title, tab, columns, rows, note))

    add("schedule_s", "Schedule S: salaries", "salary", AMOUNT,
        _salary(docs.get("salary"), heads.get("salary")))

    business = regime.get("business") or {}
    add("schedule_bp", "Schedule BP: business or profession", "business_computation", AMOUNT,
        [_row(r["item"], r["item"], r["label"], [r["amount"]], r.get("kind") or "")
         for r in business.get("rows") or []], business.get("verify") or "")

    add("schedule_dep", "Schedules DPM, DOA and DEP: depreciation", "depreciation",
        [{"t": "Opening written down value", "num": True},
         {"t": "Additions, 180 days or more", "num": True},
         {"t": "Additions, under 180 days", "num": True},
         {"t": "Depreciation", "num": True}, {"t": "Closing written down value", "num": True}],
        _depreciation(business.get("depreciation_schedule")))

    cg = regime.get("capital_gains") or {}
    add("schedule_cg", "Schedule CG: capital gains", "capital_gains",
        [{"t": "Sell value", "num": True}, {"t": "Buy value", "num": True},
         {"t": "Expenses", "num": True}, {"t": "Gain after expenses", "num": True}],
        _capital_gains(cg.get("form")), (cg.get("form") or {}).get("verify") or "")

    # Schedule 112A: the rows as they are entered, consolidated where the form
    # allows it. The text columns say which kind of row each is.
    s112a = regime.get("schedule_112a") or {}
    add("schedule_112a", "Schedule 112A: equity shares and units on which STT is paid",
        "scrip_112a",
        [{"t": "(1a) Acquired"}, {"t": "(2) ISIN"}, {"t": "(6) Full value of consideration", "num": True},
         {"t": "(7) Cost without indexation", "num": True}, {"t": "(8) Cost of acquisition", "num": True},
         {"t": "(12) Expenditure on transfer", "num": True}, {"t": "(13) Total deductions", "num": True},
         {"t": "(14) Balance", "num": True}],
        [_row(f"{r.get('isin')}:{r.get('sl')}", r.get("sl"), r.get("name"),
              [{"after": "After 31 Jan 2018", "on_or_before": "On or before 31 Jan 2018"}
               .get(r.get("acquired"), "Date not known"),
               r.get("isin") or "", r.get("full_value"), r.get("cost_without_indexation"),
               r.get("cost_of_acquisition"), r.get("expenditure"), r.get("total_deductions"),
               r.get("balance")])
         for r in s112a.get("rows") or []]
        + ([_row("total", "", "Total of each column",
                 ["", "", (s112a.get("totals") or {}).get("full_value"),
                  (s112a.get("totals") or {}).get("cost_without_indexation"),
                  (s112a.get("totals") or {}).get("cost_of_acquisition"),
                  (s112a.get("totals") or {}).get("expenditure"),
                  (s112a.get("totals") or {}).get("total_deductions"),
                  (s112a.get("totals") or {}).get("balance")], "total")]
           if s112a.get("rows") else []),
        s112a.get("verify") or "")

    os_form = (heads.get("other_sources") or {}).get("form")
    add("schedule_os", "Schedule OS: other sources", "other_sources", AMOUNT,
        _other_sources(os_form), (os_form or {}).get("verify") or "")

    via = regime.get("chapter_via") or {}
    add("schedule_via", "Schedule VI-A: deductions", "deductions",
        [{"t": "Claimed", "num": True}, {"t": "Allowed", "num": True}],
        [_row(line["section"], line["section"], line.get("note") or "",
              [line["claimed"], line["allowed"]]) for line in via.get("lines") or []]
        + ([_row("total", "", "Total deductions allowed", [None, via.get("total_allowed", 0)],
                 "total")] if via.get("lines") else []))

    add("part_b_ti", "Part B-TI: computation of total income", "summary", AMOUNT,
        _part_b(stages, "Part B-TI"),
        "Entered as the form prints them: a deduction is the amount deducted, not a negative.")
    add("part_b_tti", "Part B-TTI: computation of tax liability", "summary", AMOUNT,
        _part_b(stages, "Part B-TTI"),
        "Lines 8a to 8d, interest and fee, are worked out by the utility and are nil here.")

    sheets += _taxes_paid(docs.get("taxes_paid"))
    sheets += _foreign(regime.get("foreign"))
    sheets += _foreign_assets(regime.get("foreign_assets"))
    return sheets


def stamp(row: dict) -> str:
    """What a row said when it was marked entered, to notice it changing."""
    return "|".join("" if v is None else str(v) for v in row.get("values") or [])
