"""Checking form fields before they go into the database.

Plain functions without Flask: the form's fields go in, clean data plus
error messages come out (see tests/test_validation.py). Each returns
(data, errors), where errors maps a field name to a message for people.

Never trust a form. A browser (or a script) can send anything, including
the id of somebody else's wallet, so the caller passes in the wallets and
categories this user may use, and we only accept those.
"""
from datetime import date, timedelta

from .dates import parse_month
from .money import parse_amount

KINDS = ("income", "expense", "transfer")
ACCOUNT_KINDS = {"cash": "Cash", "ewallet": "E-wallet", "bank": "Bank"}
CATEGORY_KINDS = {"expense": "Spending", "income": "Income"}
# The 8 chart colours (in their fixed order) plus a gray for "other" things.
# The real colours are CSS variables (--cat-blue ...), so dark mode can use
# its own shade of each. Checked with the dataviz palette validator.
CATEGORY_COLORS = ("blue", "orange", "aqua", "yellow", "magenta", "green", "violet", "red", "gray")

NAME_MAX_LENGTH = 40
NOTE_MAX_LENGTH = 200
SEARCH_MAX_LENGTH = 80
EARLIEST_DATE = date(2000, 1, 1)
# Entries may be dated up to a year ahead (a bill you already know about).
LATEST_DAYS_AHEAD = 366


def clean_text(text, max_length):
    """Trim, squash extra spaces, and say if it's too long."""
    text = " ".join((text or "").split())
    return text, len(text) > max_length


def parse_id(text):
    """A row id from a form or URL, or None if it isn't a whole number."""
    text = (text or "").strip()
    return int(text) if text.isdigit() and len(text) < 10 else None


def parse_date(text):
    try:
        return date.fromisoformat((text or "").strip())
    except ValueError:
        return None


def validate_transaction(form, accounts, categories, today):
    """Check an income, expense or transfer.

    `accounts` and `categories` are dicts {id: row} of what this user may
    pick. A category row has a "kind", which must match the entry's kind.
    """
    errors = {}
    kind = form.get("kind")
    if kind not in KINDS:
        return None, {"kind": "Choose income, spending or transfer."}

    amount = parse_amount(form.get("amount"))
    if not amount:  # None (not a number) or 0
        errors["amount"] = "Type an amount above zero, like 150 or 1,234.50."

    day = parse_date(form.get("date"))
    if day is None:
        errors["date"] = "Choose a date."
    elif not EARLIEST_DATE <= day <= today + timedelta(days=LATEST_DAYS_AHEAD):
        errors["date"] = "Choose a date from 2000 up to one year from today."

    account_id = parse_id(form.get("account_id"))
    if account_id not in accounts:
        errors["account_id"] = "Choose a wallet."

    to_account_id = category_id = None
    if kind == "transfer":
        to_account_id = parse_id(form.get("to_account_id"))
        if to_account_id not in accounts:
            errors["to_account_id"] = "Choose the wallet the money goes to."
        elif to_account_id == account_id:
            errors["to_account_id"] = "Choose two different wallets."
    else:
        category_id = parse_id(form.get("category_id"))
        category = categories.get(category_id)
        if category is None or category["kind"] != kind:
            errors["category_id"] = "Choose a category."

    note, too_long = clean_text(form.get("note"), NOTE_MAX_LENGTH)
    if too_long:
        errors["note"] = f"Use {NOTE_MAX_LENGTH} characters or fewer."

    if errors:
        return None, errors
    return {
        "kind": kind,
        "amount": amount,
        "date": day.isoformat(),
        "account_id": account_id,
        "to_account_id": to_account_id,
        "category_id": category_id,
        "note": note,
    }, {}


def validate_name(form, errors):
    name, too_long = clean_text(form.get("name"), NAME_MAX_LENGTH)
    if not name:
        errors["name"] = "Type a name."
    elif too_long:
        errors["name"] = f"Use {NAME_MAX_LENGTH} characters or fewer."
    return name


def validate_account(form, taken_names):
    """Check a wallet. `taken_names` are the user's other wallet names, in lower case."""
    errors = {}
    name = validate_name(form, errors)
    if name and name.lower() in taken_names:
        errors["name"] = "You already have a wallet with this name."

    kind = form.get("kind")
    if kind not in ACCOUNT_KINDS:
        errors["kind"] = "Choose a type."

    opening_text = (form.get("opening_balance") or "").strip()
    opening_balance = parse_amount(opening_text, allow_negative=True) if opening_text else 0
    if opening_balance is None:
        errors["opening_balance"] = "Type an amount, like 2500 or -500 (or leave it empty)."

    if errors:
        return None, errors
    return {"name": name, "kind": kind, "opening_balance": opening_balance}, {}


def validate_category(form, taken_names, kind=None):
    """Check a category. `kind` is given when editing (it can't change then).

    `taken_names` are the user's other category names of the same kind, in lower case.
    """
    errors = {}
    name = validate_name(form, errors)
    kind = kind or form.get("kind")
    if kind not in CATEGORY_KINDS:
        errors["kind"] = "Choose spending or income."
    elif name and name.lower() in taken_names.get(kind, set()):
        errors["name"] = "You already have a category with this name."

    color = form.get("color")
    if color not in CATEGORY_COLORS:
        errors["color"] = "Choose a colour."

    if errors:
        return None, errors
    return {"name": name, "kind": kind, "color": color}, {}


def read_filters(args, today):
    """Read the filters of the entries list from the URL. Bad values are ignored.

    No month in the URL means this month. month=all means every month.
    """
    month_text = args.get("month") or today.strftime("%Y-%m")
    month = None if month_text == "all" else parse_month(month_text)
    if month is None and month_text != "all":
        month = today.replace(day=1)
    kind = args.get("kind")
    query, _ = clean_text(args.get("q"), SEARCH_MAX_LENGTH)
    page = parse_id(args.get("page")) or 1
    return {
        "month": month,  # the 1st of the month, or None for all months
        "kind": kind if kind in KINDS else None,
        "category_id": parse_id(args.get("category")),
        "account_id": parse_id(args.get("account")),
        "q": query[:SEARCH_MAX_LENGTH],
        "page": max(page, 1),
    }


def validate_recurring(form, accounts, categories, today):
    """Check a repeating entry (income or spending only, not transfers).

    Like validate_transaction(), `accounts` and `categories` are what this
    user may pick, as {id: row}.
    """
    errors = {}
    kind = form.get("kind")
    if kind not in CATEGORY_KINDS:
        return None, {"kind": "Choose spending or income."}

    amount = parse_amount(form.get("amount"))
    if not amount:
        errors["amount"] = "Type an amount above zero, like 549 or 6,500."

    day_of_month = parse_id(form.get("day_of_month"))
    if day_of_month is None or not 1 <= day_of_month <= 31:
        errors["day_of_month"] = "Choose a day from 1 to 31."

    start = parse_date(form.get("start_date"))
    if start is None:
        errors["start_date"] = "Choose the first date."
    elif not EARLIEST_DATE <= start <= today + timedelta(days=LATEST_DAYS_AHEAD):
        errors["start_date"] = "Choose a date from 2000 up to one year from today."

    end_text = (form.get("end_date") or "").strip()
    end = parse_date(end_text) if end_text else None
    if end_text and end is None:
        errors["end_date"] = "Choose a date, or leave it empty."
    elif end and start and end < start:
        errors["end_date"] = "The last date can't be before the first date."

    account_id = parse_id(form.get("account_id"))
    if account_id not in accounts:
        errors["account_id"] = "Choose a wallet."
    category_id = parse_id(form.get("category_id"))
    category = categories.get(category_id)
    if category is None or category["kind"] != kind:
        errors["category_id"] = "Choose a category."

    note, too_long = clean_text(form.get("note"), NOTE_MAX_LENGTH)
    if not note:
        errors["note"] = "Give it a name, like Rent or Netflix."
    elif too_long:
        errors["note"] = f"Use {NOTE_MAX_LENGTH} characters or fewer."

    if errors:
        return None, errors
    return {
        "kind": kind,
        "amount": amount,
        "day_of_month": day_of_month,
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end else None,
        "account_id": account_id,
        "category_id": category_id,
        "note": note,
    }, {}


def validate_budgets(form, category_ids):
    """Check the budgets form: one box per category, named "budget-<id>".

    Returns ({category id: centavos or None}, errors). None (an empty box)
    means "no budget": the caller deletes it.
    """
    data, errors = {}, {}
    for category_id in category_ids:
        name = f"budget-{category_id}"
        text = (form.get(name) or "").strip()
        if not text:
            data[category_id] = None
            continue
        amount = parse_amount(text)
        if amount is None:
            errors[name] = "Type an amount, like 5000, or leave it empty."
        elif amount == 0:
            data[category_id] = None  # 0 also means "no budget"
        else:
            data[category_id] = amount
    return (None, errors) if errors else (data, {})
