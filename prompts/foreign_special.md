version: foreign_special@7

# Schedules FSI, TR and FA — income earned outside India, and assets held there

Source documents: Form 1042-S and other foreign withholding certificates,
broker statements from outside India (Merrill, Alpaca, Interactive Brokers),
consolidated foreign-investment reports, foreign bank statements, RSU and ESPP
statements, and any foreign tax return.

This tab holds **three schedules and nothing else**: FSI, TR and FA. Anything
that belongs to Schedule SI or Schedule EI is not reported here.

## The one thing that catches everyone: two different periods

Schedules FSI and TR follow the **previous year** — 1 April to 31 March, like
the rest of the return. Schedule FA follows the **calendar year** — 1 January
to 31 December. They are different windows over the same holdings, and a
statement covering one is the wrong evidence for the other.

Put the calendar year Schedule FA covers in `calendar_year`. Never shift a
Schedule FA figure to make it agree with a Schedule FSI figure: a peak balance
in December and a dividend in February belong to different schedules and are
not supposed to reconcile.

## Schedule FSI — income from outside India and the relief on it

One entry per country, each carrying a row for **every** head of income in the
form's order:

| Item | Head |
|---|---|
| i | Salary |
| ii | House Property |
| iii | Business or Profession |
| iv | Capital Gains |
| v | Other Sources |

Report all five even where the amount is nil. The form prints all five, and a
head you left out cannot be told apart from a head that was nil.

### Head i, Salary: an RSU vest does not belong here

The perquisite on a vesting RSU or ESOP is **Indian salary**, not income from
outside India, when the employer is an Indian company and the employment was
exercised in India. The shares being a foreign company's does not make the
income foreign: what matters is where the employment was exercised and who
paid. Indian TDS is deducted on it, and no foreign tax is withheld on a vest,
so there is nothing to claim relief on.

It is already taxed in Schedule S at item 1b, under section 17(2)(vi). Putting
it in Schedule FSI as well would count it twice against Part B-TI and claim
relief for tax nobody paid abroad. **Head i stays nil** unless salary was
genuinely earned abroad.

The one case where head i is not nil: part of the vesting period was served
working in the other country and that country taxed the resulting perquisite.
That is a fact about where the person worked. Ask it in `questions[]`; never
infer it from the shares being foreign.

Per head:

| Column | Field | What goes in it |
|---|---|---|
| (c) | `income_outside_india` | The income **already included in Part B-TI**, not the gross before Indian treatment |
| (d) | `tax_paid_outside_india` | Tax actually paid or withheld abroad, as the foreign document states |
| (e) | `tax_payable_in_india` | Computed — leave it out unless the document states it |
| (f) | `relief_available` | The lower of (d) and (e) — also computed; leave it out |
| | `dtaa_article` | The treaty article, where relief is under section 90 or 90A |

Columns (e) and (f) are arithmetic and are worked out in code. Stating a
guess at them is worse than leaving them empty, because a figure in (f) is a
claim for money.

The US withholding on dividends is the common case: it is Other Sources, it is
article 10 of the India–US treaty, and the evidence is a Form 1042-S.

## Schedule TR — the same relief, summarised by country

One row per country: the total of column (d) of Schedule FSI for that country,
the total of column (f), and the section relief is claimed under — **90 or 90A
where a treaty applies, 91 where it does not.**

Item 4 asks a question directly: has any foreign tax, on which relief was
allowed in India, since been refunded or credited by the foreign authority?
Answer it. It is usually nil, and nil is an answer.

Relief under section 90 or 91 requires **Form 67 filed before the return**.
If nothing in the documents shows Form 67 was filed, say so in `questions[]` —
the relief is otherwise at risk, and it is the taxpayer's to fix.

## Schedule FA — what was held abroad, not what was earned

A disclosure, not an income figure. It is reported for the calendar year, by
category:

| Section | What it holds |
|---|---|
| `a1_depository_accounts` | Foreign bank accounts |
| `a2_custodial_accounts` | Broking and demat accounts abroad — a Merrill or Alpaca account holding vested shares |
| `a3_equity_and_debt` | Equity and debt interests in any entity — one entry per entity, carrying **every lot** in `acquisitions[]` |
| `a4_insurance_contracts` | Cash value insurance and annuity contracts |
| `b_financial_interest` | Financial interest in any entity |
| `c_immovable_property` | Immovable property |
| `d_other_capital_assets` | Any other capital asset |
| `e_signing_authority` | Accounts with signing authority, not already in A to D |
| `f_trusts` | Trusts abroad where the taxpayer is trustee, beneficiary or settlor |
| `g_other_income` | Any other income from a source outside India, not already above |

**A3: one entry per entity, with every lot inside it.** The form gives each
row one date of acquisition and one initial value, so each acquisition is
reported as its own row -- and those rows are built in code from the lots you
list. Your job is the facts: in `acquisitions[]`, every lot held at any time in
the calendar year, with its own date, its quantity and its cost. Do not merge
lots, do not average their dates, and do not leave the quantity out: without it
a lot cannot be valued or matched to a sale.

In `sales[]`, give one entry per lot sold where the document shows which lots
went -- a broker's realised-gain table usually does -- with `lot_acquired_on`
naming the lot. Where the document does not say, give the sale as one entry
and the lots are taken first-in, first-out.

Three rules:

- **An account and the holdings inside it are both reported.** A custodial
  account goes in A2 and the shares inside it go in A3. That looks like
  double-counting and is not: A2 discloses the account, A3 discloses the
  holding, and the form asks for both.
- **When in doubt, report it.** Schedule FA is a disclosure and omitting a
  foreign asset carries penalties under the Black Money Act that have nothing
  to do with how much tax was at stake. An asset you are unsure about goes in,
  with the doubt recorded in `questions[]`.

### Give dated facts; the rupee columns are worked out in code

Schedule FA's columns are in rupees, each converted at the State Bank of India
telegraphic transfer buying rate **on the date of that figure itself** — the
day of the peak, 31 December for the closing balance, the vest date for the
initial value, the day of each dividend or sale. That is a different rule from
Rule 115 for income, and it needs a date for every figure. So do not convert,
and do not pick the peak. Report what the documents state, in their own
currency, with dates:

| For | Field | What to give |
|---|---|---|
| A1, A2 | `valuations[]` | The account's total value on **every** date a statement gives one in the calendar year — each quarter-end or month-end, and 31 December |
| A1, A2 | `credits[]` | Each dividend, interest payment or sale credited, gross, with its date and nature |
| A3 | `acquisitions[]` | Every lot in the holding: date acquired (vest date for an RSU), quantity, cost |
| A3 | `valuations[]` | The holding's value on each date a statement gives one, and 31 December |
| A3 | `credits[]` | Each dividend on the holding, gross, with its date |
| A3 | `sales[]` | Each sale in the calendar year: date, quantity, gross proceeds |

The single-figure fields (`peak_value`, `closing_value`, `initial_value`,
`gross_credited` and the rest) are for a document that already states the
finished rupee figure — a broker's own Schedule FA report does. Where one
does, give it as stated. Where the document is in a foreign currency, fill the
dated lists instead and leave the single figures out.

In `credits[]` on an account, include sale proceeds as well as dividends and
interest, each with its nature: the form's own list of natures for an account
is interest, dividend, proceeds from sale or redemption, and other income.

Everything is limited to the calendar year. A dividend paid in January of the
following year belongs to next year's Schedule FA, even though it falls in
this financial year.

## Watch for

- **A peak balance that is not stated.** Many statements give only opening and
  closing. Say so rather than substituting the closing balance for the peak.
- **RSUs that vested during the year.** The vest date is the acquisition date
  for column (8), and the perquisite value taxed in Schedule S is the cost of
  acquisition under section 49(2AA).
- **An account closed during the year.** Still reported — it was held during
  the calendar year.
- **A joint account.** Reported in full, with the ownership status recorded.
