from datetime import date

from gastos import dates


def test_month_text_round_trip():
    assert dates.month_of(date(2026, 10, 28)) == "2026-10"
    assert dates.parse_month("2026-10") == date(2026, 10, 1)


def test_parse_month_rejects_nonsense():
    for text in ("", None, "2026-13", "2026-1x", "October", "2026-10-01"):
        assert dates.parse_month(text) is None


def test_add_months_crosses_years():
    assert dates.add_months(date(2026, 11, 1), 1) == date(2026, 12, 1)
    assert dates.add_months(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert dates.add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert dates.add_months(date(2026, 10, 1), -12) == date(2025, 10, 1)


def test_day_in_month_moves_back_to_the_last_day():
    assert dates.day_in_month(2026, 2, 31) == date(2026, 2, 28)
    assert dates.day_in_month(2028, 2, 31) == date(2028, 2, 29)  # a leap year
    assert dates.day_in_month(2026, 4, 31) == date(2026, 4, 30)
    assert dates.day_in_month(2026, 1, 31) == date(2026, 1, 31)
    assert dates.day_in_month(2026, 6, 15) == date(2026, 6, 15)


def test_today_is_philippine_time():
    assert dates.now().utcoffset().total_seconds() == 8 * 60 * 60


def test_month_label():
    assert dates.month_label(date(2026, 10, 1)) == "October 2026"
