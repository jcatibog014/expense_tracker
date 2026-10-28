"""The wallet and category pages."""
from gastos import db

from .conftest import add_entry, log_in_as, names_to_ids, post


def ids(app, user_id):
    with app.app_context():
        return names_to_ids(user_id)


def test_wallets_page_shows_balances(owner_client, app, owner_id):
    add_entry(app, owner_id, "income", 1_000_00, "2026-10-01", account="GCash")
    add_entry(app, owner_id, "expense", 250_00, "2026-10-02", account="GCash")
    page = owner_client.get("/wallets").get_data(as_text=True)
    assert "₱750.00" in page and "2 transactions" in page and "All your money now" in page


def test_add_and_edit_a_wallet(owner_client, app, owner_id):
    response = post(owner_client, "/wallets/new", {"name": "Maya", "kind": "ewallet", "opening_balance": "1,500"})
    assert response.headers["Location"] == "/wallets"
    accounts, _ = ids(app, owner_id)
    assert "Maya" in accounts

    post(owner_client, f"/wallets/{accounts['Maya']}/edit", {"name": "Maya Savings", "kind": "bank", "opening_balance": ""})
    with app.app_context():
        row = db.query_one("SELECT name, kind, opening_balance FROM accounts WHERE id = ?", (accounts["Maya"],))
    assert row == {"name": "Maya Savings", "kind": "bank", "opening_balance": 0}


def test_wallet_names_must_be_different(owner_client, app, owner_id):
    response = post(owner_client, "/wallets/new", {"name": "gcash", "kind": "ewallet"})
    assert response.status_code == 400
    assert "already have a wallet" in response.get_data(as_text=True)
    # Keeping its own name when editing is fine.
    accounts, _ = ids(app, owner_id)
    response = post(owner_client, f"/wallets/{accounts['GCash']}/edit", {"name": "GCash", "kind": "ewallet"})
    assert response.status_code == 302


def test_a_used_wallet_is_archived_not_deleted(owner_client, app, owner_id):
    add_entry(app, owner_id, "expense", 100, "2026-10-01", account="GCash")
    accounts, _ = ids(app, owner_id)
    post(owner_client, f"/wallets/{accounts['GCash']}/delete")
    assert "GCash" in ids(app, owner_id)[0]  # still there
    assert "can&#39;t be deleted" in owner_client.get(f"/wallets/{accounts['GCash']}/edit").get_data(as_text=True)

    post(owner_client, f"/wallets/{accounts['GCash']}/archive")
    page = owner_client.get("/wallets").get_data(as_text=True)
    assert "Archived" in page
    post(owner_client, f"/wallets/{accounts['GCash']}/archive")  # and back
    assert "Archived" not in owner_client.get("/wallets").get_data(as_text=True)


def test_an_unused_wallet_can_be_deleted(owner_client, app, owner_id):
    accounts, _ = ids(app, owner_id)
    post(owner_client, f"/wallets/{accounts['Bank']}/delete")
    assert "Bank" not in ids(app, owner_id)[0]


def test_no_wallets_means_add_one_first(owner_client, app, owner_id):
    with app.app_context():
        db.execute("UPDATE accounts SET archived = 1 WHERE user_id = ?", (owner_id,))
        db.commit()
    response = owner_client.get("/transactions/new")
    assert response.headers["Location"] == "/wallets/new"


def test_categories_page(owner_client, app, owner_id):
    add_entry(app, owner_id, "expense", 100, "2026-10-01", category="Rent")
    page = owner_client.get("/categories").get_data(as_text=True)
    assert "Spending" in page and "Income" in page and "Rent" in page and "1 transaction" in page


def test_add_and_edit_a_category(owner_client, app, owner_id):
    response = post(owner_client, "/categories/new", {"name": "Pets", "kind": "expense", "color": "violet"})
    assert response.headers["Location"] == "/categories"
    _, categories = ids(app, owner_id)
    # The kind can't change: the form's "kind" is ignored when editing.
    post(owner_client, f"/categories/{categories['Pets']}/edit", {"name": "Pet food", "kind": "income", "color": "green"})
    with app.app_context():
        row = db.query_one("SELECT name, kind, color FROM categories WHERE id = ?", (categories["Pets"],))
    assert row == {"name": "Pet food", "kind": "expense", "color": "green"}


def test_category_form_errors(owner_client):
    response = post(owner_client, "/categories/new", {"name": "Food", "kind": "expense", "color": "pink"})
    page = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "already have a category" in page and "Choose a colour" in page


def test_a_used_category_is_archived_not_deleted(owner_client, app, owner_id):
    add_entry(app, owner_id, "expense", 100, "2026-10-01", category="Fun")
    _, categories = ids(app, owner_id)
    post(owner_client, f"/categories/{categories['Fun']}/delete")
    assert "Fun" in ids(app, owner_id)[1]
    post(owner_client, f"/categories/{categories['Health']}/delete")
    assert "Health" not in ids(app, owner_id)[1]
    post(owner_client, f"/categories/{categories['Fun']}/archive")
    assert ">Fun<" not in owner_client.get("/transactions/new?kind=expense").get_data(as_text=True)


def test_nobody_can_touch_another_users_wallets_or_categories(client, app, owner_id, other_id):
    accounts, categories = ids(app, owner_id)
    log_in_as(client, other_id)
    for url in (f"/wallets/{accounts['Cash']}/edit", f"/categories/{categories['Food']}/edit"):
        assert client.get(url).status_code == 404
    for url in (f"/wallets/{accounts['Cash']}/archive", f"/wallets/{accounts['Cash']}/delete",
                f"/categories/{categories['Food']}/archive", f"/categories/{categories['Food']}/delete"):
        assert post(client, url).status_code == 404
    assert "Cash" in ids(app, owner_id)[0] and "Food" in ids(app, owner_id)[1]
