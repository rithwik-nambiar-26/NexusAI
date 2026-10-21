"""Pydantic schemas for the document intelligence and RAG subsystem.

These schemas define the contract between ingestion, chunking, indexing,
retrieval and answer generation. Evidence carries a stable source
reference at every level so that a claim can always be traced back to the
exact text it came from.

Retrieval and answer generation are deliberately separate: retrieval
returns evidence, and answer construction consumes evidence. An answer is
never produced without a citation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DocumentFormat(StrEnum):
    """Supported document formats."""

    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MARKDOWN = "markdown"
    UNKNOWN = "unknown"


class ExtractionStatus(StrEnum):
    """Outcome of an extraction attempt."""

    OK = "ok"
    EMPTY = "empty"
    UNSUPPORTED_FORMAT = "unsupported_format"
    CORRUPTED = "corrupted"
    FAILED = "failed"


class DocumentSection(BaseModel):
    """A contiguous block of text from a source document.

    ``page_number`` is 1-based and is ``None`` for formats without pages.
    ``start_offset``/``end_offset`` locate the section within the extracted
    text of the document, so the original source text can be recovered
    verbatim.
    """

    text: str = Field(..., description="The section text as extracted")
    page_number: int | None = Field(default=None, description="1-based page number, if any")
    section_index: int = Field(default=0, description="Index of the section within the document")
    heading: str | None = Field(default=None, description="Nearest heading above the section, if any")
    start_offset: int = Field(default=0, description="Start offset within the document's extracted text")
    end_offset: int = Field(default=0, description="End offset within the document's extracted text")


class Document(BaseModel):
    """An ingested document."""

    document_id: str = Field(..., description="Stable content-addressed identifier")
    name: str = Field(..., description="Display name of the document")
    source_path: str | None = Field(default=None, description="Path the document was read from")
    doc_format: DocumentFormat = Field(default=DocumentFormat.UNKNOWN, description="Detected format")
    content_hash: str = Field(..., description="Hash of the normalised full text")
    sections: list[DocumentSection] = Field(default_factory=list, description="Extracted sections")
    page_count: int | None = Field(default=None, description="Number of pages, if the format has pages")
    char_count: int = Field(default=0, description="Number of characters of extracted text")
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Ingestion time")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Free-form document metadata")

    @property
    def full_text(self) -> str:
        """Return the concatenated text of all sections."""
        return "\n\n".join(section.text for section in self.sections)


class Chunk(BaseModel):
    """A retrievable unit of document text."""

    chunk_id: str = Field(..., description="Stable identifier for the chunk")
    document_id: str = Field(..., description="Identifier of the owning document")
    text: str = Field(..., description="The chunk text")
    chunk_index: int = Field(default=0, description="Position of the chunk within the document")
    page_number: int | None = Field(default=None, description="1-based page number, if any")
    heading: str | None = Field(default=None, description="Nearest heading above the chunk, if any")
    start_offset: int = Field(default=0, description="Start offset within the document's extracted text")
    end_offset: int = Field(default=0, description="End offset within the document's extracted text")
    token_estimate: int = Field(default=0, description="Approximate token count of the chunk")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Free-form chunk metadata")

    def source_reference(self, document_name: str = "") -> str:
        """Return a human-readable citation for this chunk."""
        parts: list[str] = []
        if document_name:
            parts.append(document_name)
        if self.page_number is not None:
            parts.append(f"p.{self.page_number}")
        if self.heading:
            parts.append(f"§{self.heading}")
        parts.append(self.chunk_id)
        return " | ".join(parts)


class RetrievedChunk(BaseModel):
    """A chunk returned by retrieval, with its relevance score."""

    chunk: Chunk = Field(..., description="The retrieved chunk")
    score: float = Field(default=0.0, description="Similarity score against the query")
    document_name: str = Field(default="", description="Name of the owning document")
    source_reference: str = Field(default="", description="Human-readable citation")
    rank: int = Field(default=0, description="Rank of the result, 1-based")


class AnswerStatus(StrEnum):
    """Outcome of an answer attempt."""

    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NO_DOCUMENTS = "no_documents"
    ERROR = "error"


class EvidenceSpan(BaseModel):
    """A span of source text supporting part of an answer."""

    text: str = Field(..., description="The supporting source text, verbatim")
    chunk_id: str = Field(..., description="Identifier of the supporting chunk")
    document_id: str = Field(..., description="Identifier of the supporting document")
    document_name: str = Field(default="", description="Name of the supporting document")
    page_number: int | None = Field(default=None, description="1-based page number, if any")
    source_reference: str = Field(default="", description="Human-readable citation")
    score: float = Field(default=0.0, description="Relevance score of the supporting chunk")


class Answer(BaseModel):
    """A grounded answer to a question.

    The answer is extractive: it is assembled from retrieved source text
    rather than generated, so every claim can be pointed at. When the
    retrieved evidence does not support an answer, ``status`` is
    ``INSUFFICIENT_EVIDENCE`` and ``answer_text`` says so rather than
    guessing.
    """

    question: str = Field(..., description="The question asked")
    answer_text: str = Field(default="", description="The grounded answer, or an explicit refusal")
    status: AnswerStatus = Field(default=AnswerStatus.ERROR, description="Outcome of the answer attempt")
    evidence: list[EvidenceSpan] = Field(default_factory=list, description="Supporting evidence")
    citations: list[str] = Field(default_factory=list, description="Citation strings for the evidence")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence in the answer")
    insufficient_reason: str | None = Field(
        default=None, description="Why the evidence was judged insufficient"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Answer time")

    def is_grounded(self) -> bool:
        """Return True when the answer is backed by at least one evidence span."""
        return self.status == AnswerStatus.ANSWERED and bool(self.evidence)


class Summary(BaseModel):
    """A grounded summary of a document or of retrieved passages."""

    source_document_id: str | None = Field(default=None, description="Document summarised, if any")
    summary_text: str = Field(default="", description="The summary text")
    evidence: list[EvidenceSpan] = Field(default_factory=list, description="Supporting evidence")
    citations: list[str] = Field(default_factory=list, description="Citation strings for the evidence")
    status: AnswerStatus = Field(default=AnswerStatus.ERROR, description="Outcome of the summary attempt")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Summary time")

    def is_grounded(self) -> bool:
        """Return True when the summary is backed by evidence."""
        return self.status == AnswerStatus.ANSWERED and bool(self.evidence)


class IngestionResult(BaseModel):
    """Outcome of ingesting a document."""

    document: Document | None = Field(default=None, description="The ingested document")
    status: ExtractionStatus = Field(default=ExtractionStatus.FAILED, description="Extraction outcome")
    chunk_count: int = Field(default=0, description="Number of chunks produced")
    duplicate: bool = Field(default=False, description="True when the document was already indexed")
    message: str | None = Field(default=None, description="Human-readable detail about the outcome")
