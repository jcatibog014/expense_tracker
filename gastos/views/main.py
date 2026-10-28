"""The dashboard: one month at a time (?month=2026-10), this month by default."""
from datetime import timedelta

from flask import Blueprint, g, redirect, render_template, request, url_for

from .. import charts, queries, recurring, tithes
from ..auth import login_required
from ..dates import add_months, day_in_month, month_label, parse_month, today
from .ikapu import give_link

bp = Blueprint("main", __name__)

HISTORY_MONTHS = 12


@bp.get("/healthz")
def health():
    """Render calls this to check the site is up. No login and no database, so it's quick."""
    return {"status": "ok"}


@bp.get("/entries")
@bp.get("/entries/<path:rest>")
def old_entries_address(rest=""):
    """The Transactions page used to be called Entries. Old links and bookmarks still work."""
    query = request.query_string.decode()
    return redirect(f"/transactions{'/' + rest if rest else ''}{'?' + query if query else ''}", code=301)


@bp.get("/")
@login_required
def home():
    user_id = g.user["id"]
    now = today()
    first = parse_month(request.args.get("month")) or now.replace(day=1)
    previous = add_months(first, -1)

    is_this_month = first == now.replace(day=1)
    this_month = queries.month_totals(user_id, first)
    if is_this_month:
        # The month isn't over, so compare with the same days of last month:
        # October 1-28 with September 1-28, not with all of September.
        same_day = day_in_month(previous.year, previous.month, now.day)
        last_month = queries.month_totals(user_id, previous, until=same_day + timedelta(days=1))
        compare_name = f"{previous:%B} 1–{same_day.day}"
    else:
        last_month = queries.month_totals(user_id, previous)
        compare_name = f"{previous:%B}"
    wallets = [w for w in queries.wallet_balances(user_id) if not w["archived"]]
    budgets = [
        {**row, **charts.budget_status(row["budget"], row["spent"])}
        for row in queries.budget_rows(user_id, first) if row["budget"]
    ]
    ikapu = tithes.month_summary(user_id, first)
    # The fullest budgets first: those are the ones to watch.
    budgets.sort(key=lambda row: (-row["percent"], row["name"]))
    history = queries.monthly_totals(user_id, add_months(first, -(HISTORY_MONTHS - 1)), HISTORY_MONTHS)

    return render_template(
        "dashboard.html",
        month=first,
        month_title=month_label(first),
        is_this_month=is_this_month,
        previous_month=url_for("main.home", month=previous.strftime("%Y-%m")),
        next_month=url_for("main.home", month=add_months(first, 1).strftime("%Y-%m")),
        income=this_month["income"],
        spending=this_month["spending"],
        left_over=this_month["income"] - this_month["spending"],
        income_change=charts.change(this_month["income"], last_month["income"]),
        spending_change=charts.change(this_month["spending"], last_month["spending"]),
        kept=charts.kept_percent(this_month["income"], this_month["spending"]),
        last_month_name=previous.strftime("%B"),
        compare_name=compare_name,
        wallets=wallets,
        wallet_total=sum(w["balance"] for w in wallets),
        categories=charts.category_bars(queries.spending_by_category(user_id, first)),
        daily=charts.running_lines(
            queries.running_spending(user_id, first),
            queries.running_spending(user_id, previous),
            first, now,
        ),
        history=charts.month_columns(history),
        history_rows=history,
        entries=queries.month_entries(user_id, first),
        budgets=budgets,
        upcoming=recurring.upcoming(user_id, now),
        ikapu=ikapu,
        ikapu_give=give_link(ikapu, back=request.full_path.rstrip('?')) if ikapu else None,
    )
