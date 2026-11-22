from fastapi.testclient import TestClient

from conftest import bills_csv, make_client, upload
from kavach.app import create_app

DUMMY_ACCOUNT = "918273645500991"
DUMMY_EMAIL = "zz.private.person@carrier-example.in"


def test_malformed_upload_shows_a_readable_error_without_echoing_input(client):
    bad = f"bill,who,acct\nC-1,x,{DUMMY_ACCOUNT}\n"
    response = upload(client, "pay_bills", bad)
    assert response.status_code == 400
    assert "missing these columns" in response.text
    assert DUMMY_ACCOUNT not in response.text


def test_no_full_account_number_or_email_reaches_any_page_or_output(client, caplog):
    run_url = upload(client, "pay_bills", bills_csv(
        f"C-301,CAR-9,Sharma Roadlines,4000,INR,{DUMMY_ACCOUNT},HDFC0000053,{DUMMY_EMAIL}",
    )).headers["location"]
    responses = [client.get(run_url), client.get(f"{run_url}/result.json"), client.get(f"{run_url}/status.json")]
    assert all(r.status_code == 200 for r in responses)
    surfaces = [r.text for r in responses] + [caplog.text]
    for text in surfaces:
        assert DUMMY_ACCOUNT not in text
        assert DUMMY_EMAIL not in text
    assert "0991" in surfaces[0]


def test_after_a_restart_the_same_run_and_rows_come_back_without_resubmitting(db_path):
    first = make_client(db_path)
    run_url = upload(first, "pay_bills", bills_csv(
        "C-401,CAR-1,Blue Dart,1500,INR,123456781234,HDFC0000053,",
    )).headers["location"]
    before = first.get(f"{run_url}/result.json").json()
    assert before["rows"][0]["item_ref"] == "C-401"

    restarted = make_client(db_path)
    assert restarted.get(f"{run_url}/result.json").json() == before
    assert "C-401" in restarted.get(run_url).text


def test_organizer_result_agrees_with_the_page(client):
    data = bills_csv("C-801,CAR-1,Blue Dart,,INR,123456781234,HDFC0000053,")
    run_url = client.post("/runs", files={"file": ("bills.csv", data, "text/csv")}).headers["location"]
    result = client.get(f"{run_url}/result.json").json()
    page = client.get(run_url).text

    assert result["run_id"] in page
    assert result["mode"] == "pay_bills"
    outcomes = {r["item_ref"]: (r["outcome"], r["missing"]) for r in result["rows"]}
    assert outcomes == {
        "C-801": ("cannot_verify", ["amount"]),
    }
    assert "Cannot verify: missing amount" in page


def test_organizer_result_agrees_with_the_page_for_bank_lines(client):
    run_url = upload(client, "post_lines",
        "date,description,amount,currency,reference\n"
        "2026-10-03,RAZ*SWIGGY BLR,1240,INR,\n"
        "2026-10-09,PAYTM*SHARMA TRD,,INR,\n",
    ).headers["location"]
    result = client.get(f"{run_url}/result.json").json()
    page = client.get(run_url).text

    assert result["run_id"] in page
    assert result["mode"] == "post_lines"
    outcomes = {r["item_ref"]: (r["outcome"], r["missing"]) for r in result["rows"]}
    assert outcomes == {
        "line 1": ("posted", []),
        "line 2": ("cannot_verify", ["amount"]),
    }
    assert "Cannot verify: missing amount" in page


def test_status_reports_the_last_update_time_for_reconnecting_pages(client):
    run_url = upload(client, "pay_bills", bills_csv(
        "C-501,CAR-1,Blue Dart,1500,INR,123456781234,HDFC0000053,",
    )).headers["location"]
    status = client.get(f"{run_url}/status.json").json()
    assert status["run_id"] in run_url
    assert status["updated_at"]
