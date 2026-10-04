version: classify@3

# Routing documents to ITR-3 schedules

You are given every document in one assessment year's folder. Decide which
ITR-3 schedule tabs each one belongs to. You are **not** extracting any figures
here — only routing.

## How to work

1. **Start from the listing.** Most Indian tax documents are named well enough
   to classify: `Form 16 Part B_...pdf`, `Form26AS_...pdf`, `taxpnl-...xlsx`,
   `AxisBank_savings_...xlsx`.

2. **Open anything you cannot place from its name.** `Multiple_Statements_Download (1).pdf`
   and `STMT_12312025_XXXXX506_1042S.pdf` tell you little; read them. Set
   `opened: true` when you do. Reading the first page is normally enough — you
   are identifying the document, not extracting from it.

3. **Never guess silently.** If you still cannot tell, set `confidence: "low"`,
   put your best guess in `tabs`, and say plainly in `why` that it is a guess.
   A low-confidence answer that says so is useful; a wrong high-confidence one
   is worse than no answer at all.

4. **A document may belong to several tabs, and often does.**
   - A broker tax P&L covers equity capital gains **and** F&O, which is business
     income — so `["capital_gains", "books"]`.
   - Form 26AS is `["taxes_paid"]`, but AIS also evidences income you might
     otherwise miss, so AIS can be `["taxes_paid", "other_sources"]`.
   - A bank statement can evidence savings interest **and** business receipts.
   - `general` is the person's identity and their bank accounts. The AIS and
     Form 26AS state the name, PAN, date of birth and address as the department
     holds them, so they go to `general` as well as to their other tabs; so does
     a PAN card, and every bank statement, because each account held has to be
     listed there.
   Assign every tab that genuinely needs to read it. Over-assigning costs a
   little context; under-assigning loses income from the return.

5. **Empty `tabs` is a real answer.** A PAN card, an acknowledgement of last
   year's return, or a duplicate belongs to no schedule. Say so, and say why.
   Do not stretch to find a home for it.

6. **A zip archive is routed by what is inside it.** Its members are listed
   under it, with the opening text of each and a note where a member is the
   same file as a document already in the listing. An archive of expense
   invoices belongs to `books` (and to `depreciation` if it holds asset
   purchases), exactly as the loose invoices would. An archive whose members
   are all, or nearly all, marked as the same as documents in the listing is a
   download of the folder: it is a duplicate, `tabs` is empty, and `why` says
   so. Never route by the archive's name alone when its members are listed.

## Things that are commonly misrouted

- **F&O and intraday trading are business income** under Schedule BP, not
  capital gains. A file holding both belongs to both tabs.
- **RSU vest reports and a 1042-S** are foreign assets and foreign income —
  `foreign_special` — and usually also relate to salary perquisites. Route to
  both when the document evidences both.
- **A dividend statement** is Other Sources, not Capital Gains, even when it
  comes from a broker and sits beside capital-gains files.
- **Form 12BA** is the perquisite annexure to Form 16, so it is `salary`.
- **A demat "corporate benefits" entitlement report is not a payment advice.**
  It states what was due, not what was received. Flag that in `why`.

## Output

One entry per document in the listing, using the path exactly as given. Do not
invent paths, do not omit documents, and do not merge duplicates into one entry —
if the listing shows a file twice under different paths, answer for both.

Put anything the reviewer should know in `notes[]`: a document that looks like a
duplicate, a period that seems to fall outside the financial year, an archive
that could not be unpacked (a .rar or .7z, or a damaged zip), whose contents
nobody has seen.


## Documents the department itself holds

Set `reported_summary: true` on a document that states what was **reported to
the income-tax department** about this taxpayer, or the department's own
aggregation of it: the Annual Information Statement (AIS), the Taxpayer
Information Summary (TIS), Form 26AS.

These are not a source of figures for any schedule -- they are aggregates,
they arrive late and they are sometimes wrong. Every schedule's reconciliation
is given them regardless of which tabs you route them to, so that each
schedule can be checked against what the department already knows. Still route
them to the tabs they inform, as you would anyway.

A broker's, bank's or employer's own statement is **not** one of these, even
when it contains totals: it is evidence, not the department's record of it.

## Notes about the year ahead

A document about what is **still to come** this year -- a note the taxpayer
wrote ("salary from October will be ...", "selling the 2024 RSUs in January",
"PPF Rs 1.5 lakh in March"), an offer or increment letter, a CTC statement, a
vesting schedule -- goes to **`plan` and to no other tab**.

These are expectations, not evidence. Routing one to `salary` as well would
have a figure someone hopes to be paid read as a figure that was paid. The
Planning page sets them beside the schedules instead. A payslip, Form 16,
broker statement or bank statement says what has already happened and goes to
its schedule as usual, even in the middle of the year.

## A return that was already filed

An ITR-V, an acknowledgement, a filed JSON, or the PDF the e-filing utility
produces for a submitted return -- often named for its acknowledgement number,
such as `Form_pdf_123456789012345.pdf` -- goes to **`filed_return` and to no
other tab.**

That exclusivity is the point. A filed return contains salary, capital gains
and every other figure, so it looks like a source for all of them. It is not.
The tool works those out from the underlying evidence -- the Form 16, the
broker statement, the bank statement -- and then sets its answer beside the
filed return to see whether they agree. Routing the filed return to the salary
tab as well would have the tool extract a figure from the return and then
congratulate itself for matching it, which checks nothing at all.

Check the assessment year on it before routing. `filed_return` is for the
return of the year being worked on. A return, intimation under section 143(1)
or assessment order for an **earlier** year goes to **`setoff_cfl` and nowhere
else**: the only thing taken from it is its Schedule CFL -- the losses carried
forward into this year, which are an opening balance, not a figure this return
computes. Say in `notes[]` which year it is for.
