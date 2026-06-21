"""
legacy_ir_adapter.py

Phase 5, step 2 — backward-compatibility adapter.

Converts the existing single-table semantic object into the new
MultiTableSemanticIR shape. It accepts both legacy forms:

  * the rule-based parser's object, which nests the query under a
    "relational" block, and
  * the LLM extractor's flat dict.

Both use: entity, select (column-name strings or ["*"]), filters with keys
field/operator/value, a single aggregation {function, field}, a single
group_by, and sort {field, direction}.

The result is always single-table: every column is qualified with the one
table and `relationship_hints` is empty.

Pure mapping. No SQL generation, no joins, no graph traversal, no validation,
no LLM, and no change to /query.
"""

from semantic_ir import MultiTableSemanticIR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_column(table_name, column):
    """Return a table-qualified column reference {table, column}."""
    return {
        "table": (table_name or "").strip().lower(),
        "column": str(column).strip().lower(),
    }


def _relational(legacy_semantic):
    """Return the relational mapping from either the full semantic object
    (with a 'relational' block) or an already-flat single-table dict."""
    if not isinstance(legacy_semantic, dict):
        return {}
    inner = legacy_semantic.get("relational")
    if isinstance(inner, dict):
        return inner
    return legacy_semantic


def _map_select(table, select_list):
    if not select_list:
        return []
    return [_normalize_column(table, col) for col in select_list]


def _map_filters(table, filters):
    mapped = []
    for f in filters or []:
        if not isinstance(f, dict):
            continue
        qualified = _normalize_column(table, f.get("field", f.get("column")))
        mapped.append({
            "table": qualified["table"],
            "column": qualified["column"],
            "op": f.get("operator", f.get("op")),
            "value": f.get("value"),
            "connector": f.get("connector", "AND"),
        })
    return mapped


def _map_aggregations(table, aggregation):
    if not isinstance(aggregation, dict):
        return []
    field = aggregation.get("field", aggregation.get("column", "*"))
    column = "*" if field in (None, "*") else _normalize_column(table, field)["column"]
    return [{
        "function": aggregation.get("function"),
        "table": (table or "").strip().lower(),
        "column": column,
        "alias": aggregation.get("alias"),
    }]


def _map_group_by(table, group_by):
    if not group_by:
        return []
    if isinstance(group_by, list):
        return [_normalize_column(table, g) for g in group_by if g]
    return [_normalize_column(table, group_by)]


def _map_order_by(table, sort):
    if not isinstance(sort, dict):
        return []
    field = sort.get("field", sort.get("column"))
    if not field:
        return []
    qualified = _normalize_column(table, field)
    return [{
        "table": qualified["table"],
        "column": qualified["column"],
        "aggregation_alias": None,
        "direction": (sort.get("direction") or "ASC").upper(),
    }]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def from_legacy_semantic(database_id, table_name, legacy_semantic):
    """Convert a single-table legacy semantic object into a
    MultiTableSemanticIR (single table, fully qualified, no joins)."""
    relational = _relational(legacy_semantic)

    table = (table_name or relational.get("entity") or "").strip().lower()
    tables = [table] if table else []

    return MultiTableSemanticIR(
        database_id=database_id,
        tables=tables,
        select=_map_select(table, relational.get("select")),
        filters=_map_filters(table, relational.get("filters")),
        aggregations=_map_aggregations(table, relational.get("aggregation")),
        group_by=_map_group_by(table, relational.get("group_by")),
        having=[],
        order_by=_map_order_by(table, relational.get("sort")),
        limit=relational.get("limit"),
        distinct=bool(relational.get("distinct", False)),
        relationship_hints=[],
    )