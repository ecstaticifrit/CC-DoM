# 13: Explain every rupee on the receipt

**What to build:** Give the controller one downloadable account of what finished, what is waiting, what the work cost, and which personal data it used. The receipt and page must agree after restart.

**Blocked by:** 03, 08, 09

**Status:** ready-for-agent

- [ ] Show mode, budget, sandbox label, and ready, held, and unresolved items. Each exception names the outstanding fact, owner, and next action. Include the client cutoff where supplied.
- [ ] Report submitted, processed, and reconciled totals separately with provider IDs. In posting mode show committed posting IDs, legal payees, and ledger accounts. Recompute stage totals from saved outcomes without treating stages as separate payments.
- [ ] Show actual API spend including retries, model spend if any, conversion rate, sponsored credits separately, and human handling minutes. Do not treat held principal as savings or a customer's callback as Kavach work.
- [ ] List the personal-data categories used and the configured retention period. Identify retention as policy; claim deletion only if a completed deletion record supports the claim.
- [ ] Derive the person-lookup count from the run's call log rather than hardcoding zero. The screening run must make none.
- [ ] Download both modes' receipts after refresh or restart. IDs, stage totals, costs, and data disclosures match the saved run shown in the browser.
