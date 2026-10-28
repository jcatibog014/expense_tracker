"""Categories for spending (Food, Rent...) and income (Salary...).

Like wallets, a category that is used can't be deleted, only archived.
Its kind (spending or income) is chosen once and can't change later,
because its entries have that kind too.
"""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import db, queries
from ..auth import login_required
from ..validation import CATEGORY_COLORS, CATEGORY_KINDS, validate_category
from . import owned_row

bp = Blueprint("categories", __name__, url_prefix="/categories")


def taken_names(user_id, except_id=None):
    """{kind: {lower-case names}} of this user's categories."""
    names = {kind: set() for kind in CATEGORY_KINDS}
    for row in db.query("SELECT id, name, kind FROM categories WHERE user_id = ?", (user_id,)):
        if row["id"] != except_id:
            names[row["kind"]].add(row["name"].lower())
    return names


def times_used(category_id):
    row = db.query_one(
        """SELECT (SELECT COUNT(*) FROM transactions WHERE category_id = ?)
                + (SELECT COUNT(*) FROM recurring WHERE category_id = ?) AS n""",
        (category_id, category_id),
    )
    return row["n"]


def render_form(values, errors, category=None):
    return render_template(
        "category_form.html", values=values, errors=errors, category=category,
        kinds=CATEGORY_KINDS, colors=CATEGORY_COLORS,
        uses=times_used(category["id"]) if category else 0,
    ), 400 if errors else 200


@bp.get("")
@login_required
def index():
    rows = queries.category_usage(g.user["id"])
    return render_template(
        "categories.html",
        groups=[(kind, label, [r for r in rows if r["kind"] == kind and not r["archived"]])
                for kind, label in CATEGORY_KINDS.items()],
        archived=[r for r in rows if r["archived"]],
        kinds=CATEGORY_KINDS,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        data, errors = validate_category(request.form, taken_names(g.user["id"]))
        if errors:
            return render_form(request.form, errors)
        db.execute(
            "INSERT INTO categories (user_id, name, kind, color) VALUES (?, ?, ?, ?)",
            (g.user["id"], data["name"], data["kind"], data["color"]),
        )
        db.commit()
        flash(f"Added the category {data['name']}.")
        return redirect(url_for("categories.index"))
    kind = request.args.get("kind") if request.args.get("kind") in CATEGORY_KINDS else "expense"
    return render_form({"kind": kind, "color": CATEGORY_COLORS[0]}, {})


@bp.route("/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
def edit(category_id):
    category = owned_row("categories", category_id)
    if request.method == "POST":
        data, errors = validate_category(
            request.form, taken_names(g.user["id"], category_id), kind=category["kind"]
        )
        if errors:
            return render_form(request.form, errors, category)
        db.execute(
            "UPDATE categories SET name = ?, color = ? WHERE id = ? AND user_id = ?",
            (data["name"], data["color"], category_id, g.user["id"]),
        )
        db.commit()
        flash(f"Saved the category {data['name']}.")
        return redirect(url_for("categories.index"))
    return render_form({"name": category["name"], "color": category["color"]}, {}, category)


@bp.post("/<int:category_id>/archive")
@login_required
def archive(category_id):
    category = owned_row("categories", category_id)
    archived = 0 if category["archived"] else 1
    db.execute("UPDATE categories SET archived = ? WHERE id = ? AND user_id = ?",
               (archived, category_id, g.user["id"]))
    db.commit()
    flash(f"{category['name']} is {'archived' if archived else 'back'}.")
    return redirect(url_for("categories.index"))


@bp.post("/<int:category_id>/delete")
@login_required
def delete(category_id):
    category = owned_row("categories", category_id)
    if times_used(category_id):
        flash(f"{category['name']} has transactions, so it can't be deleted. You can archive it instead.")
        return redirect(url_for("categories.edit", category_id=category_id))
    db.execute("DELETE FROM categories WHERE id = ? AND user_id = ?", (category_id, g.user["id"]))
    db.commit()
    flash(f"Deleted the category {category['name']}.")
    return redirect(url_for("categories.index"))
