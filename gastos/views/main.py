"""The home page. (Stage 3 turns it into the dashboard with charts.)"""
from flask import Blueprint, g, render_template

from .. import db
from ..auth import login_required
from ..dates import add_months, month_label, today

bp = Blueprint("main", __name__)


@bp.get("/")
@login_required
def home():
    first = today().replace(day=1)
    # Text dates compare like dates, so "this month" is: from the 1st up to
    # (but not including) the 1st of next month.
    totals = db.query_one(
        """SELECT
               COALESCE(SUM(CASE WHEN kind = 'income' THEN amount END), 0) AS income,
               COALESCE(SUM(CASE WHEN kind = 'expense' THEN amount END), 0) AS spending
           FROM transactions
           WHERE user_id = ? AND date >= ? AND date < ?""",
        (g.user["id"], first.isoformat(), add_months(first, 1).isoformat()),
    )
    # JOIN adds the wallet and category names. LEFT JOIN keeps transfers,
    # which have no category (and only transfers have a "to" wallet).
    recent = db.query(
        """SELECT t.id, t.date, t.kind, t.amount, t.note,
                  c.name AS category, c.color, a.name AS account, ta.name AS to_account
           FROM transactions t
           JOIN accounts a ON a.id = t.account_id
           LEFT JOIN categories c ON c.id = t.category_id
           LEFT JOIN accounts ta ON ta.id = t.to_account_id
           WHERE t.user_id = ?
           ORDER BY t.date DESC, t.id DESC
           LIMIT 8""",
        (g.user["id"],),
    )
    return render_template(
        "home.html",
        month=month_label(first),
        income=totals["income"],
        spending=totals["spending"],
        recent=recent,
    )
