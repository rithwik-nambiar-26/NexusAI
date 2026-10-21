"""Text normalisation and chunking for the RAG subsystem.

Chunks are produced by splitting a document's sections on paragraph
boundaries and packing them into windows of a target character size with
a small overlap. Every chunk keeps a pointer back to the section it came
from, so the original source text can always be recovered.

Chunk identifiers are content-addressed: the same document text always
produces the same chunk ids, which makes re-ingestion idempotent and makes
duplicate detection possible.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from nexusai.rag.schemas import Chunk, Document, DocumentSection

#: Default target size of a chunk, in characters.
DEFAULT_CHUNK_SIZE = 800

#: Default overlap between consecutive chunks, in characters.
DEFAULT_CHUNK_OVERLAP = 100

#: Minimum size of a chunk worth keeping.
MIN_CHUNK_SIZE = 20

_MULTIPLE_BLANK_RE = re.compile(r"\n{3,}")
_TRAILING_SPACE_RE = re.compile(r"[ \t]+")
_SOFT_HYPHEN_RE = re.compile(r"­")


def normalize_text(text: str) -> str:
    """Normalise text for stable hashing and clean chunking.

    Normalisation is deliberately conservative: it does not change words,
    punctuation or case, because the normalised text is what citations are
    checked against.
    """
    if not text:
        return ""

    # Unicode normalisation, so equivalent encodings hash the same.
    normalized = unicodedata.normalize("NFC", text)

    # Remove soft hyphens and normalise line endings.
    normalized = _SOFT_HYPHEN_RE.sub("", normalized)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    # Collapse trailing spaces and runs of blank lines.
    normalized = _TRAILING_SPACE_RE.sub(" ", normalized)
    normalized = _MULTIPLE_BLANK_RE.sub("\n\n", normalized)

    return normalized.strip()


def content_hash(text: str) -> str:
    """Return a stable content hash for *text*.

    The hash is computed over the normalised text, so whitespace-only
    differences do not produce a different hash.
    """
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def document_id_for(name: str, text: str) -> str:
    """Return a stable identifier for a document.

    The identifier combines the document name with a hash of its content,
    so the same file ingested twice yields the same id, and a file whose
    content changed yields a different id. Two files with identical
    content but different names are also distinct documents.
    """
    digest = hashlib.sha256(f"{name}\n{normalize_text(text)}".encode()).hexdigest()
    return f"doc_{digest[:16]}"


def chunk_id_for(document_id: str, index: int, text: str) -> str:
    """Return a stable identifier for a chunk."""
    digest = hashlib.sha256(f"{document_id}:{index}:{normalize_text(text)}".encode()).hexdigest()
    return f"chunk_{digest[:16]}"


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs on blank lines."""
    parts = re.split(r"\n\s*\n", text)
    return [part.strip() for part in parts if part.strip()]


def chunk_section(
    section: DocumentSection,
    document_id: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    start_index: int = 0,
) -> list[Chunk]:
    """Split one section into chunks.

    Paragraphs are packed into windows of at most ``chunk_size`` characters.
    A single paragraph longer than ``chunk_size`` is split on sentence
    boundaries, and failing that on word boundaries, so no chunk is ever
    silently dropped.
    """
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    paragraphs = _split_paragraphs(normalize_text(section.text))
    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_len = 0
    index = start_index

    def flush() -> None:
        nonlocal buffer, buffer_len, index
        if not buffer:
            return
        body = "\n\n".join(buffer)
        # A very short fragment is normally dropped as noise, but the only
        # content of a short document must not be discarded entirely.
        if len(body.strip()) >= MIN_CHUNK_SIZE or not chunks:
            chunks.append(
                _build_chunk(
                    body=body,
                    document_id=document_id,
                    index=index,
                    section=section,
                )
            )
            index += 1
        buffer = []
        buffer_len = 0

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            flush()
            for piece in _split_long_paragraph(paragraph, chunk_size):
                buffer = [piece]
                buffer_len = len(piece)
                flush()
            continue

        if buffer_len + len(paragraph) + 2 > chunk_size:
            # Carry the tail of the previous chunk forward as overlap.
            carry = _overlap_tail(buffer, chunk_overlap)
            flush()
            if carry:
                buffer = [carry]
                buffer_len = len(carry)
            else:
                buffer = []
                buffer_len = 0

        buffer.append(paragraph)
        buffer_len += len(paragraph) + 2

    flush()
    return chunks


def _overlap_tail(paragraphs: list[str], chunk_overlap: int) -> str:
    """Return the trailing text of the previous chunk to carry forward."""
    if chunk_overlap <= 0:
        return ""
    tail: list[str] = []
    total = 0
    for paragraph in reversed(paragraphs):
        if total + len(paragraph) > chunk_overlap:
            break
        tail.insert(0, paragraph)
        total += len(paragraph) + 2
    return "\n\n".join(tail)


def _split_long_paragraph(paragraph: str, chunk_size: int) -> list[str]:
    """Split a paragraph longer than *chunk_size* into sentence-sized pieces."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces: list[str] = []
    buffer: list[str] = []
    buffer_len = 0

    for sentence in sentences:
        if len(sentence) > chunk_size:
            if buffer:
                pieces.append(" ".join(buffer))
                buffer = []
                buffer_len = 0
            pieces.extend(_split_on_words(sentence, chunk_size))
            continue
        if buffer_len + len(sentence) + 1 > chunk_size:
            pieces.append(" ".join(buffer))
            buffer = []
            buffer_len = 0
        buffer.append(sentence)
        buffer_len += len(sentence) + 1

    if buffer:
        pieces.append(" ".join(buffer))

    return pieces


def _split_on_words(text: str, chunk_size: int) -> list[str]:
    """Split text into word-aligned pieces of at most *chunk_size* characters."""
    words = text.split()
    pieces: list[str] = []
    buffer: list[str] = []
    buffer_len = 0

    for word in words:
        if buffer_len + len(word) + 1 > chunk_size:
            pieces.append(" ".join(buffer))
            buffer = []
            buffer_len = 0
        buffer.append(word)
        buffer_len += len(word) + 1

    if buffer:
        pieces.append(" ".join(buffer))

    return pieces


def _build_chunk(
    body: str,
    document_id: str,
    index: int,
    section: DocumentSection,
) -> Chunk:
    """Build a chunk with its source metadata preserved."""
    normalized_body = body.strip()
    return Chunk(
        chunk_id=chunk_id_for(document_id, index, normalized_body),
        document_id=document_id,
        text=normalized_body,
        chunk_index=index,
        page_number=section.page_number,
        heading=section.heading,
        start_offset=section.start_offset,
        end_offset=section.end_offset,
        token_estimate=_estimate_tokens(normalized_body),
        metadata={"section_index": section.section_index},
    )


def _estimate_tokens(text: str) -> int:
    """Approximate the token count of *text*.

    A rough estimate is enough for budgeting purposes; it is not used for
    billing or for any measured claim.
    """
    if not text:
        return 0
    # Roughly four characters per token for English prose.
    return max(1, (len(text) + 3) // 4)


def chunk_document(
    document: Document,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Chunk a whole document, preserving section metadata.

    Args:
        document: The document to chunk.
        chunk_size: Target maximum characters per chunk.
        chunk_overlap: Characters of overlap between consecutive chunks.

    Returns:
        The document's chunks, in document order.
    """
    chunks: list[Chunk] = []
    for section in document.sections:
        section_chunks = chunk_section(
            section,
            document.document_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            start_index=len(chunks),
        )
        chunks.extend(section_chunks)
    return chunks
