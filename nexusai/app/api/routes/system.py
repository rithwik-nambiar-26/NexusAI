"""System status endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from nexusai.app.api.dependencies import get_app_settings
from nexusai.app.api.schemas.system import ServiceStatus, SystemStatusResponse
from nexusai.app.config import Settings
from nexusai.app.core.context import get_request_id
from nexusai.app.services.system import get_service_status

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    summary="Detailed system status",
    description=(
        "Reports configuration and the real availability of optional local "
        "services. Services are probed at request time; nothing is reported "
        "as available unless the probe actually succeeded."
    ),
)
def system_status(
    request: Request, settings: Settings = Depends(get_app_settings)
) -> SystemStatusResponse:
    engine = getattr(request.app.state, "engine", None)
    services = get_service_status(settings, engine)

    def _detail(name: str, info: dict) -> str:
        if info.get("available"):
            return f"{name} is available"
        if not info.get("configured"):
            return f"{name} is not configured (no URL set); not probed"
        return f"{name} is configured at {info.get('url')} but the probe did not succeed"

    service_statuses = [
        ServiceStatus(
            name="database",
            available=bool(services["database"]["available"]),
            configured=True,
            backend=services["database"]["backend"],
            detail=(
                "SQLite store is reachable"
                if services["database"]["available"]
                else "SQLite store is NOT reachable"
            ),
        ),
        ServiceStatus(
            name="ollama",
            available=bool(services["ollama"]["available"]),
            configured=bool(services["ollama"]["configured"]),
            url=services["ollama"].get("url"),
            detail=_detail("Ollama", services["ollama"]),
        ),
        ServiceStatus(
            name="chromadb",
            available=bool(services["chromadb"]["available"]),
            configured=bool(services["chromadb"]["configured"]),
            url=services["chromadb"].get("url"),
            detail=_detail("ChromaDB", services["chromadb"]),
        ),
    ]

    return SystemStatusResponse(
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        request_id=get_request_id(),
        services=service_statuses,
        limits={
            "upload_max_size_mb": settings.upload_max_size_mb,
            "max_execution_steps": settings.max_execution_steps,
            "max_retry_budget": settings.max_retry_budget,
            "max_execution_time_seconds": settings.max_execution_time_seconds,
        },
    )
