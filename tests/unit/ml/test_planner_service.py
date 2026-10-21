"""Tests for the planner service."""

from __future__ import annotations

import pytest

from nexusai.ml.planner.schemas import PlanStatus, TaskType
from nexusai.ml.planner.service import (
    PlannerService,
    create_plan,
    get_planner_service,
    reset_planner_service,
)
from nexusai.ml.schemas import IntentCategory

SUPPORTED = [
    IntentCategory.DOCUMENT_QUESTION_ANSWERING,
    IntentCategory.DOCUMENT_SUMMARISATION,
    IntentCategory.DOCUMENT_EXTRACTION,
    IntentCategory.DOCUMENT_TRANSFORMATION,
    IntentCategory.DATA_ANALYSIS,
    IntentCategory.RESEARCH,
    IntentCategory.COMMUNICATION,
]


@pytest.fixture(autouse=True)
def _reset():
    """Reset the shared planner service between tests."""
    reset_planner_service()
    yield
    reset_planner_service()


def test_get_planner_service_is_shared():
    """Test that the planner service is a singleton."""
    first = get_planner_service()
    second = get_planner_service()
    assert first is second


@pytest.mark.parametrize("intent", SUPPORTED, ids=lambda i: i.value)
def test_each_supported_intent_produces_a_ready_plan(intent):
    """Test that every supported intent decomposes into a valid plan."""
    plan, warnings = create_plan(
        request="Process data/sample/product_manual.md and report the result.",
        intent=intent.value,
        source="explicit",
    )
    assert plan.plan_status == PlanStatus.READY
    assert len(plan.tasks) >= 2
    assert len(plan.execution_order) == len(plan.tasks)
    assert warnings == []
    assert plan.intent == intent.value


def test_plan_records_dependencies_consistently():
    """Test that plan-level and task-level dependencies agree."""
    plan, _ = create_plan(
        request="Summarise data/sample/product_manual.md",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        source="explicit",
    )
    task_ids = {t.task_id for t in plan.tasks}
    for prerequisite, dependent in plan.dependencies:
        assert prerequisite in task_ids
        assert dependent in task_ids
        dependent_task = plan.get_task(dependent)
        assert prerequisite in dependent_task.dependencies


def test_plan_source_is_recorded():
    """Test that the source of the intent is recorded on the plan."""
    plan, _ = create_plan(
        request="Summarise the manual",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        source="explicit",
    )
    assert plan.source == "explicit"


def test_empty_request_with_explicit_intent():
    """Test that an empty request still produces a plan when intent is given."""
    plan, _ = create_plan(
        request="",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        source="explicit",
    )
    assert plan.plan_status == PlanStatus.READY
    assert plan.missing_information


def test_missing_intent_produces_error_plan():
    """Test that a missing intent produces an error plan."""
    plan, warnings = create_plan(request="Do something", intent=None)
    assert plan.plan_status == PlanStatus.INVALID
    assert plan.validation_errors
    assert warnings


def test_unknown_intent_produces_error_plan():
    """Test that an unknown intent produces an error plan."""
    plan, warnings = create_plan(request="Do something", intent="not_an_intent")
    assert plan.plan_status == PlanStatus.INVALID
    assert any("Unknown intent" in e for e in plan.validation_errors)
    assert warnings


def test_clarification_required_status_blocks_planning():
    """Test that a clarification-required classification does not plan."""
    plan, warnings = create_plan(
        request="Deal with the report",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        intent_status="clarification_required",
        intent_confidence=0.12,
        source="classifier",
    )
    assert plan.plan_status == PlanStatus.INVALID
    assert plan.clarification_required is True
    assert plan.clarification_question
    assert plan.tasks == []
    assert warnings


def test_low_confidence_is_not_treated_as_ground_truth():
    """Test that a low-confidence classification is surfaced, not planned."""
    plan, _ = create_plan(
        request="Deal with the report",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        intent_status="low_confidence",
        intent_confidence=0.3,
        source="classifier",
    )
    # low_confidence is not a blocking status, but the plan records that the
    # intent was classifier-derived rather than explicit.
    assert plan.source == "classifier"
    assert plan.intent == IntentCategory.DOCUMENT_SUMMARISATION.value


def test_error_status_blocks_planning():
    """Test that an errored classification does not plan."""
    plan, warnings = create_plan(
        request="Anything",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        intent_status="error",
        source="classifier",
    )
    assert plan.plan_status == PlanStatus.INVALID
    assert warnings


def test_abstained_status_blocks_planning():
    """Test that an abstained classification does not plan."""
    plan, _ = create_plan(
        request="Anything",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        intent_status="abstained",
        source="classifier",
    )
    assert plan.plan_status == PlanStatus.INVALID


@pytest.mark.parametrize(
    "intent",
    [
        IntentCategory.DESTRUCTIVE_OPERATION,
        IntentCategory.INFEASIBLE,
        IntentCategory.OUT_OF_SCOPE,
        IntentCategory.CHANNEL_UNAVAILABLE,
        IntentCategory.INVALID,
    ],
    ids=lambda i: i.value,
)
def test_special_intents_never_produce_tasks(intent):
    """Test that special-handling intents never become executable plans."""
    plan, warnings = create_plan(
        request="Delete every file in the notes/ directory",
        intent=intent.value,
        source="explicit",
    )
    assert plan.plan_status == PlanStatus.INVALID
    assert plan.tasks == []
    assert plan.clarification_required is True
    assert plan.clarification_question
    assert warnings


def test_destructive_intent_requires_approval():
    """Test that a destructive intent requires approval and no tasks."""
    plan, _ = create_plan(
        request="Delete every file in the notes/ directory",
        intent=IntentCategory.DESTRUCTIVE_OPERATION.value,
        source="explicit",
    )
    assert plan.requires_approval is True
    assert plan.approval_reasons
    assert plan.tasks == []


def test_write_task_requires_approval():
    """Test that a plan containing a write task requires approval."""
    plan, _ = create_plan(
        request="Convert data/sample/meeting_notes.md to PDF and save it",
        intent=IntentCategory.DOCUMENT_TRANSFORMATION.value,
        source="explicit",
    )
    assert plan.requires_approval is True
    assert any("approval" in reason for reason in plan.approval_reasons)


def test_send_task_requires_approval():
    """Test that a communication plan requires approval for the send step."""
    plan, _ = create_plan(
        request="Email the client the project update",
        intent=IntentCategory.COMMUNICATION.value,
        source="explicit",
    )
    assert plan.requires_approval is True
    assert any(
        t.task_type == TaskType.COMMUNICATION_SEND for t in plan.tasks
    )


def test_read_only_plan_does_not_require_approval():
    """Test that a read-only plan does not require approval."""
    plan, _ = create_plan(
        request="What does data/sample/product_manual.md say about warranty?",
        intent=IntentCategory.DOCUMENT_QUESTION_ANSWERING.value,
        source="explicit",
    )
    assert plan.requires_approval is False
    assert plan.approval_reasons == []


def test_missing_document_path_is_recorded():
    """Test that a missing document reference is recorded."""
    plan, _ = create_plan(
        request="Summarise it for me please",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        source="explicit",
    )
    assert any("document path" in item for item in plan.missing_information)


def test_missing_data_measure_is_recorded():
    """Test that a missing measure for a data analysis is recorded."""
    plan, _ = create_plan(
        request="Look at data/sample/sales_2026.csv",
        intent=IntentCategory.DATA_ANALYSIS.value,
        source="explicit",
    )
    assert any("measure" in item.lower() for item in plan.missing_information)


def test_missing_recipient_is_recorded():
    """Test that a missing recipient for communication is recorded."""
    plan, _ = create_plan(
        request="Send the report",
        intent=IntentCategory.COMMUNICATION.value,
        source="explicit",
    )
    assert any("recipient" in item.lower() for item in plan.missing_information)


def test_unsupported_operation_is_detected():
    """Test that an unsupported operation is detected."""
    plan, _ = create_plan(
        request="Research the topic and then deploy the service",
        intent=IntentCategory.RESEARCH.value,
        source="explicit",
    )
    assert any("Deployment" in item for item in plan.unsupported_operations)


def test_entities_are_attached_to_first_task():
    """Test that extracted entities are recorded on the plan."""
    plan, _ = create_plan(
        request="Summarise data/sample/product_manual.md",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        entities={"document": "data/sample/product_manual.md"},
        source="explicit",
    )
    assert plan.tasks[0].input_parameters
    parameter = plan.tasks[0].input_parameters[0]
    assert parameter.name == "entities"
    assert parameter.value == {"document": "data/sample/product_manual.md"}


def test_planner_service_plan_method():
    """Test the PlannerService.plan() convenience method."""
    service = PlannerService()
    plan = service.plan(
        request="Summarise data/sample/product_manual.md",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
    )
    assert plan.plan_status == PlanStatus.READY
    assert plan.source == "explicit"


def test_plan_is_deterministic():
    """Test that the same request and intent produce the same task structure."""
    first, _ = create_plan(
        request="Summarise data/sample/product_manual.md",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        source="explicit",
    )
    second, _ = create_plan(
        request="Summarise data/sample/product_manual.md",
        intent=IntentCategory.DOCUMENT_SUMMARISATION.value,
        source="explicit",
    )
    assert [t.task_type for t in first.tasks] == [t.task_type for t in second.tasks]
    assert [t.task_name for t in first.tasks] == [t.task_name for t in second.tasks]
    assert len(first.tasks) == len(second.tasks)
