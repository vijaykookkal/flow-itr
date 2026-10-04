version: plan@1

# Planning notes

Source documents: notes about the year that is still running. A text file or
email the taxpayer wrote ("salary from October will be ...", "planning to sell
the 2024 RSUs in January"), a spreadsheet of expectations, an offer or
increment letter, a CTC statement, a vesting schedule, a list of investments
meant for 80C.

These are **expectations, not evidence**. None of this enters the return. It
feeds the Planning page's projection of the year, where it is set beside what
the payslips, Form 16 and statements already show. So the job here is to say
precisely what each note expects, with the period it expects it for, so that
the arithmetic can be done -- and checked -- in code.

## What to produce

`expectations[]`, one entry per figure a document expects. Each takes:

| Field | What goes in it |
|---|---|
| `kind` | `salary`, `bonus`, `interest`, `dividend`, `other_income`, `capital_gain`, `deduction` or `tds` |
| `description` | the document's own words for it |
| `amount` | the figure as stated, in rupees, with `cite` and `basis` |
| `per` | `month` if it recurs monthly, `year` if it is for the whole financial year, `once` for a single payment or sale |
| `from_month`, `to_month` | for a monthly amount, the months it applies to (`YYYY-MM`), where stated |
| `on` | for a one-off, the date it is expected, where stated |

`as_of` is the date the note was written or speaks from, where it says.

## The rules that matter here

- **Transcribe the period, do not multiply it out.** "Rs 3.5 lakh a month
  from April" is `amount` 350000, `per` "month", `from_month` "2026-04". Do not
  turn it into an annual figure; code does that, for the months of this
  financial year only.
- **One entry per figure.** A monthly salary and a bonus are two entries. Two
  planned sales are two entries.
- **CTC is not salary.** Cost to company includes the employer's provident fund,
  gratuity and similar amounts that are never paid as salary. If a document
  gives only CTC, record it as stated, with `description` saying it is CTC, and
  say in `questions[]` that gross salary is usually lower.
- **A planned sale** is `capital_gain`. `amount` is the expected gain or loss,
  `direction` says which, `asset_class` says what is sold (`equity_stt` for
  shares listed in India and equity funds, `foreign_shares` for shares listed
  abroad such as RSUs), `acquired_on` is when it was bought or vested and `on`
  when it is to be sold, where stated. Set `term` only where the note itself
  says short- or long-term: the holding period is worked out in code from the
  dates. If the note gives a sale value but no gain, put the sale value in
  `questions[]` rather than guessing the cost.
- **A deduction** is `deduction` with its `section`: PPF, ELSS, life insurance
  and principal on a home loan are 80C; health insurance is 80D; the extra NPS
  contribution is 80CCD(1B); the employer's NPS contribution is 80CCD(2).
- **Evidence is not an expectation.** A payslip, Form 16, broker statement or
  bank statement says what has happened, and belongs to its schedule even in
  the middle of the year. Do not copy figures from one into this tab. Only
  what a document says is still to come belongs here.
- **Never fill a gap.** If a note says "bonus, maybe" with no figure, put it in
  `questions[]`, not in `expectations[]` with an amount you chose.
