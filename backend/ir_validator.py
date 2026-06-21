"""
ir_validator.py

Phase 5, step 4 — validate a MultiTableSemanticIR against a schema graph.

Checks that the IR refers only to tables and columns that exist, that
aggregation functions are supported, and that having/order_by aliases and
relationship hints resolve. It does NOT check join paths, infer missing
relationships, traverse the graph, generate SQL, call the LLM, or touch
/query. Its only import is semantic_ir.

`graph` is expected to be the full schema-graph payload (as returned by
get_database_graph): tables each carrying a `columns` list, plus a
`relationships` list.
"""

from semantic_ir import MultiTableSemanticIR, to_dict, from_dict

VALID_AGG_FUNCTIONS = {"COUNT", "SUM", "AVG", "MIN", "MAX"}


# ---------------------------------------------------------------------------
# Input normalization
# ---------------------------------------------------------------------------
def _as_ir_dict(ir):
    """Accept either a MultiTableSemanticIR or a dict; return a normalized
    IR dict with every key present."""
    if isinstance(ir, MultiTableSemanticIR):
        return to_dict(ir)
    if isinstance(ir, dict):
        return to_dict(from_dict(ir))
    return to_dict(from_dict({}))


def _graph_dict(graph):
    """Tolerate a graph wrapped under a 'database' key."""
    if isinstance(graph, dict) and isinstance(graph.get("database"), dict):
        return graph["database"]
    return graph if isinstance(graph, dict) else {}


def _index_graph(graph):
    """Return {table_name: set(column_names)} from the schema graph."""
    g = _graph_dict(graph)
    table_cols = {}
    for table in g.get("tables") or []:
        if not isinstance(table, dict):
            continue
        name = str(table.get("table_name", "")).strip().lower()
        cols = set()
        for col in table.get("columns") or []:
            if isinstance(col, dict) and col.get("column_name") is not None:
                cols.add(str(col["column_name"]).strip().lower())
        table_cols[name] = cols
    return table_cols


# ---------------------------------------------------------------------------
# Column existence check
# ---------------------------------------------------------------------------
def _check_column(ref, table_cols, where, errors):
    """Validate a table-qualified column reference {table, column}. A column
    of '*' (e.g. COUNT(*) or table.*) is accepted without a column lookup."""
    if not isinstance(ref, dict):
        errors.append(f"{where}: malformed entry {ref!r}")
        return

    table = str(ref.get("table") or "").strip().lower()
    raw_col = ref.get("column")
    column = str(raw_col).strip().lower() if raw_col is not None else None

    if column == "*":
        return
    if not table:
        errors.append(f"{where}: missing table for column '{column}'")
        return
    if table not in table_cols:
        errors.append(f"{where}: table '{table}' not found in schema")
        return
    if column is None:
        return
    if column not in table_cols[table]:
        errors.append(f"{where}: column '{table}.{column}' not found in schema")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def validate_ir(ir, graph):
    errors = []
    warnings = []

    d = _as_ir_dict(ir)
    table_cols = _index_graph(graph)

    # 1. database_id present
    if d.get("database_id") is None:
        errors.append("database_id is missing")

    # 2. all IR tables exist
    ir_tables = [str(t).strip().lower() for t in (d.get("tables") or [])]
    for table in ir_tables:
        if table not in table_cols:
            errors.append(f"table '{table}' not found in schema")

    # 3 + 5. table-qualified columns exist
    for ref in d.get("select") or []:
        _check_column(ref, table_cols, "select", errors)
    for ref in d.get("filters") or []:
        _check_column(ref, table_cols, "filters", errors)
    for ref in d.get("group_by") or []:
        _check_column(ref, table_cols, "group_by", errors)

    # 4. aggregation functions + their columns; collect aliases
    agg_aliases = set()
    for agg in d.get("aggregations") or []:
        if not isinstance(agg, dict):
            errors.append(f"aggregations: malformed entry {agg!r}")
            continue
        fn = str(agg.get("function") or "").strip().upper()
        if fn not in VALID_AGG_FUNCTIONS:
            errors.append(
                f"aggregation function '{agg.get('function')}' is not one of "
                "COUNT, SUM, AVG, MIN, MAX"
            )
        col = agg.get("column")
        if col is not None and str(col).strip() != "*":
            _check_column(
                {"table": agg.get("table"), "column": col},
                table_cols, "aggregations", errors,
            )
        alias = agg.get("alias")
        if alias:
            agg_aliases.add(str(alias).strip().lower())

    # order_by: a table-qualified column OR an aggregation alias
    for ob in d.get("order_by") or []:
        if not isinstance(ob, dict):
            errors.append(f"order_by: malformed entry {ob!r}")
            continue
        if ob.get("column") is not None:
            _check_column(ob, table_cols, "order_by", errors)
        elif ob.get("aggregation_alias") is not None:
            if str(ob["aggregation_alias"]).strip().lower() not in agg_aliases:
                errors.append(
                    f"order_by references unknown aggregation alias "
                    f"'{ob['aggregation_alias']}'"
                )
        else:
            warnings.append("order_by entry has neither column nor aggregation_alias")

    # 6. having must reference a known aggregation alias
    for h in d.get("having") or []:
        if not isinstance(h, dict):
            errors.append(f"having: malformed entry {h!r}")
            continue
        alias = h.get("aggregation_alias")
        if alias is None:
            errors.append("having entry must reference an aggregation_alias")
        elif str(alias).strip().lower() not in agg_aliases:
            errors.append(f"having references unknown aggregation alias '{alias}'")

    # 7. relationship hints reference existing tables + columns
    for hint in d.get("relationship_hints") or []:
        if not isinstance(hint, dict):
            errors.append(f"relationship_hints: malformed entry {hint!r}")
            continue
        _check_column(
            {"table": hint.get("from_table"), "column": hint.get("from_column")},
            table_cols, "relationship_hints(from)", errors,
        )
        _check_column(
            {"table": hint.get("to_table"), "column": hint.get("to_column")},
            table_cols, "relationship_hints(to)", errors,
        )

    # 8. multiple tables but no hints -> warning, not error (no path checks)
    if len(ir_tables) > 1 and not (d.get("relationship_hints") or []):
        warnings.append(
            "multiple tables but no relationship_hints; "
            "Phase 6 will need to resolve a join path"
        )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}