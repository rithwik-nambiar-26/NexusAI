"""Intent classification API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from nexusai.ml.schemas import (
    IntentClassificationRequest,  # noqa: F401 - re-exported for API routes
    IntentClassificationResult,
)


class IntentInfo(BaseModel):
    """Information about an intent category."""

    category: str = Field(..., description="Intent category identifier")
    supported: bool = Field(..., description="Whether this intent maps to a supported workflow")


class IntentClassificationResponse(BaseModel):
    """Response for intent classification endpoint."""

    result: IntentClassificationResult
    request_id: str = Field(..., description="Correlation ID for this request")


class IntentListResponse(BaseModel):
    """Response for listing intent categories."""

    intents: list[IntentInfo]
    request_id: str = Field(..., description="Correlation ID for this request")
