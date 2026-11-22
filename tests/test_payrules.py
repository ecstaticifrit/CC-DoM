from datetime import date
from pathlib import Path

from kavach.intake import parse
from kavach.payrules import evaluate_bills
from kavach.records import load_records

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "samples" / "friday_bills.csv"


class FakeSources:
    def ifsc(self, code):
        call = {"adapter": "ifsc", "endpoint": f"https://ifsc.razorpay.com/{code}", "cost_credits": 0.0, "status": "ok"}
        if code == "XXXX0000000":
            return {"status": "invalid", "call": call, "retrieved_at": "t"}
        return {"status": "ok", "bank": "Bank", "branch": "Branch", "call": call, "retrieved_at": "t"}

    def company_domain(self, domain):
        return {"call": {"adapter": "crustdata.company_identify", "endpoint": "x", "cost_credits": 0.2, "status": "ok"},
                "primary_domain": domain, "retrieved_at": "t", "source_ref": "Crustdata"}


def evaluate(csv_bytes):
    return evaluate_bills(parse("pay_bills", csv_bytes), load_records(), FakeSources(), date(2026, 11, 27))


def test_friday_rehearsal_three_ready_one_bank_change_one_possible_duplicate():
    rows = {r["item_ref"]: r for r in evaluate(SAMPLE.read_bytes())}
    assert {k: r["outcome"] for k, r in rows.items()} == {
        "C-101": "ready", "C-102": "ready", "C-103": "ready",
        "C-104": "hold_bank_change", "C-105": "hold_possible_duplicate",
    }
    change = rows["C-104"]["decision"]
    assert "1234" in change["reason"] and "9876" in change["reason"]
    assert "TC-0101" in change["next_step"]


def test_exact_sender_domain_match_adds_no_hold_and_lookalike_goes_to_review():
    header = b"bill_id,carrier_id,carrier_name,amount,currency,account_number,ifsc,sender_email\n"
    rows = evaluate(header + b"C-201,CAR-1,Blue Dart,700,INR,502000112341234,HDFC0000053,ar@bluedrat.com\n")
    assert rows[0]["outcome"] == "review_sender_domain"
    assert "not an accusation" in rows[0]["decision"]["reason"]


def test_invalid_ifsc_on_an_otherwise_matching_bill_is_held():
    records = load_records()
    records["carriers"]["CAR-1"]["beneficiaries"][0]["ifsc"] = "XXXX0000000"
    header = b"bill_id,carrier_id,carrier_name,amount,currency,account_number,ifsc,sender_email\n"
    rows = evaluate_bills(parse("pay_bills", header + b"C-301,CAR-1,Blue Dart,700,INR,502000112341234,XXXX0000000,\n"),
                          records, FakeSources(), date(2026, 11, 27))
    assert rows[0]["outcome"] == "hold_invalid_routing"
