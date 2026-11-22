import re
from pathlib import Path

from conftest import FakeProvider, make_client, upload

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


def test_five_bills_sign_three_and_exactly_three_test_payouts(client, provider):
    run_url = upload(client, "pay_bills", (SAMPLES / "friday_bills.csv").read_text()).headers["location"]
    assert provider.calls == []
    confirm = sign_all_ready(client, run_url)
    assert "Approve 3 bills for Rs 72,950.00" in confirm.text
    client.app.state.worker.tick()
    ids = payout_ids(client, run_url)
    assert set(ids) == {"C-101", "C-102", "C-103"}
    assert len(set(ids.values())) == 3


def test_uploading_twice_and_signing_again_creates_no_second_payment(client, provider):
    text = (SAMPLES / "friday_bills.csv").read_text()
    first = upload(client, "pay_bills", text).headers["location"]
    sign_all_ready(client, first)
    client.app.state.worker.tick()
    second = upload(client, "pay_bills", text, filename="renamed.csv").headers["location"]
    outcomes = {r["item_ref"]: r["outcome"] for r in client.get(f"{second}/result.json").json()["rows"]}
    assert outcomes["C-101"] == "already_signed"
    sign_all_ready(client, second)
    client.app.state.worker.tick()
    assert len(provider.payouts) == 3


def test_kill_after_provider_accepts_recovers_the_same_payouts(db_path):
    provider = FakeProvider()
    provider.fail_next = 3
    client = make_client(db_path, provider)
    run_url = upload(client, "pay_bills", (SAMPLES / "friday_bills.csv").read_text()).headers["location"]
    sign_all_ready(client, run_url)
    client.app.state.worker.tick()
    restarted = make_client(db_path, provider)
    restarted.app.state.worker.tick()
    ids = payout_ids(restarted, run_url)
    assert set(ids) == {"C-101", "C-102", "C-103"}
    assert len(provider.payouts) == 3


def test_brief_bank_lines_post_twice_hold_one_and_leave_sharma_unposted(client, provider):
    run_url = upload(client, "post_lines", (SAMPLES / "brief_bank_lines.csv").read_text()).headers["location"]
    rows = client.get(f"{run_url}/result.json").json()["rows"]
    got = [(r["outcome"], (r["posting"] or {}).get("legal_payee"), (r["posting"] or {}).get("ledger_account")) for r in rows]
    assert got == [
        ("posted", "Swiggy Limited", "staff meals"),
        ("posted", "Amazon Web Services EMEA SARL", "cloud hosting"),
        ("hold_possible_duplicate", None, None),
        ("cannot_verify", None, None),
    ]
    assert provider.calls == []
