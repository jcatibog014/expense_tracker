"""Reports: one year at a time (?year=2026), month by month and category by category."""
from datetime import date

from flask import Blueprint, g, render_template, request, url_for

from .. import charts, queries
from ..auth import login_required
from ..dates import today
from ..validation import parse_id

bp = Blueprint("reports", __name__, url_prefix="/reports")

FIRST_YEAR = 2000


@bp.get("")
@login_required
def index():
    user_id = g.user["id"]
    now = today()
    year = parse_id(request.args.get("year")) or now.year
    year = min(max(year, FIRST_YEAR), now.year + 1)

    monthly = queries.monthly_totals(user_id, date(year, 1, 1), 12)
    # The average counts the months so far (all 12 for a past year).
    months_so_far = 12 if year < now.year else (now.month if year == now.year else 0)
    income = sum(row["income"] for row in monthly)
    spending = sum(row["spending"] for row in monthly)

    grid = queries.category_month_grid(user_id, year)
    biggest_cell = max((value for row in grid for value in row["months"]), default=0)
    for row in grid:
        row["levels"] = [charts.heat_level(value, biggest_cell) for value in row["months"]]
    month_spending = [row["spending"] for row in monthly]

    return render_template(
        "reports.html",
        year=year,
        previous_year=url_for("reports.index", year=year - 1) if year > FIRST_YEAR else None,
        next_year=url_for("reports.index", year=year + 1) if year <= now.year else None,
        income=income,
        spending=spending,
        left_over=income - spending,
        kept=charts.kept_percent(income, spending),
        average_spending=charts.average(month_spending[:months_so_far]),
        months_so_far=months_so_far,
        monthly=[{**row, "kept": charts.kept_percent(row["income"], row["spending"])} for row in monthly],
        columns=charts.month_columns(monthly),
        grid=grid,
        month_spending=month_spending,
        month_names=[row["month"].strftime("%b") for row in monthly],
        biggest=queries.biggest_expenses(user_id, date(year, 1, 1), date(year + 1, 1, 1)),
        heat_levels=charts.HEAT_LEVELS,
    )
