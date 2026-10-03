version: general@1

# Part A-GEN - General information

Source documents: anything that states who the return is for and which bank
accounts they hold. Form 16 Part A, Form 26AS, the AIS (its Part A lists name,
PAN, date of birth, address, mobile and e-mail), a PAN card, bank statements,
cancelled cheques, interest certificates and broker statements that name the
linked bank account.

This part of the return has no amounts. It is identity, a few filing choices
and the list of bank accounts, and each of the three is treated differently.

## Identity: transcribe it

`assessee.name`, `pan`, `date_of_birth` (as `YYYY-MM-DD`), `address`, `email`
and `mobile`, as the documents state them.

- **The department's record wins a disagreement.** Where the AIS or Form 26AS
  spells the name or gives the address differently from an employer or a bank,
  report the department's version and say what differed in `questions[]`. The
  return is validated against the department's record.
- **A masked value is not a value.** `XXXXXX1234` or `AB*****9F` is left out
  unless another document gives it in full. Do not complete a masked number
  from context.
- **Aadhaar: the last four digits only**, in `aadhaar_last_four`. Never record
  the full number, even where a document prints it.
- `assessee.found_in` names the document the identity was taken from.

## Bank accounts: one row per account, never guessed

List every bank account **held in India** that the documents show for the year,
in `bank_accounts[]`: `bank_name`, `ifsc`, `account_number`, `account_type`
(savings, current, and so on, where stated) and `found_in` (the document that
shows it).

- An account appears once however many documents mention it. Take the fullest
  statement of it.
- `ifsc` and `account_number` are both required by the return. An account whose
  number is only ever shown masked, or whose IFSC no document gives, is **not**
  put in the list with a made-up or partial value: describe it in `unmapped[]`
  and ask for the missing part in `questions[]`.
- Loan accounts, credit cards, demat accounts, fixed deposits and foreign
  accounts are not bank accounts for this part. Leave them out; a foreign
  account belongs to Schedule FA.
- `for_refund` is a choice, not a fact. Leave it null unless a document
  expressly nominates an account for refunds, and ask which account should
  receive any refund.

## Filing choices: not in the documents

Everything under `filing` is decided by the person, not stated by a document:
whether the return is on time, belated or revised, whether they opt out of
section 115BAC, the Form 10-IEA acknowledgement, and whether section 5A applies.

Leave each of these null. Do not infer them from a salary certificate that
happens to mention a regime: the employer's choice for TDS does not bind the
return. Raise one question for each that a person must settle, and no more.

## Watch for

- **Somebody else's details.** A joint account's second holder, an employer's
  PAN or TAN, a deductor's address, a nominee. Only the person the return is
  for goes in `assessee`.
- **A document for another person altogether.** If a document's PAN differs
  from the PAN on the others, do not merge it in: list it in `unmapped[]` and
  ask.
- **An old address.** Where documents give different addresses, report the one
  on the department's record and mention the other in `questions[]`.
