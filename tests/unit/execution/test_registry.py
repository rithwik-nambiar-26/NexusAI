"""Tests for the typed tool registry."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nexusai.app.execution.registry import (
    RetryPolicy,
    ToolDefinition,
    ToolError,
    ToolErrorCategory,
    ToolPermission,
    ToolRegistry,
    ToolRisk,
)


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)


class EchoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    echoed: str
    length: int


def _echo_handler(payload: EchoInput) -> EchoOutput:
    return EchoOutput(echoed=payload.text, length=len(payload.text))


def _tool(capability: str = "test.echo", **overrides) -> ToolDefinition:
    defaults = {
        "capability": capability,
        "description": "Echo the input text",
        "input_schema": EchoInput,
        "output_schema": EchoOutput,
        "handler": _echo_handler,
        "permissions": [],
        "risk": ToolRisk.SAFE,
        "requires_approval": False,
        "timeout_seconds": 5.0,
        "retry_policy": RetryPolicy(max_attempts=1),
        "idempotent": True,
    }
    defaults.update(overrides)
    return ToolDefinition(**defaults)


def test_register_tool():
    """Test registering a tool."""
    registry = ToolRegistry()
    registry.register(_tool())
    assert registry.has("test.echo") is True
    assert registry.capabilities() == ["test.echo"]
    assert len(registry) == 1


def test_duplicate_registration_is_rejected():
    """Test that registering the same capability twice is refused."""
    registry = ToolRegistry()
    registry.register(_tool())
    with pytest.raises(ToolError) as exc_info:
        registry.register(_tool())
    assert exc_info.value.category == ToolErrorCategory.DUPLICATE_REGISTRATION


def test_unknown_capability_is_rejected():
    """Test that an unregistered capability cannot be executed."""
    registry = ToolRegistry()
    with pytest.raises(ToolError) as exc_info:
        registry.get("nope")
    assert exc_info.value.category == ToolErrorCategory.NOT_REGISTERED


def test_no_automatic_registration():
    """Test that a registry starts empty."""
    registry = ToolRegistry()
    assert len(registry) == 0
    assert registry.capabilities() == []


def test_execute_validates_input():
    """Test that invalid input is rejected before the handler runs."""
    registry = ToolRegistry()
    registry.register(_tool())
    with pytest.raises(ToolError) as exc_info:
        registry.execute("test.echo", {"text": ""})
    assert exc_info.value.category == ToolErrorCategory.INVALID_INPUT


def test_execute_rejects_unknown_input_fields():
    """Test that an unknown input field is rejected."""
    registry = ToolRegistry()
    registry.register(_tool())
    with pytest.raises(ToolError) as exc_info:
        registry.execute("test.echo", {"text": "hi", "extra": 1})
    assert exc_info.value.category == ToolErrorCategory.INVALID_INPUT


def test_execute_validates_output():
    """Test that an invalid output is rejected."""
    registry = ToolRegistry()

    def bad_handler(payload: EchoInput) -> dict:
        return {"wrong": "field"}

    registry.register(_tool(handler=bad_handler))
    with pytest.raises(ToolError) as exc_info:
        registry.execute("test.echo", {"text": "hi"})
    assert exc_info.value.category == ToolErrorCategory.INVALID_OUTPUT


def test_execute_success():
    """Test a successful execution."""
    registry = ToolRegistry()
    registry.register(_tool())
    output, elapsed = registry.execute("test.echo", {"text": "hello"})
    assert output.echoed == "hello"
    assert output.length == 5
    assert elapsed >= 0


def test_execute_wraps_handler_exception():
    """Test that a handler exception becomes a structured error."""
    registry = ToolRegistry()

    def exploding_handler(payload: EchoInput) -> EchoOutput:
        raise RuntimeError("boom")

    registry.register(_tool(handler=exploding_handler))
    with pytest.raises(ToolError) as exc_info:
        registry.execute("test.echo", {"text": "hi"})
    assert exc_info.value.category == ToolErrorCategory.HANDLER_ERROR
    assert exc_info.value.details["error_type"] == "RuntimeError"


def test_execute_reports_timeout():
    """Test that a handler timeout is reported as a timeout."""
    registry = ToolRegistry()

    def timing_out_handler(payload: EchoInput) -> EchoOutput:
        raise TimeoutError

    registry.register(_tool(handler=timing_out_handler))
    with pytest.raises(ToolError) as exc_info:
        registry.execute("test.echo", {"text": "hi"})
    assert exc_info.value.category == ToolErrorCategory.TIMEOUT


def test_list_tools_reports_metadata():
    """Test the registry listing."""
    registry = ToolRegistry()
    registry.register(
        _tool(
            permissions=[ToolPermission.READ_DOCUMENT],
            requires_approval=True,
            risk=ToolRisk.SENSITIVE,
        )
    )
    tools = registry.list_tools()
    assert len(tools) == 1
    tool = tools[0]
    assert tool.capability == "test.echo"
    assert tool.requires_approval is True
    assert tool.risk == ToolRisk.SENSITIVE
    assert tool.permissions == [ToolPermission.READ_DOCUMENT]
    assert "text" in tool.input_fields
    assert "echoed" in tool.output_fields


def test_tool_definition_is_frozen():
    """Test that a registered tool cannot be edited in place."""
    tool = _tool()
    with pytest.raises(ValidationError):
        tool.capability = "changed"


def test_unregister():
    """Test removing a tool."""
    registry = ToolRegistry()
    registry.register(_tool())
    assert registry.unregister("test.echo") is True
    assert registry.unregister("test.echo") is False
    assert len(registry) == 0


def test_clear():
    """Test clearing the registry."""
    registry = ToolRegistry()
    registry.register(_tool("a.one"))
    registry.register(_tool("b.two"))
    registry.clear()
    assert len(registry) == 0


def test_retry_policy_defaults():
    """Test that the retry policy defaults to a single attempt."""
    policy = RetryPolicy()
    assert policy.max_attempts == 1
    assert policy.enabled is False


def test_retry_policy_rejects_zero_attempts():
    """Test that a zero-attempt policy is rejected."""
    with pytest.raises(ValidationError):
        RetryPolicy(max_attempts=0)


def test_shared_registry_singleton():
    """Test that the shared registry is a singleton."""
    from nexusai.app.execution.registry import get_registry, reset_registry

    reset_registry()
    first = get_registry()
    second = get_registry()
    assert first is second
    reset_registry()
