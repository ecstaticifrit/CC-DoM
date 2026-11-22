import json
import sqlite3
import uuid
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
"""
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
            row_cols = {r["name"] for r in con.execute("PRAGMA table_info(rows)")}
            if "evidence_json" not in row_cols:
                con.execute("ALTER TABLE rows ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '[]'")
            if "decision_json" not in row_cols:
                con.execute("ALTER TABLE rows ADD COLUMN decision_json TEXT NOT NULL DEFAULT '{}'")
            if "posting_json" not in row_cols:
                con.execute("ALTER TABLE rows ADD COLUMN posting_json TEXT")

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
                   input_hash: str | None = None, allowance_credits: float | None = None) -> str:
        run_id = "run_" + uuid.uuid4().hex[:12]
        stamp = now()
        with self._connect() as con:
            con.execute("INSERT INTO runs (run_id, mode, rule_version, created_at, updated_at, input_hash, allowance_credits) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (run_id, mode, rule_version, stamp, stamp, input_hash, allowance_credits))
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
                "SELECT run_id, row_number, bill_id, reference_id, status, provider_id, provider_status, utr, note, signed_at "
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
                    "payout": payouts.get((run_id, r["row_number"])),
                }
                for r in rows
            ],
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

    def approve(self, run_id: str, items: list[tuple[int, str]], fingerprints: dict[int, str], signer: str) -> list[str]:
        """Sign an exact batch in one transaction. Returns refs that were queued."""
        queued = []
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            for row_number, signed_fp in items:
                row = con.execute("SELECT item_ref, outcome FROM rows WHERE run_id = ? AND row_number = ?",
                                  (run_id, row_number)).fetchone()
                if row is None or row["outcome"] != "ready" or fingerprints.get(row_number) != signed_fp:
                    continue
                cur = con.execute(
                    "INSERT OR IGNORE INTO outbox (client_id, bill_id, run_id, row_number, idem_key, reference_id, "
                    "fingerprint, signed_by, signed_at, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (CLIENT_ID, row["item_ref"], run_id, row_number, str(uuid.uuid4()), uuid.uuid4().hex,
                     signed_fp, signer, now(), now()),
                )
                if cur.rowcount:
                    con.execute("UPDATE rows SET outcome = 'signed' WHERE run_id = ? AND row_number = ?", (run_id, row_number))
                    queued.append(row["item_ref"])
            self.touch(con, run_id)
        return queued

    # Outbox operations used by the payout worker.
    def open_payouts(self) -> list[dict]:
        with self._connect() as con:
            return [dict(p) for p in con.execute(
                "SELECT * FROM outbox WHERE status IN ('pending', 'sending', 'not_configured') "
                "OR (status = 'submitted' AND COALESCE(provider_status, '') NOT IN ('processed', 'reversed', 'failed', 'rejected', 'cancelled')) "
                "ORDER BY id")]

    def update_payout(self, payout_id: int, **fields) -> None:
        fields["updated_at"] = now()
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._connect() as con:
            con.execute(f"UPDATE outbox SET {cols} WHERE id = ?", (*fields.values(), payout_id))
            run_id = con.execute("SELECT run_id FROM outbox WHERE id = ?", (payout_id,)).fetchone()["run_id"]
            self.touch(con, run_id)

    def record_call(self, run_id: str, call: dict) -> None:
        with self._connect() as con:
            con.execute("INSERT INTO ledger_calls (run_id, adapter, endpoint, cost_credits, status, at) VALUES (?, ?, ?, ?, ?, ?)",
                        (run_id, call["adapter"], call["endpoint"], call.get("cost_credits", 0.0), call["status"], now()))
