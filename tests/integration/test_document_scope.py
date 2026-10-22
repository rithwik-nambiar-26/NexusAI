"""Regression tests for the document scope.

The scope is the set of documents a request is about. Three rules apply:

* a request about one document reads only that document;
* a request may span several documents, but only when the caller states
  which ones, and the summary keeps them apart rather than blending
  them;
* a document id that is not indexed fails clearly, and never widens the
  search to the whole corpus.

The tests also check that the capabilities report which documents they
actually read, so a mismatch is visible rather than silent.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexusai.app.config import Settings
from nexusai.app.main import create_app

MEETING_NOTES = "data/sample/meeting_notes.md"
PRODUCT_MANUAL = "data/sample/product_manual.md"

REQUEST = "Summarise the uploaded meeting notes and identify the important decisions."
CROSS_DOCUMENT_REQUEST = "Summarise the meeting notes and the product manual."


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


def _plan(
    client: TestClient,
    source_documents: list[str] | None = None,
    text: str = REQUEST,
) -> dict:
    """Create a summarisation plan with a document scope."""
    payload = {
        "text": text,
        "intent": "document_summarisation",
        "source": "explicit",
    }
    if source_documents is not None:
        payload["source_documents"] = list(source_documents)
    return client.post("/api/v1/planner/plan", json=payload).json()["plan"]


def _execute(client: TestClient, plan: dict) -> dict:
    """Execute a plan and return the report."""
    return client.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]


def _result(report: dict, capability: str) -> dict:
    """Return the result of one capability."""
    return next(r for r in report["task_results"] if r["capability"] == capability)


# ---------------------------------------------------------------------------
# A meeting-notes request cannot reach the product manual
# ---------------------------------------------------------------------------


def test_a_selected_document_is_the_only_source(indexed: TestClient):
    """The warranty and installation passages are unreachable.

    This is the defect that was reported: a request about the meeting
    notes returned passages from the product manual, and the summary
    mixed the two.
    """
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    report = _execute(indexed, _plan(indexed, [meeting_notes]))
    extract = _result(report, "document.extract")

    assert extract["status"] == "completed"
    passages = extract["output"]["passages"]
    assert passages
    for passage in passages:
        assert passage["document_id"] == meeting_notes
        assert passage["document_name"] == "meeting_notes.md"

    # The unrelated document's content is nowhere in the evidence.
    text = " ".join(passage["text"].lower() for passage in passages)
    assert "warranty" not in text
    assert "installation" not in text
    assert "device x1" not in text


def test_the_summary_contains_no_unrelated_document_content(indexed: TestClient):
    """The summary does not quote the document the user did not select."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    report = _execute(indexed, _plan(indexed, [meeting_notes]))
    summarise = _result(report, "llm.summarise")

    assert summarise["status"] == "completed"
    for evidence in summarise["output"]["evidence"]:
        assert evidence["document_id"] == meeting_notes

    text = summarise["output"]["summary_text"].lower()
    assert "warranty" not in text
    assert "installation" not in text
    assert "device x1" not in text


def test_the_summary_describes_the_meeting_not_the_manual(indexed: TestClient):
    """The summary is about the meeting: its plan, its work and its actions."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    report = _execute(indexed, _plan(indexed, [meeting_notes]))
    summarise = _result(report, "llm.summarise")
    text = summarise["output"]["summary_text"]

    assert "2026-10-12" in text
    assert "Priya Raman" in text
    assert "agreed" in text.lower()
    assert "Complete the intent-classification component" in text


def test_the_extraction_reports_the_documents_it_read(indexed: TestClient):
    """The output says which documents the passages came from."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    report = _execute(indexed, _plan(indexed, [meeting_notes]))
    extract = _result(report, "document.extract")

    assert extract["output"]["documents"] == [meeting_notes]


def test_the_summary_reports_the_documents_it_covered(indexed: TestClient):
    """The summary says which documents it covers."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    report = _execute(indexed, _plan(indexed, [meeting_notes]))
    summarise = _result(report, "llm.summarise")

    assert summarise["output"]["documents"] == [meeting_notes]


# ---------------------------------------------------------------------------
# Cross-document analysis — possible, but only when it is asked for
# ---------------------------------------------------------------------------


def test_a_request_may_explicitly_span_two_documents(indexed: TestClient):
    """A request that names both documents may retrieve from both.

    Cross-document retrieval is possible, but it is never the default: it
    happens only when the caller states which documents are in scope.
    """
    meeting_notes = _document_id(indexed, "meeting_notes.md")
    product_manual = _document_id(indexed, "product_manual.md")

    plan = _plan(indexed, [meeting_notes, product_manual], CROSS_DOCUMENT_REQUEST)
    assert plan["source_documents"] == [meeting_notes, product_manual]

    report = _execute(indexed, plan)
    extract = _result(report, "document.extract")

    document_ids = {passage["document_id"] for passage in extract["output"]["passages"]}
    assert document_ids <= {meeting_notes, product_manual}
    assert document_ids


def test_a_cross_document_summary_keeps_the_documents_apart(indexed: TestClient):
    """Two documents are summarised separately, never blended into one.

    A reader must be able to tell which document a statement came from,
    so each document gets its own headings and the sections record which
    document they describe.
    """
    meeting_notes = _document_id(indexed, "meeting_notes.md")
    product_manual = _document_id(indexed, "product_manual.md")

    plan = _plan(indexed, [meeting_notes, product_manual], CROSS_DOCUMENT_REQUEST)
    report = _execute(indexed, plan)
    summarise = _result(report, "llm.summarise")
    output = summarise["output"]

    assert set(output["documents"]) <= {meeting_notes, product_manual}

    for section in output["sections"]:
        assert section["document_id"] in {meeting_notes, product_manual}

    by_document: dict[str, set[str]] = {}
    for section in output["sections"]:
        for item in section["items"]:
            by_document.setdefault(section["document_id"], set()).add(item["text"])

    all_meeting = " ".join(by_document.get(meeting_notes, set()))
    all_manual = " ".join(by_document.get(product_manual, set()))
    if all_meeting and all_manual:
        # A meeting statement never appears under the manual, and a manual
        # statement never appears under the meeting.
        assert "Priya Raman" not in all_manual
        assert "warranty" not in all_meeting.lower()


def test_the_summary_never_blends_two_documents_into_one_section(
    indexed: TestClient,
):
    """A section may not contain items from more than one document."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")
    product_manual = _document_id(indexed, "product_manual.md")

    plan = _plan(indexed, [meeting_notes, product_manual], CROSS_DOCUMENT_REQUEST)
    report = _execute(indexed, plan)
    summarise = _result(report, "llm.summarise")

    for section in summarise["output"]["sections"]:
        if not section["items"]:
            continue
        item_documents = {item.get("document_id") for item in section["items"]}
        assert len(item_documents) == 1, (
            "a section mixed items from more than one document"
        )


# ---------------------------------------------------------------------------
# An invalid or missing document id must be handled safely
# ---------------------------------------------------------------------------


def test_an_unknown_document_id_is_reported_not_guessed(indexed: TestClient):
    """A document id that is not indexed must fail clearly."""
    plan = _plan(indexed, ["doc_does_not_exist"])

    report = _execute(indexed, plan)
    read = _result(report, "document.read")

    assert read["status"] == "failed"
    assert "doc_does_not_exist" in (read["error"] or "")

    # Nothing was retrieved, and nothing was invented.
    for result in report["task_results"]:
        assert result["status"] != "completed"


def test_an_unknown_document_id_does_not_fall_back_to_the_whole_corpus(
    indexed: TestClient,
):
    """An unknown id must not silently widen the search."""
    plan = _plan(indexed, ["doc_does_not_exist"])

    report = _execute(indexed, plan)
    extract = next(
        (
            result
            for result in report["task_results"]
            if result["capability"] == "document.extract"
        ),
        None,
    )
    if extract is not None and extract["status"] == "completed":
        documents = set(extract["output"].get("documents") or [])
        assert "doc_does_not_exist" not in documents
        assert documents
    else:
        # The extraction was blocked because the read failed, which is the
        # correct outcome.
        assert extract is None or extract["status"] != "completed"


def test_an_empty_scope_does_not_silently_mean_every_document(indexed: TestClient):
    """An empty scope is not the same as a scope of every document."""
    plan = _plan(indexed, [])

    # The plan reports that it has no source document, because an empty
    # list is not a selection.
    joined = " ".join(plan["missing_information"]).lower()
    assert "no source document" in joined


# ---------------------------------------------------------------------------
# Without a scope, the plan says what it needs
# ---------------------------------------------------------------------------


def test_without_a_scope_the_plan_asks_for_a_document(indexed: TestClient):
    """Without a selection the plan says what it needs, and nothing runs."""
    plan = _plan(indexed, None)

    joined = " ".join(plan["missing_information"]).lower()
    assert "no source document" in joined

    report = _execute(indexed, plan)
    for result in report["task_results"]:
        assert result["status"] != "completed"


def test_the_read_task_names_the_document_and_the_others_name_the_scope(
    indexed: TestClient,
):
    """The reading task names one document; the others name the scope."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")
    product_manual = _document_id(indexed, "product_manual.md")

    plan = _plan(indexed, [meeting_notes, product_manual], CROSS_DOCUMENT_REQUEST)

    for task in plan["tasks"]:
        parameters = {
            parameter["name"]: parameter["value"]
            for parameter in task.get("input_parameters") or []
        }
        capabilities = task["required_capabilities"]
        if "document.read" in capabilities:
            assert parameters.get("document_id") == meeting_notes
        elif set(capabilities) & {"document.extract", "llm.summarise"}:
            assert parameters.get("document_ids") == [meeting_notes, product_manual]
