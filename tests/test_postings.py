import copy
import json
from pathlib import Path

from kavach.intake import parse
from kavach.postings import evaluate_lines

ROOT = Path(__file__).resolve().parent.parent
RECORDS = json.loads((ROOT / "data" / "client_records.json").read_text())
BRIEF = (ROOT / "data" / "samples" / "brief_bank_lines.csv").read_bytes()
AWS_URL = "https://aws.amazon.com/legal/aws-contracting-party/"
PAGE = ("Contracting party table …  Amazon Web Services EMEA SARL | 352 2789 0057 | "
        "38 Avenue John F. Kennedy, L-1855, Luxembourg … more text")


def fake_fetch(url):
    assert url == AWS_URL
    return PAGE, "2026-10-10T09:00:00Z"


def failing_fetch(url):
    raise ConnectionError("network down")


def check(row, name):
    return next(ev for ev in row["evidence"] if ev["check"] == name)


def test_brief_lines():
    out = evaluate_lines(parse("post_lines", BRIEF), RECORDS, fake_fetch)
    assert [r["outcome"] for r in out] == ["posted", "posted", "hold_possible_duplicate", "cannot_verify"]
    assert out[0]["posting"]["legal_payee"] == "Swiggy Limited"
    assert out[0]["posting"]["ledger_account"] == "staff meals"
    assert out[0]["posting"]["posting_id"].startswith("post_")
    assert check(out[0], "Legal payee")["source_type"] == "registry"
    assert out[1]["posting"]["legal_payee"] == "Amazon Web Services EMEA SARL"
    assert out[1]["posting"]["ledger_account"] == "cloud hosting"
    assert out[1]["posting"]["posting_id"].startswith("post_")
    ev = check(out[1], "Legal payee")
    assert ev["source_type"] == "web_page" and ev["retrieved_at"] == "2026-10-10T09:00:00Z"
    assert "Amazon Web Services EMEA SARL" in ev["field_or_passage"] and len(ev["field_or_passage"]) <= 130
    assert out[1]["calls"] == [{"adapter": "web", "endpoint": AWS_URL, "cost_credits": 0, "status": "ok"}]
    assert "posting" not in out[2]
    assert out[2]["display"]["reason"].startswith("Same payee, amount and date as line 2.")
    assert out[3]["missing"] == ["legal payee: no client record links this descriptor to a vendor"]
    assert "posting" not in out[3]
    assert out[3]["display"]["description"] == "PAYTM*SHARMA TRD"


def test_fetch_failure_holds_aws_but_swiggy_posts():
    out = evaluate_lines(parse("post_lines", BRIEF), RECORDS, failing_fetch)
    assert [r["outcome"] for r in out] == ["posted", "cannot_verify", "cannot_verify", "cannot_verify"]
    for r in out[1:3]:
        assert "posting" not in r
        assert r["missing"] == ["legal payee: vendor legal page unavailable or does not state "
                                "Amazon Web Services EMEA SARL"]
    assert out[1]["calls"][0]["status"] == "error"


def test_page_without_name_is_cannot_verify():
    out = evaluate_lines(parse("post_lines", BRIEF), RECORDS, lambda u: ("nothing here", "t"))
    assert out[1]["outcome"] == "cannot_verify" and out[1]["calls"][0]["status"] == "error"


def test_missing_ledger_rule_names_the_rule():
    records = copy.deepcopy(RECORDS)
    del records["ledger_rules"]["V-SWIGGY"]
    out = evaluate_lines(parse("post_lines", BRIEF), records, fake_fetch)
    assert out[0]["outcome"] == "cannot_verify"
    assert out[0]["missing"] == ["ledger rule for Swiggy Limited"]
    assert "posting" not in out[0]


def test_rows_missing_values_stay_cannot_verify():
    rows = parse("post_lines", b"date,description,amount,currency\n,AWS EMEA,10,INR\n")
    out = evaluate_lines(rows, RECORDS, fake_fetch)
    assert out[0]["outcome"] == "cannot_verify" and out[0]["missing"] == ["date"]
    assert out[0]["evidence"] == [] and out[0]["calls"] == []
