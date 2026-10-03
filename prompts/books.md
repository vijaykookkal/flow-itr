version: books@4

# Part A-BS, Part A-P&L and Part A-OI - Books of account

Source documents: trial balance, balance sheet, profit and loss account, the
audit report in Form 3CA/3CB and its annexure 3CD, and broker tax P&L reports
where trading is a business.

## Report the form's own lines

The schema mirrors the ITR-3 structure, and each field carries its item number.
Transcribe the figures against those lines. Do not restate the accounts and do
not compute totals the documents do not give.

## Trading is business income, and it splits three ways

This is the distinction that most often goes wrong:

- **F&O (derivatives)** is a **non-speculative** business. Its turnover decides
  whether a section 44AB audit is required.
- **Intraday equity** is a **speculative** business. Its losses set off only
  against speculative income, and carry forward four years rather than eight.
- **Delivery-based equity** is capital gains, not business income at all, and
  belongs on Schedule CG.

A broker tax P&L usually holds all three in one workbook. Take the first two
here and note in `unmapped[]` that the delivery rows belong to Schedule CG.

## Book depreciation is not tax depreciation

`depreciation_in_books` is what the accounts charged. Depreciation allowable
under the Income-tax Act is computed block-wise on the Depreciation tab, and
the difference is an adjustment in Schedule BP. Never substitute one for the
other.

## Part A-OI carries the adjustments

Amounts disallowed under sections 43B, 40(a) and 40A(3) come from the 3CD
annexure. These flow into Schedule BP, so capture them even when the accounts
show no corresponding entry.

## Watch for

- **Balance sheet must balance.** If total assets and total liabilities differ,
  report both as stated and raise it in `questions[]` - do not adjust either.
- **The no-accounts case.** Where books are not maintained, only Part A-P&L
  item 61 applies. Set `books_maintained` to false and fill `no_accounts_case`.
- **Presumptive taxation** under 44AD/44ADA/44AE is a different computation
  altogether. If the documents point that way, say so in `questions[]`.


## Charges are business expenses, and they are not optional

A broker's tax P&L states the realised profit **gross**, then lists the
charges separately -- brokerage, exchange transaction charges, STT, SEBI fees,
stamp duty, GST, clearing charges. Every one of them is a deductible expense
of that business, so a return that takes the profit and ignores the charges
pays tax on money that was never earned. Securities transaction tax is
deductible here precisely because this is business income, not capital gains.

Put each charge in `charges[]` on the segment it belongs to -- `derivatives`
for F&O, `speculative` for intraday -- one row per head, named as the
statement names it, with its amount. **Do not add them up.** The sheet rarely
states a total, and the sum is arithmetic that code does; if the statement
does state a total, put that in `expenses` as well so the two can be checked
against each other.

Charges that belong to no single segment -- depository (DP) charges, annual
maintenance, pledge charges, platform fees -- go in
`other_expenses_of_business[]`.

Where a charge may already be netted off the profit figure, say so in its
`note` rather than leaving it out: deducting it twice and not at all are both
wrong, and only a person can settle which.

## Invoices and bills

Expenses also arrive as loose invoices -- a broadband or mobile bill, a
software subscription, a piece of equipment. Read them and report each one in
`other_expenses_of_business[]` with the supplier, the invoice date and the
amount as the invoice states it.

Take the document at its face value. An invoice the taxpayer has put in the
source folder is business evidence: report the amount the invoice states, in
full. Do not apportion it between business and personal use, do not ask what
proportion is business, and do not hold the figure back pending an answer.
That call belongs to the person filing the return and they have made it by
supplying the document.

An invoice addressed to the taxpayer personally, with no business GSTIN, is
not thereby disqualified -- a proprietor's business has no separate legal
identity.

Two things are still not face value, because they are arithmetic and law
rather than judgement:

- **The year.** An invoice dated before the first day of this previous year
  belongs to an earlier one. Report it with its date and say so in the `note`;
  do not put it in this year's expenses.
- **Capital or revenue.** A laptop, a monitor, a phone is not an expense at
  all: it is an asset, and relief comes through depreciation under section 32,
  over its life. Do not put it in `other_expenses_of_business[]`. Report it in
  `assets_acquired[]` with its description, its invoice date and its cost, so
  the Depreciation tab can carry it into Schedule DEP.
