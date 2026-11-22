# 11: Post an evidenced Indian-company charge

**What to build:** Resolve the supported October Swiggy charge to Swiggy Limited and post it to staff meals. Let the controller inspect the name, the connection to the charge, and the client's ledger rule.

**Blocked by:** 03, 09

**Status:** ready-for-agent

- [ ] Retrieve the Indian company's `CompanyName` from MCA company master data via data.gov.in. Show the exact field, source link, actual dataset date, and retrieval time. MCA is the only registry integration.
- [ ] A merchant suggestion may guide the lookup but cannot establish the legal payee. Require statement or supporting client evidence linking Swiggy Limited to this charge, plus the staff-meals ledger rule.
- [ ] Without a bank reference, the fully supported line still produces one posting ID. Removing the entity link or ledger rule leaves it unposted and names the missing fact.
- [ ] A failed required lookup or exhausted allowance shows `cannot verify` for the affected fact. Independent lines still finish. Use live evidence for the rehearsal and make no payout calls.
