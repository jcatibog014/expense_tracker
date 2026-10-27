"""Turning query results into numbers for the dashboard and the charts.

Plain functions without Flask or SQL (see tests/test_charts.py). The chart
data goes into the page as JSON; static/app.js draws it with Chart.js.
Colours are named by CSS variable, so the browser picks the light or dark
shade. Amounts stay in centavos; app.js turns them into pesos.
"""
import math

from .dates import add_months, last_day

# Chart colours (see the dataviz notes in AGENTS.md): blue and orange are
# palette slots 1 and 2, which colour-blind readers can still tell apart.
# Red and green (like the text colours) can't be, so charts don't use them.
INCOME_COLOR = "--chart-income"
SPENDING_COLOR = "--chart-spending"
CURRENT_COLOR = "--chart-current"
CONTEXT_COLOR = "--chart-context"  # gray: "last month", for comparison only
HEAT_LEVELS = 4


def change(current, previous):
    """How much a number went up or down since last time.

    {"amount": +500_00, "percent": 12} or percent None when there was nothing before.
    """
    amount = current - previous
    percent = round(amount * 100 / previous) if previous else None
    return {"amount": amount, "percent": percent}


def kept_percent(income, spending):
    """What part of the income was not spent, like 18 (%). None without income."""
    if income <= 0:
        return None
    return round((income - spending) * 100 / income)


def month_columns(monthly):
    """Income and spending columns, one pair per month."""
    return {
        "labels": [row["month"].strftime("%b") for row in monthly],
        "titles": [row["month"].strftime("%B %Y") for row in monthly],
        "series": [
            {"name": "Income", "color": INCOME_COLOR, "values": [row["income"] for row in monthly]},
            {"name": "Spending", "color": SPENDING_COLOR, "values": [row["spending"] for row in monthly]},
        ],
    }


def fill_days(running, days, until_day):
    """[(day, total so far)] -> one value per day 1..days.

    Days without spending keep yesterday's total. Days after `until_day`
    (the future) are None, so the line stops at today.
    """
    values, total, known = [], 0, dict(running)
    for day in range(1, days + 1):
        total = known.get(day, total)
        values.append(total if day <= until_day else None)
    return values


def running_lines(this_month, last_month, first_day, today):
    """This month's running spending, with last month's in gray to compare."""
    previous = add_months(first_day, -1)
    this_days = last_day(first_day.year, first_day.month)
    last_days = last_day(previous.year, previous.month)
    days = max(this_days, last_days)
    if first_day > today:
        this_until = 0  # a future month: nothing yet
    elif first_day.year == today.year and first_day.month == today.month:
        this_until = today.day
    else:
        this_until = this_days
    return {
        "labels": [str(day) for day in range(1, days + 1)],
        "titles": [f"Day {day}" for day in range(1, days + 1)],
        "series": [
            {"name": first_day.strftime("%B"), "color": CURRENT_COLOR,
             "values": fill_days(this_month, days, this_until)},
            {"name": previous.strftime("%B"), "color": CONTEXT_COLOR,
             "values": fill_days(last_month, days, last_days)},
        ],
    }


def category_bars(rows):
    """Add each category's share of the spending and its bar width (biggest = 100%)."""
    total = sum(row["total"] for row in rows)
    biggest = max((row["total"] for row in rows), default=0)
    return [
        {**row,
         "share": round(row["total"] * 100 / total) if total else 0,
         "width": round(row["total"] * 100 / biggest, 1) if biggest else 0}
        for row in rows
    ]


def heat_level(value, biggest):
    """0 for nothing, then 1..HEAT_LEVELS: how dark a table cell is."""
    if value <= 0 or biggest <= 0:
        return 0
    return max(1, math.ceil(value * HEAT_LEVELS / biggest))


def average(values):
    """The average of the numbers, rounded to whole centavos (0 for none)."""
    values = list(values)
    return round(sum(values) / len(values)) if values else 0
