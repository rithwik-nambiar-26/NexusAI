"""Tests for text normalisation and chunking."""

from __future__ import annotations

import pytest

from nexusai.rag.chunking import (
    chunk_document,
    chunk_section,
    content_hash,
    document_id_for,
    normalize_text,
)
from nexusai.rag.schemas import Document, DocumentSection


def test_normalize_text_collapses_blank_lines():
    """Test that runs of blank lines collapse."""
    assert normalize_text("a\n\n\n\nb") == "a\n\nb"


def test_normalize_text_strips_trailing_spaces():
    """Test that trailing whitespace is removed."""
    assert normalize_text("hello   ") == "hello"


def test_normalize_text_normalises_line_endings():
    """Test that CRLF becomes LF."""
    assert normalize_text("a\r\nb") == "a\nb"


def test_normalize_text_empty():
    """Test that empty input normalises to empty."""
    assert normalize_text("") == ""
    assert normalize_text("   \n  ") == ""


def test_content_hash_is_stable_across_whitespace():
    """Test that whitespace-only differences do not change the hash."""
    assert content_hash("hello world") == content_hash("hello   world\n")
    assert content_hash("a b") != content_hash("a c")


def test_document_id_is_content_addressed():
    """Test that the document id depends on name and content."""
    first = document_id_for("doc.md", "hello")
    second = document_id_for("doc.md", "hello")
    third = document_id_for("doc.md", "goodbye")
    fourth = document_id_for("other.md", "hello")

    assert first == second
    assert first != third
    assert first != fourth
    assert first.startswith("doc_")


def _section(text: str, heading: str | None = None) -> DocumentSection:
    return DocumentSection(
        text=text,
        page_number=None,
        section_index=0,
        heading=heading,
        start_offset=0,
        end_offset=len(text),
    )


def test_chunk_section_splits_long_content():
    """Test that a long section is split into several chunks."""
    text = "\n\n".join(f"Paragraph number {i} with some content." for i in range(40))
    chunks = chunk_section(_section(text), "doc_1", chunk_size=200, chunk_overlap=20)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.text) <= 300
        assert chunk.document_id == "doc_1"


def test_chunk_section_preserves_heading():
    """Test that the section heading is carried onto every chunk."""
    text = "\n\n".join(f"Paragraph {i}." for i in range(30))
    chunks = chunk_section(
        _section(text, heading="2. Warranty"), "doc_1", chunk_size=150, chunk_overlap=10
    )
    assert all(chunk.heading == "2. Warranty" for chunk in chunks)


def test_chunk_section_preserves_page_number():
    """Test that the page number is carried onto every chunk."""
    text = "\n\n".join(f"Paragraph {i}." for i in range(30))
    section = _section(text)
    section.page_number = 7
    chunks = chunk_section(section, "doc_1", chunk_size=150, chunk_overlap=10)
    assert all(chunk.page_number == 7 for chunk in chunks)


def test_chunk_ids_are_stable():
    """Test that the same content always yields the same chunk id."""
    text = "A paragraph of content for chunking."
    first = chunk_section(_section(text), "doc_1")
    second = chunk_section(_section(text), "doc_1")
    assert first[0].chunk_id == second[0].chunk_id


def test_chunk_ids_differ_between_documents():
    """Test that chunks of different documents have different ids."""
    text = "A paragraph of content for chunking."
    first = chunk_section(_section(text), "doc_1")
    second = chunk_section(_section(text), "doc_2")
    assert first[0].chunk_id != second[0].chunk_id


def test_chunk_indices_are_sequential():
    """Test that chunk indices increase across a document."""
    document = Document(
        document_id="doc_1",
        name="d.md",
        content_hash="h",
        sections=[
            _section("\n\n".join(f"P{i}." for i in range(20))),
            _section("\n\n".join(f"Q{i}." for i in range(20))),
        ],
    )
    chunks = chunk_document(document, chunk_size=120, chunk_overlap=10)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunk_overlap_must_be_smaller_than_size():
    """Test that an invalid overlap is rejected."""
    with pytest.raises(ValueError):
        chunk_section(_section("text"), "doc_1", chunk_size=100, chunk_overlap=100)


def test_chunk_never_exceeds_size_by_much():
    """Test that chunks stay within the target size for normal paragraphs."""
    text = "\n\n".join(f"Paragraph {i} with a reasonable amount of text." for i in range(50))
    chunks = chunk_section(_section(text), "doc_1", chunk_size=250, chunk_overlap=30)
    for chunk in chunks:
        assert len(chunk.text) <= 400


def test_chunk_handles_a_very_long_single_paragraph():
    """Test that a paragraph longer than the chunk size is still kept."""
    text = "word " * 500
    chunks = chunk_section(_section(text), "doc_1", chunk_size=200, chunk_overlap=20)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 260 for chunk in chunks)


def test_chunk_preserves_all_content():
    """Test that no content is silently dropped."""
    text = "\n\n".join(f"Unique paragraph marker {i}." for i in range(30))
    chunks = chunk_section(_section(text), "doc_1", chunk_size=200, chunk_overlap=20)
    joined = " ".join(chunk.text for chunk in chunks)
    for i in range(30):
        assert f"marker {i}." in joined


def test_chunk_token_estimate_is_positive():
    """Test that the token estimate is populated."""
    chunks = chunk_section(_section("Some content here."), "doc_1")
    assert chunks[0].token_estimate > 0
