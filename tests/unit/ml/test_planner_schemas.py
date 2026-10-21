"""Tests for planner schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nexusai.ml.planner.schemas import (
    APPROVAL_REQUIRED_TASK_TYPES,
    SUPPORTED_TASK_TYPES,
    Plan,
    PlanStatus,
    Task,
    TaskParameter,
    TaskStatus,
    TaskType,
)


def _task(task_id: str, deps: list[str] | None = None) -> Task:
    return Task(
        task_id=task_id,
        task_name=f"Task {task_id}",
        description=f"Description for {task_id}",
        task_type=TaskType.DOCUMENT_READ,
        expected_output="Some output",
        dependencies=deps or [],
    )


def test_task_defaults():
    """Test that a task gets a generated id and pending status."""
    task = Task(
        task_name="Read doc",
        description="Read the document",
        task_type=TaskType.DOCUMENT_READ,
        expected_output="content",
    )
    assert task.task_id
    assert task.status == TaskStatus.PENDING
    assert task.dependencies == []
    assert task.input_parameters == []
    assert task.verification_criteria is None


def test_task_rejects_empty_task_id():
    """Test that a blank task id is rejected."""
    with pytest.raises(ValidationError):
        Task(
            task_id="   ",
            task_name="Read doc",
            description="Read the document",
            task_type=TaskType.DOCUMENT_READ,
            expected_output="content",
        )


def test_task_parameter():
    """Test task parameters."""
    param = TaskParameter(name="path", value="data/sample/file.md")
    assert param.name == "path"
    assert param.required is True


def test_plan_add_task_rejects_duplicate_id():
    """Test that adding a task with an existing id raises."""
    plan = Plan(original_request="test")
    plan.add_task(_task("t1"))
    with pytest.raises(ValueError):
        plan.add_task(_task("t1"))


def test_plan_get_task():
    """Test retrieving a task by id."""
    plan = Plan(original_request="test")
    plan.add_task(_task("t1"))
    assert plan.get_task("t1") is not None
    assert plan.get_task("nope") is None


def test_plan_validate_empty_plan_fails():
    """Test that a plan with no tasks is invalid."""
    plan = Plan(original_request="test")
    errors = plan.validate()
    assert any("at least one task" in e for e in errors)


def test_plan_validate_valid_chain():
    """Test that a valid dependency chain validates and gets an order."""
    plan = Plan(original_request="test")
    plan.add_task(_task("t1"))
    plan.add_task(_task("t2", ["t1"]))
    plan.add_task(_task("t3", ["t2"]))
    plan.dependencies = [("t1", "t2"), ("t2", "t3")]

    errors = plan.validate()
    assert errors == []
    assert plan.execution_order == ["t1", "t2", "t3"]
    assert plan.parallel_levels == [["t1"], ["t2"], ["t3"]]


def test_plan_validate_detects_duplicate_task_ids():
    """Test that duplicate task ids are reported."""
    plan = Plan(original_request="test")
    plan.add_task(_task("t1"))
    plan.tasks.append(_task("t1"))
    errors = plan.validate()
    assert any("Duplicate task id" in e for e in errors)


def test_plan_validate_detects_missing_dependency():
    """Test that a dependency on an unknown task is reported."""
    plan = Plan(original_request="test")
    plan.add_task(_task("t1"))
    plan.dependencies = [("t1", "ghost")]
    errors = plan.validate()
    assert any("unknown task: ghost" in e for e in errors)


def test_plan_validate_detects_self_dependency():
    """Test that a self dependency is reported."""
    plan = Plan(original_request="test")
    plan.add_task(_task("t1"))
    plan.dependencies = [("t1", "t1")]
    errors = plan.validate()
    assert any("Self-dependency" in e for e in errors)


def test_plan_validate_detects_cycle():
    """Test that a dependency cycle is reported."""
    plan = Plan(original_request="test")
    plan.add_task(_task("t1"))
    plan.add_task(_task("t2"))
    plan.dependencies = [("t1", "t2"), ("t2", "t1")]
    errors = plan.validate()
    assert any("Cyclic dependency" in e for e in errors)


def test_plan_validate_detects_unsupported_task_type():
    """Test that a task type outside the supported set is rejected."""
    plan = Plan(original_request="test")
    task = _task("t1")
    task.task_type = TaskType.CUSTOM
    plan.tasks.append(task)
    errors = plan.validate()
    assert any("Unsupported task type" in e for e in errors)


def test_plan_validate_detects_task_level_bad_dependency():
    """Test that a task depending on an unknown task is reported."""
    plan = Plan(original_request="test")
    plan.add_task(_task("t1", ["ghost"]))
    errors = plan.validate()
    assert any("depends on unknown task: ghost" in e for e in errors)


def test_plan_validate_detects_task_self_dependency():
    """Test that a task depending on itself is reported."""
    plan = Plan(original_request="test")
    plan.add_task(_task("t1", ["t1"]))
    errors = plan.validate()
    assert any("depends on itself" in e for e in errors)


def test_plan_get_ready_tasks():
    """Test that only tasks with completed dependencies are ready."""
    plan = Plan(original_request="test")
    plan.add_task(_task("t1"))
    plan.add_task(_task("t2", ["t1"]))
    plan.dependencies = [("t1", "t2")]

    ready = plan.get_ready_tasks()
    assert [t.task_id for t in ready] == ["t1"]

    plan.mark_task_completed("t1")
    ready = plan.get_ready_tasks()
    assert [t.task_id for t in ready] == ["t2"]


def test_plan_mark_task_completed_and_failed():
    """Test task status transitions."""
    plan = Plan(original_request="test")
    plan.add_task(_task("t1"))

    assert plan.mark_task_completed("t1", result="ok") is True
    assert plan.get_task("t1").status == TaskStatus.COMPLETED
    assert plan.get_task("t1").result == "ok"

    assert plan.mark_task_failed("t1", "boom") is True
    assert plan.get_task("t1").status == TaskStatus.FAILED
    assert plan.get_task("t1").error == "boom"

    assert plan.mark_task_completed("missing") is False
    assert plan.mark_task_failed("missing", "x") is False


def test_plan_status_values():
    """Test the plan status enum."""
    assert PlanStatus.DRAFT.value == "draft"
    assert PlanStatus.VALIDATED.value == "validated"
    assert PlanStatus.READY.value == "ready"
    assert PlanStatus.INVALID.value == "invalid"


def test_supported_task_types_excludes_custom():
    """Test that CUSTOM is not in the supported set."""
    assert TaskType.CUSTOM not in SUPPORTED_TASK_TYPES


def test_approval_required_task_types():
    """Test the approval-required task type set."""
    assert TaskType.DOCUMENT_WRITE in APPROVAL_REQUIRED_TASK_TYPES
    assert TaskType.COMMUNICATION_SEND in APPROVAL_REQUIRED_TASK_TYPES
    assert TaskType.DOCUMENT_READ not in APPROVAL_REQUIRED_TASK_TYPES
    assert TaskType.DATA_EXPORT not in APPROVAL_REQUIRED_TASK_TYPES
