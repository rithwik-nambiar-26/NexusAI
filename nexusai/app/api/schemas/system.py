"""System-status response schema.

``available`` is only ``True`` when the service was actually probed and the
probe succeeded. ``configured`` distinguishes "not set up" from "set up but
unreachable".
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ServiceStatus(BaseModel):
    name: str
    available: bool = Field(..., description="True only if the probe succeeded.")
    configured: bool = Field(..., description="True if the service is configured in settings.")
    backend: str | None = None
    url: str | None = None
    detail: str = Field(..., description="Human-readable probe result.")


class SystemStatusResponse(BaseModel):
    app: str
    version: str
    environment: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    request_id: str
    services: list[ServiceStatus]
    limits: dict[str, int] = Field(default_factory=dict)
