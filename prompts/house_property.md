version: house_property@1

# Schedule HP - Income from House Property

Source documents: rent agreements, rent receipts, home-loan interest
certificates from the lender, municipal tax receipts, co-ownership deeds,
and any completion certificate for a property still under construction.

## One entry per property

Each property is reported separately, and `occupancy` decides almost everything
that follows:

- **self_occupied** - annual value is nil. Interest under section 24(b) is
  capped at Rs 2 lakh. At most two properties may be treated this way.
- **let_out** - actual rent is the annual value. Interest is uncapped here,
  although the loss that can be set off against other heads is capped at
  Rs 2 lakh by Schedule CYLA.
- **deemed_let_out** - a third or later property that is not actually let. Its
  notional annual value must be established; if the documents do not give one,
  say so in `questions[]` rather than entering nil.

## Fields follow the form

`rent_received_or_receivable` is item 1(a), `unrealised_rent` 1(b),
`municipal_tax_paid` 1(c), `annual_value` 1(d), the 30% standard deduction
1(e), `interest_on_borrowed_capital` 1(f) and section 25A arrears 1(g).

Report the 30% deduction and the final figure only if the document states them.
`engine/` computes both; a stated figure is kept for cross-checking.

## Watch for

- **Municipal tax is deductible only when actually paid** during the year, not
  when it falls due. If a receipt is dated outside the year, flag it.
- **Co-ownership.** Report your share, not the whole property, and capture each
  co-owner's name, PAN and share. A missing co-owner PAN blocks the return.
- **Pre-construction interest** is claimed in five equal instalments beginning
  in the year of completion. If the certificate shows it, put the instalment in
  `interest_on_borrowed_capital` and explain in `questions[]`.
- **A lender certificate splits principal and interest.** Only interest belongs
  here; the principal is an 80C claim on the Deductions tab. Put the principal
  in `unmapped[]`.
- **Under the section 115BAC default regime** a self-occupied property's
  interest is not deductible at all, and a let-out loss cannot be set off
  against other heads. Extract as stated; the regime is applied downstream.
