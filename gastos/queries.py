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
    SELECT t.id, t.kind, t.amount, t.date, t.note, t.recurring_id, t.tithe_of,
           a.name AS account, ta.name AS to_account,
           c.name AS category, c.color AS color
    FROM transactions t
    JOIN accounts a ON a.id = t.account_id
    LEFT JOIN accounts ta ON ta.id = t.to_account_id
    LEFT JOIN categories c ON c.id = t.category_id
"""


def month_totals(user_id, first_day, until=None):
    """Income and spending in one month. Transfers are neither, so they are left out.

    `until` (a date, not included) stops early: for "September 1-28" pass Sep 29.
    """
    end = until or add_months(first_day, 1)
    return db.query_one(
        """SELECT
               COALESCE(SUM(CASE WHEN kind = 'income' THEN amount END), 0) AS income,
               COALESCE(SUM(CASE WHEN kind = 'expense' THEN amount END), 0) AS spending
           FROM transactions
           WHERE user_id = ? AND date >= ? AND date < ?""",
        (user_id, first_day.isoformat(), end.isoformat()),
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
        """SELECT a.id, a.name, a.kind, a.opening_balance, a.archived, a.is_ikapu,
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


# ---------- Dashboard and reports ----------

def monthly_totals(user_id, first_month, months):
    """Income and spending for `months` months from `first_month`, oldest first.

    GROUP BY puts the rows of each month together, and SUM(CASE ...) adds up
    income and spending separately in the same pass ("conditional aggregation").
    Months without entries don't come back from SQL, so Python fills them with 0.
    """
    end = add_months(first_month, months)
    rows = db.query(
        """SELECT substr(date, 1, 7) AS month,
                  COALESCE(SUM(CASE WHEN kind = 'income' THEN amount END), 0) AS income,
                  COALESCE(SUM(CASE WHEN kind = 'expense' THEN amount END), 0) AS spending
           FROM transactions
           WHERE user_id = ? AND date >= ? AND date < ?
           GROUP BY substr(date, 1, 7)
           ORDER BY month""",
        (user_id, first_month.isoformat(), end.isoformat()),
    )
    found = {row["month"]: row for row in rows}
    result = []
    for n in range(months):
        month = add_months(first_month, n)
        key = month.strftime("%Y-%m")
        row = found.get(key, {"income": 0, "spending": 0})
        result.append({"month": month, "income": row["income"], "spending": row["spending"]})
    return result


def spending_by_category(user_id, first_day):
    """Spending per category this month, with last month's next to it, biggest first.

    One pass over two months: each SUM(CASE ...) only adds the rows of its month.
    WHERE filters rows *before* grouping; HAVING filters the groups *after*:
    here it drops categories with nothing spent this month.
    """
    last_month = add_months(first_day, -1)
    this_start, next_start = first_day.isoformat(), add_months(first_day, 1).isoformat()
    return db.query(
        """SELECT c.id, c.name, c.color,
                  COALESCE(SUM(CASE WHEN t.date >= ? THEN t.amount END), 0) AS total,
                  COALESCE(SUM(CASE WHEN t.date < ? THEN t.amount END), 0) AS last_month
           FROM transactions t
           JOIN categories c ON c.id = t.category_id
           WHERE t.user_id = ? AND t.kind = 'expense' AND t.date >= ? AND t.date < ?
           GROUP BY c.id, c.name, c.color
           HAVING SUM(CASE WHEN t.date >= ? THEN t.amount ELSE 0 END) > 0
           ORDER BY total DESC, c.name""",
        (this_start, this_start, user_id, last_month.isoformat(), next_start, this_start),
    )


def running_spending(user_id, first_day):
    """Spending added up day by day in one month: [(day number, total so far)].

    SUM(SUM(amount)) OVER (ORDER BY date) is a *window function*: the inner
    SUM adds each day's spending (GROUP BY date), the outer one keeps a
    running total over the days in date order. CAST keeps it a whole number
    in Postgres, which would otherwise return a decimal.
    """
    rows = db.query(
        """SELECT date,
                  CAST(SUM(SUM(amount)) OVER (ORDER BY date) AS BIGINT) AS running
           FROM transactions
           WHERE user_id = ? AND kind = 'expense' AND date >= ? AND date < ?
           GROUP BY date
           ORDER BY date""",
        (user_id, first_day.isoformat(), add_months(first_day, 1).isoformat()),
    )
    return [(int(row["date"][8:10]), row["running"]) for row in rows]


def category_month_grid(user_id, year):
    """Spending per category per month of one year, for the reports table.

    Returns rows like {"name", "color", "months": [12 amounts], "total"},
    biggest total first. SQL groups by category AND month; Python turns
    the rows into a grid ("pivots" them).
    """
    rows = db.query(
        """SELECT c.id, c.name, c.color, substr(t.date, 6, 2) AS month, SUM(t.amount) AS total
           FROM transactions t
           JOIN categories c ON c.id = t.category_id
           WHERE t.user_id = ? AND t.kind = 'expense' AND t.date >= ? AND t.date < ?
           GROUP BY c.id, c.name, c.color, substr(t.date, 6, 2)""",
        (user_id, f"{year}-01-01", f"{year + 1}-01-01"),
    )
    grid = {}
    for row in rows:
        entry = grid.setdefault(row["id"], {"id": row["id"], "name": row["name"], "color": row["color"],
                                            "months": [0] * 12})
        entry["months"][int(row["month"]) - 1] = row["total"]
    result = list(grid.values())
    for entry in result:
        entry["total"] = sum(entry["months"])
    return sorted(result, key=lambda entry: (-entry["total"], entry["name"]))


def biggest_expenses(user_id, start, end, limit=5):
    return db.query(
        ENTRY_SELECT + """ WHERE t.user_id = ? AND t.kind = 'expense' AND t.date >= ? AND t.date < ?
                           ORDER BY t.amount DESC, t.date DESC LIMIT ?""",
        (user_id, start.isoformat(), end.isoformat(), limit),
    )


def month_entries(user_id, first_day, limit=8):
    """The latest entries of one month."""
    return db.query(
        ENTRY_SELECT + """ WHERE t.user_id = ? AND t.date >= ? AND t.date < ?
                           ORDER BY t.date DESC, t.id DESC LIMIT ?""",
        (user_id, first_day.isoformat(), add_months(first_day, 1).isoformat(), limit),
    )


# ---------- Budgets ----------

def budget_rows(user_id, first_day):
    """Every spending category with its budget for the month (or None) and what was spent.

    LEFT JOIN keeps categories without a budget. Note where "b.month = ?"
    goes: in the ON part, it only picks which budget to join; in WHERE, it
    would throw away every category without a budget for that month.
    Archived categories only show when they still have a budget.
    """
    return db.query(
        """SELECT c.id, c.name, c.color, c.archived, b.amount AS budget,
                  COALESCE(s.spent, 0) AS spent
           FROM categories c
           LEFT JOIN budgets b ON b.category_id = c.id AND b.month = ?
           LEFT JOIN (
               SELECT category_id, SUM(amount) AS spent
               FROM transactions
               WHERE user_id = ? AND kind = 'expense' AND date >= ? AND date < ?
               GROUP BY category_id
           ) s ON s.category_id = c.id
           WHERE c.user_id = ? AND c.kind = 'expense' AND (c.archived = 0 OR b.id IS NOT NULL)
           ORDER BY c.name""",
        (first_day.strftime("%Y-%m"), user_id, first_day.isoformat(),
         add_months(first_day, 1).isoformat(), user_id),
    )


def save_budget(user_id, category_id, month, amount):
    """Set a budget, or remove it when amount is None. The caller commits.

    ON CONFLICT ... DO UPDATE is an "upsert": insert a new row, or update
    the one that's already there (UNIQUE user_id, category_id, month).
    "excluded" is the row we tried to insert.
    """
    if amount is None:
        db.execute("DELETE FROM budgets WHERE user_id = ? AND category_id = ? AND month = ?",
                   (user_id, category_id, month))
        return
    db.execute(
        """INSERT INTO budgets (user_id, category_id, month, amount) VALUES (?, ?, ?, ?)
           ON CONFLICT (user_id, category_id, month) DO UPDATE SET amount = excluded.amount""",
        (user_id, category_id, month, amount),
    )


def copy_budgets(user_id, from_month, to_month):
    """Copy one month's budgets into another; budgets already there stay. The caller commits.

    INSERT ... SELECT inserts the rows a query finds, all in one statement.
    Returns how many were added.
    """
    count = "SELECT COUNT(*) AS n FROM budgets WHERE user_id = ? AND month = ?"
    before = db.query_one(count, (user_id, to_month))["n"]
    db.execute(
        # CAST tells Postgres the type of the ? (in a SELECT list it can't always guess).
        """INSERT INTO budgets (user_id, category_id, month, amount)
           SELECT user_id, category_id, CAST(? AS TEXT), amount
           FROM budgets
           WHERE user_id = ? AND month = ?
           ON CONFLICT (user_id, category_id, month) DO NOTHING""",
        (to_month, user_id, from_month),
    )
    return db.query_one(count, (user_id, to_month))["n"] - before


# ---------- CSV ----------

def export_entries(user_id, filters):
    """Every entry that matches the filters, oldest first (for a CSV file)."""
    where, params = filter_sql(user_id, filters)
    return db.query(ENTRY_SELECT + where + " ORDER BY t.date, t.id", params)


def entries_between(user_id, first_date, last_date):
    """Every entry from one date to another (both included), to find duplicates."""
    return db.query(ENTRY_SELECT + " WHERE t.user_id = ? AND t.date >= ? AND t.date <= ?",
                    (user_id, first_date, last_date))
