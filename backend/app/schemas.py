"""Pydantic models: the validation boundary for every request and response."""
from datetime import date, datetime
from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class ApplicationStatus(str, Enum):
    applied = "Applied"
    interview = "Interview"
    offer = "Offer"
    rejected = "Rejected"


# ---------- Auth ----------

class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.strip().lower()


class UserOut(BaseModel):
    id: int
    email: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------- Applications ----------

def _clean_text(value: str | None) -> str | None:
    """Trim whitespace; treat an all-whitespace string as empty."""
    return value.strip() if isinstance(value, str) else value


def _check_url(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    parsed = urlparse(value)
    # Only http(s) with a host. This blocks "javascript:" links, which the
    # frontend would otherwise render as clickable hrefs.
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("must be a full link starting with http:// or https://")
    return value


class ApplicationFields(BaseModel):
    """Shared field rules for create and update."""
    model_config = ConfigDict(extra="forbid")

    company: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    url: str | None = Field(default=None, max_length=2048)
    status: ApplicationStatus = ApplicationStatus.applied
    follow_up_date: date | None = None
    applied_on: date | None = None  # defaults to today when not sent
    notes: str | None = Field(default=None, max_length=2000)

    # mode="before" runs before the length checks, so "   " fails min_length.
    @field_validator("company", "role", "url", "notes", mode="before")
    @classmethod
    def strip_text(cls, value):
        return _clean_text(value)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        return _check_url(value)

    @field_validator("notes")
    @classmethod
    def empty_notes_to_null(cls, value):
        return value or None

    @field_validator("applied_on")
    @classmethod
    def applied_on_not_in_future(cls, value):
        if value is not None and value > date.today():
            raise ValueError("can't be in the future")
        return value


class ApplicationCreate(ApplicationFields):
    pass


class ApplicationUpdate(ApplicationFields):
    """Partial update: every field optional, but company/role/status can't be cleared."""
    company: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, min_length=1, max_length=120)
    status: ApplicationStatus | None = None

    @model_validator(mode="after")
    def check_fields(self):
        if not self.model_fields_set:
            raise ValueError("send at least one field to update")
        for name in ("company", "role", "status", "applied_on"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be empty")
        return self

    def changes(self) -> dict:
        """Only the fields the client actually sent (so null can mean 'clear it')."""
        data = self.model_dump(include=self.model_fields_set)
        if "status" in data and data["status"] is not None:
            data["status"] = data["status"].value
        return data


class ApplicationOut(BaseModel):
    id: int
    company: str
    role: str
    url: str | None
    status: ApplicationStatus
    follow_up_date: date | None
    applied_on: date
    notes: str | None
    follow_up_due: bool
    created_at: datetime
    updated_at: datetime


class ApplicationList(BaseModel):
    items: list[ApplicationOut]


class WeekCount(BaseModel):
    week_start: date  # Monday
    count: int


class StatsOut(BaseModel):
    total: int
    by_status: dict[str, int]  # current status
    responded: int    # ever moved past Applied (interview, offer or rejection)
    interviewed: int  # ever reached Interview or Offer
    offers: int       # ever reached Offer
    response_rate: float   # 0..1 of total
    interview_rate: float  # 0..1 of total
    offer_rate: float      # 0..1 of total
    weekly: list[WeekCount]  # last 12 weeks by applied_on, oldest first, zeros included


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv: str = Field(min_length=1, max_length=1_000_000)


class ImportRowError(BaseModel):
    row: int  # spreadsheet row number (header is row 1)
    message: str


class ImportResult(BaseModel):
    imported: int


class HealthOut(BaseModel):
    status: str = "ok"
