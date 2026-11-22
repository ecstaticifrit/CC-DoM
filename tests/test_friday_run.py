import csv
import io
import re
from pathlib import Path

from conftest import make_client, upload

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"


def sign_all_ready(client, run_url):
    page = client.get(run_url).text
    rows = re.findall(r'name="row" value="(\d+)"', page)
    confirm = client.post(f"{run_url}/confirm", data={"row": rows})
    items = re.findall(r'name="item" value="([^"]+)"', confirm.text)
    client.post(f"{run_url}/approve", data={"item": items})
    return confirm


def bank_refs(client, run_url):
    rows = client.get(f"{run_url}/result.json").json()["rows"]
    return {r["item_ref"]: r["payout"]["reference_id"] for r in rows if r["payout"]}


def file_rows(client, run_url):
    files = client.get(f"{run_url}/result.json").json()["payment_files"]
    out = []
    for f in files:
        text = client.get(f"{run_url}/files/{f['file_id']}.csv").text
        out += list(csv.DictReader(io.StringIO(text)))
    return files, out


def test_five_bills_sign_three_and_get_exactly_three_payment_lines(client):
    run_url = upload(client, "pay_bills", (SAMPLES / "friday_bills.csv").read_text()).headers["location"]
    assert client.get(f"{run_url}/result.json").json()["payment_files"] == []
    confirm = sign_all_ready(client, run_url)
    assert "Approve 3 bills for Rs 72,950.00" in confirm.text
    files, lines = file_rows(client, run_url)
    assert len(files) == 1 and files[0]["bills"] == 3
    assert sorted(ln["bill_id"] for ln in lines) == ["C-101", "C-102", "C-103"]
    assert len({ln["bank_reference"] for ln in lines}) == 3
    assert set(bank_refs(client, run_url)) == {"C-101", "C-102", "C-103"}


def test_uploading_twice_and_signing_again_creates_no_second_payment_line(client):
    text = (SAMPLES / "friday_bills.csv").read_text()
    first = upload(client, "pay_bills", text).headers["location"]
    sign_all_ready(client, first)
    second = upload(client, "pay_bills", text, filename="renamed.csv").headers["location"]
    outcomes = {r["item_ref"]: r["outcome"] for r in client.get(f"{second}/result.json").json()["rows"]}
    assert outcomes["C-101"] == "already_signed"
    sign_all_ready(client, second)
    assert client.get(f"{second}/result.json").json()["payment_files"] == []
    assert len(file_rows(client, first)[1]) == 3


def test_kill_after_sign_off_returns_the_same_file_and_references(db_path):
    client = make_client(db_path)
    run_url = upload(client, "pay_bills", (SAMPLES / "friday_bills.csv").read_text()).headers["location"]
    sign_all_ready(client, run_url)
    files, lines = file_rows(client, run_url)
    restarted = make_client(db_path)
    files2, lines2 = file_rows(restarted, run_url)
    assert [f["sha256"] for f in files2] == [f["sha256"] for f in files] and lines2 == lines
    assert restarted.get(f"{run_url}/result.json").json()["payment_files"][0]["downloads"] == 2
    assert bank_refs(restarted, run_url) == bank_refs(client, run_url)


def test_bank_statement_cannot_start_a_payment_run(client):
    response = upload(client, "post_lines", (SAMPLES / "brief_bank_lines.csv").read_text())
    assert response.status_code == 400 and "open its signed run" in response.text
