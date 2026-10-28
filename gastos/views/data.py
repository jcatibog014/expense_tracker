"""Your data as CSV: download (export) and upload (import).

Import is two steps. First you upload the file and see a preview: which
rows are good, which have problems, what is new. Then you press "Add".
The preview form carries the file's text, and the second step checks it
all again: never trust what comes back from a browser.
"""
from flask import Blueprint, Response, flash, g, redirect, render_template, request, url_for

from .. import csv_io, db, queries, tithes
from ..auth import login_required
from ..dates import today
from ..validation import read_filters

bp = Blueprint("data", __name__, url_prefix="/data")

# The demo is shared, so it may only add a small file at a time.
DEMO_MAX_ROWS = 200


def known_names(user_id):
    """This user's wallet and category names, keyed in lower case."""
    wallets = {r["name"].lower(): r["name"]
               for r in db.query("SELECT name FROM accounts WHERE user_id = ?", (user_id,))}
    categories = {(r["kind"], r["name"].lower()): r["name"]
                  for r in db.query("SELECT name, kind FROM categories WHERE user_id = ?", (user_id,))}
    return wallets, categories


def check_file(user_id, text, create_missing):
    """Parse and check the CSV, and mark the rows that are saved already."""
    wallets, categories = known_names(user_id)
    result = csv_io.parse_import(text, wallets, categories, today(), create_missing)
    good = [row["data"] for row in result["rows"] if row["data"]]
    if g.user["is_demo"] and len(result["rows"]) > DEMO_MAX_ROWS:
        result["error"] = f"The demo can add up to {DEMO_MAX_ROWS} rows at a time."
    if good and not result["error"]:
        saved = queries.entries_between(user_id, min(d["date"] for d in good), max(d["date"] for d in good))
        csv_io.mark_duplicates(result["rows"], [
            csv_io.entry_key(t["kind"], t["amount"], t["date"], t["account"], t["to_account"],
                             t["category"], t["note"])
            for t in saved
        ])
    # Ikapu set-asides in the file (from an export) are skipped: the app
    # makes them by itself from each income, so they'd be there twice.
    wallet = tithes.ikapu_wallet(user_id)
    for d in good:
        d["auto_ikapu"] = bool(wallet and d["kind"] == "transfer" and d["note"] == tithes.SET_ASIDE_NOTE
                               and (d["to_wallet"] or "").lower() == wallet["name"].lower())
        d["gets_ikapu"] = bool(wallet and d["kind"] == "income" and d["wallet"].lower() != wallet["name"].lower())
    return result


@bp.get("")
@login_required
def index():
    return render_template("data.html", this_month=today().strftime("%Y-%m"),
                           max_rows=DEMO_MAX_ROWS if g.user["is_demo"] else csv_io.MAX_ROWS,
                           max_kb=csv_io.MAX_FILE_BYTES // 1024)


@bp.get("/export")
@login_required
def export():
    """The entries list's filters (?month=, kind, category, account, q) as a CSV download."""
    filters = read_filters(request.args, today())
    entries = queries.export_entries(g.user["id"], filters)
    label = filters["month"].strftime("%Y-%m") if filters["month"] else "all"
    return Response(
        csv_io.export_csv(entries),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{csv_io.filename(label)}"'},
    )


@bp.post("/import")
@login_required
def upload():
    file = request.files.get("file")
    if file is None or not file.filename:
        flash("Choose a CSV file first.")
        return redirect(url_for("data.index"))
    raw = file.read(csv_io.MAX_FILE_BYTES + 1)
    if len(raw) > csv_io.MAX_FILE_BYTES:
        flash(f"That file is too big (the most is {csv_io.MAX_FILE_BYTES // 1024} KB). Split it into smaller files.")
        return redirect(url_for("data.index"))
    text = csv_io.decode(raw)
    create_missing = bool(request.form.get("create_missing"))
    return render_preview(text, create_missing, file.filename)


def render_preview(text, create_missing, file_name):
    result = check_file(g.user["id"], text, create_missing)
    rows = result["rows"]
    good = [row for row in rows if row["data"]]
    return render_template(
        "import_preview.html",
        result=result,
        file_name=file_name,
        csv_text=text,
        create_missing=create_missing,
        bad=[row for row in rows if row["errors"]],
        good=good,
        new_count=sum(1 for row in good if not row["data"].get("duplicate") and not row["data"].get("auto_ikapu")),
        duplicate_count=sum(1 for row in good if row["data"].get("duplicate")),
        auto_ikapu_count=sum(1 for row in good if row["data"].get("auto_ikapu")),
        ikapu_total=sum(tithes.tithe_amount(row["data"]["amount"]) for row in good
                        if row["data"].get("gets_ikapu") and not row["data"].get("duplicate")),
    ), 400 if result["error"] else 200


@bp.post("/import/confirm")
@login_required
def confirm():
    user_id = g.user["id"]
    text = request.form.get("csv_text", "")
    if len(text.encode("utf-8")) > csv_io.MAX_FILE_BYTES * 2:
        flash("That file is too big.")
        return redirect(url_for("data.index"))
    create_missing = bool(request.form.get("create_missing"))
    skip_duplicates = bool(request.form.get("skip_duplicates"))
    result = check_file(user_id, text, create_missing)
    if result["error"]:
        return render_preview(text, create_missing, request.form.get("file_name", ""))

    for name in result["new_wallets"]:
        db.execute("INSERT INTO accounts (user_id, name, kind) VALUES (?, ?, 'cash')", (user_id, name))
    for kind, name in result["new_categories"]:
        db.execute("INSERT INTO categories (user_id, name, kind, color) VALUES (?, ?, ?, 'gray')",
                   (user_id, name, kind))
    accounts = {r["name"].lower(): r["id"]
                for r in db.query("SELECT id, name FROM accounts WHERE user_id = ?", (user_id,))}
    categories = {(r["kind"], r["name"].lower()): r["id"]
                  for r in db.query("SELECT id, name, kind FROM categories WHERE user_id = ?", (user_id,))}

    rows = [row["data"] for row in result["rows"]
            if row["data"] and not row["data"]["auto_ikapu"]
            and not (skip_duplicates and row["data"].get("duplicate"))]
    for d in rows:
        new_id = db.insert(
            """INSERT INTO transactions
                   (user_id, kind, amount, date, account_id, to_account_id, category_id, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (user_id, d["kind"], d["amount"], d["date"], accounts[d["wallet"].lower()],
             accounts[d["to_wallet"].lower()] if d["to_wallet"] else None,
             categories[(d["kind"], d["category"].lower())] if d["category"] else None,
             d["note"]),
        )
        if d["gets_ikapu"]:
            tithes.sync(user_id, new_id)  # income: set aside its ikapu
    db.commit()
    skipped = len(result["rows"]) - len(rows)
    flash(f"Added {len(rows)} transaction{'' if len(rows) == 1 else 's'} from the file."
          + (f" Skipped {skipped}." if skipped else ""))
    return redirect(url_for("transactions.index", month="all"))
