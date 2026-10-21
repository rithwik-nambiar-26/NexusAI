"""Shared error schemas.

All API errors share one shape so clients can handle them uniformly:

    {"error": {"code": ..., "message": ..., "details": {...}}, "request_id": ...}
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Stable machine-readable error code.")
    message: str = Field(..., description="Human-readable error summary.")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Additional structured context."
    )


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str = Field(..., description="Correlation id for this request.")
