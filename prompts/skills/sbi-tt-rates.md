---
name: sbi-tt-rates
use_when: A foreign-currency amount has to be converted to rupees for the return, and the State Bank of India telegraphic-transfer buying rate for a given date is needed.
schedules: [fx_rates]
verified_from: The sbi-fx-ratekeeper archive of SBI forex card rates, checked for USD in August 2025.
archive_url: https://raw.githubusercontent.com/sahilgupta/sbi-fx-ratekeeper/main/csv_files/SBI_REFERENCE_RATES_{CUR}.csv
---

# SBI telegraphic-transfer buying rates (Rule 115)

## Which rate, which date

Rule 115 of the Income-tax Rules converts foreign-currency income at the
**telegraphic transfer buying rate (TT BUY) of the State Bank of India**. Not
TT SELL, not the bill or card rates, not the RBI reference rate.

The date is fixed by the rule; for capital gains it is the last day of the
month before the month of transfer. You are always given the date needed --
do not work it out again.

**If no rate was published for that date** -- a Sunday, a bank holiday -- the
rule itself is silent. The settled practice is the rate for the nearest earlier
date that has one; use that, and say in `note` which date you used and that it
is a holiday fallback. Never use a later date, and never average.

## Where the rates are

SBI publishes a forex card rate PDF every business day but keeps only the
current one online. The sbi-fx-ratekeeper project archives each day's PDF and
transcribes it into one CSV per currency (the `archive_url` above, with `{CUR}`
the ISO code). The archive for each currency you need is downloaded before you
start and listed below with its path; read it there -- search it for the dates
you need rather than reading it whole. Columns:

    DATE,PDF FILE,TT BUY,TT SELL,BILL BUY,BILL SELL,FOREX TRAVEL CARD BUY,FOREX TRAVEL CARD SELL,CN BUY,CN SELL

- `DATE` is `YYYY-MM-DD HH:MM`, the time the card was published.
- `PDF FILE` links to SBI's own card for that day -- the primary evidence.
- `TT BUY` is the rate you want.
- Coverage starts in January 2020. Early rows can show `0.00` for TT BUY; a
  zero is not a rate.

## Traps

- **More than one card in a day.** SBI sometimes revises the card during the
  day, and the archive then holds two rows for one date. Use the first one
  published that day, and mention the later one in `note`.
- A row dated with a time is still that calendar date; do not shift it.
- Nothing else on the internet is a substitute. If this archive does not have
  the date, report that the rate could not be found rather than taking a
  figure from a blog, a converter site or a different bank.
