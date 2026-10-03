# Deciding what to leave out

These rules apply to every schedule and every pass. The folders you are given
are a person's whole document dump for the year, not a curated set for this
schedule, so most of what you see will not belong here. Leaving a document out
is often the right call. Leaving one out *without saying so* never is.

Every document you do not use goes in `excluded[]` (in a table plan) or
`unmapped[]` (in an extraction), with a reason a person can check in one
glance. Name the document exactly as it is listed below.

## Leave it out when

1. **It duplicates another document.** The same statement often arrives more
   than once: as a PDF and a Word or Excel export, as a full download and a
   trimmed copy, or as two downloads of one period. Read the most complete
   copy -- the one covering the longest period, with the most pages, in the
   most readable form -- and leave the others out, naming the copy you read
   instead: "duplicate of `<file>`, which covers the same account and period".
   If two copies disagree, that is not a duplicate; read both and raise the
   difference in `questions[]`.

2. **It belongs to another schedule.** Say which one: "dividends -- Schedule
   OS", "F&O -- Schedule BP", "foreign holdings -- Schedule FA". The same
   document can be relevant to several schedules; take only this schedule's
   part and leave out the rest with the same kind of note.

3. **It only summarises what other documents state in detail.** The AIS, the
   TIS, Form 26AS and a broker's summary sheet report aggregates. They are for
   reconciliation, never a source of rows: do not create a row from them. Use
   them to check completeness instead -- when a summary reports a transaction
   that no detailed document accounts for, raise it in `questions[]` with the
   figure, because that is how a missing statement is found.

4. **It could not be opened.** Some documents are left out before you see
   them because they are password-protected with a password that is not
   available, or hold no readable content at all. They are listed under
   *Left out before you saw them* with the reason. Do not guess what they
   contain from their names. If one of them looks likely to matter for this
   schedule, say so in `questions[]`, naming it, so a person can supply a
   readable copy.

   The same applies to any document you try to read and cannot. Say that you
   could not read it, and why -- "could not read `<file>`: exceeds the size
   limit". Never describe a document you have not actually read as excluded
   by choice: an unread document is a gap in the return, not a decision.

## Do not leave it out because

- **It is long, or tedious.** Thousands of rows is a reason to be careful,
  not a reason to skip.
- **It is in an unfamiliar format.** A foreign brokerage statement, a demat
  transaction statement or a scanned page is still a document; read it.
- **Its figures are in another currency.** Report them as stated and say so;
  conversion is done downstream.
