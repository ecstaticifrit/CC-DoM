# 07: Recover an interrupted payout without replacing it

**What to build:** After a timeout or process kill, recover the existing payment when evidence identifies it. Tell the controller whether it failed or remains uncertain without issuing a replacement.

**Blocked by:** 06

**Status:** ready-for-agent

- [ ] Kill the process after provider acceptance but before local acknowledgement. Restart and reopen the same run. Any submission retry uses the saved provider key and exact body, within the remaining allowance.
- [ ] If submission is still uncertain, query payouts using the source account number and stored reference. Accept only one result in that source account with that reference and the approved destination, amount, and currency.
- [ ] Exercise fixtures for zero matches, multiple matches, wrong destination, wrong amount or currency, and unavailable provider. Each displays `pending_review`, keeps the intent locked, and prevents a fresh-key submission.
- [ ] A uniquely matched, confirmed failure displays `failed` and returns to the controller. It does not trigger an automatic replacement or appear as an unknown result.
- [ ] Repeat the double-upload screening run with an acceptance-time kill in the live sandbox. Across restart and browser refresh, the provider shows the original three distinct payout IDs, no fourth payment, and none for held bills.
