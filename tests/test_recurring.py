"""Repeating entries: the date maths, posting them, and the pages."""
from datetime import date

from gastos import db, recurring
from gastos.dates import today

from .conftest import log_in_as, names_to_ids, post


def test_due_dates_move_day_31_to_the_last_day():
    dates = recurring.due_dates(31, date(2026, 1, 1), None, date(2026, 4, 30))
    assert dates == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    assert recurring.due_dates(31, date(2028, 2, 1), None, date(2028, 2, 29)) == [date(2028, 2, 29)]


def test_due_dates_respect_start_end_and_after():
    # Starts after the 5th of January, so January's 5th is skipped.
    assert recurring.due_dates(5, date(2026, 1, 10), None, date(2026, 3, 31)) == [date(2026, 2, 5), date(2026, 3, 5)]
    # Ends on Feb 20.
    assert recurring.due_dates(5, date(2026, 1, 1), date(2026, 2, 20), date(2026, 12, 31)) == [date(2026, 1, 5), date(2026, 2, 5)]
    # Already added up to Feb 5.
    assert recurring.due_dates(5, date(2026, 1, 1), None, date(2026, 3, 31), after=date(2026, 2, 5)) == [date(2026, 3, 5)]
    # Up to today, including today.
    assert recurring.due_dates(28, date(2026, 10, 1), None, date(2026, 10, 28)) == [date(2026, 10, 28)]


def test_next_due():
    assert recurring.next_due(15, date(2026, 1, 1), None, date(2026, 10, 28)) == date(2026, 11, 15)
    assert recurring.next_due(31, date(2026, 1, 1), None, date(2026, 2, 1)) == date(2026, 2, 28)
    assert recurring.next_due(15, date(2026, 1, 1), date(2026, 10, 31), date(2026, 10, 28)) is None
    # A start date in the future: the first date is on or after the start.
    assert recurring.next_due(1, date(2027, 3, 1), None, date(2026, 10, 28)) == date(2027, 3, 1)


def add_item(app, user_id, note="Netflix", amount=549_00, day=20, start="2026-07-01", end=None,
             kind="expense", account="GCash", category="Fun", posted_until=None):
    with app.app_context():
        accounts, categories = names_to_ids(user_id)
        item_id = db.insert(
            """INSERT INTO recurring (user_id, kind, amount, day_of_month, start_date, end_date,
                                      account_id, category_id, note, posted_until)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (user_id, kind, amount, day, start, end, accounts[account], categories[category], note, posted_until),
        )
        db.commit()
        return item_id


def entry_dates(app, item_id):
    with app.app_context():
        return [r["date"] for r in db.query(
            "SELECT date FROM transactions WHERE recurring_id = ? ORDER BY date", (item_id,))]


def test_post_due_adds_missed_months_once(app, owner_id):
    item_id = add_item(app, owner_id)
    with app.app_context():
        added = recurring.post_due(owner_id, date(2026, 10, 28))
        db.commit()
        assert added == ["Netflix"] * 4
        assert recurring.post_due(owner_id, date(2026, 10, 28)) == []  # nothing new
    assert entry_dates(app, item_id) == ["2026-07-20", "2026-08-20", "2026-09-20", "2026-10-20"]
    with app.app_context():
        row = db.query_one("SELECT * FROM transactions WHERE recurring_id = ? LIMIT 1", (item_id,))
        assert (row["kind"], row["amount"], row["note"]) == ("expense", 549_00, "Netflix")


def test_a_deleted_entry_is_not_added_again(app, owner_id):
    item_id = add_item(app, owner_id)
    with app.app_context():
        recurring.post_due(owner_id, date(2026, 10, 28))
        db.execute("DELETE FROM transactions WHERE recurring_id = ? AND date = '2026-09-20'", (item_id,))
        db.commit()
        recurring.post_due(owner_id, date(2026, 10, 29))
        recurring.post_due(owner_id, date(2026, 11, 20))
        db.commit()
    assert entry_dates(app, item_id) == ["2026-07-20", "2026-08-20", "2026-10-20", "2026-11-20"]


def test_post_due_never_adds_twice_even_without_posted_until(app, owner_id):
    item_id = add_item(app, owner_id)
    with app.app_context():
        recurring.post_due(owner_id, date(2026, 10, 28))
        # As if two requests ran at once: posted_until isn't saved yet.
        db.execute("UPDATE recurring SET posted_until = NULL WHERE id = ?", (item_id,))
        recurring.post_due(owner_id, date(2026, 10, 28))
        db.commit()
    assert len(entry_dates(app, item_id)) == 4  # UNIQUE (recurring_id, date) + ON CONFLICT DO NOTHING


def test_post_due_only_touches_that_user(app, owner_id, other_id):
    add_item(app, other_id)
    with app.app_context():
        assert recurring.post_due(owner_id, date(2026, 10, 28)) == []


def test_upcoming(app, owner_id):
    add_item(app, owner_id, note="Netflix", day=5, posted_until="2026-10-28")
    add_item(app, owner_id, note="Spotify", day=1, posted_until="2026-10-28")
    add_item(app, owner_id, note="Gym", day=25, posted_until="2026-10-28")  # too far
    add_item(app, owner_id, note="Old", day=2, end="2026-10-01", posted_until="2026-10-28")  # ended
    with app.app_context():
        soon = recurring.upcoming(owner_id, date(2026, 10, 28))
    assert [(day, item["note"]) for day, item in soon] == [(date(2026, 11, 1), "Spotify"), (date(2026, 11, 5), "Netflix")]


def test_visiting_any_page_adds_due_entries(owner_client, app, owner_id):
    first = today().replace(day=1)
    item_id = add_item(app, owner_id, note="Rent", day=1, start=first.isoformat(), category="Rent", account="Bank")
    page = owner_client.get("/entries", follow_redirects=True).get_data(as_text=True)
    assert "Added 1 repeating entry: Rent." in page
    assert entry_dates(app, item_id) == [first.isoformat()]
    assert "Repeats" in owner_client.get("/entries").get_data(as_text=True)


def test_add_a_repeating_entry(owner_client, app, owner_id):
    accounts, categories = names_to_ids_for(app, owner_id)
    response = post(owner_client, "/repeating/new", {
        "kind": "income", "note": "Sweldo", "amount": "18,500", "day_of_month": "31",
        "start_date": "2026-01-01", "end_date": "", "account_id": accounts["Bank"],
        "category_id": categories["Salary"],
    })
    assert response.headers["Location"] == "/repeating"
    page = owner_client.get("/repeating", follow_redirects=True).get_data(as_text=True)
    # Past months were added straight away, on the last day of each month.
    assert "Sweldo" in page and "added" in page
    with app.app_context():
        dates = [r["date"] for r in db.query("SELECT date FROM transactions WHERE note = 'Sweldo' ORDER BY date")]
    assert dates[:2] == ["2026-01-31", "2026-02-28"]


def names_to_ids_for(app, user_id):
    with app.app_context():
        return names_to_ids(user_id)


def test_repeating_form_errors(owner_client):
    response = post(owner_client, "/repeating/new", {
        "kind": "expense", "note": "", "amount": "x", "day_of_month": "32",
        "start_date": "2026-05-01", "end_date": "2026-04-01",
    })
    page = response.get_data(as_text=True)
    assert response.status_code == 400
    for message in ("Give it a name", "Type an amount", "Choose a day from 1 to 31",
                    "can&#39;t be before the first date", "Choose a wallet", "Choose a category"):
        assert message in page


def test_edit_and_delete_keep_the_added_entries(owner_client, app, owner_id):
    item_id = add_item(app, owner_id, posted_until="2026-10-28")
    with app.app_context():
        recurring.post_due(owner_id, date(2026, 10, 28))
        db.commit()
    accounts, categories = names_to_ids_for(app, owner_id)
    post(owner_client, f"/repeating/{item_id}/edit", {
        "kind": "expense", "note": "Netflix Premium", "amount": "649", "day_of_month": "20",
        "start_date": "2026-07-01", "account_id": accounts["GCash"], "category_id": categories["Fun"],
    })
    with app.app_context():
        assert db.query_one("SELECT note, amount FROM recurring WHERE id = ?", (item_id,)) == {
            "note": "Netflix Premium", "amount": 649_00}
    add_entry_id = add_item(app, owner_id, note="Gym", start="2026-10-01", posted_until=None)
    with app.app_context():
        recurring.post_due(owner_id, date(2026, 10, 28))
        db.commit()
    post(owner_client, f"/repeating/{add_entry_id}/delete")
    with app.app_context():
        assert db.query_one("SELECT COUNT(*) AS n FROM recurring WHERE id = ?", (add_entry_id,))["n"] == 0
        # The added entry stays, without its link.
        row = db.query_one("SELECT recurring_id FROM transactions WHERE note = 'Gym'")
        assert row == {"recurring_id": None}


def test_nobody_can_touch_another_users_repeating_entry(client, app, owner_id, other_id):
    item_id = add_item(app, owner_id, note="Owner subscription", posted_until="2026-10-28")
    log_in_as(client, other_id)
    assert client.get(f"/repeating/{item_id}/edit").status_code == 404
    assert post(client, f"/repeating/{item_id}/delete").status_code == 404
    assert "Owner subscription" not in client.get("/repeating").get_data(as_text=True)
