from datetime import date

from fastapi import APIRouter, Depends, Path, Query, Response, status
from psycopg import Connection
from psycopg.errors import ForeignKeyViolation

from .. import repository
from ..applications_logic import is_follow_up_due, rate
from ..csv_io import ImportError_, parse_import, to_csv
from ..db import get_conn
from ..errors import ApiError, error_response
from ..schemas import (
    ApplicationCreate, ApplicationList, ApplicationOut, ApplicationStatus, ApplicationUpdate,
    ImportRequest, ImportResult, StatsOut,
)
from ..security import get_current_user_id

router = APIRouter(prefix="/applications", tags=["applications"])

MAX_ID = 2**63 - 1  # Largest Postgres bigint; bigger values would be a DB error, not a 404.
ApplicationId = Path(gt=0, le=MAX_ID)
NOT_FOUND = ApiError(404, "not_found", "Application not found.")


def to_output(row: dict) -> ApplicationOut:
    """Add fields the backend computes (the frontend only displays them)."""
    due = is_follow_up_due(row["status"], row["follow_up_date"], date.today())
    return ApplicationOut(**row, follow_up_due=due)


@router.get("", response_model=ApplicationList)
def list_applications(
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"),
    user_id: int = Depends(get_current_user_id),
    conn: Connection = Depends(get_conn),
):
    value = status_filter.value if status_filter else None
    rows = repository.list_applications(conn, user_id, value)
    return ApplicationList(items=[to_output(r) for r in rows])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApplicationOut)
def create_application(
    body: ApplicationCreate,
    user_id: int = Depends(get_current_user_id),
    conn: Connection = Depends(get_conn),
):
    data = body.model_dump()
    data["status"] = body.status.value
    try:
        row = repository.create_application(conn, user_id, data)
    except ForeignKeyViolation:
        # Token is valid but the user no longer exists.
        raise ApiError(401, "unauthorized", "Your account was not found. Please log in again.")
    return to_output(row)


# ---------- Stats, export and import ----------
# Declared before "/{application_id}" so these fixed paths are matched first.

STATS_WEEKS = 12


@router.get("/stats", response_model=StatsOut)
def application_stats(
    user_id: int = Depends(get_current_user_id),
    conn: Connection = Depends(get_conn),
):
    row = repository.get_stats(conn, user_id, STATS_WEEKS)
    total = row["total"]
    return StatsOut(
        total=total,
        by_status={
            "Applied": row["applied"], "Interview": row["interview"],
            "Offer": row["offer"], "Rejected": row["rejected"],
        },
        responded=row["responded"],
        interviewed=row["interviewed"],
        offers=row["offers"],
        response_rate=rate(row["responded"], total),
        interview_rate=rate(row["interviewed"], total),
        offer_rate=rate(row["offers"], total),
        weekly=row["weekly"],
    )


@router.get("/export", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def export_applications(
    user_id: int = Depends(get_current_user_id),
    conn: Connection = Depends(get_conn),
):
    csv_text = to_csv(repository.all_applications_for_export(conn, user_id))
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="applications.csv"'},
    )


@router.post("/import", status_code=status.HTTP_201_CREATED, response_model=ImportResult)
def import_applications(
    body: ImportRequest,
    user_id: int = Depends(get_current_user_id),
    conn: Connection = Depends(get_conn),
):
    try:
        rows = parse_import(body.csv)
    except ImportError_ as error:
        details = [{"field": f"row {p['row']}", "message": p["message"]} for p in error.problems[:50]]
        first = details[0]
        count = len(error.problems)
        summary = f"{first['field']}: {first['message']}" if count == 1 else (
            f"{count} problems found, nothing was imported. First: {first['field']}: {first['message']}"
        )
        return error_response(422, "validation_error", summary, details)

    try:
        repository.import_applications(conn, user_id, rows)  # all or nothing
    except ForeignKeyViolation:
        raise ApiError(401, "unauthorized", "Your account was not found. Please log in again.")
    return ImportResult(imported=len(rows))


@router.get("/{application_id}", response_model=ApplicationOut)
def get_application(
    application_id: int = ApplicationId,
    user_id: int = Depends(get_current_user_id),
    conn: Connection = Depends(get_conn),
):
    row = repository.get_application(conn, user_id, application_id)
    if row is None:
        raise NOT_FOUND
    return to_output(row)


@router.patch("/{application_id}", response_model=ApplicationOut)
def update_application(
    body: ApplicationUpdate,
    application_id: int = ApplicationId,
    user_id: int = Depends(get_current_user_id),
    conn: Connection = Depends(get_conn),
):
    row = repository.update_application(conn, user_id, application_id, body.changes())
    if row is None:
        raise NOT_FOUND
    return to_output(row)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(
    application_id: int = ApplicationId,
    user_id: int = Depends(get_current_user_id),
    conn: Connection = Depends(get_conn),
):
    if not repository.delete_application(conn, user_id, application_id):
        raise NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)
