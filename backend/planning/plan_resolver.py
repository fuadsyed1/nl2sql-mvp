"""
plan_resolver.py

Phase 6, step 5 — orchestrate a validated IR and a schema graph into a
ResolvedQueryPlan.

resolve_plan(ir, graph):
  * reads the IR's tables and relationship_hints (read-only),
  * builds adjacency from the graph (read-only),
  * spans the required tables with join_tree_builder,
  * returns a success_plan when connected, or a failure_plan mapped to an
    approved reason (empty_tables / no_relationships / disconnected_tables).

It never mutates the IR or the graph, embeds the original IR object unchanged
in the plan, preserves the builder's diagnostics, and resolves a single-table
IR trivially (empty joins). It builds no SQL and runs no queries.
"""

from planning.query_plan import success_plan, failure_plan
from planning.schema_graph_adapter import build_adjacency
from planning.join_tree_builder import build_join_tree

__all__ = ["resolve_plan"]


def _ir_tables(ir):
    if isinstance(ir, dict):
        return list(ir.get("tables") or [])
    return list(getattr(ir, "tables", []) or [])


def _ir_hints(ir):
    if isinstance(ir, dict):
        return list(ir.get("relationship_hints") or [])
    return list(getattr(ir, "relationship_hints", []) or [])


def resolve_plan(ir, graph):
    """Validated IR + schema graph -> ResolvedQueryPlan (success or failure)."""
    ir_tables = _ir_tables(ir)
    hints = _ir_hints(ir)

    # No tables to resolve.
    if not ir_tables:
        return failure_plan(
            reason="empty_tables",
            unresolved_tables=[],
            components=[],
            ir=ir,
            diagnostics={"reason": "empty_tables", "note": "IR has no tables"},
        )

    adjacency = build_adjacency(graph)
    result = build_join_tree(list(ir_tables), adjacency, hints)

    if result["connected"]:
        return success_plan(
            from_table=result["from_table"],
            joins=result["joins"],
            tables_used=result["tables_used"],
            bridge_tables=result["bridge_tables"],
            ir=ir,
            diagnostics=result["diagnostics"],
        )

    # Disconnected: distinguish "no relationships at all" from "edges exist but
    # don't connect these tables".
    has_edges = any(adjacency.values())
    reason = "disconnected_tables" if has_edges else "no_relationships"

    diagnostics = dict(result.get("diagnostics") or {})
    diagnostics["resolved_reason"] = reason

    return failure_plan(
        reason=reason,
        unresolved_tables=result.get("unresolved_tables", []),
        components=result.get("components", []),
        ir=ir,
        diagnostics=diagnostics,
    )