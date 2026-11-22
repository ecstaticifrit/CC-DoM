import pytest
from fastapi.testclient import TestClient

from kavach.app import create_app
from test_payrules import FakeSources


class FakeProvider:
    configured = True
    source_account = "2323230000001111"

    def __init__(self):
        self.payouts = {}
        self.calls = []
        self.fail_next = 0

    def create_payout(self, body, idem_key):
        from kavach.payouts import Uncertain
        self.calls.append(idem_key)
        existing = self.payouts.get(idem_key)
        if existing is None:
            existing = {"id": f"pout_{len(self.payouts) + 1:04d}", "status": "processing", "utr": None,
                        "reference_id": body["reference_id"], "amount": body["amount"], "currency": body["currency"]}
            self.payouts[idem_key] = existing
        if self.fail_next:
            self.fail_next -= 1
            raise Uncertain("timeout after provider accepted")
        return existing

    def find_by_reference(self, reference_id):
        return [p for p in self.payouts.values() if p["reference_id"] == reference_id]

    def get_payout(self, payout_id):
        return next(p for p in self.payouts.values() if p["id"] == payout_id)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "kavach.db"


@pytest.fixture
def provider():
    return FakeProvider()


def make_client(db_path, provider):
    from datetime import date
    app = create_app(db_path, sources=FakeSources(), provider=provider, start_worker=False, today=date(2026, 11, 27))
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def client(db_path, provider):
    return make_client(db_path, provider)


def bills_csv(*rows):
    header = "bill_id,carrier_id,carrier_name,amount,currency,account_number,ifsc,sender_email"
    return "\n".join([header, *rows]) + "\n"


def upload(client, mode, text, filename="input.csv"):
    return client.post(
        "/runs",
        data={"mode": mode},
        files={"file": (filename, text.encode(), "text/csv")},
    )
