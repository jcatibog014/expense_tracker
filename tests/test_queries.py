"""The SQL sums, checked against entries whose totals we know exactly."""
from datetime import date

from gastos import db, queries
from gastos.validation import read_filters

from .conftest import add_entry

OCTOBER = date(2026, 10, 1)


def filters(**changes):
    result = read_filters({}, date(2026, 10, 28))
    result.update(changes)
    return result


def setup_money(app, owner_id):
    add_entry(app, owner_id, "income", 18_500_00, "2026-10-15", account="Bank", note="Sweldo")
    add_entry(app, owner_id, "expense", 150_50, "2026-10-02", note="Jollibee")
    add_entry(app, owner_id, "expense", 6_500_00, "2026-10-05", account="Bank", category="Rent")
    add_entry(app, owner_id, "transfer", 2_000_00, "2026-10-06", account="Bank", to_account="Cash", note="ATM")
    add_entry(app, owner_id, "expense", 99_00, "2026-09-30", note="Last month")
    add_entry(app, owner_id, "expense", 45_00, "2026-11-01", account="GCash", note="Next month")


def test_month_totals_leave_out_transfers_and_other_months(app, owner_id):
    setup_money(app, owner_id)
    with app.app_context():
        assert queries.month_totals(owner_id, OCTOBER) == {"income": 18_500_00, "spending": 6_650_50}
        assert queries.month_totals(owner_id, date(2026, 8, 1)) == {"income": 0, "spending": 0}


def test_wallet_balances(app, owner_id):
    setup_money(app, owner_id)
    with app.app_context():
        db.execute("UPDATE accounts SET opening_balance = 1000000 WHERE user_id = ? AND name = 'Cash'", (owner_id,))
        balances = {w["name"]: (w["balance"], w["uses"]) for w in queries.wallet_balances(owner_id)}
    assert balances == {
        # 10,000 - 150.50 - 99 + 2,000 (transfer in)
        "Cash": (11_750_50, 3),
        # 18,500 - 6,500 - 2,000 (transfer out)
        "Bank": (10_000_00, 3),
        "GCash": (-45_00, 1),
    }


def test_category_usage(app, owner_id):
    setup_money(app, owner_id)
    with app.app_context():
        rows = {r["name"]: (r["uses"], r["total"]) for r in queries.category_usage(owner_id)}
    assert rows["Food"] == (3, 150_50 + 99_00 + 45_00)
    assert rows["Rent"] == (1, 6_500_00)
    assert rows["Salary"] == (1, 18_500_00)
    assert rows["Health"] == (0, 0)


def test_find_entries_by_month_newest_first(app, owner_id):
    setup_money(app, owner_id)
    with app.app_context():
        notes = [e["note"] for e in queries.find_entries(owner_id, filters(), 50, 0)]
        assert notes == ["Sweldo", "ATM", "", "Jollibee"]
        assert queries.filtered_totals(owner_id, filters()) == {"count": 4, "income": 18_500_00, "spending": 6_650_50}
        everything = queries.find_entries(owner_id, filters(month=None), 50, 0)
        assert len(everything) == 6


def test_find_entries_filters(app, owner_id):
    setup_money(app, owner_id)
    with app.app_context():
        accounts = {r["name"]: r["id"] for r in db.query("SELECT id, name FROM accounts WHERE user_id = ?", (owner_id,))}
        rent = db.query_one("SELECT id FROM categories WHERE user_id = ? AND name = 'Rent'", (owner_id,))["id"]

        def notes(**changes):
            return sorted(e["note"] for e in queries.find_entries(owner_id, filters(month=None, **changes), 50, 0))

        assert notes(kind="income") == ["Sweldo"]
        assert notes(category_id=rent) == [""]
        # A transfer shows in both wallets.
        assert notes(account_id=accounts["Cash"]) == ["ATM", "Jollibee", "Last month"]
        assert notes(account_id=accounts["Bank"]) == ["", "ATM", "Sweldo"]
        # Search looks at the note and the category name, in any case.
        assert notes(q="JOLLI") == ["Jollibee"]
        assert notes(q="rent") == [""]


def test_search_treats_percent_and_underscore_as_letters(app, owner_id):
    add_entry(app, owner_id, "expense", 100, "2026-10-01", note="50% off")
    add_entry(app, owner_id, "expense", 100, "2026-10-01", note="500 pesos")
    add_entry(app, owner_id, "expense", 100, "2026-10-01", note="snake_case")
    add_entry(app, owner_id, "expense", 100, "2026-10-01", note="snakeXcase")
    with app.app_context():
        assert [e["note"] for e in queries.find_entries(owner_id, filters(q="50%"), 50, 0)] == ["50% off"]
        assert [e["note"] for e in queries.find_entries(owner_id, filters(q="e_c"), 50, 0)] == ["snake_case"]


def test_paging(app, owner_id):
    for day in range(1, 8):
        add_entry(app, owner_id, "expense", 100, f"2026-10-0{day}", note=str(day))
    with app.app_context():
        first = queries.find_entries(owner_id, filters(), 3, 0)
        third = queries.find_entries(owner_id, filters(), 3, 6)
    assert [e["note"] for e in first] == ["7", "6", "5"]
    assert [e["note"] for e in third] == ["1"]


def test_queries_never_mix_users(app, owner_id, other_id):
    setup_money(app, owner_id)
    with app.app_context():
        assert queries.month_totals(other_id, OCTOBER) == {"income": 0, "spending": 0}
        assert queries.find_entries(other_id, filters(month=None), 50, 0) == []
        assert queries.recent_entries(other_id) == []
        assert all(w["balance"] == 0 for w in queries.wallet_balances(other_id))
