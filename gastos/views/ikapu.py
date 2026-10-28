"""The Ikapu page (under Settings): how ikapu works, this month, and catching up."""
from flask import Blueprint, flash, g, redirect, render_template, url_for

from .. import db, tithes
from ..auth import login_required
from ..dates import month_label, today
from ..money import amount_input

bp = Blueprint("ikapu", __name__, url_prefix="/ikapu")


def give_link(summary, back=None):
    """The "Give ikapu" button: a new spending from the Ikapu wallet, filled in."""
    category = tithes.ikapu_category(g.user["id"])
    return url_for(
        "transactions.new", kind="expense", account=summary["wallet"]["id"],
        category=category["id"] if category else None,
        amount=amount_input(summary["waiting"]) if summary["waiting"] > 0 else None,
        note="Ikapu", back=back,
    )


@bp.get("")
@login_required
def index():
    first = today().replace(day=1)
    summary = tithes.month_summary(g.user["id"], first)
    missing = tithes.missing(g.user["id"], first)
    return render_template(
        "ikapu.html",
        summary=summary,
        month_name=first.strftime("%B"),
        month_title=month_label(first),
        missing_count=len(missing),
        missing_total=sum(tithes.tithe_amount(row["amount"]) for row in missing),
        give_link=give_link(summary, back=url_for("ikapu.index")) if summary else None,
        percent=tithes.TITHE_PERCENT,
    )


@bp.post("/catch-up")
@login_required
def catch_up():
    """Set aside ikapu for this month's income that came before ikapu existed."""
    first = today().replace(day=1)
    count = tithes.catch_up(g.user["id"], first)
    db.commit()
    if count:
        flash(f"Set aside ikapu for {count} income{'' if count == 1 else 's'} in {first:%B}.")
    else:
        flash(f"Every income in {first:%B} already has its ikapu.")
    return redirect(url_for("ikapu.index"))
