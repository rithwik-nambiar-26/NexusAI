"""Workflow run routes: create, list, inspect, delete runs and steps.

The agent planning, tool execution, verification and replanning logic is
scheduled for Days 2-7. These routes expose the persistence path that the
agent will drive, so the API surface is stable now and the agent plugs in later.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from nexusai.app.core.context import get_request_id
from nexusai.app.core.exceptions import NotFoundError, ValidationError
from nexusai.app.db.session import get_db
from nexusai.app.services.workflow import WorkflowService

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


def _serialise(obj: Any) -> str:
    """JSON-serialise arbitrary objects, handling datetimes."""
    return json.dumps(jsonable_encoder(obj), default=str)


def _run_to_dict(service: WorkflowService, run) -> dict[str, Any]:
    return service.to_dict(run)


@router.post(
    "",
    response_model=dict,
    summary="Create a workflow run",
    description=(
        "Register a new workflow run for a natural-language goal. The run is "
        "created in 'pending' status; the agent subsystem (Days 2-7) will drive "
        "it through planning, execution, verification and replanning."
    ),
)
def create_run(
    request: Request,
    session: Session = Depends(get_db),
    goal: str | None = Query(None, description="Natural-language goal"),
    intent: str | None = Query(None),
    condition: str | None = Query(None),
) -> dict[str, Any]:
    if not goal:
        raise ValidationError(
            "goal query parameter is required",
            code="missing_goal",
            details={"parameter": "goal"},
        )
    service = WorkflowService(session)
    run = service.create_run(
        goal=goal,
        intent=intent,
        condition=condition,
    )
    data = _run_to_dict(service, run)
    service.commit()
    return {
        "run": data,
        "request_id": get_request_id(),
    }


@router.get(
    "",
    response_model=dict,
    summary="List workflow runs",
)
def list_runs(
    session: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    condition: str | None = Query(None),
) -> dict[str, Any]:
    service = WorkflowService(session)
    runs = service.list_runs(limit=limit, offset=offset, status=status, condition=condition)
    total = service.count_runs(status=status, condition=condition)
    return {
        "runs": [_run_to_dict(service, run) for run in runs],
        "total": total,
        "limit": limit,
        "offset": offset,
        "request_id": get_request_id(),
    }


@router.get(
    "/{run_id}",
    response_model=dict,
    summary="Get a workflow run with its execution steps",
)
def get_run(
    run_id: int,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    service = WorkflowService(session)
    run = service.get_run(run_id)
    if run is None:
        raise NotFoundError(
            f"workflow run {run_id} not found",
            code="workflow_run_not_found",
            status_code=404,
        )
    return {
        "run": _run_to_dict(service, run),
        "request_id": get_request_id(),
    }


@router.delete(
    "/{run_id}",
    response_model=dict,
    summary="Delete a workflow run",
)
def delete_run(
    run_id: int,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    service = WorkflowService(session)
    deleted = service.delete_run(run_id)
    if not deleted:
        raise NotFoundError(
            f"workflow run {run_id} not found",
            code="workflow_run_not_found",
            status_code=404,
        )
    service.commit()
    return {
        "deleted": True,
        "run_id": run_id,
        "request_id": get_request_id(),
    }
