"""CSV analysis capability for NexusAI.

A small, safe, read-only analysis over a tabular file. It is registered
as an explicit tool like every other capability, so it goes through the
same registry, the same input and output validation, and the same
filesystem policy.

What it deliberately does **not** do:

* it does not train a model on arbitrary labels;
* it does not invent a target variable;
* it does not produce a predictive result of any kind.

It reports what the file contains: its shape, its columns and their
types, missing values, descriptive statistics for numeric columns, and
aggregations over a column the user names. Every figure comes from the
file, and the file is named in the output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator

from nexusai.app.core.logging import get_logger
from nexusai.app.execution.registry import (
    RetryPolicy,
    ToolDefinition,
    ToolError,
    ToolErrorCategory,
    ToolPermission,
    ToolRegistry,
    ToolRisk,
)
from nexusai.app.security.paths import PathPolicy, PathPolicyError

logger = get_logger("execution.csv_tool")

#: Column names that are never used as a grouping key, because they
#: identify a row rather than describe it.
_IDENTIFYING_COLUMNS = ("date", "id", "index", "timestamp", "uuid")

#: The CSV capability names. They match the planner's ``data.load`` and
#: ``data.analyse`` capabilities, so a plan for a data-analysis task
#: binds to this tool without a translation layer. The tool loads the
#: file and analyses it in one call, so it serves both names.
CSV_CAPABILITIES: tuple[str, ...] = ("data.load", "data.analyse")


class CsvAnalyseInput(BaseModel):
    """Input for the ``data.analyse_csv`` capability."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., min_length=1, description="Path to the CSV file")
    group_by: str | None = Field(
        default=None, description="Column to group the numeric aggregation by"
    )
    measure: str | None = Field(
        default=None, description="Numeric column to aggregate"
    )
    top_n: int = Field(default=10, ge=1, le=100, description="Rows to report per group")

    @field_validator("group_by", "measure")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ColumnProfile(BaseModel):
    """Description of one column."""

    model_config = ConfigDict(extra="forbid")

    name: str
    dtype: str
    missing: int
    missing_percent: float
    unique: int
    example: str | None = None


class CsvAnalyseOutput(BaseModel):
    """Output of the ``data.analyse_csv`` capability."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="Path of the analysed file")
    rows: int = Field(..., description="Number of data rows")
    columns: int = Field(..., description="Number of columns")
    column_names: list[str] = Field(default_factory=list)
    profiles: list[ColumnProfile] = Field(default_factory=list)
    numeric_descriptives: dict[str, dict[str, float]] = Field(default_factory=dict)
    group_by: str | None = None
    measure: str | None = None
    aggregation: str | None = None
    grouped_totals: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV file, trying the common encodings."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    # Let pandas raise its own error for a genuinely unreadable file.
    return pd.read_csv(path)


def _profile_columns(frame: pd.DataFrame) -> list[ColumnProfile]:
    """Build a profile for every column."""
    total = len(frame)
    profiles: list[ColumnProfile] = []

    for name in frame.columns:
        series = frame[name]
        missing = int(series.isna().sum())
        example: str | None = None
        try:
            first = series.dropna()
            if len(first):
                example = str(first.iloc[0])
        except Exception:  # pragma: no cover - defensive
            example = None

        profiles.append(
            ColumnProfile(
                name=str(name),
                dtype=str(series.dtype),
                missing=missing,
                missing_percent=round((missing / total * 100) if total else 0.0, 2),
                unique=int(series.nunique(dropna=True)),
                example=example,
            )
        )

    return profiles


def _numeric_descriptives(frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Descriptive statistics for the numeric columns."""
    numeric = frame.select_dtypes(include="number")
    if numeric.empty:
        return {}

    described = numeric.describe().to_dict()
    result: dict[str, dict[str, float]] = {}
    for column, stats in described.items():
        result[str(column)] = {
            key: round(float(value), 4)
            for key, value in stats.items()
            if isinstance(value, (int, float)) and value == value  # not NaN
        }
    return result


def _grouped_totals(
    frame: pd.DataFrame,
    group_by: str,
    measure: str,
    top_n: int,
) -> list[dict[str, Any]]:
    """Sum a numeric measure, grouped by a column, largest first."""
    grouped = (
        frame.groupby(group_by, dropna=False)[measure]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
    )
    return [
        {group_by: str(key), f"total_{measure}": round(float(value), 4)}
        for key, value in grouped.items()
    ]


def analyse_csv(
    path: str,
    *,
    group_by: str | None = None,
    measure: str | None = None,
    top_n: int = 10,
    policy: PathPolicy | None = None,
) -> CsvAnalyseOutput:
    """Analyse a CSV file and return a description of its contents.

    Args:
        path: Path to the CSV file.
        group_by: Column to group by.
        measure: Numeric column to aggregate.
        top_n: Number of groups to report.
        policy: The filesystem policy. When given, the path must resolve
            inside the allowed roots.

    Returns:
        A :class:`CsvAnalyseOutput` describing the file.

    Raises:
        PathPolicyError: The path may not be read.
        ValueError: The file is empty, the named columns are absent, or
            the file cannot be parsed.
    """
    resolved = policy.resolve(path) if policy is not None else Path(path)

    frame = _read_csv(resolved)

    if frame.empty and len(frame.columns) == 0:
        raise ValueError(f"{resolved.name} contains no data")

    notes: list[str] = []
    numeric_columns = [
        str(c) for c in frame.select_dtypes(include="number").columns
    ]

    if group_by and group_by not in frame.columns:
        raise ValueError(
            f"Column '{group_by}' is not in the file. "
            f"Available columns: {', '.join(str(c) for c in frame.columns)}"
        )
    if measure and measure not in frame.columns:
        raise ValueError(
            f"Column '{measure}' is not in the file. "
            f"Available columns: {', '.join(str(c) for c in frame.columns)}"
        )
    if measure and measure not in numeric_columns:
        raise ValueError(
            f"Column '{measure}' is not numeric, so it cannot be summed. "
            f"Numeric columns: {', '.join(numeric_columns) or '(none)'}"
        )

    aggregation = None
    grouped_totals: list[dict[str, Any]] = []

    if group_by and measure:
        aggregation = f"sum({measure}) grouped by {group_by}"
        grouped_totals = _grouped_totals(frame, group_by, measure, top_n)
    elif group_by and not measure:
        notes.append(
            "A grouping column was named but no measure, so no aggregation "
            "was computed. Every numeric column is profiled instead."
        )
    elif measure and not group_by:
        notes.append(
            "A measure was named but no grouping column, so only the "
            "overall total is reported."
        )
        total = frame[measure].sum()
        grouped_totals = [{f"total_{measure}": round(float(total), 4)}]
        aggregation = f"sum({measure})"

    if not numeric_columns:
        notes.append("The file contains no numeric columns, so no statistics are reported.")

    return CsvAnalyseOutput(
        source=resolved.name,
        rows=len(frame),
        columns=len(frame.columns),
        column_names=[str(c) for c in frame.columns],
        profiles=_profile_columns(frame),
        numeric_descriptives=_numeric_descriptives(frame),
        group_by=group_by,
        measure=measure,
        aggregation=aggregation,
        grouped_totals=grouped_totals,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Input and output schemas exposed to the registry
# ---------------------------------------------------------------------------


class CsvToolInput(BaseModel):
    """Input schema for the registered CSV tool."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., min_length=1, description="Path to the CSV file")
    group_by: str | None = Field(default=None, description="Column to group by")
    measure: str | None = Field(default=None, description="Numeric column to aggregate")
    top_n: int = Field(default=10, ge=1, le=100, description="Rows to report per group")


class CsvToolOutput(BaseModel):
    """Output schema for the registered CSV tool."""

    model_config = ConfigDict(extra="forbid")

    source: str
    rows: int
    columns: int
    column_names: list[str] = Field(default_factory=list)
    profiles: list[ColumnProfile] = Field(default_factory=list)
    numeric_descriptives: dict[str, dict[str, float]] = Field(default_factory=dict)
    group_by: str | None = None
    measure: str | None = None
    aggregation: str | None = None
    grouped_totals: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _make_handler(policy: PathPolicy | None):
    """Build the CSV analysis handler.

    Failures are raised as structured :class:`ToolError` values so the
    caller receives a precise reason — a refused path, an unknown column
    or an unparsable file — rather than a generic handler failure.
    """

    def handler(payload: CsvToolInput) -> CsvToolOutput:
        try:
            result = analyse_csv(
                payload.path,
                group_by=payload.group_by,
                measure=payload.measure,
                top_n=payload.top_n,
                policy=policy,
            )
        except PathPolicyError as exc:
            raise ToolError(
                str(exc),
                ToolErrorCategory.PATH_NOT_ALLOWED,
                {"path": payload.path, "code": exc.code},
            ) from exc
        except pd.errors.EmptyDataError as exc:
            raise ToolError(
                "The file is empty and has no header row.",
                ToolErrorCategory.INVALID_INPUT,
                {"path": payload.path},
            ) from exc
        except pd.errors.ParserError as exc:
            raise ToolError(
                f"The file could not be parsed as CSV: {exc}",
                ToolErrorCategory.INVALID_INPUT,
                {"path": payload.path},
            ) from exc
        except ValueError as exc:
            # analyse_csv raises ValueError for an unknown column or a
            # non-numeric measure.
            raise ToolError(
                str(exc),
                ToolErrorCategory.INVALID_INPUT,
                {"path": payload.path},
            ) from exc
        return CsvToolOutput.model_validate(result.model_dump())

    return handler


def register_csv_tool(
    registry: ToolRegistry,
    policy: PathPolicy | None = None,
) -> list[ToolDefinition]:
    """Register the CSV analysis capabilities.

    The tool is registered under both ``data.load`` and ``data.analyse``
    because the planner's data-analysis workflow has a load step and an
    analysis step, and this tool loads and analyses the file together.

    Args:
        registry: The registry to register into.
        policy: The filesystem policy the tool reads under.

    Returns:
        The registered tool definitions.
    """
    tools: list[ToolDefinition] = []
    handler = _make_handler(policy)

    for capability in CSV_CAPABILITIES:
        tool = ToolDefinition(
            capability=capability,
            description=(
                "Load and analyse a CSV file: report its shape, columns and "
                "types, missing values, descriptive statistics for numeric "
                "columns, and a group-by aggregation over a named column."
            ),
            input_schema=CsvToolInput,
            output_schema=CsvToolOutput,
            handler=handler,
            permissions=[ToolPermission.READ_DOCUMENT],
            risk=ToolRisk.SAFE,
            requires_approval=False,
            timeout_seconds=30.0,
            retry_policy=RetryPolicy(max_attempts=1),
            idempotent=True,
        )
        registry.register(tool)
        tools.append(tool)

    logger.info(
        "CSV analysis tools registered",
        extra={"capabilities": [tool.capability for tool in tools]},
    )
    return tools
