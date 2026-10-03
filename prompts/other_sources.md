version: other_sources@4

# Schedule OS - Income from Other Sources

Source documents: bank and post-office interest certificates, FD and RD
statements, dividend statements from brokers and fund registrars,
Form 26AS interest entries, and anything showing interest on an income-tax
refund.

## What to produce

**A ledger, then totals.** `items[]` holds one row per **credit** -- payer,
account reference, category, date of receipt, amount, TDS. One row per credit,
not per payer and not per certificate: a company paying an interim and a final
dividend is two rows, and a bank crediting savings interest each quarter is
four. `totals_by_category` is the sum of those rows and nothing else. Never
state a total the ledger does not support: the whole point of the ledger is
that a missing certificate shows up as a gap you can see.

This matters most for anything paid in a foreign currency. Each credit is
converted at the rate for its own date, so four dividends from the same company
carry four different rates and four different rupee amounts. Rolled into one
row they cannot be converted at all.

Categories:

| Category | What goes in it |
|---|---|
| `interest_savings` | Savings bank and post-office savings interest (relevant to 80TTA/80TTB) |
| `interest_deposits` | Fixed deposits, recurring deposits, corporate deposits |
| `interest_income_tax_refund` | Interest under section 244A on a refund -- taxable, and very often missed |
| `interest_other` | Loans to others, PPF-ineligible instruments, partner interest not on Schedule IF |
| `dividend` | Dividends from shares and mutual funds |
| `family_pension` | Pension to a legal heir (attracts the section 57(iia) deduction) |
| `winnings_115BB` | Lottery, crossword, betting, game shows |
| `other` | Anything real that fits nowhere above -- name it clearly in `payer` |

## Watch for

- **Accrued versus credited FD interest.** Certificates state one or the other
  and sometimes both. If both appear, report the basis the certificate presents
  as the FY figure and note the other in `questions[]`.
- **Interest on an income-tax refund** is frequently buried in a note or only in
  Form 26AS. It is taxable. Find it.
- **Dividend rows are per security.** Keep them separate so they reconcile
  against Form 26AS section 194 entries one-to-one.
- **TDS belongs to Schedule TDS2 as well.** Record `tds_deducted` here so the two
  can be reconciled, but Schedule TDS2 is extracted separately from Form 26AS --
  it is not this schedule's job to be the authority on TDS.
- **Do not net expenses off income.** Section 57 deductions go in `deductions_57`
  as their own figure.
- **Exempt income** (PPF interest, tax-free bonds) is not Schedule OS. Put it in
  `unmapped[]` noting it belongs on Schedule EI.


## Dates, and foreign receipts

Give `received_on` for every entry where the document states a date of credit
or payment. It is what lets a receipt be placed in the right year.

For an amount stated in a foreign currency it is not optional: record the
amount with `currency` and `amount_foreign` exactly as stated, never converted,
and give the date. Rule 115 fixes the exchange rate by the month of receipt,
so a foreign amount with no date cannot be converted and stays out of the
return entirely.

## Tax withheld abroad

A receipt from outside India usually arrives net of foreign tax. Record the
tax withheld on that receipt in `tax_withheld_outside_india`, in the currency
the document states it in, beside the gross amount in `amount`.

Two things depend on it and neither can be recovered later:

- **Schedule FSI column (d)** is built from these, receipt by receipt, and the
  relief claimed under section 90 follows from that. A withholding that was
  never recorded is relief that is never claimed -- real money, silently lost.
- Each receipt converts at **its own** date under Rule 115, so a single annual
  total of withholding cannot be converted correctly. The per-receipt figure is
  the only one that works.

`amount` stays **gross**, before the withholding. A Form 1042-S states the
gross in box 2 and the tax withheld in box 7 or box 10; a broker statement
usually shows the dividend and the "NRA tax" as separate lines on the same
date. Do not net them.

This field is not Indian TDS. Indian TDS on a resident's dividend goes in
`tds_deducted` and is claimed in Schedule TDS2, which is a different claim
under a different section.
