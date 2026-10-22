"""API schemas for planner endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nexusai.ml.planner.schemas import Plan, PlanStatus, TaskStatus


class PlanRequest(BaseModel):
    """Request to create a plan."""

    text: str = Field(..., min_length=1, max_length=2000, description="Natural-language user request")
    intent: str | None = Field(default=None, description="Optional explicit intent category")
    entities: dict[str, Any] | None = Field(default=None, description="Extracted entities from request")
    source: str = Field(default="classifier", description="Source of intent: 'classifier' or 'explicit'")
    intent_status: str | None = Field(
        default=None,
        description=(
            "Status of the intent classification, when the intent came from "
            "the classifier. A status of 'clarification_required' makes the "
            "planner ask for clarification rather than plan."
        ),
    )
    intent_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence of the intent classification",
    )


class PlanResponse(BaseModel):
    """Response for plan creation endpoint."""

    plan: Plan
    request_id: str = Field(..., description="Correlation ID for this request")


class PlanStatusResponse(BaseModel):
    """Response for plan status endpoint."""

    plan_id: str
    status: PlanStatus
    request_id: str = Field(..., description="Correlation ID for this request")


class TaskStatusUpdate(BaseModel):
    """Request to update task status."""

    task_id: str = Field(..., description="Task ID to update")
    status: TaskStatus = Field(..., description="New task status")
    result: str | None = Field(default=None, description="Task result if completed")
    error: str | None = Field(default=None, description="Error message if failed")
