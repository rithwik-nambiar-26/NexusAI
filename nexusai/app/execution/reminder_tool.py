"""Reminder capabilities for NexusAI.

These are the registered tools that create, list and cancel reminders.
They go through the same registry, the same input and output schemas and
the same approval policy as every other capability, so a reminder is
created exactly the way a document is read.

Two of the three capabilities change state and therefore require explicit
approval. A reminder is something the user asked NexusAI to remember on
their behalf, and it is written to their database; that is a state change,
and the registry says so.

The capabilities never run a shell command, never write outside the
reminder table, and never claim that a reminder was delivered.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from nexusai.app.core.logging import get_logger
from nexusai.app.execution.registry import (
    RetryPolicy,
    ToolDefinition,
    ToolError,
    ToolErrorCategory,
    ToolPermission,
    ToolRegistry,
    ToolRisk,
)
from nexusai.app.services.reminder import ReminderNotFoundError, ReminderService
from nexusai.app.services.reminder_time import ReminderTimeError

logger = get_logger("execution.reminder_tool")

#: The capability names. They match the planner's reminder task types.
REMINDER_CAPABILITIES: tuple[str, ...] = (
    "reminder.create",
    "reminder.list",
    "reminder.cancel",
)


class ReminderCreateInput(BaseModel):
    """Input for the ``reminder.create`` capability."""

    model_config = ConfigDict(extra="forbid")

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


class ReminderListInput(BaseModel):
    """Input for the ``reminder.list`` capability."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(
        default=None,
        description="Only return reminders with this status: pending, fired, cancelled or missed",
    )
    limit: int = Field(default=100, ge=1, le=500, description="Maximum reminders to return")


class ReminderCancelInput(BaseModel):
    """Input for the ``reminder.cancel`` capability."""

    model_config = ConfigDict(extra="forbid")

    reminder_id: int = Field(..., ge=1, description="The id of the reminder to cancel")


class ReminderOutput(BaseModel):
    """Output of the reminder capabilities."""

    model_config = ConfigDict(extra="forbid")

    reminders: list[dict[str, Any]] = Field(
        default_factory=list, description="The reminders that were acted on"
    )
    count: int = Field(default=0, description="How many reminders were returned")
    message: str | None = Field(
        default=None, description="A short statement of what was done"
    )
    notes: list[str] = Field(
        default_factory=list, description="Anything the user should know"
    )


def _make_create_handler(service: ReminderService):
    """Build the ``reminder.create`` handler."""

    def handler(payload: ReminderCreateInput) -> ReminderOutput:
        try:
            stored = service.create(
                payload.message,
                payload.due_at,
                timezone=payload.timezone,
            )
        except ReminderTimeError as exc:
            raise ToolError(
                str(exc),
                ToolErrorCategory.INVALID_INPUT,
                {"code": exc.code, **exc.details},
            ) from exc
        except ValueError as exc:
            raise ToolError(
                str(exc),
                ToolErrorCategory.INVALID_INPUT,
            ) from exc

        notes = [
            "A reminder is only delivered while NexusAI is running. If the "
            "application or the computer is off when it falls due, the "
            "reminder is recorded as missed and reported on the next start.",
        ]
        return ReminderOutput(
            reminders=[stored],
            count=1,
            message=f"Reminder stored for {stored['local_due_at']} ({stored['timezone']}).",
            notes=notes,
        )

    return handler


def _make_list_handler(service: ReminderService):
    """Build the ``reminder.list`` handler."""

    def handler(payload: ReminderListInput) -> ReminderOutput:
        reminders = service.list(status=payload.status, limit=payload.limit)
        return ReminderOutput(
            reminders=reminders,
            count=len(reminders),
            message=f"{len(reminders)} reminder(s).",
        )

    return handler


def _make_cancel_handler(service: ReminderService):
    """Build the ``reminder.cancel`` handler."""

    def handler(payload: ReminderCancelInput) -> ReminderOutput:
        try:
            stored = service.cancel(payload.reminder_id)
        except ReminderNotFoundError as exc:
            raise ToolError(
                str(exc),
                ToolErrorCategory.INVALID_INPUT,
                {"reminder_id": payload.reminder_id},
            ) from exc
        except ValueError as exc:
            raise ToolError(
                str(exc),
                ToolErrorCategory.INVALID_INPUT,
                {"reminder_id": payload.reminder_id},
            ) from exc

        return ReminderOutput(
            reminders=[stored],
            count=1,
            message=f"Reminder {stored['id']} cancelled.",
        )

    return handler


def register_reminder_tools(
    registry: ToolRegistry,
    service: ReminderService,
) -> list[ToolDefinition]:
    """Register the reminder capabilities.

    Args:
        registry: The registry to register into.
        service: The reminder service the capabilities act on.

    Returns:
        The registered tool definitions.
    """
    definitions = [
        ToolDefinition(
            capability="reminder.create",
            description=(
                "Store a reminder for a time the user names, for example "
                "'7 AM' or 'tomorrow at 7'. The time must be unambiguous; a "
                "time that could be morning or evening is reported rather "
                "than guessed."
            ),
            input_schema=ReminderCreateInput,
            output_schema=ReminderOutput,
            handler=_make_create_handler(service),
            permissions=[ToolPermission.WRITE_DATABASE],
            risk=ToolRisk.SENSITIVE,
            requires_approval=True,
            timeout_seconds=10.0,
            retry_policy=RetryPolicy(max_attempts=1),
            idempotent=False,
        ),
        ToolDefinition(
            capability="reminder.list",
            description=(
                "List the reminders NexusAI is keeping, with their due times "
                "and whether they are pending, fired, cancelled or missed."
            ),
            input_schema=ReminderListInput,
            output_schema=ReminderOutput,
            handler=_make_list_handler(service),
            permissions=[ToolPermission.READ_DOCUMENT],
            risk=ToolRisk.SAFE,
            requires_approval=False,
            timeout_seconds=10.0,
            retry_policy=RetryPolicy(max_attempts=1),
            idempotent=True,
        ),
        ToolDefinition(
            capability="reminder.cancel",
            description=(
                "Cancel a pending reminder by its id. A reminder that has "
                "already fired or been cancelled cannot be cancelled again."
            ),
            input_schema=ReminderCancelInput,
            output_schema=ReminderOutput,
            handler=_make_cancel_handler(service),
            permissions=[ToolPermission.WRITE_DATABASE],
            risk=ToolRisk.SENSITIVE,
            requires_approval=True,
            timeout_seconds=10.0,
            retry_policy=RetryPolicy(max_attempts=1),
            idempotent=False,
        ),
    ]

    for definition in definitions:
        registry.register(definition)

    logger.info(
        "Reminder tools registered",
        extra={"capabilities": [definition.capability for definition in definitions]},
    )
    return definitions
