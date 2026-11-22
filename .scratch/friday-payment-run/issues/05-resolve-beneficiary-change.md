# 05: Resolve a beneficiary change with two people

**What to build:** Let the AP lead record a callback without treating it as authorization. Release the account-change hold only after independent confirmation and a separate authorized person's decision.

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] Use a trusted contact enrolled before the change request. Record the AP lead's confirmation outcome against the carrier and requested change. The application does not contact the vendor.
- [ ] A recorded callback alone leaves the bill held. A missing trusted channel, unsuccessful confirmation, or onboarding record supplied as bank-change authority also leaves it held, with a named next action.
- [ ] The callback recorder cannot separately authorize the same update. A distinct authorized person can approve the confirmed update; an unauthorized person cannot.
- [ ] An approved update produces a new beneficiary version. Retired destinations remain unusable. Re-evaluate the bill against the current version and all other holds; the update itself does not approve or send a payment.
- [ ] Refresh the run. It retains the confirmation and authorization outcomes, masked destination, and outstanding next step. Independent bills remain eligible throughout.
