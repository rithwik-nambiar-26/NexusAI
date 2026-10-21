"""API schemas for the document intelligence endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nexusai.rag.schemas import (
    Answer,
    Document,
    DocumentSection,
    EvidenceSpan,
    IngestionResult,
    RetrievedChunk,
    Summary,
)


class IngestRequest(BaseModel):
    """Request to ingest a document."""

    path: str = Field(..., min_length=1, description="Path to the document to ingest")
    name: str | None = Field(default=None, description="Display name; defaults to the file name")
    metadata: dict[str, Any] | None = Field(default=None, description="Extra document metadata")


class IngestTextRequest(BaseModel):
    """Request to ingest text supplied directly."""

    text: str = Field(..., min_length=1, description="The document text")
    name: str = Field(default="untitled.md", description="Display name for the document")
    metadata: dict[str, Any] | None = Field(default=None, description="Extra document metadata")


class IngestResponse(BaseModel):
    """Response for an ingestion request."""

    result: IngestionResult
    request_id: str = Field(..., description="Correlation ID for this request")


class RetrieveRequest(BaseModel):
    """Request to retrieve passages."""

    query: str = Field(..., min_length=1, description="The query text")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of passages")
    document_id: str | None = Field(default=None, description="Restrict to one document")
    min_score: float = Field(default=0.0, ge=-1.0, le=1.0, description="Minimum similarity")


class RetrieveResponse(BaseModel):
    """Response for a retrieval request."""

    query: str
    results: list[RetrievedChunk]
    count: int = Field(..., description="Number of results returned")
    request_id: str = Field(..., description="Correlation ID for this request")


class AnswerRequest(BaseModel):
    """Request for a grounded answer."""

    question: str = Field(..., min_length=1, description="The question to answer")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of passages to use")
    document_id: str | None = Field(default=None, description="Restrict to one document")


class AnswerResponse(BaseModel):
    """Response for a grounded answer."""

    answer: Answer
    request_id: str = Field(..., description="Correlation ID for this request")


class SummariseRequest(BaseModel):
    """Request for a grounded summary."""

    document_id: str | None = Field(default=None, description="Document to summarise")
    question: str | None = Field(default=None, description="Focus the summary on a question")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of passages to use")


class SummariseResponse(BaseModel):
    """Response for a grounded summary."""

    summary: Summary
    request_id: str = Field(..., description="Correlation ID for this request")


class DocumentListResponse(BaseModel):
    """Response listing the indexed documents."""

    documents: list[Document]
    chunk_count: int = Field(..., description="Total number of indexed chunks")
    request_id: str = Field(..., description="Correlation ID for this request")


class CapabilityListResponse(BaseModel):
    """Response listing the capabilities this module satisfies."""

    capabilities: list[str]
    request_id: str = Field(..., description="Correlation ID for this request")


__all__ = [
    "AnswerRequest",
    "AnswerResponse",
    "CapabilityListResponse",
    "DocumentListResponse",
    "DocumentSection",
    "EvidenceSpan",
    "IngestRequest",
    "IngestResponse",
    "IngestTextRequest",
    "RetrieveRequest",
    "RetrieveResponse",
    "SummariseRequest",
    "SummariseResponse",
]
