"""Registration of the Day 4 document capabilities as executable tools.

The adapters here are thin: they translate a tool's typed input into the
call the Day 4 :class:`DocumentCapabilities` interface already exposes, and
translate the result back into a typed output. The RAG implementation is
not duplicated or modified.

The capability names are exactly the ones the Day 3 planner emits in
``required_capabilities``, so a planner task binds to these tools without
a translation layer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexusai.app.core.logging import get_logger
from nexusai.app.execution.registry import (
    RetryPolicy,
    ToolDefinition,
    ToolPermission,
    ToolRegistry,
    ToolRisk,
)
from nexusai.rag.capabilities import DocumentCapabilities

logger = get_logger("execution.tools")


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class DocumentReadInput(BaseModel):
    """Input for the ``document.read`` capability."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = Field(
        default=None, description="Path to the document, relative to an allowed root"
    )
    document_id: str | None = Field(
        default=None, description="Identifier of an already-indexed document"
    )

    @model_validator(mode="after")
    def _require_a_target(self) -> DocumentReadInput:
        """Require either a path or a document id.

        Catching this in the schema means the failure is reported as
        invalid input, before the handler runs.
        """
        if not self.path and not self.document_id:
            raise ValueError("either 'path' or 'document_id' must be supplied")
        return self


class DocumentExtractInput(BaseModel):
    """Input for the ``document.extract`` capability."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="The query to retrieve passages for")
    document_id: str | None = Field(
        default=None, description="Restrict retrieval to one document"
    )
    document_ids: list[str] | None = Field(
        default=None,
        description=(
            "Restrict retrieval to these documents. Used when the request "
            "explicitly spans several documents; a single document is given "
            "as document_id."
        ),
    )
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of passages")


class LlmSummariseInput(BaseModel):
    """Input for the ``llm.summarise`` capability."""

    model_config = ConfigDict(extra="forbid")

    document_id: str | None = Field(
        default=None, description="Document to summarise; all documents when omitted"
    )
    document_ids: list[str] | None = Field(
        default=None,
        description=(
            "Documents to summarise. Each is summarised under its own "
            "heading; the documents are never blended into one narrative."
        ),
    )
    question: str | None = Field(
        default=None, description="Focus the summary on this question"
    )
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of passages")


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class DocumentReadOutput(BaseModel):
    """Output of the ``document.read`` capability."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    name: str
    doc_format: str
    page_count: int | None = None
    char_count: int
    text: str
    sections: list[dict[str, Any]] = Field(default_factory=list)


class DocumentPassage(BaseModel):
    """One retrieved passage."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    document_name: str = ""
    page_number: int | None = None
    heading: str | None = None
    score: float
    source_reference: str
    text: str


class DocumentExtractOutput(BaseModel):
    """Output of the ``document.extract`` capability."""

    model_config = ConfigDict(extra="forbid")

    query: str
    passages: list[DocumentPassage] = Field(default_factory=list)
    count: int = 0
    documents: list[str] = Field(
        default_factory=list,
        description="The documents the passages came from",
    )


class SummaryEvidence(BaseModel):
    """One evidence span backing a summary."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    document_name: str = ""
    page_number: int | None = None
    source_reference: str
    text: str


class LlmSummariseOutput(BaseModel):
    """Output of the ``llm.summarise`` capability."""

    model_config = ConfigDict(extra="forbid")

    status: str
    summary_text: str = ""
    citations: list[str] = Field(default_factory=list)
    evidence: list[SummaryEvidence] = Field(default_factory=list)
    method: str = Field(
        default="extractive",
        description=(
            "How the summary was produced: 'llm' when a local model wrote "
            "it, 'extractive' when the text was selected from the source."
        ),
    )
    sections: list[dict[str, Any]] = Field(
        default_factory=list,
        description="The structured sections of the summary, when it is structured",
    )
    documents: list[str] = Field(
        default_factory=list,
        description="The documents the summary covers",
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _make_read_handler(capabilities: DocumentCapabilities):
    """Build the ``document.read`` handler."""

    def handler(payload: DocumentReadInput) -> DocumentReadOutput:
        result = capabilities.document_read(
            path=payload.path,
            document_id=payload.document_id,
        )
        return DocumentReadOutput.model_validate(result)

    return handler


def _make_extract_handler(capabilities: DocumentCapabilities):
    """Build the ``document.extract`` handler."""

    def handler(payload: DocumentExtractInput) -> DocumentExtractOutput:
        result = capabilities.document_extract(
            query=payload.query,
            document_id=payload.document_id,
            document_ids=payload.document_ids,
            top_k=payload.top_k,
        )
        return DocumentExtractOutput.model_validate(result)

    return handler


def _make_summarise_handler(capabilities: DocumentCapabilities):
    """Build the ``llm.summarise`` handler."""

    def handler(payload: LlmSummariseInput) -> LlmSummariseOutput:
        result = capabilities.llm_summarise(
            document_id=payload.document_id,
            document_ids=payload.document_ids,
            question=payload.question,
            top_k=payload.top_k,
        )
        return LlmSummariseOutput.model_validate(result)

    return handler


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

#: The document capabilities the planner's document tasks require.
DOCUMENT_CAPABILITIES: tuple[str, ...] = (
    "document.read",
    "document.extract",
    "llm.summarise",
)


def register_document_tools(
    registry: ToolRegistry,
    capabilities: DocumentCapabilities,
) -> list[ToolDefinition]:
    """Register the Day 4 document capabilities in *registry*.

    All three are read-only: they read a document, retrieve passages, or
    summarise existing content. None of them writes, sends or deletes, so
    none of them requires approval.

    Args:
        registry: The registry to register into.
        capabilities: The Day 4 capability adapter to bind to.

    Returns:
        The tool definitions that were registered.
    """
    tools = [
        ToolDefinition(
            capability="document.read",
            description=(
                "Read a document from an allowed root and return its extracted "
                "text, sections and page count."
            ),
            input_schema=DocumentReadInput,
            output_schema=DocumentReadOutput,
            handler=_make_read_handler(capabilities),
            permissions=[ToolPermission.READ_DOCUMENT],
            risk=ToolRisk.SAFE,
            requires_approval=False,
            timeout_seconds=30.0,
            retry_policy=RetryPolicy(max_attempts=1),
            idempotent=True,
        ),
        ToolDefinition(
            capability="document.extract",
            description=(
                "Retrieve the passages most relevant to a query, each with a "
                "source reference."
            ),
            input_schema=DocumentExtractInput,
            output_schema=DocumentExtractOutput,
            handler=_make_extract_handler(capabilities),
            permissions=[ToolPermission.READ_DOCUMENT],
            risk=ToolRisk.SAFE,
            requires_approval=False,
            timeout_seconds=30.0,
            retry_policy=RetryPolicy(max_attempts=1),
            idempotent=True,
        ),
        ToolDefinition(
            capability="llm.summarise",
            description=(
                "Produce a summary of a document or of the passages most "
                "relevant to a question, with citations to the source. A "
                "local language model writes the summary when one is "
                "configured and answering; otherwise the summary is "
                "extracted from the source text. The output records which "
                "method was used."
            ),
            input_schema=LlmSummariseInput,
            output_schema=LlmSummariseOutput,
            handler=_make_summarise_handler(capabilities),
            permissions=[ToolPermission.READ_DOCUMENT],
            risk=ToolRisk.SAFE,
            requires_approval=False,
            timeout_seconds=30.0,
            retry_policy=RetryPolicy(max_attempts=1),
            idempotent=True,
        ),
    ]

    for tool in tools:
        registry.register(tool)

    logger.info(
        "Document tools registered",
        extra={"capabilities": [tool.capability for tool in tools]},
    )
    return tools
