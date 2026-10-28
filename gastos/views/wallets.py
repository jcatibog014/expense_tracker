"""Wallets (the accounts table): Cash, GCash, a bank account...

A wallet that has entries can't be deleted (the database's FOREIGN KEY
rule says no), so it can be archived instead: it keeps its history, but
new entries can't pick it.
"""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import db, queries
from ..auth import login_required
from ..money import amount_input
from ..validation import ACCOUNT_KINDS, validate_account
from . import owned_row

bp = Blueprint("wallets", __name__, url_prefix="/wallets")


def taken_names(user_id, except_id=None):
    rows = db.query("SELECT id, name FROM accounts WHERE user_id = ?", (user_id,))
    return {row["name"].lower() for row in rows if row["id"] != except_id}


def times_used(wallet_id):
    """Entries and repeating items that use this wallet."""
    row = db.query_one(
        """SELECT (SELECT COUNT(*) FROM transactions
                   WHERE account_id = ? OR to_account_id = ?)
                + (SELECT COUNT(*) FROM recurring WHERE account_id = ?) AS n""",
        (wallet_id, wallet_id, wallet_id),
    )
    return row["n"]


def render_form(values, errors, wallet=None):
    return render_template(
        "wallet_form.html", values=values, errors=errors, wallet=wallet, kinds=ACCOUNT_KINDS,
        uses=times_used(wallet["id"]) if wallet else 0,
    ), 400 if errors else 200


@bp.get("")
@login_required
def index():
    wallets = queries.wallet_balances(g.user["id"])
    active = [w for w in wallets if not w["archived"]]
    return render_template(
        "wallets.html",
        active=active,
        archived=[w for w in wallets if w["archived"]],
        total=sum(w["balance"] for w in active),
        kinds=ACCOUNT_KINDS,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        data, errors = validate_account(request.form, taken_names(g.user["id"]))
        if errors:
            return render_form(request.form, errors)
        db.execute(
            "INSERT INTO accounts (user_id, name, kind, opening_balance) VALUES (?, ?, ?, ?)",
            (g.user["id"], data["name"], data["kind"], data["opening_balance"]),
        )
        db.commit()
        flash(f"Added the wallet {data['name']}.")
        return redirect(url_for("wallets.index"))
    return render_form({"kind": "cash"}, {})


@bp.route("/<int:wallet_id>/edit", methods=["GET", "POST"])
@login_required
def edit(wallet_id):
    wallet = owned_row("accounts", wallet_id)
    if request.method == "POST":
        data, errors = validate_account(request.form, taken_names(g.user["id"], wallet_id))
        if errors:
            return render_form(request.form, errors, wallet)
        db.execute(
            "UPDATE accounts SET name = ?, kind = ?, opening_balance = ? WHERE id = ? AND user_id = ?",
            (data["name"], data["kind"], data["opening_balance"], wallet_id, g.user["id"]),
        )
        db.commit()
        flash(f"Saved the wallet {data['name']}.")
        return redirect(url_for("wallets.index"))
    values = {"name": wallet["name"], "kind": wallet["kind"],
              "opening_balance": amount_input(wallet["opening_balance"])}
    return render_form(values, {}, wallet)


@bp.post("/<int:wallet_id>/archive")
@login_required
def archive(wallet_id):
    """Archive a wallet, or bring an archived one back."""
    wallet = owned_row("accounts", wallet_id)
    archived = 0 if wallet["archived"] else 1
    db.execute("UPDATE accounts SET archived = ? WHERE id = ? AND user_id = ?",
               (archived, wallet_id, g.user["id"]))
    db.commit()
    flash(f"{wallet['name']} is {'archived' if archived else 'back'}.")
    return redirect(url_for("wallets.index"))


@bp.post("/<int:wallet_id>/delete")
@login_required
def delete(wallet_id):
    wallet = owned_row("accounts", wallet_id)
    if times_used(wallet_id):
        flash(f"{wallet['name']} has transactions, so it can't be deleted. You can archive it instead.")
        return redirect(url_for("wallets.edit", wallet_id=wallet_id))
    db.execute("DELETE FROM accounts WHERE id = ? AND user_id = ?", (wallet_id, g.user["id"]))
    db.commit()
    flash(f"Deleted the wallet {wallet['name']}.")
    return redirect(url_for("wallets.index"))
