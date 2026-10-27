"""Starting data: the default wallets and categories, and the demo's sample money.

The demo data is made up, but it looks like a real month in Metro Manila:
salary on the 15th and 30th, rent, Meralco, jeep fares, carinderia lunches...
It is always dated relative to today, so the charts are never out of date.
"""
import random
from datetime import timedelta

from . import db
from .dates import add_months, day_in_month, last_day

DEFAULT_ACCOUNTS = [
    # (name, kind)
    ("Cash", "cash"),
    ("GCash", "ewallet"),
    ("Bank", "bank"),
]

DEFAULT_CATEGORIES = [
    # (name, kind, color). Colours are names from validation.CATEGORY_COLORS.
    # There are more categories than colours, so a few share one; the
    # category name is always shown next to its colour, so that's fine.
    ("Food", "expense", "orange"),
    ("Groceries", "expense", "yellow"),
    ("Transport", "expense", "blue"),
    ("Bills", "expense", "violet"),
    ("Load & Internet", "expense", "aqua"),
    ("Rent", "expense", "red"),
    ("Health", "expense", "green"),
    ("Shopping", "expense", "magenta"),
    ("Fun", "expense", "magenta"),
    ("Family / Padala", "expense", "aqua"),
    ("Other", "expense", "gray"),
    ("Salary", "income", "green"),
    ("Freelance", "income", "blue"),
    ("Gifts", "income", "magenta"),
    ("Other income", "income", "gray"),
]

# The demo starts with this much money in each wallet (centavos).
DEMO_OPENING_BALANCES = {"Cash": 2_000_00, "GCash": 1_500_00, "Bank": 25_000_00}
DEMO_MONTHS = 6

# The demo's repeating entries: (note, kind, amount, wallet, category, day of month).
# demo_transactions() makes the same entries, and reset_demo() links them.
# Salary twice: on the 15th and on day 31, which becomes the last day of short months.
DEMO_RECURRING = [
    ("Sweldo", "income", 18_500_00, "Bank", "Salary", 15),
    ("Sweldo", "income", 18_500_00, "Bank", "Salary", 31),
    ("PLDT Fiber", "expense", 1_299_00, "GCash", "Load & Internet", 1),
    ("Upa", "expense", 6_500_00, "Bank", "Rent", 5),
    ("Padala kay Nanay", "expense", 3_000_00, "GCash", "Family / Padala", 16),
]

# The demo's monthly budgets (centavos). Some months go over, to show the red meters.
DEMO_BUDGETS = {
    "Food": 3_500_00,
    "Groceries": 7_500_00,
    "Transport": 1_800_00,
    "Bills": 3_000_00,
    "Shopping": 3_000_00,
    "Fun": 1_500_00,
}


def add_defaults(user_id, opening_balances=None):
    """Give a new user the default wallets and categories."""
    opening_balances = opening_balances or {}
    for name, kind in DEFAULT_ACCOUNTS:
        db.execute(
            "INSERT INTO accounts (user_id, name, kind, opening_balance) VALUES (?, ?, ?, ?)",
            (user_id, name, kind, opening_balances.get(name, 0)),
        )
    for name, kind, color in DEFAULT_CATEGORIES:
        db.execute(
            "INSERT INTO categories (user_id, name, kind, color) VALUES (?, ?, ?, ?)",
            (user_id, name, kind, color),
        )


def delete_user_data(user_id):
    """Remove everything a user owns, but keep the user (children first)."""
    for table in ("transactions", "budgets", "recurring", "categories", "accounts"):
        # The table name comes from our own list above, never from a visitor,
        # so putting it in the text is safe. Values still go in as parameters.
        db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))


def demo_transactions(today, months=DEMO_MONTHS):
    """Make the sample transactions from the 1st of (months - 1) months ago up to today.

    Returns rows of (kind, amount, date, account, to_account, category, note),
    with wallet and category *names*. The same `today` always gives the same
    rows, because the random numbers start from today's date (handy for tests).
    """
    rng = random.Random(today.isoformat())
    rows = []
    balances = dict(DEMO_OPENING_BALANCES)

    def add(kind, amount, day, account, category=None, note="", to_account=None):
        # Like a real person: if Cash or GCash can't pay, first get money from the bank.
        if kind != "income" and account != "Bank" and balances[account] < amount:
            short = amount - balances[account]
            top_up = (short // 1_000_00 + 2) * 1_000_00  # round up, plus ₱1,000 extra
            note_for_top_up = "ATM" if account == "Cash" else "Cash in to GCash"
            add("transfer", top_up, day, "Bank", note=note_for_top_up, to_account=account)
        balances[account] += amount if kind == "income" else -amount
        if to_account:
            balances[to_account] += amount
        rows.append((kind, amount, day.isoformat(), account, to_account, category, note))

    def pesos(low, high, step=1):
        """A random whole-peso amount from low to high, in centavos."""
        return rng.randrange(low, high + 1, step) * 100

    day = add_months(today.replace(day=1), -(months - 1))
    while day <= today:
        last = last_day(day.year, day.month)
        weekday = day.weekday()  # Monday is 0, Sunday is 6

        # Fixed things on fixed days of the month.
        if day.day == 15 or day.day == last:
            add("income", 18_500_00, day, "Bank", "Salary", "Sweldo")
            # GCash pays for groceries, bills and padala, so it gets money every payday.
            add("transfer", 5_000_00, day, "Bank", note="Cash in to GCash", to_account="GCash")
        if day.day == 1:
            add("expense", 1_299_00, day, "GCash", "Load & Internet", "PLDT Fiber")
        if day.day == 5:
            add("expense", 6_500_00, day, "Bank", "Rent", "Upa")
        if day.day == 10:
            add("expense", pesos(1_800, 2_600), day, "Bank", "Bills", "Meralco")
        if day.day == 12:
            add("expense", pesos(350, 520), day, "GCash", "Bills", "Maynilad")
        if day.day == 16:
            add("expense", 3_000_00, day, "GCash", "Family / Padala", "Padala kay Nanay")

        # Weekly things.
        if weekday == 0:
            add("transfer", 1_500_00, day, "Bank", note="ATM", to_account="Cash")
        if weekday == 5:
            store = rng.choice(["Puregold", "SM Supermarket", "Palengke"])
            # Groceries have centavos, like a real receipt.
            add("expense", pesos(1_200, 2_400) + rng.randrange(0, 100), day, "GCash", "Groceries", store)

        # Everyday things on weekdays.
        if weekday < 5:
            if rng.random() < 0.85:
                add("expense", pesos(90, 260, 5), day, "Cash", "Food",
                    rng.choice(["Carinderia", "Jollibee", "Siomai rice", "Lugaw", "7-Eleven"]))
            if rng.random() < 0.9:
                add("expense", pesos(26, 140, 2), day, "Cash", "Transport",
                    rng.choice(["Jeep", "Jeep + MRT", "Tricycle", "Bus"]))

        # Now and then.
        if rng.random() < 0.05:
            add("expense", pesos(300, 2_500, 50), day, "GCash", "Shopping",
                rng.choice(["Shopee", "Lazada", "Uniqlo"]))
        if rng.random() < 0.07:
            add("expense", pesos(250, 1_200, 10), day, "GCash", "Fun",
                rng.choice(["Sine", "Samgyup", "Milk tea", "Videoke"]))
        if rng.random() < 0.03:
            add("expense", pesos(150, 1_500, 10), day, "Cash", "Health",
                rng.choice(["Mercury Drug", "Check-up"]))
        if rng.random() < 0.03:
            add("income", pesos(2_000, 6_000, 100), day, "GCash", "Freelance", "Raket")

        day += timedelta(days=1)
    return rows


def reset_demo(user_id, today):
    """Throw away the demo's data and make a fresh set (the caller commits)."""
    delete_user_data(user_id)
    add_defaults(user_id, DEMO_OPENING_BALANCES)

    # Look up the new ids by name once, instead of once per transaction.
    accounts = {row["name"]: row["id"] for row in db.query(
        "SELECT id, name FROM accounts WHERE user_id = ?", (user_id,))}
    categories = {row["name"]: row["id"] for row in db.query(
        "SELECT id, name FROM categories WHERE user_id = ?", (user_id,))}
    first_month = add_months(today.replace(day=1), -(DEMO_MONTHS - 1))

    # Repeating entries, already added up to today (posted_until).
    repeating = []  # (id, note, category, day of month)
    for note, kind, amount, account, category, day in DEMO_RECURRING:
        item_id = db.insert(
            """INSERT INTO recurring (user_id, kind, amount, day_of_month, start_date,
                                      account_id, category_id, note, posted_until)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (user_id, kind, amount, day, first_month.isoformat(), accounts[account],
             categories[category], note, today.isoformat()),
        )
        repeating.append((item_id, note, category, day))

    def recurring_id(category, note, date_text):
        """The repeating item that made this demo entry, if any."""
        year, month, day = (int(part) for part in date_text.split("-"))
        for item_id, item_note, item_category, item_day in repeating:
            if (item_note, item_category) == (note, category) and                     day_in_month(year, month, item_day).day == day:
                return item_id
        return None

    db.execute_many(
        """INSERT INTO transactions
               (user_id, kind, amount, date, account_id, to_account_id, category_id, note, recurring_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (user_id, kind, amount, date, accounts[account], accounts.get(to_account),
             categories.get(category), note, recurring_id(category, note, date))
            for kind, amount, date, account, to_account, category, note in demo_transactions(today)
        ],
    )

    db.execute_many(
        "INSERT INTO budgets (user_id, category_id, month, amount) VALUES (?, ?, ?, ?)",
        [
            (user_id, categories[name], add_months(first_month, n).strftime("%Y-%m"), amount)
            for n in range(DEMO_MONTHS)
            for name, amount in DEMO_BUDGETS.items()
        ],
    )
