"""Live source adapters. Each returns its ledger call; none returns raw personal data."""
import os
from datetime import datetime, timezone

import httpx

CRUSTDATA_URL = "https://api.crustdata.com/company/identify"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LiveSources:
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self.crustdata_key = os.environ.get("CRUSTDATA_API_KEY", "")

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

    def company_domain(self, domain: str) -> dict:
        """Corroborate a carrier's domain with Crustdata company_identify (0.2 credits per match)."""
        call = {"adapter": "crustdata.company_identify", "endpoint": CRUSTDATA_URL, "cost_credits": 0.0, "status": "skipped_no_key"}
        if not self.crustdata_key:
            return {"call": call}
        try:
            r = httpx.post(CRUSTDATA_URL, json={"domains": [domain]}, timeout=self.timeout, headers={
                "authorization": f"Bearer {self.crustdata_key}", "x-api-version": "2025-11-01"})
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
