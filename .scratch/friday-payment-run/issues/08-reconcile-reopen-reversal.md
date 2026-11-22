# 08: Reconcile a debit and reopen a reversal

**What to build:** Tell the controller whether the provider accepted a payment, processed it, or the statement supports reconciliation. Reopen the item if a processed payout later reverses.

**Blocked by:** 06

**Status:** ready-for-agent

- [ ] Persist provider status, payout ID, and UTR when available. A provider submission alone never counts as processed; a processed status alone never counts as reconciled.
- [ ] Use the reference type established at kickoff: Kavach reference, provider payout ID, or UTR. Require a nonempty reference, equal amount and currency, and the same account. Match one processed payout to exactly one debit in both directions.
- [ ] Demonstrate reconciliation with a UTR-only statement. A missing UTR, conflicting reference, two candidate debits, or right reference with wrong amount remains unreconciled. Other statement lines can still be coded.
- [ ] Watch processed payouts through T+3 working days across process restarts. Exercise a reversal during that window; the item reopens and the page and receipt no longer count it as reconciled.
