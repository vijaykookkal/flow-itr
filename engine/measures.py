"""The figures a schedule can be reconciled against, computed from our data.

Reconciliation compares what the department was told about you with what this
return says. Those two sides have to be produced differently. The department's
side is read out of the AIS or TIS at runtime, because only a reader can tell
which line of a statement is which. Our side must never be: it is computed
here, from the extracted data, by name, so that the comparison cannot quietly
become the engine agreeing with itself.

A measure is one named, computed figure -- "sale value of Indian securities and
mutual funds" -- with a note on what it covers, so a difference can be opened
up and argued about in the right terms. Capital Gains measures also carry the
ledger rows behind them.

Adding a schedule here is what makes its Reconciliation card work: its measures
and the one-line description of what it is checked against, side by side.
"""

from __future__ import annotations


# --------------------------------------------------------------------------
# reading our own documents
# --------------------------------------------------------------------------
def amount(node) -> int:
    """Rupees out of a money object, or 0.

    A figure stated only in a foreign currency has no rupee amount until it is
    converted, and counting it as zero would be wrong -- so those are reported
    separately by the schedule that holds them, never folded in here."""
    if isinstance(node, dict):
        return int(node.get("amount") or 0)
    return int(node or 0)


def total(rows, field) -> int:
    return sum(amount((r or {}).get(field)) for r in rows or [])


def data_of(doc) -> dict:
    return (doc or {}).get("data") or {}


def m(key, label, value, basis, rows=None, is_count=False) -> dict:
    return {"key": key, "label": label, "amount": int(value or 0), "rows": rows or [],
            "basis": basis, **({"is_count": True} if is_count else {})}


# --------------------------------------------------------------------------
# capital gains -- computed from the ledger after conversion, not the raw doc
# --------------------------------------------------------------------------
INDIAN_SECURITIES = {"equity_stt", "equity_unlisted", "debt_mf_specified",
                     "debt_mf_other", "bonds_debentures"}
FOREIGN = {"foreign_shares"}


def _cg_rows(summary: dict) -> list[dict]:
    """The computed disposal rows, whichever regime is shown; capital gains do
    not differ between regimes, so either copy has the same ledger."""
    for regime in (summary.get("regimes") or {}).values():
        rows = (regime.get("capital_gains") or {}).get("rows")
        if rows is not None:
            return rows
    return []


def capital_gains(summary: dict, doc: dict | None = None) -> list[dict]:
    rows = _cg_rows(summary)
    unconverted = 0
    for regime in (summary.get("regimes") or {}).values():
        unconverted = max(unconverted, len((regime.get("capital_gains") or {}).get("unconverted", [])))

    def sums(field, keep):
        picked = [r for r in rows if keep(r)]
        return sum(r.get(field, 0) for r in picked), [r["index"] for r in picked if "index" in r]

    def measure(key, label, field, keep, basis):
        value, used = sums(field, keep)
        return m(key, label, value, basis, rows=used)

    india = lambda r: r.get("asset_class") in INDIAN_SECURITIES          # noqa: E731
    foreign = lambda r: r.get("asset_class") in FOREIGN                  # noqa: E731

    out = [
        measure("sale_value_india_securities_mf",
                "Sale value of Indian securities and mutual fund units", "proceeds", india,
                "Full value of every disposal of Indian shares, bonds and mutual fund "
                "units in the ledger, before expenses."),
        measure("purchase_value_of_what_was_sold", "Cost of the Indian securities sold",
                "cost", india,
                "Cost of acquisition of those same disposals, including the charges paid "
                "on purchase where a document states them. NOT the department's purchase "
                "reporting, which covers what you BOUGHT in the year."),
        measure("sale_value_foreign_shares", "Sale value of foreign shares", "proceeds", foreign,
                "Foreign disposals, converted to rupees. No Indian source reports these."),
        measure("short_term_gain", "Short-term capital gain", "gain",
                lambda r: r.get("term") == "short",
                "Net of gains and losses on disposals held under the threshold: sale value "
                "less cost (purchase value plus purchase charges) less the charges on the "
                "sale. Securities transaction tax is deducted nowhere. A broker's own figure "
                "may be before these charges."),
        measure("long_term_gain", "Long-term capital gain", "gain",
                lambda r: r.get("term") == "long",
                "Net of gains and losses on disposals held at or beyond the threshold: sale "
                "value less cost (purchase value plus purchase charges) less the charges on "
                "the sale. Securities transaction tax is deducted nowhere. A broker's own "
                "figure may be before these charges."),
        measure("total_gain", "Total capital gain", "gain", lambda r: True, "Every disposal."),
        m("disposal_count", "Number of disposals", len(rows), "Rows in the ledger.", is_count=True),
    ]
    if unconverted:
        out.append(m("excluded_unconverted", "Disposals left out for want of a rate", unconverted,
                     "Foreign disposals with no exchange rate yet: they are in no figure "
                     "above, so a difference of that size explains itself.", is_count=True))
    return out


# --------------------------------------------------------------------------
# the other schedules -- computed from their own extracted data
# --------------------------------------------------------------------------
def salary(summary: dict, doc: dict | None = None) -> list[dict]:
    data = data_of(doc)
    employers = data.get("employers") or []
    exempt = sum(total(e.get("exempt_allowances") or [], "amount") for e in employers)
    return [
        m("gross_salary", "Gross salary", total(employers, "gross_salary"),
          "Section 17(1) salary, 17(2) perquisites and 17(3) profits in lieu, added across "
          "every employer -- what Form 16 Part B calls gross salary, and what an employer "
          "reports to the department."),
        m("perquisites", "Perquisites under section 17(2)", total(employers, "perquisites_17_2"),
          "Including the value of shares vested under an employee stock plan, which is "
          "also the cost of those shares if they are later sold."),
        m("exempt_allowances", "Allowances exempt under section 10", exempt,
          "House rent, leave travel and the rest: reported by the employer but not taxed."),
        m("net_salary_after_10", "Salary after section 10 exemptions", total(employers, "net_salary"),
          "Gross salary less the exempt allowances."),
        m("income_chargeable", "Income chargeable under Salaries", amount(data.get("income_chargeable")),
          "After the section 16 deductions: the figure that enters the computation."),
        m("employer_count", "Number of employers", len(employers),
          "Each one files its own TDS return, so each appears separately in the AIS.",
          is_count=True),
    ]


def house_property(summary: dict, doc: dict | None = None) -> list[dict]:
    data = data_of(doc)
    props = data.get("properties") or []
    return [
        m("rent_received", "Rent received or receivable", total(props, "rent_received_or_receivable"),
          "Gross rent across every let property, before municipal tax or the standard "
          "deduction. A tenant deducting TDS reports this same figure."),
        m("municipal_tax", "Municipal tax paid", total(props, "municipal_tax_paid"),
          "Deductible only when actually paid in the year."),
        m("income_from_hp", "Income from house property", amount(data.get("total_income_from_hp")),
          "After municipal tax, the 30% standard deduction and interest on borrowed capital."),
        m("property_count", "Number of properties", len(props), "Let and self-occupied together.",
          is_count=True),
    ]


def books(summary: dict, doc: dict | None = None) -> list[dict]:
    data = data_of(doc)
    pl = data.get("profit_and_loss") or {}
    no_accounts = data.get("no_accounts_case") or {}
    spec = data.get("speculative") or {}
    deriv = data.get("derivatives") or {}
    return [
        m("turnover", "Turnover or gross receipts",
          amount(pl.get("total_revenue")) or amount(no_accounts.get("gross_receipts")),
          "Revenue from operations plus other income, or gross receipts where no books "
          "are kept. Compare with GST returns and any receipts reported in the AIS."),
        m("speculative_turnover", "Speculative turnover", amount(spec.get("turnover")),
          "Intraday equity. A broker states this in its own tax P&L."),
        m("speculative_profit", "Speculative profit or loss", amount(spec.get("profit_or_loss")),
          "Intraday equity, taxed as speculative business income."),
        m("derivatives_turnover", "Derivatives turnover", amount(deriv.get("turnover")),
          "F&O turnover as the broker computes it; the basis differs between brokers, so "
          "say which was used."),
        m("derivatives_profit", "Derivatives profit or loss", amount(deriv.get("profit_or_loss")),
          "F&O, taxed as non-speculative business income."),
    ]


def vda(summary: dict, doc: dict | None = None) -> list[dict]:
    data = data_of(doc)
    transfers = data.get("transfers") or []
    return [
        m("consideration", "Consideration on virtual digital assets", total(transfers, "consideration"),
          "Gross sale value. An exchange deducting TDS under section 194S reports this."),
        m("cost", "Cost of those assets", total(transfers, "cost_of_acquisition"),
          "Only the cost of acquisition is deductible: no expenses, no set-off of losses."),
        m("income", "Income from virtual digital assets", amount(data.get("total_income")),
          "Taxed at a flat 30%."),
    ]


def other_sources(summary: dict, doc: dict | None = None) -> list[dict]:
    data = data_of(doc)
    by = data.get("totals_by_category") or {}
    items = data.get("items") or []
    return [
        m("dividend", "Dividend income", amount(by.get("dividend")),
          "Every dividend credited in the year. Each company reports its own under "
          "SFT-015, and the TIS adds them into one Dividend category."),
        m("interest_savings", "Interest from savings accounts", amount(by.get("interest_savings")),
          "Reported by each bank under SFT-016(SB). Deductible up to Rs 10,000 under "
          "section 80TTA."),
        m("interest_deposits", "Interest on deposits", amount(by.get("interest_deposits")),
          "Fixed and recurring deposits, where TDS under section 194A usually appears."),
        m("interest_other", "Other interest",
          amount(by.get("interest_other")) + amount(by.get("interest_income_tax_refund")),
          "Including interest on an income-tax refund, which the department knows about "
          "because it paid it."),
        m("gross_income_from_os", "Gross income from other sources", amount(data.get("gross_income_from_os")),
          "Everything above, before the section 57 deductions."),
        m("item_count", "Number of entries", len(items), "One per payer and category.", is_count=True),
    ]


def deductions(summary: dict, doc: dict | None = None) -> list[dict]:
    data = data_of(doc)
    claims = data.get("claims") or []
    by_section: dict[str, int] = {}
    for c in claims:
        by_section[c.get("section", "?")] = by_section.get(c.get("section", "?"), 0) + amount(c.get("amount"))
    out = [
        m("total_claimed", "Total claimed under Chapter VI-A", amount(data.get("total_claimed")),
          "Before the ceilings, which the computation applies. The employer's own figure "
          "in Form 16 Part B is the thing to compare with."),
    ]
    for section in ("80C", "80D", "80CCD(1B)", "80G", "80TTA", "80TTB"):
        if section in by_section:
            out.append(m(f"claimed_{section}", f"Claimed under {section}", by_section[section],
                         f"Everything claimed under {section} across payees."))
    out.append(m("claim_count", "Number of claims", len(claims), "One per payee and section.",
                 is_count=True))
    return out


def taxes_paid(summary: dict, doc: dict | None = None) -> list[dict]:
    data = data_of(doc)
    salary_tds = data.get("tds_salary") or []
    other_tds = data.get("tds_other") or []
    tcs = data.get("tcs") or []
    challans = data.get("taxes_paid_challans") or []
    advance = [c for c in challans if "advance" in str(c.get("kind", "")).lower()]
    self_assessment = [c for c in challans if "self" in str(c.get("kind", "")).lower()]
    return [
        m("tds_salary", "TDS on salary", total(salary_tds, "tds"),
          "Deducted by employers under section 192. Form 26AS is the authority, and a "
          "credit the department cannot see is a credit you will not get."),
        m("income_paid_by_employers", "Income on which salary TDS was deducted",
          total(salary_tds, "income_paid"),
          "The employer's own figure for what it paid you: cross-checks Salary."),
        m("tds_other", "TDS other than on salary", total(other_tds, "tds"),
          "Dividends, interest, rent, professional fees."),
        m("tcs", "Tax collected at source", total(tcs, "tcs"),
          "Including section 206C(1G) on foreign remittances."),
        m("advance_tax", "Advance tax paid", total(advance, "amount"),
          "By challan, before the year ended."),
        m("self_assessment_tax", "Self-assessment tax paid", total(self_assessment, "amount"),
          "By challan, at or after filing."),
        m("total_taxes_paid", "Total taxes paid", amount(data.get("total_taxes_paid")),
          "Every credit claimed in the return."),
    ]


def _fa_rows(fa: dict) -> list[dict]:
    """Every Schedule FA section flattened, because the peak value the Black
    Money Act cares about is across all of them, not one."""
    rows = []
    for key, items in (fa or {}).items():
        if isinstance(items, list):
            rows.extend(items)
    return rows


def foreign_special(summary: dict, doc: dict | None = None) -> list[dict]:
    data = data_of(doc)
    heads = [h for country in (data.get("schedule_fsi") or [])
             for h in (country.get("heads") or [])]
    tr = (data.get("schedule_tr") or {}).get("countries") or []
    assets = _fa_rows(data.get("schedule_fa") or {})
    return [
        m("foreign_income", "Foreign income (Schedule FSI)",
          total(heads, "income_outside_india"),
          "Income arising outside India, which a resident is taxed on whether or not it "
          "was brought here. No Indian source reports it."),
        m("foreign_tax_paid", "Foreign tax paid (Schedule FSI column d)",
          total(heads, "tax_paid_outside_india"),
          "Tax withheld abroad. A Form 1042-S is the evidence for US withholding."),
        m("relief_claimed", "Relief claimed (Schedule TR)",
          total(tr, "total_relief_available"),
          "The credit claimed under section 90, 90A or 91, which needs Form 67 filed "
          "before the return. It can be less than the tax paid: the relief is capped at "
          "the Indian tax on the same income."),
        m("foreign_assets_peak", "Peak value of foreign assets (Schedule FA)",
          total(assets, "peak_value"),
          "A disclosure, not an income figure: it is reported for the calendar year, and "
          "omitting an asset carries Black Money Act penalties whatever the tax at stake."),
        m("asset_count", "Number of foreign assets", len(assets),
          "Each account, holding and interest counts separately, and an account and the "
          "holdings inside it are both reported.", is_count=True),
    ]


BY_SCHEDULE = {
    "salary": salary,
    "house_property": house_property,
    "books": books,
    "capital_gains": capital_gains,
    "vda": vda,
    "other_sources": other_sources,
    "deductions": deductions,
    "taxes_paid": taxes_paid,
    "foreign_special": foreign_special,
}

# What each schedule is checked against, in the words a reader needs on the
# card. Every schedule reconciles against something different, and saying which
# is the difference between a table of numbers and a statement about the return.
ABOUT = {
    "salary": {"title": "Salary and perquisites",
               "against": "Form 16, the TIS Salary category and the AIS TDS records"},
    "house_property": {"title": "Rent and property income",
                       "against": "the AIS rent-received records and any tenant's TDS"},
    "books": {"title": "Turnover and business profit",
              "against": "the broker's own F&O and intraday totals, and any receipts in the AIS"},
    "capital_gains": {"title": "Sale values and gains",
                      "against": "AIS and TIS categories, and each broker's own totals"},
    "vda": {"title": "Virtual digital asset transfers",
            "against": "the exchange's statement and section 194S TDS in the AIS"},
    "other_sources": {"title": "Dividend and interest",
                      "against": "the AIS dividend and interest lines and the TIS categories"},
    "deductions": {"title": "Chapter VI-A claims",
                   "against": "Form 16 Part B and the proofs in the folder"},
    "taxes_paid": {"title": "TDS, TCS and challans",
                   "against": "Form 26AS and the AIS tax-deducted records"},
    "foreign_special": {"title": "Schedules FSI, TR and FA",
                        "against": "Form 1042-S, broker statements and the LRS remittances in the AIS"},
}


def about(schedule: str) -> dict:
    return ABOUT.get(schedule, {"title": "Reported figures", "against": "the summary documents"})


def for_schedule(schedule: str, summary: dict, doc: dict | None = None) -> list[dict]:
    """The measures available for this schedule, or none if it has no set yet."""
    fn = BY_SCHEDULE.get(schedule)
    if not fn:
        return []
    return [x for x in fn(summary or {}, doc) if x["amount"] or x.get("is_count")]


def lookup(schedule: str, summary: dict, key: str, doc: dict | None = None) -> dict | None:
    for x in for_schedule(schedule, summary, doc):
        if x["key"] == key:
            return x
    return None
