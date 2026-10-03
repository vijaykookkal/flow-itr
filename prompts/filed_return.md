version: filed_return@1

# A return already filed — transcription, not computation

Source documents: the filed ITR-V, the acknowledgement, the filed JSON, or the
PDF the e-filing utility produces. Anything that shows what was actually
submitted.

## What this schedule is for

Every other schedule in this tool works out what the return *should* say. This
one records what a return *does* say, so the two can be set side by side and
every difference named. It is the only schedule where being right is not the
objective: being faithful is.

Rule 7 of the shared rules -- a filed return is not evidence -- is about every
*other* schedule. Here the filed return is the document being transcribed, and
nothing you transcribe is used to compute anything: it is only ever shown
beside the figures the other schedules reached on their own.

## The one rule

**Transcribe. Do not compute, correct, reconcile or tidy.**

If the document prints a figure that is arithmetically wrong, transcribe the
wrong figure. If a line is nil, transcribe the nil. If a line's number looks
misprinted, transcribe it as printed. The comparison is worthless if the
transcription has already quietly fixed the thing being compared, and a
difference that turns out to be a typo in the filed return is exactly the kind
of finding this schedule exists to surface.

## What to produce

`part_b_ti[]` and `part_b_tti[]`: **every** line the document prints, in
printed order, including lines whose amount is nil. Each line carries:

| Field | What it is |
|---|---|
| `item` | The line number exactly as printed — `1`, `3i`, `4ai`, `12c`. Character for character. Do not renumber, expand or normalise it. |
| `label` | The line's wording as printed |
| `amount` | The figure as printed |

A line you leave out cannot be compared, and once it is missing there is no
way to tell it apart from a line that agreed. Nil lines matter most of all:
"the filed return claimed nothing here" and "we do not know what the filed
return said here" are completely different statements.

`schedules[]` is optional and useful: where the document also prints schedule
totals — Schedule S item 6, Schedule BP item A38, Schedule OS item 6, Schedule
CG — record them, so a difference in Part B-TI can be traced to the schedule it
came from rather than merely observed.

`identity` establishes that this document is the return for this person and
this year: form, assessment year, PAN, acknowledgement number, date filed, and
the section it was filed under.

## Watch for

- **More than one filed return for the year.** A revised return under section
  139(5) supersedes the original entirely. If the folder holds both, transcribe
  the one being compared and say in `questions[]` that another exists, with its
  acknowledgement number and date. Do not merge them.
- **A return for a different assessment year.** Common, because people keep
  them in one folder. Check `identity.assessment_year` against the profile's
  year and raise it in `questions[]` rather than transcribing it as this year's.
- **A draft or a pre-filled JSON that was never submitted.** It has no
  acknowledgement number. Say so; it is still worth transcribing, but it is not
  a filed return and must not be described as one.
- **An ITR-V that prints only totals.** Many acknowledgements carry a dozen
  summary lines rather than the whole of Part B-TI. Transcribe what is there
  and do not invent the rest — `questions[]` is where to say the document is a
  summary.
