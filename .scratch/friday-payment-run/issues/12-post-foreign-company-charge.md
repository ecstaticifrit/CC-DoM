# 12: Post an evidenced foreign-company charge

**What to build:** Determine which legal entity billed the client rather than treating a descriptor as a legal name. For the supported October AWS charge, post Amazon Web Services EMEA SARL to cloud hosting.

**Blocked by:** 03, 09

**Status:** ready-for-agent

- [ ] Fetch the vendor's official legal-entity page through Crustdata live web enrichment. Quote the relevant passage exactly and record the source link, retrieval time, and record date when supplied.
- [ ] Require evidence connecting the relevant contracting entity to this charge and a client rule supporting cloud hosting. A page listing several entities, an AWS descriptor, or a search hit alone cannot identify the correct payee.
- [ ] With the supporting records, the reference-less EMEA line posts once. If the connected evidence indicates another contracting entity, do not post it as EMEA. If the link is absent, name the missing fact and leave the line unposted.
- [ ] Where a dated filing is the appropriate legal-name source, accept its stated name only with a link to the charge and a supporting ledger rule. Do not add another registry.
- [ ] A needed but unavailable source affects only the dependent line. Preserve masked evidence and charge actual lookup costs against the run. Make zero payout calls.
