# 09: Post one supported charge exactly once

**What to build:** In Post bank lines mode, show the supported legal payee and client ledger account, then write one posting. A bank reference and directory profile are not prerequisites.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Accept a proprietor's legal name from a client onboarding record verified before the request. Require the statement or supporting client document to link its carrier ID to this charge, and a client rule to support the ledger account.
- [ ] Show the legal-name evidence, link to the charge, and ledger rule. Remove the charge link, legal name, or rule: the line stays visible and unposted with the specific missing fact. A trade name on a new invoice is insufficient.
- [ ] For irreversible posting targets, require human confirmation of the exact line, payee, amount, currency, and ledger account before writing.
- [ ] Commit the statement-row outcome and its ledger posting together in SQLite. Interrupt the posting, resume, and replay the input: the supported row has one committed posting ID, not two or a posted outcome without a posting.
- [ ] Posting mode shows no payout button, makes zero payout calls, and cannot update a beneficiary. A proprietor record that supports a posting cannot authorize a bank change or payment.
