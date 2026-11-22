# Kavach — supplier payment runs

"One carrier changed its bank account. Why should every other carrier miss Friday's payment? Kavach holds that bill, gets the rest ready for your sign-off, and gives you a receipt showing where every rupee went or why it is still waiting."

Track: Buying and paying. Kavach never moves money: it writes a bank payment file that the controller uploads to the bank. All data in this repo is test data. Shared words are in [`GLOSSARY.md`](GLOSSARY.md). Decisions are in [`docs/adr/`](docs/adr/).

**Status labels in this file.** "Working" means the team tested it. "Not done at freeze" lists what is missing. Kavach does not claim anything works until a test or the live demo shows it.

## The service

For the Speed Post bill sample, see [dataset provenance](data/SOURCES.md). Prices are public; payment instructions are fictional.

**The job.** Kavach does the outsourced payables desk's work between bill approval and statement reconciliation. The client is a mid-size Indian logistics (3PL) company. Each week it must pay many carriers. The work is:

1. Compare approved bills with the approved bank destinations and the payment history.
2. Hold the bills that are not safe to pay, with the evidence, an owner and a next step.
3. Prepare an exact clean batch for the controller to sign.
4. Generate a frozen bank payment file without adding a second instruction for the same bill.
5. Reconcile the signed bills against the bank statement.

**Who does it today.** In-house AP (accounts payable) staff, outsourced payables desks, and freight payment firms such as Cass Information Systems.

**Who pays.** The logistics company's finance controller.

**Pricing.** Per bill, not per run or lookup. The rate and billable event are not set; the demo does not charge. Friday carrier payments are the hackathon example, not a restriction.

## What it does now

**Input.** Start with a bill CSV. The statement belongs to that same run after sign-off.

| Job | Columns |
| --- | --- |
| Pay approved bills | `bill_id, carrier_id, carrier_name, amount, currency, account_number, ifsc, sender_email` (`sender_email` optional) |
| Reconcile a signed run | `date, description, amount, currency, reference, type` (`type` defaults to debit; use credit for a return) |

**Working (tested):**

- The start page accepts approved supplier bills and identifies the logistics examples as demo data.
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
  - Sign-off and the **bank payment file** are written in one SQLite transaction ([ADR 0004](docs/adr/0004-bank-payment-file.md)). Each bill gets one bank reference (`KV` + bill ID) and is in exactly one line of one file, ever. The file is frozen: every download returns the same bytes and SHA-256, also after a restart. Downloads are counted. Uploading the same bills again shows **Already signed earlier** and creates no new line.
- Each run enforces internal credit and time limits. When a required check cannot finish, independent bills can still proceed.
- *Run receipt* (`/runs/{id}/receipt.json` and on the page): held, signed, paid per bank, waiting and returned counts; the personal data used, how it is masked, the retention policy, payment-file downloads and the person-lookup count from the call log (zero). Every external call and its credit cost is saved in the `ledger_calls` table; the demo screens do not show metering.

**Working (tested):**

- *Reconciliation.* Upload the bank statement CSV on the run page. A bill is **paid** only when exactly one debit carries its bank reference with the same amount and currency. Two debits → open as a possible double payment by the bank. A different amount or no debit → open with the reason. Uploading the same statement again changes nothing.
- *Returned payment.* A credit line with the bill's bank reference reopens the bill as **Reopened: payment returned**, with an owner and next step.
- *Two-person bank change.* On a **Held: bank account changed** bill, **Record callback and authorization** opens a screen. The AP lead records the callback through the trusted contact. A different person authorizes the new beneficiary version. The bill is then checked again against every rule, including bills already signed. A denied callback keeps the bill held as a possible fraud attempt. Names are typed; there are no user logins yet.
- *Change after sign-off.* The file never changes after sign-off. If a carrier's beneficiary changes later, the file shows **Do not upload this file as it is** and names the bill.
- *Value block.* The run page starts with "What Kavach did in this run": bills checked and how long it took, clean bills ready, money held (not counted as savings), exceptions with an owner, and bills paid twice (including double debits found on the statement).

**Not done (stated honestly):**

- The payment file uses a generic CSV layout. Each bank (for example ICICI, HDFC) has its own bulk-upload format; the layout is set per client at onboarding.
- Kavach cannot see whether the controller uploaded the file. The bank statement is the only proof of payment.
- MCA registry integration needs a data.gov.in key; the Swiggy payee cites the MCA record from client records.

**Finished result.** A run receipt and `result.json` with, for each row: the outcome (ready, held, cannot verify, signed, paid per bank, returned, posted), the evidence, the owner and next step for each exception, and bank references, payment file IDs or posting IDs.

**Pass mark** (from the spec and the organizers' example):

- Five bills (three clean, one possible duplicate, one changed account): three ready for sign-off, two held with reasons, no payment file before sign-off, exactly three payment-file lines with three distinct bank references after sign-off.
- Upload the bills twice, sign, kill the process. Restart: the same file (same SHA-256), still exactly three lines, no fourth payment.

**Where it still needs a person:**

- The **controller** signs the batch. Nothing is paid without that sign-off.
- The **AP lead** makes the callback through the trusted contact (a carrier contact recorded before the change request).
- A separate **authorizer** approves a beneficiary change. A recorded callback alone does not release the bill.
- Kavach never contacts carriers. It records a beneficiary change only after the AP lead's callback and a separate authorizer's approval.

## What it could do in the future

| Next build | Why not now |
| --- | --- |
| MCA company registry integration for Indian legal payees | It needs a data.gov.in API key. Signup and approval did not fit the build window. |
| Live reconciliation against bank feeds | It needs a bank-feed connection per client. In the event we can only reconcile against an uploaded statement. |
| Bank-account name check (who owns the account) | RBI's beneficiary name lookup has no API for third parties. Payment-provider account validation needs a provider account. |
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
   Keys: `CRUSTDATA_API_KEY`. `DATA_GOV_IN_API_KEY` is for the planned registry integration.
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

- **Runs on:** one Python process. FastAPI serves the server-rendered page and the JSON endpoints. There is no background worker: sign-off writes the payment file in the same transaction. There is no separate frontend ([ADR 0002](docs/adr/0002-one-process-server-rendered-page.md)). The judges can kill and restart one process.
- **State:** one SQLite file in WAL mode. Set the path with `KAVACH_DB`. Tables: `runs`, `rows` (with evidence and decisions), `outbox` (signed bills, bank references, file IDs, paid or returned per statement), `payment_files` (frozen file bytes, SHA-256, download count), `beneficiary_changes`, `reconciliations` and `ledger_calls` (every external call and its cost). The browser and `result.json` read the same rows.
- **Agents and models:** no LLM in v1. The inputs are structured (CSV), so parsers extract the fields and rules decide. A model would only be added to read unstructured invoices or emails, and it would never decide or send anything.
- **Tools and data:** source adapters with timeouts, retries and cost reservation call Crustdata, the Razorpay IFSC API (public, no key) and the vendor's legal page. Rules have a version (`kavach/config.toml`, `rule_version`), and every run saves the version it used.
- **Where it calls Crustdata:** `company_identify` in the Pay approved bills job. It corroborates the carrier's recorded web domain. Kavach compares domains by exact equality only. Kavach never uses a name-only match.

## Its sources and checks

| Source | What it proves | What it cannot prove | Cost per call |
| --- | --- | --- | --- |
| Client records (approved beneficiary versions, payment history, trusted contacts, ledger rules, onboarding records) | The approved destination, past payments, who to call back, which ledger account | That a new bank account is genuine | Rs 0 |
| Razorpay IFSC API (`https://ifsc.razorpay.com/<IFSC>`, no key) | The IFSC code exists and names a bank branch | Who owns the account | Rs 0 |
| Crustdata `company_identify` | A company directory entry agrees with the carrier's recorded domain | That the sender is who they claim; a lookalike domain only triggers review | 0.2 credit per match ($0.06) |
| Vendor legal page (AWS contracting-party page, fetched live) | The legal entity name, quoted exactly (for example, Amazon Web Services EMEA SARL) | That this charge belongs to that entity, without a link from the statement or a client record | Rs 0 direct fetch; 1 credit ($0.30) if fetched through Crustdata `web_enrich_live` |
| MCA company master data, data.gov.in (planned) | The registered `CompanyName` of an Indian company | That the company was the payee of this charge | Free with key (not integrated) |
| Bank statement (uploaded CSV) | A debit with the bill's bank reference, amount and currency left the account; a credit with it came back | That the account belongs to the carrier | Rs 0 |

Crustdata pricing on our pay-as-you-go account: 1 credit = $0.30 (dashboard). Other costs measured during exploration: `company_enrich` 2 credits, `web_search_live` 1 credit, `web_enrich_live` 1 credit.

**Where a person approves:** the controller signs the exact batch (bills, amounts, destinations, beneficiary versions). The AP lead records the callback. A separate authorizer approves a beneficiary change. An edit after sign-off voids the approval for that item only.

**Internal metering:** Kavach saves adapter calls and their costs in SQLite. Customer receipts show payment outcomes and source evidence, not internal expenses.

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
| RazorpayX payouts | The team has no RazorpayX account | Kavach writes a bank payment file and reconciles from the statement ([ADR 0004](docs/adr/0004-bank-payment-file.md)) |
| Next.js frontend plus API | Two services to kill, restart and keep in sync | One server-rendered FastAPI process ([ADR 0002](docs/adr/0002-one-process-server-rendered-page.md)) |

## Your demo video

Link: <add before submission>

Two-minute storyboard:

Use one file: `data/samples/demo_bills.csv` (also linked on the start page). Do one warm-up run first, and wait a minute between runs (Crustdata rate limit).

| Bill | What it shows | Outcome |
| --- | --- | --- |
| D-201, D-202, D-203 | Clean bills; D-202 is a small owner with no company record | Ready to sign |
| D-204 | Bank account changed, sender `bluedart-payments.com` (no company owns it) | Held: bank account changed, with Crustdata profile and news |
| D-205 | Same carrier and amount as a recent payment | Held: possible duplicate |
| D-206 | Approved account, but sender `bluedrat.com` (one-letter swap) | Review: sender domain |
| D-207 | Account number missing | Cannot verify: missing account_number |
| D-208 | Carrier not in client records | Cannot verify |

1. **0:00 Upload.** Upload `demo_bills.csv`. Read the summary: 3 clean, 5 need attention.
2. **0:20 Why.** Open D-204: the HELD stamp, approved vs requested account, and the Crustdata checks. Use the arrow keys to step to D-206 and D-207.
3. **0:50 Two people.** On D-204, select **Record callback and approval** to show the two-step check. (You can stop at step 1.)
4. **1:05 Sign.** Tick D-201 to D-203, select **Review and sign**, then press and hold. The SIGNED stamp lands on the payment file.
5. **1:25 Kill and restart.** Stop the server, start it again, refresh. Same run, same file, same SHA-256, 3 lines.
6. **1:45 Receipt.** Show the personal-data block: masked accounts, zero person lookups, download count.
