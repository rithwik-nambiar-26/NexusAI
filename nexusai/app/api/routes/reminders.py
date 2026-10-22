"""Reminder API routes.

These endpoints manage reminders directly, without a task plan. That
keeps them an independent, explicitly triggered workflow: a reminder is
created when the user asks for one, and nothing else writes to the
reminder table.

The scheduler's limitation is stated in the endpoint descriptions, because
it is part of the contract: a reminder is only delivered while NexusAI is
running.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from nexusai.app.api.dependencies import get_app_settings
from nexusai.app.api.schemas.reminders import (
    CancelReminderResponse,
    CreateReminderRequest,
    CreateReminderResponse,
    ReminderListResponse,
)
from nexusai.app.config import Settings
from nexusai.app.core.context import get_request_id
from nexusai.app.core.exceptions import ServiceUnavailableError, ValidationError
from nexusai.app.services.reminder import ReminderNotFoundError
from nexusai.app.services.reminder_time import ReminderTimeError

router = APIRouter(prefix="/api/v1/reminders", tags=["reminders"])

#: The reminder's delivery guarantee, stated where it is read.
DELIVERY_NOTE = (
    "A reminder is only delivered while NexusAI is running. If the "
    "application or the computer is switched off when a reminder falls due, "
    "it is recorded as missed and reported the next time NexusAI starts."
)


def _service_for(request: Request):
    """Return the reminder service owned by the running application."""
    service = getattr(request.app.state, "reminder_service", None)
    if service is None:
        raise ServiceUnavailableError(
            "The reminder service is not available.",
            code="service_unavailable",
        )
    return service


@router.get(
    "",
    response_model=ReminderListResponse,
    summary="List reminders",
    description="List the reminders NexusAI is keeping, with their due times and status.",
)
def list_reminders(
    request: Request,
    status: str | None = Query(
        default=None,
        description="Only return reminders with this status.",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    settings: Settings = Depends(get_app_settings),
) -> ReminderListResponse:
    """List the stored reminders."""
    service = _service_for(request)
    reminders = service.list(status=status, limit=limit, offset=offset)
    return ReminderListResponse(
        reminders=reminders,
        count=len(reminders),
        request_id=get_request_id(),
    )


@router.get(
    "/due",
    response_model=ReminderListResponse,
    summary="List due reminders",
    description=(
        "List the pending reminders that are due, or that fall due within "
        "the requested window."
    ),
)
def list_due_reminders(
    request: Request,
    within_minutes: int = Query(
        default=0,
        ge=0,
        le=60 * 24,
        description="How far ahead to look. Zero returns only the reminders already due.",
    ),
    settings: Settings = Depends(get_app_settings),
) -> ReminderListResponse:
    """List the reminders that are due."""
    service = _service_for(request)
    reminders = service.due(within_minutes=within_minutes)
    return ReminderListResponse(
        reminders=reminders,
        count=len(reminders),
        request_id=get_request_id(),
    )


@router.post(
    "",
    response_model=CreateReminderResponse,
    summary="Create a reminder",
    description=(
        "Store a reminder for a time the user names. The time must be "
        "unambiguous: a phrase such as '7' is reported as ambiguous rather "
        "than guessed. " + DELIVERY_NOTE
    ),
)
def create_reminder(
    request: Request,
    payload: CreateReminderRequest,
    settings: Settings = Depends(get_app_settings),
) -> CreateReminderResponse:
    """Store a reminder."""
    service = _service_for(request)
    try:
        stored = service.create(
            payload.message,
            payload.due_at,
            timezone=payload.timezone,
        )
    except ReminderTimeError as exc:
        raise ValidationError(
            str(exc),
            code=exc.code,
            details=exc.details,
        ) from exc
    except ValueError as exc:
        raise ValidationError(str(exc), code="invalid_input") from exc

    return CreateReminderResponse(
        reminder=stored,
        notes=[DELIVERY_NOTE],
        request_id=get_request_id(),
    )


@router.delete(
    "/{reminder_id}",
    response_model=CancelReminderResponse,
    summary="Cancel a reminder",
    description="Cancel a pending reminder by its id.",
)
def cancel_reminder(
    request: Request,
    reminder_id: int,
    settings: Settings = Depends(get_app_settings),
) -> CancelReminderResponse:
    """Cancel a pending reminder."""
    service = _service_for(request)
    try:
        stored = service.cancel(reminder_id)
    except ReminderNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise ValidationError(str(exc), code="not_cancellable") from exc

    return CancelReminderResponse(
        reminder=stored,
        request_id=get_request_id(),
    )
