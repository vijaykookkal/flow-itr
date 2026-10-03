version: deductions@1

# Schedule VI-A - Deductions

Source documents: 80C investment proofs (ELSS, PPF, LIC, tuition fees, principal
repayment), NPS statements, health insurance premium receipts, donation receipts,
education-loan interest certificates, disability certificates.

## What to produce

`claims[]` -- one row per proof document, carrying **what the proof evidences**,
not what is ultimately allowable.

**Do not apply the statutory ceilings.** If the proofs show Rs 2,34,000 of 80C
investment, report Rs 2,34,000. The Rs 1,50,000 cap is applied by `engine/`,
which is tested code, and keeping the raw figure means the cap is visible as a
decision rather than baked invisibly into an extraction. The same goes for the
80D age slabs, the 80G qualifying limits and the 80CCD(1B) ceiling.

`total_claimed` is the sum of `claims[]` before any ceiling.

## Section 80G needs more than an amount

A donation claim is rejected without the donee's PAN and the ARN of the donee's
80G registration. Capture `payee`, `payee_pan`, `donation_arn` and `mode` for
every 80G row. Cash donations above Rs 2,000 are not deductible at all -- if the
mode is cash, say so in `questions[]`.

## Watch for

- **Employer contributions.** Employer PF and employer NPS under 80CCD(2) are not
  employee claims. Employer NPS has its own field; employer PF is not claimed at
  all. Put either in `unmapped[]` if a proof sheet lists them.
- **Double counting.** The same LIC premium often appears in both a Form 16
  annexure and a standalone proof. One row, and a note in `questions[]`.
- **80CCD(1) versus 80CCD(1B).** Self NPS contribution up to the 80C aggregate is
  80CCD(1); the extra Rs 50,000 is 80CCD(1B). If the statement does not split it,
  report it as stated and ask.
- **80D parent premiums** turn on whether a parent is 60 or over. Capture the age
  or date of birth in `description` when the receipt gives it.
- **Under the section 115BAC default regime almost all of Chapter VI-A is
  unavailable** apart from 80CCD(2) and 80JJAA. Extract everything anyway -- the
  regime comparison needs both sides -- but do not assume it will be allowed.
