"""Repeating entries (the recurring table): list, add, edit, delete.

Also adds the due entries at the start of every request (post_due_entries).
"""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import db, recurring
from ..auth import login_required
from ..dates import today
from ..money import amount_input
from ..validation import CATEGORY_KINDS, validate_recurring
from . import owned_row
from .transactions import choices

bp = Blueprint("recurring", __name__, url_prefix="/repeating")


@bp.before_app_request
def post_due_entries():
    """Add repeating entries that came due since the last visit.

    It runs after auth.load_user (that blueprint is registered first),
    so g.user is known. Most of the time nothing is due and it's one quick query.
    """
    if g.get("user") is None or request.endpoint in (None, "static"):
        return
    added = recurring.post_due(g.user["id"], today())
    if added:
        db.commit()
        names = ", ".join(sorted(set(added)))
        flash(f"Added {len(added)} repeating entr{'y' if len(added) == 1 else 'ies'}: {names}.")


def render_form(kind, values, errors, accounts, categories, item=None):
    return render_template(
        "repeating_form.html",
        kind=kind,
        kinds=CATEGORY_KINDS,
        values=values,
        errors=errors,
        item=item,
        wallet_options=[(a["id"], a["name"]) for a in accounts.values()],
        category_options=[(c["id"], c["name"]) for c in categories.values() if c["kind"] == kind],
        day_options=[(day, str(day)) for day in range(1, 32)],
    ), 400 if errors else 200


def save_values(data):
    return (data["kind"], data["amount"], data["day_of_month"], data["start_date"], data["end_date"],
            data["account_id"], data["category_id"], data["note"])


@bp.get("")
@login_required
def index():
    user_id = g.user["id"]
    now = today()
    items = db.query(
        """SELECT r.*, c.name AS category, c.color, a.name AS account,
                  (SELECT COUNT(*) FROM transactions t WHERE t.recurring_id = r.id) AS added
           FROM recurring r
           JOIN categories c ON c.id = r.category_id
           JOIN accounts a ON a.id = r.account_id
           WHERE r.user_id = ?
           ORDER BY r.kind DESC, r.day_of_month, r.note""",
        (user_id,),
    )
    for item in items:
        item["next"] = recurring.next_date(item, now)  # None: it has ended
    # About how much comes in and goes out each month (items that haven't ended).
    monthly = {
        kind: sum(i["amount"] for i in items if i["kind"] == kind and i["next"]) for kind in CATEGORY_KINDS
    }
    return render_template("repeating.html", items=items, monthly=monthly)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    user_id = g.user["id"]
    accounts, categories = choices(user_id)
    if not accounts:
        flash("Add a wallet first.")
        return redirect(url_for("wallets.new"))
    if request.method == "POST":
        data, errors = validate_recurring(request.form, accounts, categories, today())
        kind = request.form.get("kind") if request.form.get("kind") in CATEGORY_KINDS else "expense"
        if errors:
            return render_form(kind, request.form, errors, accounts, categories)
        db.execute(
            """INSERT INTO recurring
                   (user_id, kind, amount, day_of_month, start_date, end_date, account_id, category_id, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, *save_values(data)),
        )
        db.commit()
        flash(f"Saved {data['note']}. It will be added on day {data['day_of_month']} of every month.")
        return redirect(url_for("recurring.index"))

    kind = request.args.get("kind") if request.args.get("kind") in CATEGORY_KINDS else "expense"
    now = today()
    values = {"day_of_month": str(now.day), "start_date": now.isoformat(),
              "account_id": str(next(iter(accounts)))}
    return render_form(kind, values, {}, accounts, categories)


@bp.route("/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit(item_id):
    item = owned_row("recurring", item_id)
    accounts, categories = choices(g.user["id"], {**item, "to_account_id": None})
    if request.method == "POST":
        data, errors = validate_recurring(request.form, accounts, categories, today())
        kind = request.form.get("kind") if request.form.get("kind") in CATEGORY_KINDS else item["kind"]
        if errors:
            return render_form(kind, request.form, errors, accounts, categories, item)
        # Entries added already keep their old amount; the change counts from now on.
        db.execute(
            """UPDATE recurring
               SET kind = ?, amount = ?, day_of_month = ?, start_date = ?, end_date = ?,
                   account_id = ?, category_id = ?, note = ?
               WHERE id = ? AND user_id = ?""",
            (*save_values(data), item_id, g.user["id"]),
        )
        db.commit()
        flash(f"Saved {data['note']}.")
        return redirect(url_for("recurring.index"))

    kind = request.args.get("kind") if request.args.get("kind") in CATEGORY_KINDS else item["kind"]
    values = {
        "amount": amount_input(item["amount"]),
        "day_of_month": str(item["day_of_month"]),
        "start_date": item["start_date"],
        "end_date": item["end_date"] or "",
        "account_id": str(item["account_id"]),
        "category_id": str(item["category_id"]),
        "note": item["note"],
    }
    return render_form(kind, values, {}, accounts, categories, item)


@bp.post("/<int:item_id>/delete")
@login_required
def delete(item_id):
    item = owned_row("recurring", item_id)
    # The entries it added stay (their recurring_id becomes NULL: ON DELETE SET NULL).
    db.execute("DELETE FROM recurring WHERE id = ? AND user_id = ?", (item_id, g.user["id"]))
    db.commit()
    flash(f"Deleted {item['note']}. The entries it already added are still there.")
    return redirect(url_for("recurring.index"))
