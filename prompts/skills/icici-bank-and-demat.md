---
name: icici-bank-and-demat
use_when: An ICICI Bank savings-account statement ("Statement of Transactions in Saving Account"), an ICICI Bank NSDL demat statement (DP ID IN303028), or an ICICI Direct / ICICI Securities report -- whatever the file is called.
schedules: [capital_gains, other_sources, assets_liabilities, general]
verified_from: An ICICI Bank savings-account statement, an ICICI Bank NSDL demat transaction-and-holding statement, and an ICICI Direct capital gains report, all April 2025 to March 2026.
---

# ICICI documents

ICICI file names are unreliable: in the verified set, a file named
`..._dividend_statement_...` was a demat statement and one named
`..._OpTransactionHistory...` was a savings account statement. **Identify
these by their first page, never their name.**

## Savings account statement

Headed "Statement of Transactions in Saving Account no. ..." with a period.

- **Not capital gains.** Interest credits are Schedule OS (with 80TTA or
  80TTB); dividend credits through NACH (`NACH ... <company name>`) are
  Schedule OS dividends; the account itself belongs in Part A-GEN (bank
  account) and, if required, Schedule AL.
- Credits described as sale proceeds of securities are evidence a sale
  happened, not a disposal row: the cost and dates are elsewhere.

## NSDL demat statement (ICICI Bank as depository participant)

Transaction and holding statement for a demat account, DP ID `IN303028`.

- **Debit (Dr) lines are deliveries out of the account** -- usually a sale
  through ICICI Securities, sometimes a transfer. They carry quantity and date
  but **no sale price, no cost and no acquisition date**, so they cannot
  become disposal rows. Exclude the document from Schedule CG as
  `no_transactions`, and list the debits in `questions[]` so each can be
  matched to a broker's capital gains report.
- A debit of old ISIN shares together with a credit of more shares of a new
  ISIN on the same date is a **split or bonus**, not a sale. The cost and
  acquisition date carry over to the new shares.
- A debit a day or two before 31 March may be a trade in one financial year
  settling in the next; the trade date decides the year.
- The corporate-benefits table lists dividend entitlements: Schedule OS.

## ICICI Direct capital gains report

Named `ICICIDIRECT_EQCapitalGainsDetails.xlsx` in the verified set, but it is
**not** an Excel file: it is tab-separated text, converted to CSV before you
see it. Three header lines (Account, Name, and "Capital Gain" with the
assessment year), then this row of column names:

    Stock Symbol, ISIN, Qty, Sale Average Rate, Sale Value, Sale Expenses,
    Purchase Average Rate, Price as on 31st Jan 2018,
    Purchase Price Considered, Purchase Value, Purchase Expenses, Profit/Loss(-)

A later download of the same report (`ICICIDIRECT_EQCapitalGainsDetail.xlsx`)
also carries `Sale Date`, `Sale Rate`, `Purchase Date` and `Purchase Rate`, one
row per lot. Read the header row in front of you rather than this list.

Under it, one heading line per bucket -- "Long Term Capital Gain (STT paid)",
and similarly for short term -- then that bucket's rows, then `Sub Total` and
`Total` lines in the second-to-last column. The file ends with a disclaimer
that the figures depend on the portfolio held on icicidirect.com.

- `Sale Value` is `full_value` and `Purchase Value` is `cost_of_acquisition`,
  both before charges. `Sale Expenses` is `transfer_expenses`. `Purchase
  Expenses` is **`purchase_expenses`**, not a transfer expense: it is part of
  the cost, and the computation adds it to the purchase value.
- `Profit/Loss(-)` is the report's own figure, net of **both** sets of
  expenses: `stated_gain`.
- The report does not break the expenses down or say whether STT is inside
  them. In the verified copies sale expenses ran at about 0.30% of sale value,
  which is brokerage, GST and exchange charges without the 0.1% STT -- but
  that is arithmetic about one account, not something the report states.
  Report the figures as stated and leave the question to the reviewer.
- `Price as on 31st Jan 2018` is the section 112A grandfathering price ->
  `fmv_31jan2018`. `NA` means the share was bought after that date; leave the
  field out rather than reporting "NA".
- `Purchase Price Considered` is what the report used after grandfathering.
  Report it only in `basis`; the computation applies the rule itself.
- **Dates may be missing.** The earlier copy carried neither the purchase nor
  the sale date; the later one carries both. Where they are present, use them.
  Where they are not, the bucket heading says what ICICI concluded -- put that
  in `stated_term` -- and say in `questions[]` that the dates are missing,
  naming each scrip. The demat statement for the same account gives the
  delivery-out date of each sale, which is the evidence for the sale date; a
  contract note gives the purchase date.
- The symbols are ICICI's own short codes (`ADFFOO`, `BALCHI`, `INDHOT`), not
  exchange tickers. Match them to the demat statement by **ISIN**, never by
  the code.
- Its `Sub Total` is what your rows must add up to, and its total sale value
  is the figure to compare against the "sale of listed equity" line in the
  AIS or TIS.
