"""The reminder service.

Reminders are the first capability in NexusAI that stores something on
the user's behalf, so the service is where the honesty rules live:

* a reminder is only stored once its due time is known unambiguously;
* a reminder that was due while NexusAI was not running is recorded as
  **missed**, not silently dropped and not reported as delivered;
* nothing here claims that a reminder was delivered when it was not.

The service does not decide *when* a reminder fires. That is the
scheduler's job; the service only owns the stored state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import sessionmaker

from nexusai.app.core.logging import get_logger
from nexusai.app.db.models import Reminder as ReminderModel
from nexusai.app.db.repositories.reminder import ReminderRepository
from nexusai.app.services.reminder_time import (
    ParsedTime,
    ReminderTimeError,
    parse_due_at,
    resolve_timezone,
)

logger = get_logger("reminders.service")

#: The states a reminder moves through.
PENDING = "pending"
FIRED = "fired"
CANCELLED = "cancelled"
MISSED = "missed"


class ReminderNotFoundError(LookupError):
    """Raised when a reminder id does not exist."""


def _as_utc(value: datetime | None) -> datetime | None:
    """Return *value* as a timezone-aware UTC datetime."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ReminderService:
    """Stores, lists and cancels reminders.

    Args:
        session_factory: The factory the service opens its own sessions
            with, so a caller never has to manage a session.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------
    def create(
        self,
        message: str,
        due_expression: str,
        *,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        """Store a reminder due at the time named in *due_expression*.

        Args:
            message: What the reminder is about.
            due_expression: The phrase that names the time, for example
                "tomorrow at 7 AM".
            timezone: The IANA zone to read the phrase in. Defaults to
                the machine's local zone.

        Returns:
            A dictionary describing the stored reminder.

        Raises:
            ReminderTimeError: When the time is missing, ambiguous or
                already past.
        """
        text = (message or "").strip()
        if not text:
            raise ValueError("A reminder needs a message.")

        parsed = parse_due_at(due_expression, timezone=timezone)

        with self._session_factory() as session:
            repository = ReminderRepository(session)
            reminder = repository.create(
                text,
                parsed.due_at,
                timezone=parsed.timezone,
                status=PENDING,
            )
            session.commit()
            stored = _describe(reminder)

        logger.info(
            "Reminder stored",
            extra={
                "reminder_id": stored["id"],
                "due_at": stored["due_at"],
                "timezone": stored["timezone"],
            },
        )
        return stored

    def list(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return the stored reminders."""
        with self._session_factory() as session:
            repository = ReminderRepository(session)
            reminders = repository.list(status=status, limit=limit, offset=offset)
            return [_describe(reminder) for reminder in reminders]

    def due(self, *, within_minutes: int = 0, now: datetime | None = None) -> list[dict[str, Any]]:
        """Return the pending reminders that are due.

        Args:
            within_minutes: How far ahead to look. Zero returns only the
                reminders that are already due.
            now: The current instant, for testing.
        """
        current = now or datetime.now(UTC)
        horizon = current + timedelta(minutes=within_minutes)
        with self._session_factory() as session:
            repository = ReminderRepository(session)
            reminders = repository.list_due(horizon)
            return [_describe(reminder) for reminder in reminders]

    def cancel(self, reminder_id: int) -> dict[str, Any]:
        """Cancel a pending reminder.

        Raises:
            ReminderNotFoundError: When the id does not exist.
            ValueError: When the reminder is no longer pending.
        """
        with self._session_factory() as session:
            repository = ReminderRepository(session)
            reminder = repository.get(reminder_id)
            if reminder is None:
                raise ReminderNotFoundError(f"No reminder with id {reminder_id}.")
            if reminder.status != PENDING:
                raise ValueError(
                    f"Reminder {reminder_id} is already {reminder.status} and "
                    "cannot be cancelled."
                )
            updated = repository.update_status(
                reminder_id, CANCELLED, cancelled_at=datetime.now(UTC)
            )
            session.commit()
            stored = _describe(updated)  # type: ignore[arg-type]

        logger.info("Reminder cancelled", extra={"reminder_id": reminder_id})
        return stored

    # ------------------------------------------------------------------
    # Scheduler support
    # ------------------------------------------------------------------
    def fire_due(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Mark every reminder that is due as fired.

        Returns:
            The reminders that were fired by this call.
        """
        current = now or datetime.now(UTC)
        with self._session_factory() as session:
            repository = ReminderRepository(session)
            due = list(repository.list_due(current))
            fired = []
            for reminder in due:
                updated = repository.update_status(
                    reminder.id, FIRED, fired_at=current
                )
                if updated is not None:
                    fired.append(_describe(updated))
            session.commit()

        for reminder in fired:
            logger.info(
                "Reminder fired",
                extra={
                    "reminder_id": reminder["id"],
                    "due_at": reminder["due_at"],
                    "reminder_message": reminder["message"],
                },
            )
        return fired

    def mark_missed(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Mark the reminders that were due while NexusAI was not running.

        A reminder that came due while the application was stopped cannot
        be delivered. It is recorded as missed, so the user is told it was
        missed rather than being told nothing at all, and so it is never
        reported as delivered.
        """
        current = now or datetime.now(UTC)
        with self._session_factory() as session:
            repository = ReminderRepository(session)
            overdue = [
                reminder
                for reminder in repository.list_pending()
                if (_as_utc(reminder.due_at) or current) <= current
            ]
            missed = []
            for reminder in overdue:
                updated = repository.update_status(
                    reminder.id, MISSED, missed_at=current
                )
                if updated is not None:
                    missed.append(_describe(updated))
            session.commit()

        if missed:
            logger.info(
                "Reminders missed while NexusAI was not running",
                extra={"count": len(missed)},
            )
        return missed


def _describe(reminder: ReminderModel) -> dict[str, Any]:
    """Describe a reminder as a plain dictionary."""
    due_at = _as_utc(reminder.due_at)
    zone_name = reminder.timezone or "UTC"
    try:
        _, zone = resolve_timezone(zone_name)
        local_due = due_at.astimezone(zone) if due_at else None
    except Exception:  # pragma: no cover - defensive
        local_due = due_at

    return {
        "id": reminder.id,
        "message": reminder.message,
        "due_at": due_at.isoformat() if due_at else None,
        "local_due_at": local_due.isoformat() if local_due else None,
        "timezone": zone_name,
        "status": reminder.status,
        "created_at": _as_utc(reminder.created_at).isoformat() if reminder.created_at else None,
        "fired_at": _as_utc(reminder.fired_at).isoformat() if reminder.fired_at else None,
        "cancelled_at": (
            _as_utc(reminder.cancelled_at).isoformat() if reminder.cancelled_at else None
        ),
        "missed_at": _as_utc(reminder.missed_at).isoformat() if reminder.missed_at else None,
    }


__all__ = [
    "CANCELLED",
    "FIRED",
    "MISSED",
    "PENDING",
    "ParsedTime",
    "ReminderNotFoundError",
    "ReminderService",
    "ReminderTimeError",
]
