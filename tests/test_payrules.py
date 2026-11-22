from datetime import date
from pathlib import Path

from kavach.intake import parse
from kavach.payrules import evaluate_bills
from kavach.records import load_records

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "samples" / "friday_bills.csv"


def _company(cid, name, domain, all_domains, founded, size, ctype, markets):
    return {"crustdata_company_id": cid, "name": name, "primary_domain": domain, "all_domains": all_domains,
            "website": f"https://www.{domain}", "description": f"{name} (test record)", "company_type": ctype,
            "year_founded": founded, "employee_count_range": size, "markets": markets}


# Shapes follow the live Crustdata responses confirmed on 2026-11-22.
COMPANIES = {
    "bluedart.com": _company(736, "Blue Dart", "bluedart.com", ["bluedart.com"], 1983, "10001+", "Public Company", ["NSE"]),
    "navata.com": _company(1276926, "Navata Road Transport", "navata.com", ["navata.com"], 1982, "1001-5000",
                           "Partnership", ["PRIVATE"]),
    "vrlgroup.in": _company(1975388, "VRL LOGISTICS LTD", "vrlgroup.in", ["vrlgroup.in", "vrllogistics.com"], 1976,
                            "10001+", "Public Company", []),
    "swiggy.com": _company(5702, "Swiggy", "swiggy.com", ["swiggy.in", "swiggy.com"], 2014, "10001+", "Public Company", ["BSE"]),
    "aws.com": _company(1033829, "Amazon Web Services (AWS)", "aws.com", ["aws.com", "aws.eu"], 2006, "10001+",
                        "Public Company", ["PRIVATE"]),
    "dhl.com": _company(9999, "DHL Group", "dhl.com", ["dhl.com"], 1969, "10001+", "Public Company", []),
}
COMPANIES["vrllogistics.com"] = COMPANIES["vrlgroup.in"]

# List prices (credits per call) for tests that check costs.
LIST_COSTS = {"company_identify": 0.2, "company_enrich": 2.0, "web_search_live": 1.0, "web_enrich_live": 1.0}
# Default costs keep the app tests' fixed receipt total for the Friday sample at 0.2 credits
# (four company_identify calls x 0.05; the other fake calls cost nothing).
APP_TEST_COSTS = {"company_identify": 0.05, "company_enrich": 0.0, "web_search_live": 0.0, "web_enrich_live": 0.0}
AWS_PAGE = ("Account Country | AWS Contracting Party ... Amazon Web Services EMEA SARL | 352 2789 0057 | "
            "38 Avenue John F. Kennedy, L-1855, Luxembourg")


class FakeSources:
    """Deterministic sources for tests. No network."""

    def __init__(self, costs=None, enrich_page=True):
        self.costs = {**APP_TEST_COSTS, **(costs or {})}
        self.enrich_page = enrich_page
        self.seen = []  # (method, argument) for each call

    def _call(self, adapter, endpoint, status="ok"):
        self.seen.append((adapter, endpoint))
        return {"adapter": f"crustdata.{adapter}", "endpoint": endpoint, "cost_credits": self.costs[adapter], "status": status}

    def ifsc(self, code):
        call = {"adapter": "ifsc", "endpoint": f"https://ifsc.razorpay.com/{code}", "cost_credits": 0.0, "status": "ok"}
        if code == "XXXX0000000":
            return {"status": "invalid", "call": call, "retrieved_at": "t"}
        return {"status": "ok", "bank": "Bank", "branch": "Branch", "call": call, "retrieved_at": "t"}

    def fetch_page_text(self, url):
        return AWS_PAGE, "2026-11-22T10:00:00+00:00"

    def company_identify(self, domain):
        company = COMPANIES.get(domain)
        return {"status": "ok" if company else "not_found", "company": dict(company) if company else None,
                "call": self._call("company_identify", "https://api.crustdata.com/company/identify"),
                "retrieved_at": "2026-11-22T10:00:00+00:00", "source_ref": f"Crustdata company_identify domains=[{domain}]"}

    def company_domain(self, domain):
        res = self.company_identify(domain)
        return {**res, "primary_domain": (res["company"] or {}).get("primary_domain")}

    def company_enrich(self, company_id):
        company = next((c for c in COMPANIES.values() if c["crustdata_company_id"] == company_id), None)
        profile = {**company, "headcount_total": 10946, "largest_headcount_country": "IND",
                   "headquarters": "Sahar Airport Road, Mumbai", "city": "Mumbai", "country": "IND"} if company else None
        return {"status": "ok" if company else "not_found", "profile": profile,
                "call": self._call("company_enrich", "https://api.crustdata.com/company/enrich"),
                "retrieved_at": "2026-11-22T10:00:00+00:00",
                "source_ref": f"Crustdata company_enrich crustdata_company_ids=[{company_id}]"}

    def web_search_live(self, query, start_date=None, page=1):
        results = [{"title": f"Result {i} for {query[:20]}", "url": f"https://news.example/{i}", "snippet": "text"}
                   for i in range(1, 5)]
        return {"status": "ok", "results": results,
                "call": self._call("web_search_live", "https://api.crustdata.com/web/search/live"),
                "retrieved_at": "2026-11-22T10:00:00+00:00", "source_ref": f"Crustdata web_search_live query={query}"}

    def web_enrich_live(self, url):
        call = self._call("web_enrich_live", "https://api.crustdata.com/web/enrich/live",
                          "ok" if self.enrich_page else "error")
        if not self.enrich_page:
            return {"status": "unavailable", "text": None, "call": call, "retrieved_at": "t"}
        return {"status": "ok", "text": AWS_PAGE, "title": "AWS Contracting Party", "call": call,
                "retrieved_at": "2026-11-22T10:00:00+00:00", "source_ref": f"{url} (via Crustdata web_enrich_live)"}


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
