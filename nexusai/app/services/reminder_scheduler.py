"""The in-process reminder scheduler.

The scheduler is a daemon thread inside the NexusAI process. It wakes at
a fixed interval, asks the reminder service which reminders are due, and
marks them as fired.

**What it does not do.** It does not register a Windows scheduled task, it
does not start a separate operating-system job, and it does not run any
external command. Nothing is written outside NexusAI's own database.

**What that means for the user.** A reminder can only be delivered while
NexusAI is running. If the application is stopped, or the machine is
switched off or asleep, a reminder that comes due in that time is *not*
delivered. When NexusAI starts again it records those reminders as
**missed** and reports them, rather than pretending they were delivered.
That limitation is stated in the interface as well as here.
"""

from __future__ import annotations

import threading
from datetime import datetime

from nexusai.app.core.logging import get_logger

logger = get_logger("reminders.scheduler")

#: How often the scheduler checks for due reminders.
DEFAULT_INTERVAL_SECONDS = 15.0


class ReminderScheduler:
    """Fires due reminders while NexusAI is running.

    Args:
        service: The reminder service the scheduler asks for due
            reminders.
        interval_seconds: How long the scheduler sleeps between checks.
    """

    def __init__(
        self,
        service,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._service = service
        self._interval = interval_seconds
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the scheduler thread.

        The reminders that came due while NexusAI was not running are
        recorded as missed before the thread begins, so they are not
        reported as delivered.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._stop.clear()
            missed = self._service.mark_missed()
            if missed:
                logger.info(
                    "Recorded reminders that were due while NexusAI was not running",
                    extra={"count": len(missed)},
                )

            self._thread = threading.Thread(
                target=self._run,
                name="nexusai-reminder-scheduler",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                "Reminder scheduler started",
                extra={"interval_seconds": self._interval},
            )

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the scheduler thread."""
        with self._lock:
            thread = self._thread
            self._thread = None
        self._stop.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
            logger.info("Reminder scheduler stopped")

    @property
    def is_running(self) -> bool:
        """True when the scheduler thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Work
    # ------------------------------------------------------------------
    def tick(self, now: datetime | None = None) -> list[dict]:
        """Fire the reminders that are due, once.

        This is the scheduler's whole job, and it is a plain method so it
        can be called directly in a test without waiting for the thread.
        """
        fired = self._service.fire_due(now=now)
        return fired

    def _run(self) -> None:
        """The scheduler loop."""
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # pragma: no cover - the thread must survive
                logger.exception("The reminder scheduler pass failed")
            self._stop.wait(self._interval)
