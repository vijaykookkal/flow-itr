"""Schedule BP: business income, from the books and the depreciation schedule.

The books say what the business earned by its own accounting. The Act taxes
something else, and Schedule BP is the bridge: start at the profit in the
profit and loss account, take out what belongs to another head, put back what
the accounts deducted but the Act does not allow, and swap the depreciation in
the books for the depreciation the Act permits.

Three things are kept apart the whole way down, because the Act never lets
them mix freely:

  * ordinary (non-speculative) business, which includes futures and options;
  * speculative business -- intraday equity -- whose losses may meet nothing
    but speculative profit;
  * specified business under section 35AD.

Item numbers follow the ITR-3 Schedule BP structure. VERIFY THEM against the
released utility for the assessment year: the numbering moves between years,
and a correct amount on the wrong line is still a defective return.
"""

from __future__ import annotations


def amount(node) -> int:
    if isinstance(node, dict):
        return int(node.get("amount") or 0)
    return int(node or 0)


def _data(doc) -> dict:
    return (doc or {}).get("data") or {}


def line(item, label, value, note="", kind="") -> dict:
    return {"item": item, "label": label, "amount": int(value or 0), "note": note, "kind": kind}


def allowable_depreciation(dep_doc) -> tuple[int, int]:
    """(depreciation allowable under the Act, blocks it came from)."""
    blocks = _data(dep_doc).get("blocks") or []
    return sum(amount(b.get("depreciation_allowable")) for b in blocks), len(blocks)


def _charges(segment: dict) -> tuple[list[dict], int]:
    """(each charge as stated, their total).

    The total is computed here rather than read from the document: the
    statement usually gives no total, and an extraction that added them up
    itself would be doing arithmetic nobody could check.
    """
    rows = []
    for c in (segment or {}).get("charges") or []:
        # Which document a cost came from is the difference between "these are
        # broker charges" and "these are the invoices you supplied", and a
        # bucket that mixes the two hides both.
        cite = (c.get("amount") or {}).get("cite") or "" if isinstance(c.get("amount"), dict) else ""
        rows.append({"head": c.get("head", "(unnamed)"), "amount": amount(c.get("amount")),
                     "note": c.get("note") or "",
                     "source": cite.split("#")[0].strip() or "(source not stated)"})
    return rows, sum(r["amount"] for r in rows)


def build(books_doc: dict, dep_doc: dict | None = None) -> dict:
    books = _data(books_doc)
    pl = books.get("profit_and_loss") or {}
    no_accounts = books.get("no_accounts_case") or {}
    spec = books.get("speculative") or {}
    deriv = books.get("derivatives") or {}
    info = books.get("other_information") or {}

    keeps_books = bool(books.get("books_maintained"))
    book_profit = amount(pl.get("profit_before_tax")) or amount(pl.get("net_profit"))
    if not book_profit and no_accounts:
        book_profit = amount(no_accounts.get("net_profit"))

    spec_profit = amount(spec.get("profit_or_loss"))
    deriv_profit = amount(deriv.get("profit_or_loss"))

    # A broker states the realised profit gross and lists the charges beside
    # it. Every one of them is an expense of that business -- including STT,
    # which is deductible here precisely because this is business income and
    # not capital gains -- so a profit taken without them is tax on money that
    # was never earned.
    spec_charges, spec_cost = _charges(spec)
    deriv_charges, deriv_cost = _charges(deriv)
    other_charges, other_cost = _charges({"charges": books.get("other_expenses_of_business")})

    book_depreciation = amount(pl.get("depreciation_in_books"))
    act_depreciation, blocks = allowable_depreciation(dep_doc)

    d43b = amount(info.get("disallowance_43B"))
    d40a = amount(info.get("disallowance_40a"))
    d40A3 = amount(info.get("disallowance_40A3"))
    additions = d43b + d40a + d40A3

    # A -- ordinary business
    # A2a takes the speculative result OUT of the profit and loss account, so it
    # may only be subtracted when it was in there to begin with. Subtracting it
    # from an account that never included it quietly loses that much income.
    spec_in_books = bool(keeps_books and book_profit)
    rows = [
        line("A1", "Profit before tax as per the profit and loss account", book_profit,
             "Part A-P&L. Where no books are kept, the net profit declared there."),
        line("A2a", "Less: net profit from speculative business, carried to part B",
             -spec_profit if spec_in_books else 0,
             ("Intraday equity is a separate business under section 43(5); its profit is taxed "
              "in part B and its loss may meet nothing else.") if spec_in_books else
             ("The speculative result is reported separately by the broker and is not inside "
              "any profit and loss account here, so there is nothing to remove. It is taxed "
              "in part B below." if spec_profit else "")),
        line("A3", "Less: net profit from specified business under section 35AD", 0,
             "None recorded."),
    ]
    subtotal = book_profit - (spec_profit if spec_in_books else 0)
    rows.append(line("A6", "Profit from ordinary business before adjustment", subtotal, "", "sub"))

    rows.append(line("A11", "Add: depreciation debited to the profit and loss account",
                     book_depreciation,
                     "Whatever the books charged is added back in full; the Act's own figure "
                     "replaces it on the next line." if book_depreciation else ""))
    rows.append(line("A12", "Less: depreciation allowable under section 32", -act_depreciation,
                     f"Schedule DEP, {blocks} block(s) of assets." if blocks else
                     "Nothing computed: the Depreciation tab has no blocks, so no allowance is "
                     "claimed. If the business holds assets, this is understating the deduction."))

    rows.append(line("A14", "Add: amounts disallowed under section 43B, not paid in time", d43b,
                     "Statutory dues, deductible only in the year they are actually paid."
                     if d43b else ""))
    rows.append(line("A15", "Add: amounts disallowed under section 40(a)", d40a,
                     "Payments where tax was not deducted or not deposited." if d40a else ""))
    rows.append(line("A16", "Add: amounts disallowed under section 40A(3)", d40A3,
                     "Cash payments above the limit." if d40A3 else ""))
    if additions:
        rows.append(line("A21", "Total additions", additions, "", "sub"))

    ordinary = subtotal + book_depreciation - act_depreciation + additions

    # F&O is an ordinary business. Whether it is already inside the profit and
    # loss account depends on how the books were kept, and getting that wrong
    # either doubles it or loses it -- so it is never added silently.
    deriv_note = ""
    if deriv_profit:
        if keeps_books and book_profit:
            deriv_note = (f"The broker's own futures and options result is Rs {deriv_profit:,}. "
                          f"It is NOT added here, on the assumption that the profit and loss "
                          f"account above already includes it. Confirm that, because adding it "
                          f"twice and leaving it out are both easy from here.")
        else:
            ordinary += deriv_profit
            rows.append(line("A24", "Add: futures and options result, not in any books",
                             deriv_profit,
                             "Non-speculative business under the Act, stated gross of the "
                             "charges deducted below. Added because no profit and loss account "
                             "was drawn up that would already include it."))

    if deriv_cost:
        ordinary -= deriv_cost
        rows.append(line("A25", "Less: charges on that business",
                         -deriv_cost,
                         f"{len(deriv_charges)} charge head(s): brokerage, exchange and "
                         f"clearing charges, STT, stamp duty, SEBI fees and GST. Broken down "
                         f"below."))
    if other_cost:
        ordinary -= other_cost
        rows.append(line("A26", "Less: other expenses of the business", -other_cost,
                         f"{len(other_charges)} item(s) belonging to no single segment -- "
                         f"depository and maintenance charges and the like."))

    rows.append(line("A38", "Income from business other than speculative", ordinary, "", "total"))

    # B -- speculative
    spec_net = spec_profit - spec_cost
    if spec_cost:
        rows.append(line("B39a", "Speculative result before its own charges", spec_profit, ""))
        rows.append(line("B39b", "Less: charges on the speculative business", -spec_cost,
                         f"{len(spec_charges)} charge head(s) on intraday trades."))
    rows.append(line("B39", "Net profit or loss from speculative business", spec_net,
                     "Taxed at slab rates like any business income, but a loss here is "
                     "ring-fenced: it may be set off only against speculative profit, and "
                     "carried forward four years." if spec_profit else "", "total"))

    total = ordinary + spec_net
    rows.append(line("D", "Income chargeable under the head business or profession",
                     total, "A38 plus B39.", "total"))

    warnings = []
    if book_depreciation and not act_depreciation:
        warnings.append(
            f"The books charge Rs {book_depreciation:,} of depreciation and it has been added "
            f"back, but nothing is claimed under section 32 because the Depreciation tab is "
            f"empty. Until it is filled in, this overstates business income by that amount.")
    if not keeps_books and book_profit:
        warnings.append("No books are maintained, so the figures come from the no-accounts "
                        "section of Part A-P&L. Section 44AA may still require books.")
    if not deriv_cost and deriv_profit:
        warnings.append(
            "No charges are recorded against the futures and options business. A broker's "
            "realised profit is stated gross of brokerage, exchange charges, STT, stamp duty "
            "and GST, and all of those are deductible here. Unless they are genuinely nil, "
            "this is tax on money that was never earned -- re-extract Books.")
    if spec_net < 0:
        warnings.append(f"The speculative loss of Rs {abs(spec_net):,} is carried forward, "
                        f"not set off. It can meet only speculative profit, within four years.")

    return {
        "rows": rows,
        "ordinary": ordinary,
        "speculative": spec_net,
        "total": total,
        "book_profit": book_profit,
        "depreciation": {"books": book_depreciation, "act": act_depreciation, "blocks": blocks},
        "charges": {"derivatives": deriv_charges, "speculative": spec_charges,
                    "other": other_charges,
                    "total": deriv_cost + spec_cost + other_cost},
        "derivatives_note": deriv_note,
        "warnings": warnings,
        "verify": ("Item numbers follow the ITR-3 Schedule BP structure and must be checked "
                   "against the released utility for this assessment year."),
    }
