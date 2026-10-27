"""The pages, one blueprint per part of the app, plus helpers they share."""
from flask import abort, g

from .. import db

# Only these names may go into the SQL text of owned_row().
OWNED_TABLES = ("transactions", "accounts", "categories", "budgets", "recurring")


def owned_row(table, row_id):
    """The row with this id, if it belongs to the logged-in user. Otherwise 404.

    We answer "not found" (and not "forbidden") for other people's rows, so
    nobody can find out which ids exist.
    """
    if table not in OWNED_TABLES:
        raise ValueError(f"unknown table {table}")
    row = db.query_one(
        f"SELECT * FROM {table} WHERE id = ? AND user_id = ?", (row_id, g.user["id"])
    )
    if row is None:
        abort(404)
    return row
