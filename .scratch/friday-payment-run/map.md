# Kavach: freeze priorities

## Decisions so far

- Kavach helps a finance team check approved supplier bills, hold exceptions, sign the clean batch and confirm payment against a statement. Run it whenever bills are due. Friday and logistics carriers are demo fixtures, not product requirements.
- One customer workflow. Standalone expense posting (#09-12) is outside the freeze scope. Keep historical runs readable.
- Price per bill, not per week, alert or API call. The rate and billable event are not settled. The old weekly pilot quote (#15) is not the current offer.

## Notes: active queue

1. **Shipped: #13 / #15 freeze scope.** Customer pages and downloads exclude internal costs. Source evidence and internal metering remain. Per-bill pricing is stated without quoting a rate or charging.
2. **Shipped: #02 / #04 positioning.** Supplier payment runs have no fixed schedule; logistics is the labeled demo. Existing carrier CSV headers remain compatible.
3. **#14 / #16 - Rehearse and freeze.** Upload the sample, explain one hold, sign the clean bills, download the frozen file and reconcile its references on the same run. Verify privacy and the customer receipt. Keep demo evidence of internal costs separate.

Keep the bank-file portions of #05, #06 and #08. The provider retry workflow in #07 is superseded; do not rebuild it. This map sets scope, not completion status.

## Fog

- What counts as one billable bill (including holds and re-uploads), and what is the unit price?
- Does the organizer accept the bank payment file in lieu of a provider sandbox (#01)?
