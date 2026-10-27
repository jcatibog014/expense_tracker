from datetime import date

from gastos import charts


def test_change():
    assert charts.change(1_500, 1_000) == {"amount": 500, "percent": 50}
    assert charts.change(900, 1_000) == {"amount": -100, "percent": -10}
    assert charts.change(500, 0) == {"amount": 500, "percent": None}


def test_kept_percent():
    assert charts.kept_percent(10_000, 8_200) == 18
    assert charts.kept_percent(10_000, 12_000) == -20
    assert charts.kept_percent(0, 500) is None


def test_month_columns():
    monthly = [
        {"month": date(2026, 9, 1), "income": 100, "spending": 40},
        {"month": date(2026, 10, 1), "income": 0, "spending": 70},
    ]
    data = charts.month_columns(monthly)
    assert data["labels"] == ["Sep", "Oct"]
    assert data["titles"] == ["September 2026", "October 2026"]
    assert [s["name"] for s in data["series"]] == ["Income", "Spending"]
    assert data["series"][1]["values"] == [40, 70]
    assert data["series"][0]["color"] == charts.INCOME_COLOR


def test_fill_days_carries_totals_and_stops_at_today():
    assert charts.fill_days([(2, 100), (4, 250)], 6, 5) == [0, 100, 100, 250, 250, None]


def test_running_lines_for_this_month():
    data = charts.running_lines([(1, 100), (3, 300)], [(30, 900)], date(2026, 10, 1), date(2026, 10, 3))
    assert data["labels"][0] == "1" and len(data["labels"]) == 31
    this_month, last_month = data["series"]
    assert this_month["name"] == "October" and last_month["name"] == "September"
    assert this_month["values"][:4] == [100, 100, 300, None]
    # September has 30 days, so day 31 is empty.
    assert last_month["values"][29] == 900 and last_month["values"][30] is None
    assert last_month["color"] == charts.CONTEXT_COLOR


def test_running_lines_for_past_and_future_months():
    past = charts.running_lines([(28, 500)], [], date(2026, 2, 1), date(2026, 10, 28))
    assert len(past["labels"]) == 31  # January has 31 days
    assert past["series"][0]["values"][27] == 500 and past["series"][0]["values"][28] is None
    future = charts.running_lines([], [], date(2026, 12, 1), date(2026, 10, 28))
    assert set(future["series"][0]["values"]) == {None}


def test_category_bars():
    rows = [{"name": "Rent", "total": 600}, {"name": "Food", "total": 300}, {"name": "Fun", "total": 100}]
    bars = charts.category_bars(rows)
    assert [(b["share"], b["width"]) for b in bars] == [(60, 100.0), (30, 50.0), (10, 16.7)]
    assert charts.category_bars([]) == []


def test_heat_level():
    assert charts.heat_level(0, 1000) == 0
    assert charts.heat_level(1, 1000) == 1
    assert charts.heat_level(500, 1000) == 2
    assert charts.heat_level(1000, 1000) == charts.HEAT_LEVELS


def test_average():
    assert charts.average([100, 200, 301]) == 200
    assert charts.average([]) == 0
