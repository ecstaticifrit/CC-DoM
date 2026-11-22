# 15: Make the pilot offer measurable

**What to build:** Give the buyer a priced offer and a read-only shadow-pilot scorecard. Let them test whether Kavach saves enough work to justify the fee without claiming that a held payment is a saving.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] State Rs 2,000 per weekly run of up to 100 bills, including evidence and follow-up tracking for up to five exceptions. Bank payout fees are separate. Agree extra work in advance; do not price per alert.
- [x] Distinguish Kavach's evidence gathering and follow-up from the customer's callback and separate beneficiary authorization. Describe a paid, read-only pilot; running the pilot or contacting a vendor is outside this ticket.
- [x] Provide a scorecard comparing the same historical batch with and without Kavach. Include callback time in both methods. Record total handling minutes, false holds, and late clean payments.
- [x] Separately record Kavach's API/model spend, conversion rate, sponsored credits, and staff time. Mark illustrative inputs as illustrative.
- [x] Show the arithmetic: at Rs 250 per hour the fee requires eight staff-hours saved; at Rs 500 it requires four. Exclude the face value of held bills from savings.

## Comments

- 2026-11-22: Delivered in `docs/pilot-offer.md` (offer, roles, read-only pilot, scorecard, 4/8-hour arithmetic). No code.
