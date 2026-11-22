# Kavach pilot offer and scorecard

Ticket: `.scratch/friday-payment-run/issues/15-measure-pilot-offer.md`. Words follow `GLOSSARY.md`.

## 1. The offer

**Per bill, whenever a payment run is needed.** Agree the unit price and what counts as billable (including holds and repeat uploads) before a paid pilot. The demo does not charge.

- There is no charge per alert or external lookup.

## 2. Who does what

| Work | Done by |
| --- | --- |
| Compare bills with beneficiaries and payment history; find discrepancies; gather evidence; prepare the batch; track every exception to an owner and next step; write each signed bill into exactly one bank payment file; reconcile against the bank statement; write the run receipt | **Kavach** |
| Callback to the trusted contact for a beneficiary change | **Client's AP lead** |
| Authorize a beneficiary update | **Client's authorizer** (a different person from the AP lead) |
| Sign the batch | **Client's controller** |

Kavach never contacts a carrier and never changes a beneficiary.

## 3. The pilot (paid, read-only)

1. The client gives one historical payment run: bills, beneficiaries, payment history, statement and the known outcome.
2. Kavach runs it read-only. No bank access. No carrier contact.
3. The client's team re-does the same run its usual way, or uses its own timesheet from the original run.
4. Both sides fill in the scorecard below. Success targets are agreed with the controller before the pilot starts.

Running the pilot and contacting any carrier are outside this ticket.

## 4. Scorecard (same historical run, two methods)

| Measure | Without Kavach | With Kavach | Notes |
| --- | --- | --- | --- |
| Total staff handling minutes |  |  | Include callback minutes in **both** columns |
| of which: callback minutes |  |  | The AP lead does callbacks either way |
| False holds (clean bills held) | n/a |  | Each one is a delayed carrier |
| Late clean payments |  |  | Clean bills paid after the client cutoff |
| Exceptions found |  |  | |
| Exceptions with owner and next step |  |  | |
| Bills paid twice or to a wrong destination |  |  | Target: zero |

**Kavach delivery cost (recorded separately):**

| Item | Value |
| --- | --- |
| API spend (credits and Rs) | |
| Model spend, if any | |
| Conversion rate used (Rs per $) and its date | |
| Sponsored or free credits | |
| Kavach-side staff minutes | |

Values shown in examples are **illustrative** until a pilot fills them in.

## 5. Does the fee pay for itself?

On labour alone, break-even staff-hours = agreed per-bill price times billable bills divided by the client's loaded hourly labour cost.

Both labour costs are illustrative. Basis checked 22 Nov 2026 (third-party salary sites): Glassdoor India average for accounts payable Rs 4.18 lakh per year (about Rs 209 per hour at 2,000 hours, before overhead); PayScale median for AP manager Rs 9.36 lakh per year (about Rs 468 per hour).

**Not counted as savings:** the face value of any held bill. A hold that prevents a bad payment is reported as an exception, not as money saved.

## 6. Commercial pass mark

The controller agrees to pay for the next run.
