"""Run History page: the workflow runs the backend has recorded.

Runs are persisted in the SQLite database, so this page shows real
history rather than an in-memory placeholder. What is *not* persisted is
the individual execution report: the plan is stored, and the run's status
and intent, but the per-task output of a past run is not replayed.
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


def render() -> None:
    """Render the Run History page."""
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")

    st.title("Run History")
    st.caption(
        "Workflow runs recorded in the local SQLite database. Each run stores the "
        "request, the classified intent, the plan and the outcome."
    )

    if not require_backend():
        return

    st.divider()

    if st.button("Refresh", key="history_refresh"):
        try:
            listing = api_client.list_runs()
        except api_client.ApiError as error:
            show_api_error(error)
            return
        st.session_state["history_runs"] = listing

    listing = st.session_state.get("history_runs")
    if listing is None:
        try:
            listing = api_client.list_runs()
        except api_client.ApiError as error:
            show_api_error(error)
            return
        st.session_state["history_runs"] = listing

    runs = listing.get("runs") or []
    total = listing.get("total", len(runs))

    if not runs:
        st.info(
            "No runs recorded yet. Use the Task Automation page to plan and "
            "execute a request; each execution is saved here."
        )
        return

    st.caption(f"{total} run(s) recorded, showing the most recent {len(runs)}.")

    st.dataframe(
        [
            {
                "id": run.get("id"),
                "request": (run.get("goal") or "")[:70],
                "intent": run.get("intent") or "-",
                "status": run.get("status"),
                "created": run.get("created_at"),
            }
            for run in runs
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    st.subheader("Run detail")

    run_ids = [run.get("id") for run in runs if run.get("id") is not None]
    if not run_ids:
        return

    selected = st.selectbox("Choose a run", run_ids, key="history_selected")
    if st.button("Load run", key="history_load"):
        try:
            detail = api_client.get_run(selected)
        except api_client.ApiError as error:
            show_api_error(error)
            return
        st.session_state["history_detail"] = detail.get("run")

    detail = st.session_state.get("history_detail")
    if not detail:
        return

    columns = st.columns(3)
    columns[0].metric("Intent", (detail.get("intent") or "-").replace("_", " "))
    columns[1].metric("Status", detail.get("status") or "-")
    columns[2].metric("Terminal state", detail.get("terminal_state") or "-")

    st.markdown("**Request**")
    st.write(detail.get("goal"))

    steps = detail.get("steps") or []
    if steps:
        st.markdown("**Steps**")
        st.dataframe(
            [
                {
                    "index": step.get("step_index"),
                    "step id": step.get("step_id"),
                    "type": step.get("step_type"),
                    "tool": step.get("tool"),
                    "verification": step.get("verification_result"),
                }
                for step in steps
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("This run has no recorded steps.")

    plan_text = detail.get("plan")
    if plan_text:
        with st.expander("Stored plan"):
            st.json(plan_text)

    st.caption(
        "The plan, intent, status and request are persisted. The per-task output "
        "of a past run is not replayed here; it is returned by the execution "
        "response that produced the run."
    )
