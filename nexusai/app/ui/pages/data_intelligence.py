"""Data Intelligence page (tabular ML demonstrations) — scheduled for Day 4-5."""

from __future__ import annotations

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]


def render() -> None:
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")
    st.title("Data Intelligence")
    st.caption("Tabular data analysis and ML demonstration area.")

    st.divider()
    st.info(
        "Dataset documentation lives under `experiments/datasets/`. "
        "Actual dataset views are scheduled after the experiment foundation "
        "is stable.",
        icon="📊",
    )
    st.subheader("Placeholder: dataset overview")
    st.table(
        {
            "Dataset": [],
            "Purpose": [],
            "Source": [],
            "License": [],
            "Rows": [],
        }
    )
    st.caption("No external data has been collected; fixtures only.")


if __name__ == "__main__":  # pragma: no cover
    render()
