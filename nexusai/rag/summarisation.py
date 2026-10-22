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
    re.compile(r"\b(?:agreed|agreements? reached|concluded|decided|resolved|approved)\b", re.IGNORECASE),
    re.compile(r"\b(?:we|the group|the team|the committee) (?:agreed|decided|resolved|approved|concluded)\b", re.IGNORECASE),
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

#: A row of a Markdown table: cells separated by pipes.
_TABLE_ROW_RE = re.compile(r"^\s*\|(?P<cells>.+)\|\s*$")

#: A Markdown table separator row, which carries no content.
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

#: A list item.
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<text>.+)$")

#: An owner stated as a name near an action item.
_OWNER_RE = re.compile(
    r"\b(?:owner|assigned to|responsible for)\s*[:\-]?\s*(?P<owner>[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,2})"
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

#: A table header that names the columns of an action-item table.
_ACTION_TABLE_HEADERS = ("action item", "action", "task", "owner", "due")


@dataclass
class SummaryItem:
    """One item within a summary section.

    Attributes:
        text: The text of the item, taken from the source.
        source_reference: Where in the source it came from.
        owner: The owner, when the source states one.
        due: The due date, when the source states one.
    """

    text: str
    source_reference: str
    owner: str | None = None
    due: str | None = None
    score: float = 0.0


@dataclass
class SummarySection:
    """One section of a structured summary.

    Attributes:
        name: The section's name.
        title: A readable title for the section.
        items: The items in the section.
    """

    name: str
    title: str
    items: list[SummaryItem] = field(default_factory=list)


@dataclass
class StructuredSummary:
    """A summary assembled by extraction.

    Attributes:
        sections: The sections, in reading order.
        evidence: The spans the summary was drawn from.
        sufficient: False when the evidence did not support a summary.
        reason: Why the evidence was judged insufficient.
    """

    sections: list[SummarySection] = field(default_factory=list)
    evidence: list[EvidenceSpan] = field(default_factory=list)
    sufficient: bool = True
    reason: str | None = None

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
    sections: list[DocumentSection] | None = None,
) -> StructuredSummary:
    """Build a structured summary from the supplied evidence.

    Args:
        evidence: The spans the summary may draw on.
        question: What the summary should focus on, when one was asked.
        sections: The document's own sections, when a single document is
            being summarised. A document's sections are the natural unit
            for a structured summary: a heading such as "Action items"
            says what the text under it is, which a chunk boundary does
            not.

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

    if sections:
        return _summary_from_sections(sections, evidence, question)

    sections_out: list[SummarySection] = []
    overview_items = _overview_items(evidence)
    sections_out.append(SummarySection(name=OVERVIEW, title="Overview", items=overview_items))

    decision_items = _items_matching(evidence, _DECISION_PATTERNS)
    sections_out.append(SummarySection(name=DECISIONS, title="Decisions", items=decision_items))

    action_items = _action_items(evidence)
    sections_out.append(SummarySection(name=ACTION_ITEMS, title="Action items", items=action_items))

    if not any(section.items for section in sections_out):
        return StructuredSummary(
            evidence=list(evidence),
            sufficient=False,
            reason=(
                "The retrieved passages did not contain a statement that "
                "could be summarised."
            ),
        )

    return StructuredSummary(sections=sections_out, evidence=list(evidence), sufficient=True)


def _summary_from_sections(
    sections: list[DocumentSection],
    evidence: list[EvidenceSpan],
    question: str | None,
) -> StructuredSummary:
    """Build the summary from a document's own sections.

    A section's heading states what the text under it is. The summary
    keeps that structure: the text before the first content heading is
    the overview, sentences recording a decision are the decisions, and
    the rows of an action-item table are the action items.
    """
    overview = _overview_from_sections(sections)
    decisions = _decisions_from_sections(sections)
    actions = _actions_from_sections(sections)

    summary_sections = [
        SummarySection(name=OVERVIEW, title="Overview", items=overview),
        SummarySection(name=DECISIONS, title="Decisions", items=decisions),
        SummarySection(name=ACTION_ITEMS, title="Action items", items=actions),
    ]

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
        sections=summary_sections, evidence=list(evidence), sufficient=True
    )


def _overview_from_sections(sections: list[DocumentSection]) -> list[SummaryItem]:
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
                    SummaryItem(text=line, source_reference=reference, score=1.0)
                )
            continue

        for line in _content_lines(section.text):
            if line in seen:
                continue
            if _is_metadata_line(line):
                seen.add(line)
                items.append(
                    SummaryItem(text=line, source_reference=reference, score=1.0)
                )

    return items[:12]


def _decisions_from_sections(sections: list[DocumentSection]) -> list[SummaryItem]:
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
                SummaryItem(text=sentence, source_reference=reference, score=1.0)
            )

    return items


def _actions_from_sections(sections: list[DocumentSection]) -> list[SummaryItem]:
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

            if not columns:
                # A table with no recognisable header: the first
                # non-numeric cell is taken as the action.
                columns = {}

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


def _overview_items(
    evidence: list[EvidenceSpan],
) -> list[SummaryItem]:
    """Return the sentences that describe what the retrieved text is about.

    Used when the summary is built from retrieved passages rather than
    from a document's own sections.
    """
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
                score=span.score,
            )
        )

    return items


def _items_matching(
    evidence: list[EvidenceSpan],
    patterns: tuple[re.Pattern[str], ...],
    *,
    exclude_overview: bool = False,
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
                    score=span.score,
                )
            )

    return items


def _action_items(evidence: list[EvidenceSpan]) -> list[SummaryItem]:
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

        for index, line in enumerate(lines):
            row = _TABLE_ROW_RE.match(line)
            if not row:
                continue
            cells = [cell.strip() for cell in row.group("cells").split("|")]
            if any(_TABLE_SEPARATOR_RE.match(cell) for cell in cells):
                continue

            # A header row tells us what the columns mean. The row after
            # it is the first data row.
            if index == 0 and _is_action_header(cells):
                continue
            if _is_action_header(cells):
                continue

            text = cells[0] if cells else ""
            if not text or text in seen:
                continue
            owner = _find_owner(cells)
            due = _find_due(cells)
            seen.add(text)
            items.append(
                SummaryItem(
                    text=text,
                    source_reference=span.source_reference,
                    owner=owner,
                    due=due,
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
                    score=span.score,
                )
            )

    return items


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


def to_dict(summary: StructuredSummary) -> dict[str, Any]:
    """Render a structured summary as plain data."""
    return {
        "sections": [
            {
                "name": section.name,
                "title": section.title,
                "items": [
                    {
                        "text": item.text,
                        "source_reference": item.source_reference,
                        "owner": item.owner,
                        "due": item.due,
                    }
                    for item in section.items
                ],
            }
            for section in summary.sections
        ],
        "sufficient": summary.sufficient,
        "reason": summary.reason,
    }
