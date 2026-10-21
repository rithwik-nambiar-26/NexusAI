"""Document Intelligence page (RAG) — scheduled for Day 4."""

from __future__ import annotations

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]


def render() -> None:
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")
    st.title("Document Intelligence")
    st.caption("Retrieve grounded evidence from user-provided documents.")

    st.divider()
    st.info(
        "RAG module scheduled for Day 4. This page will let you upload "
        "documents, index them locally, and cite evidence per workflow step.",
        icon="📄",
    )
    st.subheader("Placeholder: document upload")
    st.file_uploader("Upload a document (coming Day 4)", type=["txt", "md", "pdf"], disabled=True)
    st.subheader("Placeholder: retrieval query")
    st.text_input("Ask about your documents (coming Day 4)", disabled=True)
    st.button("Retrieve", disabled=True)


if __name__ == "__main__":  # pragma: no cover
    render()
