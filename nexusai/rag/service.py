"""Document intelligence service for NexusAI.

Ties ingestion, chunking, embedding, indexing and retrieval together, and
provides grounded question answering and summarisation on top of them.

Three principles shape this module:

* **Retrieval and answer generation are separate.** Retrieval returns
  evidence; the answer is constructed from that evidence. An answer is
  never produced without a citation.
* **Similarity is not truth.** A similarity score says a passage looks
  relevant, not that it is correct. When the evidence does not support an
  answer, the service says so explicitly instead of guessing.
* **Documents are data, never instructions.** Text found inside a
  document is quoted, never obeyed. Nothing in a document is executed.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from nexusai.app.core.logging import get_logger
from nexusai.app.security.paths import PathPolicy, PathPolicyError
from nexusai.rag.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    chunk_document,
    document_id_for,
    normalize_text,
)
from nexusai.rag.embeddings import Embedder, HashingEmbedder
from nexusai.rag.extractors import (
    CorruptedDocumentError,
    ExtractionError,
    UnsupportedFormatError,
    extract_document,
)
from nexusai.rag.schemas import (
    Answer,
    AnswerStatus,
    Document,
    DocumentFormat,
    DocumentSection,
    EvidenceSpan,
    ExtractionStatus,
    IngestionResult,
    RetrievedChunk,
    Summary,
)
from nexusai.rag.store import VectorStore
from nexusai.rag.summarisation import build_structured_summary, to_dict

logger = get_logger("rag.service")

#: Default directory for the persisted vector store.
DEFAULT_STORE_DIR = Path("artifacts/vectors")

#: Minimum retrieval score for a chunk to be considered supporting evidence.
DEFAULT_MIN_EVIDENCE_SCORE = 0.05

#: How each path-policy failure is reported by ingestion.
_POLICY_STATUS: dict[str, ExtractionStatus] = {
    "unsupported_type": ExtractionStatus.UNSUPPORTED_FORMAT,
    "not_found": ExtractionStatus.FAILED,
    "not_a_file": ExtractionStatus.FAILED,
    "not_readable": ExtractionStatus.FAILED,
    "unresolvable_path": ExtractionStatus.FAILED,
    "no_roots": ExtractionStatus.PATH_NOT_ALLOWED,
    "outside_root": ExtractionStatus.PATH_NOT_ALLOWED,
}

#: Default number of chunks to retrieve per query.
DEFAULT_TOP_K = 5

#: Fraction of the top result's score that a passage must reach to be
#: treated as supporting evidence. This is relative rather than absolute
#: so the rule behaves the same way under embedders whose score scale
#: differs, and it stops weakly-related passages from being included
#: merely to fill a result count.
DEFAULT_RELATIVE_EVIDENCE_RATIO = 0.5

#: Patterns that suggest a document is trying to give the system orders.
#: Matched content is still indexed, but it is flagged so that a reviewer
#: can see it. Nothing here causes a document to be obeyed.
_INSTRUCTION_PATTERNS = (
    re.compile(r"\bignore (?:all |any )?(?:previous|prior|above)\b", re.IGNORECASE),
    re.compile(r"\bdisregard (?:the )?(?:previous|prior|above|system)\b", re.IGNORECASE),
    re.compile(r"\byou are now\b", re.IGNORECASE),
    re.compile(r"\bsystem prompt\b", re.IGNORECASE),
    re.compile(r"\bexecute (?:the )?(?:following|this) (?:command|code|script)\b", re.IGNORECASE),
    re.compile(r"```\s*(?:python|bash|sh|shell|powershell)\b", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
)

#: Sentence splitting used when selecting supporting sentences.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class DocumentIntelligenceService:
    """Document ingestion, retrieval and grounded answer generation.

    The service holds no FastAPI dependency, so it can be used from the
    CLI, the Streamlit UI, the experiment harness or the API.
    """

    def __init__(
        self,
        store_dir: Path | str = DEFAULT_STORE_DIR,
        embedder: Embedder | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        min_evidence_score: float = DEFAULT_MIN_EVIDENCE_SCORE,
        relative_evidence_ratio: float = DEFAULT_RELATIVE_EVIDENCE_RATIO,
        path_policy: PathPolicy | None = None,
        llm_client=None,
    ) -> None:
        self.store_dir = Path(store_dir)
        self.embedder = embedder or HashingEmbedder()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_evidence_score = min_evidence_score
        self.relative_evidence_ratio = relative_evidence_ratio
        # The optional local LLM. When it is None, or when it is not
        # answering, summarisation uses the extractive method.
        self.llm_client = llm_client
        # When a policy is supplied, only paths inside its allowed roots
        # may be read. With no policy the service is unrestricted, which is
        # only appropriate for a local, single-user tool.
        self.path_policy = path_policy

        self.store = VectorStore(self.store_dir, self.embedder.dimension)
        self.store.load()
        self._documents: dict[str, Document] = {}
        # The chunk index is persisted, but the document metadata that
        # describes it was not, so a restart would know the chunks but not
        # the documents they came from. The metadata is restored here.
        self._restore_documents()

    def _restore_documents(self) -> None:
        """Rebuild the document metadata from the persisted chunk index.

        A chunk carries its document id, page number and heading, which is
        enough to describe the document it came from. The name and path
        are recovered from the store's own document-name index.
        """
        metadata_path = self.store_dir / "documents.json"
        if not metadata_path.exists():
            return

        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return

        for document_id, payload in raw.items():
            if not isinstance(payload, dict):
                continue
            try:
                self._documents[document_id] = Document.model_validate(payload)
            except Exception:
                continue

        # Only keep the documents that still have chunks in the index.
        known = self.store.document_ids()
        self._documents = {
            document_id: document
            for document_id, document in self._documents.items()
            if document_id in known
        }

    def _save_documents(self) -> None:
        """Persist the document metadata beside the chunk index."""
        try:
            self.store_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                document_id: document.model_dump(mode="json")
                for document_id, document in self._documents.items()
            }
            (self.store_dir / "documents.json").write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        except OSError:
            logger.warning("Could not persist the document metadata")

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    def _resolve_readable_path(self, path: Path | str) -> Path:
        """Resolve *path* under the path policy.

        Raises:
            PathPolicyError: The path may not be read.
        """
        if self.path_policy is None:
            return Path(path)
        return self.path_policy.resolve(path)

    def ingest(
        self,
        path: Path | str,
        *,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IngestionResult:
        """Ingest a document into the index.

        Re-ingesting a document with unchanged content is a no-op that
        reports ``duplicate=True``.

        Args:
            path: Path to the document. When a path policy is configured,
                the path must resolve inside an allowed root.
            name: Display name; defaults to the file name.
            metadata: Extra document metadata to store.

        Returns:
            An :class:`IngestionResult` describing the outcome.
        """
        try:
            file_path = self._resolve_readable_path(path)
        except PathPolicyError as exc:
            logger.warning(
                "Document ingestion refused by path policy",
                extra={"code": exc.code, "path": str(path)},
            )
            return IngestionResult(
                status=_POLICY_STATUS.get(exc.code, ExtractionStatus.PATH_NOT_ALLOWED),
                message=str(exc),
            )

        try:
            sections, page_count, doc_format = extract_document(file_path)
        except UnsupportedFormatError as exc:
            return IngestionResult(
                status=ExtractionStatus.UNSUPPORTED_FORMAT,
                message=str(exc),
            )
        except CorruptedDocumentError as exc:
            return IngestionResult(
                status=ExtractionStatus.CORRUPTED,
                message=str(exc),
            )
        except ExtractionError as exc:
            return IngestionResult(
                status=ExtractionStatus.FAILED,
                message=str(exc),
            )

        full_text = "\n\n".join(section.text for section in sections)
        if not full_text.strip():
            return IngestionResult(
                status=ExtractionStatus.EMPTY,
                message=f"No text could be extracted from {file_path.name}",
            )

        document_name = name or file_path.name
        document_id = document_id_for(document_name, full_text)

        # Duplicate ingestion: the same name and content is already indexed.
        if self.store.has_document(document_id):
            return IngestionResult(
                document=self._documents.get(document_id),
                status=ExtractionStatus.OK,
                duplicate=True,
                chunk_count=len(self.store.chunks_for_document(document_id)),
                message=f"Document already indexed as {document_id}",
            )

        document = Document(
            document_id=document_id,
            name=document_name,
            source_path=str(file_path),
            doc_format=doc_format,
            content_hash=document_id_for("", full_text).removeprefix("doc_"),
            sections=sections,
            page_count=page_count,
            char_count=len(full_text),
            metadata=dict(metadata or {}),
        )

        chunks = chunk_document(
            document,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        if not chunks:
            return IngestionResult(
                document=document,
                status=ExtractionStatus.EMPTY,
                message=f"No usable chunks produced from {file_path.name}",
            )

        vectors = self.embedder.embed([chunk.text for chunk in chunks])
        self.store.add_many(chunks, vectors, {document_id: document_name})

        self._documents[document_id] = document
        self.store.save()
        self._save_documents()

        logger.info(
            "Document ingested",
            extra={
                "document_id": document_id,
                "document_name": document_name,
                "chunks": len(chunks),
                "doc_format": doc_format.value,
            },
        )

        return IngestionResult(
            document=document,
            status=ExtractionStatus.OK,
            chunk_count=len(chunks),
            message=f"Ingested {len(chunks)} chunks from {document_name}",
        )

    def ingest_text(
        self,
        text: str,
        *,
        name: str = "untitled.md",
        metadata: dict[str, Any] | None = None,
    ) -> IngestionResult:
        """Ingest text directly, without a file on disk.

        Used for documents that are supplied in-band rather than as files.
        """
        normalized = normalize_text(text)
        if not normalized:
            return IngestionResult(
                status=ExtractionStatus.EMPTY,
                message="The supplied text was empty",
            )

        document_id = document_id_for(name, normalized)
        if self.store.has_document(document_id):
            return IngestionResult(
                document=self._documents.get(document_id),
                status=ExtractionStatus.OK,
                duplicate=True,
                message=f"Document already indexed as {document_id}",
            )

        document = Document(
            document_id=document_id,
            name=name,
            source_path=None,
            doc_format=DocumentFormat.MARKDOWN,
            content_hash=document_id_for("", normalized).removeprefix("doc_"),
            sections=[
                _section_from_text(normalized)
            ],
            char_count=len(normalized),
            metadata=dict(metadata or {}),
        )

        chunks = chunk_document(
            document,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        if not chunks:
            return IngestionResult(
                document=document,
                status=ExtractionStatus.EMPTY,
                message="No usable chunks produced",
            )

        vectors = self.embedder.embed([chunk.text for chunk in chunks])
        self.store.add_many(chunks, vectors, {document_id: name})
        self._documents[document_id] = document
        self.store.save()
        self._save_documents()

        return IngestionResult(
            document=document,
            status=ExtractionStatus.OK,
            chunk_count=len(chunks),
            message=f"Ingested {len(chunks)} chunks from {name}",
        )

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = 0.0,
        document_ids: set[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve the chunks most relevant to a query.

        Args:
            query: The query text.
            top_k: Maximum number of results.
            min_score: Minimum similarity a result must reach.
            document_ids: Restrict retrieval to these documents.

        Returns:
            Retrieved chunks ordered by descending score.
        """
        if not query.strip() or not len(self.store):
            return []

        vector = self.embedder.embed([query])[0]
        return self.store.search(
            vector,
            top_k=top_k,
            min_score=min_score,
            document_ids=document_ids,
        )

    # ------------------------------------------------------------------
    # Grounded question answering
    # ------------------------------------------------------------------
    def answer(
        self,
        question: str,
        top_k: int = DEFAULT_TOP_K,
        document_ids: set[str] | None = None,
    ) -> Answer:
        """Answer a question using only the retrieved evidence.

        The answer is extractive: it is assembled from sentences in the
        retrieved chunks. When no retrieved chunk is relevant enough, the
        result is an explicit insufficient-evidence response rather than a
        guess.
        """
        if not question.strip():
            return Answer(
                question=question,
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                insufficient_reason="The question was empty.",
            )

        if not len(self.store):
            return Answer(
                question=question,
                status=AnswerStatus.NO_DOCUMENTS,
                insufficient_reason="No documents have been indexed yet.",
            )

        retrieved = self.retrieve(
            question,
            top_k=top_k,
            min_score=self.min_evidence_score,
            document_ids=document_ids,
        )

        if not retrieved:
            return Answer(
                question=question,
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                insufficient_reason=(
                    "No indexed passage was similar enough to the question to be "
                    "treated as supporting evidence."
                ),
            )

        evidence = self._select_evidence(question, retrieved)
        if not evidence:
            return Answer(
                question=question,
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                insufficient_reason=(
                    "The retrieved passages did not contain a statement that "
                    "addresses the question."
                ),
            )

        answer_text = " ".join(span.text for span in evidence)
        citations = list(dict.fromkeys(span.source_reference for span in evidence))
        confidence = max(span.score for span in evidence)

        logger.info(
            "Question answered",
            extra={
                "question": question[:120],
                "evidence_spans": len(evidence),
                "confidence": confidence,
            },
        )

        return Answer(
            question=question,
            answer_text=answer_text,
            status=AnswerStatus.ANSWERED,
            evidence=evidence,
            citations=citations,
            confidence=confidence,
        )

    def _select_evidence(
        self,
        question: str,
        retrieved: list[RetrievedChunk],
    ) -> list[EvidenceSpan]:
        """Select the sentences that best address the question.

        Each retrieved chunk contributes its most question-relevant
        sentence, provided that sentence actually shares terms with the
        question. A chunk that shares nothing with the question contributes
        nothing, so unrelated passages are not included merely to fill a
        result count.

        Sentence relevance is weighted by inverse document frequency, so a
        term that occurs in many chunks ("period") counts for less than a
        distinctive one ("warranty"). Only sentences reaching a fraction of
        the best weighted score are kept, so a single strong match is not
        diluted by weak ones.
        """
        question_terms = _content_terms(question)
        if not question_terms:
            return []

        if not retrieved:
            return []

        idf = self._inverse_document_frequency()
        top_score = retrieved[0].score
        cutoff = max(self.min_evidence_score, top_score * self.relative_evidence_ratio)

        # Rank every candidate sentence across all retrieved chunks by its
        # IDF-weighted overlap, then keep only those that reach a fraction
        # of the best overlap found. A passage that shares only an
        # incidental term with the question is dropped.
        candidates: list[tuple[float, RetrievedChunk, str]] = []
        for result in retrieved:
            if result.score < cutoff:
                break
            # A chunk's heading is part of its context: a passage under
            # "Warranty exclusions" is about exclusions even when the
            # sentence itself does not use the word.
            context_terms = (
                _content_terms(result.chunk.heading) if result.chunk.heading else set()
            )
            sentence = _best_sentence(
                result.chunk.text, question_terms, idf, context_terms
            )
            if sentence is None:
                continue
            weight = _shared_weight(sentence, question_terms, idf)
            if context_terms:
                weight += sum(
                    idf.get(term, 1.0)
                    for term in _matched_terms(context_terms, question_terms)
                )
            candidates.append((weight, result, sentence))

        if not candidates:
            return []

        candidates.sort(key=lambda item: -item[0])
        best_weight = candidates[0][0]
        weight_cutoff = best_weight * self.relative_evidence_ratio

        evidence: list[EvidenceSpan] = []
        for weight, result, sentence in candidates:
            if weight < weight_cutoff:
                break
            evidence.append(
                EvidenceSpan(
                    text=sentence,
                    chunk_id=result.chunk.chunk_id,
                    document_id=result.chunk.document_id,
                    document_name=result.document_name,
                    page_number=result.chunk.page_number,
                    source_reference=result.source_reference,
                    score=result.score,
                )
            )
        return evidence

    def _inverse_document_frequency(self) -> dict[str, float]:
        """Return the inverse document frequency of each indexed term.

        Terms that occur in many chunks carry less discriminative weight,
        so a sentence that matches a rare term outranks one that matches a
        common one. The measure is computed over the indexed corpus, which
        is what makes it meaningful for this corpus and not a universal
        constant.
        """
        chunks = self.store.all_chunks()
        if not chunks:
            return {}

        document_frequency: dict[str, int] = {}
        for chunk in chunks:
            # Headings are part of a chunk's searchable context, so they
            # count towards document frequency too.
            terms = set(_content_terms(chunk.text))
            if chunk.heading:
                terms |= _content_terms(chunk.heading)
            for term in terms:
                document_frequency[term] = document_frequency.get(term, 0) + 1

        total = len(chunks)
        return {
            term: math.log((total + 1) / (frequency + 1)) + 1.0
            for term, frequency in document_frequency.items()
        }

    # ------------------------------------------------------------------
    # Summarisation
    # ------------------------------------------------------------------
    def summarize(
        self,
        document_id: str | None = None,
        top_k: int = DEFAULT_TOP_K,
        question: str | None = None,
        document_ids: list[str] | None = None,
    ) -> Summary:
        """Summarise a document, or the passages most relevant to a question.

        Two methods are possible and the result always says which was
        used.

        When a local LLM is configured and answering, it writes the
        summary and the method is ``"llm"``. The model is given only the
        retrieved evidence and is told not to add anything that is not in
        it.

        Otherwise the summary is *extractive*: sentences are selected from
        the source text and organised into an overview, the decisions and
        the action items. Nothing is generated, so every statement can be
        checked against the source, and the method is ``"extractive"``.

        **One document is summarised at a time.** When several documents
        are in scope, each is summarised under its own heading and the
        documents are never blended into a single narrative, because a
        reader would then have no way to tell which document a statement
        came from.

        A summary is never produced from no evidence: the result is an
        explicit insufficient-evidence response.
        """
        scope = self._resolve_scope(document_id, document_ids)

        if scope is not None:
            missing = [doc for doc in scope if not self.store.has_document(doc)]
            if missing and len(missing) == len(scope):
                return Summary(
                    source_document_id=scope[0] if len(scope) == 1 else None,
                    status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                    method="none",
                    documents=list(scope),
                    summary_text=(
                        "That document is not indexed, so there is nothing to "
                        "summarise."
                    ),
                )
            scope = [doc for doc in scope if self.store.has_document(doc)]
            document_ids = set(scope) if scope else None
        else:
            document_ids = None

        if question:
            retrieved = self.retrieve(
                question,
                top_k=top_k,
                min_score=self.min_evidence_score,
                document_ids=document_ids,
            )
        else:
            retrieved = self._representative_chunks(document_ids=document_ids, top_k=top_k)

        if not retrieved:
            return Summary(
                source_document_id=document_id,
                status=AnswerStatus.NO_DOCUMENTS,
                method="none",
                documents=list(scope) if scope else [],
                summary_text=(
                    "No document was found that matches the request, so there "
                    "is nothing to summarise."
                ),
            )

        evidence = self._select_evidence(
            question or "summary key points overview",
            retrieved,
        )
        if not evidence:
            evidence = [
                EvidenceSpan(
                    text=result.chunk.text.strip(),
                    chunk_id=result.chunk.chunk_id,
                    document_id=result.chunk.document_id,
                    document_name=result.document_name,
                    page_number=result.chunk.page_number,
                    source_reference=result.source_reference,
                    score=result.score,
                )
                for result in retrieved
                if result.chunk.text.strip()
            ]

        if not evidence:
            return Summary(
                source_document_id=document_id,
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                method="none",
                documents=list(scope) if scope else [],
                summary_text=(
                    "The retrieved passages did not contain anything that "
                    "could be summarised."
                ),
            )

        # A local LLM is used when one is configured and answering. The
        # result records which method produced the summary.
        llm_summary = self._summarize_with_llm(evidence, question)
        if llm_summary is not None:
            llm_summary.documents = list(scope) if scope else sorted(
                {span.document_id for span in evidence}
            )
            return llm_summary

        structured = build_structured_summary(
            evidence,
            question=question,
            groups=self._groups_for(scope, evidence),
        )
        if not structured.sufficient:
            return Summary(
                source_document_id=document_id,
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                method="extractive",
                documents=list(scope) if scope else [],
                summary_text=structured.reason
                or "The evidence did not support a summary.",
                evidence=evidence,
                citations=list(dict.fromkeys(span.source_reference for span in evidence)),
            )

        return Summary(
            source_document_id=document_id,
            summary_text=structured.to_text(),
            evidence=evidence,
            citations=structured.citations,
            status=AnswerStatus.ANSWERED,
            method="extractive",
            documents=structured.documents,
            sections=to_dict(structured)["sections"],
        )

    def _resolve_scope(
        self,
        document_id: str | None,
        document_ids: list[str] | None,
    ) -> list[str] | None:
        """Return the documents in scope, or None when the scope is open.

        A single document and a list of documents are both accepted. The
        result preserves the order the documents were given in and drops
        duplicates.
        """
        scope: list[str] = []
        for candidate in list(document_ids or []) + ([document_id] if document_id else []):
            if candidate and candidate not in scope:
                scope.append(candidate)
        return scope or None

    def _groups_for(
        self,
        scope: list[str] | None,
        evidence: list[EvidenceSpan],
    ) -> list[tuple[str, str, list[DocumentSection]]]:
        """Return the documents to summarise, each with its own sections.

        A document's sections are the natural unit for a structured
        summary: a heading such as "Action items" says what the text under
        it is, which a chunk boundary does not.

        When the scope is open, the documents are taken from the evidence
        that was retrieved, so the summary still separates one document
        from another rather than blending them.
        """
        names = {span.document_id: span.document_name for span in evidence}
        wanted = list(scope) if scope else sorted(names)

        groups: list[tuple[str, str, list[DocumentSection]]] = []
        for wanted_id in wanted:
            document = self._documents.get(wanted_id)
            if document is None:
                continue
            groups.append(
                (wanted_id, document.name or names.get(wanted_id, ""), list(document.sections))
            )
        return groups

    def _summarize_with_llm(
        self,
        evidence: list[EvidenceSpan],
        question: str | None,
    ) -> Summary | None:
        """Summarise with the local LLM, if there is one that is working.

        Returns None when there is no usable LLM, so the caller falls
        back to the extractive method. A failure is never presented as a
        summary.
        """
        if self.llm_client is None:
            return None

        try:
            if not self.llm_client.is_available():
                return None
            generated = self.llm_client.summarise(
                [
                    {
                        "text": span.text,
                        "source_reference": span.source_reference,
                    }
                    for span in evidence
                ],
                instruction=question or "",
            )
        except Exception:
            logger.warning(
                "The local LLM could not produce a summary; the extractive "
                "method was used instead",
                exc_info=True,
            )
            return None

        if not generated.sufficient:
            return Summary(
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                method="llm",
                summary_text=(
                    "The local model reported that the retrieved evidence did "
                    "not support a summary."
                ),
                evidence=evidence,
                citations=list(dict.fromkeys(span.source_reference for span in evidence)),
            )

        sections: list[dict[str, Any]] = []
        if generated.overview:
            sections.append(
                {
                    "name": "overview",
                    "title": "Overview",
                    "items": [
                        {
                            "text": generated.overview,
                            "source_reference": "local model",
                            "owner": None,
                            "due": None,
                        }
                    ],
                }
            )
        for name, title, values in (
            ("decisions", "Decisions", generated.decisions),
            ("action_items", "Action items", generated.action_items),
        ):
            if values:
                sections.append(
                    {
                        "name": name,
                        "title": title,
                        "items": [
                            {
                                "text": value,
                                "source_reference": "local model",
                                "owner": None,
                                "due": None,
                            }
                            for value in values
                        ],
                    }
                )

        text_parts: list[str] = []
        for section in sections:
            text_parts.append(f"{section['title']}:")
            for item in section["items"]:
                text_parts.append(f"- {item['text']}")
            text_parts.append("")

        return Summary(
            summary_text="\n".join(text_parts).strip(),
            evidence=evidence,
            citations=list(dict.fromkeys(span.source_reference for span in evidence)),
            status=AnswerStatus.ANSWERED,
            method="llm",
            sections=sections,
        )

    def _representative_chunks(
        self,
        document_ids: set[str] | None,
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Return representative chunks when no query is supplied.

        Chunks are ordered by their position in the document, so a summary
        without a query reads in source order rather than by score.
        """
        candidates = [
            chunk
            for chunk in self.store.all_chunks()
            if document_ids is None or chunk.document_id in document_ids
        ]
        if not candidates:
            return []

        candidates.sort(key=lambda c: (c.document_id, c.chunk_index))
        chosen = candidates[:top_k]

        results: list[RetrievedChunk] = []
        for rank, chunk in enumerate(chosen, start=1):
            document_name = self.store.get_document_name(chunk.chunk_id)
            results.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=1.0,
                    document_name=document_name,
                    source_reference=chunk.source_reference(document_name),
                    rank=rank,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------
    def documents(self) -> list[Document]:
        """Return the documents known to the store."""
        return [
            self._documents[document_id]
            for document_id in sorted(self.store.document_ids())
            if document_id in self._documents
        ]

    def chunk_count(self) -> int:
        """Return the number of chunks held by the store."""
        return len(self.store)

    def is_ready(self) -> bool:
        """Return True when the service can serve queries."""
        return self.embedder is not None

    def clear(self) -> None:
        """Remove every indexed document and chunk."""
        self.store.clear()
        self._documents.clear()
        self.store.save()


# ----------------------------------------------------------------------
# Module-level helpers
# ----------------------------------------------------------------------
_service: DocumentIntelligenceService | None = None


def get_document_service() -> DocumentIntelligenceService:
    """Return the shared document intelligence service."""
    global _service
    if _service is None:
        _service = DocumentIntelligenceService()
    return _service


def reset_document_service() -> None:
    """Reset the shared document service (used by tests)."""
    global _service
    _service = None


def _section_from_text(text: str):
    """Build a single document section covering all of *text*."""
    from nexusai.rag.schemas import DocumentSection

    return DocumentSection(
        text=text,
        page_number=None,
        section_index=0,
        heading=None,
        start_offset=0,
        end_offset=len(text),
    )


def _content_terms(text: str) -> set[str]:
    """Return the content-bearing stemmed terms of *text*.

    Stop words are removed so that a sentence is only considered relevant
    when it shares meaningful terms with the question. Terms are stemmed so
    that "exclude", "excluded" and "exclusion" are recognised as the same
    word.
    """
    from nexusai.rag.embeddings import tokenize

    tokens = tokenize(text)
    return {
        _stem(token)
        for token in tokens
        if token not in _STOP_WORDS and len(token) > 2
    }


#: Suffixes stripped when stemming a word.
_STEM_SUFFIXES = ("ations", "ation", "ions", "ion", "ing", "ied", "ies", "ed", "es", "s")

#: Minimum length of a stem before a suffix may be stripped.
_MIN_STEM_LENGTH = 4


def _stem(word: str) -> str:
    """Return a light stem of *word*.

    Only common inflections are removed. The stem is used for matching
    question terms against document terms, not for presentation, so a
    slightly over-eager stem is harmless.
    """
    if len(word) <= _MIN_STEM_LENGTH:
        return word
    for suffix in _STEM_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_STEM_LENGTH:
            return word[: -len(suffix)]
    return word


#: Minimum length of the shorter stem for two stems to be treated as the
#: same word by prefix matching.
_MIN_PREFIX_MATCH = 5


def _matched_terms(terms: set[str], other: set[str]) -> set[str]:
    """Return the terms of *terms* that match a term in *other*.

    Two stems match when they are equal, or when the shorter one is a
    prefix of the longer and is at least five characters long. Prefix
    matching relates forms that a light stemmer cannot unify, such as
    "exclus" and "exclud".
    """
    matched: set[str] = set()
    for term in terms:
        for candidate in other:
            if term == candidate:
                matched.add(term)
                break
            shorter, longer = sorted((term, candidate), key=len)
            if len(shorter) >= _MIN_PREFIX_MATCH and longer.startswith(shorter):
                matched.add(term)
                break
    return matched


def _shared_weight(
    sentence: str,
    question_terms: set[str],
    idf: dict[str, float] | None = None,
) -> float:
    """Return the IDF-weighted overlap between a sentence and the question."""
    weights = idf or {}
    shared = _matched_terms(_content_terms(sentence), question_terms)
    return sum(weights.get(term, 1.0) for term in shared)


def _best_sentence(
    text: str,
    question_terms: set[str],
    idf: dict[str, float] | None = None,
    context_terms: set[str] | None = None,
) -> str | None:
    """Return the sentence of *text* that best matches *question_terms*.

    Matching is weighted by inverse document frequency when an *idf* table
    is supplied, so a distinctive term outweighs a common one. When
    *context_terms* is given (a chunk's heading, for example) those terms
    also count towards the match, so a passage under a heading such as
    "Warranty exclusions" is recognised as answering a question about
    exclusions even when the sentence itself does not repeat the word.

    Returns ``None`` when no sentence shares a term with the question.
    """
    weights = idf or {}
    best: str | None = None
    best_score = 0.0

    for sentence in _SENTENCE_RE.split(text):
        stripped = sentence.strip()
        if not stripped:
            continue
        sentence_terms = _content_terms(stripped)
        shared = _matched_terms(sentence_terms, question_terms)
        if context_terms:
            shared |= _matched_terms(context_terms, question_terms)
        if not shared:
            continue
        score = sum(weights.get(term, 1.0) for term in shared)
        if score > best_score:
            best_score = score
            best = stripped

    return best


#: Small stop-word list used when matching sentences to a question.
_STOP_WORDS = frozenset(
    ["the", "a", "an", "and", "or", "but", "if", "then", "else", "for", "of", "to", "in", "on", "at", "by", "with", "without", "from", "as", "is", "are", "was", "were", "be", "been", "being", "it", "its", "this", "that", "these", "those", "there", "here", "which", "what", "who", "whom", "whose", "when", "where", "why", "how", "do", "does", "did", "doing", "have", "has", "had", "having", "will", "would", "shall", "should", "can", "could", "may", "might", "must", "not", "no", "nor", "so", "than", "too", "very", "just", "also", "into", "over", "under", "again", "about", "above", "after", "before", "between", "during", "each", "few", "more", "most", "other", "some", "such", "only", "own", "same", "s", "t", "don", "now"]
)


def _is_suspicious_content(text: str) -> bool:
    """Return True when a passage looks like an attempt to give orders.

    Flagged content is still indexed and quoted as data. The check exists
    so a reviewer can see it, not so the system can obey it.
    """
    return any(pattern.search(text) for pattern in _INSTRUCTION_PATTERNS)
