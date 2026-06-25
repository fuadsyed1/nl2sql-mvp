"""
semantic_ir.py

Phase 5, step 1 — the multi-table semantic IR data structure.

A schema-aware, pre-SQL representation of a query: user intent bound to
validated schema identifiers (table names and table-qualified columns). It
deliberately holds NO resolved join path, NO schema metadata, and NO SQL.

`relationship_hints` are advisory, by-value endpoint references that Phase 6
may use or recompute from the schema graph; the IR never depends on them
being present or current. (relationship_id is optional and non-authoritative
because Phase 4 re-detection re-issues IDs.)

This module is pure data — construction and serialization only. It does not
touch SQL generation, the /query pipeline, the schema graph, or joins, and it
remains a strict superset of the single-table case (see single_table_ir).
"""

from dataclasses import dataclass, field

IR_VERSION = "1.0"

__all__ = [
    "IR_VERSION",
    "MultiTableSemanticIR",
    "empty_ir",
    "single_table_ir",
    "to_dict",
    "from_dict",
]


@dataclass
class MultiTableSemanticIR:
    database_id: int
    version: str = IR_VERSION
    tables: list = field(default_factory=list)               # list[str]
    select: list = field(default_factory=list)               # {table, column, alias?}
    filters: list = field(default_factory=list)              # {table, column, op, value, connector}
    aggregations: list = field(default_factory=list)         # {function, table, column, alias}
    group_by: list = field(default_factory=list)             # {table, column}
    having: list = field(default_factory=list)               # {aggregation_alias, op, value}
    order_by: list = field(default_factory=list)             # {table?, column?, aggregation_alias?, direction}
    limit: int | None = None
    distinct: bool = False
    relationship_hints: list = field(default_factory=list)   # {from_table, from_column, to_table, to_column, relationship_id?}


# ---------------------------------------------------------------------------
# Constructors
# ---------------------------------------------------------------------------
def empty_ir(database_id):
    """An IR scoped to a database with no clauses filled in yet."""
    return MultiTableSemanticIR(database_id=database_id)


def single_table_ir(database_id, table_name):
    """A single-table IR — the backward-compatible shape: exactly one table
    and no relationship hints. The caller fills select/filters as needed."""
    return MultiTableSemanticIR(database_id=database_id, tables=[table_name])


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def to_dict(ir):
    """Serialize an IR to a plain dict in the approved field order."""
    return {
        "version": ir.version,
        "database_id": ir.database_id,
        "tables": ir.tables,
        "select": ir.select,
        "filters": ir.filters,
        "aggregations": ir.aggregations,
        "group_by": ir.group_by,
        "having": ir.having,
        "order_by": ir.order_by,
        "limit": ir.limit,
        "distinct": ir.distinct,
        "relationship_hints": ir.relationship_hints,
    }


def from_dict(data):
    """Build an IR from a dict, tolerant of missing keys.

    Accepts the legacy keys `columns` (-> select) and `relationships`
    (-> relationship_hints) as fallbacks, so earlier-shaped payloads still
    deserialize cleanly.
    """
    data = data or {}
    return MultiTableSemanticIR(
        database_id=data.get("database_id"),
        version=data.get("version", IR_VERSION),
        tables=data.get("tables", []),
        select=data.get("select", data.get("columns", [])),
        filters=data.get("filters", []),
        aggregations=data.get("aggregations", []),
        group_by=data.get("group_by", []),
        having=data.get("having", []),
        order_by=data.get("order_by", []),
        limit=data.get("limit"),
        distinct=data.get("distinct", False),
        relationship_hints=data.get(
            "relationship_hints", data.get("relationships", [])
        ),
    )