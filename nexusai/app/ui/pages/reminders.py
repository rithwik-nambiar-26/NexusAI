"""Reminders page: create, list and cancel reminders.

The page states plainly what a reminder can and cannot do. NexusAI
delivers a reminder while it is running; if the application or the
computer is off when a reminder falls due, the reminder is recorded as
missed and reported here the next time NexusAI starts. Nothing on this
page claims a reminder was delivered when it was not.
"""

from __future__ import annotations

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]

from nexusai.app.ui import api_client
from nexusai.app.ui.components import (
    require_backend,
    show_api_error,
)

#: The reminder's delivery guarantee, stated where the user acts.
DELIVERY_NOTICE = (
    "A reminder is delivered **only while NexusAI is running**. If the "
    "application or the computer is switched off, asleep or stopped when a "
    "reminder falls due, it is recorded as **missed** and listed here the "
    "next time NexusAI starts. NexusAI does not register a Windows "
    "scheduled task and does not run any background command of its own."
)

#: The statuses a reminder can be in, and what each one means.
STATUS_MEANINGS = {
    "pending": "Waiting for its time.",
    "fired": "Delivered while NexusAI was running.",
    "missed": "Its time passed while NexusAI was not running. It was not delivered.",
    "cancelled": "Cancelled before it was due.",
}


def render() -> None:
    """Render the Reminders page."""
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")

    st.title("Reminders")
    st.caption(
        "Ask NexusAI to remember something for later. Reminders are stored "
        "in the local database and delivered by a scheduler that runs inside "
        "the NexusAI process."
    )

    if not require_backend():
        return

    st.info(DELIVERY_NOTICE)
    st.divider()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    st.subheader("1 · Create a reminder")

    message = st.text_input(
        "What should the reminder say?",
        placeholder="e.g. Team standup",
        key="reminder_message",
    )

    due_at = st.text_input(
        "When is it due?",
        placeholder=(
            "e.g. 7 AM, tomorrow at 9, 2026-10-25 09:30, in 30 minutes"
        ),
        key="reminder_due_at",
        help=(
            "A time without a date means the next time that comes. A time "
            "that could be morning or evening is reported rather than "
            "guessed."
        ),
    )

    timezone = st.text_input(
        "Timezone (optional)",
        placeholder="e.g. Europe/London",
        key="reminder_timezone",
        help="Leave empty to use this machine's local timezone.",
    )

    if st.button("Create reminder", type="primary", key="reminder_create"):
        if not message.strip():
            st.error("Please say what the reminder is about.")
            return
        if not due_at.strip():
            st.error("Please say when the reminder is due.")
            return
        try:
            response = api_client.create_reminder(
                message=message.strip(),
                due_at=due_at.strip(),
                timezone=timezone.strip() or None,
            )
        except api_client.ApiError as error:
            show_api_error(error)
            return
        st.session_state["reminder_created"] = response.get("reminder") or {}
        st.session_state.pop("reminder_list", None)

    created = st.session_state.get("reminder_created")
    if created:
        st.success(
            f"Stored: **{created.get('message')}** — due "
            f"**{created.get('local_due_at')}** ({created.get('timezone')})."
        )
        st.caption(
            "This is what NexusAI recorded. It is not a claim that the "
            "reminder will be delivered at that time if NexusAI is not "
            "running."
        )

    st.divider()

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    st.subheader("2 · Your reminders")

    columns = st.columns([3, 1])
    status_filter = columns[0].selectbox(
        "Show",
        ["all", "pending", "fired", "missed", "cancelled"],
        key="reminder_status_filter",
    )
    if columns[1].button("Refresh", key="reminder_refresh"):
        st.session_state.pop("reminder_list", None)

    try:
        reminders = st.session_state.get("reminder_list")
        if reminders is None:
            response = api_client.list_reminders(
                status=None if status_filter == "all" else status_filter
            )
            reminders = response.get("reminders") or []
            st.session_state["reminder_list"] = reminders
    except api_client.ApiError as error:
        show_api_error(error)
        return

    if not reminders:
        st.info("There are no reminders yet.")
    else:
        rows = []
        for reminder in reminders:
            rows.append(
                {
                    "id": reminder.get("id"),
                    "reminder": reminder.get("message"),
                    "due (local)": reminder.get("local_due_at"),
                    "timezone": reminder.get("timezone"),
                    "status": reminder.get("status"),
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)

        for reminder in reminders:
            status = reminder.get("status")
            with st.expander(
                f"#{reminder.get('id')} — {reminder.get('message')} ({status})"
            ):
                st.caption(STATUS_MEANINGS.get(status, ""))
                st.write(f"Due at: `{reminder.get('due_at')}`")
                st.write(f"Local time: `{reminder.get('local_due_at')}`")
                st.write(f"Timezone: `{reminder.get('timezone')}`")
                if status == "pending" and st.button(
                    "Cancel this reminder",
                    key=f"reminder_cancel_{reminder.get('id')}",
                ):
                    try:
                        api_client.cancel_reminder(int(reminder.get("id")))
                    except api_client.ApiError as error:
                        show_api_error(error)
                        continue
                    st.session_state.pop("reminder_list", None)
                    st.success(f"Reminder #{reminder.get('id')} cancelled.")
                    st.rerun()
