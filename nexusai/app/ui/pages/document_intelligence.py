"""Document Intelligence page: upload, ingest, retrieve, answer, summarise.

Uploads are written into the shared allowed-root area and ingested
through the same document service the API uses, so the PathPolicy
governs an upload exactly as it governs any other read.
"""

from __future__ import annotations

from pathlib import Path

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]

from nexusai.app.ui import api_client
from nexusai.app.ui.components import (
    require_backend,
    show_api_error,
    show_evidence,
)
from nexusai.app.ui.config import UPLOAD_DIR


def _upload_dir() -> Path:
    """Return the directory uploads are written to, creating it if needed."""
    path = Path(UPLOAD_DIR)
    if not path.is_absolute():
        from nexusai.app.config import REPO_ROOT

        path = REPO_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def render() -> None:
    """Render the Document Intelligence page."""
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")

    st.title("Document Intelligence")
    st.caption(
        "Ingest PDF, DOCX, TXT and Markdown documents, retrieve relevant passages "
        "with their source references, and ask questions the documents can answer."
    )

    if not require_backend():
        return

    st.divider()

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------
    st.subheader("1 · Ingest a document")

    uploaded = st.file_uploader(
        "Choose a file",
        type=["pdf", "docx", "txt", "md", "markdown", "text"],
        key="doc_upload",
    )

    if uploaded is not None and st.button("Ingest uploaded file", key="doc_ingest"):
        with st.spinner(f"Ingesting {uploaded.name}..."):
            try:
                target = _upload_dir() / Path(uploaded.name).name
                target.write_bytes(uploaded.getvalue())
                response = api_client.ingest_document(str(target), name=uploaded.name)
            except api_client.ApiError as error:
                show_api_error(error)
                return
            except OSError as error:
                st.error(f"Could not write the upload: {error}")
                return

        result = response.get("result", {})
        status = result.get("status")
        if status == "ok":
            st.success(result.get("message") or "Ingested.")
            if result.get("duplicate"):
                st.info("This document was already indexed.")
        else:
            st.error(f"**{status}** — {result.get('message') or 'Ingestion failed.'}")

    with st.expander("Ingest a file already in the project"):
        st.caption(
            "The path must sit inside the backend's allowed document roots "
            "(data, docs, experiments)."
        )
        path = st.text_input(
            "Path",
            value="data/sample/product_manual.md",
            key="doc_existing_path",
        )
        if st.button("Ingest by path", key="doc_ingest_path"):
            with st.spinner("Ingesting..."):
                try:
                    response = api_client.ingest_document(path)
                except api_client.ApiError as error:
                    show_api_error(error)
                    return
            result = response.get("result", {})
            if result.get("status") == "ok":
                st.success(result.get("message") or "Ingested.")
            else:
                st.error(
                    f"**{result.get('status')}** — {result.get('message') or 'Failed.'}"
                )

    # ------------------------------------------------------------------
    # Indexed documents
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("2 · Indexed documents")

    if st.button("Refresh list", key="doc_refresh"):
        try:
            listing = api_client.list_documents()
        except api_client.ApiError as error:
            show_api_error(error)
            return
        st.session_state["doc_listing"] = listing

    listing = st.session_state.get("doc_listing")
    if listing is None:
        try:
            listing = api_client.list_documents()
        except api_client.ApiError as error:
            show_api_error(error)
            return
        st.session_state["doc_listing"] = listing

    documents = listing.get("documents") or []
    if not documents:
        st.info("No documents are indexed yet. Upload one above.")
    else:
        rows = [
            {
                "name": document.get("name"),
                "format": document.get("doc_format"),
                "pages": document.get("page_count") or "-",
                "characters": document.get("char_count"),
                "id": document.get("document_id"),
            }
            for document in documents
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption(f"{listing.get('chunk_count', 0)} chunks indexed.")

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("3 · Retrieve and answer")

    query = st.text_input(
        "Question or query",
        placeholder="e.g. What is the warranty period?",
        key="doc_query",
    )
    top_k = st.slider("Passages to retrieve", min_value=1, max_value=10, value=5)

    if st.button("Retrieve passages", key="doc_retrieve"):
        if not query.strip():
            st.error("Please enter a query.")
        else:
            with st.spinner("Retrieving..."):
                try:
                    response = api_client.retrieve_passages(query, top_k=top_k)
                except api_client.ApiError as error:
                    show_api_error(error)
                    return
            st.session_state["doc_retrieval"] = response

    retrieval = st.session_state.get("doc_retrieval")
    if retrieval:
        st.markdown(f"**{retrieval.get('count', 0)} passages**")
        show_evidence(retrieval.get("results") or [])

    st.divider()
    st.subheader("4 · Answer and summarise")

    question = st.text_input(
        "Ask a question",
        placeholder="e.g. What does the manual say about installation?",
        key="doc_question",
    )

    if st.button("Answer from the documents", key="doc_answer"):
        if not question.strip():
            st.error("Please enter a question.")
        else:
            with st.spinner("Answering..."):
                try:
                    response = api_client.answer_question(question)
                except api_client.ApiError as error:
                    show_api_error(error)
                    return
            st.session_state["doc_answer"] = response.get("answer")

    answer = st.session_state.get("doc_answer")
    if answer:
        status = answer.get("status")
        if status == "answered":
            st.success(answer.get("answer_text", ""))
        elif status == "insufficient_evidence":
            st.warning(
                "**Insufficient evidence.** The indexed documents do not support "
                "an answer to that question."
            )
            if answer.get("insufficient_reason"):
                st.caption(answer["insufficient_reason"])
        elif status == "no_documents":
            st.info("No documents are indexed yet.")
        else:
            st.error(f"**{status}**")

        if answer.get("citations"):
            st.markdown("**Citations**")
            for citation in answer["citations"]:
                st.write(f"- {citation}")

        if answer.get("evidence"):
            with st.expander("Supporting evidence"):
                show_evidence(answer["evidence"])

    st.divider()
    if st.button("Summarise the indexed documents", key="doc_summarise"):
        with st.spinner("Summarising..."):
            try:
                response = api_client.summarise_document()
            except api_client.ApiError as error:
                show_api_error(error)
                return
        st.session_state["doc_summary"] = response.get("summary")

    summary = st.session_state.get("doc_summary")
    if summary:
        if summary.get("status") == "answered":
            st.write(summary.get("summary_text", ""))
            if summary.get("citations"):
                st.markdown("**Citations**")
                for citation in summary["citations"]:
                    st.write(f"- {citation}")
        else:
            st.info(f"Status: **{summary.get('status')}**")
