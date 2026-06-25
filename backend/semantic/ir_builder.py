"""
ir_builder.py

Phase 5, step 3 — build a MultiTableSemanticIR from a schema-graph-aware
extraction dict.

The extraction already speaks the IR's vocabulary (tables + table-qualified
clauses); the builder normalizes casing, copies the clauses, and — only when a
schema graph is supplied — attaches non-authoritative `relationship_hints` for
the DIRECT edges whose two endpoint tables are both in the extraction.

It does NOT search join paths, infer missing tables, validate correctness,
call the LLM, touch SQL generation, or read the database (the graph is passed
in by the caller). Its only import is semantic_ir.
"""

from semantic.semantic_ir import MultiTableSemanticIR


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------
def _lower(value):
    return str(value).strip().lower()


def _normalize_ref(entry):
    """Return a copy of a clause entry with its `table` / `column` keys
    lowercased (when present). Other keys (op, value, alias, direction,
    aggregation_alias, function, connector, …) are preserved as-is."""
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    if out.get("table") is not None:
        out["table"] = _lower(out["table"])
    if out.get("column") is not None:
        out["column"] = _lower(out["column"])
    return out


def _normalize_list(items):
    return [_normalize_ref(x) for x in (items or [])]


# ---------------------------------------------------------------------------
# Relationship hints (direct edges only — no traversal)
# ---------------------------------------------------------------------------
def _graph_relationships(graph):
    """Pull the edge list from a schema-graph payload, tolerating either the
    full graph dict (with a 'relationships' key) or a bare list of edges."""
    if not graph:
        return []
    if isinstance(graph, dict):
        return graph.get("relationships") or []
    if isinstance(graph, list):
        return graph
    return []


def _referenced_tables(clause_lists):
    """First-seen-ordered list of table names appearing on any clause entry."""
    seen = []
    for clause in clause_lists:
        for entry in clause or []:
            if isinstance(entry, dict) and entry.get("table"):
                t = _lower(entry["table"])
                if t and t not in seen:
                    seen.append(t)
    return seen


def _union_tables(provided, clause_lists):
    """Union of model-provided tables and tables referenced by clause entries,
    preserving provided order first, then first-seen referenced order. Lossless
    and additive: it never removes, renames, or remaps anything."""
    tables = []
    for t in provided:
        if t and t not in tables:
            tables.append(t)
    for t in _referenced_tables(clause_lists):
        if t not in tables:
            tables.append(t)
    return tables


def _relationship_hints(graph, tables_set):
    """Direct relationships whose BOTH endpoint tables are among `tables_set`,
    reduced to by-value, non-authoritative hints. Volatile fields (confirmed,
    confidence, type, scores) are intentionally dropped; relationship_id is
    kept only as an optional back-reference."""
    hints = []
    seen = set()
    for rel in _graph_relationships(graph):
        if not isinstance(rel, dict):
            continue
        ft = _lower(rel.get("from_table", ""))
        tt = _lower(rel.get("to_table", ""))
        if ft not in tables_set or tt not in tables_set:
            continue

        fc = _lower(rel.get("from_column", ""))
        tc = _lower(rel.get("to_column", ""))
        key = (ft, fc, tt, tc)
        if key in seen:
            continue
        seen.add(key)

        hint = {
            "from_table": ft,
            "from_column": fc,
            "to_table": tt,
            "to_column": tc,
        }
        rid = rel.get("relationship_id")
        if rid is not None:
            hint["relationship_id"] = rid
        hints.append(hint)

    return hints


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def build_from_extraction(database_id, extraction, graph=None):
    """Build a MultiTableSemanticIR from an extraction dict.

    `tables` is derived as the union of the model-provided tables and every
    table referenced in select, filters, aggregations, group_by, having, and
    order_by. This fills in a list the model sometimes omits even though its
    columns are already table-qualified; it is lossless and never remaps or
    invents column references. If `graph` is provided, direct relationship
    hints between the resulting tables are attached; otherwise relationship_hints
    is empty. No path search, no table inference beyond the union, no validation.
    """
    extraction = extraction or {}

    select = _normalize_list(extraction.get("select"))
    filters = _normalize_list(extraction.get("filters"))
    aggregations = _normalize_list(extraction.get("aggregations"))
    group_by = _normalize_list(extraction.get("group_by"))
    having = _normalize_list(extraction.get("having"))
    order_by = _normalize_list(extraction.get("order_by"))

    provided = [_lower(t) for t in (extraction.get("tables") or [])]
    tables = _union_tables(
        provided,
        [select, filters, aggregations, group_by, having, order_by],
    )
    tables_set = set(tables)

    return MultiTableSemanticIR(
        database_id=database_id,
        tables=tables,
        select=select,
        filters=filters,
        aggregations=aggregations,
        group_by=group_by,
        having=having,
        order_by=order_by,
        limit=extraction.get("limit"),
        distinct=bool(extraction.get("distinct", False)),
        relationship_hints=_relationship_hints(graph, tables_set) if graph else [],
    )