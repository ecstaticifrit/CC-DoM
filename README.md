# Kavach — close the Friday carrier payment run

"One carrier changed its bank account. Why should every other carrier miss Friday's payment? Kavach holds that bill, gets the rest ready for your sign-off, and gives you a receipt showing where every rupee went or why it is still waiting."

Track: Buying and paying. Only test money moves (RazorpayX test mode). Shared words are in [`GLOSSARY.md`](GLOSSARY.md). Decisions are in [`docs/adr/`](docs/adr/).

**Status labels in this file.** "Working" means the team tested it. "Not done at freeze" lists what is missing. Kavach does not claim anything works until a test or the live demo shows it.

## The service

**The job.** Kavach does the outsourced payables desk's work between bill approval and statement reconciliation. The client is a mid-size Indian logistics (3PL) company. Each week it must pay many carriers. The work is:

1. Compare approved bills with the approved bank destinations and the payment history.
2. Hold the bills that are not safe to pay, with the evidence, an owner and a next step.
3. Prepare an exact clean batch for the controller to sign.
4. Pay each signed bill exactly once, also through a crash.
5. Record bank charges that already left the account to the correct ledger account and legal payee.
6. Reconcile payouts against the bank statement.

**Who does it today.** In-house AP (accounts payable) staff, outsourced payables desks, and freight payment firms such as Cass Information Systems.

**Who pays.** The logistics company's finance controller.

**Price to test.** Rs 2,000 per weekly run of up to 100 bills. The price includes evidence and follow-up tracking for up to five exceptions. Bank payout fees are separate. There is no charge per alert. On labour alone, the fee must save 4 to 8 staff-hours per run (at an illustrative Rs 250 to Rs 500 per hour). See [`docs/pilot-offer.md`](docs/pilot-offer.md) for the offer, the paid read-only pilot and the scorecard.

## What it does now

**Input.** One CSV file per run. The kickoff format can replace these columns.

| Job | Columns |
| --- | --- |
| Pay approved bills | `bill_id, carrier_id, carrier_name, amount, currency, account_number, ifsc, sender_email` (`sender_email` optional) |
| Post bank lines | `date, description, amount, currency, reference` (`reference` optional) |

**Working (tested):**

- One page offers two jobs: **Pay approved bills** and **Post bank lines**. It shows the run allowance (time and credits) and the sandbox label before you start.
- You upload a CSV. A bad file gets a readable error. The error never repeats input values.
- Each run is saved in SQLite (WAL mode) and has a stable URL (`/runs/{run_id}`). After a restart, the same URL shows the same run. You do not upload again.
- A row with a missing required value stays visible as **Cannot verify**, and the page names the missing field.
- Account numbers show only the last 4 digits. Emails show only the domain. This applies to the page, the organizer output and the logs.
- The organizer output is at `GET /runs/{run_id}/result.json`. It reads the same saved run as the page.
- The page polls `GET /runs/{run_id}/status.json`. If the server stops, the page shows "Connection lost" with the last update time. It reconnects to the same run.

**Working (tested, with live IFSC and live AWS page calls):**

- *Pay approved bills.* Kavach checks each bill against client records (`data/carriers.json`):
  - Bank account differs from the approved beneficiary version, or is a retired account → **Held: bank account changed**, with both masked endings, the trusted contact's role and record ID, and the next step.
  - Bill already paid → hold. Same carrier, amount and currency as a recent payment or an earlier row → **possible duplicate**, not proven.
  - IFSC checked live at `ifsc.razorpay.com`; a 404 → **Held: invalid IFSC**. A branch never counts as proof of account ownership.
  - Sender email domain differs from the carrier's recorded domain → **Review**, never an accusation. When `CRUSTDATA_API_KEY` is set, Crustdata `company_identify` corroborates the recorded domain.
  - The controller ticks ready bills, sees "Approve N bills for Rs X" with exact bills, destinations and beneficiary versions, and signs. The server rechecks each bill's fingerprint. Held or changed bills cannot be sent.
  - The approved intent, retry key and a 32-character reference are saved in SQLite before any RazorpayX call. A worker thread sends test payouts. After a crash it retries only with the same key and body, then looks the payout up by reference; more than one match → `pending_review` ([ADR 0001](docs/adr/0001-payout-recovery-never-replaces.md)). Uploading the same bills again shows **Already signed earlier** and pays nothing twice.
- *Post bank lines.* Legal payee from client records, a registry citation or the vendor's legal page (the AWS contracting-party page is fetched live and quoted). The client's ledger rule sets the account. Possible duplicates are held; unknown descriptors are **Cannot verify** with the missing fact named. Zero payout calls.
- *Run receipt* (`/runs/{id}/receipt.json` and on the page): held, signed, submitted, processed and posted counts; every external call with its status and credits, converted to dollars and rupees with the rate shown; model spend (none); the personal data used, how it is masked, the retention policy and the person-lookup count from the call log (zero).

**Not done at freeze (stated honestly):**

- Live RazorpayX payouts need the team's test keys in `.env`. Without them, signed bills show "Payout not sent: RazorpayX test keys are missing". The exactly-once logic is tested against a fake provider that mimics Razorpay's idempotency.
- Reconciliation against a bank statement and the T+3 reversal reopen are not built. The worker refreshes provider status (processed, reversed) but the page does not reopen reversed items yet.
- The run allowance is shown but not yet enforced as a hard stop.
- The two-person beneficiary change (callback + separate authorizer) is described in the next step text but has no screen yet.
- MCA registry integration needs a data.gov.in key; the Swiggy payee cites the MCA record from client records.

**Finished result.** A run receipt and `result.json` with, for each row: the outcome (ready, held, cannot verify, submitted, processed, posted), the evidence, the owner and next step for each exception, and provider or posting IDs.

**Pass mark** (from the spec and the organizers' example):

- Five bills (three clean, one possible duplicate, one changed account): three ready for sign-off, two held with reasons, zero payouts before sign-off, exactly three provider payout IDs after sign-off.
- Upload the bills twice, sign once, kill the process after the provider accepts. Restart: still exactly three distinct payout IDs, no fourth payment.
- The four October lines: Swiggy Limited → staff meals; Amazon Web Services EMEA SARL → cloud hosting; the second AWS line held as a possible duplicate; the Sharma line **Cannot verify**; zero payout calls.

**Where it still needs a person:**

- The **controller** signs the batch. Nothing is paid without that sign-off.
- The **AP lead** makes the callback through the trusted contact (a carrier contact recorded before the change request).
- A separate **authorizer** approves a beneficiary change. A recorded callback alone does not release the bill.
- Kavach never contacts carriers and never changes a beneficiary.

## What it could do in the future

| Next build | Why not now |
| --- | --- |
| MCA company registry integration for Indian legal payees | It needs a data.gov.in API key. Signup and approval did not fit the build window. |
| Live reconciliation against bank feeds | It needs a bank-feed connection per client. In the event we can only reconcile against an uploaded statement. |
| Bank-account name check (who owns the account) | RBI's beneficiary name lookup has no API for third parties. RazorpayX account validation does not work in test mode. |
| Shared fraud signal across clients (for example, one bank account claimed by two carriers) | It needs more than one client and a data-sharing agreement. |
| MCP tool `authorize_payment` for AI agents | First the rules and the approval gate must be stable for human users. |

## The future of this service

When agents can do the whole payables job, they will also send the money. An agent that pays needs a firewall outside the model. The model can propose a payment. Rules, records and a signed approval decide whether it goes out. Kavach is that firewall.

- **Autonomy slider.** The client chooses what Kavach may release alone. For example: known carrier, same beneficiary version, amount under a limit. Everything else waits for a person.
- **Every human override becomes a test case.** When a person releases a hold or stops a ready bill, Kavach saves the case with its evidence. The rules must pass every saved case before a new rule version goes live.

## How to run it

On a fresh clone:

1. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh` (or `brew install uv`).
2. Install dependencies:
   ```bash
   uv sync
   ```
3. Copy the environment file and fill in your own keys. Never commit `.env`.
   ```bash
   cp .env.example .env
   ```
   Keys: `RAZORPAYX_KEY_ID`, `RAZORPAYX_KEY_SECRET` (RazorpayX **test** keys), `RAZORPAYX_SOURCE_ACCOUNT_NUMBER`, `CRUSTDATA_API_KEY`. `DATA_GOV_IN_API_KEY` is for the planned registry integration.
4. Start the server:
   ```bash
   uv run python -m kavach
   ```
5. Open http://127.0.0.1:8000.
6. Upload a sample file from `data/samples/`.
7. Run the tests:
   ```bash
   uv run pytest -q
   ```

Optional environment variables: `KAVACH_DB` (database file, default `./kavach.db`), `HOST`, `PORT`.

## How it's built

Full diagram and the exactly-once procedure: [`docs/architecture.md`](docs/architecture.md).

- **Runs on:** one Python process. FastAPI serves the server-rendered page and the JSON endpoints. A background worker thread in the same process sends payouts. There is no separate frontend ([ADR 0002](docs/adr/0002-one-process-server-rendered-page.md)). The judges can kill and restart one process.
- **State:** one SQLite file in WAL mode. Set the path with `KAVACH_DB`. Tables: `runs`, `rows` (with evidence and decisions), `outbox` (approved payouts, retry keys, references, provider IDs) and `ledger_calls` (every external call and its cost). The browser and `result.json` read the same rows.
- **Agents and models:** no LLM in v1. The inputs are structured (CSV), so parsers extract the fields and rules decide. A model would only be added to read unstructured invoices or emails, and it would never decide or send anything.
- **Tools and data:** source adapters with timeouts, retries and cost reservation call Crustdata, the Razorpay IFSC API, the vendor's legal page and RazorpayX. Rules have a version (`kavach/config.toml`, `rule_version`), and every run saves the version it used.
- **Where it calls Crustdata:** `company_identify` in the Pay approved bills job. It corroborates the carrier's recorded web domain. Kavach compares domains by exact equality only. Kavach never uses a name-only match.

## Its sources and checks

| Source | What it proves | What it cannot prove | Cost per call |
| --- | --- | --- | --- |
| Client records (approved beneficiary versions, payment history, trusted contacts, ledger rules, onboarding records) | The approved destination, past payments, who to call back, which ledger account | That a new bank account is genuine | Rs 0 |
| Razorpay IFSC API (`https://ifsc.razorpay.com/<IFSC>`, no key) | The IFSC code exists and names a bank branch | Who owns the account | Rs 0 |
| Crustdata `company_identify` | A company directory entry agrees with the carrier's recorded domain | That the sender is who they claim; a lookalike domain only triggers review | 0.2 credit per match ($0.06) |
| Vendor legal page (AWS contracting-party page, fetched live) | The legal entity name, quoted exactly (for example, Amazon Web Services EMEA SARL) | That this charge belongs to that entity, without a link from the statement or a client record | Rs 0 direct fetch; 1 credit ($0.30) if fetched through Crustdata `web_enrich_live` |
| MCA company master data, data.gov.in (planned) | The registered `CompanyName` of an Indian company | That the company was the payee of this charge | Free with key (not integrated) |
| RazorpayX test payouts | The provider received (submitted) and completed (processed) a test payout; payout ID and reference | That the account belongs to the carrier (account validation does not work in test mode) | Rs 0 in test mode |

Crustdata pricing on our pay-as-you-go account: 1 credit = $0.30 (dashboard). Other costs measured during exploration: `company_enrich` 2 credits, `web_search_live` 1 credit, `web_enrich_live` 1 credit.

**Where a person approves:** the controller signs the exact batch (bills, amounts, destinations, beneficiary versions). The AP lead records the callback. A separate authorizer approves a beneficiary change. An edit after sign-off voids the approval for that item only.

**Cost ledger on the receipt:** Kavach saves every external call with the source, the status, the time and the credits it cost. The receipt shows the total in credits, dollars and rupees with the conversion rate used. The run allowance (`kavach/config.toml`: 600 seconds, 150 credits) is shown; enforcing it as a hard stop is not built yet.

## The approaches you tried

**Ideas we dropped before we chose the payment run:**

- **Outbound sales (AI SDR).** The market is crowded and the ethics are weak (cold outreach to real people).
- **Backhaul freight brokerage.** Crustdata cannot find cargo or truck capacity.
- **Credit desk (carrier and customer credit checks).** In our checks, headcount stayed flat before insolvency, so the data gave no early warning.
- **The payment run.** The job has a clear buyer, a clear fee and a clear pass mark ("each invoice paid exactly once").

**What we learned while building:**

| Tried | Result | What we do now |
| --- | --- | --- |
| Crustdata name-only company matching | Wrong company in 2 of 6 tests | Anchor on domains, never on names ([ADR 0003](docs/adr/0003-legal-payee-sources.md)) |
| Fuzzy domain matching | `asia.com` matched unrelated firms at confidence 1.0 | Exact domain equality only; one or two edits → review |
| RazorpayX bank-account validation | Does not work in test mode | We never claim account-ownership verification |
| Next.js frontend plus API | Two services to kill, restart and keep in sync | One server-rendered FastAPI process ([ADR 0002](docs/adr/0002-one-process-server-rendered-page.md)) |

## Your demo video

Link: <add before submission>

Two-minute storyboard:

1. **0:00 Request in.** Choose Pay approved bills, upload five bills. Show the allowance and the sandbox label.
2. **0:20 Holds explained.** Open the changed-account hold: old and new account endings, evidence, owner (AP lead), next step, client cutoff. Open the possible-duplicate hold.
3. **0:45 Sign 3.** "Approve 3 bills for Rs X". The confirmation lists the exact bills and masked destinations.
4. **1:00 Kill.** Stop the process after the provider accepts. The page shows "Connection lost".
5. **1:10 Restart.** Same run URL. The same 3 RazorpayX payout IDs. No fourth payout. No payout for either hold.
6. **1:30 Posting example.** Post the October lines: Swiggy Limited → staff meals, AWS EMEA SARL → cloud hosting, one duplicate held, Sharma **Cannot verify**, zero payout calls.
7. **1:50 Receipt.** Cost ledger (each call and its cost) and the personal-data block (masked fields, retention policy).
