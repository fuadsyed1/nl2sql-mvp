"""
query_plan.py

Phase 6, step 1 — the ResolvedQueryPlan data shapes.

A ResolvedQueryPlan is the output of the Phase 6 resolver: the validated
Phase 5 IR plus an explicit, ordered join layer that connects every required
table. This module is pure data — construction and serialization only. It does
NOT traverse the graph, rank paths, build join trees, generate SQL, execute
anything, or mutate the IR (the IR is held by reference, unchanged).

Two variants share one container:
  * success (resolved=True): from_table + ordered joins + tables_used + bridge_tables
  * failure (resolved=False): reason + unresolved_tables + components

A single-table query is a valid success: one from_table, joins == [],
bridge_tables == [].
"""

from dataclasses import dataclass, field

# Allowed failure reasons (an enum the resolver/orchestrator selects from).
FAILURE_REASONS = (
    "empty_tables",
    "no_relationships",
    "disconnected_tables",
)

DEFAULT_JOIN_TYPE = "inner"

__all__ = [
    "FAILURE_REASONS",
    "DEFAULT_JOIN_TYPE",
    "ResolvedQueryPlan",
    "join_step",
    "success_plan",
    "single_table_plan",
    "failure_plan",
    "to_dict",
]


@dataclass
class ResolvedQueryPlan:
    resolved: bool
    # success fields
    from_table: str | None = None
    joins: list = field(default_factory=list)
    tables_used: list = field(default_factory=list)
    bridge_tables: list = field(default_factory=list)
    # carried through both variants
    ir: dict | None = None
    diagnostics: dict = field(default_factory=dict)
    # failure-only fields
    reason: str | None = None
    unresolved_tables: list = field(default_factory=list)
    components: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Join step shape (defined here so every producer emits the same dict)
# ---------------------------------------------------------------------------
def join_step(from_table, from_column, to_table, to_column, join_type=DEFAULT_JOIN_TYPE):
    """One ordered join edge. Its `from_table` is expected to already be in the
    growing join tree when the step is emitted (the resolver guarantees this)."""
    return {
        "from_table": from_table,
        "from_column": from_column,
        "to_table": to_table,
        "to_column": to_column,
        "join_type": join_type,
    }


# ---------------------------------------------------------------------------
# Constructors
# ---------------------------------------------------------------------------
def success_plan(from_table, joins, tables_used, bridge_tables, ir, diagnostics=None):
    """A resolved plan connecting every required table."""
    return ResolvedQueryPlan(
        resolved=True,
        from_table=from_table,
        joins=list(joins or []),
        tables_used=list(tables_used or []),
        bridge_tables=list(bridge_tables or []),
        ir=ir,
        diagnostics=diagnostics or {},
    )


def single_table_plan(table, ir, diagnostics=None):
    """A trivially resolved single-table plan: one table, no joins, no bridges."""
    return success_plan(
        from_table=table,
        joins=[],
        tables_used=[table],
        bridge_tables=[],
        ir=ir,
        diagnostics=diagnostics,
    )


def failure_plan(reason, unresolved_tables=None, components=None, ir=None, diagnostics=None):
    """An all-or-nothing failure: required tables could not be connected.
    `reason` should be one of FAILURE_REASONS."""
    return ResolvedQueryPlan(
        resolved=False,
        reason=reason,
        unresolved_tables=list(unresolved_tables or []),
        components=[list(c) for c in (components or [])],
        ir=ir,
        diagnostics=diagnostics or {},
    )


# ---------------------------------------------------------------------------
# Serialization (variant-aware, approved key order)
# ---------------------------------------------------------------------------
def to_dict(plan):
    """Serialize a plan to a plain dict.

    Success and failure emit their own approved shapes; the IR is passed
    through by reference, never copied or mutated.
    """
    if plan.resolved:
        return {
            "resolved": True,
            "from_table": plan.from_table,
            "joins": plan.joins,
            "tables_used": plan.tables_used,
            "bridge_tables": plan.bridge_tables,
            "ir": plan.ir,
            "diagnostics": plan.diagnostics,
        }

    return {
        "resolved": False,
        "reason": plan.reason,
        "unresolved_tables": plan.unresolved_tables,
        "components": plan.components,
        "from_table": plan.from_table,
        "joins": plan.joins,
        "tables_used": plan.tables_used,
        "bridge_tables": plan.bridge_tables,
        "ir": plan.ir,
        "diagnostics": plan.diagnostics,
    }