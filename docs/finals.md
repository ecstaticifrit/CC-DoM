# Finals prep

Words follow [`GLOSSARY.md`](../GLOSSARY.md). Scoring: live run 20, robustness 15, design 15, ethics 25, finance 25.

## Before you go on stage

1. Start the server with a fresh database: `rm -f kavach.db* && uv run python -m kavach`.
2. Do one warm-up run with `data/samples/demo_bills.csv`. Wait one minute before the real run (Crustdata rate limit).
3. Keep `data/samples/demo_bank_statement.csv` and `data/samples/brief_bank_lines.csv` ready.

## Three-minute demo

Follow "Your demo video" in the [README](../README.md). The kill can come at any time. After a restart, refresh the same URL and show the same payment-file SHA-256.

## Five-minute live fix: drills

| Likely request | Where to change it |
| --- | --- |
| Lower the cost limit | `kavach/config.toml`, `[limits] run_credits` |
| Change the duplicate window (30 days) | `kavach/payrules.py`, `DUPLICATE_WINDOW_DAYS` |
| Add a field to the output | `kavach/app.py`, the `result()` route |
| New ledger rule or vendor | `data/client_records.json` |
| New carrier or bank account version | `data/carriers.json` |

After each change: `uv run pytest -q`, then upload a fresh file. Prior runs keep their saved results.

## Design questions

- **100 times the volume.** Move checks to a queue with workers, keep the stable IDs (bill ID per client, bank reference, payment-file SHA-256), batch the Crustdata lookups per run, cache company records per domain, and move SQLite to Postgres.
- **A second client.** Every table already carries a client ID for the payment record. Give each client its own records, approvals, keys and run allowance, and never share bank details across clients.
- **Why no LLM.** The inputs are structured. Rules decide, and each decision has a source. A model would only read unstructured invoices, and it would never decide or send money.

## Ethics answers

- A person signs every payment. A bank change needs two different people.
- Every hold shows its evidence, what that evidence proves and what it does not prove.
- Screens and exports show only the last 4 digits of an account and only the domain of an email. Only the bank payment file has full numbers, because the bank needs them, and its downloads are counted.
- Person lookups per run: 0.

## Finance answer

| Question | Answer |
| --- | --- |
| Buyer | The finance controller of a mid-size Indian logistics (3PL) company |
| Who does the job today | In-house AP staff, outsourced payables desks, freight payment firms |
| Price (pilot proposal) | Rs 20 per bill checked. A run of 100 bills costs Rs 2,000. |
| Measured cost per run | A live 8-bill demo run used 3.6 Crustdata credits over 11 calls (about $1.08, about Rs 104). Exact per-call costs are in `receipt.json`. |
| Why they pay | Clean carriers are paid on time, a changed bank account cannot be paid without two people, and no bill can enter two payment files. |
| Proof plan | A paid, read-only pilot on one historical run. See [pilot-offer.md](pilot-offer.md). |

Held money is not savings. Do not claim it as savings.
