# CC-DoM: Kavach

Kavach closes a logistics company's weekly carrier payment run. It gets clean bills signed and paid once in a sandbox, holds the rest with an owner and a next step, and records charges that already left the bank.

- Spec: `.scratch/friday-payment-run/spec.md`
- Tickets: `.scratch/friday-payment-run/issues/`
- Shared words: `GLOSSARY.md`. Decisions: `docs/adr/`. Team workflow: `docs/collaboration.md`.

## Run it

```bash
uv sync
uv run python -m kavach            # http://127.0.0.1:8000, data in ./kavach.db
uv run pytest -q                    # tests
```

Environment: `KAVACH_DB` (database file), `PORT`, `HOST`. Secrets go in `.env` (see `.env.example`); never commit them.

## Provisional input (until the kickoff format is known)

**Pay approved bills** CSV columns: `bill_id, carrier_id, carrier_name, amount, currency, account_number, ifsc, sender_email` (`sender_email` optional).

**Post bank lines** CSV columns: `date, description, amount, currency, reference` (`reference` optional).

A row with a missing required value stays visible as `Cannot verify` with the missing field named. Nothing is paid or posted at this stage.

## Organizer output (provisional)

`GET /runs/{run_id}/result.json`: run ID, mode, rule version and each row's outcome, missing facts and masked display fields. It reads the same saved run as the page.

The job, payer, sources, pass mark and architecture diagram are completed in ticket 16.
