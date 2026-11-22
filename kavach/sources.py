"""Live source adapters. Each returns its ledger call; none returns raw personal data.

Every adapter returns a dict with "status" and "call" ({adapter, endpoint, cost_credits, status}).
Crustdata credit cost comes from the response header x-credits-used.
"""
import html
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

CRUSTDATA_BASE = "https://api.crustdata.com"
CRUSTDATA_URL = f"{CRUSTDATA_BASE}/company/identify"
COMPANY_ENRICH_URL = f"{CRUSTDATA_BASE}/company/enrich"
WEB_SEARCH_URL = f"{CRUSTDATA_BASE}/web/search/live"
WEB_ENRICH_URL = f"{CRUSTDATA_BASE}/web/enrich/live"
CRUSTDATA_API_VERSION = "2025-11-01"
RATE_LIMIT_WAIT_SECONDS = 1.5

COMPANY_IDENTIFY_ESTIMATE = 0.2
COMPANY_ENRICH_ESTIMATE = 2.0
WEB_SEARCH_ESTIMATE = 1.0
WEB_ENRICH_ESTIMATE = 1.0

# Sections confirmed by a live probe on this plan (2026-11-22): basic_info, headcount, locations.
ENRICH_FIELDS = ["basic_info", "headcount", "locations"]
BASIC_INFO_KEYS = ("name", "primary_domain", "all_domains", "website", "description", "company_type",
                   "year_founded", "employee_count_range", "markets")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_dotenv_key(name: str, path: Path = Path(".env")) -> str:
    val = os.environ.get(name, "").strip()
    if val or not path.exists():
        return val
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    return ""


def html_to_text(text: str) -> str:
    """Page text with scripts, styles and HTML tags removed."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text or "")
    text = text.replace("\\n", " ").replace('\\"', '"')
    return html.unescape(re.sub(r"<[^>]+>", " ", text)).replace("\xa0", " ")


def _company(company_data: dict) -> dict:
    info = company_data.get("basic_info") or {}
    out = {k: info.get(k) for k in BASIC_INFO_KEYS}
    out["crustdata_company_id"] = company_data.get("crustdata_company_id") or info.get("crustdata_company_id")
    out["all_domains"] = list(out.get("all_domains") or [])
    out["markets"] = list(out.get("markets") or [])
    return out


class LiveSources:
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    @property
    def crustdata_key(self) -> str:
        return _read_dotenv_key("CRUSTDATA_API_KEY")

    def ifsc(self, code: str) -> dict:
        url = f"https://ifsc.razorpay.com/{code}"
        call = {"adapter": "ifsc", "endpoint": url, "cost_credits": 0.0, "status": "ok"}
        try:
            r = httpx.get(url, timeout=self.timeout)
        except httpx.HTTPError:
            call["status"] = "error"
            return {"status": "unavailable", "call": call, "retrieved_at": _now()}
        if r.status_code == 404:
            call["status"] = "not_found"
            return {"status": "invalid", "call": call, "retrieved_at": _now()}
        if r.status_code != 200:
            call["status"] = f"http_{r.status_code}"
            return {"status": "unavailable", "call": call, "retrieved_at": _now()}
        data = r.json()
        return {"status": "ok", "bank": data.get("BANK"), "branch": data.get("BRANCH"), "call": call, "retrieved_at": _now()}

    def _crustdata(self, adapter: str, url: str, body: dict, timeout: float) -> tuple[dict, object]:
        """POST to Crustdata. Returns (call, parsed JSON or None). The key never leaves this method."""
        call = {"adapter": adapter, "endpoint": url, "cost_credits": 0.0, "status": "skipped_no_key"}
        key = self.crustdata_key
        if not key:
            return call, None
        headers = {"authorization": f"Bearer {key}", "x-api-version": CRUSTDATA_API_VERSION,
                   "content-type": "application/json"}
        try:
            r = httpx.post(url, json=body, timeout=timeout, headers=headers)
            if r.status_code == 429:  # rate limited: wait once, then try one more time
                time.sleep(RATE_LIMIT_WAIT_SECONDS)
                r = httpx.post(url, json=body, timeout=timeout, headers=headers)
        except httpx.HTTPError:
            call["status"] = "error"
            return call, None
        call["status"] = "ok" if r.status_code == 200 else f"http_{r.status_code}"
        try:
            call["cost_credits"] = float(r.headers.get("x-credits-used", "0") or 0)
        except ValueError:
            pass
        if r.status_code != 200:
            return call, None
        try:
            return call, r.json()
        except ValueError:
            call["status"] = "error"
            return call, None

    def company_identify(self, domain: str) -> dict:
        """Find the Crustdata company that owns a web domain. Domain matching only, never name matching."""
        domain = (domain or "").lower().strip()
        call, data = self._crustdata("crustdata.company_identify", CRUSTDATA_URL, {"domains": [domain]}, self.timeout)
        res = {"call": call, "retrieved_at": _now(), "source_ref": f"Crustdata company_identify domains=[{domain}]",
               "company": None}
        if data is None:
            res["status"] = "unavailable"
            return res
        entries = data if isinstance(data, list) else []
        matches = [m for e in entries for m in (e.get("matches") or [])]
        companies = [_company(m.get("company_data") or {}) for m in
                     sorted(matches, key=lambda m: -(m.get("confidence_score") or 0))]
        owns = [c for c in companies if c.get("primary_domain") == domain] or \
               [c for c in companies if domain in c.get("all_domains", [])]
        res["status"] = "ok" if owns else "not_found"
        res["company"] = owns[0] if owns else None
        return res

    def company_domain(self, domain: str) -> dict:
        """Older adapter: corroborate a carrier's domain. Kept for callers that still use it."""
        res = self.company_identify(domain)
        company = res.get("company") or {}
        return {**res, "primary_domain": company.get("primary_domain")}

    def company_enrich(self, company_id) -> dict:
        """Company profile by Crustdata company ID (2 credits per returned match)."""
        call, data = self._crustdata("crustdata.company_enrich", COMPANY_ENRICH_URL,
                                     {"crustdata_company_ids": [company_id], "fields": ENRICH_FIELDS}, self.timeout * 3)
        res = {"call": call, "retrieved_at": _now(), "source_ref": f"Crustdata company_enrich crustdata_company_ids=[{company_id}]",
               "profile": None}
        if data is None:
            res["status"] = "unavailable"
            return res
        entries = data if isinstance(data, list) else []
        match = next((m for e in entries for m in (e.get("matches") or [])), None)
        if not match:
            res["status"] = "not_found"
            return res
        cd = match.get("company_data") or {}
        head = cd.get("headcount") or {}
        loc = cd.get("locations") or {}
        res["profile"] = {**_company(cd), "headcount_total": head.get("total"),
                          "largest_headcount_country": head.get("largest_headcount_country"),
                          "headquarters": loc.get("headquarters"), "city": loc.get("city"), "country": loc.get("country")}
        res["status"] = "ok"
        return res

    def web_search_live(self, query: str, start_date: int | None = None, page: int = 1) -> dict:
        """Live web search (1 credit per page). start_date is a Unix timestamp in seconds."""
        body = {"query": query, "page": page}
        if start_date is not None:
            body["start_date"] = int(start_date)
        call, data = self._crustdata("crustdata.web_search_live", WEB_SEARCH_URL, body, self.timeout * 6)
        res = {"call": call, "retrieved_at": _now(), "source_ref": f"Crustdata web_search_live query={query}",
               "results": []}
        if not isinstance(data, dict) or not data.get("success", True):
            res["status"] = "unavailable"
            return res
        res["results"] = [{"title": it.get("title") or "", "url": it.get("url") or "", "snippet": it.get("snippet") or ""}
                          for it in (data.get("results") or []) if isinstance(it, dict)]
        res["status"] = "ok"
        return res

    def web_enrich_live(self, url: str) -> dict:
        """Live page fetch through Crustdata (1 credit per page). Returns text with HTML removed."""
        call, data = self._crustdata("crustdata.web_enrich_live", WEB_ENRICH_URL, {"urls": [url]}, self.timeout * 6)
        res = {"call": call, "retrieved_at": _now(), "source_ref": f"{url} (via Crustdata web_enrich_live)",
               "text": None, "title": None}
        item = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else None
        if not item or not item.get("success") or not item.get("content"):
            res["status"] = "unavailable"
            if call["status"] == "ok":
                call["status"] = "error"
            return res
        res.update(status="ok", text=html_to_text(item["content"]), title=item.get("title"))
        return res

    def fetch_text(self, url: str):
        r = httpx.get(url, timeout=self.timeout * 2, follow_redirects=True, headers={"user-agent": "Mozilla/5.0 Kavach"})
        r.raise_for_status()
        return r.text, _now()


class BudgetedSources:
    """Enforces per-run credit and wall-clock allowances before any external call."""

    def __init__(self, inner, max_credits: float, max_seconds: float):
        self.inner = inner
        self.max_credits = max_credits
        self.max_seconds = max_seconds
        self.credits_used = 0.0
        self.started_at = time.monotonic()

    def _can_spend(self, estimated_credits: float) -> bool:
        elapsed = time.monotonic() - self.started_at
        return elapsed <= self.max_seconds and (self.credits_used + estimated_credits) <= self.max_credits + 1e-9

    def _guarded(self, method: str, adapter: str, endpoint: str, estimate: float, *args) -> dict:
        """Reserve the estimated credits, then call the inner adapter and record its real cost."""
        if not self._can_spend(estimate):
            return {"status": "budget_exceeded", "retrieved_at": _now(),
                    "call": {"adapter": adapter, "endpoint": endpoint, "cost_credits": 0.0, "status": "budget_exceeded"}}
        fn = getattr(self.inner, method, None)
        if fn is None:
            return {"status": "unavailable", "retrieved_at": _now(), "call": None}
        res = fn(*args)
        self.credits_used += float((res.get("call") or {}).get("cost_credits", 0.0) or 0.0)
        return res

    def ifsc(self, code: str) -> dict:
        if not self._can_spend(0.0):
            return {"status": "budget_exceeded", "retrieved_at": _now(),
                    "call": {"adapter": "ifsc", "endpoint": f"https://ifsc.razorpay.com/{code}", "cost_credits": 0.0, "status": "budget_exceeded"}}
        return self.inner.ifsc(code)

    def company_domain(self, domain: str) -> dict:
        return self._guarded("company_domain", "crustdata.company_identify", CRUSTDATA_URL, COMPANY_IDENTIFY_ESTIMATE, domain)

    def company_identify(self, domain: str) -> dict:
        return self._guarded("company_identify", "crustdata.company_identify", CRUSTDATA_URL, COMPANY_IDENTIFY_ESTIMATE, domain)

    def company_enrich(self, company_id) -> dict:
        return self._guarded("company_enrich", "crustdata.company_enrich", COMPANY_ENRICH_URL, COMPANY_ENRICH_ESTIMATE, company_id)

    def web_search_live(self, query: str, start_date: int | None = None, page: int = 1) -> dict:
        return self._guarded("web_search_live", "crustdata.web_search_live", WEB_SEARCH_URL, WEB_SEARCH_ESTIMATE,
                             query, start_date, page)

    def web_enrich_live(self, url: str) -> dict:
        return self._guarded("web_enrich_live", "crustdata.web_enrich_live", WEB_ENRICH_URL, WEB_ENRICH_ESTIMATE, url)

    def fetch_page_text(self, url: str):
        if not self._can_spend(0.0):
            raise RuntimeError("run allowance reached")
        fn = getattr(self.inner, "fetch_page_text", None)
        if fn is None:
            from kavach.postings import fetch_page_text
            return fetch_page_text(url)
        return fn(url)
