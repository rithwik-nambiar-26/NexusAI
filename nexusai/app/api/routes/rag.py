"""Document intelligence API routes.

These endpoints expose ingestion, retrieval, grounded question answering
and grounded summarisation, plus a direct CSV analysis endpoint.

The CSV analysis endpoint invokes the registered ``data.analyse``
capability directly rather than through a task plan. That keeps the
analysis an independent, explicitly user-triggered workflow: it needs no
plan, cannot be affected by a stale plan from another page, and still
goes through the tool registry, the input and output schemas, and the
filesystem policy.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from nexusai.app.api.dependencies import get_app_settings
from nexusai.app.api.schemas.rag import (
    AnswerRequest,
    AnswerResponse,
    CapabilityListResponse,
    DocumentListResponse,
    IngestRequest,
    IngestResponse,
    IngestTextRequest,
    RetrieveRequest,
    RetrieveResponse,
    SummariseRequest,
    SummariseResponse,
)
from nexusai.app.config import Settings
from nexusai.app.core.context import get_request_id
from nexusai.app.core.exceptions import ServiceUnavailableError, ValidationError
from nexusai.app.execution.csv_tool import CSV_CAPABILITIES
from nexusai.app.execution.registry import ToolError, ToolErrorCategory, ToolRisk
from nexusai.rag.capabilities import DocumentCapabilities
from nexusai.rag.service import DocumentIntelligenceService

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


class CsvAnalyseRequest(BaseModel):
    """Request to analyse a CSV file."""

    path: str = Field(..., min_length=1, description="Path to the CSV file")
    group_by: str | None = Field(
        default=None, description="Column to group the numeric aggregation by"
    )
    measure: str | None = Field(
        default=None, description="Numeric column to aggregate"
    )
    top_n: int = Field(default=10, ge=1, le=100, description="Rows to report per group")


class CsvAnalyseResponse(BaseModel):
    """Response for a CSV analysis request."""

    output: dict = Field(..., description="The analysis result")
    request_id: str = Field(..., description="Correlation ID for this request")


def _service_for(request: Request) -> DocumentIntelligenceService:
    """Return the document service owned by the running application."""
    service = getattr(request.app.state, "document_service", None)
    if service is None:
        raise ServiceUnavailableError(
            "The document service is not available.", code="service_unavailable"
        )
    return service


def _registry_for(request: Request):
    """Return the tool registry owned by the running application."""
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is None:
        raise ServiceUnavailableError(
            "The tool registry is not available.", code="registry_unavailable"
        )
    return registry


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Ingest a document",
    description=(
        "Ingest a PDF, DOCX, TXT or Markdown document into the local index. "
        "Re-ingesting unchanged content is reported as a duplicate."
    ),
)
def ingest_document(
    request: Request,
    payload: IngestRequest,
    settings: Settings = Depends(get_app_settings),
) -> IngestResponse:
    """Ingest a document from disk."""
    service = _service_for(request)
    result = service.ingest(payload.path, name=payload.name, metadata=payload.metadata)
    return IngestResponse(result=result, request_id=get_request_id())


@router.post(
    "/ingest-text",
    response_model=IngestResponse,
    summary="Ingest text directly",
    description="Ingest document text supplied in the request body.",
)
def ingest_text(
    request: Request,
    payload: IngestTextRequest,
    settings: Settings = Depends(get_app_settings),
) -> IngestResponse:
    """Ingest text supplied in the request body."""
    service = _service_for(request)
    result = service.ingest_text(
        payload.text,
        name=payload.name,
        metadata=payload.metadata,
    )
    return IngestResponse(result=result, request_id=get_request_id())


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List indexed documents",
)
def list_documents(
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> DocumentListResponse:
    """List the documents currently indexed."""
    service = _service_for(request)
    return DocumentListResponse(
        documents=service.documents(),
        chunk_count=service.chunk_count(),
        request_id=get_request_id(),
    )


@router.post(
    "/analyse-csv",
    response_model=CsvAnalyseResponse,
    summary="Analyse a CSV file",
    description=(
        "Profile a CSV file and aggregate over a column you name. The "
        "analysis runs through the registered 'data.analyse' capability, so "
        "it uses the same input and output validation and the same "
        "filesystem policy as every other capability. It needs no task plan."
    ),
)
def analyse_csv_endpoint(
    request: Request,
    payload: CsvAnalyseRequest,
    settings: Settings = Depends(get_app_settings),
) -> CsvAnalyseResponse:
    """Analyse a CSV file through the registered capability."""
    registry = _registry_for(request)

    capability = next(
        (name for name in CSV_CAPABILITIES if registry.has(name)),
        None,
    )
    if capability is None:
        raise ServiceUnavailableError(
            "The CSV analysis capability is not registered.", code="capability_missing"
        )

    tool = registry.get(capability)

    # Only a read-only, non-approval-gated capability may be invoked
    # directly. This endpoint must never be able to perform a state
    # change, so the check is explicit rather than assumed.
    if tool.risk != ToolRisk.SAFE or tool.requires_approval:
        raise ValidationError(
            "The CSV analysis capability is not eligible for direct invocation.",
            code="capability_not_directly_invocable",
        )

    try:
        output, _elapsed = registry.execute(
            capability,
            payload.model_dump(exclude_none=False),
        )
    except ToolError as error:
        if error.category in (
            ToolErrorCategory.INVALID_INPUT,
            ToolErrorCategory.PATH_NOT_ALLOWED,
        ):
            raise ValidationError(
                str(error),
                code=error.category.value,
                details=error.details,
            ) from error
        raise

    return CsvAnalyseResponse(
        output=output.model_dump(),
        request_id=get_request_id(),
    )


@router.post(
    "/retrieve",
    response_model=RetrieveResponse,
    summary="Retrieve relevant passages",
    description=(
        "Return the passages most relevant to a query, each with its source "
        "reference. Similarity scores rank the passages; they are not a "
        "measure of factual correctness."
    ),
)
def retrieve(
    request: Request,
    payload: RetrieveRequest,
    settings: Settings = Depends(get_app_settings),
) -> RetrieveResponse:
    """Retrieve passages relevant to a query."""
    service = _service_for(request)
    document_ids = {payload.document_id} if payload.document_id else None
    results = service.retrieve(
        payload.query,
        top_k=payload.top_k,
        min_score=payload.min_score,
        document_ids=document_ids,
    )
    return RetrieveResponse(
        query=payload.query,
        results=results,
        count=len(results),
        request_id=get_request_id(),
    )


@router.post(
    "/answer",
    response_model=AnswerResponse,
    summary="Answer a question from the indexed documents",
    description=(
        "Answer a question using only the retrieved evidence, and cite the "
        "passages used. When the indexed documents do not support an answer, "
        "the response says so explicitly rather than guessing."
    ),
)
def answer_question(
    request: Request,
    payload: AnswerRequest,
    settings: Settings = Depends(get_app_settings),
) -> AnswerResponse:
    """Answer a question grounded in the indexed documents."""
    service = _service_for(request)
    document_ids = {payload.document_id} if payload.document_id else None
    result = service.answer(
        payload.question,
        top_k=payload.top_k,
        document_ids=document_ids,
    )
    return AnswerResponse(answer=result, request_id=get_request_id())


@router.post(
    "/summarise",
    response_model=SummariseResponse,
    summary="Summarise a document or the indexed corpus",
    description=(
        "Produce a summary assembled from the source text, with citations to "
        "the passages used."
    ),
)
def summarise(
    request: Request,
    payload: SummariseRequest,
    settings: Settings = Depends(get_app_settings),
) -> SummariseResponse:
    """Summarise a document, or the passages relevant to a question."""
    service = _service_for(request)
    result = service.summarize(
        document_id=payload.document_id,
        top_k=payload.top_k,
        question=payload.question,
    )
    return SummariseResponse(summary=result, request_id=get_request_id())


@router.get(
    "/capabilities",
    response_model=CapabilityListResponse,
    summary="List the planner capabilities this module satisfies",
    description=(
        "Return the capability names the planner can bind to this module, "
        "matching the planner's required_capabilities values exactly."
    ),
)
def list_capabilities(
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> CapabilityListResponse:
    """List the capability names this module satisfies."""
    service = _service_for(request)
    capabilities = DocumentCapabilities(service)
    return CapabilityListResponse(
        capabilities=capabilities.capabilities(),
        request_id=get_request_id(),
    )
