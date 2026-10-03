---
name: zerodha-tax-pnl
use_when: A Zerodha (Console) tax P&L workbook -- sheets such as "Equity and Non Equity", "Tradewise Exits from <date>", "F&O", "Open Positions as of <date>", with a Client ID, Client Name and PAN at the top.
schedules: [capital_gains, books, other_sources]
verified_from: A full-year tax P&L workbook for April 2025 to March 2026 with 11 sheets and a 4,543-line Tradewise Exits sheet.
---

# Zerodha tax P&L workbook

## Sheets, and where each belongs

| Sheet | What it is | Where it goes |
|---|---|---|
| Tradewise Exits from <date> | every exit, one line each, in stacked sub-tables | the transactions -- see below |
| Equity and Non Equity | "Realized Profit Breakdown": Intraday/Speculative, Short Term, Long Term and Non Equity profit | `summary_only` -- reconcile your rows against it |
| Mutual Funds | mutual fund summary | `summary_only`, or `no_transactions` if all zero |
| F&O, Currency, Commodity | derivative summaries | `other_schedule`: Books (Schedule BP) |
| Equity Dividends | dividends | `other_schedule`: Schedule OS |
| Open Positions as of <start/end date> | positions held, not exited | `no_transactions` -- a held position is not a transfer |
| Other Debits and Credits | DP, AMC, pledge charges | `other_schedule` -- account costs, not tied to a disposal |
| Ledger Balances | funds balance with the broker | `no_transactions` |

## Tradewise Exits: several tables in one sheet

The sheet stacks sub-tables, each with a one-cell heading line and then its
own header line, and **different columns in different sub-tables**:

| Heading | Schedule | Notes |
|---|---|---|
| Equity - Intraday | Books: speculative business income | not capital gains |
| Equity - Short Term | CG, section 111A | |
| Equity - Long Term | CG, section 112A | |
| Equity - Buyback | see below | column is **Non-Taxable Profit**, not Taxable Profit |
| Non Equity | CG | ETFs, debt, gold and similar -- classify each by what it is |
| Mutual Funds | CG | |
| F&O | Books: non-speculative business income | thousands of lines; no ISIN column |
| Currency, Commodity | Books | |

Equity sub-tables' columns: `Symbol, ISIN, Entry Date, Exit Date, Quantity,
Buy Value, Sell Value, Profit, Period of Holding, Fair Market Value, Taxable
Profit, Turnover, Brokerage, Exchange Transaction Charges, IPFT, SEBI Charges,
CGST, SGST, IGST, Stamp Duty, STT`.

- Entry Date -> `acquired_on`, Exit Date -> `transferred_on`, Buy Value ->
  `cost_of_acquisition`, Sell Value -> `full_value`, Profit -> `stated_gain`.
- **Fair Market Value** is the 31-January-2018 price used for section 112A
  grandfathering -> `fmv_31jan2018`, when present. Taxable Profit already
  applies it; keep it out of the row and let the computation apply the rule.
- Buy Value and Sell Value are before charges: Profit is Sell Value less Buy
  Value exactly, on every row. The sheet does not say so in words.
- The charge columns after Turnover are the charges on **that exit**:
  `Brokerage, Exchange Transaction Charges, IPFT, SEBI Charges, CGST, SGST,
  IGST, Stamp Duty` together are `transfer_expenses`. Map the field to that
  list of columns and code adds them up, to the paisa. **`STT` is not among them**: it goes in `stt` and is deducted nowhere.
- The charges on the purchase are not in this workbook when the purchase was
  in an earlier year. Leave `purchase_expenses` out rather than guessing.
- The `Charges` table on the "Equity and Non Equity" sheet is the same charges
  totalled for the whole equity segment, intraday included. Do not share it
  out across rows; the per-row columns already carry each exit's own share.
- The sub-tables sit next to each other with no reliable blank line between
  them, so each needs its own mapping (its own header line). Map only the
  capital gains sub-tables for Schedule CG.

## Traps

- **Non Equity is not one asset class.** An ETF of shares, a gold ETF, a debt
  fund and a specified mutual fund under section 50AA (always short-term) are
  taxed differently. Classify each symbol; when you cannot tell, say so.
- **Buybacks** after 01-10-2024 are taxed as a deemed dividend in Schedule OS;
  the proceeds are not capital gains, though the cost may create a capital
  loss. Flag them in `questions[]` rather than folding them into CG.
- The summary sheet's figures are the reconciliation target: the rows you
  report for each sub-table should add up to its Profit line.
