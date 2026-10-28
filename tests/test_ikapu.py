"""Ikapu: 10% of every income set aside in the Ikapu wallet, and the database upgrade."""
import io
from datetime import date
from pathlib import Path

from gastos import db, recurring, tithes
from gastos.dates import today

from .conftest import add_entry, log_in_as, names_to_ids, post

FIXTURES = Path(__file__).parent / "fixtures"


def ids(app, user_id):
    with app.app_context():
        return names_to_ids(user_id)


def set_asides(app, user_id):
    """Every set-aside: (amount, date, from wallet, to wallet, the income's id)."""
    with app.app_context():
        return db.query(
            """SELECT t.amount, t.date, a.name AS wallet, ta.name AS to_wallet, t.tithe_of
               FROM transactions t JOIN accounts a ON a.id = t.account_id
               JOIN accounts ta ON ta.id = t.to_account_id
               WHERE t.user_id = ? AND t.tithe_of IS NOT NULL ORDER BY t.id""",
            (user_id,),
        )


def add_income(client, app, user_id, amount="18,500", day="2026-10-15", wallet="Bank"):
    accounts, categories = ids(app, user_id)
    return post(client, "/transactions/new", {
        "kind": "income", "amount": amount, "date": day,
        "account_id": accounts[wallet], "category_id": categories["Salary"], "note": "Sweldo",
    })


def income_id(app, user_id):
    with app.app_context():
        return db.query_one("SELECT id FROM transactions WHERE user_id = ? AND kind = 'income'", (user_id,))["id"]


def test_tithe_amount_rounds_to_the_centavo():
    assert tithes.tithe_amount(18_500_00) == 1_850_00
    assert tithes.tithe_amount(15) == 2  # 1.5 centavos -> 2
    assert tithes.tithe_amount(14) == 1
    assert tithes.tithe_amount(1_234_56) == 12_346


def test_new_users_get_the_ikapu_wallet_and_category(app, owner_id):
    with app.app_context():
        assert tithes.ikapu_wallet(owner_id)["name"] == "Ikapu"
        assert tithes.ikapu_category(owner_id)["kind"] == "expense"


def test_income_sets_aside_ten_percent(owner_client, app, owner_id):
    response = add_income(owner_client, app, owner_id)
    assert response.status_code == 302
    page = owner_client.get("/transactions?month=2026-10").get_data(as_text=True)
    assert "₱1,850.00 (10%) went to your Ikapu wallet." in page and "Bank → Ikapu" in page
    assert set_asides(app, owner_id) == [{
        "amount": 1_850_00, "date": "2026-10-15", "wallet": "Bank", "to_wallet": "Ikapu",
        "tithe_of": income_id(app, owner_id)}]


def test_spending_and_transfers_have_no_ikapu(owner_client, app, owner_id):
    accounts, categories = ids(app, owner_id)
    post(owner_client, "/transactions/new", {"kind": "expense", "amount": "100", "date": "2026-10-01",
                                             "account_id": accounts["Cash"], "category_id": categories["Food"]})
    post(owner_client, "/transactions/new", {"kind": "transfer", "amount": "100", "date": "2026-10-01",
                                             "account_id": accounts["Bank"], "to_account_id": accounts["Cash"]})
    add_income(owner_client, app, owner_id, wallet="Ikapu")  # income straight into Ikapu
    assert set_asides(app, owner_id) == []


def test_editing_the_income_changes_its_ikapu(owner_client, app, owner_id):
    add_income(owner_client, app, owner_id)
    the_income = income_id(app, owner_id)
    accounts, categories = ids(app, owner_id)
    post(owner_client, f"/transactions/{the_income}/edit", {
        "kind": "income", "amount": "20,000", "date": "2026-10-16",
        "account_id": accounts["GCash"], "category_id": categories["Salary"], "note": "Sweldo",
    })
    assert set_asides(app, owner_id) == [{
        "amount": 2_000_00, "date": "2026-10-16", "wallet": "GCash", "to_wallet": "Ikapu", "tithe_of": the_income}]
    # Income -> spending: no ikapu any more.
    post(owner_client, f"/transactions/{the_income}/edit", {
        "kind": "expense", "amount": "200", "date": "2026-10-16",
        "account_id": accounts["GCash"], "category_id": categories["Food"],
    })
    assert set_asides(app, owner_id) == []


def test_deleting_the_income_deletes_its_ikapu(owner_client, app, owner_id):
    add_income(owner_client, app, owner_id)
    post(owner_client, f"/transactions/{income_id(app, owner_id)}/delete")
    with app.app_context():
        assert db.query("SELECT * FROM transactions WHERE user_id = ?", (owner_id,)) == []
    assert "Its ikapu set-aside is deleted too." in owner_client.get("/transactions").get_data(as_text=True)


def test_a_set_aside_is_changed_through_its_income(owner_client, app, owner_id):
    add_income(owner_client, app, owner_id)
    with app.app_context():
        set_aside = db.query_one("SELECT id FROM transactions WHERE tithe_of IS NOT NULL")["id"]
    response = owner_client.get(f"/transactions/{set_aside}/edit")
    assert response.headers["Location"].startswith(f"/transactions/{income_id(app, owner_id)}/edit")


def test_repeating_income_sets_aside_ikapu(app, owner_id):
    accounts, categories = ids(app, owner_id)
    with app.app_context():
        db.execute(
            """INSERT INTO recurring (user_id, kind, amount, day_of_month, start_date, account_id, category_id, note)
               VALUES (?, 'income', 1000000, 15, '2026-09-01', ?, ?, 'Sweldo')""",
            (owner_id, accounts["Bank"], categories["Salary"]),
        )
        recurring.post_due(owner_id, date(2026, 10, 28))
        db.commit()
    assert [(s["amount"], s["date"]) for s in set_asides(app, owner_id)] == [
        (1_000_00, "2026-09-15"), (1_000_00, "2026-10-15")]


def test_csv_income_gets_ikapu_and_exported_set_asides_are_skipped(owner_client, app, owner_id):
    add_income(owner_client, app, owner_id)
    exported = owner_client.get("/data/export?month=all").get_data(as_text=True).lstrip("﻿")
    assert "Ikapu (10% set aside)" in exported

    # Import the export into a new user: the income comes in, and its ikapu is
    # made fresh, not copied (that would make it twice).
    with app.app_context():
        from gastos import auth
        new_user = auth.create_user("maria", "long enough")
        db.commit()
    log_in_as(owner_client, new_user)
    page = post(owner_client, "/data/import", {"file": (io.BytesIO(exported.encode()), "x.csv")},
                content_type="multipart/form-data").get_data(as_text=True)
    assert "₱1,850.00</strong>, will be set aside" in page and "made by itself" in page
    post(owner_client, "/data/import/confirm", {"csv_text": exported})
    assert [(s["amount"], s["to_wallet"]) for s in set_asides(app, new_user)] == [(1_850_00, "Ikapu")]


def test_catch_up_for_income_from_before_ikapu(owner_client, app, owner_id):
    first = today().replace(day=1)
    add_entry(app, owner_id, "income", 5_000_00, first.isoformat(), account="Bank")  # no set-aside: as if old
    page = owner_client.get("/ikapu").get_data(as_text=True)
    assert "1 income in" in page and "Set aside ₱500.00 for it?" in page
    post(owner_client, "/ikapu/catch-up")
    assert [s["amount"] for s in set_asides(app, owner_id)] == [500_00]
    assert "Every income in" in owner_client.get("/ikapu").get_data(as_text=True)


def test_month_summary_and_give_button(owner_client, app, owner_id):
    first = today().replace(day=1)
    add_income(owner_client, app, owner_id, amount="10,000", day=first.isoformat())
    add_entry(app, owner_id, "expense", 600_00, first.isoformat(), account="Ikapu", category="Ikapu")
    with app.app_context():
        summary = tithes.month_summary(owner_id, first)
    assert (summary["set_aside"], summary["given"], summary["waiting"]) == (1_000_00, 600_00, 400_00)

    page = owner_client.get("/").get_data(as_text=True)
    assert "Ikapu <span" in page and "Waiting <strong>₱400.00</strong>" in page
    accounts, categories = ids(app, owner_id)
    form = owner_client.get(
        f"/transactions/new?kind=expense&account={accounts['Ikapu']}&category={categories['Ikapu']}&amount=400.00"
    ).get_data(as_text=True)
    assert 'value="400.00"' in form


def test_the_ikapu_wallet_cannot_be_archived_or_deleted(owner_client, app, owner_id):
    accounts, _ = ids(app, owner_id)
    post(owner_client, f"/wallets/{accounts['Ikapu']}/archive")
    post(owner_client, f"/wallets/{accounts['Ikapu']}/delete")
    with app.app_context():
        assert tithes.ikapu_wallet(owner_id)["archived"] == 0
    assert "can&#39;t be deleted" in owner_client.get(f"/wallets/{accounts['Ikapu']}/edit").get_data(as_text=True)


def test_sync_only_touches_your_own_transactions(app, owner_id, other_id):
    entry = add_entry(app, owner_id, "income", 1_000_00, "2026-10-01", account="Bank")
    with app.app_context():
        assert tithes.sync(other_id, entry) is None
        assert db.query("SELECT * FROM transactions WHERE tithe_of IS NOT NULL") == []


# ---------- The database upgrade ----------

def make_old_database(app):
    """Turn the test database into one from before ikapu (schema_v0.sql), with one user."""
    sql = (FIXTURES / "schema_v0.sql").read_text(encoding="utf-8")
    with app.app_context():
        if db.is_postgres():
            sql = sql.replace("id INTEGER PRIMARY KEY", "id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY")
            db.get_db().execute("DROP TABLE IF EXISTS schema_version")
            db.get_db().execute(sql)
        else:
            db.get_db().executescript("DROP TABLE IF EXISTS schema_version;" + sql)
        user = db.insert("INSERT INTO users (username, password_hash) VALUES ('old', 'x') RETURNING id")
        db.execute("INSERT INTO accounts (user_id, name, kind) VALUES (?, 'Cash', 'cash')", (user,))
        db.commit()
        return user


def test_upgrade_an_old_database(app):
    user = make_old_database(app)
    result = app.test_cli_runner().invoke(args=["upgrade-db"])
    assert "Upgraded the database from version 0 to 1." in result.output
    with app.app_context():
        assert tithes.ikapu_wallet(user)["name"] == "Ikapu"
        assert tithes.ikapu_category(user) is not None
        assert db.query_one("SELECT tithe_of FROM transactions LIMIT 1") is None  # the column exists
        assert db.schema_version() == len(db.MIGRATIONS)
    # Running it again is safe.
    assert "up to date" in app.test_cli_runner().invoke(args=["upgrade-db"]).output


def test_a_new_database_is_already_up_to_date(app):
    with app.app_context():
        assert db.schema_version() == len(db.MIGRATIONS)
        assert db.upgrade_db() == (len(db.MIGRATIONS), len(db.MIGRATIONS))


def test_the_demo_sets_aside_and_gives_ikapu(app):
    from gastos import seed
    day = date(2026, 10, 28)
    with app.app_context():
        demo = db.insert("INSERT INTO users (username, password_hash, is_demo) VALUES ('demo', 'x', 1) RETURNING id")
        seed.reset_demo(demo, day)
        db.commit()
        pairs = db.query(
            """SELECT s.amount, s.date AS s_date, s.account_id AS s_wallet, i.amount AS income,
                      i.date AS i_date, i.account_id AS i_wallet, i.kind
               FROM transactions s JOIN transactions i ON i.id = s.tithe_of
               WHERE s.user_id = ?""", (demo,))
        incomes = db.query_one("SELECT COUNT(*) AS n FROM transactions WHERE user_id = ? AND kind = 'income'", (demo,))["n"]
        summary = tithes.month_summary(demo, day.replace(day=1))
    assert len(pairs) == incomes > 0  # every income has exactly one set-aside
    for p in pairs:
        assert p["kind"] == "income" and p["amount"] == tithes.tithe_amount(p["income"])
        assert (p["s_date"], p["s_wallet"]) == (p["i_date"], p["i_wallet"])
    assert summary["given"] > 0 and summary["waiting"] >= 0
