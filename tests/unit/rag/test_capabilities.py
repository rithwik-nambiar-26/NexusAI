"""Tests for the planner capability adapter."""

from __future__ import annotations

import pytest
from tests.unit.rag import fixtures

from nexusai.rag.capabilities import (
    SUPPORTED_CAPABILITIES,
    CapabilityError,
    DocumentCapabilities,
    get_capabilities,
)
from nexusai.rag.service import DocumentIntelligenceService


@pytest.fixture
def capabilities(tmp_path):
    """Return a capability adapter over a temporary service."""
    service = DocumentIntelligenceService(store_dir=tmp_path / "vectors")
    return DocumentCapabilities(service), service


def test_supported_capabilities_match_the_planner():
    """Test that the capability names match the planner's exactly.

    The planner emits these names in ``required_capabilities``; the Day 5
    registry must be able to bind them without a translation layer.
    """
    assert "document.read" in SUPPORTED_CAPABILITIES
    assert "document.extract" in SUPPORTED_CAPABILITIES
    assert "llm.summarise" in SUPPORTED_CAPABILITIES


def test_capabilities_listing(capabilities):
    """Test that the adapter lists its capabilities."""
    adapter, _ = capabilities
    assert adapter.capabilities() == [
        "document.extract",
        "document.read",
        "llm.summarise",
    ]


def test_supports(capabilities):
    """Test the capability support check."""
    adapter, _ = capabilities
    assert adapter.supports("document.read") is True
    assert adapter.supports("llm.summarise") is True
    assert adapter.supports("web.search") is False


def test_invoke_unknown_capability(capabilities):
    """Test that an unknown capability is rejected."""
    adapter, _ = capabilities
    with pytest.raises(CapabilityError):
        adapter.invoke("web.search", query="x")


def test_document_read_reads_a_file(capabilities):
    """Test the document.read capability."""
    adapter, service = capabilities
    base = service.store_dir.parent
    path = fixtures.write_markdown(base / "widget.md")

    result = adapter.invoke("document.read", path=str(path))
    assert result["name"] == "widget.md"
    assert "warranty" in result["text"].lower()
    assert result["sections"]


def test_document_read_requires_a_target(capabilities):
    """Test that document.read needs a path or a document id."""
    adapter, _ = capabilities
    with pytest.raises(CapabilityError):
        adapter.invoke("document.read")


def test_document_read_by_document_id(capabilities):
    """Test document.read against an already-indexed document."""
    adapter, service = capabilities
    base = service.store_dir.parent
    service.ingest(fixtures.write_markdown(base / "widget.md"))
    document_id = service.documents()[0].document_id

    result = adapter.invoke("document.read", document_id=document_id)
    assert result["document_id"] == document_id
    assert result["text"]


def test_document_read_unknown_document_id(capabilities):
    """Test that an unknown document id is rejected."""
    adapter, _ = capabilities
    with pytest.raises(CapabilityError):
        adapter.invoke("document.read", document_id="doc_nope")


def test_document_extract_returns_passages_with_sources(capabilities):
    """Test the document.extract capability."""
    adapter, service = capabilities
    base = service.store_dir.parent
    service.ingest(fixtures.write_markdown(base / "widget.md"))

    result = adapter.invoke("document.extract", query="warranty period")
    assert result["count"] > 0
    passage = result["passages"][0]
    assert passage["chunk_id"]
    assert passage["source_reference"]
    assert passage["text"]


def test_document_extract_requires_a_query(capabilities):
    """Test that document.extract needs a query."""
    adapter, _ = capabilities
    with pytest.raises(CapabilityError):
        adapter.invoke("document.extract")


def test_llm_summarise_returns_grounded_summary(capabilities):
    """Test the llm.summarise capability."""
    adapter, service = capabilities
    base = service.store_dir.parent
    service.ingest(fixtures.write_markdown(base / "widget.md"))
    document_id = service.documents()[0].document_id

    result = adapter.invoke("llm.summarise", document_id=document_id)
    assert result["status"] == "answered"
    assert result["summary_text"]
    assert result["citations"]
    assert result["evidence"]


def test_get_capabilities_uses_the_shared_service():
    """Test that the adapter can be built from the shared service."""
    adapter = get_capabilities()
    assert "document.read" in adapter.capabilities()
