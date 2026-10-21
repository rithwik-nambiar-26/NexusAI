"""Task Automation page: submit a request, inspect the plan, execute it.

This is the primary demonstration surface. It shows the whole path a
request takes: classification, planning, and execution through the tool
registry.
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
    show_execution_report,
    show_intent,
    show_plan,
)


def render() -> None:
    """Render the Task Automation page."""
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")

    st.title("Task Automation")
    st.caption(
        "Submit a natural-language request. The classifier determines the intent, "
        "the planner produces a dependency-aware plan, and the executor runs the "
        "registered capabilities."
    )

    if not require_backend():
        return

    st.divider()

    # ------------------------------------------------------------------
    # Request
    # ------------------------------------------------------------------
    st.subheader("1 · Request")
    request_text = st.text_area(
        "What would you like NexusAI to do?",
        placeholder=(
            "e.g. Read data/sample/product_manual.md and summarise the warranty "
            "conditions."
        ),
        height=100,
        key="task_request_text",
    )

    with st.expander("Advanced — override the classified intent"):
        st.caption(
            "Leave this empty to use the classifier's prediction. Supplying an "
            "intent bypasses classification, which is useful for demonstrating "
            "a specific workflow."
        )
        override = st.text_input(
            "Intent override",
            placeholder="e.g. document_summarisation",
            key="task_intent_override",
        )
        override = override.strip() or None

    # --- document selection ---------------------------------------------
    # A request that says "the uploaded document" does not name a file.
    # Rather than guess between several indexed documents, the user picks.
    selected_document = None
    try:
        listing = api_client.list_documents()
        documents = listing.get("documents") or []
    except api_client.ApiError:
        documents = []

    if documents:
        options = ["(none)"] + [
            f"{document.get('name')} — {document.get('document_id')}"
            for document in documents
        ]
        choice = st.selectbox(
            "Document for this request",
            options,
            key="task_document_choice",
            help=(
                "Used when the request refers to a document without naming a "
                "file. With several documents indexed, NexusAI asks rather "
                "than guessing."
            ),
        )
        if choice != "(none)":
            selected_document = choice.split("—")[-1].strip()
            st.caption(f"The plan will read document `{selected_document}`.")
    else:
        st.caption(
            "No documents are indexed yet. Use the Document Intelligence page "
            "to ingest one."
        )

    planned = st.button("Classify and plan", type="primary")

    # ------------------------------------------------------------------
    # Classification and planning
    # ------------------------------------------------------------------
    if planned:
        if not request_text.strip():
            st.error("Please enter a request.")
            return

        with st.spinner("Classifying the request..."):
            try:
                classification = api_client.classify_intent(request_text)
            except api_client.ApiError as error:
                show_api_error(error)
                return

        result = classification.get("result", {})
        st.session_state["task_classification"] = classification
        st.session_state["task_request_used"] = request_text

        # A supplied intent replaces the classifier's prediction.
        if override:
            st.session_state["task_override_applied"] = override

    classification = st.session_state.get("task_classification")
    if not classification:
        return

    st.divider()
    st.subheader("2 · Classification")
    result = classification.get("result", {})

    override = st.session_state.get("task_override_applied")
    if override:
        st.info(
            f"Using the explicit intent `{override}` instead of the classifier's "
            f"prediction."
        )
        show_intent(override, result.get("confidence"), "explicit")
    else:
        show_intent(
            result.get("predicted_intent"),
            result.get("confidence"),
            result.get("status"),
        )

    if result.get("clarification_question"):
        st.warning(f"**Clarification needed** {result['clarification_question']}")
    if result.get("abstention_reason"):
        st.info(f"**Note** {result['abstention_reason']}")

    # ------------------------------------------------------------------
    # Plan
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("3 · Plan")

    plan_request = st.session_state.get("task_request_used", request_text)
    intent_to_use = override or result.get("predicted_intent")

    if st.button("Generate plan", key="task_generate_plan"):
        with st.spinner("Building the plan..."):
            try:
                plan_response = api_client.create_plan(plan_request, intent=intent_to_use)
            except api_client.ApiError as error:
                show_api_error(error)
                return
        plan = plan_response.get("plan") or {}

        # Attach the chosen document to the first document-reading task, so
        # the executor knows which file to read rather than guessing.
        if selected_document:
            for task in plan.get("tasks") or []:
                if "document.read" in (task.get("required_capabilities") or []):
                    task.setdefault("input_parameters", []).append(
                        {
                            "name": "document_id",
                            "value": selected_document,
                            "description": "Document chosen in the UI",
                            "required": True,
                        }
                    )
                    break

        st.session_state["task_plan"] = plan

    plan = st.session_state.get("task_plan")
    if not plan:
        st.info("Generate a plan to see its tasks, dependencies and execution order.")
        return

    show_plan(plan)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("4 · Execution")

    if st.button("Execute plan", type="primary", key="task_execute"):
        with st.spinner("Executing the plan..."):
            try:
                execution = api_client.execute_plan(plan)
            except api_client.ApiError as error:
                show_api_error(error)
                return
        st.session_state["task_execution"] = execution.get("report")
        st.session_state["task_run_id"] = execution.get("run_id")

    report = st.session_state.get("task_execution")
    if not report:
        st.info("Execute the plan to see what actually ran.")
        return

    show_execution_report(report)

    if st.session_state.get("task_run_id"):
        st.caption(
            f"Saved as workflow run #{st.session_state['task_run_id']}. "
            "See the Run History page."
        )
