"""System status page — reads GET /api/v1/system/status."""

from __future__ import annotations

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]


def render() -> None:
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")
    st.title("System status")
    st.caption("Honest availability of every service — nothing is assumed available.")

    st.divider()
    st.info(
        "This page reads `GET /api/v1/system/status` from the FastAPI backend. "
        "Start the backend with `nexusai serve` and refresh.",
        icon="🛡️",
    )
    st.subheader("Services")
    st.table(
        {
            "Service": ["database", "ollama", "chromadb"],
            "Configured": [True, False, False],
            "Available": [False, False, False],
            "Detail": [
                "Probe at request time; status shown on refresh",
                "Not configured; no URL set",
                "Not configured; no URL set",
            ],
        }
    )
    st.subheader("Limits")
    st.table(
        {
            "Limit": [
                "Upload max size (MB)",
                "Max execution steps",
                "Max retry budget",
                "Max execution time (seconds)",
            ],
            "Value": [25, 50, 2, 300],
        }
    )


if __name__ == "__main__":  # pragma: no cover
    render()
