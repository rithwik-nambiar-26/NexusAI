"""Request-scoped state (request ID) exposed through a context variable."""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str:
    """Return the active request id, or ``"-"`` when none is set."""
    return request_id_var.get() or "-"


def set_request_id(value: str) -> None:
    """Set the active request id."""
    request_id_var.set(value)
