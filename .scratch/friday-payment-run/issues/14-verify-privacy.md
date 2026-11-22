# 14: Verify privacy on success and error paths

**What to build:** Prove that a user inspecting the browser, download, or logs cannot recover private input values. This checks the masking already used by the run; it is not a delay on implementing masking.

**Blocked by:** 13

**Status:** ready-for-agent

- [ ] Use distinctive dummy account numbers, full email addresses, and raw email-body markers. Exercise successful uploads and failures in both modes, including opening evidence and downloading receipts.
- [ ] Search rendered HTML, browser response payloads, evidence links and their served content, exports, and application and error logs. No full test account, email address, or raw body marker appears. Expected last-four endings still appear where needed.
- [ ] Inspect a payout run through recovery. The exact request body remains available to server-side recovery but no browser payload, receipt, or log exposes it.
- [ ] With only a retention policy, no surface says data was deleted. A deletion claim must identify completed deletion evidence. Verify the zero person-lookup count against actual logged calls.
- [ ] Keep a repeatable privacy check with a masked pass/fail report. The report itself must not disclose the values it searched for.
