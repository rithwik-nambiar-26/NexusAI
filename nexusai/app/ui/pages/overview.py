"""Overview page: what NexusAI is and what is actually implemented."""

from __future__ import annotations

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]

from nexusai.app.ui import api_client
from nexusai.app.ui.components import require_backend, show_api_error
from nexusai.app.ui.config import API_BASE_URL

#: Objectives and the phase that implements them.
OBJECTIVES = [
    ("O1", "Interpret natural-language goals and classify task intent", "Days 2 & 2.2"),
    ("O2", "Decompose goals into executable, dependency-aware steps", "Day 3"),
    ("O3", "Retrieve relevant information from user-provided documents", "Day 4"),
    ("O4", "Secure tool execution with registered tools and validated inputs", "Day 5"),
    ("O5", "Verification, bounded retries, failure handling, replanning", "Not started"),
    ("O6", "Evaluate with measurable metrics", "Not started"),
]

#: What the running system can actually do today.
IMPLEMENTED = [
    "Intent classification over a 12-class taxonomy (ML classifier)",
    "Structured planning with typed tasks and a dependency graph",
    "Document ingestion for PDF, DOCX, TXT and Markdown",
    "Local retrieval with traceable source references",
    "Grounded question answering and summarisation with citations",
    "An explicit tool registry with input and output schema validation",
    "Controlled execution with approval bound to task inputs",
    "CSV profiling and group-by aggregation",
]

#: What exists in the design but is not built yet.
NOT_YET = [
    "Independent verification of a result (O5) — planned for Day 6",
    "Adaptive replanning after a failure (O5) — planned for Day 6",
    "The execution report generator (O5/O6) — planned for Day 7",
    "The experiment harness and the A/B/C comparative evaluation (O6) — planned for Day 7",
    "A local LLM planning or answering backend — optional by design",
]


def render() -> None:
    """Render the Overview page."""
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")

    st.title("Overview")
    st.caption(
        "NexusAI decomposes a natural-language request into a validated plan and "
        "executes the parts it has registered tools for."
    )

    st.divider()

    st.subheader("What it does")
    st.write(
        "NexusAI is an AI-powered personal task automation platform. It "
        "classifies the intent of a request, decomposes it into a typed plan "
        "with an explicit dependency graph, and executes the tasks whose "
        "capabilities are registered — refusing to run anything that has not "
        "been registered or approved."
    )

    st.subheader("Research question")
    st.info(
        '"Can an AI-driven workflow engine autonomously decompose, execute, '
        'verify and adapt multi-step everyday tasks using heterogeneous '
        'real-time information?"'
    )
    st.caption(
        "This is the hypothesis under investigation, not an established result. "
        "The comparative evaluation of the rule-based, LLM-only and hybrid "
        "conditions is not complete."
    )

    st.subheader("Research objectives")
    st.dataframe(
        [
            {"id": oid, "objective": text, "phase": phase}
            for oid, text, phase in OBJECTIVES
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("Implemented and tested")
    for item in IMPLEMENTED:
        st.markdown(f"- ✅ {item}")

    st.subheader("Not yet implemented")
    for item in NOT_YET:
        st.markdown(f"- ⏳ {item}")

    st.divider()
    st.subheader("System")
    if require_backend():
        try:
            status = api_client.system_status()
            tools = api_client.list_execution_tools()
        except api_client.ApiError as error:
            show_api_error(error)
            return

        columns = st.columns(3)
        columns[0].metric("Backend", API_BASE_URL)
        columns[1].metric("Version", status.get("version", "-"))
        columns[2].metric(
            "Registered capabilities", (tools or {}).get("count", 0)
        )
        st.caption(
            "Phase 1, Days 1–5 complete. Day 6 (independent verification and "
            "adaptive recovery) and Day 7 (experiment harness) are not started."
        )
