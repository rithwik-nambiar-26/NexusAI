"""Document text extraction for the RAG subsystem.

An extractor turns a file on disk into a list of :class:`DocumentSection`
objects, preserving page numbers and source offsets where the format
allows. Each format is handled by a small dedicated function; a format
whose library is not installed raises a clear error rather than failing
silently.

Nothing in this module executes content found in a document. Documents are
read as data only.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from nexusai.rag.schemas import DocumentFormat, DocumentSection

#: Extensions mapped to the format they represent.
EXTENSION_FORMATS: dict[str, DocumentFormat] = {
    ".pdf": DocumentFormat.PDF,
    ".docx": DocumentFormat.DOCX,
    ".txt": DocumentFormat.TXT,
    ".text": DocumentFormat.TXT,
    ".md": DocumentFormat.MARKDOWN,
    ".markdown": DocumentFormat.MARKDOWN,
}


class ExtractionError(Exception):
    """Raised when a document cannot be extracted."""


class UnsupportedFormatError(ExtractionError):
    """Raised when the file format is not supported."""


class CorruptedDocumentError(ExtractionError):
    """Raised when the file exists but cannot be parsed."""


def detect_format(path: Path | str) -> DocumentFormat:
    """Detect the document format from the file extension."""
    suffix = Path(path).suffix.lower()
    return EXTENSION_FORMATS.get(suffix, DocumentFormat.UNKNOWN)


# ---------------------------------------------------------------------------
# Plain text and Markdown
# ---------------------------------------------------------------------------

#: Markdown heading pattern, used to attach a heading to each section.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _split_markdown_headings(text: str) -> list[tuple[str | None, str]]:
    """Split Markdown into (heading, body) pairs.

    A heading applies to the body that follows it, until the next heading
    of any level. Text before the first heading has no heading.
    """
    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
                current_lines = []
            current_heading = match.group(2).strip()
            continue
        current_lines.append(line)

    if current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    return [(heading, body) for heading, body in sections if body]


def _extract_plain_text(text: str, format_hint: DocumentFormat) -> list[DocumentSection]:
    """Extract sections from plain text or Markdown."""
    if not text.strip():
        return []

    if format_hint == DocumentFormat.MARKDOWN:
        parts = _split_markdown_headings(text)
    else:
        parts = [(None, text)]

    sections: list[DocumentSection] = []
    offset = 0
    for index, (heading, body) in enumerate(parts):
        if not body.strip():
            continue
        start = text.find(body, offset)
        if start < 0:
            start = offset
        end = start + len(body)
        offset = end
        sections.append(
            DocumentSection(
                text=body,
                page_number=None,
                section_index=index,
                heading=heading,
                start_offset=start,
                end_offset=end,
            )
        )
    return sections


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _extract_pdf(path: Path) -> tuple[list[DocumentSection], int | None]:
    """Extract sections from a PDF using PyMuPDF.

    Returns the sections and the page count.
    """
    try:
        import pymupdf  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ExtractionError(
            "PDF extraction requires PyMuPDF. Install it with: pip install pymupdf"
        ) from exc

    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise CorruptedDocumentError(f"Could not open PDF {path.name}: {exc}") from exc

    try:
        if document.needs_pass:
            raise CorruptedDocumentError(f"PDF {path.name} is password protected")

        sections: list[DocumentSection] = []
        offset = 0
        section_index = 0
        page_count = document.page_count

        for page_number in range(page_count):
            page = document.load_page(page_number)
            text = page.get_text("text") or ""
            if not text.strip():
                continue
            heading = _first_heading_in(text)
            sections.append(
                DocumentSection(
                    text=text,
                    page_number=page_number + 1,
                    section_index=section_index,
                    heading=heading,
                    start_offset=offset,
                    end_offset=offset + len(text),
                )
            )
            offset += len(text)
            section_index += 1

        return sections, page_count
    finally:
        document.close()


def _first_heading_in(text: str) -> str | None:
    """Return a heading candidate from the top of a page of text.

    A markdown heading is used when present. Otherwise the first
    non-empty line is treated as a heading when it is short and does not
    end in a sentence terminator, which is the shape most document
    titles take.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    first = lines[0]
    markdown_match = _HEADING_RE.match(first)
    if markdown_match:
        return markdown_match.group(2).strip()

    if len(first) <= 80 and not first.endswith((".", "!", "?")):
        return first
    return None


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def _extract_docx(path: Path) -> tuple[list[DocumentSection], int | None]:
    """Extract sections from a DOCX using python-docx.

    Paragraphs are grouped by the nearest preceding heading paragraph, so a
    citation can name the section it came from.
    """
    try:
        import docx  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ExtractionError(
            "DOCX extraction requires python-docx. Install it with: pip install python-docx"
        ) from exc

    try:
        document = docx.Document(str(path))
        paragraphs = document.paragraphs
    except Exception as exc:
        raise CorruptedDocumentError(f"Could not open DOCX {path.name}: {exc}") from exc

    sections: list[DocumentSection] = []
    current_heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        body = "\n".join(buffer).strip()
        if body:
            sections.append(
                DocumentSection(
                    text=body,
                    page_number=None,
                    section_index=len(sections),
                    heading=current_heading,
                    start_offset=0,
                    end_offset=0,
                )
            )
        buffer.clear()

    for paragraph in paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name or "").lower() if paragraph.style else ""
        if style.startswith("heading"):
            flush()
            current_heading = text
            continue
        buffer.append(text)
    flush()

    return sections, None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: Extraction functions keyed by format. Each returns (sections, page_count).
_EXTRACTORS: dict[DocumentFormat, Callable[[Path], tuple[list[DocumentSection], int | None]]] = {
    DocumentFormat.PDF: _extract_pdf,
    DocumentFormat.DOCX: _extract_docx,
    DocumentFormat.TXT: lambda path: (_extract_plain_text(_read_text(path), DocumentFormat.TXT), None),
    DocumentFormat.MARKDOWN: lambda path: (
        _extract_plain_text(_read_text(path), DocumentFormat.MARKDOWN),
        None,
    ),
}


def _read_text(path: Path) -> str:
    """Read a text file, tolerating common encodings."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise CorruptedDocumentError(f"Could not decode {path.name} as text")


def extract_document(path: Path | str) -> tuple[list[DocumentSection], int | None, DocumentFormat]:
    """Extract sections and page count from a document.

    Args:
        path: Path to the document.

    Returns:
        A tuple of (sections, page_count, detected_format).

    Raises:
        UnsupportedFormatError: The format is not supported.
        CorruptedDocumentError: The file exists but cannot be parsed.
        ExtractionError: The file cannot be read.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise ExtractionError(f"Document not found: {file_path}")
    if not file_path.is_file():
        raise ExtractionError(f"Not a file: {file_path}")

    doc_format = detect_format(file_path)
    if doc_format == DocumentFormat.UNKNOWN:
        raise UnsupportedFormatError(
            f"Unsupported document format: {file_path.suffix or '(no extension)'}"
        )

    extractor = _EXTRACTORS[doc_format]
    sections, page_count = extractor(file_path)
    return sections, page_count, doc_format
