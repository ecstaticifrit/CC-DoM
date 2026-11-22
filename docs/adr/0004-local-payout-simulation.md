# Simulate transfers locally instead of using a payment provider

The student team cannot use RazorpayX. For the hackathon, the local simulator replaces the external payout and recovery workflow in ADR 0001 and the original build brief. Its receipts are not evidence of bank settlement.

Approval, a unique client/bill claim, and the paired wallet balances commit in one SQLite transaction. A crash before commit leaves no transfer; a crash after commit leaves the same `sim_` ID. Historical provider attempts remain read-only and are never retried by the simulator. Posting a statement does not move demo money.
