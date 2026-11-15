"""Unit tests for CSV parsing and export: no database needed."""
import csv
import io
from datetime import date, timedelta

import pytest

from app.applications_logic import rate
from app.csv_io import MAX_ROWS, ImportError_, parse_import, to_csv


def test_parses_rows_with_friendly_headers_and_case():
    text = "﻿Company,Job Title,Status,Date Applied,Link\nAcme,Dev,interview,2026-09-01,https://acme.example\n"
    [row] = parse_import(text)
    assert row["company"] == "Acme" and row["role"] == "Dev" and row["status"] == "Interview"
    assert row["applied_on"] == date(2026, 9, 1) and row["url"] == "https://acme.example"


def test_empty_cells_use_defaults_and_blank_lines_are_skipped():
    rows = parse_import("company,role,status,notes\nAcme,Dev,,\n\n,,,\nGlobex,QA,,\n")
    assert [r["status"] for r in rows] == ["Applied", "Applied"]
    assert rows[0]["notes"] is None and rows[0]["applied_on"] is None


def test_every_bad_row_is_reported_with_its_row_number():
    future = (date.today() + timedelta(days=3)).isoformat()
    text = ("company,role,status,applied_on,url\n"
            "Acme,Dev,Applied,2026-09-01,\n"
            ",Dev,,,\n"
            "Globex,QA,Ghosted,,\n"
            f"Initech,PM,,{future},\n"
            "Hooli,SRE,,yesterday,javascript:alert(1)\n")
    with pytest.raises(ImportError_) as caught:
        parse_import(text)
    problems = caught.value.problems
    assert sorted({p["row"] for p in problems}) == [3, 4, 5, 6]
    joined = " | ".join(p["message"] for p in problems)
    assert "status: use Applied" in joined and "future" in joined and "2026-10-31" in joined


@pytest.mark.parametrize("text, expected", [
    ("", "empty"),
    ("company,notes\nAcme,x\n", "Missing column(s): role"),
    ("company,role\n", "No applications found"),
])
def test_unusable_files(text, expected):
    with pytest.raises(ImportError_) as caught:
        parse_import(text)
    assert expected in caught.value.problems[0]["message"]


def test_row_limit():
    text = "company,role\n" + "Acme,Dev\n" * (MAX_ROWS + 1)
    with pytest.raises(ImportError_, match="import failed"):
        parse_import(text)


def test_export_round_trips_and_neutralises_formulas():
    rows = [{"company": "=HYPERLINK(\"evil\")", "role": "Dev", "status": "Offer", "applied_on": date(2026, 9, 1),
             "follow_up_date": None, "url": None, "notes": "+254 712 000 000"}]
    out = list(csv.DictReader(io.StringIO(to_csv(rows))))
    assert out[0]["company"].startswith("'=") and out[0]["notes"].startswith("'+")
    assert out[0]["applied_on"] == "2026-09-01" and out[0]["follow_up_date"] == ""


def test_rate():
    assert rate(1, 3) == 0.333 and rate(0, 0) == 0.0
