"""Tests for the intent-confirmation flow.

The classifier is experimental: a 12-way taxonomy over 75 training
examples produces low absolute probabilities even when its top-ranked
intent is the right one. Rather than block the request or plan it on a
guess, NexusAI shows the ranked candidates and lets the user choose. The
choice is then planned as an explicit intent.

The tests here cover three things:

* the confirmation flow lets a valid request reach the planner;
* an explicit choice never bypasses the destructive-operation guard;
* the safety refusals still refuse.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexusai.app.config import Settings
from nexusai.app.main import create_app
from nexusai.ml.planner.service import create_plan
from nexusai.ml.schemas import ClassificationStatus, IntentCategory

# A request the classifier ranks first as document_summarisation, but with a
# probability below the clarification threshold.
MEETING_NOTES = "Summarise the uploaded meeting notes and identify the important decisions."

# A request the classifier ranks first as destructive_operation with
# confidence. Measured against the shipped model, this phrasing scores
# 0.627 on destructive_operation, above the 0.55 confidence threshold.
DESTRUCTIVE = "Delete every file in the data directory."

# A request the classifier also ranks first as destructive_operation, but
# only at 0.451 — below the confidence threshold and inside the same range
# as benign phrasings such as "how do I delete my old backups safely". The
# classifier cannot separate the two, so this case is recorded rather than
# refused.
DESTRUCTIVE_UNCERTAIN = "Delete all files in the project folder."


@pytest.fixture
def client(tmp_path) -> TestClient:
    """A test client with an isolated database and vector index."""
    settings = Settings(
        database_url="sqlite:///:memory:",
        vector_store_dir=str(tmp_path / "vectors"),
        allowed_document_roots=["./data", "./docs", "./experiments", str(tmp_path)],
    )
    return TestClient(create_app(settings))


# ---------------------------------------------------------------------------
# The guard — a confirmed intent may not redirect a destructive classification
# ---------------------------------------------------------------------------


def test_confirmed_intent_cannot_redirect_a_confident_destructive_classification():
    """A confirmed intent must not erase a confident destructive verdict."""
    plan, warnings = create_plan(
        request=DESTRUCTIVE,
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        source="explicit",
        classifier_intent=IntentCategory.DESTRUCTIVE_OPERATION.value,
        classifier_status=ClassificationStatus.CONFIDENT.value,
    )

    assert plan.plan_status.value == "invalid"
    assert plan.tasks == []
    assert plan.clarification_required is True
    assert plan.requires_approval is True
    assert plan.approval_reasons
    assert warnings
    assert "destructive" in plan.clarification_question.lower()


def test_a_low_confidence_destructive_guess_does_not_block_a_redirect():
    """A weak destructive guess is noise, not a signal, so it does not block.

    The classifier's per-class F1 for ``destructive_operation`` is 0.00, so a
    low-confidence destructive prediction must not be allowed to refuse an
    otherwise ordinary request.
    """
    plan, _warnings = create_plan(
        request="Summarise the notes.",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        source="explicit",
        classifier_intent=IntentCategory.DESTRUCTIVE_OPERATION.value,
        classifier_status=ClassificationStatus.LOW_CONFIDENCE.value,
    )

    assert plan.plan_status.value == "ready"
    assert plan.tasks


def test_no_classifier_verdict_leaves_a_redirect_untouched():
    """With no classifier verdict there is nothing to guard against."""
    plan, _warnings = create_plan(
        request="Summarise the notes.",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        source="explicit",
    )

    assert plan.plan_status.value == "ready"
    assert plan.tasks


def test_selecting_the_destructive_intent_is_still_refused():
    """Choosing the refusal path is refused by the special-intent handling."""
    plan, _warnings = create_plan(
        request=DESTRUCTIVE,
        intent=IntentCategory.DESTRUCTIVE_OPERATION.value,
        source="explicit",
        classifier_intent=IntentCategory.DESTRUCTIVE_OPERATION.value,
        classifier_status=ClassificationStatus.CONFIDENT.value,
    )

    assert plan.plan_status.value == "invalid"
    assert plan.tasks == []
    assert plan.requires_approval is True


# ---------------------------------------------------------------------------
# The API — the guard is enforced by the server, not by the UI
# ---------------------------------------------------------------------------


def test_api_refuses_a_redirect_away_from_a_destructive_classification(client: TestClient):
    """The server refuses even when the caller asserts the intent."""
    response = client.post(
        "/api/v1/planner/plan",
        json={
            "text": DESTRUCTIVE,
            "intent": IntentCategory.DOCUMENT_SUMMARISATION.value,
            "source": "explicit",
        },
    )

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["plan_status"] == "invalid"
    assert plan["tasks"] == []
    assert plan["requires_approval"] is True


def test_api_refuses_a_redirect_that_claims_classifier_source(client: TestClient):
    """Claiming the classifier's source must not bypass the guard."""
    response = client.post(
        "/api/v1/planner/plan",
        json={
            "text": DESTRUCTIVE,
            "intent": IntentCategory.DOCUMENT_SUMMARISATION.value,
            "source": "classifier",
        },
    )

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["plan_status"] == "invalid"
    assert plan["tasks"] == []


def test_an_uncertain_destructive_signal_is_recorded_rather_than_refused(
    client: TestClient,
):
    """A weak destructive signal is reported, not used to refuse a request.

    The classifier's per-class F1 for ``destructive_operation`` is 0.00, and
    it scores benign phrasings such as "how do I delete my old backups
    safely" in the same range as genuine destructive commands. Refusing on
    that signal would block legitimate questions, so the signal is recorded
    on the plan instead — the destructive part is reported rather than
    silently dropped.
    """
    response = client.post(
        "/api/v1/planner/plan",
        json={
            "text": DESTRUCTIVE_UNCERTAIN,
            "intent": IntentCategory.DOCUMENT_SUMMARISATION.value,
            "source": "explicit",
        },
    )

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["plan_status"] in ("ready", "validated")
    assert plan["tasks"]

    # The destructive signal is visible on the plan.
    notes = " ".join(plan["unsupported_operations"]).lower()
    assert "destructive" in notes
    assert plan["requires_approval"] is True
    assert plan["approval_reasons"]


def test_a_benign_request_is_not_blocked_by_a_destructive_top_intent(
    client: TestClient,
):
    """A benign question about deleting files must still be answerable.

    "How do I delete my old backups safely?" is classified as a destructive
    operation by the shipped model, at the same confidence as a genuine
    destructive command. A guard that refused it would block a legitimate
    request, so the uncertain signal is recorded rather than enforced.
    """
    response = client.post(
        "/api/v1/planner/plan",
        json={
            "text": "How do I delete my old backups safely?",
            "intent": IntentCategory.DOCUMENT_QUESTION_ANSWERING.value,
            "source": "explicit",
        },
    )

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["plan_status"] in ("ready", "validated")
    assert plan["tasks"]


def test_api_plans_a_confirmed_intent_for_an_ordinary_request(client: TestClient):
    """A confirmed intent produces a ready plan for a supported intent."""
    response = client.post(
        "/api/v1/planner/plan",
        json={
            "text": MEETING_NOTES,
            "intent": IntentCategory.DOCUMENT_SUMMARISATION.value,
            "source": "explicit",
        },
    )

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["intent"] == IntentCategory.DOCUMENT_SUMMARISATION.value
    assert plan["plan_status"] in ("ready", "validated")
    assert plan["tasks"]
    assert plan["execution_order"]
    assert plan["source"] == "explicit"
    assert plan["clarification_required"] is False


# ---------------------------------------------------------------------------
# The confirmation flow — candidates and their scores
# ---------------------------------------------------------------------------


def test_classification_returns_ranked_candidates(client: TestClient):
    """The classification response carries a score for every intent."""
    response = client.post("/api/v1/intent/classify", json={"text": MEETING_NOTES})

    assert response.status_code == 200
    result = response.json()["result"]
    scores = result["all_scores"]

    # The classifier scores the categories it was trained on. The
    # taxonomy has one more category than the model, because the reminder
    # capability was added after the model was trained; the classifier
    # does not score it, and the confirmation flow does not offer it.
    assert len(scores) == len(list(IntentCategory)) - 1
    assert IntentCategory.REMINDER.value not in scores

    # The scores are ranked, and the top-ranked intent for this request is
    # the summarisation.
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    assert ranked[0][0] == IntentCategory.DOCUMENT_SUMMARISATION.value
    assert ranked[0][1] > ranked[1][1]


def test_candidates_helper_ranks_and_labels_the_scores():
    """The UI helper ranks the candidates and marks the refusal paths."""
    from nexusai.app.ui.components import intent_candidates

    candidates = intent_candidates(
        {
            "all_scores": {
                "document_summarisation": 0.24,
                "document_transformation": 0.16,
                "destructive_operation": 0.02,
            }
        }
    )

    assert [c["intent"] for c in candidates] == [
        "document_summarisation",
        "document_transformation",
        "destructive_operation",
    ]
    assert candidates[0]["is_supported"] is True
    assert candidates[0]["is_refusal"] is False
    assert candidates[2]["is_refusal"] is True
    assert candidates[0]["label"] == "document summarisation"


def test_candidates_helper_respects_its_limit():
    """The helper never returns more candidates than asked for."""
    from nexusai.app.ui.components import intent_candidates

    scores = {intent.value: 0.1 for intent in IntentCategory}
    assert len(intent_candidates({"all_scores": scores}, limit=3)) == 3


# ---------------------------------------------------------------------------
# The safety refusals must survive the confirmation flow
# ---------------------------------------------------------------------------


def test_destructive_request_is_still_refused_without_any_selection(client: TestClient):
    """The classifier's own destructive verdict is still a refusal."""
    plan = client.post(
        "/api/v1/planner/plan",
        json={"text": DESTRUCTIVE},
    ).json()["plan"]

    assert plan["plan_status"] == "invalid"
    assert plan["tasks"] == []
    assert plan["requires_approval"] is True


def test_destructive_request_is_refused_for_the_uncertain_phrasing_too(
    client: TestClient,
):
    """The refusal path holds even when the destructive score is lower.

    The request is not planned as a destructive operation either way, so
    there is no plan and nothing to execute.
    """
    plan = client.post(
        "/api/v1/planner/plan",
        json={"text": DESTRUCTIVE_UNCERTAIN},
    ).json()["plan"]

    assert plan["intent"] == IntentCategory.DESTRUCTIVE_OPERATION.value
    assert plan["plan_status"] == "invalid"
    assert plan["tasks"] == []
    assert plan["requires_approval"] is True


def test_infeasible_request_is_still_refused(client: TestClient):
    """An infeasible goal still reports that it cannot be completed."""
    plan = client.post(
        "/api/v1/planner/plan",
        json={"text": "Book me a flight to London tomorrow."},
    ).json()["plan"]

    assert plan["plan_status"] == "invalid"
    assert plan["tasks"] == []


def test_communication_plan_still_requires_approval(client: TestClient):
    """A sending request is still flagged for approval and never sent."""
    plan = client.post(
        "/api/v1/planner/plan",
        json={
            "text": "Send the report to the client.",
            "intent": IntentCategory.COMMUNICATION.value,
            "source": "explicit",
        },
    ).json()["plan"]

    assert plan["requires_approval"] is True

    report = client.post("/api/v1/execution/execute", json={"plan": plan}).json()["report"]
    for result in report["task_results"]:
        assert result["status"] != "completed"
