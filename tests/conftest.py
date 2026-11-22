import pytest
from fastapi.testclient import TestClient

from kavach.app import create_app


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "kavach.db"


@pytest.fixture
def client(db_path):
    return TestClient(create_app(db_path), follow_redirects=False)


def bills_csv(*rows):
    header = "bill_id,carrier_id,carrier_name,amount,currency,account_number,ifsc,sender_email"
    return "\n".join([header, *rows]) + "\n"


def upload(client, mode, text, filename="input.csv"):
    return client.post(
        "/runs",
        data={"mode": mode},
        files={"file": (filename, text.encode(), "text/csv")},
    )
