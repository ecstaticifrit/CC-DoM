# Kavach

Kavach closes a logistics company's weekly carrier payment run: it gets clean bills signed and paid once, holds the rest with an owner and a next step, and records charges that already left the bank.

## People

**Controller**:
The client's finance controller, who signs the batch and owns the run's outcome.
_Avoid_: Admin, user, approver

**AP lead**:
The client's accounts-payable lead, who works exceptions and performs callbacks to carriers.
_Avoid_: Clerk, operator

**Authorizer**:
A client person, distinct from the AP lead who made the callback, who approves a beneficiary update.
_Avoid_: Approver, admin

**Carrier**:
A transport company or sole proprietor that the client owes money for freight work.
_Avoid_: Vendor, supplier, transporter

## Paying bills

**Invoice**:
The document a carrier sends to request payment.
_Avoid_: Bill (when meaning the carrier's document)

**Bill**:
An amount the client has already approved for payment to a carrier, identified by the client's bill ID.
_Avoid_: Payable, invoice, payment request

**Payment run**:
One processing of one client request, from upload to receipt.
_Avoid_: Job, batch, session

**Batch**:
The exact set of bills, amounts, currencies, destinations and beneficiary versions the controller signs in one sign-off.
_Avoid_: Run, selection

**Sign-off**:
The controller's approval of one batch, valid only for the values shown at that moment.
_Avoid_: Approval (alone), confirmation

**Beneficiary**:
The client's approved bank destination for a carrier.
_Avoid_: Bank details, payee account

**Beneficiary version**:
One numbered state of a carrier's beneficiary; any change creates a new version and retires the old one.
_Avoid_: Revision

**Trusted contact**:
A carrier contact recorded in client records before the change request it is used to confirm.
_Avoid_: Enrolled contact, known contact, vendor email

**Callback**:
The AP lead's confirmation of a requested beneficiary change through the trusted contact.
_Avoid_: Verification call, OOB check

**Payout**:
A simulated transfer of demo INR from the treasury to a beneficiary wallet. It does not move bank funds.
_Avoid_: Payment (when meaning the provider transfer), transfer

**Submitted**:
The simulator accepted the signed transfer.
_Avoid_: Paid, sent

**Processed**:
The simulator recorded the treasury debit and beneficiary credit. This is not bank settlement.
_Avoid_: Paid, settled

**Reconciled**:
A processed payout is uniquely matched to one statement debit by reference, amount and currency.
_Avoid_: Matched (alone), cleared

**Reversal**:
A processed payout that the bank later returns, reopening the bill.
_Avoid_: Refund, failure

**Pending review**:
A payout whose provider outcome cannot be established safely; it stays locked and is never replaced automatically.
_Avoid_: Unknown, stuck

## Recording charges

**Statement line**:
One debit or credit row on the client's bank statement.
_Avoid_: Transaction, bank line, entry

**Posting**:
A statement line written once to a client ledger account with its legal payee.
_Avoid_: Booking, journal entry

**Legal payee**:
The registered legal name of the entity a charge was paid to, supported by evidence linked to that charge.
_Avoid_: Merchant, payee name, descriptor

**Descriptor**:
The merchant text a bank prints on a statement line, such as `RAZ*SWIGGY BLR`.
_Avoid_: Merchant name, payee

**Ledger rule**:
A client rule that assigns a legal payee's charges to a ledger account.
_Avoid_: Mapping, category

**Replay**:
The same statement or bills submitted again; it returns the saved outcomes and creates nothing new.
_Avoid_: Duplicate, re-upload

**Possible duplicate**:
A different row that resembles an earlier charge or bill; it is held for review, never deleted or merged.
_Avoid_: Duplicate, repeat

## Evidence and outcomes

**Evidence**:
The exact field or passage, its source, its record date when supplied, and its retrieval time, supporting one fact.
_Avoid_: Proof, data, source (alone)

**Record date**:
The date of the record or event itself.
_Avoid_: Fetch date, timestamp

**Retrieval time**:
When Kavach obtained the evidence.
_Avoid_: Record date

**Corroborated domain**:
A carrier's web domain supported by both client records and a company directory entry.
_Avoid_: Official domain, verified domain

**Lookalike domain**:
A domain one or two edits away from a corroborated domain; it triggers review, never an accusation.
_Avoid_: Fake domain, spoofed domain

**Hold**:
A bill or statement line Kavach will not pay or post until a named fact is resolved.
_Avoid_: Block, rejection, flag

**Exception**:
A held item with its missing fact, owner, next step and client cutoff.
_Avoid_: Alert, issue, error

**Cannot verify**:
The outcome when no available evidence settles a required fact; the missing fact is named.
_Avoid_: Unknown, failed, fraud

**Client cutoff**:
The deadline the client sets for its payment run.
_Avoid_: Legal deadline, SLA

**Run allowance**:
The time and money a payment run may spend on external calls.
_Avoid_: Budget (alone), quota, limit

**Run receipt**:
The downloadable account of what finished, what is waiting, what it cost and which personal data was used.
_Avoid_: Report, summary
