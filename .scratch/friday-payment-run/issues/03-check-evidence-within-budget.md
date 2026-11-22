# 03: Check live evidence within the run budget

**What to build:** Explain what a live check proves for a bill, what it costs, and what remains unknown. Keep unrelated bills moving when a source or the remaining allowance cannot support a check.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] For an unfamiliar sender, corroborate the carrier domain with Crustdata company identification. Normalize domains before comparing. An exact match adds no lookalike warning; one or two edits warrant review, not a claim of fraud or sender authentication.
- [ ] If routing verification is required, report only what the IFSC establishes about the branch. Do not claim account ownership or successful test-mode bank-account validation.
- [ ] The selected row links to masked evidence with the exact relevant field or passage, source link, retrieval time, and record date when supplied. A missing directory profile alone does not hold an otherwise supported carrier.
- [ ] Before every external attempt, including retries, persist a spend reservation and check the remaining time and cost allowances. Record actual charges and distinguish outstanding reservations from actual spend.
- [ ] Lower the cap mid-run and restart the process. Prior spend and elapsed time remain visible; no new call starts beyond either cap. A needed but unavailable fact shows `cannot verify`; independent work still finishes.
- [ ] Demonstrate a real decision-relevant source call using a qualifying rehearsal record. Log the call without raw personal data. Make no person lookups.
