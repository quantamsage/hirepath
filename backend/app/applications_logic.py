"""Business rules that don't need the database (easy to unit test)."""
from datetime import date

from .schemas import ApplicationStatus

# A follow-up only matters while the application is still in progress.
ACTIVE_STATUSES = {ApplicationStatus.applied.value, ApplicationStatus.interview.value}


def is_follow_up_due(status: str, follow_up_date: date | None, today: date) -> bool:
    return follow_up_date is not None and follow_up_date <= today and status in ACTIVE_STATUSES


def rate(part: int, total: int) -> float:
    """Share of total, rounded to 3 places. 0 when there's nothing to divide."""
    return round(part / total, 3) if total else 0.0
