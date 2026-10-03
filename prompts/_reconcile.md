# Reconciling a schedule against what was reported about it

The income-tax department already holds figures about this taxpayer, reported
to it by banks, brokers, registrars and employers. Your job is to read those
figures out of the summary documents and say which computed figure each one
should equal.

You are not being asked whether the return is right. The return's own figures
are computed from the ledger and are listed below; you match lines to them and
explain differences. Never restate, adjust or "correct" a computed figure.

## How to work

1. **Read every summary document listed** -- the AIS, the TIS, Form 26AS, and
   any broker or registrar summary. Take every line that states an amount for
   this schedule.

2. **Copy the document's own wording** into `category`, and its information
   code into `code` when it has one. Do not translate or tidy it.

3. **Quote the amount** in `reported`, with `cite` naming the document and
   where in it, exactly as the extraction rules require.

4. **Map it to one computed measure** by `key`, from the list below, and say
   how it relates to it in `relation`:

   - `equals` -- this one line covers the same ground as the whole measure.
     The TIS category totals are like this.
   - `part_of` -- it is one component: a figure reported by a single broker,
     depository or registrar, or for one bucket. Every component of a measure
     is added up and the total compared once. **Use this whenever the line
     covers only part of what the measure covers**; comparing one broker's
     figure against the whole ledger produces a difference that means nothing.
   - `none` -- nothing here is comparable, and `measure` must be null.

   If no measure is comparable, use `null` with `relation: "none"` and say why:
   - the line reports **purchases**, and this schedule holds sales;
   - the line belongs to a **different schedule** -- then also set
     `belongs_to`, so it can be picked up there;
   - the line is an **aggregate of things already counted separately**, which
     would double-count if compared.

5. **Account for the difference, in figures.** Where the reported amount and
   the computed measure differ, break the difference into parts in
   `accounted_by`, each with what it is and a signed amount -- positive where
   the reported figure is the larger. Code adds them up and checks they come
   to the difference exactly; a difference whose parts do not add up is
   reported as unexplained however well argued, so do not put an explanation
   there you cannot quantify.

   Typical parts: a sale no Indian source reports (foreign shares), a document
   still missing from the folder, gross against net of charges, a transaction
   settling in another year.

   If you cannot account for it, leave `accounted_by` out and say so in
   `questions[]` with both figures. An unexplained difference is a finding,
   not a failure -- it is the whole point of doing this.

6. **Nothing is reported for a measure?** That is not a line. Say it in
   `questions[]` only if it looks wrong, for instance a large sale value the
   department appears not to know about.

## What a difference usually means

- **Reported more than the return shows**: a sale missing from the return, a
  document not yet in the folder, or a source reporting gross proceeds while
  the ledger records net.
- **The return shows more than reported**: transactions no Indian source has
  to report, above all foreign holdings; or a source that has not filed.
- **Small differences**: reporting in whole rupees against paise in a broker's
  file. Say so rather than leaving it unexplained.
