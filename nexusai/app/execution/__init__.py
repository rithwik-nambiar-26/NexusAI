"""Controlled tool execution for NexusAI.

This package turns a validated plan into executed tasks:

* :mod:`nexusai.app.execution.registry` — the typed tool registry. Only
  explicitly registered capabilities can be executed.
* :mod:`nexusai.app.execution.tools` — adapters that register the Day 4
  document capabilities under the planner's capability names.
* :mod:`nexusai.app.execution.csv_tool` — the read-only CSV analysis
  capability, registered under the planner's data capability names.
* :mod:`nexusai.app.execution.engine` — the execution engine, which
  enforces dependency order, approval state, timeouts and bounded retries.

The engine plans and executes; it does not verify the correctness of a
result. Verification is the Day 6 verifier's job.
"""

from nexusai.app.execution.csv_tool import (
    CSV_CAPABILITIES,
    CsvAnalyseInput,
    CsvAnalyseOutput,
    analyse_csv,
    register_csv_tool,
)
from nexusai.app.execution.engine import (
    ApprovalRequest,
    ApprovalState,
    ExecutionEngine,
    ExecutionReport,
    ExecutionStatus,
    TaskExecutionResult,
)
from nexusai.app.execution.registry import (
    RetryPolicy,
    ToolDefinition,
    ToolError,
    ToolErrorCategory,
    ToolInfo,
    ToolPermission,
    ToolRegistry,
    ToolRisk,
    get_registry,
    reset_registry,
)
from nexusai.app.execution.tools import (
    DOCUMENT_CAPABILITIES,
    register_document_tools,
)

__all__ = [
    "CSV_CAPABILITIES",
    "DOCUMENT_CAPABILITIES",
    "ApprovalRequest",
    "ApprovalState",
    "CsvAnalyseInput",
    "CsvAnalyseOutput",
    "ExecutionEngine",
    "ExecutionReport",
    "ExecutionStatus",
    "RetryPolicy",
    "TaskExecutionResult",
    "ToolDefinition",
    "ToolError",
    "ToolErrorCategory",
    "ToolInfo",
    "ToolPermission",
    "ToolRegistry",
    "ToolRisk",
    "analyse_csv",
    "get_registry",
    "register_csv_tool",
    "register_document_tools",
    "reset_registry",
]
