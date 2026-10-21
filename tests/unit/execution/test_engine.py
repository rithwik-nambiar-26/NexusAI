"""Tests for the controlled execution engine."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, Field

from nexusai.app.execution.engine import (
    ApprovalState,
    ExecutionEngine,
    ExecutionStatus,
)
from nexusai.app.execution.registry import (
    RetryPolicy,
    ToolDefinition,
    ToolErrorCategory,
    ToolRegistry,
    ToolRisk,
)
from nexusai.ml.planner.schemas import (
    Plan,
    Task,
    TaskParameter,
    TaskStatus,
    TaskType,
)


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="hello")


class EchoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    echoed: str


class WriteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="data")


def _echo_handler(payload: EchoInput) -> EchoOutput:
    return EchoOutput(echoed=payload.text)


def _write_handler(payload: WriteInput) -> EchoOutput:
    return EchoOutput(echoed=payload.content)


def _exploding_handler(payload: EchoInput) -> EchoOutput:
    raise RuntimeError("boom")


def _flaky_handler(payload: EchoInput) -> EchoOutput:
    # Fails on the first attempt, succeeds afterwards.
    _flaky_handler.calls = getattr(_flaky_handler, "calls", 0) + 1
    if _flaky_handler.calls == 1:
        raise RuntimeError("transient")
    return EchoOutput(echoed=payload.text)


def _tool(capability="test.echo", **overrides) -> ToolDefinition:
    defaults = {
        "capability": capability,
        "description": "Echo the input text",
        "input_schema": EchoInput,
        "output_schema": EchoOutput,
        "handler": _echo_handler,
        "risk": ToolRisk.SAFE,
        "requires_approval": False,
        "timeout_seconds": 5.0,
        "retry_policy": RetryPolicy(max_attempts=1),
        "idempotent": True,
    }
    defaults.update(overrides)
    return ToolDefinition(**defaults)


def _task(task_id="t1", capability="test.echo", deps=None, params=None) -> Task:
    return Task(
        task_id=task_id,
        task_name=f"Task {task_id}",
        description="A test task",
        task_type=TaskType.DOCUMENT_READ,
        expected_output="An echo",
        dependencies=deps or [],
        required_capabilities=[capability] if capability else [],
        input_parameters=params or [],
    )


def _plan(tasks: list[Task], **kwargs) -> Plan:
    plan = Plan(original_request="test request", **kwargs)
    for task in tasks:
        plan.add_task(task)
    for index in range(1, len(plan.tasks)):
        prerequisite = plan.tasks[index - 1].task_id
        dependent = plan.tasks[index].task_id
        if prerequisite not in plan.tasks[index].dependencies:
            plan.tasks[index].dependencies.append(prerequisite)
        pair = (prerequisite, dependent)
        if pair not in plan.dependencies:
            plan.dependencies.append(pair)
    return plan


@pytest.fixture
def registry() -> ToolRegistry:
    """Return a registry with an echo tool."""
    reg = ToolRegistry()
    reg.register(_tool())
    return reg


# ---------------------------------------------------------------------------
# Basic execution
# ---------------------------------------------------------------------------


def test_executes_a_single_task(registry):
    """Test that a task runs and completes."""
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task()]))

    assert report.status == ExecutionStatus.COMPLETED
    assert report.task_results[0].status == TaskStatus.COMPLETED
    assert report.task_results[0].output == {"echoed": "hello"}


def test_unknown_capability_is_skipped(registry):
    """Test that a task with no registered capability is skipped, not run."""
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task(capability="not.registered")]))

    result = report.task_results[0]
    assert result.status == TaskStatus.SKIPPED
    assert result.error_category == ToolErrorCategory.NOT_REGISTERED


def test_task_with_no_capability_is_skipped(registry):
    """Test that a task naming no capability is skipped."""
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task(capability=None)]))
    assert report.task_results[0].status == TaskStatus.SKIPPED


def test_invalid_plan_is_rejected(registry):
    """Test that a plan that does not validate is refused."""
    plan = _plan([_task()])
    plan.dependencies.append(("t1", "ghost"))  # break the plan

    engine = ExecutionEngine(registry)
    report = engine.execute(plan)

    assert report.status == ExecutionStatus.INVALID
    assert report.task_results == []
    assert report.error


def test_cyclic_plan_is_rejected(registry):
    """Test that a cyclic plan is refused."""
    plan = _plan([_task("t1", deps=["t2"]), _task("t2", deps=["t1"])])
    plan.dependencies = [("t1", "t2"), ("t2", "t1")]

    engine = ExecutionEngine(registry)
    report = engine.execute(plan)
    assert report.status == ExecutionStatus.INVALID


# ---------------------------------------------------------------------------
# Dependency handling
# ---------------------------------------------------------------------------


def test_dependency_order_is_respected(registry):
    """Test that tasks run in dependency order."""
    plan = _plan([_task("t1"), _task("t2", deps=["t1"]), _task("t3", deps=["t2"])])
    engine = ExecutionEngine(registry)
    report = engine.execute(plan)

    assert [r.task_id for r in report.task_results] == ["t1", "t2", "t3"]
    assert all(r.status == TaskStatus.COMPLETED for r in report.task_results)


def test_failed_dependency_blocks_dependent(registry):
    """Test that a failed dependency blocks the dependent task."""
    registry.register(_tool("test.fail", handler=_exploding_handler))
    plan = _plan([_task("t1", capability="test.fail"), _task("t2", deps=["t1"])])

    engine = ExecutionEngine(registry)
    report = engine.execute(plan)

    assert report.task_results[0].status == TaskStatus.FAILED
    assert report.task_results[1].status == TaskStatus.BLOCKED
    assert "did not complete" in report.task_results[1].error
    assert report.status == ExecutionStatus.FAILED


def test_skipped_dependency_blocks_dependent(registry):
    """Test that a skipped dependency blocks the dependent task."""
    plan = _plan([_task("t1", capability="not.registered"), _task("t2", deps=["t1"])])

    engine = ExecutionEngine(registry)
    report = engine.execute(plan)

    assert report.task_results[0].status == TaskStatus.SKIPPED
    assert report.task_results[1].status == TaskStatus.BLOCKED


def test_failed_task_is_not_marked_completed(registry):
    """Test that a failed task is never reported as completed."""
    registry.register(_tool("test.fail", handler=_exploding_handler))
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task(capability="test.fail")]))

    result = report.task_results[0]
    assert result.status == TaskStatus.FAILED
    assert result.output is None
    assert result.error_category == ToolErrorCategory.HANDLER_ERROR


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


def _approval_tool(**overrides) -> ToolDefinition:
    defaults = {
        "capability": "test.write",
        "description": "Write something",
        "input_schema": WriteInput,
        "output_schema": EchoOutput,
        "handler": _write_handler,
        "risk": ToolRisk.SENSITIVE,
        "requires_approval": True,
        "timeout_seconds": 5.0,
        "retry_policy": RetryPolicy(max_attempts=1),
        "idempotent": False,
    }
    defaults.update(overrides)
    return ToolDefinition(**defaults)


def test_approval_required_task_waits(registry):
    """Test that an approval-required task does not run without approval."""
    registry.register(_approval_tool())
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task(capability="test.write")]))

    result = report.task_results[0]
    assert result.status == TaskStatus.BLOCKED
    assert result.error_category == ToolErrorCategory.APPROVAL_REQUIRED
    assert report.status == ExecutionStatus.AWAITING_APPROVAL
    assert report.pending_approval_task_ids == [result.task_id]


def test_approval_request_is_raised(registry):
    """Test that an approval request is recorded for a pending task."""
    registry.register(_approval_tool())
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task(capability="test.write")]))

    assert len(report.approvals) == 1
    approval = report.approvals[0]
    assert approval.state == ApprovalState.PENDING
    assert approval.capability == "test.write"
    assert approval.input_fingerprint


def test_granted_approval_allows_execution(registry):
    """Test that a granted approval lets the task run."""
    registry.register(_approval_tool())
    engine = ExecutionEngine(registry)
    plan = _plan([_task(capability="test.write")])

    first = engine.execute(plan)
    assert first.task_results[0].status == TaskStatus.BLOCKED

    engine.approve(first, first.task_results[0].task_id, granted=True)
    assert first.approvals[0].state == ApprovalState.GRANTED

    second = engine.execute(plan, approvals=first.approvals)
    assert second.task_results[0].status == TaskStatus.COMPLETED


def test_denied_approval_skips_the_task(registry):
    """Test that a denied approval prevents the task running."""
    registry.register(_approval_tool())
    engine = ExecutionEngine(registry)
    plan = _plan([_task(capability="test.write")])

    first = engine.execute(plan)
    engine.approve(first, first.task_results[0].task_id, granted=False)
    assert first.approvals[0].state == ApprovalState.DENIED

    second = engine.execute(plan, approvals=first.approvals)
    assert second.task_results[0].status == TaskStatus.SKIPPED


def test_changed_inputs_invalidate_approval(registry):
    """Test that changing the task inputs invalidates a granted approval."""
    registry.register(_approval_tool())
    engine = ExecutionEngine(registry)
    plan = _plan([_task(capability="test.write")])

    first = engine.execute(plan)
    engine.approve(first, first.task_results[0].task_id, granted=True)

    # The task's inputs change after the approval was granted.
    plan.tasks[0].input_parameters = [
        TaskParameter(name="content", value="different data")
    ]

    second = engine.execute(plan, approvals=first.approvals)
    result = second.task_results[0]
    assert result.status == TaskStatus.BLOCKED
    assert result.error_category == ToolErrorCategory.APPROVAL_INVALID
    assert first.approvals[0].state == ApprovalState.INVALIDATED


def test_unchanged_inputs_keep_approval_valid(registry):
    """Test that an unchanged task keeps its approval."""
    registry.register(_approval_tool())
    engine = ExecutionEngine(registry)
    plan = _plan([_task(capability="test.write")])

    first = engine.execute(plan)
    engine.approve(first, first.task_results[0].task_id, granted=True)

    second = engine.execute(plan, approvals=first.approvals)
    assert second.task_results[0].status == TaskStatus.COMPLETED


def test_approval_is_bound_to_the_task(registry):
    """Test that an approval for one task does not authorise another."""
    registry.register(_approval_tool())
    engine = ExecutionEngine(registry)
    plan = _plan([_task("t1", capability="test.write"), _task("t2", capability="test.write")])

    first = engine.execute(plan)
    engine.approve(first, "t1", granted=True)

    second = engine.execute(plan, approvals=first.approvals)
    statuses = {r.task_id: r.status for r in second.task_results}
    assert statuses["t1"] == TaskStatus.COMPLETED
    assert statuses["t2"] == TaskStatus.BLOCKED


def test_destructive_tool_is_never_executed(registry):
    """Test that a destructive tool is skipped even when registered."""
    registry.register(
        _approval_tool(capability="test.destroy", risk=ToolRisk.DESTRUCTIVE)
    )
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task(capability="test.destroy")]))

    result = report.task_results[0]
    assert result.status == TaskStatus.SKIPPED
    assert result.error_category == ToolErrorCategory.PERMISSION_DENIED


# ---------------------------------------------------------------------------
# Retries and timeouts
# ---------------------------------------------------------------------------


def test_bounded_retry_on_transient_failure(registry):
    """Test that a transient failure is retried up to the policy limit."""
    registry.register(
        _tool(
            "test.flaky",
            handler=_flaky_handler,
            retry_policy=RetryPolicy(max_attempts=3),
        )
    )
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task(capability="test.flaky")]))

    result = report.task_results[0]
    assert result.status == TaskStatus.COMPLETED
    assert result.attempts == 2


def test_retries_are_bounded(registry):
    """Test that retries stop at the configured maximum."""
    def always_failing(payload: EchoInput) -> EchoOutput:
        raise RuntimeError("boom")

    registry.register(
        _tool(
            "test.always_fails",
            handler=always_failing,
            retry_policy=RetryPolicy(max_attempts=2),
        )
    )
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task(capability="test.always_fails")]))

    result = report.task_results[0]
    assert result.status == TaskStatus.FAILED
    assert result.attempts == 2


def test_non_idempotent_tool_is_not_retried(registry):
    """Test that a non-idempotent tool is never retried."""
    calls = {"count": 0}

    def failing_write(payload: WriteInput) -> EchoOutput:
        calls["count"] += 1
        raise RuntimeError("boom")

    registry.register(
        _tool(
            "test.write.fail",
            input_schema=WriteInput,
            handler=failing_write,
            idempotent=False,
            retry_policy=RetryPolicy(max_attempts=3),
        )
    )
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task(capability="test.write.fail")]))

    assert report.task_results[0].attempts == 1
    assert calls["count"] == 1


def test_timeout_is_reported(registry):
    """Test that a handler timeout is reported as a failure."""
    def timing_out(payload: EchoInput) -> EchoOutput:
        raise TimeoutError

    registry.register(_tool("test.slow", handler=timing_out))
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task(capability="test.slow")]))

    result = report.task_results[0]
    assert result.status == TaskStatus.FAILED
    assert result.error_category == ToolErrorCategory.TIMEOUT


# ---------------------------------------------------------------------------
# Duplicate execution
# ---------------------------------------------------------------------------


def test_duplicate_execution_is_skipped(registry):
    """Test that running the same plan twice does not repeat a task."""
    engine = ExecutionEngine(registry)
    plan = _plan([_task()])

    first = engine.execute(plan)
    assert first.task_results[0].status == TaskStatus.COMPLETED

    second = engine.execute(plan)
    assert second.task_results[0].status == TaskStatus.SKIPPED
    assert second.task_results[0].error_category == ToolErrorCategory.SKIPPED


def test_reset_clears_execution_state(registry):
    """Test that reset allows a task to run again."""
    engine = ExecutionEngine(registry)
    plan = _plan([_task()])
    engine.execute(plan)
    engine.reset()
    report = engine.execute(plan)
    assert report.task_results[0].status == TaskStatus.COMPLETED


def test_has_run_reports_state(registry):
    """Test the execution-state query."""
    engine = ExecutionEngine(registry)
    plan = _plan([_task()])
    assert engine.has_run(plan.plan_id, "t1") is False
    engine.execute(plan)
    assert engine.has_run(plan.plan_id, "t1") is True


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def test_report_records_identifiers(registry):
    """Test that the report carries execution and plan identifiers."""
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task()]))
    assert report.execution_id.startswith("exec_")
    assert report.plan_id
    assert report.started_at
    assert report.completed_at
    assert report.elapsed_seconds >= 0


def test_partially_completed_when_some_tasks_skipped(registry):
    """Test the overall status when some tasks were skipped."""
    engine = ExecutionEngine(registry)
    report = engine.execute(
        _plan([_task("t1"), _task("t2", capability="not.registered")])
    )
    assert report.status == ExecutionStatus.PARTIALLY_COMPLETED


def test_awaiting_approval_status(registry):
    """Test the overall status when a task awaits approval."""
    registry.register(_approval_tool())
    engine = ExecutionEngine(registry)
    report = engine.execute(_plan([_task(capability="test.write")]))
    assert report.status == ExecutionStatus.AWAITING_APPROVAL
