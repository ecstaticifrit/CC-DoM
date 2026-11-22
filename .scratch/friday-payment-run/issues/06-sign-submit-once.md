# 06: Sign an exact batch and submit it once

**What to build:** Let the controller sign only the displayed bills and destinations, then receive a test payout ID for each accepted payment. A repeated upload, confirmation, or refresh must not create a second payment.

**Blocked by:** 03, 04

**Status:** ready-for-agent

- [ ] Show "Approve 3 bills for Rs X" for the screening selection, followed by confirmation of the exact bill IDs, amounts, currencies, masked destinations, and beneficiary versions. No provider submission occurs before confirmation.
- [ ] Recheck eligibility and signed values on the server before submission. Change one beneficiary after sign-off: only that item's approval becomes invalid. Held, unsigned, or stale items cannot be sent.
- [ ] Before sending, commit the approved intent in one SQLite transaction, unique per client and payable ID. Persist the source account identifier, destination fund-account ID, amount, currency, provider retry key, exact body, and a unique reference of at most 40 characters. Generate the reference independently of the invoice number.
- [ ] Only an eligible, approved intent may call RazorpayX in test mode and within the run allowance. Keep the exact provider body server-side. Persist the returned provider ID and show submitted separately from processed or reconciled.
- [ ] Upload the five bills twice and sign once. Exactly three distinct test payout IDs belong to three different clean bills. Repeating the confirmation or refreshing the run adds none. An uncertain intent stays locked for recovery.
