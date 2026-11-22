from pathlib import Path

from conftest import bills_csv, upload

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"


def test_bank_change_with_mismatched_domain_corroborates_with_crustdata(client):
    run_url = upload(client, "pay_bills", (SAMPLES / "friday_bills.csv").read_text()).headers["location"]
    result = client.get(f"{run_url}/result.json").json()
    c104 = next(r for r in result["rows"] if r["item_ref"] == "C-104")
    assert c104["outcome"] == "hold_bank_change"
    assert any("bluedart.com" in ev["field_or_passage"] for ev in c104["evidence"])

    receipt = client.get(f"{run_url}/receipt.json").json()
    adapters = [c["adapter"] for c in receipt["live_checks"]]
    assert "crustdata.company_identify" in adapters
    assert "cost" not in receipt and "allowance" not in receipt


def test_start_page_does_not_offer_expense_samples(client):
    assert client.get("/samples/brief_bank_lines.csv").status_code == 404
    assert client.get("/samples/public_spending_gbp.csv").status_code == 404


def test_lower_credit_allowance_blocks_new_paid_calls_while_independent_bills_finish(client):
    response = client.post(
        "/runs",
        data={"mode": "pay_bills", "run_credits": "0.1"},
        files={"file": ("bills.csv", (SAMPLES / "friday_bills.csv").read_bytes(), "text/csv")},
    )
    run_url = response.headers["location"]
    result = client.get(f"{run_url}/result.json").json()
    outcomes = {r["item_ref"]: r["outcome"] for r in result["rows"]}
    assert outcomes["C-101"] == "ready"
    assert outcomes["C-104"] == "hold_bank_change"

    receipt = client.get(f"{run_url}/receipt.json").json()
    assert any(c["status"] == "budget_exceeded" for c in receipt["live_checks"])


def test_budget_exhausted_on_lookalike_review_marks_cannot_verify_not_ready(client):
    csv_text = bills_csv(
        "C-201,CAR-1,Blue Dart,700.00,INR,502000112341234,HDFC0000053,ar@bluedrat.com",
    )
    run_url = client.post(
        "/runs",
        data={"mode": "pay_bills", "run_credits": "0.1"},
        files={"file": ("b.csv", csv_text.encode(), "text/csv")},
    ).headers["location"]
    row = client.get(f"{run_url}/result.json").json()["rows"][0]
    assert row["outcome"] == "cannot_verify"
    assert any("allowance" in m.lower() or "budget" in m.lower() for m in row["missing"])
