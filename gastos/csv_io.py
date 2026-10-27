"""CSV files: download your entries, and add entries from a file.

Plain functions without Flask or SQL (see tests/test_csv_io.py). A CSV file
is a table as text: one line per row, commas between the cells. Excel,
Google Sheets and banks' websites can all read and write it.

The columns: date, type, amount, wallet, to_wallet, category, note
"""
import csv
import io
import re
from collections import Counter
from datetime import date, datetime, timedelta

from .money import amount_input, parse_amount

HEADERS = ["date", "type", "amount", "wallet", "to_wallet", "category", "note"]
REQUIRED = ["date", "type", "amount", "wallet"]
# Other names people use for the same columns.
HEADER_ALIASES = {"kind": "type", "account": "wallet", "to_account": "to_wallet",
                  "description": "note", "memo": "note"}
TYPE_ALIASES = {"income": "income", "in": "income",
                "expense": "expense", "spending": "expense", "out": "expense",
                "transfer": "transfer"}

MAX_FILE_BYTES = 400 * 1024  # the file travels in the preview form too, so keep it small
MAX_ROWS = 2000
NAME_MAX_LENGTH = 40
NOTE_MAX_LENGTH = 200
EARLIEST_DATE = date(2000, 1, 1)
LATEST_DAYS_AHEAD = 366

# A cell that starts with one of these can be run as a formula by Excel
# ("CSV injection": =HYPERLINK(...) in a note could trick someone). A ' in
# front makes Excel show it as plain text.
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(text):
    text = str(text)
    return "'" + text if text.startswith(FORMULA_STARTS) else text


def unsafe_cell(text):
    """Undo safe_cell() when reading our own files back."""
    if text.startswith("'") and text[1:].startswith(FORMULA_STARTS):
        return text[1:]
    return text


def export_csv(entries):
    """Entries (rows from queries.ENTRY_SELECT) as CSV text.

    It starts with a BOM (an invisible mark) so Excel knows the file is
    UTF-8 and shows ₱ and ñ correctly.
    """
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(HEADERS)
    for t in entries:
        writer.writerow([
            t["date"], t["kind"], amount_input(t["amount"]),
            safe_cell(t["account"]), safe_cell(t["to_account"] or ""),
            safe_cell(t["category"] or ""), safe_cell(t["note"] or ""),
        ])
    return "﻿" + out.getvalue()


def decode(raw):
    """Bytes of an uploaded file -> text. Excel on Windows may save as cp1252."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def parse_date(text):
    """ "2026-10-28" or "10/28/2026" (month first, as Excel shows it in the Philippines)."""
    text = text.strip()
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    return None


def clean(text):
    return " ".join(unsafe_cell((text or "").strip()).split())


def read_rows(text):
    """Text -> (rows as dicts with our column names, error or None)."""
    first_line = text.split("\n", 1)[0]
    # Some Excel settings use ; between cells instead of ,
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        return [], "The file is empty."
    columns = [HEADER_ALIASES.get(h.strip().lower(), h.strip().lower()) for h in header]
    missing = [name for name in REQUIRED if name not in columns]
    if missing:
        return [], ("The first line must name the columns. Missing: " + ", ".join(missing)
                    + ". Download a CSV from Ang Gastos to see the right layout.")
    rows = []
    for cells in reader:
        if not any(cell.strip() for cell in cells):
            continue  # skip empty lines
        rows.append({"line": reader.line_num, **{name: (cells[i] if i < len(cells) else "")
                                                  for i, name in enumerate(columns)}})
        if len(rows) > MAX_ROWS:
            return [], f"The file has more than {MAX_ROWS} rows. Split it into smaller files."
    return rows, None


def parse_import(text, wallets, categories, today, create_missing):
    """Check every row of an uploaded CSV.

    wallets: {lower-case name: name} of this user's wallets.
    categories: {(kind, lower-case name): name} of this user's categories.
    create_missing: True to plan new wallets/categories for unknown names.

    Returns a dict:
      rows:  [{"line", "data" (or None), "errors": [...]}]
      new_wallets: [names], new_categories: [(kind, name)]
      error: a problem with the whole file, or None
    """
    rows, error = read_rows(text)
    result = {"rows": [], "new_wallets": [], "new_categories": [], "error": error}
    if error:
        return result
    new_wallets, new_categories = {}, {}

    def wallet_name(text, errors, label):
        name = clean(text)
        if not name:
            errors.append(f"{label} is empty.")
        elif len(name) > NAME_MAX_LENGTH:
            errors.append(f"{label} is longer than {NAME_MAX_LENGTH} letters.")
        elif name.lower() in wallets:
            return wallets[name.lower()]
        elif create_missing:
            return new_wallets.setdefault(name.lower(), name)
        else:
            errors.append(f'There is no wallet "{name}".')
        return None

    for row in rows:
        errors = []
        kind = TYPE_ALIASES.get(clean(row.get("type")).lower())
        if kind is None:
            errors.append('Type must be "income", "expense" or "transfer".')
        amount = parse_amount(row.get("amount"))
        if not amount:
            errors.append("Amount must be a number above zero, like 150 or 1234.50.")
        day = parse_date(row.get("date", ""))
        if day is None:
            errors.append("Date must look like 2026-10-28 or 10/28/2026.")
        elif not EARLIEST_DATE <= day <= today + timedelta(days=LATEST_DAYS_AHEAD):
            errors.append("Date must be from 2000 up to one year from today.")
        wallet = wallet_name(row.get("wallet"), errors, "Wallet")
        to_wallet = category = None
        if kind == "transfer":
            to_wallet = wallet_name(row.get("to_wallet"), errors, "To_wallet")
            if wallet and to_wallet and wallet.lower() == to_wallet.lower():
                errors.append("A transfer needs two different wallets.")
        elif kind:
            name = clean(row.get("category"))
            key = (kind, name.lower())
            if not name:
                errors.append("Category is empty.")
            elif len(name) > NAME_MAX_LENGTH:
                errors.append(f"Category is longer than {NAME_MAX_LENGTH} letters.")
            elif key in categories:
                category = categories[key]
            elif create_missing:
                category = new_categories.setdefault(key, name)
            else:
                errors.append(f'There is no {"income" if kind == "income" else "spending"} category "{name}".')
        note = clean(row.get("note"))
        if len(note) > NOTE_MAX_LENGTH:
            errors.append(f"Note is longer than {NOTE_MAX_LENGTH} letters.")

        data = None if errors else {
            "kind": kind, "amount": amount, "date": day.isoformat(),
            "wallet": wallet, "to_wallet": to_wallet, "category": category, "note": note,
        }
        result["rows"].append({"line": row["line"], "data": data, "errors": errors})

    # Only plan new names that a good row really uses.
    used_wallets = {n.lower() for r in result["rows"] if r["data"]
                    for n in (r["data"]["wallet"], r["data"]["to_wallet"]) if n}
    used_categories = {(r["data"]["kind"], r["data"]["category"].lower())
                       for r in result["rows"] if r["data"] and r["data"]["category"]}
    result["new_wallets"] = sorted(n for k, n in new_wallets.items() if k in used_wallets)
    result["new_categories"] = sorted((k[0], n) for k, n in new_categories.items() if k in used_categories)
    return result


def entry_key(kind, amount, day, wallet, to_wallet, category, note):
    """What makes two entries "the same", for finding duplicates."""
    return (day, kind, amount, wallet.lower(), (to_wallet or "").lower(), (category or "").lower(), note)


def mark_duplicates(rows, existing_keys):
    """Mark good rows that are already saved (data["duplicate"] = True).

    It counts: if the same entry is saved twice and the file has it three
    times, two are duplicates and one is new (two jeep rides can cost the same).
    """
    left = Counter(existing_keys)
    for row in rows:
        data = row["data"]
        if not data:
            continue
        key = entry_key(data["kind"], data["amount"], data["date"], data["wallet"],
                        data["to_wallet"], data["category"], data["note"])
        data["duplicate"] = left[key] > 0
        if data["duplicate"]:
            left[key] -= 1
    return rows


SAFE_FILENAME = re.compile(r"[^A-Za-z0-9_-]")


def filename(label):
    """ "2026-10" -> "ang-gastos-2026-10.csv" (only safe letters in a file name)."""
    return f"ang-gastos-{SAFE_FILENAME.sub('-', label)}.csv"
