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

from semantic.semantic_ir import MultiTableSemanticIR, to_dict, from_dict

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

    # 0. Derived relations (CTEs). Validate each body against the REAL schema,
    # then register the CTE name + its output columns as a pseudo-table so the
    # main query may reference them. main_from must name a declared CTE.
    cte_cols = {}
    for r in d.get("derived_relations") or []:
        if not isinstance(r, dict):
            errors.append(f"derived_relations: malformed entry {r!r}")
            continue
        name = str(r.get("name") or "").strip().lower()
        if not name:
            errors.append("derived_relations entry missing name")
            continue
        ft = str(r.get("from_table") or "").strip().lower()
        if not ft or ft not in table_cols:
            errors.append(f"derived_relations '{name}': from_table '{ft}' not found in schema")
        for j in r.get("joins") or []:
            if isinstance(j, dict):
                _check_column({"table": j.get("from_table"), "column": j.get("from_column")},
                              table_cols, f"derived_relations.{name}.joins(from)", errors)
                _check_column({"table": j.get("to_table"), "column": j.get("to_column")},
                              table_cols, f"derived_relations.{name}.joins(to)", errors)
        for s in r.get("select") or []:
            if isinstance(s, dict):
                _check_column(s, table_cols, f"derived_relations.{name}.select", errors)
        for a in r.get("aggregations") or []:
            if isinstance(a, dict) and a.get("column") is not None and str(a.get("column")).strip() != "*":
                _check_column({"table": a.get("table"), "column": a.get("column")},
                              table_cols, f"derived_relations.{name}.aggregations", errors)
        for g in r.get("group_by") or []:
            if isinstance(g, dict):
                _check_column(g, table_cols, f"derived_relations.{name}.group_by", errors)
        for f in r.get("filters") or []:
            if isinstance(f, dict):
                _check_column(f, table_cols, f"derived_relations.{name}.filters", errors)
        outs = set()
        for s in r.get("select") or []:
            if isinstance(s, dict):
                outs.add(str(s.get("alias") or s.get("column") or "").strip().lower())
        for a in r.get("aggregations") or []:
            if isinstance(a, dict) and a.get("alias"):
                outs.add(str(a["alias"]).strip().lower())
        cte_cols[name] = {c for c in outs if c}
        # Register progressively so a later CTE body may read from an earlier one.
        table_cols.setdefault(name, cte_cols[name])
    mf = str(d.get("main_from") or "").strip().lower()
    if mf and mf not in cte_cols:
        errors.append(f"main_from '{mf}' is not a declared derived relation")

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

    # 7b. anti-exists (NOT EXISTS) subqueries reference existing tables/columns.
    for spec in d.get("anti_exists") or []:
        if not isinstance(spec, dict):
            errors.append(f"anti_exists: malformed entry {spec!r}")
            continue
        target = str(spec.get("target_table") or "").strip().lower()
        if not target:
            errors.append("anti_exists entry missing target_table")
        elif target not in table_cols:
            errors.append(f"anti_exists: table '{target}' not found in schema")
        for j in spec.get("joins") or []:
            if not isinstance(j, dict):
                continue
            _check_column({"table": j.get("from_table"), "column": j.get("from_column")},
                          table_cols, "anti_exists.joins(from)", errors)
            _check_column({"table": j.get("to_table"), "column": j.get("to_column")},
                          table_cols, "anti_exists.joins(to)", errors)
        for key in ("join_conditions", "where", "filters"):
            for p in spec.get(key) or []:
                if not isinstance(p, dict):
                    continue
                if isinstance(p.get("left"), dict):
                    _check_column(p["left"], table_cols, f"anti_exists.{key}(left)", errors)
                if isinstance(p.get("right"), dict):
                    _check_column(p["right"], table_cols, f"anti_exists.{key}(right)", errors)

    # 7c. top-per-group specs reference existing tables/columns.
    for spec in d.get("top_per_group") or []:
        if not isinstance(spec, dict):
            errors.append(f"top_per_group: malformed entry {spec!r}")
            continue
        tbl = str(spec.get("table") or "").strip().lower()
        if not tbl:
            errors.append("top_per_group entry missing table")
        elif tbl not in table_cols:
            errors.append(f"top_per_group: table '{tbl}' not found in schema")
        ob = spec.get("order_by")
        if not isinstance(ob, dict) or ob.get("column") is None:
            errors.append("top_per_group entry missing order_by column")
        else:
            _check_column({"table": ob.get("table") or tbl, "column": ob.get("column")},
                          table_cols, "top_per_group.order_by", errors)
        for pc in spec.get("partition_by") or []:
            if isinstance(pc, dict):
                _check_column({"table": pc.get("table") or tbl, "column": pc.get("column")},
                              table_cols, "top_per_group.partition_by", errors)

    # 7d. universal quantification: validate referenced tables. Column refs are
    # checked only when their table is a real schema table (a domain_alias is not,
    # so alias-qualified refs are skipped rather than wrongly flagged).
    def _check_ref_lenient(ref, where):
        if isinstance(ref, dict) and str(ref.get("table") or "").strip().lower() in table_cols:
            _check_column(ref, table_cols, where, errors)

    def _check_subspec(sub, where):
        if not isinstance(sub, dict):
            return
        t = str(sub.get("target_table") or "").strip().lower()
        if t and t not in table_cols:
            errors.append(f"{where}: table '{t}' not found in schema")
        for key in ("join_conditions", "where", "filters"):
            for p in sub.get(key) or []:
                if isinstance(p, dict):
                    _check_ref_lenient(p.get("left"), f"{where}(left)")
                    _check_ref_lenient(p.get("right"), f"{where}(right)")

    for spec in d.get("universal") or []:
        if not isinstance(spec, dict):
            errors.append(f"universal: malformed entry {spec!r}")
            continue
        dt = str(spec.get("domain_table") or "").strip().lower()
        if dt and dt not in table_cols:
            errors.append(f"universal: domain_table '{dt}' not found in schema")
        for p in spec.get("domain_filters") or []:
            if isinstance(p, dict):
                _check_ref_lenient(p.get("left"), "universal.domain_filters(left)")
                _check_ref_lenient(p.get("right"), "universal.domain_filters(right)")
        if isinstance(spec.get("must_exist"), dict):
            _check_subspec(spec["must_exist"], "universal.must_exist")
        if isinstance(spec.get("bad_match"), dict):
            _check_subspec(spec["bad_match"], "universal.bad_match")
        for cond in spec.get("inner") or []:
            if not isinstance(cond, dict):
                continue
            if isinstance(cond.get("exists"), dict):
                _check_subspec(cond["exists"], "universal.inner.exists")
            elif isinstance(cond.get("not_exists"), dict):
                _check_subspec(cond["not_exists"], "universal.inner.not_exists")
            else:
                _check_ref_lenient(cond.get("left"), "universal.inner(left)")
                _check_ref_lenient(cond.get("right"), "universal.inner(right)")

    # 7e. set division: group_by, left aggregate, and right subquery aggregate
    # must reference existing tables/columns.
    for spec in d.get("set_division") or []:
        if not isinstance(spec, dict):
            errors.append(f"set_division: malformed entry {spec!r}")
            continue
        for g in spec.get("group_by") or []:
            if isinstance(g, dict):
                _check_column(g, table_cols, "set_division.group_by", errors)
        left = spec.get("left")
        if not isinstance(left, dict) or left.get("column") is None:
            errors.append("set_division.left aggregate missing column")
        elif str(left.get("column")).strip() != "*":
            _check_column(left, table_cols, "set_division.left", errors)
        right = spec.get("right_subquery")
        if not isinstance(right, dict):
            errors.append("set_division missing right_subquery")
        else:
            rt = str(right.get("from_table") or right.get("table") or "").strip().lower()
            if rt and rt not in table_cols:
                errors.append(f"set_division.right_subquery: table '{rt}' not found in schema")
            if right.get("column") is not None and str(right.get("column")).strip() != "*":
                _check_column({"table": right.get("table"), "column": right.get("column")},
                              table_cols, "set_division.right_subquery", errors)

    # 7f. alias / self-join references: each alias.table must exist, and every
    # alias-qualified column must resolve to a declared alias's base table.
    alias_map = {}
    for a in d.get("aliases") or []:
        if not isinstance(a, dict):
            errors.append(f"aliases: malformed entry {a!r}")
            continue
        al = str(a.get("alias") or "").strip().lower()
        tb = str(a.get("table") or "").strip().lower()
        if not al or not tb:
            errors.append("aliases entry missing alias or table")
            continue
        if tb not in table_cols:
            errors.append(f"aliases: table '{tb}' not found in schema")
        else:
            alias_map[al] = tb

    def _check_aliasref(ref, where):
        if not isinstance(ref, dict):
            return
        al = str(ref.get("alias") or "").strip().lower()
        if al not in alias_map:
            errors.append(f"{where}: unknown alias '{al}'")
            return
        col = ref.get("column")
        if col is not None and str(col).strip() != "*":
            c = str(col).strip().lower()
            if c not in table_cols.get(alias_map[al], set()):
                errors.append(f"{where}: column '{al}.{c}' not found in '{alias_map[al]}'")

    for j in d.get("alias_joins") or []:
        if isinstance(j, dict):
            _check_aliasref(j.get("from"), "alias_joins(from)")
            _check_aliasref(j.get("to"), "alias_joins(to)")
    for f in d.get("alias_filters") or []:
        if isinstance(f, dict):
            _check_aliasref(f.get("left"), "alias_filters(left)")
            if isinstance(f.get("right"), dict):
                _check_aliasref(f.get("right"), "alias_filters(right)")
    for s in d.get("alias_select") or []:
        if isinstance(s, dict):
            _check_aliasref(s, "alias_select")

    # 7g. explicit (outer) joins, null filters, compound OR/AND groups: every
    # referenced table/column must exist.
    def _check_pred(c, where):
        if not isinstance(c, dict):
            return
        if isinstance(c.get("left"), dict):
            _check_column(c["left"], table_cols, f"{where}(left)", errors)
        if isinstance(c.get("right"), dict):
            _check_column(c["right"], table_cols, f"{where}(right)", errors)
        if not isinstance(c.get("left"), dict) and c.get("table") is not None:
            _check_column(c, table_cols, where, errors)

    for j in d.get("explicit_joins") or []:
        if not isinstance(j, dict):
            errors.append(f"explicit_joins: malformed entry {j!r}")
            continue
        for side in ("from_table", "to_table"):
            t = str(j.get(side) or "").strip().lower()
            if t and t not in table_cols:
                errors.append(f"explicit_joins: table '{t}' not found in schema")
        for c in j.get("conditions") or []:
            _check_pred(c, "explicit_joins.conditions")
    for nf in d.get("null_filters") or []:
        if isinstance(nf, dict):
            _check_column(nf, table_cols, "null_filters", errors)
    for grp in d.get("compound_filters") or []:
        if not isinstance(grp, dict):
            errors.append(f"compound_filters: malformed entry {grp!r}")
            continue
        for c in grp.get("conditions") or []:
            _check_pred(c, "compound_filters")

    # 8. multiple tables but no hints -> warning, not error (no path checks)
    if len(ir_tables) > 1 and not (d.get("relationship_hints") or []):
        warnings.append(
            "multiple tables but no relationship_hints; "
            "Phase 6 will need to resolve a join path"
        )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}