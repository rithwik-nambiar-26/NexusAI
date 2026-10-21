"""Controlled execution of a validated plan.

The executor walks a plan's execution order and runs each task through
the tool registry. It is deliberately conservative:

* a plan that does not validate is rejected outright;
* a task whose capability is not registered is skipped, not attempted;
* a task whose dependency failed or was skipped is blocked, not run;
* a task whose tool requires approval waits for an explicit approval that
  is bound to the task *and* its validated inputs;
* a task is never marked completed unless its handler returned and the
  output validated;
* a failed task is never silently retried unless the tool declares itself
  idempotent and the retry policy allows it.

The executor does not verify the *correctness* of a result — that is the
Day 6 verifier's job. It verifies that a result is well-formed and that
the safety policy was respected.
"""

from __future__ import annotations

import hashlib
import json
import time
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from nexusai.app.core.logging import get_logger
from nexusai.app.execution.derivation import derive_tool_inputs
from nexusai.app.execution.registry import (
    RetryPolicy,
    ToolDefinition,
    ToolError,
    ToolErrorCategory,
    ToolRegistry,
    ToolRisk,
)
from nexusai.ml.planner.schemas import Plan, Task, TaskStatus

logger = get_logger("execution.engine")


class ExecutionStatus(StrEnum):
    """Overall status of an execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_COMPLETED = "partially_completed"
    AWAITING_APPROVAL = "awaiting_approval"
    BLOCKED = "blocked"
    INVALID = "invalid"


class ApprovalState(StrEnum):
    """State of an approval request."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    INVALIDATED = "invalidated"


class ApprovalRequest(BaseModel):
    """A request for explicit approval of one task.

    The approval is bound to a fingerprint of the task's validated inputs.
    If the inputs change after approval, the fingerprint no longer
    matches and the approval is invalidated.
    """

    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(default_factory=lambda: f"appr_{uuid4().hex[:12]}")
    execution_id: str
    task_id: str
    capability: str
    reason: str
    input_fingerprint: str = Field(
        ..., description="Fingerprint of the validated inputs the approval covers"
    )
    state: ApprovalState = Field(default=ApprovalState.PENDING)
    granted_at: str | None = None
    decided_at: str | None = None
    note: str | None = None


class TaskExecutionResult(BaseModel):
    """The outcome of running one task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    capability: str | None = None
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    output: dict[str, Any] | None = None
    error: str | None = None
    error_category: ToolErrorCategory | None = None
    attempts: int = 0
    elapsed_seconds: float = 0.0
    approval_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class ExecutionReport(BaseModel):
    """The outcome of executing a plan."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str = Field(default_factory=lambda: f"exec_{uuid4().hex[:12]}")
    plan_id: str
    intent: str | None = None
    original_request: str = ""
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING)
    task_results: list[TaskExecutionResult] = Field(default_factory=list)
    approvals: list[ApprovalRequest] = Field(default_factory=list)
    pending_approval_task_ids: list[str] = Field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None
    elapsed_seconds: float = 0.0
    error: str | None = None


def _fingerprint(capability: str, payload: dict[str, Any]) -> str:
    """Return a stable fingerprint of a capability and its inputs.

    The fingerprint is what binds an approval to a specific set of
    inputs. Any change to the inputs changes the fingerprint and
    invalidates a previously granted approval.
    """
    canonical = json.dumps(
        {"capability": capability, "payload": payload},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ExecutionEngine:
    """Executes a validated plan through the tool registry.

    Args:
        registry: The registry supplying the executable capabilities.
        max_attempts_override: When set, replaces each tool's own retry
            policy maximum. Used to bound a whole run.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        max_attempts_override: int | None = None,
    ) -> None:
        self._registry = registry
        self._max_attempts_override = max_attempts_override
        # Tasks that have already run, so a second execution of the same
        # plan does not repeat a side effect.
        self._completed: dict[str, str] = {}
        # Task ids skipped in this run because the chain had already run.
        self._already_run: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def execute(
        self,
        plan: Plan,
        approvals: list[ApprovalRequest] | None = None,
    ) -> ExecutionReport:
        """Execute a plan.

        Args:
            plan: The plan to execute. It must validate.
            approvals: Approval decisions to apply. An approval must match
                the task and the validated inputs it was granted for.

        Returns:
            An :class:`ExecutionReport` describing what ran.
        """
        execution_id = f"exec_{uuid4().hex[:12]}"
        # The already-run set is per execution.
        self._already_run = set()
        report = ExecutionReport(
            execution_id=execution_id,
            plan_id=plan.plan_id,
            intent=plan.intent,
            original_request=plan.original_request,
        )

        errors = plan.validate()
        if errors:
            report.status = ExecutionStatus.INVALID
            report.error = "; ".join(errors)
            report.completed_at = _now()
            logger.warning(
                "Execution refused: plan did not validate",
                extra={"execution_id": execution_id, "errors": errors},
            )
            return report

        granted = self._index_approvals(approvals or [])
        report.approvals = list(granted.values())

        order = plan.execution_order or [task.task_id for task in plan.tasks]
        tasks_by_id = {task.task_id: task for task in plan.tasks}

        report.status = ExecutionStatus.RUNNING
        report.started_at = _now()
        started = time.monotonic()

        for task_id in order:
            task = tasks_by_id.get(task_id)
            if task is None:
                continue

            result = self._execute_task(task, plan, granted, execution_id, report)
            report.task_results.append(result)

            if result.approval_id:
                report.pending_approval_task_ids.append(task.task_id)

        report.elapsed_seconds = time.monotonic() - started
        report.completed_at = _now()
        report.status = self._overall_status(report)
        report.pending_approval_task_ids = [
            result.task_id
            for result in report.task_results
            if result.status == TaskStatus.BLOCKED
            and result.error_category == ToolErrorCategory.APPROVAL_REQUIRED
        ]

        logger.info(
            "Plan execution finished",
            extra={
                "execution_id": execution_id,
                "plan_id": plan.plan_id,
                "status": report.status.value,
                "tasks": len(report.task_results),
            },
        )
        return report

    def approve(
        self,
        report: ExecutionReport,
        task_id: str,
        granted: bool = True,
        note: str | None = None,
    ) -> ExecutionReport:
        """Record an approval decision for a task awaiting approval.

        The decision is recorded against the task's input fingerprint, so
        it only authorises the inputs that were pending when the request
        was raised.
        """
        for approval in report.approvals:
            if approval.task_id != task_id:
                continue
            if approval.state != ApprovalState.PENDING:
                continue
            approval.state = ApprovalState.GRANTED if granted else ApprovalState.DENIED
            approval.decided_at = _now()
            approval.granted_at = approval.decided_at if granted else None
            approval.note = note
            logger.info(
                "Approval decision recorded",
                extra={
                    "execution_id": report.execution_id,
                    "task_id": task_id,
                    "granted": granted,
                },
            )
            return report
        return report

    def has_run(self, plan_id: str, task_id: str) -> bool:
        """Return True when a task has already been executed for a plan."""
        return self._completed.get(f"{plan_id}:{task_id}") is not None

    def reset(self) -> None:
        """Forget which tasks have run."""
        self._completed.clear()
        self._already_run.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _index_approvals(
        approvals: list[ApprovalRequest],
    ) -> dict[str, ApprovalRequest]:
        """Index approvals by task id."""
        return {approval.task_id: approval for approval in approvals}

    def _execute_task(
        self,
        task: Task,
        plan: Plan,
        approvals: dict[str, ApprovalRequest],
        execution_id: str,
        report: ExecutionReport | None = None,
    ) -> TaskExecutionResult:
        """Execute one task."""
        result = TaskExecutionResult(task_id=task.task_id)

        # --- duplicate execution protection -----------------------------
        run_key = f"{plan.plan_id}:{task.task_id}"
        if run_key in self._completed:
            result.status = TaskStatus.SKIPPED
            result.error = "Task has already been executed for this plan"
            result.error_category = ToolErrorCategory.SKIPPED
            self._already_run.add(task.task_id)
            return result

        # --- dependency check --------------------------------------------
        blocked_by, dependency_already_ran = self._dependency_state(task, plan)
        if dependency_already_ran:
            # A dependency was skipped because the chain had already run,
            # so this task is skipped too rather than blocked.
            result.status = TaskStatus.SKIPPED
            result.error = "Skipped: an upstream task had already been executed"
            result.error_category = ToolErrorCategory.SKIPPED
            self._already_run.add(task.task_id)
            task.status = TaskStatus.SKIPPED
            return result
        if blocked_by:
            result.status = TaskStatus.BLOCKED
            result.error = f"Blocked: dependency '{blocked_by}' did not complete"
            result.error_category = ToolErrorCategory.BLOCKED
            task.status = TaskStatus.BLOCKED
            return result

        # --- capability lookup ------------------------------------------
        capability = self._capability_for(task)
        if capability is None:
            result.status = TaskStatus.SKIPPED
            result.error = "No registered capability satisfies this task"
            result.error_category = ToolErrorCategory.NOT_REGISTERED
            task.status = TaskStatus.SKIPPED
            return result

        result.capability = capability

        try:
            tool = self._registry.get(capability)
        except ToolError as exc:
            result.status = TaskStatus.SKIPPED
            result.error = str(exc)
            result.error_category = exc.category
            task.status = TaskStatus.SKIPPED
            return result

        # --- destructive tools are never executed ------------------------
        if tool.risk == ToolRisk.DESTRUCTIVE:
            result.status = TaskStatus.SKIPPED
            result.error = (
                f"Capability '{capability}' is classified as destructive and is "
                "not executable by the current engine"
            )
            result.error_category = ToolErrorCategory.PERMISSION_DENIED
            task.status = TaskStatus.SKIPPED
            return result

        # --- input preparation ------------------------------------------
        payload = self._payload_for(task, tool, plan.original_request)

        try:
            validated_input = tool.validate_input(payload)
        except ToolError as exc:
            result.status = TaskStatus.FAILED
            result.error = str(exc)
            result.error_category = exc.category
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            return result

        fingerprint = _fingerprint(capability, validated_input.model_dump())

        # --- approval check ----------------------------------------------
        if tool.requires_approval:
            approval = self._resolve_approval(
                task, capability, fingerprint, approvals, execution_id, report
            )
            if approval is None:
                result.status = TaskStatus.BLOCKED
                result.error = "Awaiting explicit approval"
                result.error_category = ToolErrorCategory.APPROVAL_REQUIRED
                task.status = TaskStatus.BLOCKED
                return result
            if approval.state == ApprovalState.INVALIDATED:
                result.status = TaskStatus.BLOCKED
                result.error = (
                    "The approval no longer matches the task's inputs and "
                    "must be granted again"
                )
                result.error_category = ToolErrorCategory.APPROVAL_INVALID
                task.status = TaskStatus.BLOCKED
                return result
            if approval.state == ApprovalState.DENIED:
                result.status = TaskStatus.SKIPPED
                result.error = "The operation was denied"
                result.error_category = ToolErrorCategory.APPROVAL_REQUIRED
                task.status = TaskStatus.SKIPPED
                return result
            result.approval_id = approval.approval_id

        # --- execution ----------------------------------------------------
        task.status = TaskStatus.RUNNING
        result.started_at = _now()

        policy = self._effective_policy(tool)
        attempts = 0
        last_error: ToolError | None = None

        while attempts < policy.max_attempts:
            attempts += 1
            try:
                output, elapsed = self._registry.execute(
                    capability,
                    validated_input.model_dump(),
                    execution_id=execution_id,
                )
            except ToolError as exc:
                last_error = exc
                if not self._should_retry(exc, policy, tool, attempts):
                    break
                if policy.backoff_seconds:
                    time.sleep(policy.backoff_seconds)
                continue

            result.attempts = attempts
            result.elapsed_seconds = elapsed
            result.output = output.model_dump()
            result.status = TaskStatus.COMPLETED
            result.completed_at = _now()
            task.status = TaskStatus.COMPLETED
            task.result = json.dumps(result.output, default=str)
            self._completed[run_key] = result.output.get("status", "completed")
            return result

        # --- failure -------------------------------------------------------
        assert last_error is not None
        result.attempts = attempts
        result.status = TaskStatus.FAILED
        result.error = str(last_error)
        result.error_category = last_error.category
        result.completed_at = _now()
        task.status = TaskStatus.FAILED
        task.error = str(last_error)
        return result

    def _dependency_state(
        self,
        task: Task,
        plan: Plan,
    ) -> tuple[str | None, bool]:
        """Report the state of a task's dependencies.

        Returns:
            A tuple of (blocking dependency id or None, whether an
            upstream task was skipped because the chain had already run).
        """
        for dependency in task.dependencies:
            dependency_task = plan.get_task(dependency)
            if dependency_task is None:
                return dependency, False
            if dependency in self._already_run:
                return dependency, True
            if dependency_task.status == TaskStatus.SKIPPED:
                # Skipped for some other reason (an unregistered
                # capability, say), so the dependent is blocked.
                return dependency, False
            if dependency_task.status != TaskStatus.COMPLETED:
                return dependency, False
        return None, False

    @staticmethod
    def _capability_for(task: Task) -> str | None:
        """Return the capability a task will use.

        A task names the capabilities it needs. The executor uses the
        first one that is registered; a task with no registered capability
        is skipped rather than attempted.
        """
        for capability in task.required_capabilities:
            if capability:
                return capability
        return task.assigned_tool

    @staticmethod
    def _payload_for(
        task: Task,
        tool: ToolDefinition,
        request: str = "",
    ) -> dict[str, Any]:
        """Build the tool input payload from a task's parameters.

        The task's declared input parameters are mapped onto the tool's
        input schema by name. A parameter the schema does not know is
        dropped. Inputs the task does not declare are derived from the
        plan's own request text where the capability needs them.
        """
        known = set(tool.input_schema.model_fields)
        payload: dict[str, Any] = {}
        for parameter in task.input_parameters:
            if parameter.name in known:
                payload[parameter.name] = parameter.value

        return derive_tool_inputs(tool.capability, request, payload)

    def _resolve_approval(
        self,
        task: Task,
        capability: str,
        fingerprint: str,
        approvals: dict[str, ApprovalRequest],
        execution_id: str,
        report: ExecutionReport | None = None,
    ) -> ApprovalRequest | None:
        """Return the approval covering this task and its inputs.

        Returns ``None`` when no approval has been requested yet, and an
        approval whose state is ``INVALIDATED`` when the inputs changed
        after the approval was granted.
        """
        existing = approvals.get(task.task_id)

        if existing is None:
            request = ApprovalRequest(
                execution_id=execution_id,
                task_id=task.task_id,
                capability=capability,
                reason=(
                    f"Task '{task.task_name}' performs an operation that "
                    "requires explicit approval"
                ),
                input_fingerprint=fingerprint,
                state=ApprovalState.PENDING,
            )
            approvals[task.task_id] = request
            if report is not None and request not in report.approvals:
                report.approvals.append(request)
            return None

        if existing.state == ApprovalState.GRANTED:
            if existing.input_fingerprint != fingerprint:
                existing.state = ApprovalState.INVALIDATED
                existing.note = (
                    "The task inputs changed after approval was granted"
                )
                logger.warning(
                    "Approval invalidated: task inputs changed",
                    extra={
                        "execution_id": execution_id,
                        "task_id": task.task_id,
                    },
                )
                return existing
            return existing

        return existing

    def _effective_policy(self, tool: ToolDefinition) -> RetryPolicy:
        """Return the retry policy to use for a tool."""
        if self._max_attempts_override is not None:
            return RetryPolicy(
                max_attempts=self._max_attempts_override,
                backoff_seconds=tool.retry_policy.backoff_seconds,
                retry_on_timeout=tool.retry_policy.retry_on_timeout,
            )
        return tool.retry_policy

    @staticmethod
    def _should_retry(
        error: ToolError,
        policy: RetryPolicy,
        tool: ToolDefinition,
        attempts: int,
    ) -> bool:
        """Decide whether a failed attempt may be retried.

        A non-idempotent tool is never retried: repeating a write or a
        send could duplicate a side effect.
        """
        if attempts >= policy.max_attempts:
            return False
        if not tool.idempotent:
            return False
        if error.category == ToolErrorCategory.TIMEOUT:
            return policy.retry_on_timeout
        return error.category == ToolErrorCategory.HANDLER_ERROR

    @staticmethod
    def _overall_status(report: ExecutionReport) -> ExecutionStatus:
        """Derive the overall status from the task results."""
        results = report.task_results
        if not results:
            return ExecutionStatus.COMPLETED

        statuses = [result.status for result in results]

        # A task that is waiting for an approval is blocked, but the run as
        # a whole is awaiting a decision rather than simply blocked. The
        # error category is the marker: a blocked task with
        # APPROVAL_REQUIRED is waiting for a human.
        awaiting = [
            result
            for result in results
            if result.status == TaskStatus.BLOCKED
            and result.error_category == ToolErrorCategory.APPROVAL_REQUIRED
        ]
        if awaiting:
            return ExecutionStatus.AWAITING_APPROVAL

        # A failure dominates: the dependent tasks are blocked *because*
        # of it, so the run as a whole failed.
        if any(s == TaskStatus.FAILED for s in statuses):
            if any(s == TaskStatus.COMPLETED for s in statuses):
                return ExecutionStatus.PARTIALLY_COMPLETED
            return ExecutionStatus.FAILED

        if any(s == TaskStatus.BLOCKED for s in statuses):
            return ExecutionStatus.BLOCKED

        if all(s == TaskStatus.COMPLETED for s in statuses):
            return ExecutionStatus.COMPLETED

        if any(s == TaskStatus.SKIPPED for s in statuses):
            # Every task that did not run was skipped because it had
            # already run, so the work is done. A task skipped for any
            # other reason leaves the run partial.
            if all(
                result.error_category == ToolErrorCategory.SKIPPED
                for result in results
                if result.status == TaskStatus.SKIPPED
            ):
                return ExecutionStatus.COMPLETED
            return ExecutionStatus.PARTIALLY_COMPLETED

        return ExecutionStatus.COMPLETED


def _now() -> str:
    """Return the current UTC time as an ISO string."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
