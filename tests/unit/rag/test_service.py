"""Tests for the document intelligence service."""

from __future__ import annotations

import pytest
from tests.unit.rag import fixtures

from nexusai.rag.schemas import AnswerStatus, ExtractionStatus
from nexusai.rag.service import DocumentIntelligenceService


@pytest.fixture
def service(tmp_path):
    """Return a service backed by a temporary store."""
    return DocumentIntelligenceService(store_dir=tmp_path / "vectors")


def test_ingest_markdown(service):
    """Test ingesting a Markdown document."""
    path = fixtures.write_markdown(service.store_dir.parent / "widget.md")
    result = service.ingest(path)

    assert result.status == ExtractionStatus.OK
    assert result.document is not None
    assert result.chunk_count > 0
    assert result.document.name == "widget.md"
    assert result.document.char_count > 0


def test_ingest_plain_text(service):
    """Test ingesting a plain-text document."""
    path = fixtures.write_text(service.store_dir.parent / "notes.txt")
    result = service.ingest(path)
    assert result.status == ExtractionStatus.OK
    assert result.chunk_count > 0


def test_ingest_docx(service):
    """Test ingesting a DOCX document."""
    path = fixtures.write_docx(service.store_dir.parent / "guide.docx")
    result = service.ingest(path)
    assert result.status == ExtractionStatus.OK
    assert result.chunk_count > 0


def test_ingest_pdf(service):
    """Test ingesting a PDF document."""
    path = fixtures.write_pdf(service.store_dir.parent / "manual.pdf")
    result = service.ingest(path)
    assert result.status == ExtractionStatus.OK
    assert result.document.page_count == 2


def test_ingest_unsupported_format(service):
    """Test that an unsupported format is reported, not raised."""
    path = service.store_dir.parent / "data.xyz"
    path.write_text("hello", encoding="utf-8")
    result = service.ingest(path)
    assert result.status == ExtractionStatus.UNSUPPORTED_FORMAT
    assert result.document is None


def test_ingest_corrupt_document(service):
    """Test that a corrupt document is reported, not raised."""
    path = fixtures.write_corrupt_pdf(service.store_dir.parent / "broken.pdf")
    result = service.ingest(path)
    assert result.status == ExtractionStatus.CORRUPTED
    assert result.document is None


def test_ingest_empty_document(service):
    """Test that an empty document is reported."""
    path = fixtures.write_empty(service.store_dir.parent / "empty.txt")
    result = service.ingest(path)
    assert result.status == ExtractionStatus.EMPTY


def test_ingest_missing_file(service):
    """Test that a missing file is reported, not raised."""
    result = service.ingest(service.store_dir.parent / "nope.md")
    assert result.status == ExtractionStatus.FAILED


def test_duplicate_ingestion_is_detected(service):
    """Test that re-ingesting the same document reports a duplicate."""
    path = fixtures.write_markdown(service.store_dir.parent / "widget.md")
    first = service.ingest(path)
    second = service.ingest(path)

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.chunk_count == first.chunk_count
    # The chunk count does not double.
    assert service.chunk_count() == first.chunk_count


def test_ingest_text(service):
    """Test ingesting text directly."""
    result = service.ingest_text("# Title\n\nSome content about widgets.", name="inline.md")
    assert result.status == ExtractionStatus.OK
    assert result.chunk_count > 0


def test_ingest_empty_text(service):
    """Test that empty text is reported."""
    result = service.ingest_text("   ", name="empty.md")
    assert result.status == ExtractionStatus.EMPTY


def test_retrieve_finds_relevant_chunk(service):
    """Test that retrieval finds the relevant passage."""
    path = fixtures.write_markdown(service.store_dir.parent / "widget.md")
    service.ingest(path)

    results = service.retrieve("warranty coverage", top_k=3)
    assert results
    assert results[0].score > 0
    assert "warrant" in results[0].chunk.text.lower() or (
        results[0].chunk.heading and "warrant" in results[0].chunk.heading.lower()
    )


def test_retrieve_respects_document_filter(service):
    """Test that a document filter excludes other documents."""
    base = service.store_dir.parent
    service.ingest(fixtures.write_markdown(base / "widget.md"))
    service.ingest(fixtures.write_text(base / "notes.txt"))

    doc_id = next(iter(service.store.document_ids()))
    results = service.retrieve("warranty", top_k=10, document_ids={doc_id})
    assert all(r.chunk.document_id == doc_id for r in results)


def test_retrieve_empty_query(service):
    """Test that an empty query returns nothing."""
    assert service.retrieve("") == []


def test_answer_is_grounded_with_citations(service):
    """Test that an answer carries evidence and citations."""
    path = fixtures.write_markdown(service.store_dir.parent / "widget.md")
    service.ingest(path)

    answer = service.answer("What is the warranty period?")
    assert answer.status == AnswerStatus.ANSWERED
    assert answer.evidence
    assert answer.citations
    assert answer.is_grounded() is True
    # Every evidence span points at a real chunk.
    for span in answer.evidence:
        assert span.chunk_id
        assert span.source_reference


def test_answer_evidence_text_comes_from_the_source(service):
    """Test that quoted evidence appears verbatim in the indexed text."""
    path = fixtures.write_markdown(service.store_dir.parent / "widget.md")
    service.ingest(path)

    answer = service.answer("What is the warranty period?")
    document = service.documents()[0]
    full_text = document.full_text
    for span in answer.evidence:
        assert span.text.strip() in full_text


def test_answer_without_documents_is_explicit(service):
    """Test that answering with nothing indexed is explicit."""
    answer = service.answer("anything")
    assert answer.status == AnswerStatus.NO_DOCUMENTS
    assert answer.answer_text == ""
    assert answer.insufficient_reason


def test_answer_with_unsupported_question_is_insufficient(service):
    """Test that an unanswerable question returns insufficient evidence."""
    path = fixtures.write_markdown(service.store_dir.parent / "widget.md")
    service.ingest(path)

    answer = service.answer("What is the population of Reykjavik in 1990?")
    assert answer.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert answer.answer_text == ""
    assert answer.insufficient_reason
    assert answer.evidence == []


def test_answer_with_empty_question(service):
    """Test that an empty question is handled."""
    answer = service.answer("")
    assert answer.status == AnswerStatus.INSUFFICIENT_EVIDENCE


def test_summarize_document(service):
    """Test summarising a document."""
    path = fixtures.write_markdown(service.store_dir.parent / "widget.md")
    service.ingest(path)

    doc_id = service.documents()[0].document_id
    summary = service.summarize(document_id=doc_id)
    assert summary.status == AnswerStatus.ANSWERED
    assert summary.evidence
    assert summary.citations


def test_summarize_unknown_document(service):
    """Test summarising a document that is not indexed."""
    summary = service.summarize(document_id="doc_does_not_exist")
    assert summary.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert summary.summary_text == ""


def test_summarize_with_no_documents(service):
    """Test summarising an empty index."""
    summary = service.summarize()
    assert summary.status == AnswerStatus.NO_DOCUMENTS


def test_summarize_grounded_in_source_text(service):
    """Test that summary sentences come from the source."""
    path = fixtures.write_markdown(service.store_dir.parent / "widget.md")
    service.ingest(path)

    doc_id = service.documents()[0].document_id
    summary = service.summarize(document_id=doc_id)
    full_text = service.documents()[0].full_text
    for span in summary.evidence:
        assert span.text.strip() in full_text


def test_service_persists_between_instances(tmp_path):
    """Test that the index survives a new service instance."""
    base = tmp_path / "docs"
    base.mkdir()
    path = fixtures.write_markdown(base / "widget.md")

    first = DocumentIntelligenceService(store_dir=tmp_path / "vectors")
    first.ingest(path)
    chunk_count = first.chunk_count()

    second = DocumentIntelligenceService(store_dir=tmp_path / "vectors")
    assert second.chunk_count() == chunk_count
    assert second.retrieve("warranty")


def test_service_clear(service):
    """Test that clearing removes everything."""
    path = fixtures.write_markdown(service.store_dir.parent / "widget.md")
    service.ingest(path)
    service.clear()
    assert service.chunk_count() == 0
    assert service.documents() == []


def test_service_is_ready(service):
    """Test that the service reports readiness."""
    assert service.is_ready() is True


def test_documents_listing(service):
    """Test that ingested documents are listed."""
    base = service.store_dir.parent
    service.ingest(fixtures.write_markdown(base / "widget.md"))
    service.ingest(fixtures.write_text(base / "notes.txt"))
    assert len(service.documents()) == 2
