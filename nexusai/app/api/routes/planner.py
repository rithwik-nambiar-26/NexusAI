"""Planning API routes.

The planner consumes an intent classification result. When the caller does
not supply an intent explicitly, the route classifies the request with the
Day 2 intent service and forwards the structured result, including its
status and confidence, to the planner.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from nexusai.app.api.dependencies import get_app_settings
from nexusai.app.api.schemas.planner import (
    PlanRequest,
    PlanResponse,
    PlanStatusResponse,
    TaskStatusUpdate,
)
from nexusai.app.config import Settings
from nexusai.app.core.context import get_request_id
from nexusai.app.core.exceptions import ServiceUnavailableError
from nexusai.app.services.intent import get_intent_service
from nexusai.ml.planner.service import create_plan
from nexusai.ml.schemas import IntentClassificationRequest

router = APIRouter(prefix="/api/v1/planner", tags=["planner"])


@router.post(
    "/plan",
    response_model=PlanResponse,
    summary="Create a structured plan",
    description=(
        "Create a structured execution plan from a natural-language request. "
        "The request is classified with the intent classifier unless an intent "
        "is supplied explicitly, then decomposed into typed tasks with an "
        "explicit dependency graph and a validated execution order. "
        "This endpoint plans; it does not execute."
    ),
)
def create_plan_endpoint(
    request: Request,
    payload: PlanRequest,
    settings: Settings = Depends(get_app_settings),
) -> PlanResponse:
    """Create a structured execution plan for a natural-language request."""
    intent = payload.intent
    intent_confidence = 0.0
    intent_status = "confident"
    entities = payload.entities or {}
    source = payload.source

    if intent is None:
        # Resolve the intent through the Day 2 classifier and forward its
        # structured result. A low-confidence or failed classification is
        # passed through untouched so the planner can decline to plan.
        intent_service = get_intent_service()
        if not intent_service.is_available():
            raise ServiceUnavailableError(
                "Intent classifier not trained. Run 'python nexusai/ml/train.py' first, "
                "or supply an explicit intent.",
                code="model_unavailable",
            )

        classification = intent_service.classify(
            IntentClassificationRequest(text=payload.text, context=payload.entities)
        )
        intent = (
            classification.predicted_intent.value if classification.predicted_intent else None
        )
        intent_confidence = classification.confidence
        intent_status = classification.status.value
        entities = {**classification.entities, **(payload.entities or {})}
        source = "classifier"

    plan, _warnings = create_plan(
        request=payload.text,
        intent=intent,
        intent_confidence=intent_confidence,
        intent_status=intent_status,
        entities=entities,
        source=source,
    )

    return PlanResponse(
        plan=plan,
        request_id=get_request_id(),
    )


@router.get(
    "/status",
    response_model=PlanStatusResponse,
    summary="Get planner status",
    description="Check whether the planner service is available.",
)
def planner_status(
    settings: Settings = Depends(get_app_settings),
) -> PlanStatusResponse:
    """Get the status of the planner service."""
    from nexusai.ml.planner.schemas import PlanStatus

    return PlanStatusResponse(
        plan_id="",
        status=PlanStatus.READY,
        request_id=get_request_id(),
    )


@router.get(
    "/{plan_id}",
    summary="Get plan by ID",
    description=(
        "Retrieve a stored plan. Plan persistence is not implemented in Day 3; "
        "the planner returns plans to the caller without storing them."
    ),
)
def get_plan(
    plan_id: str,
    settings: Settings = Depends(get_app_settings),
) -> dict:
    """Report that plan storage is not yet implemented."""
    return {
        "plan_id": plan_id,
        "available": False,
        "message": (
            "Plan persistence is not implemented in Day 3. "
            "Plans are returned by POST /api/v1/planner/plan without being stored."
        ),
        "request_id": get_request_id(),
    }


@router.post(
    "/{plan_id}/task-status",
    summary="Update task status",
    description=(
        "Update the status of a task in a stored plan. Requires plan "
        "persistence, which is not implemented in Day 3."
    ),
)
def update_task_status(
    plan_id: str,
    payload: TaskStatusUpdate,
    settings: Settings = Depends(get_app_settings),
) -> dict:
    """Report that plan storage is not yet implemented."""
    return {
        "plan_id": plan_id,
        "task_id": payload.task_id,
        "status": payload.status.value,
        "available": False,
        "message": (
            "Plan persistence is not implemented in Day 3. "
            "Task status updates will be supported once plans are stored."
        ),
        "request_id": get_request_id(),
    }
