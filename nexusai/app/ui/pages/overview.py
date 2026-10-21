"""Overview page: project identity, objectives and honest status."""

from __future__ import annotations

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]

from nexusai.app.ui.config import APP_NAME, APP_VERSION, TAGLINE, page_config


def _not_implemented_box(feature: str, day: str | None = None) -> None:
    """Render an honest placeholder for unimplemented functionality."""
    if st is None:
        return
    detail = f"Scheduled for {day}." if day else "Not yet implemented."
    st.info(
        f"**{feature}** — {detail}",
        icon="📌",
    )


def render() -> None:
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")
    page_config()

    st.title(f"{APP_NAME} v{APP_VERSION}")
    st.caption(TAGLINE)

    st.subheader("About")
    st.write(
        "NexusAI is an AI-powered personal task automation platform that "
        "transforms natural-language goals into structured, executable, "
        "verifiable and adaptive workflows. It interprets user intentions, "
        "decomposes goals into smaller tasks, identifies suitable tools, "
        "executes approved operations, verifies outcomes, recovers from "
        "failures and produces a transparent execution report."
    )

    st.subheader("Research objectives")
    objectives = [
        "O1 — Interpret natural-language user goals and classify task intent.",
        "O2 — Decompose goals into executable, dependency-aware steps.",
        "O3 — Integrate RAG over user-provided documents.",
        "O4 — Secure tool execution with registered tools and validated inputs.",
        "O5 — Execution verification, bounded retries, failure handling, adaptive replanning.",
        "O6 — Evaluate with measurable completion, quality, accuracy and recovery metrics.",
    ]
    for objective in objectives:
        st.markdown(f"- {objective}")

    st.subheader("Architecture")
    st.write(
        "Components: goal intake, intent router, planner, RAG module, tool "
        "registry, executor, verifier, replanner and report generator. See "
        "`docs/architecture/system_overview.md`."
    )

    st.divider()
    st.subheader("Implemented today (Day 1)")
    st.markdown(
        "- Python project configuration (`pyproject.toml`, `ruff`, `pytest`)\n"
        "- FastAPI backend with health, system status and workflow-run APIs\n"
        "- SQLite persistence (workflow runs + execution steps)\n"
        "- Streamlit application shell (this page)\n"
        "- Structured logging with request-correlation IDs\n"
        "- Centralised Pydantic settings; `.env` never committed\n"
        "- Initial test suite\n"
    )

    st.divider()
    st.subheader("Coming in Phase 1 (Days 2-7)")
    st.markdown(
        "- Day 2 — Intent router (classifier + LLM fallback)\n"
        "- Day 3 — Structured planner (schema + dependencies)\n"
        "- Day 4 — RAG module (index + cited passages)\n"
        "- Day 5 — Tool registry + executor (validation + approval gates)\n"
        "- Day 6 — Verifier + bounded replanner\n"
        "- Day 7 — Report generator, experiment harness, first evaluation pass\n"
    )

    st.divider()
    st.subheader("Second review")
    st.write(
        "College Second Review: 23–25 October 2026. Evidence tracked in "
        "`docs/project_management/review_readiness_matrix.md`."
    )


if __name__ == "__main__":  # pragma: no cover
    render()
