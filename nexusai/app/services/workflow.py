"""Workflow run service: create, list, inspect runs and steps.

This service is intentionally thin. The actual agent planning, tool
execution, verification and replanning logic is scheduled for Days 2-7.
Today it provides the persistence path the API exposes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from nexusai.app.core.context import get_request_id
from nexusai.app.db.models import ExecutionStep, WorkflowRun
from nexusai.app.db.repositories.workflow_run import WorkflowRunRepository


class WorkflowService:
    """High-level operations over workflow runs."""

    def __init__(self, session: Session) -> None:
        self._repo = WorkflowRunRepository(session)

    def create_run(
        self,
        goal: str,
        *,
        request_id: str | None = None,
        intent: str | None = None,
        condition: str | None = None,
        status: str = "pending",
        terminal_state: str | None = None,
        plan: str | None = None,
    ) -> WorkflowRun:
        return self._repo.create(
            goal,
            request_id=request_id or get_request_id(),
            intent=intent,
            condition=condition,
            status=status,
            terminal_state=terminal_state,
            plan=plan,
        )

    def get_run(self, run_id: int) -> WorkflowRun | None:
        return self._repo.get(run_id)

    def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        condition: str | None = None,
    ):
        return self._repo.list(limit=limit, offset=offset, status=status, condition=condition)

    def count_runs(self, *, status: str | None = None, condition: str | None = None) -> int:
        return self._repo.count(status=status, condition=condition)

    def add_step(
        self,
        run_id: int,
        step_index: int,
        *,
        step_id: str | None = None,
        step_type: str | None = None,
        tool: str | None = None,
        input_data: str | None = None,
        output_data: str | None = None,
        verification_result: str | None = None,
        retries_used: int = 0,
        error: str | None = None,
    ) -> ExecutionStep:
        return self._repo.add_step(
            run_id,
            step_index,
            step_id=step_id,
            step_type=step_type,
            tool=tool,
            input_data=input_data,
            output_data=output_data,
            verification_result=verification_result,
            retries_used=retries_used,
            error=error,
        )

    def list_steps(self, run_id: int):
        return self._repo.list_steps(run_id)

    def update_step(self, step_id: int, **kwargs) -> ExecutionStep | None:
        return self._repo.update_step(step_id, **kwargs)

    def update_run(self, run_id: int, **kwargs) -> WorkflowRun | None:
        return self._repo.update_status(run_id, **kwargs)

    def delete_run(self, run_id: int) -> bool:
        return self._repo.delete(run_id)

    def commit(self) -> None:
        self._repo.commit()

    def rollback(self) -> None:
        self._repo.rollback()

    def to_dict(self, run: WorkflowRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "request_id": run.request_id,
            "goal": run.goal,
            "intent": run.intent,
            "condition": run.condition,
            "status": run.status,
            "terminal_state": run.terminal_state,
            "plan": run.plan,
            "retries_used": run.retries_used,
            "execution_time_ms": run.execution_time_ms,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            "steps": [
                {
                    "id": s.id,
                    "step_index": s.step_index,
                    "step_id": s.step_id,
                    "step_type": s.step_type,
                    "tool": s.tool,
                    "input_data": s.input_data,
                    "output_data": s.output_data,
                    "verification_result": s.verification_result,
                    "retries_used": s.retries_used,
                    "error": s.error,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
                for s in run.steps
            ],
        }
