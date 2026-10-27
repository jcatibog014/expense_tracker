"""The SQL that reads and adds up money. Every function takes the user's id,
and every query filters on it, so one user never sees another's rows.

This is the place to learn SQL aggregation: SUM, COUNT, CASE, GROUP BY,
JOIN and sub-queries. See tests/test_queries.py for the expected answers.
"""
from . import db
from .dates import add_months

# Shown in lists: the entry plus the names of its wallet(s) and category.
# LEFT JOIN keeps transfers, which have no category and a second wallet.
ENTRY_SELECT = """
    SELECT t.id, t.kind, t.amount, t.date, t.note, t.recurring_id,
           a.name AS account, ta.name AS to_account,
           c.name AS category, c.color AS color
    FROM transactions t
    JOIN accounts a ON a.id = t.account_id
    LEFT JOIN accounts ta ON ta.id = t.to_account_id
    LEFT JOIN categories c ON c.id = t.category_id
"""


def month_totals(user_id, first_day):
    """Income and spending in one month. Transfers are neither, so they are left out."""
    return db.query_one(
        """SELECT
               COALESCE(SUM(CASE WHEN kind = 'income' THEN amount END), 0) AS income,
               COALESCE(SUM(CASE WHEN kind = 'expense' THEN amount END), 0) AS spending
           FROM transactions
           WHERE user_id = ? AND date >= ? AND date < ?""",
        (user_id, first_day.isoformat(), add_months(first_day, 1).isoformat()),
    )


def recent_entries(user_id, limit=8):
    return db.query(
        ENTRY_SELECT + " WHERE t.user_id = ? ORDER BY t.date DESC, t.id DESC LIMIT ?",
        (user_id, limit),
    )


def filter_sql(user_id, filters):
    """Build the WHERE part of the entries list from the filters.

    The SQL is put together only from our own fixed pieces; everything the
    visitor typed goes into `params`, never into the SQL text.
    """
    conditions = ["t.user_id = ?"]
    params = [user_id]
    if filters["month"]:
        conditions.append("t.date >= ? AND t.date < ?")
        params += [filters["month"].isoformat(), add_months(filters["month"], 1).isoformat()]
    if filters["kind"]:
        conditions.append("t.kind = ?")
        params.append(filters["kind"])
    if filters["category_id"]:
        conditions.append("t.category_id = ?")
        params.append(filters["category_id"])
    if filters["account_id"]:
        # A transfer belongs to both of its wallets.
        conditions.append("(t.account_id = ? OR t.to_account_id = ?)")
        params += [filters["account_id"], filters["account_id"]]
    if filters["q"]:
        # In LIKE, % means "anything" and _ means "any one letter". Put a \ in
        # front of them, so a search for "50%" looks for a real percent sign.
        text = filters["q"].lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(
            "(LOWER(t.note) LIKE ? ESCAPE '\\' OR LOWER(COALESCE(c.name, '')) LIKE ? ESCAPE '\\')"
        )
        params += [f"%{text}%", f"%{text}%"]
    return " WHERE " + " AND ".join(conditions), params


def find_entries(user_id, filters, limit, offset):
    where, params = filter_sql(user_id, filters)
    return db.query(
        ENTRY_SELECT + where + " ORDER BY t.date DESC, t.id DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    )


def filtered_totals(user_id, filters):
    """How many entries match the filters, and their income and spending."""
    where, params = filter_sql(user_id, filters)
    return db.query_one(
        """SELECT COUNT(*) AS count,
                  COALESCE(SUM(CASE WHEN t.kind = 'income' THEN t.amount END), 0) AS income,
                  COALESCE(SUM(CASE WHEN t.kind = 'expense' THEN t.amount END), 0) AS spending
           FROM transactions t
           LEFT JOIN categories c ON c.id = t.category_id""" + where,
        params,
    )


def wallet_balances(user_id):
    """Every wallet with the money in it now, and how many entries use it.

    balance = opening balance
              + income into it - spending from it - transfers out of it
              + transfers into it

    The two sub-queries in brackets run once per wallet (they are
    "correlated": they use a.id from the outer query).
    """
    return db.query(
        """SELECT a.id, a.name, a.kind, a.opening_balance, a.archived,
                  a.opening_balance
                  + COALESCE((SELECT SUM(CASE WHEN t.kind = 'income' THEN t.amount ELSE -t.amount END)
                              FROM transactions t WHERE t.account_id = a.id), 0)
                  + COALESCE((SELECT SUM(t.amount)
                              FROM transactions t WHERE t.to_account_id = a.id), 0) AS balance,
                  (SELECT COUNT(*) FROM transactions t
                   WHERE t.account_id = a.id OR t.to_account_id = a.id) AS uses
           FROM accounts a
           WHERE a.user_id = ?
           ORDER BY a.archived, a.id""",
        (user_id,),
    )


def category_usage(user_id):
    """Every category with how many entries use it and their total."""
    return db.query(
        """SELECT c.id, c.name, c.kind, c.color, c.archived,
                  COUNT(t.id) AS uses,
                  COALESCE(SUM(t.amount), 0) AS total
           FROM categories c
           LEFT JOIN transactions t ON t.category_id = c.id
           WHERE c.user_id = ?
           GROUP BY c.id, c.name, c.kind, c.color, c.archived
           ORDER BY c.archived, c.kind, c.name""",
        (user_id,),
    )
