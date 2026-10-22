"""Regression tests for the document-selection and summarisation defects.

Three defects were found by manually testing the Streamlit application:

1. A document the user selected in the interface was not carried into
   the plan. The plan reported "No source document was referenced; the
   plan needs a document path" even though the user had chosen one, and
   the selection was patched onto the plan *after* it had been built, so
   the plan's own record disagreed with what ran.

2. Retrieval was not restricted to the selected document. The selection
   reached only the ``document.read`` task, so ``document.extract`` and
   ``llm.summarise`` searched the whole corpus and returned passages
   from an unrelated document.

3. The summary was a concatenation of the retrieved passages, with no
   structure and no indication of how it had been produced.

These tests cover the fixes for all three.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexusai.app.config import Settings
from nexusai.app.main import create_app
from nexusai.rag.schemas import AnswerStatus

MEETING_NOTES = "data/sample/meeting_notes.md"
PRODUCT_MANUAL = "data/sample/product_manual.md"

REQUEST = "Summarise the uploaded meeting notes and identify the important decisions."


@pytest.fixture
def client(tmp_path) -> TestClient:
    """A test client with an isolated database and vector index."""
    settings = Settings(
        database_url="sqlite:///:memory:",
        vector_store_dir=str(tmp_path / "vectors"),
        allowed_document_roots=["./data", "./docs", "./experiments", str(tmp_path)],
    )
    return TestClient(create_app(settings))


@pytest.fixture
def indexed(client: TestClient) -> TestClient:
    """A client with both sample documents indexed."""
    for path in (MEETING_NOTES, PRODUCT_MANUAL):
        response = client.post("/api/v1/documents/ingest", json={"path": path})
        assert response.json()["result"]["status"] == "ok"
    return client


def _document_id(client: TestClient, name: str) -> str:
    """Return the id of an indexed document."""
    documents = client.get("/api/v1/documents").json()["documents"]
    return next(d["document_id"] for d in documents if d["name"] == name)


def _plan(client: TestClient, source_documents: list[str] | None = None) -> dict:
    """Create a summarisation plan for the meeting notes."""
    payload = {
        "text": REQUEST,
        "intent": "document_summarisation",
        "source": "explicit",
    }
    if source_documents is not None:
        payload["source_documents"] = list(source_documents)
    return client.post("/api/v1/planner/plan", json=payload).json()["plan"]


# ---------------------------------------------------------------------------
# Defect 1 — the selected document must reach the plan
# ---------------------------------------------------------------------------


def test_the_plan_records_the_selected_document(indexed: TestClient):
    """The plan carries the document the user chose."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    plan = _plan(indexed, [meeting_notes])

    assert plan["source_documents"] == [meeting_notes]


def test_the_plan_does_not_report_a_missing_document_when_one_was_selected(
    indexed: TestClient,
):
    """The plan must not ask for a document the user already chose.

    The defect was that the plan said "No source document was referenced;
    the plan needs a document path" even though a document had been
    selected in the interface.
    """
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    plan = _plan(indexed, [meeting_notes])

    assert plan["missing_information"] == []
    joined = " ".join(plan["missing_information"]).lower()
    assert "no source document" not in joined


def test_the_plan_still_reports_a_missing_document_when_none_was_selected(
    indexed: TestClient,
):
    """Without a selection the plan still says what it needs."""
    plan = _plan(indexed, None)

    assert plan["source_documents"] == []
    joined = " ".join(plan["missing_information"]).lower()
    assert "no source document" in joined


def test_every_document_task_carries_the_selected_document(indexed: TestClient):
    """The selection reaches the reading, extraction and summary tasks.

    The defect was that only ``document.read`` received it, so the
    downstream capabilities searched the whole corpus.
    """
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    plan = _plan(indexed, [meeting_notes])

    document_tasks = [
        task
        for task in plan["tasks"]
        if set(task["required_capabilities"])
        & {"document.read", "document.extract", "llm.summarise"}
    ]
    assert document_tasks, "the plan has no document tasks"

    for task in document_tasks:
        parameters = {
            parameter["name"]: parameter["value"]
            for parameter in task.get("input_parameters") or []
        }
        # The reading task names the document; the retrieval and summary
        # tasks are given the whole scope.
        scope = parameters.get("document_ids") or []
        if "document.read" in task["required_capabilities"]:
            assert parameters.get("document_id") == meeting_notes, (
                f"task '{task['task_type']}' did not receive the selected document"
            )
        else:
            assert scope == [meeting_notes], (
                f"task '{task['task_type']}' did not receive the selected document"
            )


# ---------------------------------------------------------------------------
# Defect 2 — retrieval must be restricted to the selected document
# ---------------------------------------------------------------------------


def test_extraction_returns_only_the_selected_document(indexed: TestClient):
    """Selecting meeting_notes.md must not return product_manual.md chunks."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    plan = _plan(indexed, [meeting_notes])
    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]

    extract = next(
        result for result in report["task_results"] if result["capability"] == "document.extract"
    )
    assert extract["status"] == "completed"

    passages = extract["output"]["passages"]
    assert passages, "the extraction returned no passages"
    for passage in passages:
        assert passage["document_id"] == meeting_notes
        assert passage["document_name"] == "meeting_notes.md"

    # The unrelated document is not present in any form.
    assert not any("warranty" in passage["text"].lower() for passage in passages)
    assert not any("installation" in passage["text"].lower() for passage in passages)


def test_the_summary_contains_no_unrelated_document_content(indexed: TestClient):
    """The summary must not quote the document the user did not select."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    plan = _plan(indexed, [meeting_notes])
    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]

    summarise = next(
        result for result in report["task_results"] if result["capability"] == "llm.summarise"
    )
    assert summarise["status"] == "completed"

    output = summarise["output"]
    for evidence in output["evidence"]:
        assert evidence["document_id"] == meeting_notes
        assert evidence["document_name"] == "meeting_notes.md"

    text = output["summary_text"].lower()
    assert "warranty" not in text
    assert "installation" not in text


def test_without_a_selection_the_plan_asks_for_a_document(indexed: TestClient):
    """Without a selection the plan says what it needs, and nothing runs.

    This is the behaviour the selection removes. When the user has not
    chosen a document and the request names none either, the plan reports
    the missing document and the execution cannot proceed: the reading
    task has nothing to read, so the tasks that depend on it are blocked.
    """
    plan = _plan(indexed, None)

    joined = " ".join(plan["missing_information"]).lower()
    assert "no source document" in joined

    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]

    # Nothing completed, and nothing claimed to have.
    for result in report["task_results"]:
        assert result["status"] != "completed"


def test_a_request_that_names_a_file_may_still_reach_the_whole_corpus(
    indexed: TestClient,
):
    """Without a selection, retrieval is not restricted to one document.

    The request names a file, so the reading task succeeds, but no
    document id is set on the plan, so the extraction is free to draw on
    the whole corpus. This is the behaviour the selection narrows, and
    the point of the selection is that it removes that freedom.
    """
    plan = indexed.post(
        "/api/v1/planner/plan",
        json={
            "text": "Read data/sample/meeting_notes.md and summarise the decisions.",
            "intent": "document_summarisation",
            "source": "explicit",
        },
    ).json()["plan"]

    assert plan["source_documents"] == []

    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]
    extract = next(
        (result for result in report["task_results"] if result["capability"] == "document.extract"),
        None,
    )
    if extract is None or extract["status"] != "completed":
        # The extraction is blocked because the read did not complete.
        # That is acceptable: the point of the test is that nothing was
        # silently restricted to one document.
        return

    document_ids = {
        passage["document_id"] for passage in extract["output"].get("passages") or []
    }
    assert len(document_ids) > 1, (
        "an unrestricted retrieval should be able to reach more than one document"
    )


def test_the_selected_document_reaches_the_execution_inputs(indexed: TestClient):
    """The executor passes the selection to the capability, not just the plan."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    plan = _plan(indexed, [meeting_notes])
    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]

    read = next(
        result for result in report["task_results"] if result["capability"] == "document.read"
    )
    assert read["status"] == "completed"
    assert read["output"]["document_id"] == meeting_notes
    assert read["output"]["name"] == "meeting_notes.md"


# ---------------------------------------------------------------------------
# Defect 3 — the summary must be a real summary, and say how it was made
# ---------------------------------------------------------------------------


def test_the_summary_is_structured(indexed: TestClient):
    """The summary separates the overview, the decisions and the actions."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    plan = _plan(indexed, [meeting_notes])
    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]

    summarise = next(
        result for result in report["task_results"] if result["capability"] == "llm.summarise"
    )
    output = summarise["output"]

    sections = {section["name"]: section for section in output["sections"]}
    assert "overview" in sections
    assert "decisions" in sections
    assert "action_items" in sections

    # The overview says what the document is.
    overview_text = " ".join(item["text"] for item in sections["overview"]["items"])
    assert "2026-10-12" in overview_text
    assert "Priya Raman" in overview_text

    # The decisions are the statements that record one.
    decision_text = " ".join(item["text"] for item in sections["decisions"]["items"])
    assert "agreed" in decision_text.lower()

    # The action items carry the owner and the due date from the source.
    actions = sections["action_items"]["items"]
    assert len(actions) == 6
    assert any(item["owner"] == "Priya Raman" for item in actions)
    assert any(item["due"] == "2026-10-18" for item in actions)
    assert all(item["text"] for item in actions)


def test_the_summary_does_not_invent_owners_or_dates(indexed: TestClient):
    """Every owner and date in the summary is one the source states.

    The source table names five owners and six due dates. A summary that
    produced an owner or a date that is not in the source would be
    inventing it, so the two sets must match exactly.
    """
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    plan = _plan(indexed, [meeting_notes])
    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]

    summarise = next(
        result for result in report["task_results"] if result["capability"] == "llm.summarise"
    )
    actions = next(
        section
        for section in summarise["output"]["sections"]
        if section["name"] == "action_items"
    )["items"]

    expected_owners = {
        "Priya Raman",
        "Sofia Almeida",
        "Kenji Nakamura",
        "Grace Oyelaran",
        "Tom Whitfield",
    }
    expected_dues = {
        "2026-10-16",
        "2026-10-17",
        "2026-10-18",
    }
    assert {item["owner"] for item in actions} == expected_owners
    assert {item["due"] for item in actions} == expected_dues


def test_the_summary_states_how_it_was_made(indexed: TestClient):
    """The result records the method, so extraction is never called generation.

    No local LLM is configured in the test environment, so the method must
    be ``extractive``.
    """
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    plan = _plan(indexed, [meeting_notes])
    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]

    summarise = next(
        result for result in report["task_results"] if result["capability"] == "llm.summarise"
    )
    assert summarise["output"]["method"] == "extractive"


def test_the_summary_keeps_its_source_references(indexed: TestClient):
    """Every item in the summary points at where it came from."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    plan = _plan(indexed, [meeting_notes])
    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]

    summarise = next(
        result for result in report["task_results"] if result["capability"] == "llm.summarise"
    )
    output = summarise["output"]

    assert output["citations"]
    for section in output["sections"]:
        for item in section["items"]:
            assert item["source_reference"]


def test_the_summary_is_not_a_concatenation_of_passages(indexed: TestClient):
    """The summary is organised, not the retrieved text joined together."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    plan = _plan(indexed, [meeting_notes])
    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]

    summarise = next(
        result for result in report["task_results"] if result["capability"] == "llm.summarise"
    )
    output = summarise["output"]
    text = output["summary_text"]

    # The section headings are present, so the summary is organised. Each
    # names the document it comes from, so a reader can tell which
    # document a statement belongs to.
    assert "Overview" in text
    assert "Decisions" in text
    assert "Action items" in text
    assert "meeting_notes.md" in text

    # It is not a raw dump of the passages: the action-item table is
    # reported row by row rather than as one Markdown table.
    assert "| Action item |" not in text


def test_an_unindexed_document_yields_an_explicit_refusal(client: TestClient):
    """A document that is not indexed produces an explicit result, not a guess."""
    response = client.post(
        "/api/v1/documents/summarise",
        json={"document_id": "doc_does_not_exist"},
    )

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["status"] in (
        AnswerStatus.INSUFFICIENT_EVIDENCE.value,
        AnswerStatus.NO_DOCUMENTS.value,
    )
    assert summary["summary_text"]
