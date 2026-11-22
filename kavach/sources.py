"""Live source adapters. Each returns its ledger call; none returns raw personal data."""
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

CRUSTDATA_URL = "https://api.crustdata.com/company/identify"
COMPANY_IDENTIFY_ESTIMATE = 0.2


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


class LiveSources:
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    @property
    def crustdata_key(self) -> str:
        return _read_dotenv_key("CRUSTDATA_API_KEY")

    def company_domain(self, domain: str) -> dict:
        """Corroborate a carrier's domain with Crustdata company_identify (0.2 credits per match)."""
        call = {"adapter": "crustdata.company_identify", "endpoint": CRUSTDATA_URL, "cost_credits": 0.0, "status": "skipped_no_key"}
        key = self.crustdata_key
        if not key:
            return {"call": call}
        try:
            r = httpx.post(CRUSTDATA_URL, json={"domains": [domain]}, timeout=self.timeout, headers={
                "authorization": f"Bearer {key}", "x-api-version": "2025-11-01"})
        except httpx.HTTPError:
            call["status"] = "error"
            return {"call": call}
        call["status"] = f"http_{r.status_code}" if r.status_code != 200 else "ok"
        try:
            call["cost_credits"] = float(r.headers.get("x-credits-used", "0") or 0)
        except ValueError:
            pass
        if r.status_code != 200:
            return {"call": call}
        matches = (r.json() or [{}])[0].get("matches", [])
        primary = next((m["company_data"]["basic_info"].get("primary_domain") for m in matches
                        if m.get("company_data", {}).get("basic_info", {}).get("primary_domain") == domain), None)
        return {"call": call, "primary_domain": primary, "retrieved_at": _now(),
                "source_ref": f"Crustdata company_identify domains=[{domain}]"}

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

    def company_domain(self, domain: str) -> dict:
        if not self._can_spend(COMPANY_IDENTIFY_ESTIMATE):
            return {"status": "budget_exceeded", "retrieved_at": _now(),
                    "call": {"adapter": "crustdata.company_identify", "endpoint": CRUSTDATA_URL, "cost_credits": 0.0, "status": "budget_exceeded"}}
        res = self.inner.company_domain(domain)
        self.credits_used += float((res.get("call") or {}).get("cost_credits", 0.0) or 0.0)
        return res

    def fetch_page_text(self, url: str):
        if not self._can_spend(0.0):
            raise RuntimeError("run allowance reached")
        fn = getattr(self.inner, "fetch_page_text", None)
        if fn is None:
            from kavach.postings import fetch_page_text
            return fetch_page_text(url)
        return fn(url)
