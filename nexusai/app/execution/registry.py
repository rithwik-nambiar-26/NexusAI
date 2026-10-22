"""Typed tool registry for NexusAI.

A tool is a registered capability with a declared input schema, output
schema, handler, permissions, timeout and retry policy. The registry is
the only way a capability can become executable:

* registration is explicit — nothing is discovered or auto-registered;
* an unregistered capability can never be executed;
* inputs are validated before the handler runs, and outputs are validated
  after it returns;
* a tool that requires approval says so, and the executor enforces it.

The registry has no FastAPI dependency.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nexusai.app.core.logging import get_logger

logger = get_logger("execution.registry")


class ToolPermission(StrEnum):
    """A permission a tool requires.

    Permissions describe what a tool is allowed to touch. They are checked
    by the executor before the handler runs.
    """

    #: Read a file from an allowed root.
    READ_DOCUMENT = "read_document"
    #: Write or modify a file.
    WRITE_DOCUMENT = "write_document"
    #: Write a record to the local database on the user's behalf.
    WRITE_DATABASE = "write_database"
    #: Send a message to an external recipient.
    SEND_COMMUNICATION = "send_communication"
    #: Perform a destructive operation.
    DESTRUCTIVE = "destructive"
    #: Use the network.
    NETWORK = "network"


class ToolRisk(StrEnum):
    """How risky a tool is.

    ``SAFE`` tools may run without approval. ``SENSITIVE`` tools change
    state or reach the outside world and require explicit approval.
    ``DESTRUCTIVE`` tools cannot be run at all by the current executor.
    """

    SAFE = "safe"
    SENSITIVE = "sensitive"
    DESTRUCTIVE = "destructive"


class ToolErrorCategory(StrEnum):
    """Category of a tool failure."""

    NOT_REGISTERED = "not_registered"
    DUPLICATE_REGISTRATION = "duplicate_registration"
    INVALID_INPUT = "invalid_input"
    INVALID_OUTPUT = "invalid_output"
    TIMEOUT = "timeout"
    HANDLER_ERROR = "handler_error"
    PERMISSION_DENIED = "permission_denied"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_INVALID = "approval_invalid"
    PATH_NOT_ALLOWED = "path_not_allowed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class ToolError(Exception):
    """A structured tool failure."""

    def __init__(
        self,
        message: str,
        category: ToolErrorCategory,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.category = category
        self.details = details or {}
        super().__init__(message)


class RetryPolicy(BaseModel):
    """When and how often a failed tool call may be retried.

    A policy only ever applies to a tool that declares itself idempotent.
    A non-idempotent tool — one that writes or sends — is never retried,
    because a retry could duplicate a side effect.
    """

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=1, ge=1, le=10, description="Total attempts, including the first")
    backoff_seconds: float = Field(default=0.0, ge=0.0, le=30.0, description="Delay between attempts")
    retry_on_timeout: bool = Field(default=False, description="Whether a timeout may be retried")

    @property
    def enabled(self) -> bool:
        """True when more than one attempt is permitted."""
        return self.max_attempts > 1


class ToolDefinition(BaseModel):
    """A registered tool.

    The model is frozen: a registered tool cannot be edited in place, so a
    running execution cannot be affected by a later change.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: str = Field(..., min_length=1, description="Unique capability name")
    description: str = Field(..., min_length=1, description="What the tool does")
    input_schema: type[BaseModel] = Field(..., description="Pydantic model for the tool input")
    output_schema: type[BaseModel] = Field(..., description="Pydantic model for the tool output")
    handler: Callable[[BaseModel], BaseModel] = Field(..., description="The execution handler")
    permissions: list[ToolPermission] = Field(
        default_factory=list, description="Permissions the tool requires"
    )
    risk: ToolRisk = Field(default=ToolRisk.SAFE, description="Risk classification")
    requires_approval: bool = Field(
        default=False, description="Whether explicit approval is needed before execution"
    )
    timeout_seconds: float = Field(
        default=30.0, gt=0.0, le=600.0, description="Maximum wall-clock time for one attempt"
    )
    retry_policy: RetryPolicy = Field(
        default_factory=RetryPolicy, description="Retry policy for transient failures"
    )
    idempotent: bool = Field(
        default=True, description="Whether repeating the call has the same effect as calling once"
    )
    version: str = Field(default="1.0.0", description="Version of the tool definition")

    def validate_input(self, payload: dict[str, Any]) -> BaseModel:
        """Validate *payload* against the tool's input schema.

        Raises:
            ToolError: The payload does not satisfy the schema.
        """
        try:
            return self.input_schema.model_validate(payload)
        except ValidationError as exc:
            raise ToolError(
                f"Invalid input for capability '{self.capability}'",
                ToolErrorCategory.INVALID_INPUT,
                {"validation_errors": exc.errors()},
            ) from exc

    def validate_output(self, value: Any) -> BaseModel:
        """Validate a handler's return value against the output schema.

        Raises:
            ToolError: The value does not satisfy the schema.
        """
        if isinstance(value, BaseModel):
            try:
                return self.output_schema.model_validate(value.model_dump())
            except ValidationError as exc:
                raise ToolError(
                    f"Invalid output from capability '{self.capability}'",
                    ToolErrorCategory.INVALID_OUTPUT,
                    {"validation_errors": exc.errors()},
                ) from exc
        try:
            return self.output_schema.model_validate(value)
        except ValidationError as exc:
            raise ToolError(
                f"Invalid output from capability '{self.capability}'",
                ToolErrorCategory.INVALID_OUTPUT,
                {"validation_errors": exc.errors()},
            ) from exc


class ToolInfo(BaseModel):
    """A registry listing entry."""

    capability: str
    description: str
    risk: ToolRisk
    requires_approval: bool
    permissions: list[ToolPermission]
    timeout_seconds: float
    max_attempts: int
    idempotent: bool
    input_fields: list[str]
    output_fields: list[str]
    version: str


class ToolRegistry:
    """An explicit registry of executable capabilities.

    Only capabilities that have been explicitly registered can be
    executed. There is no discovery and no fallback.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(self, tool: ToolDefinition) -> ToolDefinition:
        """Register a tool.

        Raises:
            ToolError: A tool with the same capability is already
                registered.
        """
        if tool.capability in self._tools:
            raise ToolError(
                f"Capability '{tool.capability}' is already registered",
                ToolErrorCategory.DUPLICATE_REGISTRATION,
                {"capability": tool.capability},
            )
        self._tools[tool.capability] = tool
        logger.info(
            "Tool registered",
            extra={
                "capability": tool.capability,
                "requires_approval": tool.requires_approval,
            },
        )
        return tool

    def unregister(self, capability: str) -> bool:
        """Remove a tool from the registry."""
        return self._tools.pop(capability, None) is not None

    def clear(self) -> None:
        """Remove every registered tool."""
        self._tools.clear()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    def get(self, capability: str) -> ToolDefinition:
        """Return a registered tool.

        Raises:
            ToolError: The capability is not registered.
        """
        tool = self._tools.get(capability)
        if tool is None:
            raise ToolError(
                f"Capability '{capability}' is not registered",
                ToolErrorCategory.NOT_REGISTERED,
                {"capability": capability},
            )
        return tool

    def has(self, capability: str) -> bool:
        """Return True when a capability is registered."""
        return capability in self._tools

    def capabilities(self) -> list[str]:
        """Return every registered capability name."""
        return sorted(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, capability: str) -> bool:
        return capability in self._tools

    def list_tools(self) -> list[ToolInfo]:
        """Return a listing of the registered tools."""
        return [
            ToolInfo(
                capability=tool.capability,
                description=tool.description,
                risk=tool.risk,
                requires_approval=tool.requires_approval,
                permissions=tool.permissions,
                timeout_seconds=tool.timeout_seconds,
                max_attempts=tool.retry_policy.max_attempts,
                idempotent=tool.idempotent,
                input_fields=list(tool.input_schema.model_fields),
                output_fields=list(tool.output_schema.model_fields),
                version=tool.version,
            )
            for tool in sorted(self._tools.values(), key=lambda t: t.capability)
        ]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        execution_id: str | None = None,
    ) -> tuple[BaseModel, float]:
        """Execute a registered capability.

        Args:
            capability: The capability to run.
            payload: The input payload, validated against the tool's schema.
            execution_id: Identifier used in logs.

        Returns:
            A tuple of the validated output and the elapsed seconds.

        Raises:
            ToolError: The capability is unknown, the input or output is
                invalid, the handler raised, or the call timed out.
        """
        tool = self.get(capability)
        execution_id = execution_id or uuid4().hex

        validated_input = tool.validate_input(payload)

        started = time.monotonic()
        try:
            raw_output = tool.handler(validated_input)
        except TimeoutError as exc:
            raise ToolError(
                f"Capability '{capability}' timed out after {tool.timeout_seconds}s",
                ToolErrorCategory.TIMEOUT,
                {"capability": capability, "execution_id": execution_id},
            ) from exc
        except ToolError:
            raise
        except Exception as exc:
            logger.exception(
                "Tool handler raised",
                extra={"capability": capability, "execution_id": execution_id},
            )
            raise ToolError(
                f"Capability '{capability}' failed: {exc}",
                ToolErrorCategory.HANDLER_ERROR,
                {
                    "capability": capability,
                    "execution_id": execution_id,
                    "error_type": type(exc).__name__,
                },
            ) from exc
        elapsed = time.monotonic() - started

        validated_output = tool.validate_output(raw_output)

        logger.info(
            "Tool executed",
            extra={
                "capability": capability,
                "execution_id": execution_id,
                "elapsed_seconds": round(elapsed, 4),
            },
        )
        return validated_output, elapsed


#: The shared registry instance.
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Return the shared tool registry."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the shared registry (used by tests)."""
    global _registry
    _registry = None
