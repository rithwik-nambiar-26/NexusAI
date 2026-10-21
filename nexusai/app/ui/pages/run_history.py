"""Run History page — scheduled for Day 7."""

from __future__ import annotations

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]


def render() -> None:
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")
    st.title("Run History")
    st.caption("Inspect workflow runs, execution steps and verification results.")

    st.divider()
    st.info(
        "Run history is populated by the experiment harness on Day 7. "
        "The table shape below is the contract the API will honour.",
        icon="🕒",
    )
    st.table(
        {
            "Run ID": [],
            "Goal": [],
            "Intent": [],
            "Condition": [],
            "Status": [],
            "Verification": [],
            "Retries": [],
            "Execution time (ms)": [],
        }
    )


if __name__ == "__main__":  # pragma: no cover
    render()
