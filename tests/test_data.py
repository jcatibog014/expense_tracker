"""The CSV pages: download and the two-step upload."""
import io

from gastos import db

from .conftest import add_entry, log_in_as, post

HEADER = "date,type,amount,wallet,to_wallet,category,note\n"


def upload(client, text, create_missing=True, name="money.csv"):
    data = {"file": (io.BytesIO(text.encode("utf-8")), name)}
    if create_missing:
        data["create_missing"] = "1"
    return post(client, "/data/import", data, content_type="multipart/form-data")


def notes(app, user_id):
    with app.app_context():
        return sorted(r["note"] for r in db.query("SELECT note FROM transactions WHERE user_id = ?", (user_id,)))


def test_export_all_and_by_filter(owner_client, app, owner_id):
    add_entry(app, owner_id, "expense", 150_50, "2026-10-02", note="=cmd")
    add_entry(app, owner_id, "income", 18_500_00, "2026-09-15", account="Bank", note="Sweldo")
    response = owner_client.get("/data/export?month=all")
    assert response.mimetype == "text/csv"
    assert 'filename="ang-gastos-all.csv"' in response.headers["Content-Disposition"]
    text = response.get_data(as_text=True)
    lines = text.lstrip("﻿").splitlines()
    assert lines[0] == HEADER.strip()
    assert lines[1] == "2026-09-15,income,18500.00,Bank,,Salary,Sweldo"  # oldest first
    assert lines[2] == "2026-10-02,expense,150.50,Cash,,Food,'=cmd"

    text = owner_client.get("/data/export?month=2026-10&kind=expense").get_data(as_text=True)
    assert "Sweldo" not in text and "150.50" in text


def test_export_is_private(client, app, owner_id, other_id):
    add_entry(app, owner_id, "expense", 100, "2026-10-02", note="owner secret")
    log_in_as(client, other_id)
    assert "owner secret" not in client.get("/data/export?month=all").get_data(as_text=True)


def test_upload_shows_a_preview_and_saves_nothing(owner_client, app, owner_id):
    response = upload(owner_client, HEADER + "2026-10-01,expense,99,Cash,,Food,Lugaw\n2026-10-02,expense,x,Cash,,Food,\n")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Ready to add" in page and "Rows with problems" in page and "Lugaw" in page
    assert "Amount must be a number" in page
    assert notes(app, owner_id) == []


def test_confirm_adds_the_good_rows_and_new_names(owner_client, app, owner_id):
    text = (HEADER + "2026-10-01,expense,99,Maya,,Pets,Dog food\n"
            "2026-10-02,transfer,500,Bank,Maya,,Cash in\n"
            "2026-10-03,income,1000,Cash,,Salary,Bonus\n"
            "2026-10-04,expense,oops,Cash,,Food,Bad row\n")
    page = upload(owner_client, text).get_data(as_text=True)
    assert "New wallets:</strong> Maya" in page and "Pets (spending)" in page
    response = post(owner_client, "/data/import/confirm", {"csv_text": text, "create_missing": "1"})
    assert response.headers["Location"] == "/transactions?month=all"
    assert notes(app, owner_id) == ["Bonus", "Cash in", "Dog food"]
    with app.app_context():
        wallet = db.query_one("SELECT kind FROM accounts WHERE user_id = ? AND name = 'Maya'", (owner_id,))
        category = db.query_one("SELECT kind, color FROM categories WHERE user_id = ? AND name = 'Pets'", (owner_id,))
    assert wallet == {"kind": "cash"} and category == {"kind": "expense", "color": "gray"}
    assert "Added 3 transactions from the file. Skipped 1." in owner_client.get("/transactions?month=all").get_data(as_text=True)


def test_unknown_names_without_create_missing(owner_client, app, owner_id):
    text = HEADER + "2026-10-01,expense,99,Maya,,Food,\n"
    page = upload(owner_client, text, create_missing=False).get_data(as_text=True)
    assert 'There is no wallet &#34;Maya&#34;' in page or "There is no wallet &quot;Maya&quot;" in page
    post(owner_client, "/data/import/confirm", {"csv_text": text})
    assert notes(app, owner_id) == []


def test_duplicates_are_found_and_skipped(owner_client, app, owner_id):
    add_entry(app, owner_id, "expense", 13_00, "2026-10-01", category="Transport", note="Jeep")
    text = HEADER + "2026-10-01,expense,13,Cash,,Transport,Jeep\n2026-10-01,expense,13,Cash,,Transport,Jeep\n"
    page = upload(owner_client, text).get_data(as_text=True)
    assert "Already saved" in page and "Skip the 1 row that is already saved" in page
    post(owner_client, "/data/import/confirm", {"csv_text": text, "skip_duplicates": "1"})
    assert notes(app, owner_id) == ["Jeep", "Jeep"]  # one was there, one was new


def test_round_trip_export_import_adds_nothing_new(owner_client, app, owner_id):
    add_entry(app, owner_id, "expense", 150_50, "2026-10-02", note="=cmd")
    add_entry(app, owner_id, "transfer", 2_000_00, "2026-10-03", account="Bank", to_account="Cash", note="ATM")
    exported = owner_client.get("/data/export?month=all").get_data(as_text=True)
    page = upload(owner_client, exported.lstrip("﻿")).get_data(as_text=True)
    assert "Skip the 2 rows that are already saved" in page


def test_bad_files(owner_client):
    page = upload(owner_client, "name,price\nrice,50\n").get_data(as_text=True)
    assert "Missing: date, type, amount, wallet" in page
    response = post(owner_client, "/data/import", {}, content_type="multipart/form-data")
    assert response.headers["Location"] == "/data"
    big = HEADER + ("2026-10-01,expense,1,Cash,,Food," + "x" * 100 + "\n") * 4000
    response = upload(owner_client, big)
    assert response.headers["Location"] == "/data"
    assert "too big" in owner_client.get("/data").get_data(as_text=True)


def test_the_demo_has_a_smaller_limit(client):
    post(client, "/demo")
    text = HEADER + "2026-10-01,expense,1,Cash,,Food,x\n" * 201
    page = upload(client, text).get_data(as_text=True)
    assert "The demo can add up to 200 rows" in page


def test_confirm_checks_everything_again(owner_client, app, owner_id, other_id):
    # A changed form can't add rows into another user's wallet: names are only looked up for you.
    text = HEADER + "2026-10-01,expense,1,Cash,,Food,mine\n"
    post(owner_client, "/data/import/confirm", {"csv_text": text})
    assert notes(app, owner_id) == ["mine"] and notes(app, other_id) == []
    assert post(owner_client, "/data/import/confirm", {"csv_text": "nonsense"}).status_code == 400


def test_pages_link_to_csv(owner_client):
    assert "Download CSV" in owner_client.get("/transactions").get_data(as_text=True)
    assert "CSV files" in owner_client.get("/settings").get_data(as_text=True)
    page = owner_client.get("/data").get_data(as_text=True)
    assert "Download your transactions" in page and "Add transactions from a file" in page
