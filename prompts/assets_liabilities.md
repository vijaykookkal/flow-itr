version: assets_liabilities@1

# Schedule AL - Assets and Liabilities

Source documents: purchase deeds, valuation reports, bank statements, demat
holding statements, insurance policy schedules and vehicle registrations.

## Only when total income exceeds Rs 50 lakh

Set `applicable` accordingly. If total income is below the threshold this
schedule is not filed at all, and reporting it anyway is a disclosure you do
not need to make.

## Cost, not market value

Every figure here is the **cost** of the asset, not what it is worth now. The
one exception is where an asset was inherited or received as a gift, in which
case the previous owner's cost applies - flag any such asset in `questions[]`,
because the cost usually is not in the documents you hold.

## Liabilities are only those relating to the assets reported

A home loan against a reported property belongs here. An unrelated personal
loan does not.

## Watch for

- **Bank balances** are the closing balance on the last day of the year, across
  all accounts including foreign ones.
- **Shares and securities** are at cost, so a demat statement showing market
  value is the wrong figure. If only market value is available, say so.
- **Jewellery** is frequently the hardest to evidence. Report what documents
  support and flag the rest rather than estimating.
- Assets already disclosed in Schedule FA are **also** reported here. That
  duplication is correct.
