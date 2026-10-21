"""Task Automation page: submit a goal and view run history."""

from __future__ import annotations

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]


def render() -> None:
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")
    st.title("Task Automation")
    st.caption(
        "Submit a natural-language goal; the workflow engine plans, executes and verifies it."
    )

    st.divider()
    st.subheader("Create a new goal")
    goal = st.text_area(
        "Goal",
        placeholder="e.g. Research renewable energy options and summarise the top three with citations",
        height=100,
    )
    intent = st.text_input("Intent hint (optional)", placeholder="e.g. research")
    condition = st.text_input("Experiment condition (optional)", placeholder="e.g. A, B or C")
    submitted = st.button("Create run", type="primary")

    if submitted:
        if not goal.strip():
            st.error("Please enter a goal.")
            return
        # Retain the submitted values so the form state is not lost while the
        # submit-to-API wiring is pending (Day 5).
        st.session_state["pending_goal"] = goal
        st.session_state["pending_intent"] = intent
        st.session_state["pending_condition"] = condition
        # The run creation API is available at POST /api/v1/workflows?goal=...
        # Wiring the HTTP call is scheduled once the FastAPI backend is verified.
        st.warning(
            "Submit-to-API wiring is scheduled for Day 5 (executor). "
            "Today the API exists at POST /api/v1/workflows?goal=... but "
            "the UI call is intentionally not wired until the agent runs end to end.",
            icon="🚧",
        )
        st.subheader("Captured submission")
        st.json(
            {
                "goal": goal,
                "intent": intent or None,
                "condition": condition or None,
            }
        )

    st.divider()
    st.subheader("Run history")
    st.info(
        "Run history reads from `GET /api/v1/workflows`. Wiring is scheduled "
        "for Day 7 (end-to-end integration). The runs page placeholder shows "
        "the table shape that will be populated.",
        icon="📋",
    )
    st.table(
        {
            "Run ID": [],
            "Goal": [],
            "Intent": [],
            "Condition": [],
            "Status": [],
            "Terminal state": [],
            "Created at": [],
        }
    )


if __name__ == "__main__":  # pragma: no cover
    render()
