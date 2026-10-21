"""Tests for the Day 4 capability adapters registered as tools."""

from __future__ import annotations

import pytest

from nexusai.app.execution.derivation import (
    derive_tool_inputs,
    find_document_reference,
)
from nexusai.app.execution.registry import (
    ToolError,
    ToolErrorCategory,
    ToolRegistry,
    ToolRisk,
)
from nexusai.app.execution.tools import (
    DOCUMENT_CAPABILITIES,
    DocumentExtractInput,
    DocumentReadInput,
    LlmSummariseInput,
    register_document_tools,
)
from nexusai.rag.capabilities import DocumentCapabilities
from nexusai.rag.service import DocumentIntelligenceService


@pytest.fixture
def registry(tmp_path):
    """Return a registry with the document tools registered."""
    service = DocumentIntelligenceService(store_dir=tmp_path / "vectors")
    service.ingest("data/sample/product_manual.md")
    capabilities = DocumentCapabilities(service)
    reg = ToolRegistry()
    register_document_tools(reg, capabilities)
    return reg, service


def test_registers_the_three_capabilities(registry):
    """Test that the Day 4 capabilities are registered under the planner's names."""
    reg, _ = registry
    for capability in DOCUMENT_CAPABILITIES:
        assert reg.has(capability) is True
    assert reg.capabilities() == [
        "document.extract",
        "document.read",
        "llm.summarise",
    ]


def test_capability_names_match_the_planner(registry):
    """Test that the names are exactly the ones the planner emits."""
    from nexusai.ml.planner.service import create_plan

    plan, _ = create_plan(
        request="Read data/sample/product_manual.md and summarise it.",
        intent="document_summarisation",
        source="explicit",
    )
    needed = {c for task in plan.tasks for c in task.required_capabilities}
    document_needed = needed & {
        "document.read",
        "document.extract",
        "llm.summarise",
    }
    assert document_needed, "the document plan should require document capabilities"

    reg, _ = registry
    for capability in document_needed:
        assert reg.has(capability) is True, f"{capability} should be registered"


def test_tools_are_read_only(registry):
    """Test that no registered document tool requires approval or is risky."""
    reg, _ = registry
    for tool in reg.list_tools():
        assert tool.requires_approval is False
        assert tool.risk == ToolRisk.SAFE
        assert tool.idempotent is True


def test_document_read_executes(registry):
    """Test the document.read tool."""
    reg, _ = registry
    output, _elapsed = reg.execute(
        "document.read", {"path": "data/sample/product_manual.md"}
    )
    assert output.name == "product_manual.md"
    assert "warranty" in output.text.lower()
    assert output.sections


def test_document_read_rejects_a_missing_path(registry):
    """Test that document.read validates its input."""
    reg, _ = registry
    with pytest.raises(ToolError) as exc_info:
        reg.execute("document.read", {})
    assert exc_info.value.category == ToolErrorCategory.INVALID_INPUT


def test_document_extract_executes(registry):
    """Test the document.extract tool."""
    reg, _ = registry
    output, _elapsed = reg.execute(
        "document.extract", {"query": "warranty period", "top_k": 3}
    )
    assert output.count > 0
    assert output.passages[0].source_reference
    assert output.passages[0].chunk_id


def test_document_extract_requires_a_query(registry):
    """Test that document.extract validates its input."""
    reg, _ = registry
    with pytest.raises(ToolError) as exc_info:
        reg.execute("document.extract", {})
    assert exc_info.value.category == ToolErrorCategory.INVALID_INPUT


def test_llm_summarise_executes(registry):
    """Test the llm.summarise tool."""
    reg, service = registry
    document_id = service.documents()[0].document_id
    output, _elapsed = reg.execute("llm.summarise", {"document_id": document_id})
    assert output.status == "answered"
    assert output.summary_text
    assert output.citations
    assert output.evidence


def test_summarise_output_is_grounded(registry):
    """Test that the summary text comes from the source document."""
    reg, service = registry
    document_id = service.documents()[0].document_id
    output, _elapsed = reg.execute("llm.summarise", {"document_id": document_id})
    full_text = service.documents()[0].full_text
    for span in output.evidence:
        assert span.text.strip() in full_text


def test_input_schemas_forbid_unknown_fields(registry):
    """Test that the tool input schemas reject unknown fields."""
    reg, _ = registry
    with pytest.raises(ToolError):
        reg.execute("document.extract", {"query": "x", "unexpected": True})


def test_input_schema_types():
    """Test the declared input schemas."""
    assert "path" in DocumentReadInput.model_fields
    assert "document_id" in DocumentReadInput.model_fields
    assert "query" in DocumentExtractInput.model_fields
    assert "top_k" in DocumentExtractInput.model_fields
    assert "document_id" in LlmSummariseInput.model_fields
    assert "question" in LlmSummariseInput.model_fields


# ---------------------------------------------------------------------------
# Input derivation
# ---------------------------------------------------------------------------


def test_find_document_reference():
    """Test that a document reference is found in a request."""
    assert (
        find_document_reference("Read data/sample/product_manual.md and summarise it")
        == "data/sample/product_manual.md"
    )
    assert find_document_reference("Summarise the report") is None


def test_derives_path_for_document_read():
    """Test that a path is derived from the request."""
    resolved = derive_tool_inputs(
        "document.read",
        "Read data/sample/product_manual.md and summarise it",
        {},
    )
    assert resolved["path"] == "data/sample/product_manual.md"


def test_declared_input_wins_over_derivation():
    """Test that a declared input is not overwritten."""
    resolved = derive_tool_inputs(
        "document.read",
        "Read data/sample/product_manual.md",
        {"path": "other/file.md"},
    )
    assert resolved["path"] == "other/file.md"


def test_derives_query_for_document_extract():
    """Test that the request becomes the query."""
    resolved = derive_tool_inputs(
        "document.extract", "What is the warranty period?", {}
    )
    assert resolved["query"] == "What is the warranty period?"


def test_derives_question_for_summarise():
    """Test that the request becomes the question."""
    resolved = derive_tool_inputs("llm.summarise", "Summarise the manual", {})
    assert resolved["question"] == "Summarise the manual"


def test_no_derivation_for_unknown_capability():
    """Test that an unrelated capability gets nothing derived."""
    resolved = derive_tool_inputs("other.tool", "some request", {})
    assert resolved == {}
