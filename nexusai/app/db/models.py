"""Declarative SQLAlchemy models for NexusAI.

These are the minimal persistence models for Day 1: workflow runs and their
execution steps. Each model carries a ``created_at``/``updated_at`` pair and
an explicit ``id``. Models for the agent, RAG and tool subsystems are
scheduled for Days 2-7 and are intentionally absent today.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Shared declarative base for all NexusAI models."""


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    condition: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    terminal_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    retries_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    steps: Mapped[list[ExecutionStep]] = relationship(
        "ExecutionStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ExecutionStep.step_index",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<WorkflowRun(id={self.id}, status={self.status!r}, "
            f"condition={self.condition!r}, terminal_state={self.terminal_state!r})>"
        )


class ExecutionStep(Base):
    __tablename__ = "execution_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    step_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tool: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    input_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_result: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    retries_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[WorkflowRun] = relationship("WorkflowRun", back_populates="steps")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<ExecutionStep(run_id={self.run_id}, step_index={self.step_index}, "
            f"tool={self.tool!r}, verification={self.verification_result!r})>"
        )
