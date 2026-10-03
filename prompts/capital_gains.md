version: capital_gains@3

# Schedule CG - Capital Gains

Source documents: whatever records a transfer -- broker tax P&L statements,
mutual-fund registrar capital gains reports, foreign brokerage statements,
contract notes, demat transaction statements,
sale and purchase deeds for property, and 31-Jan-2018 price evidence.

## Produce a ledger, not totals

One row in `disposals[]` per **exit**, with its own dates and amounts. Do not
aggregate, do not group by scrip, do not sum anything.

This matters more here than on any other schedule. The rate that applies to a
row depends on its asset class, its holding period **and its transfer date**,
and the rules changed on 23 July 2024. Two sales of the same share in one year
can attract different rates. A total loses exactly the information needed to
compute the tax, so `engine/` derives every Schedule CG box from these rows.

`totals` is only for figures the **document itself** states, so the ledger can
be reconciled against them. Never put your own arithmetic there.

## Asset class decides the section

| `asset_class` | What it covers |
|---|---|
| `equity_stt` | Listed shares and equity-oriented mutual funds where STT was paid - sections 111A and 112A |
| `equity_unlisted` | Unlisted or pre-IPO shares, ESOP/RSU sales where no STT was paid |
| `debt_mf_specified` | Specified mutual funds under section 50AA - **always short-term**, whatever the holding period |
| `debt_mf_other` | Other debt funds and fund-of-funds |
| `bonds_debentures` | Listed and unlisted bonds, NCDs |
| `immovable_property` | Land and buildings |
| `gold_jewellery` | Gold, jewellery, sovereign gold bonds sold before maturity |
| `foreign_shares` | Shares on a foreign exchange - also relevant to Schedule FA |
| `other` | Anything else; name it clearly in `description` |

If you cannot tell an equity fund from a debt fund, say so in `questions[]`
rather than picking one. The two are taxed very differently.

## Dates are not optional

`transferred_on` is mandatory on every row. `acquired_on` is mandatory unless
the document genuinely does not give it, in which case say so in `questions[]` -
without it the holding period cannot be determined and the row cannot be taxed.

Use `YYYY-MM-DD`. Broker statements often carry a full timestamp; keep the date
part only.

## Grandfathering under section 112A

For `equity_stt` acquired **before 01-02-2018**, the cost is substituted by the
higher of actual cost and the lower of (31-Jan-2018 fair market value, sale
consideration). Report `fmv_31jan2018` when the document gives it, and leave it
out entirely when it does not - do not guess a price. `engine/` applies the
substitution; you only supply the inputs.

## Charges on buying and on selling

Section 48 takes two things off the sale consideration: expenditure incurred
wholly and exclusively in connection with the transfer, and the cost of
acquisition. A charge belongs to one or the other by which trade it was paid
on, and one charge belongs to neither.

- **Charges on the sale** go in `transfer_expenses`: brokerage, exchange
  transaction charges, SEBI turnover fees, stamp duty, GST and the like.
- **Charges on the purchase** go in `purchase_expenses`: the same kinds of
  charge, paid when the asset was bought. They are part of the cost of
  acquisition. `engine/` adds them to `cost_of_acquisition`, so report
  `cost_of_acquisition` as the purchase value the document states and never add
  them in yourself.
- **Securities transaction tax** goes in `stt` and nowhere else. Section 48
  allows no deduction for it on either trade. Never include it in
  `transfer_expenses` or `purchase_expenses`.

Report each as the document states it **for that row**. Where a table spreads
the charges over several columns -- brokerage, exchange charges, GST -- map the
field to the list of those columns in `tables` and code adds them up; do that
even for a short table, because adding is code's job. If you write the rows
yourself, give the sum the row's own figures make and quote every part in
`basis`.

Do not share out a charges total that the document gives only for the whole
account or the whole segment: it is not stated for any one sale. Leave it out
and say so in `unmapped[]`, with the amount.

Say in `basis` on `full_value` whether the figure is before charges or already
net of them. A sale value already net of charges must not have the same charges
reported again. If a document gives one expenses figure and shows that STT is
inside it, report it as stated and raise it in `questions[]`.

A document's own gain may be before charges, after selling charges only, or
after both. Report it in `stated_gain` exactly as stated; `engine/` works out
which and says so.

## What not to do

- **Do not compute the gain.** Report `full_value` and `cost_of_acquisition` as
  stated. If the document also states a gain, put it in `stated_gain` so the two
  can be compared; if they disagree, that is a finding, not something to fix.
- **Do not classify short or long yourself.** Put the document's own
  classification in `stated_term` if it gives one. The dates decide it.
- **Do not apply indexation.** For transfers on or after 23-07-2024 indexation
  is generally gone and the rate is 12.5%; before that date the old regime may
  apply. That branch belongs in code, not in an extraction.

## Things that are not Schedule CG

Put these in `unmapped[]`:

- **F&O and intraday equity.** These are *business* income under Schedule BP -
  non-speculative for F&O, speculative for intraday equity. A broker tax P&L
  usually contains both; take only the delivery-based capital gains here and
  note in `unmapped[]` that the F&O and intraday sheets belong to Books.
- **Dividends.** Schedule OS, even when the broker reports them alongside gains.
- **Virtual digital assets.** Schedule VDA, taxed at a flat 30% with no set-off.
- **Buyback proceeds after 01-10-2024**, which are taxed as a deemed dividend
  under Schedule OS rather than as capital gains.

## Watch for

- **Corporate actions.** Bonus shares have nil cost; splits change quantity but
  not total cost; demergers apportion it. If a row's cost looks impossible,
  flag it rather than reporting a gain equal to the full sale value.
- **Open positions carried into the next year** are not disposals. Exclude them.
- **A trade-wise sheet may repeat a scrip many times.** That is correct;
  each exit is its own row with its own dates.
