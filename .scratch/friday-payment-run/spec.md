# Kavach v6 | The Friday payment run

**ContextCon 05, BITS Pilani | Buying and paying | Hackathon build brief | 22 November 2026**

**Pitch:** "One carrier changed its bank account. Why should every other carrier miss Friday's payment? Kavach holds that bill, gets the rest ready for your sign-off, and gives you a receipt showing where every rupee went or why it is still waiting."

**Build scope:** One browser page, two jobs: pay approved bills or record charges that already happened. Only use test money. Do not add employee searches, another registry, real vendor outreach or a new screen.

**Five changes from v5:** Identify a repeated file separately from a repeated charge. Distinguish a failed payout from one whose status is unknown. Price the work Kavach does, not the customer's callback. Accept verified client records for sole proprietors' names. Test whether private details actually stay out of the browser, downloads and logs.

## 1. The one thing to ship

The customer is a mid-size Indian logistics company's finance controller. They already have a bank and accounting software. They are buying the work of closing a carrier payment run, which an outsourced payables desk does today, not another way to look up a bank branch.

At kickoff, read the actual request and output contract. Support two actions without confusing them:

| If the request is... | The finished work is... |
| --- | --- |
| **Pay approved bills** | Compare unpaid bills against current approved carrier accounts and payment history. Present an exact clean batch for human sign-off, execute it in RazorpayX test mode, then reconcile where statement evidence exists. Return an owner and next step for each exception. |
| **Post bank lines** | Identify the legal payee, apply the client's ledger rule and write the supported posting once. Hold possible duplicates; leave unknowns unposted. A bank reference is **optional**. This path cannot call the payout provider. Gate the posting if the target makes it irreversible. |

**Required frontend: one run page.** Build it at kickoff with FastAPI, a server-rendered HTML template, CSS and a little JavaScript for selection and status updates. No separate frontend service. This replaces the earlier Next.js plan: one process is simpler to kill, restart and demo. The browser and the organizer's machine-readable output must read the same saved run.

| Moment | What the controller sees and does |
| --- | --- |
| Start | Choose **Pay approved bills** or **Post bank lines**, upload the file and start the run. Show the mode, budget and sandbox label before submission. A bad file gets a readable error, not an empty receipt. |
| Review | Put **Needs attention** first. On a changed account, show the old and new account endings, evidence, owner and deadline. Identify the trusted contact by role and client record ID, not by email address. The AP lead makes the callback and records the result. A recorded callback alone does not release the bill. |
| Approve | Show **Approve 3 bills for Rs X**, followed by a confirmation listing those exact bills and destinations. The backend rechecks eligibility and versions before acting. Posting mode shows payee and ledger account instead; it has no payout button. |
| Follow the result | Keep the run at a stable URL. Show submitted, processed and reconciled separately, alongside provider or posting IDs, actual cost and a receipt download. If the backend stops, show "Connection lost" with the last update time. Reconnect to the same run without resubmitting. |

Use a ledger layout: bill IDs down the left, amounts aligned on the right, evidence beside the selected row on desktop and beneath it on mobile. Use plain status words, not color alone. Keep the selected total and approval control visible together so the controller can check what they are signing.

Example hold: **"C-104: Rs 48,000 held. Approved account ends 1234; invoice requests 9876. AP lead: confirm through the carrier contact enrolled before this request, before Friday 3 pm. Other bills are unaffected."** Link both masked source rows. The cutoff comes from the client, not a guessed legal deadline.

**Receipt sections:** run summary (mode, budget, sandbox label); ready, held and unresolved items; submitted / processed / reconciled totals with provider or posting IDs; cost (API, model if used, conversion rate, sponsored credits separately, human handling minutes); **personal data handled** (see §2, last rule).

## 2. Rules worth building

- **Check what each source actually proves.** Crustdata `company_identify` corroborates a company's domain. Normalize domains and check equality first: exact match means no lookalike warning; a near-copy (one or two edits) merits review, not an accusation. Neither result authenticates the sender. IFSC identifies a branch, not who owns an account. A missing directory profile alone never holds an otherwise supported small carrier.
- **Use live evidence that could change the result.** For a payout, check an unfamiliar sender against the carrier's corroborated domain or check a required routing code. For posting, Crustdata may suggest a merchant; a legal-name source then establishes the payee (next rule). The statement or supporting client record must connect that entity to this charge, and a client rule must support the ledger code. A web hit alone cannot post it. Record the exact field/passage, record date when supplied, retrieval time and source link. Use a post-1-September-2026 record or event for each rehearsal case; fetching an old record today doesn't make it new.
- **Source the legal name for a posting.** Use evidence appropriate to the payee:
  1. **Indian company:** the `CompanyName` field of the MCA company master data record (data.gov.in; needs a free API key; show the dataset date, last seen as 13 Oct 2026). This is the only registry integration.
  2. **Foreign company:** the vendor's official legal-entity page, fetched with Crustdata `web_enrich_live` and quoted exactly. Example: aws.amazon.com/legal/aws-contracting-party states "Amazon Web Services EMEA SARL … 38 Avenue John F. Kennedy, L-1855, Luxembourg".
  3. **Sole proprietor:** accept a client onboarding record verified before this request. It must state the legal name. Link its carrier ID to this charge through the statement or a supporting client document. A trade name on a new invoice is not enough. This evidence supports ledger posting only. It never authorizes a new bank account or a payout.
  4. **Other evidence:** a dated filing that states the name. If no source establishes both the identity and its link to the charge, leave the line unposted. Say which fact is missing.
  The same AWS page lists a different contracting entity for Indian accounts. Derive the payee from the evidence connected to the charge; never assume it from the descriptor alone.
- **Protect changes without delaying everyone.** New, changed or retired bank accounts stay held until independent confirmation via a previously enrolled channel and separate human authorization of the beneficiary update. No trusted contact: name what's missing. Approve the actual amount, currency, destination and beneficiary version per bill; show only masked account numbers. Recheck before submission. An edit voids that item's approval, not the whole batch.
- **Separate a repeated upload from a possible duplicate charge.** Identify a statement row by `(client ID, SHA-256 of statement input, original row number)`. For files, hash the original bytes, not the filename. For a JSON API request, hash the canonical UTF-8 encoding of the statement payload: sort object keys, omit formatting whitespace and preserve row order and repeated rows. Exclude transport metadata. Save the row outcome and any ledger posting together in SQLite. A replay returns the saved outcomes. Use payee, amount, currency and date to flag possible duplicates within or across statements, not to delete a row.
- **Save the payout before sending it.** In one SQLite transaction, save the approved intent under a unique `(client ID, payable ID)`. Store the source account identifier, destination fund-account ID, amount, currency, provider retry key and exact request body. Generate and persist a unique `reference_id` of at most 40 characters (for example, a UUID). Do not use an arbitrary invoice number. Uploading the bill again must reuse the saved intent, not start a new payout.
- **Recover by status, not by guesswork.** After a timeout or crash, retry an uncertain submission only with the [same key and body](https://razorpay.com/docs/api/x/payout-idempotency/make-request). If still uncertain, call [`GET /v1/payouts`](https://razorpay.com/docs/api/x/payouts/fetch-all) with the **source** `account_number` and stored `reference_id`. Accept only one result with that reference in that source account and the approved destination, amount and currency. No result, multiple results, a mismatch or an unavailable provider means `pending_review`. Keep the intent locked. Never use a fresh key to resolve uncertainty. A matching payout with a confirmed `failed` status is different: show `failed`, stop and return it to the controller. Automatic replacement payments are out of scope.
- **Don't confuse "sent" with "paid."** Submitted means the provider received the request. Processed is the provider's payment status. Store the provider payout ID and the bank's transaction reference (`utr`) when available. At kickoff, identify which reference the statement carries: Kavach's `reference_id`, the provider payout ID or the UTR. Reconcile only when a nonempty reference of that type, the amount and the currency uniquely link one processed payout to one statement debit in the same account. A missing or conflicting reference leaves the payout unreconciled; it does not prevent coding other lines. A [processed payout can reverse within T+3 working days](https://razorpay.com/docs/x/payouts/best-practices). Keep watching for that window and reopen the item on reversal.
- **Fail honestly.** Reserve spend before each external call, log actual cost including retries, and enforce time and cost caps across restarts. When a needed source fails, finish independent items and mark only the affected fact `cannot verify`. [RazorpayX test payouts work](https://razorpay.com/docs/x/dashboard/test-mode); [bank-account validation does not work in test mode](https://razorpay.com/docs/api/x/account-validation). No local mock counts as a live decision or an event payout.
- **No LLM unless the input needs one.** If the kickoff files are structured (CSV or JSON), v1 uses no LLM: rules decide and parsers extract. Add a model only to extract fields from unstructured bills or emails; every extracted value links to its source, and conflicting or unsupported values cannot pass. The model never decides, updates a beneficiary or sends anything. Choose the provider (open question Q28) only if this case arises.
- **Show what happened to personal data.** Build browser responses, evidence links, exports and logs from masked fields. Show only the last four digits of bank accounts. Do not include full email addresses or raw email bodies, including in error messages. Keep the exact payout body for recovery on the server; never copy it into a receipt or log. List the data categories used and the configured retention period. Label that period as policy, not proof of deletion. Say an item was deleted only if a completed deletion record supports that claim. Report person lookups from the run's call log; the build must make none.

## 3. Pass screening before polishing anything

| Rehearsal | Observable pass mark |
| --- | --- |
| Five approved bills: three clean, one possible duplicate, one changed account | Three eligible for sign-off, two held with reasons; zero payouts before approval. An exact sender-domain match creates no extra hold. After approval, exactly three provider payout IDs. |
| Upload the five bills twice. Approve once. Kill after provider acceptance but before saving the receipt. Restart, then refresh the browser. | Exactly three distinct provider payout IDs across both uploads. Each belongs to a different approved bill. No payout for either hold and no fourth payment. |
| Test the recovery lookup with no result, two results, a wrong destination or a confirmed failure | The first three stay `pending_review` and cannot be resubmitted with a new key. Only the last shows `failed` and returns to the controller. Use fixtures for these tests, not as a substitute for the live sandbox demo. |
| Upload the brief's four reference-less October lines twice, renaming the same file on the second upload. Interrupt one posting and resume. | Across both uploads: **two postings, one duplicate hold, one unknown, zero payout calls**. With supporting records, Swiggy Limited posts to staff meals and Amazon Web Services EMEA SARL to cloud hosting. The second AWS row stays visible and held. The Sharma row stays unposted with its missing evidence named. |
| Replay a JSON statement with different spacing and object-key order. Separately, reconcile a statement that carries only UTRs. | The JSON replay creates no new postings and preserves both AWS rows. A unique UTR, amount and currency match reconciles the debit. A missing UTR or two candidate debits leaves it unreconciled. |
| Small carrier with no registry entry | A linked, previously verified onboarding record supports the ledger posting. Remove the link to the charge: the item stays unposted. Present the same record to justify a bank change: the payment stays held. |
| Change one beneficiary after sign-off; remove a source; supply a right-reference/wrong-amount statement line | The changed item cannot be sent under the old approval; source-dependent facts stay unresolved; the wrong amount never reconciles. Clean independent work survives. |
| Lower the budget mid-run; give the operator a fresh file | No calls beyond the new allowance; prior spend remains visible. One team member can produce the required output from the new file without changing code. |
| Browser-only walkthrough | One operator uploads the file, explains a hold, signs only eligible bills and downloads the receipt. Refresh after signing: same run, same IDs, no new action. |
| Run a fixture with a distinctive dummy account number and email. Exercise a successful upload and an error. | Search the rendered page, browser responses, receipt download and application/error logs. Neither full test value may appear. The masked account ending must appear where needed. No deletion claim without a completed deletion record. |

## 4. Seven-hour build order

**Still open before kickoff:** get team approval for the data.gov.in signup; confirm RazorpayX test keys and balance; reconnect Crustdata MCP; ask the organizers about pre-written code and input formats. In the first 30 minutes, inspect the actual request format and a statement row before choosing the input adapter and reference mapping.

| Clock | Done means |
| --- | --- |
| 0:00-0:30 | Read the kickoff kit; lock the output format; decide whether any input needs an LLM. Check keys (RazorpayX test, data.gov.in, Crustdata), test balance, one sandbox payout and one useful live data call. If provider access fails, raise it immediately; do not disguise a mock. |
| 0:30-3:00 | Finish one clean item, one duplicate and one unknown. Wire browser upload, review and sign-off to saved backend state. By hour three, an operator can inspect a real row and its evidence. Commit working increments to the organizer repo. |
| Hour 3-5:00 | Apply the organizer's change. Finish posting/reconciliation, legal-name sourcing, receipt download and reconnect behavior. Kill and restart during a browser run; verify the IDs, not just the status labels. |
| 5:00-7:00 | No new integrations. Rehearse double upload, one approval, kill and restart. Run the privacy check on the receipt and error path. Check the page at projector and phone widths. Finish README (job, payer, inputs, result, sources, pass mark), diagram (calls, retries, approval, cost ledger) and logs. Freeze at seven hours. |

## 5. The finals: show, don't claim

Screening is unscored. In the finals the split is **live run 20, robustness 15, design 15, ethics 25, finance 25**. Ethics and finance together are half the points: put their proof on the receipt, not in backup slides.

| Three-minute demo | What the judge sees |
| --- | --- |
| 0:00-0:30 | Load the **unseen request**. Show the client's job, the expected result and the run budget. |
| 0:30-1:15 | Open one supported result and, if present, one exception. Show the exact evidence, masked destination or ledger rule, and the next action. The controller signs only if needed. |
| 1:15-2:20 | Leave time for the judge's kill, **whenever it comes**. Restart the same run. Prove no double action with provider IDs or committed posting IDs, not a green checkmark. |
| 2:20-3:00 | Show what actually finished, what is waiting, what the run cost and the personal-data block. If a statement or confirmation is missing, leave it visibly unresolved. |

**Five-minute live fix:** implement the judge's actual change. Rehearse one example: lower the spend cap, run a fresh input, show the changed decision and confirm prior actions weren't replayed. **Two-minute design Q&A:** at 100x volume, rate-limit workers behind a queue and retain stable action IDs; for a second client, isolate records, approvals, credentials and budgets.

**Offer to test:** Rs 2,000 per weekly run of up to 100 bills, including evidence and follow-up tracking for up to five exceptions. Bank payout fees are separate. Kavach finds the discrepancy, gathers the records, points to the trusted contact if one exists, and tracks the next step. The customer's AP lead confirms bank changes through that trusted contact. A separate authorized person approves the update. Agree any extra work in advance. Do not charge per alert.

**How to prove value:** At illustrative labor costs of Rs 250-500 per hour, the fee needs to save **4-8 staff-hours per run** on labor alone. In a paid, read-only shadow pilot, compare the same historical batch with and without Kavach. Count the customer's callback time under both methods. Report total handling minutes, false holds and late clean payments. Separately report Kavach's API/model spend, conversion rate, sponsored credits and staff time. The face value of a held bill is not a saving.

**Only stretch if everything passes:** let the judge select a receipt line and see the client record, live source and rule behind that single decision side by side. Do not add another risk score.
