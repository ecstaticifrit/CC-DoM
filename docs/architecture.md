# Kavach architecture

Words follow [`GLOSSARY.md`](../GLOSSARY.md). Status: the page, upload, saved runs, masking, checks, sign-off, the bank payment file, reconciliation from the bank statement, the two-person bank change, cost ledger and receipt work and are tested. Kavach never moves money ([ADR 0004](adr/0004-bank-payment-file.md)). Dashed boxes are planned.

```mermaid
flowchart TD
    B["Browser: server-rendered run page<br/>polls status.json, shows Connection lost"] -->|"upload CSV, sign batch,<br/>download file, upload statement"| API["FastAPI app (one Python process)"]
    ORG["Organizer"] -->|"GET /runs/run_id/result.json"| API
    API <--> DB[("SQLite WAL file (KAVACH_DB)<br/>runs, rows, outbox, payment_files,<br/>beneficiary_changes, reconciliations, ledger_calls")]
    API --> RULES["Rules engine<br/>versioned config (rule_version)"]
    RULES --> AD["Source adapters<br/>timeouts, cost reservation, run allowance"]
    AD -->|"company_identify, 0.2 credit/match"| CD["Crustdata API"]
    AD -->|"GET ifsc.razorpay.com/IFSC, free"| IFSC["Razorpay IFSC API (public)"]
    AD -->|"live fetch"| WEB["AWS legal page (web)"]
    AD -.->|"planned, needs key"| MCA["MCA company master, data.gov.in"]
    AD -->|"each call and its cost"| DB
    RULES -->|"ready / hold / cannot verify + evidence"| DB
    API --> CHG{"Bank change<br/>AP lead callback, then a different authorizer"}
    CHG -->|"new beneficiary version, bill checked again"| DB
    API --> GATE{"Approval gate<br/>controller signs exact batch<br/>server rechecks fingerprints"}
    GATE -->|"one transaction: signed bills + bank references + frozen payment file"| DB
    DB -->|"same bytes and SHA-256 on every download"| FILE["Bank payment file (CSV)"]
    FILE -->|"controller uploads"| BANK["Client's bank portal"]
    BANK -->|"statement CSV"| REC["Reconciliation<br/>one debit by bank reference + amount + currency"]
    REC -->|"paid / returned / open with reason"| DB
    DB --> RCPT["Run receipt<br/>outcomes, references, cost ledger, personal data"]
    RCPT --> B
```

## Components

| Component | Job |
| --- | --- |
| Run page | Server-rendered HTML with a little JavaScript. Two jobs, upload, review, sign-off, payment file, statement upload, receipt. Shows only masked fields. |
| FastAPI app | Parses the CSV, saves the run, serves the page, `result.json`, `receipt.json` and `status.json`. |
| SQLite (WAL) | The only state. Path from `KAVACH_DB`. |
| Rules engine | Decides ready, hold or cannot verify from client records, bills already signed and source evidence. Each run saves its `rule_version`. |
| Source adapters | One adapter per source. Each sets a timeout, reserves cost first and logs the actual cost. |
| Approval gate | Accepts a sign-off only for the exact bills, amounts, currencies, destinations and beneficiary versions shown. |
| Payment file | `kavach/payfile.py`. One CSV per sign-off, written in the sign-off transaction and never changed. Downloads are counted. |
| Bank change screen | `/runs/{run_id}/rows/{n}/change`. The AP lead records the callback through the trusted contact. A different person authorizes the new beneficiary version. The bill is then checked again. |
| Reconciliation | `kavach/reconcile.py`. Matches each signed bill to exactly one statement debit by bank reference, amount and currency. A credit with the reference is a returned payment. |
| Receipt | What finished, what waits, references, cost ledger, personal-data block. |

## Data flow: Pay approved bills

1. The controller uploads bills. Kavach saves every row, masked for display.
2. Rules compare each bill with the approved beneficiary version, payment history and bills Kavach has already signed. A changed account or possible duplicate becomes a hold.
3. Adapters check the IFSC code (Razorpay IFSC API) and corroborate the carrier domain (Crustdata `company_identify`, exact domain equality). A sender-domain mismatch means review, not an accusation.
4. The page shows **Needs attention** first, then the clean batch and its total.
5. The controller signs. The server rechecks and, in one transaction, saves the signed bills and the payment file.
6. The controller downloads the file and uploads it to the bank.
7. The controller uploads the bank statement. Each bill becomes paid, returned or stays open with the reason.

## Data flow: Post bank lines

1. The controller uploads statement lines.
2. Kavach finds the legal payee from client records, a registry record (planned) or the vendor legal page (AWS contracting-party page, fetched live).
3. A client ledger rule picks the account. Possible duplicates are held. Unknown descriptors are **cannot verify**, with the missing fact named.
4. This job makes no payments.

## Where approvals sit

- Controller sign-off at the approval gate, before any payment file exists.
- AP lead callback through the trusted contact, and a separate authorizer, before a changed beneficiary can enter a batch.
- A beneficiary change after sign-off never changes the frozen file. The page warns "Do not upload this file as it is" and names the bill.

## Where retries sit

- Source adapters: timeouts. A failed source marks only the affected fact **cannot verify**.
- There are no payment retries. A download returns the same file; a second statement upload changes nothing that is already recorded.

## Where the cost ledger sits

The adapters write each external call to `ledger_calls`: source, time, credits and status. The rules stop calls at the run allowance in `kavach/config.toml` (600 s, 150 credits). The receipt sums the ledger. Crustdata: 1 credit = $0.30.

## Exactly-once payment procedure

1. The controller signs an exact batch.
2. The server rechecks each item: same amount, currency, destination and beneficiary version.
3. In one SQLite transaction, Kavach saves each bill under a unique `(client ID, bill ID)` with its bank reference (`KV` + bill ID), and writes the payment file bytes and SHA-256.
4. A second upload of the same bill finds the saved record and shows **Already signed earlier**. It never enters a second file.
5. The bank statement proves payment: exactly one debit with the reference, amount and currency. Two debits are reported as a possible double payment by the bank.

## Kill and restart behaviour

- A kill before step 3 commits leaves no signed bill and no file. A kill after it leaves both. There is no state in between.
- After a restart, the same run URL shows the same rows, the same file and the same SHA-256. The page shows "Connection lost" with the last update time while the server is down, then reconnects without resubmitting.
