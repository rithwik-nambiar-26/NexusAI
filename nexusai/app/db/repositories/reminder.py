"""Repository for :class:`Reminder`.

The repository is the only code that touches the reminders table. It
normalises the timestamps it returns to UTC, because SQLite does not keep
the timezone a value was written with.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from nexusai.app.db.models import Reminder


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    """Return *value* as a timezone-aware UTC datetime.

    SQLite keeps the wall-clock value and drops the offset, so a value
    read back from the database is naive. It was written in UTC, so it is
    read back as UTC.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ReminderRepository:
    """Data-access object for reminders."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        message: str,
        due_at: datetime,
        *,
        timezone: str = "UTC",
        status: str = "pending",
    ) -> Reminder:
        """Store a reminder."""
        reminder = Reminder(
            message=message,
            due_at=due_at.astimezone(UTC),
            timezone=timezone,
            status=status,
        )
        self._session.add(reminder)
        self._session.flush()
        return reminder

    def get(self, reminder_id: int) -> Reminder | None:
        """Return one reminder by id, or None."""
        return self._session.get(Reminder, reminder_id)

    def list(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Reminder]:
        """Return reminders, newest first."""
        stmt = select(Reminder).order_by(Reminder.due_at.asc(), Reminder.id.asc())
        if status is not None:
            stmt = stmt.where(Reminder.status == status)
        stmt = stmt.limit(limit).offset(offset)
        return self._session.scalars(stmt).all()

    def list_pending(self) -> Sequence[Reminder]:
        """Return every reminder that has not yet been resolved."""
        stmt = (
            select(Reminder)
            .where(Reminder.status == "pending")
            .order_by(Reminder.due_at.asc(), Reminder.id.asc())
        )
        return self._session.scalars(stmt).all()

    def list_due(self, before: datetime) -> Sequence[Reminder]:
        """Return the pending reminders that are due at or before *before*."""
        stmt = (
            select(Reminder)
            .where(Reminder.status == "pending")
            .where(Reminder.due_at <= before.astimezone(UTC))
            .order_by(Reminder.due_at.asc(), Reminder.id.asc())
        )
        return self._session.scalars(stmt).all()

    def update_status(
        self,
        reminder_id: int,
        status: str,
        *,
        fired_at: datetime | None = None,
        cancelled_at: datetime | None = None,
        missed_at: datetime | None = None,
    ) -> Reminder | None:
        """Move a reminder to a new status."""
        reminder = self.get(reminder_id)
        if reminder is None:
            return None
        reminder.status = status
        if fired_at is not None:
            reminder.fired_at = fired_at
        if cancelled_at is not None:
            reminder.cancelled_at = cancelled_at
        if missed_at is not None:
            reminder.missed_at = missed_at
        reminder.updated_at = _utcnow()
        return reminder

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
