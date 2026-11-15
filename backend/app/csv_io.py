"""CSV import and export for applications. No database here, so it's easy to test.

Import is all-or-nothing: if any row is invalid, nothing is saved and every
problem is reported with its spreadsheet row number, so the user can fix the
file and try again.
"""
import csv
import io
from datetime import date

from pydantic import ValidationError

from .schemas import ApplicationCreate, ApplicationStatus

COLUMNS = ["company", "role", "status", "applied_on", "follow_up_date", "url", "notes"]
REQUIRED = {"company", "role"}
MAX_ROWS = 500

# Friendly header names people use in their own spreadsheets.
HEADER_ALIASES = {
    "position": "role", "job title": "role", "title": "role",
    "link": "url", "job link": "url",
    "applied": "applied_on", "date applied": "applied_on", "applied on": "applied_on",
    "follow up": "follow_up_date", "follow-up": "follow_up_date", "follow up date": "follow_up_date",
}
STATUS_BY_NAME = {s.value.lower(): s.value for s in ApplicationStatus}

# Cells starting with these are run as formulas by Excel/Sheets, so exported
# text that begins with one is prefixed with a quote ("CSV injection").
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class ImportError_(Exception):
    """Raised with a list of {"row", "message"} problems."""

    def __init__(self, problems: list[dict]):
        super().__init__("import failed")
        self.problems = problems


def _header_key(name: str) -> str:
    key = name.strip().lower().replace("_", " ")
    key = HEADER_ALIASES.get(key, key)
    return key.replace(" ", "_")


def _friendly(error: dict) -> str:
    field = ".".join(str(part) for part in error["loc"]) or "row"
    message = error["msg"].removeprefix("Value error, ")
    if error["type"] in ("date_from_datetime_parsing", "date_parsing"):
        message = "use a date like 2026-10-31"
    return f"{field}: {message}"


def parse_import(text: str) -> list[dict]:
    """Return validated rows ready to insert, or raise ImportError_."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        header = next(reader)
    except StopIteration:
        raise ImportError_([{"row": 1, "message": "The file is empty."}])

    keys = [_header_key(h) for h in header]
    missing = REQUIRED - set(keys)
    if missing:
        raise ImportError_([{
            "row": 1,
            "message": "Missing column(s): " + ", ".join(sorted(missing))
            + ". The first row must be headers like: " + ", ".join(COLUMNS) + ".",
        }])

    rows, problems = [], []
    for row_number, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue  # skip blank lines
        if len(rows) + len(problems) >= MAX_ROWS:
            raise ImportError_([{"row": row_number, "message": f"Too many rows. The limit is {MAX_ROWS} per import."}])

        record = {k: v.strip() for k, v in zip(keys, cells) if k in COLUMNS}
        record = {k: v for k, v in record.items() if v != ""}  # empty cell = not set
        if "status" in record:
            status = STATUS_BY_NAME.get(record["status"].lower())
            if status is None:
                problems.append({"row": row_number,
                                 "message": "status: use Applied, Interview, Offer or Rejected"})
                continue
            record["status"] = status
        try:
            app = ApplicationCreate(**record)
        except ValidationError as error:
            problems.extend({"row": row_number, "message": _friendly(e)} for e in error.errors())
            continue
        data = app.model_dump()
        data["status"] = app.status.value
        rows.append(data)

    if problems:
        raise ImportError_(problems)
    if not rows:
        raise ImportError_([{"row": 2, "message": "No applications found under the header row."}])
    return rows


def _safe(value) -> str:
    if value is None:
        return ""
    text = value.isoformat() if isinstance(value, date) else str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def to_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([_safe(row[c]) for c in COLUMNS])
    return buffer.getvalue()
