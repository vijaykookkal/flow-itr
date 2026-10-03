version: taxes_paid@2

# Schedules TDS1 / TDS2 / TDS3 / TCS / IT - Taxes Paid

Source documents: Form 26AS, AIS, TIS, advance-tax and self-assessment challans
(ITNS 280 counterfoils), Form 16 Part A, Form 16A certificates.

**Form 26AS is the authority.** Where a TDS certificate and Form 26AS disagree,
report the Form 26AS figure -- that is what the department will credit -- and
raise the disagreement in `questions[]`. A certificate that is not in 26AS is a
real problem for the filer and must be flagged, not quietly included.

## What to produce

| Target | Form 26AS part |
|---|---|
| `tds_salary[]` | Part I, one row per employer TAN |
| `tds_other[]` | Parts II and III, one row per deductor and section |
| `tcs[]` | The TCS part, one row per collector |
| `taxes_paid_challans[]` | The "tax paid other than TDS/TCS" part |

### Advance tax and self-assessment tax are in the AIS, not Form 26AS

This is the single easiest credit to lose, and losing it turns a refund into a
demand. Form 26AS no longer carries a challan part at all: its parts run I to
IX and every one of them is TDS, TCS or a specific reported transaction. The
advance tax and self-assessment tax challans live in the **AIS**, in a table
headed with the columns FINANCIAL YEAR, MAJOR HEAD, MINOR HEAD, TAX, SURCHARGE,
EDUCATION CESS, OTHERS, TOTAL, BSR CODE, DATE OF DEPOSIT and CHALLAN SERIAL
NUMBER.

Read that table. Every row of it belongs in `taxes_paid_challans[]`, with the
minor head recorded -- "Advance Tax", "Self Assessment Tax" -- because they go
to different lines of Part B-TTI.

**Check the financial year on every row.** That table lists challans for other
years beside this one: a self-assessment payment made in August for the
*previous* year sits in the same table as this year's advance tax, and it is
paid in this year, which makes it look current. It is not. Take only the rows
whose financial year is the one being filed, and put the others in `unmapped[]`
with their year, so it is visible that they were seen and set aside rather than
missed.

Two things will not be in any document, and both must be said in `questions[]`
rather than assumed to be nil:

- **Self-assessment tax paid at the time of filing.** It is paid after the AIS
  and Form 26AS were last updated -- check the "Data updated till" date on each
  -- so a statement downloaded before filing cannot show it.
- **A challan paid so recently it has not reached the statement yet**, for the
  same reason.

`total_taxes_paid` is the sum of all four. If Form 26AS states its own total and
it differs from your sum, report your sum and put the difference in
`questions[]`.

## Challans

`bsr_code`, `date_of_deposit` (as `YYYY-MM-DD`), `challan_no` and `amount` are
all mandatory -- the return is rejected without them, and a transposed challan
number is a painful thing to discover after filing. Transcribe each digit from
the document; never reconstruct one from context.

Classify each as `advance_tax` or `self_assessment`. Advance tax is paid during
the financial year; self-assessment tax is paid after it ends, before filing.

## Watch for

- **The same TDS under two sections.** Banks sometimes report 194A interest
  across several branch entries. Keep them as separate rows -- they must
  reconcile row-by-row against the interest certificates on Schedule OS.
- **TDS belonging to someone else.** Joint accounts and clubbed income mean 26AS
  can show credit that is not wholly yours. If a row looks like a joint holding,
  flag it rather than claiming it all.
- **Form 26AS covers the financial year, not the assessment year.** Confirm the
  statement header says FY 2025-26 for AY 2026-27 and flag it if it does not.
- **AIS is not 26AS.** AIS lists reported transactions including ones with no TDS.
  Use it to find missing income, not as a source of tax credit.
