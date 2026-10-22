"""Regression tests for the summarisation and retrieval quality.

Three defects were found by manually testing the cross-document
summarisation:

1. The product manual's table of operating limits was reported as
   *action items*, with the field names read as owners — "Parameter
   (owner: Parameter)" and "Supply voltage (owner: V)". A table of
   parameters is not a list of tasks.
2. The provenance line was truncated, because it is soft-wrapped across
   several lines and the text was read a line at a time.
3. The passages returned for a cross-document request were whichever
   chunks happened to score highest on a word the documents share, so
   one document could take every slot and the other was absent.

The tests here cover the ten behaviours that must hold.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexusai.app.config import Settings
from nexusai.app.main import create_app

MEETING_NOTES = "data/sample/meeting_notes.md"
PRODUCT_MANUAL = "data/sample/product_manual.md"

MEETING_REQUEST = "Summarise the uploaded meeting notes and identify the important decisions."
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


def _summary(
    client: TestClient,
    source_documents: list[str] | None = None,
    text: str = MEETING_REQUEST,
) -> dict:
    """Run a summarisation and return the summary output."""
    payload = {
        "text": text,
        "intent": "document_summarisation",
        "source": "explicit",
    }
    if source_documents is not None:
        payload["source_documents"] = list(source_documents)
    plan = client.post("/api/v1/planner/plan", json=payload).json()["plan"]
    report = client.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]
    summarise = next(
        result for result in report["task_results"] if result["capability"] == "llm.summarise"
    )
    assert summarise["status"] == "completed"
    return summarise["output"]


def _section(output: dict, document_id: str, name: str) -> dict:
    """Return one section of one document's summary."""
    for section in output["sections"]:
        if section["document_id"] == document_id and section["name"] == name:
            return section
    raise AssertionError(f"no '{name}' section for {document_id}")


def _items(output: dict, document_id: str, name: str) -> list[dict]:
    """Return the items of one section of one document's summary."""
    return _section(output, document_id, name)["items"]


# ---------------------------------------------------------------------------
# 1 and 2 — the meeting notes
# ---------------------------------------------------------------------------


def test_the_meeting_notes_produce_the_two_supported_decisions(indexed: TestClient):
    """The meeting notes record two decisions, and both are reported."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    output = _summary(indexed, [meeting_notes])
    decisions = _items(output, meeting_notes, "decisions")

    assert len(decisions) == 2
    assert all("agreed" in item["text"].lower() for item in decisions)


def test_the_meeting_notes_produce_the_six_action_items(indexed: TestClient):
    """The six action items are reported with their owners and due dates."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    output = _summary(indexed, [meeting_notes])
    actions = _items(output, meeting_notes, "action_items")

    assert len(actions) == 6
    assert {item["owner"] for item in actions} == {
        "Priya Raman",
        "Sofia Almeida",
        "Kenji Nakamura",
        "Grace Oyelaran",
        "Tom Whitfield",
    }
    assert {item["due"] for item in actions} == {
        "2026-10-16",
        "2026-10-17",
        "2026-10-18",
    }
    # The action is the text of the row, not the row number.
    for item in actions:
        assert not item["text"].isdigit()
        assert len(item["text"]) > 20
        assert item["source_reference"]


# ---------------------------------------------------------------------------
# 3 and 4 — the product manual
# ---------------------------------------------------------------------------


def test_the_product_manual_does_not_report_operating_limits_as_action_items(
    indexed: TestClient,
):
    """A table of parameters is not a list of tasks.

    The defect was that the operating-limits table was reported as
    action items, with the field name read as an owner: "Parameter
    (owner: Parameter)" and "Supply voltage (owner: V)".
    """
    product_manual = _document_id(indexed, "product_manual.md")

    output = _summary(indexed, [product_manual])
    actions = _items(output, product_manual, "action_items")

    assert actions == [], (
        "the operating-limits table must not be reported as action items"
    )
    texts = " ".join(item["text"].lower() for item in actions)
    assert "operating temperature" not in texts
    assert "supply voltage" not in texts


def test_the_product_manual_reports_no_decisions(indexed: TestClient):
    """The product manual records no decision, and says so."""
    product_manual = _document_id(indexed, "product_manual.md")

    output = _summary(indexed, [product_manual])
    section = _section(output, product_manual, "decisions")

    assert section["items"] == []
    assert section["note"]
    assert "decision" in section["note"].lower()


def test_the_product_manual_reports_an_empty_action_section(indexed: TestClient):
    """An empty action section is reported honestly, not filled."""
    product_manual = _document_id(indexed, "product_manual.md")

    output = _summary(indexed, [product_manual])
    section = _section(output, product_manual, "action_items")

    assert section["items"] == []
    assert section["note"]


def test_the_product_manual_keeps_its_values_with_their_fields(indexed: TestClient):
    """A table that is not an action table keeps its field and value pairs."""
    product_manual = _document_id(indexed, "product_manual.md")

    output = _summary(indexed, [product_manual])
    values = _items(output, product_manual, "values")

    assert values, "the operating-limits table should be reported as values"
    by_field = {item["fields"].get("Parameter"): item for item in values}
    assert "Operating temperature" in by_field
    assert by_field["Operating temperature"]["fields"]["Minimum"] == "0"
    assert by_field["Operating temperature"]["fields"]["Maximum"] == "40"


# ---------------------------------------------------------------------------
# 5 — the provenance is not truncated
# ---------------------------------------------------------------------------


def test_the_product_manual_keeps_its_complete_provenance(indexed: TestClient):
    """The provenance paragraph is soft-wrapped and must not be cut short."""
    product_manual = _document_id(indexed, "product_manual.md")

    output = _summary(indexed, [product_manual])
    overview = _items(output, product_manual, "overview")

    provenance = [item["text"] for item in overview if "Provenance" in item["text"]]
    assert provenance, "the provenance is missing from the overview"

    text = provenance[0]
    assert "Not sourced from any" in text
    assert "third party" in text
    assert "no real product, person, or organisation" in text


def test_the_meeting_notes_keep_their_complete_provenance(indexed: TestClient):
    """The same holds for the meeting notes."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    output = _summary(indexed, [meeting_notes])
    overview = _items(output, meeting_notes, "overview")

    provenance = [item["text"] for item in overview if "Provenance" in item["text"]]
    assert provenance
    assert "Not a record of any real meeting" in provenance[0]


# ---------------------------------------------------------------------------
# 6 — a section never mixes documents
# ---------------------------------------------------------------------------


def test_each_section_references_only_its_own_document(indexed: TestClient):
    """No section of a cross-document summary mixes two documents."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")
    product_manual = _document_id(indexed, "product_manual.md")

    output = _summary(indexed, [meeting_notes, product_manual], CROSS_DOCUMENT_REQUEST)

    assert output["sections"]
    for section in output["sections"]:
        if not section["items"]:
            continue
        assert section["document_id"] in {meeting_notes, product_manual}
        for item in section["items"]:
            assert item["document_id"] == section["document_id"]
            assert item["source_reference"]


def test_the_cross_document_summary_separates_the_two_documents(indexed: TestClient):
    """Each document gets its own headings, so a reader can tell them apart."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")
    product_manual = _document_id(indexed, "product_manual.md")

    output = _summary(indexed, [meeting_notes, product_manual], CROSS_DOCUMENT_REQUEST)

    meeting_text = " ".join(
        item["text"]
        for section in output["sections"]
        if section["document_id"] == meeting_notes
        for item in section["items"]
    )
    manual_text = " ".join(
        item["text"]
        for section in output["sections"]
        if section["document_id"] == product_manual
        for item in section["items"]
    )

    assert "Priya Raman" in meeting_text
    assert "Operating temperature" in manual_text
    assert "Priya Raman" not in manual_text
    assert "Operating temperature" not in meeting_text


# ---------------------------------------------------------------------------
# 7 and 8 — retrieval honours the scope
# ---------------------------------------------------------------------------


def test_explicit_cross_document_retrieval_returns_both_documents(indexed: TestClient):
    """A scope of two documents may retrieve from both."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")
    product_manual = _document_id(indexed, "product_manual.md")

    payload = {
        "text": CROSS_DOCUMENT_REQUEST,
        "intent": "document_summarisation",
        "source": "explicit",
        "source_documents": [meeting_notes, product_manual],
    }
    plan = indexed.post("/api/v1/planner/plan", json=payload).json()["plan"]
    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]
    extract = next(
        result for result in report["task_results"] if result["capability"] == "document.extract"
    )

    documents = set(extract["output"]["documents"])
    assert documents <= {meeting_notes, product_manual}
    assert documents == {meeting_notes, product_manual}


def test_a_single_document_scope_never_returns_another_document(indexed: TestClient):
    """A scope of one document returns only that document."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    payload = {
        "text": MEETING_REQUEST,
        "intent": "document_summarisation",
        "source": "explicit",
        "source_documents": [meeting_notes],
    }
    plan = indexed.post("/api/v1/planner/plan", json=payload).json()["plan"]
    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]
    extract = next(
        result for result in report["task_results"] if result["capability"] == "document.extract"
    )

    assert set(extract["output"]["documents"]) == {meeting_notes}
    for passage in extract["output"]["passages"]:
        assert passage["document_id"] == meeting_notes


def test_a_request_that_names_a_file_is_scoped_to_it(indexed: TestClient):
    """A request that names a file is about that file.

    The words in such a request are often the boilerplate every document
    shares, so the file reference itself is what decides the scope.
    """
    payload = {
        "text": "Read data/sample/meeting_notes.md and summarise the decisions.",
        "intent": "document_summarisation",
        "source": "explicit",
    }
    plan = indexed.post("/api/v1/planner/plan", json=payload).json()["plan"]
    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]
    extract = next(
        result for result in report["task_results"] if result["capability"] == "document.extract"
    )

    meeting_notes = _document_id(indexed, "meeting_notes.md")
    assert set(extract["output"]["documents"]) == {meeting_notes}


# ---------------------------------------------------------------------------
# 9 — insufficient evidence is reported honestly
# ---------------------------------------------------------------------------


def test_an_unindexed_document_reports_insufficient_evidence(indexed: TestClient):
    """A document that is not indexed is reported, not guessed."""
    payload = {
        "text": MEETING_REQUEST,
        "intent": "document_summarisation",
        "source": "explicit",
        "source_documents": ["doc_does_not_exist"],
    }
    plan = indexed.post("/api/v1/planner/plan", json=payload).json()["plan"]
    report = indexed.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]

    read = next(
        result for result in report["task_results"] if result["capability"] == "document.read"
    )
    assert read["status"] == "failed"
    assert "doc_does_not_exist" in (read["error"] or "")

    for result in report["task_results"]:
        assert result["status"] != "completed"


def test_a_summary_with_no_evidence_says_so(client: TestClient):
    """With nothing indexed there is no summary, and it says so."""
    response = client.post(
        "/api/v1/documents/summarise", json={"question": "what was decided?"}
    )

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["status"] in ("insufficient_evidence", "no_documents")
    assert summary["summary_text"]


# ---------------------------------------------------------------------------
# 10 — the existing protections still hold
# ---------------------------------------------------------------------------


def test_the_stale_plan_protection_still_works(indexed: TestClient):
    """A plan built for a document is still bound to it."""
    meeting_notes = _document_id(indexed, "meeting_notes.md")

    plan = indexed.post(
        "/api/v1/planner/plan",
        json={
            "text": MEETING_REQUEST,
            "intent": "document_summarisation",
            "source": "explicit",
            "source_documents": [meeting_notes],
        },
    ).json()["plan"]

    assert plan["source_documents"] == [meeting_notes]
    for task in plan["tasks"]:
        capabilities = task["required_capabilities"]
        if set(capabilities) & {"document.extract", "llm.summarise"}:
            parameters = {
                parameter["name"]: parameter["value"]
                for parameter in task.get("input_parameters") or []
            }
            assert parameters.get("document_ids") == [meeting_notes]
