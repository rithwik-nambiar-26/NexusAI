"""RAG subsystem: local document intelligence and retrieval.

Provides document ingestion and validation, text extraction for PDF,
DOCX, TXT and Markdown, normalisation and chunking, local embedding
generation, vector indexing and retrieval, and grounded question
answering and summarisation with traceable source references.

The planner's ``document.read``, ``document.extract`` and ``llm.summarise``
capabilities are satisfied by this module. Nothing here executes content
found in a document, and no paid or cloud service is required.
"""

from nexusai.rag.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    chunk_document,
    chunk_section,
    content_hash,
    document_id_for,
    normalize_text,
)
from nexusai.rag.embeddings import (
    DEFAULT_MODEL_NAME,
    Embedder,
    EmbeddingError,
    HashingEmbedder,
    SentenceTransformerEmbedder,
    get_embedder,
    tokenize,
)
from nexusai.rag.extractors import (
    CorruptedDocumentError,
    ExtractionError,
    UnsupportedFormatError,
    detect_format,
    extract_document,
)
from nexusai.rag.schemas import (
    Answer,
    AnswerStatus,
    Chunk,
    Document,
    DocumentFormat,
    DocumentSection,
    EvidenceSpan,
    ExtractionStatus,
    IngestionResult,
    RetrievedChunk,
    Summary,
)
from nexusai.rag.service import (
    DocumentIntelligenceService,
    get_document_service,
    reset_document_service,
)
from nexusai.rag.store import VectorStore

__all__ = [
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_MODEL_NAME",
    "Answer",
    "AnswerStatus",
    "Chunk",
    "CorruptedDocumentError",
    "Document",
    "DocumentFormat",
    "DocumentIntelligenceService",
    "DocumentSection",
    "Embedder",
    "EmbeddingError",
    "EvidenceSpan",
    "ExtractionError",
    "ExtractionStatus",
    "HashingEmbedder",
    "IngestionResult",
    "RetrievedChunk",
    "SentenceTransformerEmbedder",
    "Summary",
    "UnsupportedFormatError",
    "VectorStore",
    "chunk_document",
    "chunk_section",
    "content_hash",
    "detect_format",
    "document_id_for",
    "extract_document",
    "get_document_service",
    "get_embedder",
    "normalize_text",
    "reset_document_service",
    "tokenize",
]
