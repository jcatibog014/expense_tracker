"""The home page. (Stage 3 turns it into the dashboard with charts.)"""
from flask import Blueprint, g, render_template

from .. import queries
from ..auth import login_required
from ..dates import month_label, today

bp = Blueprint("main", __name__)


@bp.get("/")
@login_required
def home():
    first = today().replace(day=1)
    totals = queries.month_totals(g.user["id"], first)
    return render_template(
        "home.html",
        month=month_label(first),
        income=totals["income"],
        spending=totals["spending"],
        recent=queries.recent_entries(g.user["id"]),
    )
