"""Tests for the structured extractive summariser.

The summariser selects sentences from the source and organises them. It
must never add anything the source does not say, so these tests check
that owners, dates and decisions are copied and not invented.
"""

from __future__ import annotations

import pytest

from nexusai.rag.schemas import DocumentSection, EvidenceSpan
from nexusai.rag.summarisation import build_structured_summary

MEETING_SECTIONS = [
    DocumentSection(
        heading="Study Group — Meeting Notes",
        text=(
            "**Date:** 2026-10-12\n"
            "**Location:** Library, Room 3\n"
            "**Provenance:** Synthetic sample document."
        ),
        section_index=0,
    ),
    DocumentSection(
        heading="Attendees",
        text="- Priya Raman\n- Sofia Almeida\n- Kenji Nakamura",
        section_index=1,
    ),
    DocumentSection(
        heading="Agenda",
        text="1. Review of the experimental plan\n2. Division of work",
        section_index=2,
    ),
    DocumentSection(
        heading="Discussion",
        text=(
            "**Item 1 — Experimental plan.** The group agreed that the "
            "scenario suite should be reviewed by someone outside the team.\n"
            "**Item 2 — Other.** Tom reported that the design is ready."
        ),
        section_index=3,
    ),
    DocumentSection(
        heading="Action items",
        text=(
            "| # | Action item | Owner | Due |\n"
            "|---|---|---|---|\n"
            "| 1 | Complete the classifier | Priya Raman | 2026-10-16 |\n"
            "| 2 | Write the scripts | Sofia Almeida | 2026-10-17 |"
        ),
        section_index=4,
    ),
    DocumentSection(
        heading="Next meeting",
        text="2026-10-19, Library, Room 3.",
        section_index=5,
    ),
]


#: The document the fixture sections belong to.
DOC_ID = "doc_1"
DOC_NAME = "meeting_notes.md"


def _groups(sections=None):
    """Return the fixture document as a group."""
    return [(DOC_ID, DOC_NAME, sections if sections is not None else MEETING_SECTIONS)]


def _span(text: str, reference: str = "doc | §Section") -> EvidenceSpan:
    return EvidenceSpan(
        text=text,
        chunk_id="chunk_1",
        document_id="doc_1",
        document_name="doc.md",
        source_reference=reference,
        score=1.0,
    )


def test_the_sections_are_separated():
    """The summary separates the overview, the decisions and the actions."""
    summary = build_structured_summary(
        [_span("some text")], groups=_groups(MEETING_SECTIONS)
    )

    names = [section.name for section in summary.sections]
    assert names == ["overview", "decisions", "action_items", "values"]
    assert summary.sufficient is True


def test_the_overview_reports_what_the_document_is():
    """The overview carries the date, the location and the attendees."""
    summary = build_structured_summary(
        [_span("some text")], groups=_groups(MEETING_SECTIONS)
    )

    overview = summary.sections[0]
    text = " ".join(item.text for item in overview.items)

    assert "2026-10-12" in text
    assert "Library, Room 3" in text
    assert "Priya Raman" in text
    assert "Review of the experimental plan" in text
    # The list markers are not part of the content.
    assert "- Priya Raman" not in text


def test_the_decisions_are_the_statements_that_record_one():
    """Only the sentence that records a decision is reported as one."""
    summary = build_structured_summary(
        [_span("some text")], groups=_groups(MEETING_SECTIONS)
    )

    decisions = summary.sections[1]
    text = " ".join(item.text for item in decisions.items)

    assert "agreed" in text
    assert "scenario suite" in text
    # The sentence that merely reports progress is not a decision.
    assert "the design is ready" not in text


def test_the_action_items_carry_the_owner_and_the_due_date():
    """The owner and the due date are read from the table, not inferred."""
    summary = build_structured_summary(
        [_span("some text")], groups=_groups(MEETING_SECTIONS)
    )

    actions = summary.sections[2].items
    assert len(actions) == 2

    first = actions[0]
    assert first.text == "Complete the classifier"
    assert first.owner == "Priya Raman"
    assert first.due == "2026-10-16"

    second = actions[1]
    assert second.text == "Write the scripts"
    assert second.owner == "Sofia Almeida"
    assert second.due == "2026-10-17"


def test_a_row_number_is_not_reported_as_the_action():
    """A table whose first column is only a row number is read correctly."""
    summary = build_structured_summary(
        [_span("some text")], groups=_groups(MEETING_SECTIONS)
    )

    for item in summary.sections[2].items:
        assert not item.text.isdigit()


def test_nothing_is_invented():
    """Every owner and date in the summary is one the source states."""
    summary = build_structured_summary(
        [_span("some text")], groups=_groups(MEETING_SECTIONS)
    )

    owners = {item.owner for item in summary.sections[2].items}
    dues = {item.due for item in summary.sections[2].items}

    assert owners == {"Priya Raman", "Sofia Almeida"}
    assert dues == {"2026-10-16", "2026-10-17"}


def test_every_item_cites_its_source():
    """Each item points at where it came from."""
    summary = build_structured_summary(
        [_span("some text")], groups=_groups(MEETING_SECTIONS)
    )

    for section in summary.sections:
        for item in section.items:
            assert item.source_reference


def test_no_evidence_is_an_explicit_refusal():
    """With no evidence the summary says so rather than being empty."""
    summary = build_structured_summary([])

    assert summary.sufficient is False
    assert summary.reason


def test_a_summary_without_sections_falls_back_to_the_passages():
    """When there is no document structure, the passages are used."""
    span = _span(
        "The group agreed that the design is ready. "
        "Complete the classifier, owner Priya Raman, due 2026-10-16."
    )

    summary = build_structured_summary([span])

    assert summary.sufficient is True
    decisions = summary.sections[1]
    assert any("agreed" in item.text for item in decisions.items)


def test_a_sentence_is_not_broken_by_a_soft_wrapped_line():
    """A line break in the source is not a sentence break."""
    sections = [
        DocumentSection(
            heading="Discussion",
            text=(
                "The group agreed that the scenario suite\n"
                "should be reviewed before the numbers\n"
                "are collected."
            ),
            section_index=0,
        )
    ]

    summary = build_structured_summary([_span("some text")], groups=_groups(sections))

    decisions = summary.sections[1].items
    assert len(decisions) == 1
    assert "should be reviewed before the numbers are collected" in decisions[0].text
    assert "\n" not in decisions[0].text


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_blank_evidence_is_refused(text):
    """A blank passage is not evidence."""
    summary = build_structured_summary([_span(text)])

    assert summary.sufficient is False
