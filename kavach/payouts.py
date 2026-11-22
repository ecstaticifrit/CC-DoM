"""RazorpayX test-mode payouts, sent exactly once through the outbox (see docs/adr/0001)."""
import json
import os
import re
import threading
from decimal import Decimal

import httpx

API = "https://api.razorpay.com/v1"
FINAL = {"processed", "reversed", "failed", "rejected", "cancelled"}


class Uncertain(Exception):
    """The provider may or may not have the payout. Retry with the same key and body only."""


class Rejected(Exception):
    """The provider refused the request (4xx). Message is masked."""


def _mask_digits(text: str) -> str:
    return re.sub(r"\d{6,}", lambda m: "••••" + m.group()[-4:], text or "")


class RazorpayX:
    def __init__(self, timeout: float = 15.0):
        self.key_id = os.environ.get("RAZORPAYX_KEY_ID", "")
        self.key_secret = os.environ.get("RAZORPAYX_KEY_SECRET", "")
        self.source_account = os.environ.get("RAZORPAYX_SOURCE_ACCOUNT_NUMBER", "")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.key_id and self.key_secret and self.source_account)

    def _request(self, method: str, path: str, **kw) -> dict:
        try:
            r = httpx.request(method, API + path, auth=(self.key_id, self.key_secret), timeout=self.timeout, **kw)
        except httpx.HTTPError as err:
            raise Uncertain(type(err).__name__) from None
        if r.status_code >= 500:
            raise Uncertain(f"HTTP {r.status_code}")
        if r.status_code >= 400:
            try:
                desc = r.json().get("error", {}).get("description", "")
            except ValueError:
                desc = ""
            raise Rejected(_mask_digits(f"HTTP {r.status_code}: {desc}"))
        return r.json()

    def create_payout(self, body: dict, idem_key: str) -> dict:
        return self._request("POST", "/payouts", json=body, headers={"X-Payout-Idempotency": idem_key})

    def find_by_reference(self, reference_id: str) -> list[dict]:
        data = self._request("GET", "/payouts", params={"account_number": self.source_account, "reference_id": reference_id})
        return data.get("items", [])

    def get_payout(self, payout_id: str) -> dict:
        return self._request("GET", f"/payouts/{payout_id}")


def build_body(provider, payout: dict, raw: dict, display: dict) -> dict:
    name = re.sub(r"[^A-Za-z0-9 .\-]", " ", display.get("carrier") or raw.get("carrier_name") or "Carrier").strip()[:120]
    paise = int((Decimal(raw["amount"]) * 100).to_integral_value())
    return {
        "account_number": provider.source_account,
        "amount": paise,
        "currency": raw["currency"],
        "mode": "IMPS" if paise <= 50_000_000 else "NEFT",
        "purpose": "vendor bill",
        "queue_if_low_balance": True,
        "reference_id": payout["reference_id"],
        "narration": re.sub(r"[^A-Za-z0-9 ]", "", f"Kavach {payout['bill_id']}")[:30],
        "fund_account": {
            "account_type": "bank_account",
            "bank_account": {"name": name, "ifsc": raw["ifsc"], "account_number": raw["account_number"]},
            "contact": {"name": name, "type": "vendor", "reference_id": raw["carrier_id"]},
        },
    }


class PayoutWorker:
    def __init__(self, store, provider):
        self.store = store
        self.provider = provider
        self._stop = threading.Event()

    def tick(self) -> None:
        for p in self.store.open_payouts():
            if p["status"] in ("pending", "sending", "not_configured"):
                self._send(p)
            elif p["status"] == "submitted":
                self._refresh(p)

    def _send(self, p: dict) -> None:
        if not self.provider.configured:
            if p["status"] != "not_configured":
                self.store.update_payout(p["id"], status="not_configured",
                                         note="Payout not sent: RazorpayX test keys are missing. Add them to .env and restart.")
            return
        body_json = p["body_json"]
        if body_json is None:
            source = self.store.raw_row(p["run_id"], p["row_number"])
            body_json = json.dumps(build_body(self.provider, p, source["raw"], source["display"]), sort_keys=True)
        self.store.update_payout(p["id"], status="sending", body_json=body_json, attempts=p["attempts"] + 1, note=None)
        try:
            result = self.provider.create_payout(json.loads(body_json), p["idem_key"])
        except Rejected as err:
            self.store.update_payout(p["id"], status="failed_request", note=str(err))
            return
        except Uncertain as err:
            self._recover(p, str(err))
            return
        self._adopt(p, result)

    def _recover(self, p: dict, reason: str) -> None:
        try:
            items = self.provider.find_by_reference(p["reference_id"])
        except (Uncertain, Rejected):
            self.store.update_payout(p["id"], note=f"Provider uncertain ({reason}); will retry with the same key.")
            return
        body = json.loads(self.store_body(p))
        matches = [i for i in items if i.get("reference_id") == p["reference_id"] and i.get("amount") == body["amount"]
                   and i.get("currency") == body["currency"]]
        if len(matches) == 1:
            self._adopt(p, matches[0])
        elif len(matches) > 1:
            self.store.update_payout(p["id"], status="pending_review", note="More than one provider payout matches; held for review.")
        else:
            self.store.update_payout(p["id"], note=f"Provider uncertain ({reason}); will retry with the same key.")

    def store_body(self, p: dict) -> str:
        fresh = [o for o in self.store.open_payouts() if o["id"] == p["id"]]
        return (fresh[0]["body_json"] if fresh else None) or p["body_json"] or "{}"

    def _adopt(self, p: dict, result: dict) -> None:
        status = result.get("status")
        self.store.update_payout(p["id"], status="failed" if status in ("failed", "rejected") else "submitted",
                                 provider_id=result.get("id"), provider_status=status, utr=result.get("utr"),
                                 note=None if status not in ("failed", "rejected") else "Provider reports the payout failed. Returned to the controller; no automatic replacement.")

    def _refresh(self, p: dict) -> None:
        try:
            result = self.provider.get_payout(p["provider_id"])
        except (Uncertain, Rejected):
            return
        if result.get("status") != p["provider_status"] or result.get("utr") != p["utr"]:
            self.store.update_payout(p["id"], provider_status=result.get("status"), utr=result.get("utr"))

    def run_forever(self, interval: float = 2.0) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as err:  # keep the loop alive; never log bodies
                print(f"payout worker error: {type(err).__name__}")
            self._stop.wait(interval)

    def stop(self) -> None:
        self._stop.set()
