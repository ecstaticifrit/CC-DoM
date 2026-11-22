import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.templating import Jinja2Templates

from conftest import bills_csv, make_client, upload
from kavach.config import load_config


@pytest.mark.parametrize("mode", ["pay_bills", "post_lines"])
def test_intake_renderer_shows_saved_rows_without_receipt_or_approval(mode):
    directory = Path(__file__).resolve().parents[1] / "kavach" / "templates"
    template = Jinja2Templates(directory=directory).get_template("run.html")
    row = {"row_number": 1, "item_ref": "sample-1", "outcome": "cannot_verify",
           "missing": ["amount"], "display": {"amount": "", "currency": "INR"}}
    page = template.render(run={"run_id": "intake-run", "mode": mode}, rows=[row],
                           config=load_config(), mode_label=mode)

    assert "sample-1" in page and "Cannot verify: missing amount" in page
    assert "/runs/intake-run/result.json" in page
    assert "/receipt.json" not in page and "/confirm" not in page


def test_upgrade_preserves_intake_rows_and_accepts_new_uploads(db_path):
    with sqlite3.connect(db_path) as db:
        db.executescript("""
            CREATE TABLE runs (run_id TEXT PRIMARY KEY, mode TEXT NOT NULL,
                rule_version TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE rows (run_id TEXT NOT NULL, row_number INTEGER NOT NULL,
                item_ref TEXT NOT NULL, outcome TEXT NOT NULL, missing_json TEXT NOT NULL,
                display_json TEXT NOT NULL, raw_json TEXT NOT NULL, PRIMARY KEY (run_id, row_number));
            INSERT INTO runs VALUES ('intake-run', 'pay_bills', '1', '2026-11-22', '2026-11-22');
        """)
        db.execute("INSERT INTO rows VALUES (?, ?, ?, ?, ?, ?, ?)",
                   ("intake-run", 1, "B-1", "not_checked", "[]",
                    json.dumps({"amount": "125.00", "currency": "INR"}), "{}"))

    client = make_client(db_path)
    page = client.get("/runs/intake-run")
    assert page.status_code == 200 and "Not checked yet" in page.text
    row, = client.get("/runs/intake-run/result.json").json()["rows"]
    assert (row["item_ref"], row["display"]["amount"], row["outcome"]) == ("B-1", "125.00", "not_checked")
    assert row["evidence"] == [] and row["decision"] == {} and row["posting"] is None

    new_run = upload(client, "pay_bills", bills_csv("B-2,unknown,Example,10,INR,1234,TEST0000001,"))
    assert new_run.status_code == 303
    assert client.get(new_run.headers["location"]).status_code == 200
