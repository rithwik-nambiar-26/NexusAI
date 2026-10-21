"""Tests for document extraction."""

from __future__ import annotations

import pytest
from tests.unit.rag import fixtures

from nexusai.rag.extractors import (
    CorruptedDocumentError,
    ExtractionError,
    UnsupportedFormatError,
    detect_format,
    extract_document,
)
from nexusai.rag.schemas import DocumentFormat


def test_detect_format_by_extension():
    """Test format detection from file extensions."""
    assert detect_format("a.pdf") == DocumentFormat.PDF
    assert detect_format("a.docx") == DocumentFormat.DOCX
    assert detect_format("a.txt") == DocumentFormat.TXT
    assert detect_format("a.md") == DocumentFormat.MARKDOWN
    assert detect_format("a.unknown") == DocumentFormat.UNKNOWN
    assert detect_format("a") == DocumentFormat.UNKNOWN


def test_extract_markdown_preserves_headings(tmp_path):
    """Test that Markdown headings are captured as section headings."""
    path = fixtures.write_markdown(tmp_path / "widget.md")
    sections, page_count, doc_format = extract_document(path)

    assert doc_format == DocumentFormat.MARKDOWN
    assert page_count is None
    assert len(sections) >= 3
    headings = [s.heading for s in sections]
    assert "2. Warranty" in headings
    assert "1. Overview" in headings


def test_extract_markdown_offsets_point_at_source_text(tmp_path):
    """Test that section offsets locate the text in the source."""
    path = fixtures.write_markdown(tmp_path / "widget.md")
    original = path.read_text(encoding="utf-8")
    sections, _, _ = extract_document(path)

    for section in sections:
        assert original[section.start_offset : section.end_offset] == section.text


def test_extract_plain_text(tmp_path):
    """Test plain text extraction."""
    path = fixtures.write_text(tmp_path / "notes.txt")
    sections, page_count, doc_format = extract_document(path)

    assert doc_format == DocumentFormat.TXT
    assert page_count is None
    assert len(sections) == 1
    assert "firmware 1.0" in sections[0].text


def test_extract_docx(tmp_path):
    """Test DOCX extraction preserves paragraph text and headings."""
    path = fixtures.write_docx(tmp_path / "guide.docx")
    sections, page_count, doc_format = extract_document(path)

    assert doc_format == DocumentFormat.DOCX
    assert page_count is None
    text = "\n".join(s.text for s in sections)
    assert "synthetic device" in text
    assert "Disconnect the Widget" in text
    assert "support@example.invalid" in text
    # Headings are attached to the body that follows them.
    assert any(s.heading == "Safety" for s in sections)


def test_extract_pdf_preserves_page_numbers(tmp_path):
    """Test that PDF extraction records 1-based page numbers."""
    path = fixtures.write_pdf(tmp_path / "manual.pdf")
    sections, page_count, doc_format = extract_document(path)

    assert doc_format == DocumentFormat.PDF
    assert page_count == 2
    assert [s.page_number for s in sections] == [1, 2]
    assert "warranty" in sections[1].text.lower()


def test_extract_pdf_records_heading(tmp_path):
    """Test that a PDF page's first heading is captured."""
    path = fixtures.write_pdf(tmp_path / "manual.pdf")
    sections, _, _ = extract_document(path)
    assert sections[1].heading == "2. Warranty"


def test_extract_unsupported_format(tmp_path):
    """Test that an unsupported extension is rejected."""
    path = tmp_path / "data.xyz"
    path.write_text("hello", encoding="utf-8")

    with pytest.raises(UnsupportedFormatError):
        extract_document(path)


def test_extract_missing_file(tmp_path):
    """Test that a missing file is reported."""
    with pytest.raises(ExtractionError):
        extract_document(tmp_path / "nope.md")


def test_extract_directory_is_rejected(tmp_path):
    """Test that a directory is not treated as a document."""
    with pytest.raises(ExtractionError):
        extract_document(tmp_path)


def test_extract_corrupt_pdf(tmp_path):
    """Test that a corrupt PDF is reported as corrupted."""
    path = fixtures.write_corrupt_pdf(tmp_path / "broken.pdf")
    with pytest.raises(CorruptedDocumentError):
        extract_document(path)


def test_extract_empty_text_file(tmp_path):
    """Test that an empty text file yields no sections rather than raising."""
    path = fixtures.write_empty(tmp_path / "empty.txt")
    sections, _, doc_format = extract_document(path)

    assert doc_format == DocumentFormat.TXT
    assert sections == []


def test_extract_binary_garbage_as_text(tmp_path):
    """Test that undecodable bytes are handled without crashing."""
    path = fixtures.write_binary_garbage(tmp_path / "garbage.txt")
    sections, _, _ = extract_document(path)
    # The latin-1 fallback decodes any byte sequence, so extraction succeeds
    # but yields text that is not meaningful.
    assert isinstance(sections, list)
