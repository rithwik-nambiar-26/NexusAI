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
from nexusai.ml.schemas import IntentCategory

#: Intents that are refusal paths: they never produce an executable plan.
#: They are listed in the confirmation flow so the user can see that the
#: classifier recognised them, and so choosing one is refused honestly
#: rather than silently.
REFUSAL_INTENTS: frozenset[str] = frozenset(
    intent.value for intent in IntentCategory.special()
)

#: Intents that map to an executable workflow.
SUPPORTED_INTENTS: frozenset[str] = frozenset(
    intent.value for intent in IntentCategory.supported()
)


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


def intent_candidates(
    result: dict[str, Any], limit: int = 5
) -> list[dict[str, Any]]:
    """Return the ranked intent candidates from a classification result.

    The classifier returns a score for every intent in the taxonomy, so the
    candidates are simply the highest-scoring ones. Ranking by score rather
    than by the confidence threshold is deliberate: the top-ranked intent is
    frequently the correct one even when its probability is low, and the
    user is in a better position to choose than a fixed cut-off is.

    Args:
        result: The classification result, as returned by the intent API.
        limit: The maximum number of candidates to return.

    Returns:
        A list of candidate dictionaries, highest score first. Each carries
        the intent, a readable label, the score, and whether the intent is
        a refusal path.
    """
    scores = result.get("all_scores") or {}
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]

    candidates: list[dict[str, Any]] = []
    for intent, score in ranked:
        candidates.append(
            {
                "intent": intent,
                "label": intent.replace("_", " "),
                "score": float(score),
                "is_refusal": intent in REFUSAL_INTENTS,
                "is_supported": intent in SUPPORTED_INTENTS,
            }
        )
    return candidates


def show_intent_candidates(candidates: list[dict[str, Any]]) -> None:
    """Show the ranked intent candidates and their scores."""
    if not candidates:
        st.info("The classifier did not return any candidate intents.")
        return

    rows = []
    for candidate in candidates:
        kind = "refusal path" if candidate["is_refusal"] else "executable"
        rows.append(
            {
                "intent": candidate["label"],
                "score": f"{candidate['score']:.3f}",
                "kind": kind,
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


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
            "source_document": plan.get("source_document"),
        }
    )

    # The document the plan is about is shown in full, because it decides
    # which document the capabilities will read.
    source_document = plan.get("source_document")
    if source_document:
        st.info(f"**Source document:** `{source_document}`")

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


def show_summary(output: dict[str, Any]) -> None:
    """Show a summary in readable sections, with its evidence.

    The raw JSON is still available under an expander, but the summary
    itself is presented as the overview, decisions and action items it
    actually contains, so a reader does not have to read the JSON to see
    what was found.
    """
    method = output.get("method")
    if method == "llm":
        st.caption("Written by the configured local language model.")
    elif method == "extractive":
        st.caption(
            "Extracted from the source text: every statement below is taken "
            "from the document, with its source reference."
        )
    elif method == "none":
        st.caption("No summary was produced.")

    sections = output.get("sections") or []
    if sections:
        for section in sections:
            items = section.get("items") or []
            if not items:
                continue
            st.markdown(f"**{section.get('title') or section.get('name')}**")
            for item in items:
                text = item.get("text") or ""
                suffix = []
                if item.get("owner"):
                    suffix.append(f"owner: {item['owner']}")
                if item.get("due"):
                    suffix.append(f"due: {item['due']}")
                reference = item.get("source_reference")
                note = f" *({', '.join(suffix)})*" if suffix else ""
                citation = f" — `{reference}`" if reference else ""
                st.write(f"- {text}{note}{citation}")
    else:
        summary_text = output.get("summary_text") or ""
        if summary_text:
            st.markdown(summary_text)

    evidence = output.get("evidence") or []
    if evidence:
        with st.expander(f"Evidence ({len(evidence)} passages)"):
            for span in evidence:
                st.write(f"**{span.get('source_reference')}**")
                st.write(span.get("text") or "")

    with st.expander("Raw output"):
        st.json(output)


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
                # A summary is shown as the readable sections it contains,
                # rather than only as raw JSON.
                if result.get("capability") == "llm.summarise":
                    show_summary(output)
                else:
                    st.json(output)

    # A summary is shown in full outside the task expander, because it is
    # the answer the user asked for.
    for result in results:
        if result.get("capability") != "llm.summarise":
            continue
        output = result.get("output")
        if not output:
            continue
        st.divider()
        st.markdown("**Summary**")
        show_summary(output)


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
