"""Small date helpers. Plain functions without Flask (see tests/test_dates.py).

Dates are stored as text: "2026-10-28" for a day and "2026-10" for a month.
Text in this ISO order sorts like the dates themselves, so SQL can use
<, >, BETWEEN and ORDER BY on it, and substr(date, 1, 7) gives the month.
"""
import calendar
from datetime import date, datetime, timedelta, timezone

# The Philippines is UTC+8 all year (no daylight saving). The live server's
# clock runs on UTC, so "today" must be worked out in Philippine time, or the
# new day would start at 8 AM.
PH_TIME = timezone(timedelta(hours=8), "PHT")


def now():
    return datetime.now(PH_TIME)


def today():
    return now().date()


def month_of(day):
    """date(2026, 10, 28) -> "2026-10"."""
    return day.strftime("%Y-%m")


def parse_month(text):
    """ "2026-10" -> date(2026, 10, 1), or None if it isn't a month."""
    try:
        return datetime.strptime(text or "", "%Y-%m").date()
    except ValueError:
        return None


def add_months(first_day, count):
    """Move the 1st of a month `count` months forward (or back, if negative)."""
    index = first_day.year * 12 + (first_day.month - 1) + count
    return date(index // 12, index % 12 + 1, 1)


def last_day(year, month):
    """The last day of a month: 28, 29, 30 or 31."""
    return calendar.monthrange(year, month)[1]


def day_in_month(year, month, day_of_month):
    """The given day of a month, moved back to the last day if it's too big.

    Rent "every 31st" falls on Feb 28 (or 29), Apr 30 and so on.
    """
    return date(year, month, min(day_of_month, last_day(year, month)))


def month_label(first_day):
    """date(2026, 10, 1) -> "October 2026"."""
    return first_day.strftime("%B %Y")


def short_date(text, this_year=None):
    """ "2026-10-28" -> "Wed, Oct 28". Another year gets the year too: "Mon, Dec 29, 2025"."""
    day = date.fromisoformat(text)
    label = f"{day:%a}, {day:%b} {day.day}"  # day.day, because Windows has no %-d
    if day.year != (this_year or today().year):
        label += f", {day.year}"
    return label
