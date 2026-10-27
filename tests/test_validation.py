from datetime import date

from gastos import validation

TODAY = date(2026, 10, 28)
ACCOUNTS = {1: {"id": 1, "name": "Cash"}, 2: {"id": 2, "name": "GCash"}}
CATEGORIES = {10: {"id": 10, "kind": "expense"}, 20: {"id": 20, "kind": "income"}}


def check(form):
    return validation.validate_transaction(form, ACCOUNTS, CATEGORIES, TODAY)


def test_good_expense():
    data, errors = check({"kind": "expense", "amount": "1,234.50", "date": "2026-10-28",
                          "account_id": "1", "category_id": "10", "note": "  Puregold   haul "})
    assert errors == {}
    assert data == {"kind": "expense", "amount": 123450, "date": "2026-10-28", "account_id": 1,
                    "to_account_id": None, "category_id": 10, "note": "Puregold haul"}


def test_good_transfer_ignores_the_category():
    data, errors = check({"kind": "transfer", "amount": "500", "date": "2026-10-01",
                          "account_id": "1", "to_account_id": "2", "category_id": "10"})
    assert errors == {}
    assert data["to_account_id"] == 2 and data["category_id"] is None


def test_unknown_kind():
    assert check({"kind": "gift"})[1] == {"kind": "Choose income, spending or transfer."}


def test_every_field_wrong():
    data, errors = check({"kind": "income", "amount": "0", "date": "yesterday",
                          "account_id": "99", "category_id": "10", "note": "x" * 201})
    assert data is None
    assert set(errors) == {"amount", "date", "account_id", "category_id", "note"}


def test_category_must_match_the_kind():
    errors = check({"kind": "income", "amount": "5", "date": "2026-10-01", "account_id": "1", "category_id": "10"})[1]
    assert "category_id" in errors


def test_wallets_and_categories_of_others_are_refused():
    # 3 and 30 aren't in this user's lists, so they might be someone else's.
    errors = check({"kind": "expense", "amount": "5", "date": "2026-10-01", "account_id": "3", "category_id": "30"})[1]
    assert set(errors) == {"account_id", "category_id"}


def test_transfer_needs_two_different_wallets():
    errors = check({"kind": "transfer", "amount": "5", "date": "2026-10-01", "account_id": "1", "to_account_id": "1"})[1]
    assert errors == {"to_account_id": "Choose two different wallets."}


def test_dates_must_be_reasonable():
    for day in ("1999-12-31", "2027-10-30"):
        errors = check({"kind": "expense", "amount": "5", "date": day, "account_id": "1", "category_id": "10"})[1]
        assert "date" in errors
    errors = check({"kind": "expense", "amount": "5", "date": "2027-10-28", "account_id": "1", "category_id": "10"})[1]
    assert errors == {}


def test_parse_id():
    assert validation.parse_id("12") == 12
    for text in ("", None, "-1", "1.5", "abc", "1" * 12):
        assert validation.parse_id(text) is None


def test_account():
    data, errors = validation.validate_account({"name": " BDO ", "kind": "bank", "opening_balance": "-1,000"}, set())
    assert errors == {} and data == {"name": "BDO", "kind": "bank", "opening_balance": -100000}
    data, errors = validation.validate_account({"name": "Cash", "kind": "bank"}, set())
    assert data["opening_balance"] == 0  # empty means zero


def test_account_errors():
    data, errors = validation.validate_account({"name": "gcash", "kind": "piggy", "opening_balance": "lots"}, {"gcash"})
    assert set(errors) == {"name", "kind", "opening_balance"}
    assert validation.validate_account({"name": "", "kind": "cash"}, set())[1] == {"name": "Type a name."}


def test_category():
    taken = {"expense": {"food"}, "income": set()}
    data, errors = validation.validate_category({"name": "Pets", "kind": "expense", "color": "violet"}, taken)
    assert data == {"name": "Pets", "kind": "expense", "color": "violet"}
    # The same name is fine for the other kind.
    assert validation.validate_category({"name": "Food", "kind": "income", "color": "blue"}, taken)[1] == {}
    errors = validation.validate_category({"name": "FOOD", "kind": "expense", "color": "#ff0000"}, taken)[1]
    assert set(errors) == {"name", "color"}


def test_category_kind_is_fixed_when_editing():
    taken = {"expense": set(), "income": set()}
    data, _ = validation.validate_category({"name": "Tips", "kind": "expense", "color": "gray"}, taken, kind="income")
    assert data["kind"] == "income"


def test_filters_default_to_this_month():
    filters = validation.read_filters({}, TODAY)
    assert filters == {"month": date(2026, 10, 1), "kind": None, "category_id": None,
                       "account_id": None, "q": "", "page": 1}


def test_filters_read_the_url():
    filters = validation.read_filters(
        {"month": "all", "kind": "income", "category": "4", "account": "x", "q": " jolli ", "page": "3"}, TODAY)
    assert filters == {"month": None, "kind": "income", "category_id": 4,
                       "account_id": None, "q": "jolli", "page": 3}
    assert validation.read_filters({"month": "nonsense", "kind": "gift"}, TODAY)["month"] == date(2026, 10, 1)
