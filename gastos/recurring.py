"""Repeating entries: salary, rent, Netflix... added by themselves every month.

due_dates() and next_due() are pure date maths (tests/test_recurring.py).
post_due() writes the entries that are due. It runs at the start of each
request of a logged-in user, so missed months are filled in whenever you
come back, even after a long break.
"""
from datetime import date, timedelta

from . import db
from .dates import add_months, day_in_month


def due_dates(day_of_month, start, end, until, after=None):
    """Every date the item is due, from `start` up to `until` (both included).

    `end` (or None) is the last allowed date. `after` (or None) skips dates
    up to and including it: those were added already. A day that a month
    doesn't have moves to its last day (31 -> Feb 28).
    """
    limit = min(until, end) if end else until
    dates = []
    month = start.replace(day=1)
    while month <= limit:
        day = day_in_month(month.year, month.month, day_of_month)
        if start <= day <= limit and (after is None or day > after):
            dates.append(day)
        month = add_months(month, 1)
    return dates


def next_due(day_of_month, start, end, after):
    """The first due date after `after`, or None if the item has ended."""
    first = max(start, after + timedelta(days=1))
    # Two months ahead is always enough to find the next one.
    dates = due_dates(day_of_month, first, end, add_months(first.replace(day=1), 2))
    return dates[0] if dates else None


def parse(text):
    return date.fromisoformat(text) if text else None


def next_date(item, today):
    """When a recurring row is next added: after today and after what was added already."""
    start = parse(item["start_date"])
    added_until = parse(item["posted_until"]) or start - timedelta(days=1)
    return next_due(item["day_of_month"], start, parse(item["end_date"]), max(added_until, today))


def post_due(user_id, today):
    """Add the entries that are due up to today. Returns the names added.

    UNIQUE (recurring_id, date) with ON CONFLICT DO NOTHING means that two
    requests at the same moment can't add the same entry twice.
    The caller commits.
    """
    items = db.query(
        """SELECT r.*, c.name AS category
           FROM recurring r JOIN categories c ON c.id = r.category_id
           WHERE r.user_id = ? AND r.start_date <= ?
             AND (r.posted_until IS NULL OR r.posted_until < ?)""",
        (user_id, today.isoformat(), today.isoformat()),
    )
    added = []
    for item in items:
        dates = due_dates(item["day_of_month"], parse(item["start_date"]), parse(item["end_date"]),
                          today, after=parse(item["posted_until"]))
        for day in dates:
            db.execute(
                """INSERT INTO transactions
                       (user_id, kind, amount, date, account_id, category_id, note, recurring_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (recurring_id, date) DO NOTHING""",
                (user_id, item["kind"], item["amount"], day.isoformat(), item["account_id"],
                 item["category_id"], item["note"], item["id"]),
            )
            added.append(item["note"] or item["category"])
        db.execute("UPDATE recurring SET posted_until = ? WHERE id = ?", (today.isoformat(), item["id"]))
    return added


def upcoming(user_id, today, days=14):
    """Items due in the next `days` days, soonest first: [(date, item)]."""
    items = db.query(
        """SELECT r.*, c.name AS category, c.color, a.name AS account
           FROM recurring r
           JOIN categories c ON c.id = r.category_id
           JOIN accounts a ON a.id = r.account_id
           WHERE r.user_id = ?""",
        (user_id,),
    )
    result = []
    for item in items:
        day = next_date(item, today)
        if day and day <= today + timedelta(days=days):
            result.append((day, item))
    return sorted(result, key=lambda pair: (pair[0], pair[1]["id"]))
