"""The dashboard and reports pages."""
import json
import re

from gastos.dates import add_months, day_in_month, today

from .conftest import add_entry


def chart_data(page):
    """The JSON of every chart on a page."""
    return [json.loads(raw) for raw in re.findall(r'<script type="application/json" class="chart-data">(.*?)</script>', page, re.S)]


def test_dashboard_shows_a_past_month(owner_client, app, owner_id):
    add_entry(app, owner_id, "income", 20_000_00, "2025-10-15", account="Bank")
    add_entry(app, owner_id, "expense", 5_000_00, "2025-10-05", category="Rent", note="Upa")
    add_entry(app, owner_id, "expense", 4_000_00, "2025-09-05", category="Rent")
    page = owner_client.get("/?month=2025-10").get_data(as_text=True)
    assert "October 2025" in page
    assert "₱20,000.00" in page and "₱5,000.00" in page and "₱15,000.00" in page
    assert "You kept 75% of your income" in page
    # A finished month is compared with all of last month.
    assert "₱1,000.00 more than September (25%)" in page
    assert "Spending by category" in page and "Upa" in page
    assert "month=2025-09" in page and "month=2025-11" in page


def test_this_month_is_compared_with_the_same_days_of_last_month(owner_client, app, owner_id):
    now = today()
    previous = add_months(now.replace(day=1), -1)
    add_entry(app, owner_id, "expense", 100_00, now.isoformat())
    add_entry(app, owner_id, "expense", 300_00, previous.isoformat())  # day 1: counts
    if now.day < 28:  # a day after "today" in last month: doesn't count
        add_entry(app, owner_id, "expense", 9_999_00, previous.replace(day=now.day + 1).isoformat())
    same_day = day_in_month(previous.year, previous.month, now.day)
    page = owner_client.get("/").get_data(as_text=True)
    assert f"₱200.00 less than {previous:%B} 1–{same_day.day}" in page


def test_dashboard_chart_data(owner_client, app, owner_id):
    add_entry(app, owner_id, "expense", 300_00, "2026-10-02")
    page = owner_client.get("/?month=2026-10").get_data(as_text=True)
    daily, history = chart_data(page)
    assert daily["series"][0]["name"] == "October" and daily["series"][0]["values"][1] == 300_00
    assert len(history["labels"]) == 12 and history["labels"][-1] == "Oct"
    assert history["series"][1]["values"][-1] == 300_00
    # The same numbers are in the tables.
    assert "Show as table" in page and "October 2026</th>" in page


def test_chart_js_is_pinned_with_integrity(owner_client):
    page = owner_client.get("/").get_data(as_text=True)
    assert "chart.js@4.4.7/dist/chart.umd.js" in page and 'integrity="sha384-' in page


def test_empty_month(owner_client):
    page = owner_client.get("/?month=2001-01").get_data(as_text=True)
    assert "No spending in January 2001" in page and "No income yet this month" in page


def test_bad_month_means_this_month(owner_client):
    page = owner_client.get("/?month=banana").get_data(as_text=True)
    assert today().strftime("%B %Y") in page


def test_reports_page(owner_client, app, owner_id):
    add_entry(app, owner_id, "income", 10_000_00, "2025-03-15", account="Bank")
    add_entry(app, owner_id, "expense", 2_000_00, "2025-03-05", category="Rent", note="March rent")
    add_entry(app, owner_id, "expense", 1_000_00, "2025-07-05", category="Food")
    page = owner_client.get("/reports?year=2025").get_data(as_text=True)
    assert "Reports 2025" in page
    assert "₱10,000.00" in page and "₱3,000.00" in page and "₱7,000.00" in page
    # A past year averages over 12 months: 3,000 / 12 = 250.
    assert "₱250.00" in page and "Over 12 months" in page
    assert "March rent" in page and "heat-4" in page
    (columns,) = chart_data(page)
    assert columns["series"][1]["values"][2] == 2_000_00


def test_reports_year_limits(owner_client):
    this_year = today().year
    page = owner_client.get("/reports?year=99999").get_data(as_text=True)
    assert f"Reports {this_year + 1}" in page and "Next year" not in page
    assert "Reports 2000" in owner_client.get("/reports?year=1").get_data(as_text=True)


def test_reports_this_year_averages_months_so_far(owner_client, app, owner_id):
    first = today().replace(day=1)
    add_entry(app, owner_id, "expense", 1_200_00 * first.month, first.isoformat())
    page = owner_client.get("/reports").get_data(as_text=True)
    assert f"Over {first.month} month" in page and "₱1,200.00" in page


def test_dashboard_and_reports_need_a_login(client):
    assert client.get("/reports").status_code == 302
