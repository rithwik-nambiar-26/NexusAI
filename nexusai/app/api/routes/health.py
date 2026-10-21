"""Liveness and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from nexusai.app.api.dependencies import get_app_settings
from nexusai.app.api.schemas.health import HealthResponse
from nexusai.app.config import Settings
from nexusai.app.core.context import get_request_id
from nexusai.app.services.system import get_service_status

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description=(
        "Reports whether the NexusAI application process is running and whether "
        "its critical dependencies (the local database) are reachable."
    ),
)
def health(request: Request, settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    engine = getattr(request.app.state, "engine", None)
    services = get_service_status(settings, engine)
    db_ok = bool(services["database"]["available"])

    overall = "ok" if db_ok else "unhealthy"

    checks = {
        "database": "ok" if db_ok else "unavailable",
        "ollama": "available" if services["ollama"]["available"] else "unavailable",
        "chromadb": "available" if services["chromadb"]["available"] else "unavailable",
    }

    return HealthResponse(
        status=overall,
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        request_id=get_request_id(),
        checks=checks,
    )
