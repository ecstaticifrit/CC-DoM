# 04: Review five bills without sending money

**What to build:** Let the controller see which approved bills are eligible for sign-off and why the others need attention. One carrier's disputed destination must not delay the rest.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Compare unpaid bills with current approved carrier accounts and payment history. In the five-bill rehearsal, three are eligible, one possible duplicate is held, and one changed account is held. Review makes zero payout calls.
- [ ] Put "Needs attention" first. Each exception names its evidence, owner, next step, and client-supplied deadline. Where a deadline or trusted contact is missing, say so rather than inventing one.
- [ ] For the changed account, link both masked source rows. Show the old and requested last four digits, amount, and trusted contact's role and client record ID. Never display the contact's email address.
- [ ] Treat new, changed, and retired destinations as ineligible for payment. A possible duplicate stays visible rather than being removed or automatically paid.
- [ ] Selecting eligible rows updates the count and total together. Held rows cannot enter the proposed batch. The selected total remains visible beside the sign-off control.
