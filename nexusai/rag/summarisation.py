"""Structured extractive summarisation.

When no local LLM is available, NexusAI summarises by *extraction*, not
by generation: it selects sentences from the source text and organises
them into sections. Nothing is written that is not in the source, so
every statement in the summary can be checked against the document.

The sections are chosen to match what a reader of a meeting or a report
actually wants:

* **Overview** — what the document is and what it covers.
* **Decisions** — the statements in the text that record a decision.
* **Action items** — what someone is to do, with the owner and the due
  date when the text states them.

The classification of a sentence is made by explicit patterns, and the
patterns are narrow. A sentence that is not recognised as a decision is
not reported as one. An action item with no stated owner has no owner
field; the summariser never infers one.

**One document is summarised at a time.** A summary is built per
document and the documents are kept apart. Two documents are never
blended into a single narrative, because a reader would have no way to
tell which document a statement came from. When more than one document
is in scope, each is summarised under its own heading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from nexusai.rag.schemas import DocumentSection, EvidenceSpan

#: The sections a summary is organised into.
OVERVIEW = "overview"
DECISIONS = "decisions"
ACTION_ITEMS = "action_items"

#: Headings whose content is reported as action items rather than as
#: overview material.
_ACTION_ITEM_HEADINGS = frozenset({"action item", "action items", "tasks", "to do", "todo"})

#: Headings whose content describes what the document is.
_OVERVIEW_HEADINGS = frozenset(
    {
        "attendees",
        "participants",
        "agenda",
        "overview",
        "summary",
        "next meeting",
        "next steps",
        "purpose",
        "scope",
    }
)

#: Sentence patterns that mark a statement as recording a decision. These
#: are deliberately narrow: a sentence is only reported as a decision when
#: it says so.
_DECISION_PATTERNS = (
    re.compile(
        r"\b(?:agreed|agreements? reached|concluded|decided|resolved|approved)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:we|the group|the team|the committee) "
        r"(?:agreed|decided|resolved|approved|concluded)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bit was (?:agreed|decided|resolved|approved|confirmed)\b", re.IGNORECASE),
    re.compile(r"\bthere (?:was|were) no other business\b", re.IGNORECASE),
)

#: Patterns that mark a statement as an action item. An action item says
#: what is to be done, usually with a named owner.
_ACTION_PATTERNS = (
    re.compile(r"\b(?:will|shall|must|to|should)\s+\w+", re.IGNORECASE),
    re.compile(r"\baction item\b", re.IGNORECASE),
    re.compile(r"\b(?:owner|assigned to|responsible for|due by|due date|deadline)\b", re.IGNORECASE),
)

#: A table header that names the columns of an action-item table.
_ACTION_TABLE_HEADERS = ("action item", "action", "task", "owner", "due")

#: A row of a Markdown table: cells separated by pipes.
_TABLE_ROW_RE = re.compile(r"^\s*\|(?P<cells>.+)\|\s*$")

#: A Markdown table separator row, which carries no content.
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

#: An owner stated as a name near an action item.
_OWNER_RE = re.compile(
    r"\b(?:owner|assigned to|responsible for)\s*[:\-]?\s*"
    r"(?P<owner>[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,2})"
)

#: A due date stated near an action item.
_DUE_RE = re.compile(
    r"\b(?:due|by|before|deadline)\s*[:\-]?\s*"
    r"(?P<due>\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:\s+\d{4})?)",
    re.IGNORECASE,
)

#: Sentence splitting.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class SummaryItem:
    """One item within a summary section.

    Attributes:
        text: The text of the item, taken from the source.
        source_reference: Where in the source it came from.
        owner: The owner, when the source states one.
        due: The due date, when the source states one.
        document_id: The document the item came from.
    """

    text: str
    source_reference: str
    owner: str | None = None
    due: str | None = None
    document_id: str = ""
    score: float = 0.0


@dataclass
class SummarySection:
    """One section of a structured summary.

    Attributes:
        name: The section's name.
        title: A readable title for the section.
        items: The items in the section.
        document_id: The document the section describes, when it describes
            one.
    """

    name: str
    title: str
    items: list[SummaryItem] = field(default_factory=list)
    document_id: str = ""


@dataclass
class StructuredSummary:
    """A summary assembled by extraction.

    Attributes:
        sections: The sections, in reading order.
        evidence: The spans the summary was drawn from.
        sufficient: False when the evidence did not support a summary.
        reason: Why the evidence was judged insufficient.
        documents: The documents the summary covers.
    """

    sections: list[SummarySection] = field(default_factory=list)
    evidence: list[EvidenceSpan] = field(default_factory=list)
    sufficient: bool = True
    reason: str | None = None
    documents: list[str] = field(default_factory=list)

    @property
    def citations(self) -> list[str]:
        """The source references the summary rests on, in order."""
        seen: list[str] = []
        for section in self.sections:
            for item in section.items:
                if item.source_reference and item.source_reference not in seen:
                    seen.append(item.source_reference)
        return seen

    def to_text(self) -> str:
        """Render the summary as plain text."""
        lines: list[str] = []
        for section in self.sections:
            if not section.items:
                continue
            lines.append(f"{section.title}:")
            for item in section.items:
                suffix = ""
                if item.owner:
                    suffix += f" (owner: {item.owner})"
                if item.due:
                    suffix += f" (due: {item.due})"
                lines.append(f"- {item.text}{suffix} [{item.source_reference}]")
            lines.append("")
        return "\n".join(lines).strip()


def build_structured_summary(
    evidence: list[EvidenceSpan],
    *,
    question: str | None = None,
    groups: list[tuple[str, str, list[DocumentSection]]] | None = None,
) -> StructuredSummary:
    """Build a structured summary from the supplied evidence.

    Args:
        evidence: The spans the summary may draw on.
        question: What the summary should focus on, when one was asked.
        groups: The documents in scope, each as ``(document_id,
            document_name, sections)``. When it is given, each document is
            summarised under its own heading and the documents are never
            blended.

    Returns:
        The assembled summary. When the evidence is empty, the summary is
        marked insufficient rather than empty.
    """
    if not evidence:
        return StructuredSummary(
            sufficient=False,
            reason=(
                "No passage was retrieved that was similar enough to the "
                "request to be treated as evidence."
            ),
        )

    if groups:
        return _summary_from_groups(groups, evidence)

    # No document structure is available, so the evidence is grouped by the
    # document it came from and each document is summarised on its own.
    return _summary_from_evidence_by_document(evidence)


def _summary_from_groups(
    groups: list[tuple[str, str, list[DocumentSection]]],
    evidence: list[EvidenceSpan],
) -> StructuredSummary:
    """Build the summary from each document's own sections.

    A section's heading states what the text under it is. The summary
    keeps that structure: the text before the first content heading is
    the overview, sentences recording a decision are the decisions, and
    the rows of an action-item table are the action items.
    """
    summary_sections: list[SummarySection] = []
    documents: list[str] = []

    for document_id, document_name, sections in groups:
        if not sections:
            continue
        documents.append(document_id)
        label = f" — {document_name}" if document_name else ""

        overview = _overview_from_sections(sections, document_id)
        decisions = _decisions_from_sections(sections, document_id)
        actions = _actions_from_sections(sections, document_id)

        summary_sections.append(
            SummarySection(
                name=OVERVIEW,
                title=f"Overview{label}",
                items=overview,
                document_id=document_id,
            )
        )
        summary_sections.append(
            SummarySection(
                name=DECISIONS,
                title=f"Decisions{label}",
                items=decisions,
                document_id=document_id,
            )
        )
        summary_sections.append(
            SummarySection(
                name=ACTION_ITEMS,
                title=f"Action items{label}",
                items=actions,
                document_id=document_id,
            )
        )

    if not any(section.items for section in summary_sections):
        return StructuredSummary(
            evidence=list(evidence),
            sufficient=False,
            reason=(
                "The document did not contain a statement that could be "
                "summarised."
            ),
        )

    return StructuredSummary(
        sections=summary_sections,
        evidence=list(evidence),
        sufficient=True,
        documents=documents,
    )


def _summary_from_evidence_by_document(
    evidence: list[EvidenceSpan],
) -> StructuredSummary:
    """Build the summary from the passages, keeping documents apart.

    When there is no document structure to work from, the passages are
    grouped by the document they came from and each document is
    summarised on its own. The documents are never blended, because a
    reader could not then tell which document a statement came from.
    """
    by_document: dict[str, list[EvidenceSpan]] = {}
    names: dict[str, str] = {}
    for span in evidence:
        by_document.setdefault(span.document_id, []).append(span)
        if span.document_name:
            names.setdefault(span.document_id, span.document_name)

    summary_sections: list[SummarySection] = []
    documents: list[str] = []

    for document_id, spans in by_document.items():
        documents.append(document_id)
        name = names.get(document_id, "")
        label = f" — {name}" if name else ""

        summary_sections.append(
            SummarySection(
                name=OVERVIEW,
                title=f"Overview{label}",
                items=_overview_items(spans, document_id),
                document_id=document_id,
            )
        )
        summary_sections.append(
            SummarySection(
                name=DECISIONS,
                title=f"Decisions{label}",
                items=_items_matching(spans, _DECISION_PATTERNS, document_id),
                document_id=document_id,
            )
        )
        summary_sections.append(
            SummarySection(
                name=ACTION_ITEMS,
                title=f"Action items{label}",
                items=_action_items(spans, document_id),
                document_id=document_id,
            )
        )

    if not any(section.items for section in summary_sections):
        return StructuredSummary(
            evidence=list(evidence),
            sufficient=False,
            reason=(
                "The retrieved passages did not contain a statement that "
                "could be summarised."
            ),
        )

    return StructuredSummary(
        sections=summary_sections,
        evidence=list(evidence),
        sufficient=True,
        documents=documents,
    )


def _overview_from_sections(
    sections: list[DocumentSection],
    document_id: str = "",
) -> list[SummaryItem]:
    """Return the material that says what the document is.

    The document's title and its metadata — the date, the location, the
    attendees, the agenda — are what a reader needs first. Each is taken
    from the source verbatim.
    """
    items: list[SummaryItem] = []
    seen: set[str] = set()

    for section in sections:
        heading = (section.heading or "").strip()
        if heading.lower() in _ACTION_ITEM_HEADINGS:
            # Handled as action items, not as overview.
            continue

        reference = _reference_for(section)

        if _is_overview_heading(heading):
            # A list under a heading such as "Attendees" or "Agenda" is
            # reported line by line, so the items stay separate.
            for line in _content_lines(section.text):
                if line in seen:
                    continue
                seen.add(line)
                items.append(
                    SummaryItem(
                        text=line,
                        source_reference=reference,
                        document_id=document_id,
                        score=1.0,
                    )
                )
            continue

        for line in _content_lines(section.text):
            if line in seen:
                continue
            if _is_metadata_line(line):
                seen.add(line)
                items.append(
                    SummaryItem(
                        text=line,
                        source_reference=reference,
                        document_id=document_id,
                        score=1.0,
                    )
                )

    return items[:12]


def _decisions_from_sections(
    sections: list[DocumentSection],
    document_id: str = "",
) -> list[SummaryItem]:
    """Return the sentences of the document that record a decision."""
    items: list[SummaryItem] = []
    seen: set[str] = set()

    for section in sections:
        heading = (section.heading or "").strip()
        if heading.lower() in _ACTION_ITEM_HEADINGS:
            continue

        reference = _reference_for(section)
        for sentence in _split_sentences(section.text):
            sentence = _clean(sentence)
            if not sentence or sentence in seen:
                continue
            if not any(pattern.search(sentence) for pattern in _DECISION_PATTERNS):
                continue
            seen.add(sentence)
            items.append(
                SummaryItem(
                    text=sentence,
                    source_reference=reference,
                    document_id=document_id,
                    score=1.0,
                )
            )

    return items


def _actions_from_sections(
    sections: list[DocumentSection],
    document_id: str = "",
) -> list[SummaryItem]:
    """Return the action items stated in the document.

    A table whose header names an action-item column is read row by row.
    The header is used to work out which column holds the action, which
    the owner and which the due date, so a table whose first column is
    only a row number is read correctly. The values are copied from the
    row; none of them is inferred.
    """
    items: list[SummaryItem] = []
    seen: set[str] = set()

    for section in sections:
        reference = _reference_for(section)
        columns: dict[str, int] = {}

        for line in _content_lines(section.text):
            row = _TABLE_ROW_RE.match(line)
            if not row:
                continue
            cells = [cell.strip() for cell in row.group("cells").split("|")]
            if not cells or all(not cell for cell in cells):
                continue
            if all(_is_separator_cell(cell) for cell in cells):
                continue

            if _is_action_header(cells):
                # The header names the columns; it is not itself an item.
                columns = _action_columns(cells)
                continue

            text = _action_text(cells, columns)
            if not text or text in seen:
                continue
            seen.add(text)
            items.append(
                SummaryItem(
                    text=text,
                    source_reference=reference,
                    owner=_find_owner(cells, columns),
                    due=_find_due(cells, columns),
                    document_id=document_id,
                    score=1.0,
                )
            )

    return items


def _action_columns(header: list[str]) -> dict[str, int]:
    """Return which column holds the action, the owner and the due date."""
    columns: dict[str, int] = {}
    for index, cell in enumerate(header):
        lowered = cell.lower().strip()
        if "owner" in lowered or "responsible" in lowered or "assignee" in lowered:
            columns.setdefault("owner", index)
        elif "due" in lowered or "deadline" in lowered or "by when" in lowered:
            columns.setdefault("due", index)
        elif (
            "action" in lowered
            or "task" in lowered
            or "item" in lowered
            or "description" in lowered
        ):
            columns.setdefault("action", index)
    return columns


def _action_text(cells: list[str], columns: dict[str, int]) -> str:
    """Return the action described by a table row."""
    index = columns.get("action")
    if index is not None and index < len(cells):
        return cells[index].strip()

    # No recognised action column: the first cell that is not a row
    # number is the action.
    for cell in cells:
        cleaned = cell.strip()
        if cleaned and not cleaned.isdigit():
            return cleaned
    return cells[0].strip() if cells else ""


def _reference_for(section: DocumentSection) -> str:
    """Return a readable citation for a document section."""
    if section.heading:
        return f"§{section.heading}"
    return "document"


def _content_lines(text: str) -> list[str]:
    """Return the non-empty lines of *text*, cleaned."""
    lines: list[str] = []
    for raw in text.splitlines():
        line = _clean(raw)
        if line:
            lines.append(line)
    return lines


def _clean(text: str) -> str:
    """Strip Markdown emphasis and list markers from a line."""
    stripped = text.strip()
    stripped = re.sub(r"^#{1,6}\s+", "", stripped)
    stripped = re.sub(r"^\*\*(?P<label>[^*]+)\*\*", r"\g<label>", stripped)
    stripped = re.sub(r"^\*(?P<label>[^*]+)\*$", r"\g<label>", stripped)
    stripped = re.sub(r"^`(?P<label>[^`]+)`$", r"\g<label>", stripped)
    # A list marker carries no meaning once the line is reported on its
    # own.
    stripped = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", stripped)
    return stripped.strip()


def _is_overview_heading(heading: str) -> bool:
    """True when the heading names material that belongs in the overview."""
    return heading.lower() in _OVERVIEW_HEADINGS


def _is_metadata_line(line: str) -> bool:
    """True when the line states what the document is, rather than content."""
    return bool(re.match(r"^\*\*(?P<label>[^*]+):\*\*", line)) or bool(
        re.match(r"^(?P<label>[A-Z][\w ]{1,30}):\s+\S", line)
    )


def _is_separator_cell(cell: str) -> bool:
    """True when the cell is part of a table's separator row."""
    return bool(re.fullmatch(r"[\s:|-]+", cell)) and bool(re.search(r"[-:]", cell))


def _is_action_header(cells: list[str]) -> bool:
    """True when the cells look like an action-item table's header."""
    lowered = [cell.lower() for cell in cells]
    return any(
        any(header in cell for header in _ACTION_TABLE_HEADERS) for cell in lowered
    )


def _find_owner(cells: list[str], columns: dict[str, int] | None = None) -> str | None:
    """Return the owner stated in a table row, if there is one.

    When the header named an owner column, that cell is used. Otherwise a
    cell that looks like a person's name is used.
    """
    columns = columns or {}
    index = columns.get("owner")
    if index is not None and index < len(cells):
        owner = cells[index].strip()
        return owner or None

    for cell in cells:
        cleaned = cell.strip()
        if not cleaned:
            continue
        # A cell that looks like a name, and is not a date.
        if _DUE_RE.search(cleaned):
            continue
        if re.fullmatch(r"[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,2}", cleaned):
            return cleaned
    return None


def _find_due(cells: list[str], columns: dict[str, int] | None = None) -> str | None:
    """Return the due date stated in a table row, if there is one."""
    columns = columns or {}
    index = columns.get("due")
    if index is not None and index < len(cells):
        due = cells[index].strip()
        if due:
            return due

    for cell in cells:
        cleaned = cell.strip()
        if not cleaned:
            continue
        match = _DUE_RE.search(cleaned)
        if match:
            return match.group("due").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
            return cleaned
    return None


def _split_sentences(text: str) -> list[str]:
    """Split *text* into sentences, keeping only non-empty ones.

    Markdown soft-wraps a paragraph across several lines, so the lines of
    a paragraph are joined before the paragraph is split into sentences.
    A line break in the source is not a sentence break.
    """
    sentences: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        joined = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
        if not joined:
            continue
        for part in _SENTENCE_RE.split(joined):
            cleaned = part.strip()
            if cleaned:
                sentences.append(cleaned)
    return sentences


def _first_sentence(text: str) -> str:
    """Return the first sentence of *text*."""
    for part in _split_sentences(text):
        if part:
            return part
    return ""


def _overview_items(
    evidence: list[EvidenceSpan],
    document_id: str = "",
) -> list[SummaryItem]:
    """Return the sentences that describe what the retrieved text is about."""
    if not evidence:
        return []

    items: list[SummaryItem] = []
    seen: set[str] = set()

    for span in evidence[:3]:
        sentence = _first_sentence(span.text)
        if not sentence or sentence in seen:
            continue
        seen.add(sentence)
        items.append(
            SummaryItem(
                text=sentence,
                source_reference=span.source_reference,
                document_id=document_id or span.document_id,
                score=span.score,
            )
        )

    return items


def _items_matching(
    evidence: list[EvidenceSpan],
    patterns: tuple[re.Pattern[str], ...],
    document_id: str = "",
) -> list[SummaryItem]:
    """Return the sentences of the evidence that match any of *patterns*."""
    items: list[SummaryItem] = []
    seen: set[str] = set()

    for span in evidence:
        for sentence in _split_sentences(span.text):
            if sentence in seen:
                continue
            if not any(pattern.search(sentence) for pattern in patterns):
                continue
            seen.add(sentence)
            items.append(
                SummaryItem(
                    text=sentence,
                    source_reference=span.source_reference,
                    document_id=document_id or span.document_id,
                    score=span.score,
                )
            )

    return items


def _action_items(evidence: list[EvidenceSpan], document_id: str = "") -> list[SummaryItem]:
    """Return the action items stated in the evidence.

    Two forms are recognised: a row of a Markdown table whose header
    names an action-item column, and a sentence that states an action
    with an owner. The owner and the due date are copied from the text;
    neither is inferred.
    """
    items: list[SummaryItem] = []
    seen: set[str] = set()

    for span in evidence:
        lines = span.text.splitlines()

        for line in lines:
            row = _TABLE_ROW_RE.match(line)
            if not row:
                continue
            cells = [cell.strip() for cell in row.group("cells").split("|")]
            if any(_TABLE_SEPARATOR_RE.match(cell) for cell in cells):
                continue
            if _is_action_header(cells):
                continue

            text = _action_text(cells, _action_columns(cells))
            if not text or text in seen:
                continue
            seen.add(text)
            items.append(
                SummaryItem(
                    text=text,
                    source_reference=span.source_reference,
                    owner=_find_owner(cells),
                    due=_find_due(cells),
                    document_id=document_id or span.document_id,
                    score=span.score,
                )
            )

    # Sentences that state an action with an owner.
    for span in evidence:
        for sentence in _split_sentences(span.text):
            if sentence in seen:
                continue
            if not any(pattern.search(sentence) for pattern in _ACTION_PATTERNS):
                continue
            owner_match = _OWNER_RE.search(sentence)
            if not owner_match:
                continue
            due_match = _DUE_RE.search(sentence)
            seen.add(sentence)
            items.append(
                SummaryItem(
                    text=sentence,
                    source_reference=span.source_reference,
                    owner=owner_match.group("owner").strip(),
                    due=due_match.group("due").strip() if due_match else None,
                    document_id=document_id or span.document_id,
                    score=span.score,
                )
            )

    return items


def to_dict(summary: StructuredSummary) -> dict[str, Any]:
    """Render a structured summary as plain data."""
    return {
        "sections": [
            {
                "name": section.name,
                "title": section.title,
                "document_id": section.document_id,
                "items": [
                    {
                        "text": item.text,
                        "source_reference": item.source_reference,
                        "owner": item.owner,
                        "due": item.due,
                        "document_id": item.document_id,
                    }
                    for item in section.items
                ],
            }
            for section in summary.sections
        ],
        "sufficient": summary.sufficient,
        "reason": summary.reason,
        "documents": summary.documents,
    }
