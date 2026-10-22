"""Tests for the reminder capability.

Reminders are the first NexusAI capability that stores something on the
user's behalf, so the tests here cover three things:

* the time a reminder is due is resolved, or reported as unresolvable;
* a reminder moves through its states correctly, including the missed
  state that records a reminder coming due while NexusAI was not running;
* nothing claims a reminder was delivered when it was not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from nexusai.app.config import Settings
from nexusai.app.main import create_app
from nexusai.app.services.reminder import (
    CANCELLED,
    FIRED,
    MISSED,
    PENDING,
    ReminderNotFoundError,
    ReminderService,
)
from nexusai.app.services.reminder_scheduler import ReminderScheduler
from nexusai.app.services.reminder_time import (
    ReminderTimeError,
    local_timezone_name,
    parse_due_at,
)

ZONE = "Asia/Kolkata"


@pytest.fixture
def client(tmp_path) -> TestClient:
    """A test client with an isolated database."""
    settings = Settings(
        database_url="sqlite:///:memory:",
        vector_store_dir=str(tmp_path / "vectors"),
        allowed_document_roots=["./data", "./docs", "./experiments", str(tmp_path)],
    )
    return TestClient(create_app(settings))


@pytest.fixture
def service(client: TestClient) -> ReminderService:
    """The reminder service owned by the test application."""
    return client.app.state.reminder_service


# ---------------------------------------------------------------------------
# Time resolution
# ---------------------------------------------------------------------------


def test_a_time_is_resolved_to_an_instant():
    """'7 AM' becomes a specific instant in the named zone."""
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    parsed = parse_due_at("7 AM", now=now, timezone=ZONE)

    assert parsed.local_due_at.hour == 7
    assert parsed.local_due_at.date().isoformat() == "2026-10-23"
    assert parsed.due_at == parsed.local_due_at.astimezone(UTC)
    assert parsed.timezone == ZONE


def test_a_past_time_rolls_to_the_next_day():
    """A time with no date means the next occurrence of that time."""
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)  # 17:30 in the zone
    parsed = parse_due_at("9 AM", now=now, timezone=ZONE)

    assert parsed.local_due_at.date().isoformat() == "2026-10-23"
    assert "next occurrence" in " ".join(parsed.notes)


def test_tomorrow_is_the_next_day():
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    parsed = parse_due_at("tomorrow at 9 AM", now=now, timezone=ZONE)

    assert parsed.local_due_at.date().isoformat() == "2026-10-23"
    assert parsed.local_due_at.hour == 9


def test_a_relative_expression_is_resolved_from_now():
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    parsed = parse_due_at("in 90 minutes", now=now, timezone=ZONE)

    assert parsed.due_at == now + timedelta(minutes=90)


def test_an_ambiguous_time_is_reported_with_both_readings():
    """'7' could be morning or evening, so it is not guessed."""
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    with pytest.raises(ReminderTimeError) as caught:
        parse_due_at("at 7", now=now, timezone=ZONE)

    assert caught.value.code == "ambiguous_time"
    assert caught.value.details["interpretations"] == ["07:00", "19:00"]


def test_a_missing_time_is_reported():
    with pytest.raises(ReminderTimeError) as caught:
        parse_due_at("sometime soon", timezone=ZONE)

    assert caught.value.code == "missing_time"


def test_a_date_without_a_time_is_reported():
    with pytest.raises(ReminderTimeError) as caught:
        parse_due_at("on 2026-10-25", timezone=ZONE)

    assert caught.value.code == "missing_time"


def test_an_impossible_date_is_reported():
    with pytest.raises(ReminderTimeError) as caught:
        parse_due_at("2026-02-30 09:00", timezone=ZONE)

    assert caught.value.code == "invalid_date"


def test_an_unknown_timezone_is_reported():
    with pytest.raises(ReminderTimeError) as caught:
        parse_due_at("7 AM", timezone="Mars/Olympus_Mons")

    assert caught.value.code == "unknown_timezone"


def test_the_local_timezone_is_resolvable():
    """The machine's own zone resolves to a name this system knows."""
    name = local_timezone_name()
    assert name
    parsed = parse_due_at("7 AM", timezone=name)
    assert parsed.timezone == name


# ---------------------------------------------------------------------------
# Storing, listing and cancelling
# ---------------------------------------------------------------------------


def test_a_reminder_is_stored(service: ReminderService):
    stored = service.create("Team standup", "tomorrow at 9 AM", timezone=ZONE)

    assert stored["id"] > 0
    assert stored["message"] == "Team standup"
    assert stored["status"] == PENDING
    assert stored["local_due_at"] is not None
    assert stored["timezone"] == ZONE


def test_a_stored_reminder_is_listed(service: ReminderService):
    service.create("One", "in 10 minutes", timezone=ZONE)
    service.create("Two", "in 20 minutes", timezone=ZONE)

    reminders = service.list()
    assert len(reminders) == 2
    assert {r["message"] for r in reminders} == {"One", "Two"}


def test_a_reminder_is_cancelled(service: ReminderService):
    stored = service.create("Cancel me", "in 10 minutes", timezone=ZONE)

    cancelled = service.cancel(stored["id"])
    assert cancelled["status"] == CANCELLED
    assert cancelled["cancelled_at"] is not None

    # A cancelled reminder is not pending any more.
    pending = service.list(status=PENDING)
    assert all(r["id"] != stored["id"] for r in pending)


def test_cancelling_an_unknown_reminder_is_reported(service: ReminderService):
    with pytest.raises(ReminderNotFoundError):
        service.cancel(9999)


def test_cancelling_a_reminder_twice_is_reported(service: ReminderService):
    stored = service.create("Once only", "in 10 minutes", timezone=ZONE)
    service.cancel(stored["id"])

    with pytest.raises(ValueError):
        service.cancel(stored["id"])


# ---------------------------------------------------------------------------
# The scheduler
# ---------------------------------------------------------------------------


def test_a_due_reminder_is_fired(service: ReminderService):
    scheduler = ReminderScheduler(service)
    stored = service.create("Fire me", "in 1 minute", timezone=ZONE)

    # Not yet due.
    assert scheduler.tick() == []

    fired = scheduler.tick(now=datetime.now(UTC) + timedelta(minutes=5))
    assert [f["id"] for f in fired] == [stored["id"]]
    assert fired[0]["status"] == FIRED
    assert fired[0]["fired_at"] is not None


def test_a_reminder_that_came_due_while_offline_is_marked_missed(
    service: ReminderService,
):
    """The reminder is reported as missed, never as delivered."""
    stored = service.create("Missed me", "in 1 minute", timezone=ZONE)

    missed = service.mark_missed(now=datetime.now(UTC) + timedelta(minutes=10))
    assert [m["id"] for m in missed] == [stored["id"]]
    assert missed[0]["status"] == MISSED
    assert missed[0]["missed_at"] is not None
    assert missed[0]["fired_at"] is None


def test_a_missed_reminder_is_not_fired_afterwards(service: ReminderService):
    """A reminder recorded as missed is not later reported as delivered."""
    stored = service.create("Missed me", "in 1 minute", timezone=ZONE)
    service.mark_missed(now=datetime.now(UTC) + timedelta(minutes=10))

    scheduler = ReminderScheduler(service)
    fired = scheduler.tick(now=datetime.now(UTC) + timedelta(minutes=20))
    assert all(f["id"] != stored["id"] for f in fired)


def test_the_scheduler_starts_and_stops(service: ReminderService):
    scheduler = ReminderScheduler(service, interval_seconds=0.1)
    scheduler.start()
    assert scheduler.is_running
    scheduler.stop()
    assert not scheduler.is_running


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------


def test_the_api_creates_lists_and_cancels(client: TestClient):
    created = client.post(
        "/api/v1/reminders",
        json={"message": "Call the dentist", "due_at": "tomorrow at 9 AM"},
    )
    assert created.status_code == 200
    reminder = created.json()["reminder"]
    assert reminder["status"] == PENDING
    # The delivery guarantee is stated in the response.
    assert created.json()["notes"]

    listed = client.get("/api/v1/reminders")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    cancelled = client.delete(f"/api/v1/reminders/{reminder['id']}")
    assert cancelled.status_code == 200
    assert cancelled.json()["reminder"]["status"] == CANCELLED


def test_the_api_refuses_an_ambiguous_time(client: TestClient):
    response = client.post(
        "/api/v1/reminders", json={"message": "Something", "due_at": "at 7"}
    )

    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "ambiguous_time"
    assert body["details"]["interpretations"] == ["07:00", "19:00"]


def test_the_api_refuses_a_missing_time(client: TestClient):
    response = client.post(
        "/api/v1/reminders", json={"message": "Something", "due_at": "later"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "missing_time"


def test_the_api_reports_due_reminders(client: TestClient):
    client.post(
        "/api/v1/reminders", json={"message": "Soon", "due_at": "in 5 minutes"}
    )

    due = client.get("/api/v1/reminders/due")
    assert due.status_code == 200
    # Nothing is due yet.
    assert due.json()["count"] == 0

    window = client.get("/api/v1/reminders/due?within_minutes=10")
    assert window.json()["count"] == 1


def test_cancelling_an_unknown_reminder_is_a_404(client: TestClient):
    response = client.delete("/api/v1/reminders/9999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# The registered capabilities
# ---------------------------------------------------------------------------


def test_the_reminder_capabilities_are_registered(client: TestClient):
    tools = client.get("/api/v1/execution/tools").json()["tools"]
    capabilities = {tool["capability"] for tool in tools}

    assert {"reminder.create", "reminder.list", "reminder.cancel"} <= capabilities


def test_creating_a_reminder_through_the_executor_needs_approval(
    client: TestClient,
):
    """The write capability waits for a decision before it runs."""
    plan = client.post(
        "/api/v1/planner/plan",
        json={
            "text": "Remind me about the standup at 9 AM",
            "intent": "reminder",
            "source": "explicit",
        },
    ).json()["plan"]

    assert plan["intent"] == "reminder"
    assert plan["requires_approval"] is True
    assert plan["tasks"]

    report = client.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]
    assert report["status"] == "awaiting_approval"

    # Nothing was created: the task is blocked, not completed.
    for result in report["task_results"]:
        assert result["status"] != "completed"
    assert client.get("/api/v1/reminders").json()["count"] == 0


def test_the_planner_picks_the_reminder_shape_from_the_request(
    client: TestClient,
):
    """A list request and a create request get different capabilities."""
    listing = client.post(
        "/api/v1/planner/plan",
        json={
            "text": "List my reminders",
            "intent": "reminder",
            "source": "explicit",
        },
    ).json()["plan"]
    assert [task["task_type"] for task in listing["tasks"]] == ["reminder_list"]
    assert listing["requires_approval"] is False

    cancelling = client.post(
        "/api/v1/planner/plan",
        json={
            "text": "Cancel my reminder",
            "intent": "reminder",
            "source": "explicit",
        },
    ).json()["plan"]
    assert [task["task_type"] for task in cancelling["tasks"]] == ["reminder_cancel"]

    creating = client.post(
        "/api/v1/planner/plan",
        json={
            "text": "Remind me about the standup at 9 AM",
            "intent": "reminder",
            "source": "explicit",
        },
    ).json()["plan"]
    assert [task["task_type"] for task in creating["tasks"]] == ["reminder_create"]


def test_a_reminder_request_without_a_time_reports_what_is_missing(
    client: TestClient,
):
    """The plan says what it still needs rather than inventing a time."""
    plan = client.post(
        "/api/v1/planner/plan",
        json={
            "text": "Remind me about the standup",
            "intent": "reminder",
            "source": "explicit",
        },
    ).json()["plan"]

    assert plan["missing_information"]
    joined = " ".join(plan["missing_information"]).lower()
    assert "due" in joined or "time" in joined
