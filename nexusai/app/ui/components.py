"""Shared helpers for the Streamlit pages.

Formatting and error handling live here so every page presents the
backend's answers the same way, and so a backend failure is always
visible rather than swallowed.
"""

from __future__ import annotations

import json
import time
from typing import Any

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]


from nexusai.app.ui.api_client import ApiError, backend_is_reachable
from nexusai.app.ui.config import API_BASE_URL


def require_backend() -> bool:
    """Check the backend is reachable and show a clear message if not.

    The result is cached for the session so a page does not wait on a
    network timeout on every rerun. A user can force a re-check with the
    "Reconnect" button.

    Returns:
        True when the backend is reachable.
    """
    if st.session_state.get("backend_reachable"):
        return True

    # A cached negative result is only honoured briefly, so a backend
    # started after the page was first loaded is picked up.
    checked_at = st.session_state.get("backend_checked_at")
    if checked_at is not None and (time.monotonic() - checked_at) < 15:
        _show_backend_unreachable(
            st.session_state.get("backend_error")
            or "The NexusAI backend is not reachable."
        )
        return False

    reachable, message = backend_is_reachable()
    st.session_state["backend_checked_at"] = time.monotonic()
    st.session_state["backend_reachable"] = reachable
    st.session_state["backend_error"] = None if reachable else message

    if not reachable:
        _show_backend_unreachable(message)
        return False
    return True


def _show_backend_unreachable(message: str) -> None:
    """Show the standard 'backend unreachable' message."""
    st.error(
        f"**The NexusAI backend is not reachable.**\n\n"
        f"{message}\n\n"
        f"Start it in a second terminal with:\n\n"
        f"```\npython -m nexusai serve\n```\n\n"
        f"The UI is configured to talk to `{API_BASE_URL}`."
    )


def reset_backend_check() -> None:
    """Forget the cached backend reachability result."""
    st.session_state["backend_reachable"] = False
    st.session_state["backend_checked_at"] = None
    st.session_state["backend_error"] = None


def show_api_error(error: ApiError) -> None:
    """Show a backend error in a way the user can act on."""
    st.error(str(error))
    if error.status_code is not None:
        st.caption(f"HTTP status: {error.status_code}")


def status_badge(status: str) -> str:
    """Return an HTML badge for a status string."""
    mapping = {
        "completed": "badge-available",
        "ready": "badge-available",
        "ok": "badge-available",
        "answered": "badge-available",
        "confident": "badge-available",
        "skipped": "badge-pending",
        "low_confidence": "badge-pending",
        "low confidence": "badge-pending",
        "awaiting_approval": "badge-pending",
        "partially_completed": "badge-pending",
        "blocked": "badge-pending",
        "pending": "badge-pending",
        "failed": "badge-unavailable",
        "invalid": "badge-unavailable",
        "error": "badge-unavailable",
    }
    css_class = mapping.get(status.lower(), "badge-pending")
    return (
        f'<span class="status-badge {css_class}">{status}</span>'
    )


def render_status_badge(status: str) -> None:
    """Render a status badge."""
    st.markdown(status_badge(status), unsafe_allow_html=True)


def pretty_json(value: Any) -> str:
    """Render a value as indented JSON."""
    try:
        return json.dumps(value, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)


def show_intent(intent: str | None, confidence: float | None, status: str | None) -> None:
    """Show the classified intent, its confidence and status."""
    if intent is None:
        st.warning("No intent was classified for this request.")
        return

    columns = st.columns(3)
    columns[0].metric("Intent", intent.replace("_", " "))
    if confidence is not None:
        columns[1].metric("Confidence", f"{confidence:.3f}")
    if status:
        with columns[2]:
            st.markdown("**Status**")
            render_status_badge(status)


def show_plan(plan: dict[str, Any]) -> None:
    """Show a generated plan: intent, tasks, dependencies and order."""
    st.markdown("**Plan**")
    st.json(
        {
            "plan_id": plan.get("plan_id"),
            "intent": plan.get("intent"),
            "plan_status": plan.get("plan_status"),
            "requires_approval": plan.get("requires_approval"),
            "source": plan.get("source"),
        }
    )

    tasks = plan.get("tasks") or []
    if not tasks:
        st.info("This plan contains no tasks.")
        return

    st.markdown("**Tasks**")
    rows = []
    for task in tasks:
        rows.append(
            {
                "task": task.get("task_name"),
                "type": task.get("task_type"),
                "capabilities": ", ".join(task.get("required_capabilities") or []),
                "depends on": ", ".join(task.get("dependencies") or []) or "-",
                "status": task.get("status"),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    order = plan.get("execution_order") or []
    if order:
        st.markdown("**Execution order**")
        st.write(" → ".join(order))

    if plan.get("missing_information"):
        st.warning("**Missing information**")
        for item in plan["missing_information"]:
            st.write(f"- {item}")

    if plan.get("unsupported_operations"):
        st.error("**Unsupported operations**")
        for item in plan["unsupported_operations"]:
            st.write(f"- {item}")

    if plan.get("validation_errors"):
        st.error("**Validation errors**")
        for item in plan["validation_errors"]:
            st.write(f"- {item}")

    if plan.get("clarification_required"):
        question = plan.get("clarification_question")
        st.warning(f"**Clarification required** {question or ''}")


def show_execution_report(report: dict[str, Any]) -> None:
    """Show an execution report: status, per-task results and approval state."""
    st.markdown("**Execution**")
    columns = st.columns(2)
    with columns[0]:
        st.markdown("Status")
        render_status_badge(report.get("status", "unknown"))
    columns[1].metric("Tasks", len(report.get("task_results") or []))

    results = report.get("task_results") or []
    if not results:
        st.info("No task results were reported.")
        return

    rows = []
    for result in results:
        rows.append(
            {
                "task": result.get("task_id"),
                "capability": result.get("capability") or "-",
                "status": result.get("status"),
                "attempts": result.get("attempts", 0),
                "seconds": f"{result.get('elapsed_seconds', 0.0):.3f}",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    for result in results:
        task_id = result.get("task_id")
        status = result.get("status")
        with st.expander(f"{task_id} — {status}"):
            if result.get("capability"):
                st.caption(f"Capability: {result['capability']}")
            if result.get("approval_id"):
                st.info(f"Awaiting approval (id {result['approval_id']})")
            if result.get("error"):
                st.error(f"{result.get('error_category')}: {result['error']}")
            output = result.get("output")
            if output:
                st.json(output)


def show_evidence(evidence: list[dict[str, Any]]) -> None:
    """Show retrieved evidence with its source references."""
    if not evidence:
        st.info("No evidence was retrieved.")
        return

    for item in evidence:
        reference = item.get("source_reference", "")
        score = item.get("score")
        with st.container(border=True):
            st.markdown(f"**{reference}**")
            if score is not None:
                st.caption(f"Similarity score: {score:.4f}")
            st.write(item.get("text", ""))
