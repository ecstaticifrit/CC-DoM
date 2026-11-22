"""Structured, sourced checks on bills and bank lines (the UI renders these)."""
import json
from datetime import date
from pathlib import Path

from kavach.intake import parse
from kavach.payrules import evaluate_bills
from kavach.postings import evaluate_lines
from kavach.records import load_records
from kavach.sources import BudgetedSources
from test_payrules import LIST_COSTS, FakeSources

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"
TODAY = date(2026, 11, 27)
KEYS = {"source_type", "source_ref", "field_or_passage", "record_date", "retrieved_at",
        "check", "result", "source", "summary", "proves", "limits", "url", "data", "cost_credits"}
RESULTS = {"pass", "fail", "warn", "info", "unknown"}
SOURCES = {"Client record", "Crustdata", "IFSC registry", "Web page", "Payment history"}
HEADER = b"bill_id,carrier_id,carrier_name,amount,currency,account_number,ifsc,sender_email\n"


def bills(fake=None, credits=150.0, csv=None):
    fake = fake or FakeSources(costs=LIST_COSTS)
    sources = BudgetedSources(fake, max_credits=credits, max_seconds=600)
    rows = evaluate_bills(parse("pay_bills", csv or (SAMPLES / "friday_bills.csv").read_bytes()),
                          load_records(), sources, TODAY)
    return {r["item_ref"]: r for r in rows}, fake


def lines(fake=None, credits=150.0):
    fake = fake or FakeSources(costs=LIST_COSTS)
    sources = BudgetedSources(fake, max_credits=credits, max_seconds=600)
    rows = evaluate_lines(parse("post_lines", (SAMPLES / "brief_bank_lines.csv").read_bytes()), load_records(),
                          sources.fetch_page_text, sources=sources)
    return rows, fake


def check(row, name):
    found = [ev for ev in row["evidence"] if ev["check"] == name]
    assert found, f"{row['item_ref']} has no {name} check: {[ev['check'] for ev in row['evidence']]}"
    return found[0]


def assert_contract(rows):
    for row in rows:
        assert row["evidence"], row["item_ref"]
        for ev in row["evidence"]:
            assert set(ev) == KEYS, ev
            assert ev["result"] in RESULTS and ev["source"] in SOURCES
            assert ev["summary"] and ev["limits"] and ev["proves"]
            assert all(isinstance(v, (str, int, float)) for v in ev["data"].values())


def test_every_friday_bill_has_structured_checks():
    rows, _ = bills()
    assert_contract(rows.values())
    assert {k: r["outcome"] for k, r in rows.items()} == {
        "C-101": "ready", "C-102": "ready", "C-103": "ready",
        "C-104": "hold_bank_change", "C-105": "hold_possible_duplicate"}


def test_bank_change_has_sender_warning_profile_and_news_with_cost():
    rows, _ = bills()
    c104 = rows["C-104"]
    sender = check(c104, "Sender email domain")
    assert sender["result"] == "warn" and sender["summary"] == "No company in the Crustdata directory owns this domain."
    assert sender["data"]["Sender domain"] == "bluedart-payments.com" and sender["cost_credits"] > 0
    profile = check(c104, "Carrier company profile")
    assert profile["result"] == "info" and profile["cost_credits"] == 2.0 and profile["data"]["Company"] == "Blue Dart"
    news = check(c104, "Carrier news")
    assert news["result"] == "info" and news["cost_credits"] == 1.0
    assert "does not confirm or reject the bank change" in news["limits"]
    assert {"Headline 1", "Link 1", "Headline 3"} <= set(news["data"]) and "Headline 4" not in news["data"]
    assert check(c104, "Approved bank account")["result"] == "fail"
    assert check(c104, "Approved bank account")["data"] == {
        "Approved": "•••• 1234 (v2)", "This bill": "•••• 9876", "Approved IFSC": "HDFC0000053", "Bill IFSC": "HDFC0000053"}
    adapters = [c["adapter"] for c in c104["calls"]]
    assert "crustdata.company_enrich" in adapters and "crustdata.web_search_live" in adapters


def test_clean_bills_show_passes_and_make_no_enrich_or_news_calls():
    rows, fake = bills()
    for ref in ("C-101", "C-103"):
        row = rows[ref]
        for name in ("Approved bank account", "Payment history", "Bank branch (IFSC)", "Sender email domain",
                     "Carrier company record"):
            assert check(row, name)["result"] == "pass", (ref, name)
        assert not any(c["adapter"] in ("crustdata.company_enrich", "crustdata.web_search_live") for c in row["calls"])
    assert check(rows["C-101"], "Carrier company record")["data"]["Domain"] == "bluedart.com"
    # One company_identify call per domain per run, even when several bills share a carrier.
    identified = [e for m, e in fake.seen if m == "company_identify"]
    assert len(identified) == 4
    assert [m for m, _ in fake.seen].count("company_enrich") == 1


def test_small_carrier_without_domain_is_info_not_a_hold():
    rows, _ = bills()
    c102 = rows["C-102"]
    assert c102["outcome"] == "ready"
    record = check(c102, "Carrier company record")
    assert record["result"] == "info" and "normal for small truck owners" in record["summary"]
    assert record["cost_credits"] == 0


def test_tiny_allowance_makes_crustdata_checks_unknown_and_clean_bills_finish():
    rows, _ = bills(credits=0.1)
    assert rows["C-101"]["outcome"] == "ready" and rows["C-103"]["outcome"] == "ready"
    assert rows["C-104"]["outcome"] == "hold_bank_change"
    for ref in ("C-101", "C-104"):
        rec = check(rows[ref], "Carrier company record")
        assert rec["result"] == "unknown" and "run allowance" in rec["summary"]
    for name in ("Sender email domain", "Carrier company profile", "Carrier news"):
        if name == "Carrier company profile":
            continue  # no company ID, so no profile call is attempted
        assert check(rows["C-104"], name)["result"] == "unknown"
    calls = [c for r in rows.values() for c in r.get("calls", [])]
    assert sum(c["cost_credits"] for c in calls) == 0
    assert any(c["status"] == "budget_exceeded" for c in calls)


def test_lookalike_sender_domain_resolving_to_the_same_company_is_info_and_still_reviewed():
    rows, _ = bills(csv=HEADER + b"C-601,CAR-2,VRL,700,INR,00431100022227777,SBIN0000691,ap@vrllogistics.com\n")
    row = rows["C-601"]
    assert row["outcome"] == "review_sender_domain"
    assert check(row, "Sender email domain")["result"] == "info"


def test_sender_domain_owned_by_another_company_is_a_warning_naming_it():
    rows, _ = bills(csv=HEADER + b"C-602,CAR-1,Blue Dart,700,INR,502000112341234,HDFC0000053,ap@dhl.com\n")
    sender = check(rows["C-602"], "Sender email domain")
    assert sender["result"] == "warn" and "DHL Group" in sender["summary"]


def test_no_full_account_number_or_email_in_evaluated_rows():
    rows, _ = bills()
    text = json.dumps([{k: v for k, v in r.items() if k != "raw"} for r in rows.values()], ensure_ascii=False)
    for secret in ("502000112341234", "778899009876", "917020045673333", "123400006789001", "00431100022227777",
                   "ar@bluedart.com", "ar@bluedart-payments.com", "accounts@navata.com", "finance@vrlgroup.in"):
        assert secret not in text


def test_posting_chain_for_the_four_brief_lines():
    out, fake = lines()
    assert [r["outcome"] for r in out] == ["posted", "posted", "hold_possible_duplicate", "cannot_verify"]
    assert [(r.get("posting") or {}).get("ledger_account") for r in out] == ["staff meals", "cloud hosting", None, None]
    assert_contract(out)
    steps = [[s["step"] for s in r["display"]["chain"]] for r in out]
    assert steps[0] == steps[1] == steps[2] == ["Bank text", "Merchant", "Legal payee", "Ledger rule", "Posting"]
    assert [s["result"] for s in out[0]["display"]["chain"]] == ["pass"] * 5
    assert out[0]["display"]["chain"][1] == {"step": "Merchant", "value": "Swiggy (swiggy.com)", "source": "Crustdata",
                                             "result": "pass"}
    assert out[2]["display"]["chain"][-1]["result"] == "warn"
    assert out[0]["display"]["chain_gap"] is None

    sharma = out[3]
    assert sharma["display"]["chain"] == [
        {"step": "Bank text", "value": "PAYTM*SHARMA TRD", "source": None, "result": "pass"},
        {"step": "Merchant", "value": None, "source": None, "result": "fail"}]
    assert "PAYTM*SHARMA TRD" in sharma["display"]["chain_gap"]
    lookup = check(sharma, "Merchant lookup")
    assert lookup["result"] == "unknown" and lookup["cost_credits"] == 1.0
    assert "Suggestion 3" in lookup["data"] and "Suggestion 4" not in lookup["data"]
    assert len(sharma["missing"]) == 1
    assert "PAYTM*SHARMA TRD" in sharma["missing"][0] and "no source links a payee to this charge" in sharma["missing"][0]

    aws = check(out[1], "Legal payee")
    assert aws["source"] == "Web page" and "via Crustdata web_enrich_live" in aws["source_ref"]
    assert "Amazon Web Services EMEA SARL" in aws["field_or_passage"]
    # One call per domain and per page per run.
    assert [m for m, _ in fake.seen].count("web_enrich_live") == 1
    assert [m for m, _ in fake.seen].count("company_identify") == 2


def test_legal_page_falls_back_to_direct_fetch_when_web_enrich_fails():
    out, _ = lines(fake=FakeSources(costs=LIST_COSTS, enrich_page=False))
    assert out[1]["outcome"] == "posted"
    ev = check(out[1], "Legal payee")
    assert "direct fetch" in ev["source_ref"]
    assert [c["adapter"] for c in out[1]["calls"]][-1] == "web"


def test_posting_with_no_allowance_keeps_outcomes_and_marks_lookups_unknown():
    out, _ = lines(credits=0.0)
    assert [r["outcome"] for r in out] == ["posted", "posted", "hold_possible_duplicate", "cannot_verify"]
    assert check(out[0], "Merchant company record")["result"] == "unknown"
    assert check(out[3], "Merchant lookup")["result"] == "unknown"
    assert "did not run" in out[3]["missing"][0]
