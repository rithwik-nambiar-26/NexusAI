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
from nexusai.app.core.logging import get_logger
from nexusai.app.services.intent import get_intent_service
from nexusai.ml.planner.service import create_plan
from nexusai.ml.schemas import IntentClassificationRequest

logger = get_logger("api.planner")

router = APIRouter(prefix="/api/v1/planner", tags=["planner"])


def _classify_independently(text: str) -> tuple[str | None, str | None]:
    """Classify *text* and return its top intent and status.

    This is used when the caller supplies an intent of its own. The
    classifier's own verdict is needed to enforce the destructive-operation
    guard, and it must be obtained here rather than trusted from the
    request body — otherwise a caller could claim an intent that the
    classifier had already recognised as destructive.

    A classifier that is unavailable is not an error here: the guard simply
    cannot fire, and no destructive capability is registered, so nothing
    destructive can run.

    Returns:
        A tuple of (intent, status), or (None, None) when the classifier
        could not produce a prediction.
    """
    try:
        service = get_intent_service()
        if not service.is_available():
            return None, None
        result = service.classify(IntentClassificationRequest(text=text))
    except Exception:  # pragma: no cover - defensive
        logger.warning(
            "Independent classification failed; the destructive-intent guard "
            "could not be applied",
            exc_info=True,
        )
        return None, None

    if result.predicted_intent is None:
        return None, None
    return result.predicted_intent.value, result.status.value


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
    intent_confidence = payload.intent_confidence or 0.0
    intent_status = payload.intent_status or "confident"
    entities = payload.entities or {}
    source = payload.source
    classifier_intent: str | None = None
    classifier_status: str | None = None

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
        classifier_intent = intent
        classifier_status = intent_status
    else:
        # The caller supplied an intent. The classifier is run again here,
        # independently of the caller, so the destructive-operation guard
        # cannot be bypassed by asserting an intent the classifier had
        # already recognised as destructive.
        classifier_intent, classifier_status = _classify_independently(payload.text)

        if source == "explicit":
            # The caller asserted the intent, so the classification status
            # does not apply to it. An explicit choice is treated as a
            # confident statement of intent.
            intent_status = "confident"

    plan, _warnings = create_plan(
        request=payload.text,
        intent=intent,
        intent_confidence=intent_confidence,
        intent_status=intent_status,
        entities=entities,
        source=source,
        classifier_intent=classifier_intent,
        classifier_status=classifier_status,
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
