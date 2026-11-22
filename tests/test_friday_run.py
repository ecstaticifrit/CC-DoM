import re
import sqlite3
from pathlib import Path

import pytest

from conftest import bills_csv, make_client, upload

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"


def sign_all_ready(client, run_url):
    page = client.get(run_url).text
    rows = re.findall(r'name="row" value="(\d+)"', page)
    confirm = client.post(f"{run_url}/confirm", data={"row": rows})
    items = re.findall(r'name="item" value="([^"]+)"', confirm.text)
    client.post(f"{run_url}/approve", data={"item": items})
    return confirm


def payout_ids(client, run_url):
    rows = client.get(f"{run_url}/result.json").json()["rows"]
    return {r["item_ref"]: r["payout"]["provider_id"] for r in rows if r["payout"] and r["payout"]["provider_id"]}


def test_five_bills_sign_three_and_move_exactly_the_approved_amounts(client):
    run_url = upload(client, "pay_bills", (SAMPLES / "friday_bills.csv").read_text()).headers["location"]
    assert client.get(f"{run_url}/receipt.json").json()["simulated_transfers"] == []
    confirm = sign_all_ready(client, run_url)
    assert "Approve 3 bills for Rs 72,950.00" in confirm.text
    ids = payout_ids(client, run_url)
    assert set(ids) == {"C-101", "C-102", "C-103"}
    assert len(set(ids.values())) == 3
    assert all(i.startswith("sim_") for i in ids.values())
    receipt = client.get(f"{run_url}/receipt.json").json()
    assert receipt["payout_mode"] == "simulation" and receipt["processed_total"] == "72,950.00"
    assert receipt["simulated_transfers"][-1]["treasury_after_inr"] == "27,050.00"
    assert {t["beneficiary_wallet"]: t["beneficiary_after_inr"] for t in receipt["simulated_transfers"]} == {
        "CAR-1:v2": "48,000.00", "CAR-3:v1": "9,200.00", "CAR-4:v1": "15,750.00"}


def test_uploading_twice_and_signing_again_creates_no_second_payment(client):
    text = (SAMPLES / "friday_bills.csv").read_text()
    first = upload(client, "pay_bills", text).headers["location"]
    sign_all_ready(client, first)
    second = upload(client, "pay_bills", text, filename="renamed.csv").headers["location"]
    outcomes = {r["item_ref"]: r["outcome"] for r in client.get(f"{second}/result.json").json()["rows"]}
    assert outcomes["C-101"] == "already_signed"
    sign_all_ready(client, second)
    assert not client.get(f"{second}/receipt.json").json()["simulated_transfers"]
    assert "27,050.00" in client.get("/").text


def test_restart_keeps_the_same_transfer_ids_and_balances(db_path):
    client = make_client(db_path)
    run_url = upload(client, "pay_bills", (SAMPLES / "friday_bills.csv").read_text()).headers["location"]
    sign_all_ready(client, run_url)
    receipt = client.get(f"{run_url}/receipt.json").json()
    restarted = make_client(db_path)
    assert restarted.get(f"{run_url}/receipt.json").json() == receipt
    assert "27,050.00" in restarted.get("/").text


def test_bank_statement_cannot_start_a_payment_run(client):
    response = upload(client, "post_lines", (SAMPLES / "brief_bank_lines.csv").read_text())
    assert response.status_code == 400
    assert "100,000.00" in client.get("/").text


def test_insufficient_balance_leaves_wallets_unchanged(client):
    run = upload(client, "pay_bills", bills_csv(
        "BIG,CAR-1,Blue Dart,100000.01,INR,502000112341234,HDFC0000053,")).headers["location"]
    sign_all_ready(client, run)
    row, = client.get(f"{run}/result.json").json()["rows"]
    assert row["payout"]["status"] == "failed" and "Insufficient" in row["payout"]["note"]
    assert client.get(f"{run}/receipt.json").json()["simulated_transfers"] == []
    assert "100,000.00" in client.get("/").text


def test_retry_after_interrupted_signoff_moves_funds_once(client, db_path):
    run = upload(client, "pay_bills", bills_csv(
        "RETRY,CAR-1,Blue Dart,123.45,INR,502000112341234,HDFC0000053,")).headers["location"]
    confirm = client.post(f"{run}/confirm", data={"row": "1"})
    item = re.search(r'name="item" value="([^"]+)"', confirm.text)[1]
    with sqlite3.connect(db_path) as db:
        db.execute("""CREATE TRIGGER interrupt BEFORE UPDATE OF outcome ON rows
                      WHEN NEW.outcome='signed' BEGIN SELECT RAISE(ABORT, 'interrupted'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="interrupted"):
        client.post(f"{run}/approve", data={"item": item})
    restarted = make_client(db_path)
    assert not restarted.get(f"{run}/receipt.json").json()["signed"]
    assert "100,000.00" in restarted.get("/").text
    with sqlite3.connect(db_path) as db:
        db.execute("DROP TRIGGER interrupt")
    for _ in range(2):
        assert restarted.post(f"{run}/approve", data={"item": item}).status_code == 303
    moved, = restarted.get(f"{run}/receipt.json").json()["simulated_transfers"]
    assert (moved["treasury_after_inr"], moved["beneficiary_after_inr"]) == ("99,876.55", "123.45")
