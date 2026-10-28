"""The entry pages: list, add, edit, delete."""
from gastos import db
from gastos.dates import today

from .conftest import add_entry, log_in_as, names_to_ids, post


def ids(app, user_id):
    with app.app_context():
        return names_to_ids(user_id)


def count_entries(app, user_id):
    with app.app_context():
        return db.query_one("SELECT COUNT(*) AS n FROM transactions WHERE user_id = ?", (user_id,))["n"]


def test_entry_pages_need_a_login(client):
    for url in ("/transactions", "/transactions/new", "/transactions/1/edit", "/wallets", "/categories"):
        assert client.get(url).status_code == 302


def test_add_an_expense(owner_client, app, owner_id):
    accounts, categories = ids(app, owner_id)
    response = post(owner_client, "/transactions/new", {
        "kind": "expense", "amount": "150.50", "date": today().isoformat(),
        "account_id": accounts["Cash"], "category_id": categories["Food"], "note": "Jollibee",
    })
    assert response.status_code == 302 and response.headers["Location"] == "/transactions"
    page = owner_client.get("/transactions").get_data(as_text=True)
    assert "Jollibee" in page and "−₱150.50" in page and "Saved: spending" in page


def test_add_form_shows_errors(owner_client, app, owner_id):
    response = post(owner_client, "/transactions/new", {"kind": "expense", "amount": "abc", "date": ""})
    page = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Please fix the marked fields" in page and 'aria-invalid="true"' in page
    assert count_entries(app, owner_id) == 0


def test_save_and_add_another_keeps_kind_date_and_wallet(owner_client, app, owner_id):
    accounts, categories = ids(app, owner_id)
    response = post(owner_client, "/transactions/new", {
        "kind": "income", "amount": "500", "date": "2026-10-03", "account_id": accounts["GCash"],
        "category_id": categories["Gifts"], "again": "1",
    })
    location = response.headers["Location"]
    assert location.startswith("/transactions/new?")
    assert "kind=income" in location and "date=2026-10-03" in location and f"account={accounts['GCash']}" in location
    form = owner_client.get(location).get_data(as_text=True)
    assert 'value="2026-10-03"' in form


def test_add_a_transfer(owner_client, app, owner_id):
    accounts, _ = ids(app, owner_id)
    post(owner_client, "/transactions/new", {
        "kind": "transfer", "amount": "2000", "date": "2026-10-06",
        "account_id": accounts["Bank"], "to_account_id": accounts["Cash"], "note": "ATM",
    })
    page = owner_client.get("/transactions?month=2026-10").get_data(as_text=True)
    assert "Bank → Cash" in page


def test_the_form_offers_categories_of_the_kind(owner_client):
    spending = owner_client.get("/transactions/new?kind=expense").get_data(as_text=True)
    income = owner_client.get("/transactions/new?kind=income").get_data(as_text=True)
    assert ">Rent<" in spending and ">Salary<" not in spending
    assert ">Salary<" in income and ">Rent<" not in income


def test_edit_an_entry(owner_client, app, owner_id):
    entry_id = add_entry(app, owner_id, "expense", 100_00, "2026-10-02", note="Lunch")
    accounts, categories = ids(app, owner_id)
    form = owner_client.get(f"/transactions/{entry_id}/edit").get_data(as_text=True)
    assert 'value="100.00"' in form and 'value="Lunch"' in form

    response = post(owner_client, f"/transactions/{entry_id}/edit", {
        "kind": "expense", "amount": "120", "date": "2026-10-02", "account_id": accounts["GCash"],
        "category_id": categories["Food"], "note": "Lunch + drink", "back": "/transactions?month=2026-10",
    })
    assert response.headers["Location"] == "/transactions?month=2026-10"
    with app.app_context():
        row = db.query_one("SELECT amount, note, account_id FROM transactions WHERE id = ?", (entry_id,))
    assert row == {"amount": 120_00, "note": "Lunch + drink", "account_id": accounts["GCash"]}


def test_edit_never_redirects_to_another_site(owner_client, app, owner_id):
    entry_id = add_entry(app, owner_id, "expense", 100_00, "2026-10-02")
    response = post(owner_client, f"/transactions/{entry_id}/delete", {"back": "https://evil.example"})
    assert response.headers["Location"] == "/transactions"


def test_delete_an_entry(owner_client, app, owner_id):
    entry_id = add_entry(app, owner_id, "expense", 100_00, "2026-10-02")
    post(owner_client, f"/transactions/{entry_id}/delete")
    assert count_entries(app, owner_id) == 0


def test_archived_wallet_stays_on_its_old_entries(owner_client, app, owner_id):
    entry_id = add_entry(app, owner_id, "expense", 100_00, "2026-10-02", account="GCash")
    accounts, _ = ids(app, owner_id)
    post(owner_client, f"/wallets/{accounts['GCash']}/archive")
    assert ">GCash<" not in owner_client.get("/transactions/new").get_data(as_text=True)
    assert ">GCash<" in owner_client.get(f"/transactions/{entry_id}/edit").get_data(as_text=True)


def test_nobody_can_touch_another_users_entry(client, app, owner_id, other_id):
    entry_id = add_entry(app, owner_id, "expense", 100_00, "2026-10-02", note="mine")
    log_in_as(client, other_id)
    assert client.get(f"/transactions/{entry_id}/edit").status_code == 404
    assert post(client, f"/transactions/{entry_id}/edit", {"kind": "expense", "amount": "1"}).status_code == 404
    assert post(client, f"/transactions/{entry_id}/delete").status_code == 404
    assert count_entries(app, owner_id) == 1


def test_nobody_can_use_another_users_wallet(client, app, owner_id, other_id):
    owner_accounts, _ = ids(app, owner_id)
    _, other_categories = ids(app, other_id)
    log_in_as(client, other_id)
    response = post(client, "/transactions/new", {
        "kind": "expense", "amount": "5", "date": "2026-10-02",
        "account_id": owner_accounts["Cash"], "category_id": other_categories["Food"],
    })
    assert response.status_code == 400
    assert count_entries(app, other_id) == 0


def test_list_filters_and_totals(owner_client, app, owner_id):
    add_entry(app, owner_id, "income", 18_500_00, "2026-10-15", account="Bank", note="Sweldo")
    add_entry(app, owner_id, "expense", 150_00, "2026-10-02", note="Jollibee")
    add_entry(app, owner_id, "expense", 99_00, "2026-09-30", note="September lunch")
    page = owner_client.get("/transactions?month=2026-10").get_data(as_text=True)
    assert "October 2026" in page and "2 transactions" in page
    assert "Sweldo" in page and "Jollibee" in page and "September lunch" not in page
    assert "₱18,500.00" in page and "₱150.00" in page

    page = owner_client.get("/transactions?month=all&q=lunch").get_data(as_text=True)
    assert "1 transaction" in page and "September lunch" in page and "All months" in page

    page = owner_client.get("/transactions?month=2026-10&kind=income").get_data(as_text=True)
    assert "Sweldo" in page and "Jollibee" not in page


def test_month_arrows(owner_client):
    page = owner_client.get("/transactions?month=2026-01").get_data(as_text=True)
    assert "month=2025-12" in page and "month=2026-02" in page


def test_paging_links(owner_client, app, owner_id):
    for n in range(51):
        add_entry(app, owner_id, "expense", 100, "2026-10-02", note=f"n{n}")
    page = owner_client.get("/transactions?month=2026-10").get_data(as_text=True)
    assert "Page 1 of 2" in page and "page=2" in page
    page = owner_client.get("/transactions?month=2026-10&page=9").get_data(as_text=True)
    assert "Page 2 of 2" in page  # too big: the last page


def test_home_shows_this_month(owner_client, app, owner_id):
    add_entry(app, owner_id, "expense", 250_00, today().isoformat(), note="Grab")
    page = owner_client.get("/").get_data(as_text=True)
    assert "Grab" in page and "−₱250.00" in page and "See all" in page
