from pathlib import Path

from conftest import bills_csv, upload
from test_friday_run import bank_refs, file_rows, sign_all_ready

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"
HEADER = "date,description,amount,currency,reference,type"


def signed_friday_run(client):
    run_url = upload(client, "pay_bills", (SAMPLES / "friday_bills.csv").read_text()).headers["location"]
    sign_all_ready(client, run_url)
    return run_url


def reconcile(client, run_url, *lines):
    text = "\n".join([HEADER, *lines]) + "\n"
    return client.post(f"{run_url}/reconcile", files={"file": ("stmt.csv", text.encode(), "text/csv")})


def rows(client, run_url):
    return {r["item_ref"]: r for r in client.get(f"{run_url}/result.json").json()["rows"]}


def test_sample_statement_marks_the_three_signed_bills_paid(client):
    run_url = signed_friday_run(client)
    client.post(f"{run_url}/reconcile", files={"file": ("s.csv", (SAMPLES / "friday_bank_statement.csv").read_bytes(), "text/csv")})
    receipt = client.get(f"{run_url}/receipt.json").json()
    assert (receipt["paid"], receipt["returned"], receipt["waiting_for_bank"]) == (3, 0, 0)
    assert receipt["reconciliation"]["unlinked_lines"] == 1


def test_wrong_amount_missing_line_and_double_debit_stay_open(client):
    run_url = signed_friday_run(client)
    refs = bank_refs(client, run_url)
    reconcile(client, run_url,
              f"2026-11-27,NEFT {refs['C-101']} BLUE DART,48000.00,INR,,debit",
              f"2026-11-27,NEFT BLUE DART AGAIN,48000.00,INR,{refs['C-101']},debit",
              f"2026-11-27,NEFT GANESH,9999.00,INR,{refs['C-102']},debit")
    r = rows(client, run_url)
    assert all(r[b]["payout"]["status"] == "in_file" for b in ("C-101", "C-102", "C-103"))
    reasons = {o["bill_id"]: o["reason"] for o in client.get(f"{run_url}/receipt.json").json()["reconciliation"]["open"]}
    assert "double payment" in reasons["C-101"]
    assert "different amount" in reasons["C-102"]
    assert "No debit" in reasons["C-103"]
    assert client.get(f"{run_url}/receipt.json").json()["this_run"]["double_debits"] == 1


def test_returned_payment_reopens_the_bill_and_a_second_upload_changes_nothing(client):
    run_url = signed_friday_run(client)
    refs = bank_refs(client, run_url)
    stmt = [f"2026-11-27,NEFT,15750.00,INR,{refs['C-103']},debit",
            f"2026-11-29,NEFT RETURN {refs['C-103']},15750.00,INR,,credit"]
    reconcile(client, run_url, *stmt)
    reconcile(client, run_url, *stmt)
    r = rows(client, run_url)["C-103"]
    assert r["outcome"] == "reopened_reversed" and r["payout"]["status"] == "returned"
    assert r["decision"]["owner"] == "AP lead"
    assert "Reopened: payment returned" in client.get(run_url).text
    assert len(file_rows(client, run_url)[1]) == 3


def test_payment_file_has_full_accounts_but_no_other_output_does(client):
    run_url = signed_friday_run(client)
    _, lines = file_rows(client, run_url)
    assert "502000112341234" in {ln["beneficiary_account"] for ln in lines}
    for url in (run_url, f"{run_url}/result.json", f"{run_url}/receipt.json"):
        text = client.get(url).text
        assert "502000112341234" not in text and "917020045673333" not in text
    receipt = client.get(f"{run_url}/receipt.json").json()
    assert "downloaded 1 time" in receipt["personal_data"]["payment_file"]


NEW_ACCOUNT = bills_csv("C-601,CAR-2,VRL Logistics Limited,7000.00,INR,55551111222233,SBIN0000691,finance@vrlgroup.in")


def test_bank_change_needs_callback_then_a_different_authorizer(client):
    run_url = upload(client, "pay_bills", NEW_ACCOUNT).headers["location"]
    assert rows(client, run_url)["C-601"]["outcome"] == "hold_bank_change"
    change = f"{run_url}/rows/1"
    assert "error=no_callback" in client.post(f"{change}/authorize", data={"authorized_by": "Ravi"}).headers["location"]
    client.post(f"{change}/callback", data={"callback_by": "Asha", "outcome": "confirmed"})
    assert rows(client, run_url)["C-601"]["outcome"] == "hold_bank_change"
    assert "error=same_person" in client.post(f"{change}/authorize", data={"authorized_by": " asha "}).headers["location"]
    client.post(f"{change}/authorize", data={"authorized_by": "Ravi"})
    r = rows(client, run_url)["C-601"]
    assert r["outcome"] == "ready" and r["display"]["beneficiary_version"] == 2
    assert r["beneficiary_change"]["authorized_by"] == "Ravi"
    page = client.get(f"{change}/change").text
    assert "55551111222233" not in page and "2233" in page


def test_denied_callback_keeps_the_bill_held(client):
    run_url = upload(client, "pay_bills", NEW_ACCOUNT).headers["location"]
    client.post(f"{run_url}/rows/1/callback", data={"callback_by": "Asha", "outcome": "denied"})
    client.post(f"{run_url}/rows/1/authorize", data={"authorized_by": "Ravi"})
    r = rows(client, run_url)["C-601"]
    assert r["outcome"] == "hold_bank_change" and "possible fraud" in r["decision"]["reason"]


def test_no_trusted_contact_blocks_the_callback(client):
    run_url = upload(client, "pay_bills", bills_csv("C-701,CAR-4,Navata Road Transport,500.00,INR,111122223333,ICIC0000001,")).headers["location"]
    r = client.post(f"{run_url}/rows/1/callback", data={"callback_by": "Asha", "outcome": "confirmed"})
    assert "error=no_contact" in r.headers["location"]


def test_beneficiary_change_after_sign_off_warns_on_the_frozen_file(client):
    signed = upload(client, "pay_bills", bills_csv(
        "C-501,CAR-2,VRL Logistics Limited,9000.00,INR,00431100022227777,SBIN0000691,finance@vrlgroup.in",
        "C-502,CAR-3,Shree Ganesh Roadlines,100.00,INR,917020045673333,UTIB0000004,")).headers["location"]
    sign_all_ready(client, signed)
    before = file_rows(client, signed)[0][0]["sha256"]
    other = upload(client, "pay_bills", NEW_ACCOUNT).headers["location"]
    client.post(f"{other}/rows/1/callback", data={"callback_by": "Asha", "outcome": "confirmed"})
    client.post(f"{other}/rows/1/authorize", data={"authorized_by": "Ravi"})
    page = client.get(signed).text
    assert "Do not upload this file as it is" in page and "C-501" in page.split("Do not upload")[1][:300]
    assert file_rows(client, signed)[0][0]["sha256"] == before


def test_authorized_bank_change_is_still_checked_against_bills_already_signed(client):
    run_url = signed_friday_run(client)
    client.post(f"{run_url}/rows/4/callback", data={"callback_by": "Asha", "outcome": "confirmed"})
    client.post(f"{run_url}/rows/4/authorize", data={"authorized_by": "Ravi"})
    r = rows(client, run_url)["C-104"]
    assert r["outcome"] == "hold_possible_duplicate" and "C-101 (signed" in r["decision"]["reason"]


def test_value_block_shows_outcomes_and_cost(client):
    run_url = upload(client, "pay_bills", (SAMPLES / "friday_bills.csv").read_text()).headers["location"]
    page = client.get(run_url).text
    assert "What Kavach did in this run" in page and "Held money is not counted as savings" in page
    assert "src-crustdata" in page and "RazorpayX" not in page
    v = client.get(f"{run_url}/receipt.json").json()["this_run"]
    assert (v["ready"], v["bank_changes"], v["duplicates"]) == (3, 1, 1)


def test_bank_change_dialog_returns_to_the_run_page_with_feedback(client):
    run_url = upload(client, "pay_bills", NEW_ACCOUNT).headers["location"]
    page = client.get(run_url).text
    assert 'id="change-1"' in page and "Step 1. Call the carrier" in page
    r = client.post(f"{run_url}/rows/1/callback", data={"callback_by": "Asha", "outcome": "confirmed", "via": "dialog"})
    assert r.headers["location"] == f"{run_url}?done=callback#change-1"
    assert "Callback saved" in client.get(f"{run_url}?done=callback").text
    r = client.post(f"{run_url}/rows/1/authorize", data={"authorized_by": "asha", "via": "dialog"})
    assert r.headers["location"] == f"{run_url}?change_error=same_person#change-1"
    r = client.post(f"{run_url}/rows/1/authorize", data={"authorized_by": "Ravi", "via": "dialog"})
    assert r.headers["location"] == f"{run_url}?done=approved#why-1"
    assert rows(client, run_url)["C-601"]["outcome"] == "ready"


def test_signing_shows_a_toast_with_the_count(client):
    run_url = signed_friday_run(client)
    assert "3 bills signed" in client.get(f"{run_url}?done=signed&n=3").text
