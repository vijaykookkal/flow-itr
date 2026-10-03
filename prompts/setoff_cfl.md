version: setoff_cfl@1

# Losses brought forward — the opening position for Schedules BFLA and CFL

Source documents: last year's income-tax return, the intimation under section
143(1) for that year, or an assessment order — whichever shows the losses that
were carried forward into this year.

## What this schedule is for

Schedules CYLA, BFLA and CFL are computed. The one thing no computation can
supply is what was carried in from earlier years, and that is all you extract
here: each loss still being carried forward at the end of last year, by the
assessment year it arose in and its kind.

Rule 7 of the shared rules says a return already filed is not evidence. That
rule is about the return for the year being worked on. An **earlier** year's
return is read here for one thing only — its Schedule CFL and Schedule UD,
the "total loss carried forward to future years" — because that closing
position is this year's opening position. Take nothing else from it. Not its
income, not its tax, not its method.

## What to produce

`brought_forward[]`, one row per assessment year and kind of loss:

| Field | What it is |
|---|---|
| `ay_of_origin` | The assessment year the loss arose in, as `2023-24` |
| `kind` | One of the kinds below |
| `amount` | The amount still carried forward at the end of last year — after last year's own set-off, not the original loss |
| `return_filed_on` | The date the return for that year was filed, where Schedule CFL prints it |
| `source_return_ack` | The acknowledgement number of the return it was read from |

Kinds, and the Schedule CFL column each one is:

| `kind` | Column |
|---|---|
| `house_property` | House property loss |
| `business_non_speculative` | Loss from business other than speculative and specified business |
| `business_speculative` | Loss from speculative business |
| `specified_business_35AD` | Loss from specified business |
| `short_term_capital` | Short-term capital loss |
| `long_term_capital` | Long-term capital loss |
| `other_sources_race_horses` | Loss from owning and maintaining race horses |
| `unabsorbed_depreciation` | Schedule UD, not Schedule CFL: unabsorbed depreciation |

Use the **last row** of last year's Schedule CFL for each year — what remained
to be carried forward — and keep the years separate. A single total across
years cannot be used: each year's loss has its own expiry, and the oldest must
be spent first.

## Watch for

- **The intimation differs from the return.** Where a section 143(1)
  intimation or an order changed the loss, the intimation is the figure that
  stands. Report it, and say in `questions[]` that the two differ.
- **A return filed after its due date.** A loss other than a house-property
  loss or unabsorbed depreciation cannot be carried forward from a year whose
  return was filed late (section 80). Report the loss as the document shows it
  and raise the filing date in `questions[]`; do not drop it yourself.
- **A year with no loss.** Leave it out. A row of nil adds nothing.
- **Nothing carried forward at all.** Return an empty `brought_forward[]` and
  say in `questions[]` which document showed that. An empty list from a
  document that was read is a statement; an empty list from no document is not.
