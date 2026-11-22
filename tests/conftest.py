import pytest
from fastapi.testclient import TestClient

from kavach.app import create_app
from test_payrules import FakeSources


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "kavach.db"


def make_client(db_path):
    from datetime import date
    app = create_app(db_path, sources=FakeSources(), today=date(2026, 11, 27))
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def client(db_path):
    return make_client(db_path)


def bills_csv(*rows):
    header = "bill_id,carrier_id,carrier_name,amount,currency,account_number,ifsc,sender_email"
    return "\n".join([header, *rows]) + "\n"


def upload(client, mode, text, filename="input.csv"):
    return client.post(
        "/runs",
        data={"mode": mode},
        files={"file": (filename, text.encode(), "text/csv")},
    )
