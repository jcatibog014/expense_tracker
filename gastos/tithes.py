"""Ikapu (the tithe): 10% of every income is set aside for the Lord.

How it works:
- Every user has one Ikapu wallet (accounts.is_ikapu = 1), like an envelope.
- When an income is saved, sync() adds a transfer of 10% from the income's
  wallet into the Ikapu wallet: the "set-aside". Its tithe_of column points
  at the income, so editing the income changes it, and deleting the income
  deletes it (ON DELETE CASCADE).
- When you give, you write down spending from the Ikapu wallet. What is
  still in the wallet is what is waiting to be given.
Transfers are neither income nor spending, so setting money aside doesn't
change the month's totals; giving it does (it's spending).
"""
from . import db
from .dates import add_months

TITHE_PERCENT = 10
CATEGORY_NAME = "Ikapu"
SET_ASIDE_NOTE = "Ikapu (10% set aside)"


def tithe_amount(income):
    """10% of an income in centavos, rounded to the nearest centavo (half up)."""
    return (income * TITHE_PERCENT + 50) // 100


def ikapu_wallet(user_id):
    return db.query_one("SELECT * FROM accounts WHERE user_id = ? AND is_ikapu = 1", (user_id,))


def ikapu_category(user_id):
    return db.query_one(
        "SELECT * FROM categories WHERE user_id = ? AND kind = 'expense' AND name = ?",
        (user_id, CATEGORY_NAME),
    )


def sync(user_id, transaction_id):
    """Make the set-aside of this transaction match it. The caller commits.

    An income (not paid into the Ikapu wallet itself) gets one set-aside.
    Anything else (spending, a transfer, or income into the Ikapu wallet)
    gets none, so an old one is removed. Returns the set-aside's id or None.
    """
    wallet = ikapu_wallet(user_id)
    t = db.query_one("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (transaction_id, user_id))
    existing = db.query_one("SELECT id FROM transactions WHERE tithe_of = ? AND user_id = ?",
                            (transaction_id, user_id))
    wanted = (t is not None and wallet is not None and t["kind"] == "income"
              and t["account_id"] != wallet["id"])
    if not wanted:
        if existing:
            db.execute("DELETE FROM transactions WHERE id = ?", (existing["id"],))
        return None

    values = (tithe_amount(t["amount"]), t["date"], t["account_id"], wallet["id"])
    if existing:
        db.execute(
            "UPDATE transactions SET amount = ?, date = ?, account_id = ?, to_account_id = ? WHERE id = ?",
            (*values, existing["id"]),
        )
        return existing["id"]
    return db.insert(
        """INSERT INTO transactions (user_id, kind, amount, date, account_id, to_account_id, note, tithe_of)
           VALUES (?, 'transfer', ?, ?, ?, ?, ?, ?) RETURNING id""",
        (user_id, *values, SET_ASIDE_NOTE, transaction_id),
    )


def missing(user_id, first_day):
    """Income in one month that has no set-aside yet (saved before ikapu existed)."""
    wallet = ikapu_wallet(user_id)
    if wallet is None:
        return []
    # LEFT JOIN + "IS NULL" finds rows with no match: incomes nobody points at.
    return db.query(
        """SELECT i.id, i.amount
           FROM transactions i
           LEFT JOIN transactions s ON s.tithe_of = i.id
           WHERE i.user_id = ? AND i.kind = 'income' AND i.account_id <> ?
             AND i.date >= ? AND i.date < ? AND s.id IS NULL""",
        (user_id, wallet["id"], first_day.isoformat(), add_months(first_day, 1).isoformat()),
    )


def catch_up(user_id, first_day):
    """Set aside ikapu for the month's income that has none. Returns how many."""
    rows = missing(user_id, first_day)
    for row in rows:
        sync(user_id, row["id"])
    return len(rows)


def month_summary(user_id, first_day):
    """Set aside and given in one month, and what's waiting in the Ikapu wallet now."""
    wallet = ikapu_wallet(user_id)
    if wallet is None:
        return None
    start, end = first_day.isoformat(), add_months(first_day, 1).isoformat()
    totals = db.query_one(
        """SELECT
               COALESCE(SUM(CASE WHEN kind = 'transfer' AND to_account_id = ? THEN amount END), 0) AS set_aside,
               COALESCE(SUM(CASE WHEN kind = 'expense' AND account_id = ? THEN amount END), 0) AS given
           FROM transactions
           WHERE user_id = ? AND date >= ? AND date < ?""",
        (wallet["id"], wallet["id"], user_id, start, end),
    )
    # The wallet's balance: everything that went in, minus everything that came out.
    moved = db.query_one(
        """SELECT COALESCE(SUM(CASE WHEN to_account_id = ? THEN amount
                                    WHEN account_id = ? AND kind = 'income' THEN amount
                                    WHEN account_id = ? THEN -amount END), 0) AS moved
           FROM transactions
           WHERE user_id = ? AND (account_id = ? OR to_account_id = ?)""",
        (wallet["id"], wallet["id"], wallet["id"], user_id, wallet["id"], wallet["id"]),
    )["moved"]
    waiting = wallet["opening_balance"] + moved
    return {"wallet": wallet, "set_aside": totals["set_aside"], "given": totals["given"], "waiting": waiting}
