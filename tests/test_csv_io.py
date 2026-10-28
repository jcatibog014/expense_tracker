import csv
import io
from datetime import date

from gastos import csv_io

TODAY = date(2026, 10, 28)
WALLETS = {"cash": "Cash", "gcash": "GCash", "bank": "Bank"}
CATEGORIES = {("expense", "food"): "Food", ("income", "salary"): "Salary"}


def parse(text, create_missing=False):
    return csv_io.parse_import(text, WALLETS, CATEGORIES, TODAY, create_missing)


def test_safe_cells_stop_excel_formulas():
    assert csv_io.safe_cell("=HYPERLINK(\"http://evil\")") == "'=HYPERLINK(\"http://evil\")"
    assert csv_io.safe_cell("+63 917") == "'+63 917"
    assert csv_io.safe_cell("Jollibee") == "Jollibee"
    assert csv_io.unsafe_cell("'=SUM(A1)") == "=SUM(A1)"
    assert csv_io.unsafe_cell("'tis") == "'tis"  # a normal apostrophe stays


def test_export_csv():
    text = csv_io.export_csv([
        {"date": "2026-10-02", "kind": "expense", "amount": 150_50, "account": "Cash",
         "to_account": None, "category": "Food", "note": "=1+1"},
        {"date": "2026-10-06", "kind": "transfer", "amount": 2_000_00, "account": "Bank",
         "to_account": "Cash", "category": None, "note": "ATM, BDO"},
    ])
    assert text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text[1:])))
    assert rows[0] == csv_io.HEADERS
    assert rows[1] == ["2026-10-02", "expense", "150.50", "Cash", "", "Food", "'=1+1"]
    assert rows[2] == ["2026-10-06", "transfer", "2000.00", "Bank", "Cash", "", "ATM, BDO"]


def test_export_then_import_gives_the_same_rows():
    text = csv_io.export_csv([
        {"date": "2026-10-02", "kind": "expense", "amount": 150_50, "account": "Cash",
         "to_account": None, "category": "Food", "note": "=1+1"},
    ])
    row = parse(csv_io.decode(text.encode("utf-8")))["rows"][0]
    assert row["errors"] == []
    assert row["data"] == {"kind": "expense", "amount": 150_50, "date": "2026-10-02", "wallet": "Cash",
                           "to_wallet": None, "category": "Food", "note": "=1+1"}


def test_import_reads_aliases_dates_and_semicolons():
    text = "Date;Kind;Amount;Account;Description;Category\n10/28/2026;spending;₱1,234.50;gcash;Puregold;FOOD\n"
    row = parse(text)["rows"][0]
    assert row["errors"] == []
    assert row["data"]["date"] == "2026-10-28" and row["data"]["amount"] == 123450
    assert row["data"]["wallet"] == "GCash" and row["data"]["category"] == "Food"
    assert row["data"]["note"] == "Puregold"


def test_import_errors_per_row():
    text = ("date,type,amount,wallet,to_wallet,category,note\n"
            "2026-13-01,gift,-5,,,,\n"
            "2026-10-01,transfer,100,Cash,cash,,\n"
            "2026-10-01,expense,100,Maya,,Pets,\n"
            "\n"
            "2026-10-01,income,100,Cash,,Food,\n")
    rows = parse(text)["rows"]
    assert [r["line"] for r in rows] == [2, 3, 4, 6]  # empty line 5 is skipped
    assert len(rows[0]["errors"]) == 4  # date, type, amount, wallet
    assert rows[1]["errors"] == ["A transfer needs two different wallets."]
    assert rows[2]["errors"] == ['There is no wallet "Maya".', 'There is no spending category "Pets".']
    # Food is a spending category, not an income one.
    assert rows[3]["errors"] == ['There is no income category "Food".']


def test_import_can_plan_new_names():
    text = ("date,type,amount,wallet,category\n"
            "2026-10-01,expense,100,Maya,Pets\n"
            "2026-10-02,expense,200,maya,pets\n"
            "2026-10-03,expense,abc,Unused Wallet,Unused\n")
    result = parse(text, create_missing=True)
    assert result["new_wallets"] == ["Maya"]  # once, and not the one from the bad row
    assert result["new_categories"] == [("expense", "Pets")]
    assert result["rows"][1]["data"]["wallet"] == "Maya"


def test_whole_file_problems():
    assert parse("")["error"] == "The file is empty."
    assert "Missing: type, amount" in parse("date,wallet\n2026-10-01,Cash\n")["error"]
    big = "date,type,amount,wallet,category\n" + "2026-10-01,expense,1,Cash,Food\n" * (csv_io.MAX_ROWS + 1)
    assert "more than" in parse(big)["error"]


def test_dates_must_be_reasonable():
    text = "date,type,amount,wallet,category\n1999-01-01,expense,1,Cash,Food\n2028-01-01,expense,1,Cash,Food\n"
    assert all("Date must be from 2000" in r["errors"][0] for r in parse(text)["rows"])


def test_decode_cp1252():
    assert csv_io.decode("Ni\xf1o".encode("cp1252")) == "Niño"
    assert csv_io.decode("﻿date".encode("utf-8")) == "date"


def test_mark_duplicates_counts():
    key = csv_io.entry_key("expense", 13_00, "2026-10-01", "Cash", None, "Transport", "Jeep")
    rows = [{"data": {"kind": "expense", "amount": 13_00, "date": "2026-10-01", "wallet": "cash",
                      "to_wallet": None, "category": "transport", "note": "Jeep"}} for _ in range(3)]
    csv_io.mark_duplicates(rows, [key, key])
    assert [r["data"]["duplicate"] for r in rows] == [True, True, False]


def test_filename():
    assert csv_io.filename("2026-10") == "ang-gastos-2026-10.csv"
    assert csv_io.filename('a"b/c') == "ang-gastos-a-b-c.csv"
