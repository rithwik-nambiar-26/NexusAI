"""Capability adapter for the planner.

The Day 3 planner names the tools a task needs in
``required_capabilities``. This module exposes the document-intelligence
operations under exactly those names, so the Day 5 registry can bind a
planner task to a real operation without a translation layer.

The capability names match the planner verbatim:

* ``document.read`` — read a document and return its extracted text
* ``document.extract`` — retrieve the passages relevant to a query
* ``llm.summarise`` — produce a grounded summary

Every capability is a read-only operation over the local index. None of
them executes anything, and none of them authorises anything.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from nexusai.rag.schemas import ExtractionStatus, Summary
from nexusai.rag.service import DocumentIntelligenceService

#: Capabilities this module can satisfy.
SUPPORTED_CAPABILITIES: frozenset[str] = frozenset(
    {
        "document.read",
        "document.extract",
        "llm.summarise",
    }
)


class CapabilityError(Exception):
    """Raised when a capability is invoked with unusable arguments."""


class DocumentCapabilities:
    """Operations exposed to the planner under the capability names."""

    def __init__(self, service: DocumentIntelligenceService) -> None:
        self._service = service
        self._registry: dict[str, Callable[..., Any]] = {
            "document.read": self.document_read,
            "document.extract": self.document_extract,
            "llm.summarise": self.llm_summarise,
        }

    # ------------------------------------------------------------------
    # Capability implementations
    # ------------------------------------------------------------------
    def document_read(
        self,
        path: str | Path | None = None,
        *,
        document_id: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """Read a document and return its extracted text.

        Either a ``path`` (which is ingested if needed) or an already
        indexed ``document_id`` must be supplied.
        """
        if path is not None:
            result = self._service.ingest(Path(path))
            if result.status != ExtractionStatus.OK or result.document is None:
                raise CapabilityError(
                    f"document.read could not read {path}: {result.message}"
                )
            document = result.document
        elif document_id is not None:
            document = next(
                (d for d in self._service.documents() if d.document_id == document_id),
                None,
            )
            if document is None:
                raise CapabilityError(
                    f"document.read: no indexed document with id {document_id}"
                )
        else:
            raise CapabilityError("document.read requires a path or a document_id")

        return {
            "document_id": document.document_id,
            "name": document.name,
            "doc_format": document.doc_format.value,
            "page_count": document.page_count,
            "char_count": document.char_count,
            "text": document.full_text,
            "sections": [
                {
                    "section_index": section.section_index,
                    "page_number": section.page_number,
                    "heading": section.heading,
                    "text": section.text,
                }
                for section in document.sections
            ],
        }

    def document_extract(
        self,
        query: str | None = None,
        *,
        document_id: str | None = None,
        document_ids: list[str] | None = None,
        document_path: str | None = None,
        top_k: int = 5,
        **_: Any,
    ) -> dict[str, Any]:
        """Retrieve the passages most relevant to a query.

        Returns the passages with their source references, so a downstream
        verification step can check each one against the original text.

        The retrieval is restricted to the documents in scope. The scope is
        either a list of document ids or a single one; when neither is
        given, the whole corpus is searched, which is only correct when
        the caller has asked for a cross-document question.
        """
        if not query:
            raise CapabilityError("document.extract requires a query")

        scope = self._scope(document_id, document_ids, document_path)
        results = self._service.retrieve(
            query,
            top_k=top_k,
            document_ids=set(scope) if scope else None,
        )
        # A passage that shares nothing with the query is not evidence for
        # it, however similar it looked to the vector search.
        results = [result for result in results if result.score > 0]

        return {
            "query": query,
            "passages": [
                {
                    "chunk_id": result.chunk.chunk_id,
                    "document_id": result.chunk.document_id,
                    "document_name": result.document_name,
                    "page_number": result.chunk.page_number,
                    "heading": result.chunk.heading,
                    "score": result.score,
                    "source_reference": result.source_reference,
                    "text": result.chunk.text,
                }
                for result in results
            ],
            "count": len(results),
            "documents": sorted({result.chunk.document_id for result in results}),
        }

    def llm_summarise(
        self,
        document_id: str | None = None,
        *,
        document_ids: list[str] | None = None,
        document_path: str | None = None,
        question: str | None = None,
        top_k: int = 5,
        **_: Any,
    ) -> dict[str, Any]:
        """Produce a grounded summary of a document or of relevant passages.

        The summary covers only the documents in scope, and never blends
        two documents into one narrative.
        """
        scope = self._scope(document_id, document_ids, document_path)
        summary: Summary = self._service.summarize(
            document_id=document_id,
            document_ids=list(scope) if scope else None,
            top_k=top_k,
            question=question,
        )
        return {
            "status": summary.status.value,
            "summary_text": summary.summary_text,
            "citations": summary.citations,
            "method": summary.method,
            "sections": summary.sections,
            "documents": summary.documents,
            "evidence": [
                {
                    "chunk_id": span.chunk_id,
                    "document_id": span.document_id,
                    "document_name": span.document_name,
                    "page_number": span.page_number,
                    "source_reference": span.source_reference,
                    "text": span.text,
                }
                for span in summary.evidence
            ],
        }

    def _scope(
        self,
        document_id: str | None,
        document_ids: list[str] | None,
        document_path: str | None = None,
    ) -> list[str]:
        """Return the documents in scope, without duplicates.

        A path is resolved to the document it was indexed from, so a
        request that names a file is about that document. An explicit
        document id takes precedence: it is the more specific
        instruction.
        """
        scope: list[str] = []
        for candidate in list(document_ids or []) + ([document_id] if document_id else []):
            if candidate and candidate not in scope:
                scope.append(candidate)
        if scope:
            return scope

        if document_path:
            resolved = self._service.document_id_for_path(document_path)
            if resolved:
                return [resolved]
        return []

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    def supports(self, capability: str) -> bool:
        """Return True when this adapter can serve a capability."""
        return capability in self._registry

    def invoke(self, capability: str, **kwargs: Any) -> Any:
        """Invoke a capability by name.

        Raises:
            CapabilityError: The capability is not supported.
        """
        handler = self._registry.get(capability)
        if handler is None:
            raise CapabilityError(f"Unsupported capability: {capability}")
        return handler(**kwargs)

    def capabilities(self) -> list[str]:
        """Return the capability names this adapter serves."""
        return sorted(self._registry)


def get_capabilities(service: DocumentIntelligenceService | None = None) -> DocumentCapabilities:
    """Return a capability adapter bound to a document service."""
    if service is None:
        from nexusai.rag.service import get_document_service

        service = get_document_service()
    return DocumentCapabilities(service)
