# Kavach architecture

**Invariant: at most one committed payment instruction per `(client_id, bill_id)`, not exactly one execution at the bank.** This diagram describes the implemented paths: supplier payments and bank-line posting. ERP sync is a prototype, not an input on `main`.

Words follow [`GLOSSARY.md`](../GLOSSARY.md). Status: both jobs (Pay approved bills, Post bank lines), the page, upload, saved runs, masking, checks, sign-off, the bank payment file, reconciliation from the bank statement, the two-person bank change, cost ledger and receipt work and are tested. Kavach never moves money ([ADR 0004](adr/0004-bank-payment-file.md)). Dashed boxes are planned.

```mermaid
flowchart TD
    B["Browser: server-rendered run page<br/>polls status.json, shows Connection lost"] -->|"choose job, upload CSV, sign batch,<br/>download file, upload statement"| API["FastAPI app (one Python process)"]
    ORG["Organizer"] -->|"GET /runs/run_id/result.json<br/>GET /runs/run_id/receipt.json (cost block)"| API
    API <--> DB[("SQLite WAL file (KAVACH_DB)<br/>runs, rows, outbox, payment_files,<br/>beneficiary_changes, reconciliations, ledger_calls")]
    API -->|"bank lines: same SHA-256 opens the saved run"| DB
    API --> RULES["Rules engine<br/>bills: payrules.py, bank lines: postings.py<br/>versioned config (rule_version)"]
    RULES --> AD["Source adapters<br/>timeouts, one retry on HTTP 429,<br/>cost reservation, run allowance"]
    AD -->|"company_identify 0.2 credit/match, company_enrich 2,<br/>web_search_live 1, web_enrich_live 1"| CD["Crustdata API"]
    AD -->|"GET ifsc.razorpay.com/IFSC, free"| IFSC["Razorpay IFSC API (public)"]
    AD -->|"live fetch (direct or via web_enrich_live)"| WEB["AWS legal page (web)"]
    AD -.->|"planned, needs key"| MCA["MCA company master, data.gov.in"]
    AD -->|"each call and its cost"| DB
    RULES -->|"ready / hold / cannot verify / posted + evidence"| DB
    RULES -->|"destination mismatch: exclude bill"| CHG{"Bank change<br/>AP lead callback, then a different authorizer"}
    CHG -->|"persist new beneficiary version"| DB
    CHG -->|"re-evaluate affected bill, not automatic release"| RULES
    API --> GATE{"Approval gate<br/>controller signs exact batch<br/>server rechecks fingerprints"}
    RULES -->|"ready rows only"| GATE
    GATE -->|"BEGIN IMMEDIATE: insert outbox if unique by client + bill ID; mark signed; store file bytes + SHA-256"| DB
    DB -->|"same bytes and SHA-256 on every download"| FILE["Bank payment file (CSV)"]
    FILE -->|"controller uploads"| BANK["Client's bank portal"]
    BANK -->|"statement CSV"| REC["Reconciliation<br/>one debit by bank reference + amount + currency"]
    REC -->|"one matching debit: paid; matching credit: returned; missing or ambiguous: open"| DB
    DB --> RCPT["Customer receipt<br/>outcomes, references, personal data; no internal spend"]
    RCPT --> B
```

## Decisions and trade-offs

| Decision | Compared with | Benefit and boundary |
| --- | --- | --- |
| One FastAPI process, Jinja, SQLite WAL | Separate SPA, API and worker | HTML and JSON reopen the same stored run. Fewer moving parts to deploy and recover; SQLite still serializes writers. [ADR 0002](adr/0002-one-process-server-rendered-page.md) |
| Versioned rules, with directory evidence separate from beneficiary authorization | A match-only dashboard or an LLM payment verdict | A real company can request an unapproved destination. Hold that bill with a reason; independent clean bills can proceed. An IFSC check confirms a branch, not account ownership. |
| Server-side row fingerprint at sign-off | Treat checked bill IDs as blanket approval | The comparison binds bill ID, amount, currency, account hash, IFSC and beneficiary version. Changed values do not match the old selection. The fingerprint is not a digital signature; the two-person demo checks distinct typed names, not authenticated identities. |
| Commit the outbox and frozen CSV in one transaction | Regenerate the file on download, retry a provider call, or simulate money movement | A crash leaves both the instruction and its bytes or neither. Downloads return the same bytes without sending money. The trade-off is a generic CSV, manual upload and no bank acknowledgement. [ADR 0004](adr/0004-bank-payment-file.md) |
| Match a statement debit by reference, amount and currency | Mark paid when the file is signed or downloaded | Distinguishes instructions from observed debits and returns. Requires statement evidence; the bank can still execute a file uploaded twice. |

**Reference constraint:** `payfile.bank_ref` uppercases and strips non-alphanumerics from the bill ID, prefixes `KV`, and truncates to 18 characters. The database enforces uniqueness, but different bill IDs can normalize to the same reference; this is not a collision-proof ID scheme.

## Components

| Component | Job |
| --- | --- |
| Start page | Two jobs (radio choice): Pay approved bills (default) and Post bank lines. Links the demo files `demo_bills.csv` and `brief_bank_lines.csv`. |
| Run page | Server-rendered HTML with a little JavaScript. Review, sign-off, payment file, statement upload, receipt. For bank lines: posted rows with legal payee, ledger account and posting ID, and a dialog with the chain from bank text to ledger. Shows only masked fields. |
| FastAPI app | Parses the CSV, saves the run, serves the page, `result.json`, `receipt.json` and `status.json`. |
| SQLite (WAL) | The only state. Path from `KAVACH_DB`. |
| Rules engine | `kavach/payrules.py` decides ready, hold or cannot verify for bills. `kavach/postings.py` decides posted, hold or cannot verify for bank lines. Each run saves its `rule_version`. |
| Source adapters | One adapter per source. Each sets a timeout, reserves cost first and logs the actual cost. |
| Approval gate | Accepts a sign-off only for the exact bills, amounts, currencies, destinations and beneficiary versions shown. |
| Payment file | `kavach/payfile.py`. One CSV per sign-off, written in the sign-off transaction and never changed. Downloads are counted. |
| Bank change screen | `/runs/{run_id}/rows/{n}/change`. The AP lead records the callback through the trusted contact. A different person authorizes the new beneficiary version. The bill is then checked again. |
| Reconciliation | `kavach/reconcile.py`. Matches each signed bill to exactly one statement debit by bank reference, amount and currency. A credit with the reference is a returned payment. |
| Receipt | What finished, what waits, references, personal-data block. `receipt.json` adds the `cost` block (each call, total credits, USD, INR, run limits). |

## Data flow: Pay approved bills

1. The controller uploads bills. Kavach saves every row, masked for display.
2. Rules compare each bill with the approved beneficiary version, payment history and bills Kavach has already signed. A changed account or possible duplicate becomes a hold.
3. Adapters check the IFSC code (Razorpay IFSC API) and corroborate the carrier domain (Crustdata `company_identify`, exact domain equality). A sender-domain mismatch means review, not an accusation.
4. The page shows **Needs attention** first, then the clean batch and its total.
5. The controller signs. The server rechecks and, in one transaction, saves the signed bills and the payment file.
6. The controller downloads the file and uploads it to the bank.
7. The controller uploads the bank statement. Each bill becomes paid, returned or stays open with the reason.

## Data flow: Post bank lines

1. The controller chooses **Post bank lines** and uploads statement lines (demo: `data/samples/brief_bank_lines.csv`).
2. If a run with the same file SHA-256 exists, Kavach opens that run. Nothing is posted twice.
3. A client descriptor rule links the bank text to a merchant. Crustdata `company_identify` checks the merchant domain.
4. Kavach finds the legal payee from a client registry record (MCA CIN) or the vendor legal page (AWS contracting-party page), fetched live through Crustdata `web_enrich_live` or directly.
5. A client ledger rule picks the account, and the line gets a posting ID. A second line with the same payee, amount and date is held as a possible duplicate. An unknown descriptor is **cannot verify**, with the missing fact named; Crustdata `web_search_live` results show as suggestions only.
6. This job makes no payments.

## Where approvals sit

- Controller sign-off at the approval gate, before any payment file exists.
- AP lead callback through the trusted contact, and a separate authorizer, before a changed beneficiary can enter a batch.
- A beneficiary change after sign-off never changes the frozen file. The page warns "Do not upload this file as it is" and names the bill.

## Where retries sit

- Source adapters: timeouts. Crustdata calls wait 1.5 s and retry once on HTTP 429. A failed source marks only the affected fact **cannot verify**, and the call is saved with its status.
- There are no payment retries. A download returns the same file; a second statement upload changes nothing that is already recorded.

## Where the cost ledger sits

The adapters write each external call to `ledger_calls`: source, time, credits and status. The rules stop calls at the run allowance in `kavach/config.toml` (600 s, 150 credits). `GET /runs/{run_id}/receipt.json` lists each call and sums the credits, USD and INR. Crustdata: 1 credit = $0.30. The run page does not show costs. Internal spend is not customer pricing.

## At-most-once instruction creation

1. The controller signs an exact batch.
2. The server rechecks each item: same amount, currency, destination and beneficiary version.
3. In one SQLite transaction, Kavach saves each bill under a unique `(client ID, bill ID)` with its bank reference (`KV` + bill ID), and writes the payment file bytes and SHA-256.
4. A second upload of the same bill finds the saved record and shows **Already signed earlier**. It never enters a second file.
5. The bank statement proves payment: exactly one debit with the reference, amount and currency. Two debits are reported as a possible double payment by the bank.

## Kill and restart behaviour

- A kill before step 3 commits leaves no signed bill and no file. A kill after it leaves both. There is no state in between.
- After a restart, the same run URL shows the same rows, the same file and the same SHA-256. The page shows "Connection lost" with the last update time while the server is down, then reconnects without resubmitting.
