"""Document intelligence API routes.

These endpoints expose ingestion, retrieval, grounded question answering
and grounded summarisation. They read and index documents; they never
execute anything a document contains, and they never authorise an
operation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

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
from nexusai.rag.capabilities import get_capabilities
from nexusai.rag.service import DocumentIntelligenceService, get_document_service

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def _service_for(request: Request) -> DocumentIntelligenceService:
    """Return the document service owned by the running application.

    Each application instance owns its own vector index, so a test
    application never reads or writes the developer's working index.
    """
    service = getattr(request.app.state, "document_service", None)
    if service is None:
        # The application was built without a service (for example because
        # the store directory was unwritable). Fall back to the shared
        # instance rather than failing outright.
        service = get_document_service()
    return service


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
    capabilities = get_capabilities(_service_for(request))
    return CapabilityListResponse(
        capabilities=capabilities.capabilities(),
        request_id=get_request_id(),
    )
