"""Pydantic schemas for structured planning and task decomposition."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from nexusai.ml.planner.dependencies import resolve_dependencies


class TaskType(StrEnum):
    """Task type categories for planning."""

    # Document operations
    DOCUMENT_READ = "document_read"
    DOCUMENT_WRITE = "document_write"
    DOCUMENT_EXTRACT = "document_extract"
    DOCUMENT_TRANSFORM = "document_transform"
    DOCUMENT_SUMMARISE = "document_summarise"

    # Data operations
    DATA_LOAD = "data_load"
    DATA_ANALYSE = "data_analyse"
    DATA_FILTER = "data_filter"
    DATA_AGGREGATE = "data_aggregate"
    DATA_EXPORT = "data_export"

    # Research operations
    RESEARCH_QUERY = "research_query"
    RESEARCH_FETCH = "research_fetch"
    RESEARCH_EXTRACT = "research_extract"
    RESEARCH_SYNTHESISE = "research_synthesise"

    # Communication operations
    COMMUNICATION_SEND = "communication_send"
    COMMUNICATION_DRAFT = "communication_draft"

    # Verification
    VERIFY_CONTENT = "verify_content"
    VERIFY_CALCULATION = "verify_calculation"

    # Fallback
    CUSTOM = "custom"


#: Task types the planner is allowed to emit. A task type outside this set
#: is rejected during plan validation, so a malformed or unsupported
#: operation cannot enter a plan unnoticed.
SUPPORTED_TASK_TYPES: frozenset[TaskType] = frozenset(
    {
        TaskType.DOCUMENT_READ,
        TaskType.DOCUMENT_WRITE,
        TaskType.DOCUMENT_EXTRACT,
        TaskType.DOCUMENT_TRANSFORM,
        TaskType.DOCUMENT_SUMMARISE,
        TaskType.DATA_LOAD,
        TaskType.DATA_ANALYSE,
        TaskType.DATA_FILTER,
        TaskType.DATA_AGGREGATE,
        TaskType.DATA_EXPORT,
        TaskType.RESEARCH_QUERY,
        TaskType.RESEARCH_FETCH,
        TaskType.RESEARCH_EXTRACT,
        TaskType.RESEARCH_SYNTHESISE,
        TaskType.COMMUNICATION_SEND,
        TaskType.COMMUNICATION_DRAFT,
        TaskType.VERIFY_CONTENT,
        TaskType.VERIFY_CALCULATION,
    }
)

#: Task types that mutate state and therefore require explicit approval
#: before they may be executed. Reporting a computed result is not a state
#: change, so ``DATA_EXPORT`` is deliberately excluded: in the data-analysis
#: template it renders the answer rather than writing a file.
APPROVAL_REQUIRED_TASK_TYPES: frozenset[TaskType] = frozenset(
    {
        TaskType.DOCUMENT_WRITE,
        TaskType.COMMUNICATION_SEND,
    }
)


class TaskStatus(StrEnum):
    """Task execution status."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class PlanStatus(StrEnum):
    """Overall plan status."""

    DRAFT = "draft"
    VALIDATED = "validated"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    INVALID = "invalid"


class TaskParameter(BaseModel):
    """Parameter for a task."""

    name: str = Field(..., description="Parameter name")
    value: Any = Field(..., description="Parameter value")
    description: str | None = Field(default=None, description="Parameter description")
    required: bool = Field(default=True, description="Whether this parameter is required")


class Task(BaseModel):
    """A single task in a plan."""

    task_id: str = Field(default_factory=lambda: f"task_{uuid4().hex[:8]}")
    task_name: str = Field(..., description="Human-readable task name")
    description: str = Field(..., description="Detailed task description")
    task_type: TaskType = Field(..., description="Task type category")
    input_parameters: list[TaskParameter] = Field(
        default_factory=list, description="Input parameters for the task"
    )
    expected_output: str = Field(..., description="Description of expected output")
    dependencies: list[str] = Field(
        default_factory=list, description="List of task_ids this task depends on"
    )
    required_capabilities: list[str] = Field(
        default_factory=list, description="Required capabilities/tools for this task"
    )
    verification_criteria: str | None = Field(
        default=None, description="Criteria for verifying task completion"
    )
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Task execution status")
    assigned_tool: str | None = Field(
        default=None, description="Specific tool assigned to execute this task"
    )
    result: str | None = Field(default=None, description="Task execution result")
    error: str | None = Field(default=None, description="Error message if failed")

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("task_id cannot be empty")
        return v.strip()


class Plan(BaseModel):
    """A structured execution plan."""

    plan_id: str = Field(default_factory=lambda: f"plan_{uuid4().hex[:8]}")
    original_request: str = Field(..., description="Original user request")
    intent: str | None = Field(default=None, description="Classified intent category")
    plan_status: PlanStatus = Field(default=PlanStatus.DRAFT, description="Plan validation status")
    tasks: list[Task] = Field(default_factory=list, description="Ordered list of tasks")
    dependencies: list[tuple[str, str]] = Field(
        default_factory=list,
        description="List of (from_task_id, to_task_id) dependency pairs",
    )
    execution_order: list[str] = Field(
        default_factory=list, description="Topologically sorted task execution order"
    )
    parallel_levels: list[list[str]] = Field(
        default_factory=list,
        description="Groups of task ids that could run concurrently (not executed in Day 3)",
    )
    missing_information: list[str] = Field(
        default_factory=list,
        description="Information required by the plan that the request did not supply",
    )
    unsupported_operations: list[str] = Field(
        default_factory=list,
        description="Operations requested that the planner cannot support",
    )
    clarification_required: bool = Field(
        default=False, description="Whether user clarification is needed before execution"
    )
    clarification_question: str | None = Field(
        default=None, description="Question to ask user for clarification"
    )
    validation_errors: list[str] = Field(
        default_factory=list, description="Validation errors found during plan creation"
    )
    requires_approval: bool = Field(
        default=False, description="Whether plan contains operations requiring approval"
    )
    approval_reasons: list[str] = Field(
        default_factory=list, description="Reasons why approval is required"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Plan creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update timestamp"
    )
    source: str = Field(
        default="classifier", description="Source of intent: 'classifier' or 'explicit'"
    )

    def add_task(self, task: Task) -> None:
        """Add a task to the plan."""
        # Check for duplicate task_id
        if any(t.task_id == task.task_id for t in self.tasks):
            raise ValueError(f"Task with id {task.task_id} already exists")
        self.tasks.append(task)
        self.updated_at = datetime.now(UTC)

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None

    def validate(self) -> list[str]:
        """Validate the plan and return list of errors.

        Structural validation covers duplicate task ids, missing dependency
        references, self-dependencies and dependency cycles. The execution
        order and parallel levels are recomputed from the resolved graph.
        """
        errors: list[str] = []

        if not self.tasks:
            errors.append("Plan must contain at least one task")
            return errors

        task_ids = [t.task_id for t in self.tasks]

        # Resolve the dependency graph (duplicates, missing refs, self-deps, cycles).
        report = resolve_dependencies(task_ids, self.dependencies)
        errors.extend(report.errors)

        # Recompute execution order and parallel levels from the resolved graph.
        if report.is_valid:
            self.execution_order = report.execution_order
            self.parallel_levels = report.parallel_levels
        else:
            self.execution_order = []
            self.parallel_levels = []

        # A supplied execution order must name every task exactly once.
        if self.execution_order and len(self.execution_order) != len(set(self.execution_order)):
            errors.append("execution_order must contain each task id exactly once")

        # Task-level dependency references must also be resolvable.
        for task in self.tasks:
            for dependency in task.dependencies:
                if dependency not in set(task_ids):
                    errors.append(
                        f"Task '{task.task_id}' depends on unknown task: {dependency}"
                    )
                elif dependency == task.task_id:
                    errors.append(f"Task '{task.task_id}' depends on itself")

        # Unsupported task types are rejected: a plan may only contain
        # task types this planner knows how to produce.
        for task in self.tasks:
            if task.task_type not in SUPPORTED_TASK_TYPES:
                errors.append(f"Unsupported task type: {task.task_type}")

        return errors

    def get_ready_tasks(self) -> list[Task]:
        """Get tasks that are ready to execute (all dependencies completed)."""
        ready = []
        for task in self.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            # Check if all dependencies are completed
            deps_done = all(
                self.get_task(dep_id) and self.get_task(dep_id).status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
            )
            if deps_done:
                ready.append(task)
        return ready

    def mark_task_completed(self, task_id: str, result: str | None = None) -> bool:
        """Mark a task as completed."""
        task = self.get_task(task_id)
        if not task:
            return False
        task.status = TaskStatus.COMPLETED
        if result:
            task.result = result
        self.updated_at = datetime.now(UTC)
        return True

    def mark_task_failed(self, task_id: str, error: str) -> bool:
        """Mark a task as failed."""
        task = self.get_task(task_id)
        if not task:
            return False
        task.status = TaskStatus.FAILED
        task.error = error
        self.updated_at = datetime.now(UTC)
        return True
