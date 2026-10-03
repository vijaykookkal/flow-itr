# Reading this schedule's documents

Read every document listed below and work out the transactions in it that
belong to this schedule. That is the whole job, and it is the same job whatever
the format: a broker's spreadsheet, a US brokerage statement in PDF, a demat
statement, a Word export. You report what you find in one of three lists, and
**every listed document goes in exactly one of them.**

## 1. `read_directly` -- the normal case

For each document you read, give its transactions as `rows`, in this
schedule's row shape (below). Put the rows under the document they came from,
and say in `why` what the document is and where in it the rows sit -- "the
realised gains section of the July-September quarterly statement".

- One row per transaction, exactly as the document states it. A sale reported
  as six lots is six rows.
- Amounts as the document states them. A figure stated only in a foreign
  currency is recorded with `currency` and `amount_foreign`, never converted.
- Every money value carries `cite` and `basis`, as in the extraction rules.
- A document you read that holds nothing for this schedule goes in `excluded`
  with kind `no_transactions`, not here with empty rows.

## 2. `tables` -- a shortcut for very long tables

When a table runs to more than about fifty transactions, you may map its
columns instead of transcribing it, and code will read every row against your
mapping. Deciding that "Exit Date" means `transferred_on` is judgement; copying
four thousand trades is not, and doing it by hand loses rows.

1. **Find the header row.** Exports usually carry a title, the client name and
   PAN, and a blank line before the real headers. `header_row` is the 1-based
   row holding the column names, as numbered in the preview.
2. **Map only columns that exist.** A wrong mapping is worse than a missing
   one: it produces confident numbers in the wrong box.
3. **Use `require_columns` only for identity** -- a symbol or ISIN, and a date,
   that every genuine row carries. Never name a money, charge, tax or remark
   column: stamp duty, STT and brokerage are blank on most rows, so requiring
   one discards nearly the whole file. If more rows are skipped than kept, the
   plan is rejected and you will be asked to fix it.
4. **A money field spread over several columns** is mapped to the list of
   those columns -- `"transfer_expenses": ["Brokerage", "Exchange Transaction
   Charges", "CGST", "SGST"]` -- and code adds them for every row, to the
   paisa, before rounding once. Adding up is code's job: use this even for a
   short table rather than doing the sum yourself.
5. **One sheet often stacks several tables** -- equity short term, long term,
   mutual funds, F&O -- each with its own heading, header row and columns. The
   preview lists the sub-table headings it can see. Give every sub-table you
   need its own entry, same file, different `header_row`, with
   `stop_at_blank: true`.

A short table is quicker and safer to transcribe into `read_directly`, unless
one of its fields has to be added up from several columns.

## 3. `excluded` -- everything that contributes no rows

Each with a `kind` and a `why`, following the rules for leaving documents out:

| kind | when |
|---|---|
| `duplicate` | another listed document holds the same material -- name it |
| `other_schedule` | it belongs elsewhere -- name the schedule |
| `summary_only` | aggregates such as the AIS, TIS or a summary sheet, used only to check completeness |
| `no_transactions` | you read it and it holds nothing for this schedule |
| `unreadable` | you could not open or read it -- a gap in the return, never a choice |

A converted file (a CSV of a spreadsheet sheet, a text of a PDF) stands for its
original: whatever you decide for one, the other needs no separate entry.

## Getting it wrong is visible

Row counts, totals, and any row that fails to validate are reported to the
reviewer, and the plan is saved alongside the run. An honest gap is always
better than a complete-looking answer that guesses.
