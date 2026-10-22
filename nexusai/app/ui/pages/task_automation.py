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
    intent_candidates,
    require_backend,
    show_api_error,
    show_execution_report,
    show_intent,
    show_intent_candidates,
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
    # Selecting a document restricts the whole workflow to it: the reading,
    # the extraction and the summary all act on that document alone.
    selected_documents: list[str] = []
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
                "than guessing. The selected document restricts the whole "
                "workflow to it."
            ),
        )
        if choice != "(none)":
            selected_documents = [choice.split("—")[-1].strip()]
            st.caption(f"The plan will read document `{selected_documents[0]}`.")

        # Cross-document analysis is possible, but only when the user asks
        # for it. It is never the default.
        across_all = st.checkbox(
            "Search across all indexed documents",
            key="task_across_all_documents",
            help=(
                "Use this only when the request genuinely spans several "
                "documents. Each document is summarised separately; they are "
                "never blended into one summary."
            ),
        )
        if across_all and selected_documents:
            selected_documents = [
                document.get("document_id")
                for document in documents
                if document.get("document_id")
            ]
            st.caption(
                f"The plan will read {len(selected_documents)} documents, each "
                "summarised separately."
            )
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

        # A new request invalidates any plan, execution and override left
        # over from a previous one. Without this, the Plan section below
        # would keep showing a stale plan — for a different request, and
        # possibly for an intent that is not this request's at all.
        st.session_state.pop("task_plan", None)
        st.session_state.pop("task_execution", None)
        st.session_state.pop("task_run_id", None)
        st.session_state.pop("task_override_applied", None)
        st.session_state.pop("task_confirmed_intent", None)
        st.session_state.pop("task_intent_choice", None)
        st.session_state.pop("task_approvals", None)

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
    confirmed = st.session_state.get("task_confirmed_intent")
    status = result.get("status")

    if override:
        st.info(
            f"Using the explicit intent `{override}` instead of the classifier's "
            f"prediction."
        )
        show_intent(override, result.get("confidence"), "explicit")
    elif confirmed:
        st.success(
            f"**Intent confirmed by you:** `{confirmed}`. The plan will be built "
            "from this choice, and the plan records that it came from you "
            "rather than from the classifier."
        )
        show_intent(confirmed, result.get("confidence"), "confirmed")
    else:
        show_intent(
            result.get("predicted_intent"),
            result.get("confidence"),
            result.get("status"),
        )

    # The classifier's own request for clarification is only shown while
    # it is still outstanding. Once the user has confirmed the intent, the
    # question has been answered and repeating it would be misleading.
    if result.get("clarification_question") and not (override or confirmed):
        st.warning(f"**Clarification needed** {result['clarification_question']}")
    if result.get("abstention_reason"):
        st.info(f"**Note** {result['abstention_reason']}")

    # ------------------------------------------------------------------
    # Intent confirmation
    # ------------------------------------------------------------------
    # The classifier is experimental: on a 12-class taxonomy it is often
    # unsure even when its top-ranked intent is the right one. Rather than
    # block the request or plan it on a guess, the candidate intents are
    # shown with their scores and the user chooses. The choice is then
    # planned as an explicit intent, which the planner records.
    section = 2
    if not override and not confirmed and status != "confident":
        section += 1
        st.divider()
        st.subheader(f"{section} · Confirm the intent")

        candidates = intent_candidates(result)
        st.caption(
            "The classifier was not confident about this request. These are the "
            "intents it ranked, with the score it gave each one. Choose the "
            "one that matches what you asked for."
        )
        show_intent_candidates(candidates)

        # The radio shows the score beside each candidate. The option text
        # is the value, so the choice maps back to an intent through a
        # lookup rather than through a formatting function.
        options: list[str] = []
        intent_by_option: dict[str, str] = {}
        for candidate in candidates:
            option = f"{candidate['label']} ({candidate['score']:.3f})"
            if candidate["is_refusal"]:
                option += " (refusal path)"
            options.append(option)
            intent_by_option[option] = candidate["intent"]

        choice = st.radio(
            "Which intent did you mean?",
            options,
            index=0,
            key="task_intent_choice",
        )

        if st.button("Confirm this intent", key="task_confirm_intent"):
            st.session_state["task_confirmed_intent"] = intent_by_option[choice]
            # A new intent invalidates any plan built from the old one.
            st.session_state.pop("task_plan", None)
            st.session_state.pop("task_execution", None)
            st.session_state.pop("task_run_id", None)
            st.rerun()

    # ------------------------------------------------------------------
    # Plan
    # ------------------------------------------------------------------
    section += 1
    st.divider()
    st.subheader(f"{section} · Plan")

    plan_request = st.session_state.get("task_request_used", request_text)

    if override or confirmed:
        # The intent came from the user, either through the override box or
        # through the confirmation flow, so it is planned as an explicit
        # choice.
        intent_to_use = override or confirmed
        plan_source = "explicit"
    else:
        # The classifier's own prediction is planned, and its status is
        # carried through so that an uncertain classification produces a
        # request for clarification rather than a plan built on a guess.
        intent_to_use = result.get("predicted_intent")
        plan_source = "classifier"

    if st.button("Generate plan", key="task_generate_plan"):
        with st.spinner("Building the plan..."):
            try:
                plan_response = api_client.create_plan(
                    plan_request,
                    intent=intent_to_use,
                    source=plan_source,
                    intent_status=(
                        None
                        if plan_source == "explicit"
                        else result.get("status")
                    ),
                    intent_confidence=(
                        None
                        if plan_source == "explicit"
                        else result.get("confidence")
                    ),
                    # The selected documents are sent with the request, so
                    # the planner puts them on every document task. They
                    # are not patched onto the plan afterwards, which would
                    # leave the plan's own record of the source
                    # inconsistent with what actually runs.
                    source_documents=list(selected_documents) or None,
                )
            except api_client.ApiError as error:
                show_api_error(error)
                return
        plan = plan_response.get("plan") or {}

        st.session_state["task_plan"] = plan
        # The plan is bound to the request and the documents it was built
        # from. A plan built for a different request, or for different
        # documents, must not be executed against the current selection.
        st.session_state["task_plan_context"] = {
            "request": plan_request,
            "documents": list(selected_documents),
        }
        # A new plan invalidates any approval granted for the old one.
        st.session_state.pop("task_execution", None)
        st.session_state.pop("task_run_id", None)
        st.session_state.pop("task_approvals", None)

    plan = st.session_state.get("task_plan")
    if not plan:
        st.info("Generate a plan to see its tasks, dependencies and execution order.")
        return

    show_plan(plan)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    section += 1
    st.divider()
    st.subheader(f"{section} · Execution")

    # A plan is bound to the request and the documents it was built from.
    # Executing a plan that was built for a different request, or for a
    # different document, would act on something the user did not ask
    # for, so it is refused rather than run.
    context = st.session_state.get("task_plan_context") or {}
    stale_reasons: list[str] = []
    if context.get("request") not in (None, request_text):
        stale_reasons.append("the request text has changed since the plan was made")
    if list(context.get("documents") or []) != list(selected_documents):
        stale_reasons.append("the selected document has changed since the plan was made")

    if stale_reasons:
        st.warning(
            "**This plan is out of date** — "
            + "; ".join(stale_reasons)
            + ". Generate a new plan before executing it."
        )
        st.button("Generate plan", key="task_generate_plan_stale", disabled=True)
    elif st.button("Execute plan", type="primary", key="task_execute"):
        with st.spinner("Executing the plan..."):
            try:
                execution = api_client.execute_plan(
                    plan, approvals=st.session_state.get("task_approvals") or []
                )
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

    # ------------------------------------------------------------------
    # Approval
    # ------------------------------------------------------------------
    # A capability that changes state waits for an explicit decision. The
    # approval is bound to the task and to its validated inputs, so it
    # cannot be carried over to a different set of inputs.
    pending = report.get("pending_approval_task_ids") or []
    approvals = report.get("approvals") or []
    if pending and approvals:
        section += 1
        st.divider()
        st.subheader(f"{section} · Approval needed")

        for approval in approvals:
            if approval.get("state") != "pending":
                continue
            st.warning(
                f"**{approval.get('capability')}** needs your approval before it "
                f"runs."
            )
            st.caption(approval.get("reason") or "")
            st.write(f"Task: `{approval.get('task_id')}`")

            approve_column, deny_column = st.columns(2)
            if approve_column.button(
                "Approve", key=f"task_approve_{approval.get('task_id')}"
            ):
                _record_approval_decision(approval, granted=True)
                st.rerun()
            if deny_column.button(
                "Deny", key=f"task_deny_{approval.get('task_id')}"
            ):
                _record_approval_decision(approval, granted=False)
                st.rerun()

    if st.session_state.get("task_run_id"):
        st.caption(
            f"Saved as workflow run #{st.session_state['task_run_id']}. "
            "See the Run History page."
        )


def _record_approval_decision(approval: dict, *, granted: bool) -> None:
    """Record an approval decision and keep it for the next execution.

    The decision is sent to the backend, which records it against the
    report it is holding. The approved request is then re-sent with the
    next execution, because the approval is bound to the task's inputs and
    the executor checks that binding.
    """
    from nexusai.app.ui import api_client

    try:
        response = api_client.approve_task(
            task_id=approval.get("task_id"),
            granted=granted,
        )
    except api_client.ApiError as error:
        show_api_error(error)
        return

    report = response.get("report") or {}
    st.session_state["task_execution"] = report
    st.session_state["task_approvals"] = report.get("approvals") or []
