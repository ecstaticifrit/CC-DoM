# 01: Verify the kickoff contract

**What to build:** Give the team a checked example of the organizer's request and expected result. Distinguish confirmed inputs and live capabilities from assumptions before choosing an adapter.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] During the first 30 minutes, inspect the kickoff kit and a real statement row. Record a masked example, the requested job, input format, output contract, budget, and client cutoff where supplied.
- [ ] Identify which reference the statement carries: Kavach reference, provider payout ID, UTR, or none. Record the account context and whether the posting target requires approval for an irreversible write.
- [ ] Use rules and parsers for CSV or JSON. If unstructured extraction is necessary, record the provider decision and scope that work before implementation. Require a source for every extracted value. A model cannot decide eligibility, change a beneficiary, or send money.
- [ ] Confirm organizer rules for pre-written code and team approval for data.gov.in signup. Check MCA access, Crustdata connectivity, and RazorpayX test credentials and balance without recording secrets.
- [ ] With authorization, verify one test-mode payout and one decision-relevant live data call. Record masked evidence, test ID, and spend separately from screening runs. If a check fails, name the affected demo path and owner; do not count a fixture as live evidence.
- [ ] Select a record or event after 1 September 2026 for each rehearsal case. Record the event or record date separately from retrieval time.
