"""Budgets: the SQL, the status, and the page."""
from datetime import date

from gastos import charts, db, queries, validation

from .conftest import add_entry, log_in_as, names_to_ids, post

OCTOBER = date(2026, 10, 1)


def category_ids(app, user_id):
    with app.app_context():
        return names_to_ids(user_id)[1]


def test_budget_status():
    assert charts.budget_status(1000, 500) == {"percent": 50, "left": 500, "state": "ok", "width": 50}
    assert charts.budget_status(1000, 800)["state"] == "warning"
    assert charts.budget_status(1000, 1000)["state"] == "warning"  # exactly used up: not over yet
    over = charts.budget_status(1000, 1500)
    assert over == {"percent": 150, "left": -500, "state": "over", "width": 100}


def test_validate_budgets():
    data, errors = validation.validate_budgets({"budget-1": "5,000", "budget-2": "", "budget-3": "0"}, [1, 2, 3])
    assert errors == {} and data == {1: 500000, 2: None, 3: None}
    assert validation.validate_budgets({"budget-1": "lots"}, [1])[1] == {
        "budget-1": "Type an amount, like 5000, or leave it empty."}


def test_save_copy_and_read_budgets(app, owner_id):
    cats = category_ids(app, owner_id)
    add_entry(app, owner_id, "expense", 1_200_00, "2026-10-03", category="Food")
    add_entry(app, owner_id, "expense", 300_00, "2026-09-03", category="Food")  # another month
    with app.app_context():
        queries.save_budget(owner_id, cats["Food"], "2026-09", 2_000_00)
        queries.save_budget(owner_id, cats["Fun"], "2026-09", 500_00)
        queries.save_budget(owner_id, cats["Fun"], "2026-10", 900_00)
        # Copy September into October: Food is added, Fun keeps October's 900.
        assert queries.copy_budgets(owner_id, "2026-09", "2026-10") == 1
        queries.save_budget(owner_id, cats["Food"], "2026-10", 1_000_00)  # upsert: an update
        db.commit()
        rows = {r["name"]: (r["budget"], r["spent"]) for r in queries.budget_rows(owner_id, OCTOBER)}
    assert rows["Food"] == (1_000_00, 1_200_00)
    assert rows["Fun"] == (900_00, 0)
    assert rows["Rent"] == (None, 0)  # no budget, still listed
    assert "Salary" not in rows  # income categories have no budgets


def test_removing_a_budget(app, owner_id):
    cats = category_ids(app, owner_id)
    with app.app_context():
        queries.save_budget(owner_id, cats["Food"], "2026-10", 1_000_00)
        queries.save_budget(owner_id, cats["Food"], "2026-10", None)
        assert db.query("SELECT * FROM budgets") == []


def test_archived_category_shows_only_with_a_budget(app, owner_id):
    cats = category_ids(app, owner_id)
    with app.app_context():
        db.execute("UPDATE categories SET archived = 1 WHERE id IN (?, ?)", (cats["Fun"], cats["Health"]))
        queries.save_budget(owner_id, cats["Fun"], "2026-10", 500_00)
        names = [r["name"] for r in queries.budget_rows(owner_id, OCTOBER)]
    assert "Fun" in names and "Health" not in names


def test_budgets_page_saves_the_form(owner_client, app, owner_id):
    cats = category_ids(app, owner_id)
    add_entry(app, owner_id, "expense", 4_500_00, "2026-10-03", category="Food")
    response = post(owner_client, "/budgets?month=2026-10", {
        f"budget-{cats['Food']}": "4,000", f"budget-{cats['Fun']}": "1500", "month": "2026-10",
    })
    assert response.headers["Location"] == "/budgets?month=2026-10"
    page = owner_client.get("/budgets?month=2026-10").get_data(as_text=True)
    assert "₱500.00 over" in page and "meter-over" in page
    assert "₱1,500.00 left" in page
    assert 'value="4000.00"' in page


def test_budgets_page_errors(owner_client, app, owner_id):
    cats = category_ids(app, owner_id)
    response = post(owner_client, "/budgets?month=2026-10", {f"budget-{cats['Food']}": "abc"})
    assert response.status_code == 400 and "Please fix the marked boxes" in response.get_data(as_text=True)
    with app.app_context():
        assert db.query("SELECT * FROM budgets") == []


def test_copy_button(owner_client, app, owner_id):
    cats = category_ids(app, owner_id)
    with app.app_context():
        queries.save_budget(owner_id, cats["Food"], "2026-09", 2_000_00)
        db.commit()
    response = post(owner_client, "/budgets/copy", {"month": "2026-10"})
    assert response.headers["Location"] == "/budgets?month=2026-10"
    assert "Copied 1 budget from September" in owner_client.get("/budgets?month=2026-10").get_data(as_text=True)
    post(owner_client, "/budgets/copy", {"month": "2026-10"})
    assert "Nothing to copy" in owner_client.get("/budgets?month=2026-10").get_data(as_text=True)


def test_dashboard_shows_budgets(owner_client, app, owner_id):
    cats = category_ids(app, owner_id)
    add_entry(app, owner_id, "expense", 900_00, "2026-10-03", category="Food")
    with app.app_context():
        queries.save_budget(owner_id, cats["Food"], "2026-10", 1_000_00)
        db.commit()
    page = owner_client.get("/?month=2026-10").get_data(as_text=True)
    assert "meter-warning" in page and "₱100.00 left" in page and "90%" in page


def test_budgets_are_private(client, app, owner_id, other_id):
    cats = category_ids(app, owner_id)
    log_in_as(client, other_id)
    # The other user's form only has their own categories, so the owner's id is ignored.
    post(client, "/budgets?month=2026-10", {f"budget-{cats['Food']}": "100", "month": "2026-10"})
    with app.app_context():
        assert db.query("SELECT * FROM budgets") == []
