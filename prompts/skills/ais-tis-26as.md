---
name: ais-tis-26as
use_when: An income-tax portal document about what others reported for this taxpayer -- the Annual Information Statement (AIS), the Taxpayer Information Summary (TIS), or Form 26AS.
schedules: [capital_gains, salary, other_sources, taxes_paid, foreign_special, reconcile]
verified_from: An AIS and a TIS for FY 2025-26 downloaded from the income-tax portal, and a Form 26AS for the same year.
---

# AIS, TIS and Form 26AS

These are the department's record of what banks, brokers, registrars and
employers reported about the taxpayer. They are **never a source of ledger
rows**: they are aggregates, they arrive late, they are sometimes wrong, and
the same transaction appears in more than one of them. Their use is
reconciliation -- checking that nothing the department knows about is missing
from the return, and being able to explain anything that differs.

Both the AIS and the TIS are encrypted with the PAN in lower case followed by
the date of birth as ddmmyyyy; that is handled before you see them.

## TIS -- start here

The first page is a short table of **information categories** with two amounts
each, "Processed by System" and "Accepted by Taxpayer/Confirmed by Source".
The categories seen in practice:

    Salary
    Dividend
    Interest from savings bank
    Sale of securities and units of mutual fund
    Purchase of securities and units of mutual funds
    Outward foreign remittance/ purchase of foreign currency

Use **Processed by System** as the reported figure unless the two differ, in
which case report the processed figure and raise the difference: it means
feedback was submitted and the department has or has not accepted it.

The following pages repeat each category with the sources behind it, which is
where to look when a category needs explaining.

Which schedule each category belongs to:

| Category | Schedule |
|---|---|
| Salary | Salary |
| Dividend | Other Sources |
| Interest from savings bank | Other Sources |
| Sale of securities and units of mutual fund | Capital Gains |
| Purchase of securities and units of mutual funds | nothing -- a purchase is not income; it says what was bought, not sold |
| Outward foreign remittance | nothing directly; it is the LRS remittance on which TCS was collected, and that TCS is a credit in Taxes Paid |

## AIS -- the detail behind the TIS

Part B1 is tax deducted or collected at source; Part B2 is specified financial
transactions (SFT). Each line gives an information code, a description, the
reporting source and an amount, with the transactions beneath it.

Codes seen in practice: `SFT-015` dividend income (one line per company),
`SFT-016(SB)` interest on a savings bank account, `SFT-17(Pur)` purchase of
securities, `SFT-18(Pur)` purchase of mutual funds, `TDS-192` salary,
`TDS-194` dividend, `TCS-206CQ` remittance under LRS.

Note what is *not* there: the AIS and TIS report the **sale value** of
securities, never the gain. There is no "capital gain" figure to compare
against, only proceeds.

## Traps

- **The sale figure is gross proceeds**, not net of brokerage or STT. Compare
  it with a sale-value measure, never with a gain.
- **Foreign holdings are absent.** No Indian source reports a sale on a US
  exchange, so the return will exceed the reported figure by that amount --
  expected, and worth saying so explicitly.
- **Deduplication.** The TIS is already deduplicated across sources; the AIS
  is not always. Do not add AIS lines to a TIS category total.
- **Rounding.** These are whole rupees while broker files carry paise, so
  differences of a few rupees are normal. Say so rather than leaving them
  unexplained.
- **A missing category means nothing was reported**, not that nothing
  happened. A sale the department has not been told about is still taxable.
