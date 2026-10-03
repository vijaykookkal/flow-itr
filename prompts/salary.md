version: salary@2

# Schedule S - Salary

Source documents: Form 16 (Part A and Part B), salary slips, perquisite
statements, Form 12BA, and any employer letter revising the above.

## What to produce

One entry in `employers[]` per employer TAN. A mid-year job change means two
entries, not a merged one -- Schedule S is reported employer-wise and the TANs
have to match Schedule TDS1.

For each employer, take these straight from Form 16 Part B:

| Field | Form 16 Part B |
|---|---|
| `salary_17_1` | item 1(a), salary under section 17(1) |
| `perquisites_17_2` | item 1(b), perquisites under section 17(2) |
| `profits_in_lieu_17_3` | item 1(c), profits in lieu under section 17(3) |
| `gross_salary` | item 1(d), total |
| `exempt_allowances[]` | item 2, one row per section 10 exemption, each with its clause (`10(13A)`, `10(5)`, `10(14)`) |
| `net_salary` | item 3, salary received from this employer after section 10 |

### The breakup, where a document gives one

A single figure of a crore for "perquisites" is not reviewable, and the
documents almost always itemise it. Where they do, fill these in:

| Field | Where it comes from |
|---|---|
| `salary_17_1_components[]` | The salary annexure or slip behind item 1(a): basic, house rent allowance, special allowance, bonus, leave encashment and so on |
| `perquisites_17_2_components[]` | **Form 12BA**, which exists for exactly this purpose: one row per serial number, with the description the form prints |

Each component carries the wording the document uses, its `ref` (the Form 12BA
serial number, or the annexure line), and its amount.

Two rules about these arrays:

- The components must add up to the total on the line above them. If they do
  not, report them as stated and say so in `questions[]` -- do not adjust a
  component to force the total, and do not invent a balancing row.
- If no document itemises a figure, leave the array out altogether. An empty
  array says "itemised, and the breakup is nil", which is a different and
  false claim. A missing array says "no document broke this down", which is
  the truth.

An RSU or ESOP perquisite matters beyond this schedule: the amount taxed here
is the cost of acquisition under section 49(2AA) when those shares are later
sold, so naming it here is what lets Capital Gains be checked against it.

`deductions_16` and `income_chargeable` are return-level, not employer-level.
Where there are several Form 16s, `income_chargeable` is the figure for the
return as a whole; if the documents only give per-employer figures, leave it
out and say so in `questions[]`.

## Things that are specifically not Schedule S

Put these in `unmapped[]`:

- **Relief under section 89.** Belongs in Part B-TTI and needs Form 10E.
- **Employer NPS contribution under 80CCD(2).** It is inside gross salary, and
  the deduction is claimed on Schedule VI-A, not here.
- **TDS figures.** Form 16 states the tax deducted, but that belongs to
  Schedule TDS1 and is extracted from Form 26AS instead. Do not report it here.
- **Anything on Form 16 Part A** beyond identity and period.

## Watch for

- **Two Form 16s with overlapping periods.** Usually one is a superseded draft
  or a revised certificate. Do not add them together -- ask.
- **The standard deduction differs by regime** (section 16(ia)). Report what the
  document says; the regime decision is made elsewhere.
- **Professional tax under 16(iii) and entertainment allowance under 16(ii)** are
  not available under the section 115BAC default regime. If the Form 16 claims
  them, report them as stated and raise it in `questions[]`.
- **Arrears.** If any figure is described as arrears or as relating to an earlier
  year, flag it -- it interacts with section 89.
