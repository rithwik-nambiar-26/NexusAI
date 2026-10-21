"""Health-check response schema."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., description="'ok' | 'degraded' | 'unhealthy'")
    app: str
    version: str
    environment: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    request_id: str
    checks: dict[str, str] = Field(
        default_factory=dict, description="Component name -> short status string."
    )
