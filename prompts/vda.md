version: vda@1

# Schedule VDA - Virtual Digital Assets

Source documents: crypto exchange statements, wallet transaction exports and
TDS certificates under section 194S.

## Section 115BBH is unusually harsh, and the schema reflects it

- A flat **30%** applies to income from each transfer.
- The **only** permitted deduction is the cost of acquisition. Not exchange
  fees, not gas, not interest, not infrastructure.
- A **loss cannot be set off** against anything, including another VDA gain,
  and cannot be carried forward.

Because losses cannot be set off, each transfer is reported on its own and a
loss-making transfer contributes nil, not a negative. Report the actual
consideration and cost per transfer; `engine/` applies the flooring.

## Watch for

- **TDS under section 194S** at 1% is usually deducted by the exchange. That
  belongs on the Taxes Paid tab, from Form 26AS. Note it in `unmapped[]`.
- **Crypto-to-crypto trades are transfers**, even though no rupees moved. The
  consideration is the fair value of what was received.
- **Airdrops, staking and mining rewards** are not transfers; they are income
  when received. Flag them in `questions[]` rather than forcing them into a
  transfer row.
- **Transfers between your own wallets** are not transfers at all. If the
  export lists them, exclude them and say so in `unmapped[]`.
