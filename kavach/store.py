import json
import sqlite3
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, mode TEXT NOT NULL, rule_version TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  input_hash TEXT, allowance_credits REAL
);
CREATE TABLE IF NOT EXISTS rows (
  run_id TEXT NOT NULL REFERENCES runs(run_id), row_number INTEGER NOT NULL,
  item_ref TEXT NOT NULL, outcome TEXT NOT NULL, missing_json TEXT NOT NULL,
  display_json TEXT NOT NULL, raw_json TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '[]', decision_json TEXT NOT NULL DEFAULT '{}',
  posting_json TEXT, PRIMARY KEY (run_id, row_number)
);
CREATE TABLE IF NOT EXISTS ledger_calls (
  id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, adapter TEXT NOT NULL, endpoint TEXT NOT NULL,
  cost_credits REAL NOT NULL, status TEXT NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY, client_id TEXT NOT NULL, bill_id TEXT NOT NULL,
  run_id TEXT NOT NULL, row_number INTEGER NOT NULL, idem_key TEXT NOT NULL UNIQUE,
  reference_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL, signed_by TEXT NOT NULL,
  signed_at TEXT NOT NULL, body_json TEXT, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  provider_id TEXT, provider_status TEXT, utr TEXT, note TEXT, updated_at TEXT NOT NULL,
  UNIQUE (client_id, bill_id)
);
CREATE TABLE IF NOT EXISTS beneficiary_changes (
  id INTEGER PRIMARY KEY, client_id TEXT NOT NULL, carrier_id TEXT NOT NULL, run_id TEXT NOT NULL,
  row_number INTEGER NOT NULL, account_number TEXT NOT NULL, ifsc TEXT NOT NULL, status TEXT NOT NULL,
  contact_record_id TEXT, callback_by TEXT, callback_at TEXT, authorized_by TEXT, authorized_at TEXT,
  UNIQUE (run_id, row_number)
);
CREATE TABLE IF NOT EXISTS payment_files (
  file_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, created_at TEXT NOT NULL, sha256 TEXT NOT NULL,
  content BLOB NOT NULL, bills INTEGER NOT NULL, total TEXT NOT NULL, signed_by TEXT NOT NULL,
  downloads INTEGER NOT NULL DEFAULT 0, last_download_at TEXT
);
CREATE TABLE IF NOT EXISTS reconciliations (
  id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, source TEXT NOT NULL, input_hash TEXT,
  result_json TEXT NOT NULL, at TEXT NOT NULL
);
"""
OUTBOX_EXTRA = {"file_id": "TEXT", "reconciled_json": "TEXT", "returned_json": "TEXT"}
CLIENT_ID = "default"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """Saved payment runs. Raw input stays server-side; pages read display fields only."""

    def __init__(self, path: Path):
        self.path = Path(path)
        with self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA)
            cols = {r["name"] for r in con.execute("PRAGMA table_info(runs)")}
            if "input_hash" not in cols:
                con.execute("ALTER TABLE runs ADD COLUMN input_hash TEXT")
            if "allowance_credits" not in cols:
                con.execute("ALTER TABLE runs ADD COLUMN allowance_credits REAL")
            if "eval_ms" not in cols:
                con.execute("ALTER TABLE runs ADD COLUMN eval_ms INTEGER")
            row_cols = {r["name"] for r in con.execute("PRAGMA table_info(rows)")}
            if "evidence_json" not in row_cols:
                con.execute("ALTER TABLE rows ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '[]'")
            if "decision_json" not in row_cols:
                con.execute("ALTER TABLE rows ADD COLUMN decision_json TEXT NOT NULL DEFAULT '{}'")
            if "posting_json" not in row_cols:
                con.execute("ALTER TABLE rows ADD COLUMN posting_json TEXT")
            out_cols = {r["name"] for r in con.execute("PRAGMA table_info(outbox)")}
            for col, kind in OUTBOX_EXTRA.items():
                if col not in out_cols:
                    con.execute(f"ALTER TABLE outbox ADD COLUMN {col} {kind}")

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=5)
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA busy_timeout=5000")
        con.row_factory = sqlite3.Row
        return con

    def find_run_by_hash(self, mode: str, input_hash: str) -> str | None:
        with self._connect() as con:
            r = con.execute("SELECT run_id FROM runs WHERE mode = ? AND input_hash = ? ORDER BY created_at LIMIT 1",
                            (mode, input_hash)).fetchone()
        return r["run_id"] if r else None

    def create_run(self, mode: str, rule_version: str, rows: list[dict],
                   input_hash: str | None = None, allowance_credits: float | None = None, eval_ms: int | None = None) -> str:
        run_id = "run_" + uuid.uuid4().hex[:12]
        stamp = now()
        with self._connect() as con:
            con.execute("INSERT INTO runs (run_id, mode, rule_version, created_at, updated_at, input_hash, allowance_credits, eval_ms) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (run_id, mode, rule_version, stamp, stamp, input_hash, allowance_credits, eval_ms))
            for r in rows:
                con.execute(
                    "INSERT INTO rows (run_id, row_number, item_ref, outcome, missing_json, display_json, "
                    "raw_json, evidence_json, decision_json, posting_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_id, r["row_number"], r["item_ref"], r["outcome"], json.dumps(r["missing"]),
                     json.dumps(r["display"]), json.dumps(r["raw"]), json.dumps(r.get("evidence", [])),
                     json.dumps(r.get("decision", {})), json.dumps(r["posting"]) if r.get("posting") else None),
                )
                for c in r.get("calls", []):
                    con.execute(
                        "INSERT INTO ledger_calls (run_id, adapter, endpoint, cost_credits, status, at) VALUES (?, ?, ?, ?, ?, ?)",
                        (run_id, c["adapter"], c["endpoint"], c.get("cost_credits", 0.0), c["status"], stamp),
                    )
        return run_id

    def touch(self, con: sqlite3.Connection, run_id: str) -> None:
        con.execute("UPDATE runs SET updated_at = ? WHERE run_id = ?", (now(), run_id))

    def get_run(self, run_id: str) -> dict | None:
        with self._connect() as con:
            run = con.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if run is None:
                return None
            rows = con.execute("SELECT * FROM rows WHERE run_id = ? ORDER BY row_number", (run_id,)).fetchall()
            payouts = {(p["run_id"], p["row_number"]): dict(p) for p in con.execute(
                "SELECT run_id, row_number, bill_id, reference_id, status, file_id, note, signed_at, "
                "reconciled_json, returned_json "
                "FROM outbox WHERE run_id = ?", (run_id,))}
            calls = [dict(c) for c in con.execute(
                "SELECT adapter, endpoint, cost_credits, status, at FROM ledger_calls WHERE run_id = ? ORDER BY id", (run_id,))]
        return {
            **dict(run),
            "calls": calls,
            "rows": [
                {
                    "row_number": r["row_number"], "item_ref": r["item_ref"], "outcome": r["outcome"],
                    "missing": json.loads(r["missing_json"]), "display": json.loads(r["display_json"]),
                    "evidence": json.loads(r["evidence_json"]), "decision": json.loads(r["decision_json"]),
                    "posting": json.loads(r["posting_json"]) if r["posting_json"] else None,
                    "payout": _payout_view(payouts.get((run_id, r["row_number"]))),
                }
                for r in rows
            ],
            "changes": self.changes_for_run(run_id),
            "files": self.files_for_run(run_id),
            "reconciliation": self.latest_reconciliation(run_id),
        }

    def raw_row(self, run_id: str, row_number: int) -> dict:
        with self._connect() as con:
            r = con.execute("SELECT raw_json, display_json FROM rows WHERE run_id = ? AND row_number = ?",
                            (run_id, row_number)).fetchone()
        return {"raw": json.loads(r["raw_json"]), "display": json.loads(r["display_json"])}

    def payout_for_bill(self, bill_id: str) -> dict | None:
        with self._connect() as con:
            p = con.execute("SELECT * FROM outbox WHERE client_id = ? AND bill_id = ?", (CLIENT_ID, bill_id)).fetchone()
        return dict(p) if p else None

    def approve(self, run_id: str, items: list[tuple[int, str]], fingerprints: dict[int, str], signer: str) -> tuple[list[str], str | None]:
        """Sign an exact batch and write its bank payment file in one transaction. Returns (bill IDs, file ID)."""
        from kavach import payfile
        queued, lines = [], []
        file_id = "PF-" + uuid.uuid4().hex[:10].upper()
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            for row_number, signed_fp in items:
                row = con.execute("SELECT item_ref, outcome, raw_json, display_json FROM rows WHERE run_id = ? AND row_number = ?",
                                  (run_id, row_number)).fetchone()
                if row is None or row["outcome"] != "ready" or fingerprints.get(row_number) != signed_fp:
                    continue
                ref = payfile.bank_ref(row["item_ref"])
                cur = con.execute(
                    "INSERT OR IGNORE INTO outbox (client_id, bill_id, run_id, row_number, idem_key, reference_id, "
                    "fingerprint, signed_by, signed_at, status, file_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'in_file', ?, ?)",
                    (CLIENT_ID, row["item_ref"], run_id, row_number, str(uuid.uuid4()), ref, signed_fp, signer, now(), file_id, now()))
                if cur.rowcount:
                    con.execute("UPDATE rows SET outcome = 'signed' WHERE run_id = ? AND row_number = ?", (run_id, row_number))
                    raw, display = json.loads(row["raw_json"]), json.loads(row["display_json"])
                    queued.append(row["item_ref"])
                    lines.append({"bill_id": row["item_ref"], "name": display.get("carrier") or raw["carrier_name"],
                                  "account_number": raw["account_number"], "ifsc": raw["ifsc"],
                                  "amount": raw["amount"], "currency": raw["currency"]})
            if lines:
                content = payfile.build(lines)
                total = f"{sum(Decimal(ln['amount']) for ln in lines):,.2f}"
                con.execute("INSERT INTO payment_files (file_id, run_id, created_at, sha256, content, bills, total, signed_by) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (file_id, run_id, now(), payfile.sha256(content), content, len(lines), total, signer))
            self.touch(con, run_id)
        return queued, (file_id if lines else None)

    def files_for_run(self, run_id: str) -> list[dict]:
        with self._connect() as con:
            return [dict(r) for r in con.execute(
                "SELECT file_id, created_at, sha256, bills, total, signed_by, downloads, last_download_at "
                "FROM payment_files WHERE run_id = ? ORDER BY created_at", (run_id,))]

    def file_content(self, run_id: str, file_id: str) -> bytes | None:
        """Return the frozen file bytes and count the download."""
        with self._connect() as con:
            r = con.execute("SELECT content FROM payment_files WHERE run_id = ? AND file_id = ?", (run_id, file_id)).fetchone()
            if r is None:
                return None
            con.execute("UPDATE payment_files SET downloads = downloads + 1, last_download_at = ? WHERE file_id = ?",
                        (now(), file_id))
            return bytes(r["content"])

    def file_lines(self, file_id: str) -> list[dict]:
        """Server-side only: the bills in a file with their full destinations."""
        with self._connect() as con:
            return [{"bill_id": o["bill_id"], "raw": json.loads(o["raw_json"])} for o in con.execute(
                "SELECT o.bill_id, r.raw_json FROM outbox o JOIN rows r ON r.run_id = o.run_id AND r.row_number = o.row_number "
                "WHERE o.file_id = ?", (file_id,))]

    def set_row(self, run_id: str, row_number: int, outcome: str | None = None, decision: dict | None = None,
                display: dict | None = None, evidence: list | None = None, missing: list | None = None) -> None:
        fields = {"outcome": outcome, "decision_json": decision, "display_json": display,
                  "evidence_json": evidence, "missing_json": missing}
        fields = {k: (v if k == "outcome" else json.dumps(v)) for k, v in fields.items() if v is not None}
        if not fields:
            return
        with self._connect() as con:
            con.execute(f"UPDATE rows SET {', '.join(f'{k} = ?' for k in fields)} WHERE run_id = ? AND row_number = ?",
                        (*fields.values(), run_id, row_number))
            self.touch(con, run_id)

    def raw_rows(self, run_id: str) -> list[dict]:
        with self._connect() as con:
            return [{"row_number": r["row_number"], "item_ref": r["item_ref"], "outcome": r["outcome"],
                     "missing": json.loads(r["missing_json"]), "display": json.loads(r["display_json"]),
                     "raw": json.loads(r["raw_json"])}
                    for r in con.execute("SELECT * FROM rows WHERE run_id = ? ORDER BY row_number", (run_id,))]

    def add_calls(self, run_id: str, calls: list[dict]) -> None:
        for c in calls:
            self.record_call(run_id, c)

    # Beneficiary changes: callback by the AP lead, then a separate authorizer.
    def record_callback(self, run_id: str, row_number: int, carrier_id: str, account_number: str, ifsc: str,
                        contact_record_id: str, callback_by: str, confirmed: bool) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO beneficiary_changes (client_id, carrier_id, run_id, row_number, account_number, ifsc, status, "
                "contact_record_id, callback_by, callback_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (run_id, row_number) DO UPDATE SET status = excluded.status, callback_by = excluded.callback_by, "
                "callback_at = excluded.callback_at, contact_record_id = excluded.contact_record_id "
                "WHERE beneficiary_changes.status != 'authorized'",
                (CLIENT_ID, carrier_id, run_id, row_number, account_number, ifsc,
                 "callback_confirmed" if confirmed else "callback_denied", contact_record_id, callback_by, now()))
            self.touch(con, run_id)

    def authorize_change(self, run_id: str, row_number: int, authorized_by: str) -> bool:
        with self._connect() as con:
            cur = con.execute("UPDATE beneficiary_changes SET status = 'authorized', authorized_by = ?, authorized_at = ? "
                              "WHERE run_id = ? AND row_number = ? AND status = 'callback_confirmed'",
                              (authorized_by, now(), run_id, row_number))
            self.touch(con, run_id)
            return cur.rowcount == 1

    def changes_for_run(self, run_id: str) -> dict[int, dict]:
        with self._connect() as con:
            return {r["row_number"]: {k: r[k] for k in ("carrier_id", "status", "contact_record_id", "callback_by",
                                                         "callback_at", "authorized_by", "authorized_at")}
                    for r in con.execute("SELECT * FROM beneficiary_changes WHERE run_id = ?", (run_id,))}

    def authorized_changes(self) -> list[dict]:
        """Server-side only: includes full account numbers for building client records."""
        with self._connect() as con:
            return [dict(r) for r in con.execute(
                "SELECT carrier_id, account_number, ifsc, authorized_at, authorized_by FROM beneficiary_changes "
                "WHERE client_id = ? AND status = 'authorized' ORDER BY authorized_at, id", (CLIENT_ID,))]

    # Reconciliation against a bank statement.
    def payouts_for_run(self, run_id: str) -> list[dict]:
        with self._connect() as con:
            return [dict(p) for p in con.execute("SELECT * FROM outbox WHERE run_id = ? ORDER BY id", (run_id,))]

    def save_reconciliation(self, run_id: str, source: str, input_hash: str | None, result: dict,
                            matches: dict[int, dict], returns: dict[int, dict]) -> None:
        """Record what the statement proves, once: a paid bill stays paid; a return reopens the bill."""
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("INSERT INTO reconciliations (run_id, source, input_hash, result_json, at) VALUES (?, ?, ?, ?, ?)",
                        (run_id, source, input_hash, json.dumps(result), now()))
            for outbox_id, match in matches.items():
                con.execute("UPDATE outbox SET reconciled_json = ?, status = 'paid', updated_at = ? "
                            "WHERE id = ? AND reconciled_json IS NULL", (json.dumps(match), now(), outbox_id))
            for outbox_id, ret in returns.items():
                cur = con.execute("UPDATE outbox SET returned_json = ?, status = 'returned', updated_at = ? "
                                  "WHERE id = ? AND returned_json IS NULL", (json.dumps(ret), now(), outbox_id))
                if cur.rowcount:
                    o = con.execute("SELECT run_id, row_number, bill_id FROM outbox WHERE id = ?", (outbox_id,)).fetchone()
                    con.execute("UPDATE rows SET outcome = 'reopened_reversed', decision_json = ? WHERE run_id = ? AND row_number = ?",
                                (json.dumps({"reason": f"The bank returned the payment for {o['bill_id']} (statement line {ret['line']}). "
                                                       "The carrier has not been paid.",
                                             "owner": "AP lead",
                                             "next_step": "Confirm the beneficiary through the trusted contact. "
                                                          "The controller approves any new payment separately."}),
                                 o["run_id"], o["row_number"]))
            self.touch(con, run_id)

    def latest_reconciliation(self, run_id: str) -> dict | None:
        with self._connect() as con:
            r = con.execute("SELECT source, result_json, at FROM reconciliations WHERE run_id = ? ORDER BY id DESC LIMIT 1",
                            (run_id,)).fetchone()
        return {"source": r["source"], "at": r["at"], **json.loads(r["result_json"])} if r else None

    def signed_history(self) -> list[dict]:
        """Bills Kavach has signed, in payment-history shape, for duplicate checks."""
        with self._connect() as con:
            out = []
            for o in con.execute("SELECT o.bill_id, o.signed_at, r.raw_json FROM outbox o JOIN rows r "
                                 "ON r.run_id = o.run_id AND r.row_number = o.row_number WHERE o.client_id = ?", (CLIENT_ID,)):
                raw = json.loads(o["raw_json"])
                out.append({"bill_id": o["bill_id"], "carrier_id": raw.get("carrier_id"), "amount": raw.get("amount"),
                            "currency": raw.get("currency"), "paid_on": o["signed_at"][:10], "kind": "signed"})
            return out

    def record_call(self, run_id: str, call: dict) -> None:
        with self._connect() as con:
            con.execute("INSERT INTO ledger_calls (run_id, adapter, endpoint, cost_credits, status, at) VALUES (?, ?, ?, ?, ?, ?)",
                        (run_id, call["adapter"], call["endpoint"], call.get("cost_credits", 0.0), call["status"], now()))


def _payout_view(p: dict | None) -> dict | None:
    if p is None:
        return None
    rec, ret = p.pop("reconciled_json", None), p.pop("returned_json", None)
    return {**p, "reconciled": json.loads(rec) if rec else None, "returned": json.loads(ret) if ret else None}
