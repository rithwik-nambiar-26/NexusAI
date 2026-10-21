"""Intent classification API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from nexusai.app.api.dependencies import get_app_settings
from nexusai.app.api.schemas.intent import (
    IntentClassificationRequest,
    IntentClassificationResponse,
    IntentListResponse,
)
from nexusai.app.config import Settings
from nexusai.app.core.context import get_request_id
from nexusai.app.core.exceptions import ServiceUnavailableError
from nexusai.app.services.intent import get_intent_service
from nexusai.ml.schemas import IntentCategory

router = APIRouter(prefix="/api/v1/intent", tags=["intent"])


@router.post(
    "/classify",
    response_model=IntentClassificationResponse,
    summary="Classify user intent",
    description=(
        "Classify a natural-language user request into a supported intent category. "
        "Returns structured output with confidence score and handling instructions."
    ),
)
def classify_intent(
    request: Request,
    payload: IntentClassificationRequest,
    settings: Settings = Depends(get_app_settings),
) -> IntentClassificationResponse:
    """Classify a user request into an intent category."""
    service = get_intent_service()

    if not service.is_available():
        raise ServiceUnavailableError(
            "Intent classifier not trained. Run 'python nexusai/ml/train.py' first.",
            code="model_unavailable",
        )

    result = service.classify(payload)

    return IntentClassificationResponse(
        result=result,
        request_id=get_request_id(),
    )


@router.get(
    "/intents",
    response_model=IntentListResponse,
    summary="List supported intents",
    description="Return all known intent categories and their workflow support status.",
)
def list_intents(
    settings: Settings = Depends(get_app_settings),
) -> IntentListResponse:
    """List all known intent categories."""
    _ = get_intent_service()  # Ensure service is initialized

    return IntentListResponse(
        intents=[
            {
                "category": intent.value,
                "supported": intent in IntentCategory.supported(),
            }
            for intent in IntentCategory
        ],
        request_id=get_request_id(),
    )


@router.get(
    "/status",
    summary="Get classifier status",
    description="Check if the intent classifier is trained and ready.",
)
def classifier_status(
    settings: Settings = Depends(get_app_settings),
) -> dict:
    """Get the status of the intent classifier."""
    service = get_intent_service()
    available = service.is_available()

    return {
        "available": available,
        "model_path": "nexusai/ml/models/intent_classifier.pkl",
        "request_id": get_request_id(),
    }
