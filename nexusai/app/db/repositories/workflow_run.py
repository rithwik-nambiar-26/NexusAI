"""Repository for :class:`WorkflowRun` and :class:`ExecutionStep`."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from nexusai.app.db.models import ExecutionStep, WorkflowRun


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WorkflowRunRepository:
    """Data-access object for workflow runs and their execution steps."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------ runs
    def create(
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
        run = WorkflowRun(
            request_id=request_id,
            goal=goal,
            intent=intent,
            condition=condition,
            status=status,
            terminal_state=terminal_state,
            plan=plan,
        )
        self._session.add(run)
        self._session.flush()
        return run

    def get(self, run_id: int) -> WorkflowRun | None:
        return self._session.get(WorkflowRun, run_id)

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        condition: str | None = None,
    ) -> Sequence[WorkflowRun]:
        stmt = select(WorkflowRun).order_by(WorkflowRun.id.desc())
        if status is not None:
            stmt = stmt.where(WorkflowRun.status == status)
        if condition is not None:
            stmt = stmt.where(WorkflowRun.condition == condition)
        stmt = stmt.limit(limit).offset(offset)
        return self._session.scalars(stmt).all()

    def update_status(
        self,
        run_id: int,
        *,
        status: str | None = None,
        terminal_state: str | None = None,
        retries_used: int | None = None,
        execution_time_ms: int | None = None,
    ) -> WorkflowRun | None:
        run = self.get(run_id)
        if run is None:
            return None
        if status is not None:
            run.status = status
        if terminal_state is not None:
            run.terminal_state = terminal_state
        if retries_used is not None:
            run.retries_used = retries_used
        if execution_time_ms is not None:
            run.execution_time_ms = execution_time_ms
        run.updated_at = _utcnow()
        return run

    # -------------------------------------------------------------- steps
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
        step = ExecutionStep(
            run_id=run_id,
            step_index=step_index,
            step_id=step_id,
            step_type=step_type,
            tool=tool,
            input_data=input_data,
            output_data=output_data,
            verification_result=verification_result,
            retries_used=retries_used,
            error=error,
            started_at=_utcnow(),
        )
        self._session.add(step)
        self._session.flush()
        return step

    def list_steps(self, run_id: int) -> Sequence[ExecutionStep]:
        stmt = (
            select(ExecutionStep)
            .where(ExecutionStep.run_id == run_id)
            .order_by(ExecutionStep.step_index)
        )
        return self._session.scalars(stmt).all()

    def update_step(
        self,
        step_id: int,
        *,
        output_data: str | None = None,
        verification_result: str | None = None,
        retries_used: int | None = None,
        error: str | None = None,
    ) -> ExecutionStep | None:
        step = self._session.get(ExecutionStep, step_id)
        if step is None:
            return None
        if output_data is not None:
            step.output_data = output_data
        if verification_result is not None:
            step.verification_result = verification_result
        if retries_used is not None:
            step.retries_used = retries_used
        if error is not None:
            step.error = error
        step.completed_at = _utcnow()
        return step

    def delete(self, run_id: int) -> bool:
        run = self.get(run_id)
        if run is None:
            return False
        self._session.delete(run)
        return True

    def count(
        self,
        *,
        status: str | None = None,
        condition: str | None = None,
    ) -> int:
        from sqlalchemy import func

        stmt = select(func.count(WorkflowRun.id))
        if status is not None:
            stmt = stmt.where(WorkflowRun.status == status)
        if condition is not None:
            stmt = stmt.where(WorkflowRun.condition == condition)
        return int(self._session.scalar(stmt) or 0)

    def __enter__(self) -> WorkflowRunRepository:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self._session.commit()
        else:
            self._session.rollback()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
