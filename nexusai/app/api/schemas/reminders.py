"""API schemas for the reminder endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateReminderRequest(BaseModel):
    """Request to store a reminder."""

    message: str = Field(..., min_length=1, description="What the reminder is about")
    due_at: str = Field(
        ...,
        min_length=1,
        description=(
            "When the reminder is due, as a phrase such as '7 AM', "
            "'tomorrow at 7' or 'in 30 minutes'"
        ),
    )
    timezone: str | None = Field(
        default=None,
        description="IANA timezone name to read the time in, such as 'Europe/London'",
    )


class ReminderResponse(BaseModel):
    """A single reminder."""

    id: int
    message: str
    due_at: str | None = None
    local_due_at: str | None = None
    timezone: str = "UTC"
    status: str = "pending"
    created_at: str | None = None
    fired_at: str | None = None
    cancelled_at: str | None = None
    missed_at: str | None = None


class ReminderListResponse(BaseModel):
    """A list of reminders."""

    reminders: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    request_id: str = ""


class CreateReminderResponse(BaseModel):
    """The response to storing a reminder."""

    reminder: dict[str, Any]
    notes: list[str] = Field(default_factory=list)
    request_id: str = ""


class CancelReminderResponse(BaseModel):
    """The response to cancelling a reminder."""

    reminder: dict[str, Any]
    request_id: str = ""


__all__ = [
    "CancelReminderResponse",
    "CreateReminderRequest",
    "CreateReminderResponse",
    "ReminderListResponse",
    "ReminderResponse",
]
