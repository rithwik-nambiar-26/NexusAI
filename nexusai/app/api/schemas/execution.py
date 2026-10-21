"""API schemas for the execution engine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nexusai.app.execution.engine import (
    ApprovalRequest,
    ExecutionReport,
    ExecutionStatus,
    TaskExecutionResult,
)
from nexusai.app.execution.registry import ToolInfo


class ExecutePlanRequest(BaseModel):
    """Request to execute a plan."""

    plan: dict[str, Any] = Field(
        ..., description="The plan to execute, as produced by the planner"
    )
    approvals: list[ApprovalRequest] = Field(
        default_factory=list,
        description="Approval decisions to apply before execution",
    )


class ExecutePlanResponse(BaseModel):
    """Response for a plan execution request."""

    report: ExecutionReport
    request_id: str = Field(..., description="Correlation ID for this request")
    run_id: int | None = Field(
        default=None, description="Identifier of the persisted workflow run, if any"
    )


class ApprovalDecisionRequest(BaseModel):
    """Request to approve or deny a task awaiting approval."""

    task_id: str = Field(..., description="Task whose approval is being decided")
    granted: bool = Field(default=True, description="Whether the operation is approved")
    note: str | None = Field(default=None, description="Optional note recorded with the decision")


class ApprovalDecisionResponse(BaseModel):
    """Response for an approval decision."""

    report: ExecutionReport
    request_id: str = Field(..., description="Correlation ID for this request")


class ToolListResponse(BaseModel):
    """Response listing the registered tools."""

    tools: list[ToolInfo]
    count: int = Field(..., description="Number of registered tools")
    request_id: str = Field(..., description="Correlation ID for this request")


class ExecutionStatusResponse(BaseModel):
    """Response for the execution status endpoint."""

    available: bool
    registered_capabilities: list[str]
    request_id: str = Field(..., description="Correlation ID for this request")


__all__ = [
    "ApprovalDecisionRequest",
    "ApprovalDecisionResponse",
    "ExecutePlanRequest",
    "ExecutePlanResponse",
    "ExecutionStatus",
    "ExecutionStatusResponse",
    "TaskExecutionResult",
    "ToolListResponse",
]
