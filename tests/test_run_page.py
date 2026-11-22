from conftest import bills_csv, upload


def test_start_page_has_one_bill_upload_with_budget_and_sandbox_label(client):
    page = client.get("/").text
    assert "Upload approved carrier bills" in page
    assert 'name="mode"' not in page and "Post bank lines" not in page
    assert "Run allowance" in page
    assert "Sandbox" in page

def test_valid_upload_creates_a_stable_run_url_listing_every_bill(client):
    response = upload(client, "pay_bills", bills_csv(
        "C-101,CAR-1,Blue Dart,48000.00,INR,123456781234,HDFC0000053,ap@bluedart.com",
        "C-102,CAR-2,VRL Logistics,12500.50,INR,999988887777,HDFC0000053,",
    ))
    assert response.status_code == 303
    run_url = response.headers["location"]
    assert run_url.startswith("/runs/")

    page = client.get(run_url).text
    assert "C-101" in page and "C-102" in page
    assert "48,000.00" in page
    assert client.get(run_url).text == page


def test_a_bill_missing_a_required_value_stays_visible_with_its_missing_fact(client):
    run_url = upload(client, "pay_bills", bills_csv(
        "C-201,CAR-1,Blue Dart,48000.00,INR,,HDFC0000053,",
    )).headers["location"]
    page = client.get(run_url).text
    assert "C-201" in page
    assert "Cannot verify" in page
    assert "account_number" in page
