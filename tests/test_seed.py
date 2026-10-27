from datetime import date

from gastos import db, seed


def test_new_users_get_default_wallets_and_categories(app, owner_id):
    with app.app_context():
        accounts = db.query("SELECT name FROM accounts WHERE user_id = ? ORDER BY id", (owner_id,))
        assert [a["name"] for a in accounts] == ["Cash", "GCash", "Bank"]
        count = db.query_one("SELECT COUNT(*) AS n FROM categories WHERE user_id = ?", (owner_id,))["n"]
        assert count == len(seed.DEFAULT_CATEGORIES)


def test_demo_transactions_cover_six_months_up_to_today():
    today = date(2026, 10, 28)
    rows = seed.demo_transactions(today)
    days = sorted(row[2] for row in rows)
    assert days[0] == "2026-05-01"
    assert days[-1] <= "2026-10-28"
    assert all(row[1] > 0 for row in rows)
    assert {row[0] for row in rows} == {"income", "expense", "transfer"}
    # Salary on the 15th and the last day of every month.
    salaries = [row[2] for row in rows if row[5] == "Salary"]
    assert "2026-09-15" in salaries and "2026-09-30" in salaries and "2026-02-28" not in salaries


def test_demo_transactions_are_the_same_for_the_same_day():
    assert seed.demo_transactions(date(2026, 10, 28)) == seed.demo_transactions(date(2026, 10, 28))
    assert seed.demo_transactions(date(2026, 10, 28)) != seed.demo_transactions(date(2026, 10, 29))


def test_demo_wallets_never_go_below_zero():
    for today in (date(2026, 10, 28), date(2026, 3, 1), date(2027, 1, 31)):
        balances = dict(seed.DEMO_OPENING_BALANCES)
        for kind, amount, day, account, to_account, category, note in seed.demo_transactions(today):
            balances[account] += amount if kind == "income" else -amount
            if to_account:
                balances[to_account] += amount
            assert min(balances.values()) >= 0, (today, day, balances)


def test_demo_transactions_use_known_names():
    account_names = {name for name, _ in seed.DEFAULT_ACCOUNTS}
    category_names = {name for name, _, _ in seed.DEFAULT_CATEGORIES}
    for kind, amount, day, account, to_account, category, note in seed.demo_transactions(date(2026, 10, 28)):
        assert account in account_names
        if kind == "transfer":
            assert to_account in account_names and category is None
        else:
            assert category in category_names and to_account is None


def test_reset_demo_replaces_only_that_users_data(app, owner_id):
    with app.app_context():
        demo_id = db.insert(
            "INSERT INTO users (username, password_hash, is_demo) VALUES ('demo', 'x', 1) RETURNING id"
        )
        seed.reset_demo(demo_id, date(2026, 10, 28))
        seed.reset_demo(demo_id, date(2026, 10, 28))  # twice: no duplicates
        db.commit()
        count = db.query_one("SELECT COUNT(*) AS n FROM transactions WHERE user_id = ?", (demo_id,))["n"]
        assert count == len(seed.demo_transactions(date(2026, 10, 28)))
        assert db.query_one("SELECT COUNT(*) AS n FROM accounts WHERE user_id = ?", (demo_id,))["n"] == 3
        # The owner still has their own three wallets, untouched.
        assert db.query_one("SELECT COUNT(*) AS n FROM accounts WHERE user_id = ?", (owner_id,))["n"] == 3
