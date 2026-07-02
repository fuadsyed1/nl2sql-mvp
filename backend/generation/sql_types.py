"""
sql_types.py

Phase 7, step 1 — the GeneratedSQL data shape.

GeneratedSQL is the output of the multi-table SQL generator: either a
successfully rendered SQL string with its bound parameters, or a structured
decline carrying a failure reason. This module is pure data — construction and
serialization only. It renders no SQL, reads no plan/IR/graph, executes
nothing, and calls no model.

Two variants share one container:
  * success (generated=True):  sql + params + diagnostics
  * failure (generated=False): reason + null sql + empty params + diagnostics
"""

from dataclasses import dataclass, field

# Allowed failure reasons (an enum the generator selects from).
FAILURE_REASONS = (
    "unresolved_plan",        # plan.resolved is False
    "invalid_ir",             # embedded IR was flagged invalid (called out of order)
    "empty_select",           # no select columns AND no aggregations
    "empty_alias_query",      # aliases present but no alias_select to project
    "non_scalar_parameter",   # a non-scalar (e.g. column-ref dict) reached a bind slot
)

__all__ = [
    "FAILURE_REASONS",
    "GeneratedSQL",
    "generated_sql",
    "failed_sql",
    "to_dict",
]


@dataclass
class GeneratedSQL:
    generated: bool
    sql: str | None = None
    params: list = field(default_factory=list)
    reason: str | None = None
    diagnostics: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constructors
# ---------------------------------------------------------------------------
def generated_sql(sql, params=None, diagnostics=None):
    """A successfully generated SQL statement with its bound parameters."""
    return GeneratedSQL(
        generated=True,
        sql=sql,
        params=list(params or []),
        diagnostics=diagnostics or {},
    )


def failed_sql(reason, diagnostics=None):
    """A structured decline: no SQL produced. `reason` should be one of
    FAILURE_REASONS."""
    return GeneratedSQL(
        generated=False,
        sql=None,
        params=[],
        reason=reason,
        diagnostics=diagnostics or {},
    )


# ---------------------------------------------------------------------------
# Serialization (variant-aware, fixed key order)
# ---------------------------------------------------------------------------
def to_dict(result):
    """Serialize to a plain dict. Success and failure emit their own shapes."""
    if result.generated:
        return {
            "generated": True,
            "sql": result.sql,
            "params": result.params,
            "diagnostics": result.diagnostics,
        }

    return {
        "generated": False,
        "reason": result.reason,
        "sql": None,
        "params": [],
        "diagnostics": result.diagnostics,
    }