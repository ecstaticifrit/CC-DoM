import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rows (
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  row_number INTEGER NOT NULL,
  item_ref TEXT NOT NULL,
  outcome TEXT NOT NULL,
  missing_json TEXT NOT NULL,
  display_json TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  PRIMARY KEY (run_id, row_number)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """Saved payment runs. Raw input stays server-side; pages read display_json only."""

    def __init__(self, path: Path):
        self.path = Path(path)
        with self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=5)
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA busy_timeout=5000")
        con.row_factory = sqlite3.Row
        return con

    def create_run(self, mode: str, rule_version: str, rows: list[dict]) -> str:
        run_id = "run_" + uuid.uuid4().hex[:12]
        stamp = now()
        with self._connect() as con:
            con.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?)",
                (run_id, mode, rule_version, stamp, stamp),
            )
            con.executemany(
                "INSERT INTO rows VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id,
                        r["row_number"],
                        r["item_ref"],
                        r["outcome"],
                        json.dumps(r["missing"]),
                        json.dumps(r["display"]),
                        json.dumps(r["raw"]),
                    )
                    for r in rows
                ],
            )
        return run_id

    def get_run(self, run_id: str) -> dict | None:
        with self._connect() as con:
            run = con.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if run is None:
                return None
            rows = con.execute(
                "SELECT row_number, item_ref, outcome, missing_json, display_json "
                "FROM rows WHERE run_id = ? ORDER BY row_number",
                (run_id,),
            ).fetchall()
        return {
            **dict(run),
            "rows": [
                {
                    "row_number": r["row_number"],
                    "item_ref": r["item_ref"],
                    "outcome": r["outcome"],
                    "missing": json.loads(r["missing_json"]),
                    "display": json.loads(r["display_json"]),
                }
                for r in rows
            ],
        }
