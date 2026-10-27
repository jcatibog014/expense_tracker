import pytest

from gastos.money import MAX_CENTAVOS, amount_input, parse_amount, peso


def test_peso_format():
    assert peso(123450) == "₱1,234.50"
    assert peso(5) == "₱0.05"
    assert peso(0) == "₱0.00"
    assert peso(-250000) == "−₱2,500.00"
    assert peso(100, signed=True) == "+₱1.00"
    assert peso(None) == "₱0.00"


@pytest.mark.parametrize("text, centavos", [
    ("150", 15000),
    ("1,234.50", 123450),
    ("₱ 99.5", 9950),
    ("PHP 20", 2000),
    ("0.29", 29),  # float would give 28.999...
    ("0", 0),
    (" 12.00 ", 1200),
])
def test_parse_amount(text, centavos):
    assert parse_amount(text) == centavos


@pytest.mark.parametrize("text", ["", None, "abc", "1.234", "1.2.3", "-5", "1e3", "10000000.01", "nan"])
def test_parse_amount_refuses(text):
    assert parse_amount(text) is None


def test_negative_amounts_only_when_allowed():
    assert parse_amount("-500", allow_negative=True) == -50000
    assert parse_amount(f"-{MAX_CENTAVOS // 100 + 1}", allow_negative=True) is None


def test_amount_input():
    assert amount_input(123450) == "1234.50"
    assert amount_input(-5) == "-0.05"
    assert amount_input(None) == ""
