"""Budgets: a spending limit per category per month (?month=2026-10)."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import charts, db, queries
from ..auth import login_required
from ..dates import add_months, month_label, parse_month, today
from ..money import amount_input
from ..validation import validate_budgets

bp = Blueprint("budgets", __name__, url_prefix="/budgets")


def chosen_month():
    return parse_month(request.values.get("month")) or today().replace(day=1)


def with_status(rows):
    """Add the status of each row that has a budget."""
    return [{**row, **(charts.budget_status(row["budget"], row["spent"]) if row["budget"] else {})}
            for row in rows]


@bp.route("", methods=["GET", "POST"])
@login_required
def index():
    user_id = g.user["id"]
    first = chosen_month()
    month = first.strftime("%Y-%m")
    rows = queries.budget_rows(user_id, first)
    errors = {}

    if request.method == "POST":
        data, errors = validate_budgets(request.form, [row["id"] for row in rows])
        if not errors:
            for category_id, amount in data.items():
                queries.save_budget(user_id, category_id, month, amount)
            db.commit()
            flash(f"Saved the budgets for {month_label(first)}.")
            return redirect(url_for("budgets.index", month=month))

    values = request.form if errors else {
        f"budget-{row['id']}": amount_input(row["budget"]) if row["budget"] else "" for row in rows
    }
    budgeted = [row for row in rows if row["budget"]]
    previous = add_months(first, -1)
    return render_template(
        "budgets.html",
        month=first,
        month_title=month_label(first),
        rows=with_status(rows),
        values=values,
        errors=errors,
        total_budget=sum(row["budget"] for row in budgeted),
        total_spent=sum(row["spent"] for row in budgeted),
        previous_name=previous.strftime("%B"),
        previous_month=url_for("budgets.index", month=previous.strftime("%Y-%m")),
        next_month=url_for("budgets.index", month=add_months(first, 1).strftime("%Y-%m")),
    ), 400 if errors else 200


@bp.post("/copy")
@login_required
def copy():
    """Copy last month's budgets into this month."""
    first = chosen_month()
    previous = add_months(first, -1)
    added = queries.copy_budgets(g.user["id"], previous.strftime("%Y-%m"), first.strftime("%Y-%m"))
    db.commit()
    if added:
        flash(f"Copied {added} budget{'' if added == 1 else 's'} from {previous:%B}.")
    else:
        flash(f"Nothing to copy: {previous:%B} has no budgets that {first:%B} doesn't have.")
    return redirect(url_for("budgets.index", month=first.strftime("%Y-%m")))
