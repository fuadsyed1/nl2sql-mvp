"""
execution_result.py

Phase 8, step 1 — the ExecutionResult data shape.

ExecutionResult is the output of the SQL executor: either a successful run
carrying column names and rows, or a structured failure carrying a reason and
a sanitized error message. This module is pure data — construction and
serialization only. It does not open a database, execute SQL, build SQL, read
the IR/plan/graph, or know anything about workspace file paths.

Two variants share one container:
  * success (executed=True):  columns + rows + row_count + truncated
  * failure (executed=False): reason + error (no columns/rows)
"""

from dataclasses import dataclass, field

# Allowed failure reasons (an enum the executor selects from).
FAILURE_REASONS = (
    "not_generated",   # GeneratedSQL.generated was False; nothing to run
    "db_unavailable",  # the database file could not be opened
    "sql_error",       # a SQLite error occurred during execute/fetch
)

DEFAULT_ROW_LIMIT = 1000

__all__ = [
    "FAILURE_REASONS",
    "DEFAULT_ROW_LIMIT",
    "ExecutionResult",
    "success_result",
    "failure_result",
    "to_dict",
]


@dataclass
class ExecutionResult:
    executed: bool
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    reason: str | None = None
    error: str | None = None
    diagnostics: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constructors
# ---------------------------------------------------------------------------
def success_result(columns, rows, truncated=False, diagnostics=None):
    """A successful execution. row_count is derived from the rows returned."""
    rows = list(rows or [])
    return ExecutionResult(
        executed=True,
        columns=list(columns or []),
        rows=rows,
        row_count=len(rows),
        truncated=bool(truncated),
        diagnostics=diagnostics or {},
    )


def failure_result(reason, error=None, diagnostics=None):
    """A structured execution failure: no columns/rows. `reason` should be one
    of FAILURE_REASONS."""
    return ExecutionResult(
        executed=False,
        reason=reason,
        error=error,
        columns=[],
        rows=[],
        row_count=0,
        diagnostics=diagnostics or {},
    )


# ---------------------------------------------------------------------------
# Serialization (variant-aware, fixed key order)
# ---------------------------------------------------------------------------
def to_dict(result):
    """Serialize to a plain dict. Success and failure emit their own shapes."""
    if result.executed:
        return {
            "executed": True,
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "diagnostics": result.diagnostics,
        }

    return {
        "executed": False,
        "reason": result.reason,
        "error": result.error,
        "columns": [],
        "rows": [],
        "row_count": 0,
        "diagnostics": result.diagnostics,
    }