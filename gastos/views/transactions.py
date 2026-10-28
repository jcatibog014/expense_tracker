"""Entries: the list with filters, and adding, editing and deleting income,
spending and transfers between wallets."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import db, queries
from ..auth import login_required, safe_next
from ..dates import add_months, month_label, today
from ..money import amount_input, peso
from ..validation import KINDS, read_filters, validate_transaction
from . import owned_row

bp = Blueprint("transactions", __name__, url_prefix="/transactions")

PER_PAGE = 50
KIND_LABELS = {"expense": "Spending", "income": "Income", "transfer": "Transfer"}


def choices(user_id, entry=None):
    """The wallets and categories this user may pick, as {id: row}.

    Archived ones are left out, except the ones this entry already uses:
    editing an old entry must not force you to change its wallet.
    """
    keep_accounts = {entry["account_id"], entry["to_account_id"]} if entry else set()
    keep_category = entry["category_id"] if entry else None
    accounts = {
        row["id"]: row
        for row in db.query("SELECT id, name, archived FROM accounts WHERE user_id = ? ORDER BY id", (user_id,))
        if not row["archived"] or row["id"] in keep_accounts
    }
    categories = {
        row["id"]: row
        for row in db.query(
            "SELECT id, name, kind, color, archived FROM categories WHERE user_id = ? ORDER BY name", (user_id,)
        )
        if not row["archived"] or row["id"] == keep_category
    }
    return accounts, categories


def form_values(entry):
    """An entry from the database as the text the form's boxes show."""
    return {
        "amount": amount_input(entry["amount"]),
        "date": entry["date"],
        "account_id": str(entry["account_id"]),
        "to_account_id": str(entry["to_account_id"] or ""),
        "category_id": str(entry["category_id"] or ""),
        "note": entry["note"],
    }


def render_form(kind, values, errors, accounts, categories, entry=None, back=""):
    return render_template(
        "transaction_form.html",
        kind=kind,
        kinds=KIND_LABELS,
        values=values,
        errors=errors,
        # (value, label) pairs for the drop-downs.
        wallet_options=[(a["id"], a["name"]) for a in accounts.values()],
        category_options=[(c["id"], c["name"]) for c in categories.values() if c["kind"] == kind],
        entry=entry,
        back=back,
    ), 400 if errors else 200


def saved_message(data):
    sign = {"income": "+", "expense": "−"}.get(data["kind"], "")
    return f"Saved: {KIND_LABELS[data['kind']].lower()} {sign}{peso(data['amount'])}."


@bp.get("")
@login_required
def index():
    user_id = g.user["id"]
    filters = read_filters(request.args, today())
    totals = queries.filtered_totals(user_id, filters)
    pages = max((totals["count"] + PER_PAGE - 1) // PER_PAGE, 1)
    page = min(filters["page"], pages)
    entries = queries.find_entries(user_id, filters, PER_PAGE, (page - 1) * PER_PAGE)

    def link(**changes):
        """This page's address with some filters changed (and page 1, unless given)."""
        args = {
            "month": filters["month"].strftime("%Y-%m") if filters["month"] else "all",
            "kind": filters["kind"],
            "category": filters["category_id"],
            "account": filters["account_id"],
            "q": filters["q"],
        }
        args.update(changes)
        return url_for("transactions.index", **{k: v for k, v in args.items() if v})

    month = filters["month"]
    accounts, categories = choices(user_id)
    return render_template(
        "transactions.html",
        entries=entries,
        totals=totals,
        filters=filters,
        month_title=month_label(month) if month else "All months",
        previous_month=link(month=add_months(month, -1).strftime("%Y-%m")) if month else None,
        next_month=link(month=add_months(month, 1).strftime("%Y-%m")) if month else None,
        page=page,
        pages=pages,
        newer=link(page=page - 1) if page > 1 else None,
        older=link(page=page + 1) if page < pages else None,
        accounts=list(accounts.values()),
        categories=list(categories.values()),
        kinds=KIND_LABELS,
        here=request.full_path.rstrip("?"),
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    user_id = g.user["id"]
    accounts, categories = choices(user_id)
    if not accounts:
        flash("Add a wallet first. Every transaction needs one.")
        return redirect(url_for("wallets.new"))

    if request.method == "POST":
        data, errors = validate_transaction(request.form, accounts, categories, today())
        kind = request.form.get("kind") if request.form.get("kind") in KINDS else "expense"
        back = request.form.get("back", "")
        if errors:
            return render_form(kind, request.form, errors, accounts, categories, back=back)
        db.execute(
            """INSERT INTO transactions
                   (user_id, kind, amount, date, account_id, to_account_id, category_id, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, data["kind"], data["amount"], data["date"], data["account_id"],
             data["to_account_id"], data["category_id"], data["note"]),
        )
        db.commit()
        flash(saved_message(data))
        if "again" in request.form:
            # "Save and add another": keep the kind, date and wallet for quick typing.
            return redirect(url_for("transactions.new", kind=data["kind"], date=data["date"],
                                    account=data["account_id"], back=back))
        return redirect(safe_next(back, url_for("transactions.index")))

    kind = request.args.get("kind") if request.args.get("kind") in KINDS else "expense"
    values = {
        "date": request.args.get("date") or today().isoformat(),
        "account_id": request.args.get("account") or str(next(iter(accounts))),
    }
    return render_form(kind, values, {}, accounts, categories, back=request.args.get("back", ""))


@bp.route("/<int:entry_id>/edit", methods=["GET", "POST"])
@login_required
def edit(entry_id):
    entry = owned_row("transactions", entry_id)
    accounts, categories = choices(g.user["id"], entry)

    if request.method == "POST":
        data, errors = validate_transaction(request.form, accounts, categories, today())
        kind = request.form.get("kind") if request.form.get("kind") in KINDS else entry["kind"]
        back = request.form.get("back", "")
        if errors:
            return render_form(kind, request.form, errors, accounts, categories, entry, back)
        db.execute(
            """UPDATE transactions
               SET kind = ?, amount = ?, date = ?, account_id = ?, to_account_id = ?,
                   category_id = ?, note = ?
               WHERE id = ? AND user_id = ?""",
            (data["kind"], data["amount"], data["date"], data["account_id"], data["to_account_id"],
             data["category_id"], data["note"], entry_id, g.user["id"]),
        )
        db.commit()
        flash(saved_message(data))
        return redirect(safe_next(back, url_for("transactions.index")))

    # The kind tabs on the edit page switch the kind with ?kind=.
    kind = request.args.get("kind") if request.args.get("kind") in KINDS else entry["kind"]
    return render_form(kind, form_values(entry), {}, accounts, categories, entry,
                       request.args.get("back", ""))


@bp.post("/<int:entry_id>/delete")
@login_required
def delete(entry_id):
    owned_row("transactions", entry_id)
    db.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (entry_id, g.user["id"]))
    db.commit()
    flash("The transaction is deleted.")
    return redirect(safe_next(request.form.get("back", ""), url_for("transactions.index")))
