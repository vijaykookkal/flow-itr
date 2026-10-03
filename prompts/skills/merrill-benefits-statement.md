---
name: merrill-benefits-statement
use_when: A Merrill (Merrill Lynch) quarterly account statement, usually from benefits.ml.com, for employee stock such as RSUs -- headed "YOUR INDIVIDUAL INVESTOR ACCOUNT" and an alphanumeric account number.
schedules: [capital_gains, other_sources, foreign_special, salary]
verified_from: A 60-page download of four calendar-quarter statements, April 2025 to March 2026, for one employee-stock account.
---

# Merrill quarterly account statements

## Shape

- One statement per **calendar quarter**. A download often concatenates
  several, and **can contain the same quarter more than once**. Identify each
  statement by its period line (`July 01, 2025 - September 30, 2025`) and
  account number, and read each quarter once.
- An Indian financial year needs four quarters: April-June, July-September
  and October-December of the first calendar year, and January-March of the
  next. Say in `questions[]` if any of the four is missing.
- All amounts are **US dollars**. Record them with `currency: "USD"` and
  `amount_foreign`; never convert.
- Dates are **US format, MM/DD/YY**: `09/03/25` is 3 September 2025.

## Where the transactions are

**REALIZED GAINS/(LOSSES)** -- the disposals. One line per lot:

    Description  Quantity  Acquired  Liquidation  Sale Amount  Cost Basis  Gain/(Loss)
    ACME CORP    50.0000   12/07/24  09/03/25     1,500.00     1,900.00    (400.00)

- Each lot is its own disposal row. `acquired_on` is the Acquired date,
  `transferred_on` the **Liquidation** date.
- The **SECURITY TRANSACTIONS -> Sales** block shows the same sale by its
  *settlement* date, a day or two later (`09/04`). That is not the transfer
  date and not a second sale; use it only to check the lots add up to the
  sale.
- `Subtotal (Short-Term)` / `(Long-Term)` is Merrill's US classification. Put
  it in `stated_term` if you like, but the Indian holding period (24 months
  for foreign shares) decides, from the dates.
- **"This Statement" versus "Year to Date".** The later quarters' realised
  gains sections carry the earlier sale forward in the Year to Date column,
  with no lot lines of their own. A figure that appears only under Year to
  Date, with no lots, is **not a new disposal**. The year to date runs by
  calendar year and resets in January.
- "Excludes transactions for which we have insufficient data" is printed on
  every section: if Sales shows a sale with no matching lots, report the sale
  and ask for its cost in `questions[]`.

**SECURITIES YOU TRANSFERRED IN/OUT** -- RSU vests, lines like
`ACME CORP Transfer / Adjustment 70.0000 1,800.00` followed by
`RSU ACTIVITY ... GRANT DATE <date> LAPSE DATE <date>`. These are
**acquisitions, not disposals**: the lapse date is the acquisition date and the
value is the market value at vest, which was taxed as a salary perquisite and
becomes the cost of those shares. Not Schedule CG rows; they matter to Salary
(perquisite cross-check) and Schedule FA.

**Income DIVIDENDS/INTEREST INCOME TRANSACTIONS -> Taxable Dividends** --
Schedule OS, not capital gains. Each line is followed by a holding line
carrying the **PAY DATE**, in US format:

    Dividend 07/02 HP INC *            100.42
    HOLDING 347.0000 PAY DATE 07/02/2025

That pay date is the date of receipt and must be recorded: a dividend in a
foreign currency is converted at the rate Rule 115 fixes from the month it was
received, so without the date it cannot enter the return at all. The amount is
**gross**, before the US tax below.

**CASH/OTHER TRANSACTIONS -> "Non-Resident Alien Tax"** -- US tax withheld on
those dividends (`TAX ON NRA DIVIDEND PAY DATE <date>`), one line per
dividend and matched to it by that date. This is **not TDS**: nothing was
deducted under the Indian Act, so it does not belong in `tds_deducted`. It is
foreign tax, claimed as credit through Schedule FSI and TR with Form 67, and
the dividend stays in Schedule OS at its gross amount.

**EQUITIES / Long Portfolio** -- holdings at quarter end, with unrealised
gains. Nothing here is a disposal; it is Schedule FA material.

## Traps

- US-year language ("reportable on your 2025 tax return", "will appear on
  your January statement") is about US reporting. Ignore it.
- Cost basis of RSU shares is Merrill's market value at vest. Report it as
  stated; whether it equals the perquisite value in Form 16 is a question for
  the reviewer, not something to adjust.
