"""Execution API routes.

These endpoints run a validated plan through the tool registry. They
execute only registered capabilities, enforce the approval policy, and
report what ran.

Execution history is **not** persisted: a report is returned to the
caller and the in-memory state is not queryable later. The endpoints
say so rather than pretending otherwise.
"""

from __future__ import annotations

import contextlib
import json
import logging

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from nexusai.app.api.dependencies import get_app_settings
from nexusai.app.api.schemas.execution import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ExecutePlanRequest,
    ExecutePlanResponse,
    ExecutionStatusResponse,
    ToolListResponse,
)
from nexusai.app.config import Settings
from nexusai.app.core.context import get_request_id
from nexusai.app.core.exceptions import ValidationError as NexusValidationError
from nexusai.app.execution.engine import ExecutionEngine
from nexusai.ml.planner.schemas import Plan

router = APIRouter(prefix="/api/v1/execution", tags=["execution"])


def _engine_for(request: Request) -> ExecutionEngine:
    """Return the execution engine owned by the running application."""
    engine = getattr(request.app.state, "execution_engine", None)
    if engine is None:
        raise NexusValidationError(
            "The execution engine is not available",
            code="engine_unavailable",
        )
    return engine


@router.post(
    "/execute",
    response_model=ExecutePlanResponse,
    summary="Execute a validated plan",
    description=(
        "Execute a plan through the tool registry. Only registered "
        "capabilities run. A task whose tool requires approval waits for an "
        "explicit approval bound to its inputs. Execution history is not "
        "persisted; the report is returned in the response."
    ),
)
def execute_plan(
    request: Request,
    payload: ExecutePlanRequest,
    settings: Settings = Depends(get_app_settings),
) -> ExecutePlanResponse:
    """Execute a plan and return the execution report."""
    try:
        plan = Plan.model_validate(payload.plan)
    except ValidationError as exc:
        raise NexusValidationError(
            "The supplied plan is not a valid plan document",
            code="invalid_plan",
            details={"validation_errors": exc.errors()},
        ) from exc

    engine = _engine_for(request)
    report = engine.execute(plan, approvals=payload.approvals)

    # The report is kept on the application state so the approval endpoint
    # can act on it.
    request.app.state.last_execution_report = report

    # The report is also persisted as a workflow run, so the run history
    # shows what actually happened rather than an empty table.
    run_id = _persist_report(request, plan, report)

    return ExecutePlanResponse(
        report=report,
        request_id=get_request_id(),
        run_id=run_id,
    )


def _persist_report(request: Request, plan: Plan, report) -> int | None:
    """Persist an execution report as a workflow run.

    Returns:
        The identifier of the created run, or None when the database is
        unavailable.
    """
    from nexusai.app.db.session import get_db
    from nexusai.app.services.workflow import WorkflowService

    try:
        session_generator = get_db(request)
        session = next(session_generator)
    except Exception:
        return None

    try:
        service = WorkflowService(session)
        run = service.create_run(
            goal=plan.original_request,
            intent=plan.intent,
            status=report.status.value,
            plan=json.dumps(
                {
                    "plan_id": plan.plan_id,
                    "execution_id": report.execution_id,
                    "tasks": [task.model_dump(mode="json") for task in plan.tasks],
                    "execution_order": plan.execution_order,
                },
                default=str,
            ),
        )
        service.commit()
        return run.id
    except Exception:
        logging.getLogger("nexusai.app.api.routes.execution").exception(
            "failed to persist the execution report"
        )
        return None
    finally:
        with contextlib.suppress(Exception):
            session_generator.close()  # type: ignore[union-attr]


@router.post(
    "/approve",
    response_model=ApprovalDecisionResponse,
    summary="Approve or deny a pending operation",
    description=(
        "Record an approval decision for a task that is awaiting approval. "
        "The decision is bound to the task's validated inputs; changing the "
        "inputs invalidates it."
    ),
)
def approve_task(
    request: Request,
    payload: ApprovalDecisionRequest,
    settings: Settings = Depends(get_app_settings),
) -> ApprovalDecisionResponse:
    """Record an approval decision.

    The report must be resubmitted with the decision, because execution
    history is not persisted between requests.
    """
    engine = _engine_for(request)
    report = getattr(request.app.state, "last_execution_report", None)

    if report is None:
        raise NexusValidationError(
            "There is no execution report to approve against. Re-submit the "
            "plan with the ExecutePlan endpoint first.",
            code="no_execution_report",
        )

    engine.approve(report, payload.task_id, granted=payload.granted, note=payload.note)

    return ApprovalDecisionResponse(
        report=report,
        request_id=get_request_id(),
    )


@router.get(
    "/tools",
    response_model=ToolListResponse,
    summary="List registered tool capabilities",
    description=(
        "Return the capabilities that can be executed, with their risk "
        "classification, permissions, approval requirement and schemas."
    ),
)
def list_tools(
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> ToolListResponse:
    """List the registered tool capabilities."""
    registry = getattr(request.app.state, "tool_registry", None)
    tools = registry.list_tools() if registry is not None else []
    return ToolListResponse(
        tools=tools,
        count=len(tools),
        request_id=get_request_id(),
    )


@router.get(
    "/status",
    response_model=ExecutionStatusResponse,
    summary="Get execution engine status",
    description=(
        "Report whether the execution engine is available and which "
        "capabilities are registered."
    ),
)
def execution_status(
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> ExecutionStatusResponse:
    """Report the execution engine's availability."""
    registry = getattr(request.app.state, "tool_registry", None)
    capabilities = registry.capabilities() if registry is not None else []
    engine = getattr(request.app.state, "execution_engine", None)

    return ExecutionStatusResponse(
        available=engine is not None,
        registered_capabilities=capabilities,
        request_id=get_request_id(),
    )
