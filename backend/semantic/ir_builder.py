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
from semantic.ir_normalizer import normalize_ir, sanitize_derived_output_columns
from semantic.ir_semantics import apply_question_semantics


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
    # Normalize a column-to-column reference's casing if the provider emits one.
    vref = out.get("value_ref")
    if isinstance(vref, dict):
        nv = dict(vref)
        if nv.get("table") is not None:
            nv["table"] = _lower(nv["table"])
        if nv.get("column") is not None:
            nv["column"] = _lower(nv["column"])
        out["value_ref"] = nv
    return out


def _normalize_list(items):
    return [_normalize_ref(x) for x in (items or [])]


def _normalize_colref(ref):
    """Lowercase a {table, column} reference (returns a new dict) or pass through."""
    if not isinstance(ref, dict):
        return ref
    out = dict(ref)
    if out.get("table") is not None:
        out["table"] = _lower(out["table"])
    if out.get("column") is not None:
        out["column"] = _lower(out["column"])
    return out


def _normalize_predicate(p):
    """Lowercase the left/right column refs of a comparison predicate."""
    if not isinstance(p, dict):
        return p
    np = dict(p)
    if isinstance(np.get("left"), dict):
        np["left"] = _normalize_colref(np["left"])
    if isinstance(np.get("right"), dict):
        np["right"] = _normalize_colref(np["right"])
    return np


def _normalize_subspec(spec):
    """Normalize an existence subquery block {target_table, joins?,
    where|join_conditions|filters[]} — lowercasing identifiers, preserving
    values/ops/join types."""
    new = dict(spec)
    new["target_table"] = _lower(spec["target_table"])
    joins = []
    for j in spec.get("joins") or []:
        if not isinstance(j, dict):
            continue
        nj = dict(j)
        for k in ("from_table", "from_column", "to_table", "to_column"):
            if nj.get(k) is not None:
                nj[k] = _lower(nj[k])
        joins.append(nj)
    if joins or "joins" in spec:
        new["joins"] = joins
    for key in ("join_conditions", "where", "filters"):
        preds = spec.get(key)
        if isinstance(preds, list):
            new[key] = [_normalize_predicate(p) for p in preds if isinstance(p, dict)]
    return new


def _normalize_anti_exists(specs):
    """Lowercase identifiers inside each NOT EXISTS spec. Malformed entries
    (no target_table) are dropped."""
    return [_normalize_subspec(s) for s in (specs or [])
            if isinstance(s, dict) and s.get("target_table")]


def _normalize_universal(specs):
    """Lowercase identifiers inside each universal-quantification spec
    (domain_table/alias, domain_filters, must_exist/bad_match subspecs, and the
    explicit `inner` exists/not_exists/comparison conditions). Specs that would
    render nothing are dropped."""
    out = []
    for spec in specs or []:
        if not isinstance(spec, dict):
            continue
        new = dict(spec)
        if spec.get("domain_table") is not None:
            new["domain_table"] = _lower(spec["domain_table"])
        if spec.get("domain_alias") is not None:
            new["domain_alias"] = _lower(spec["domain_alias"])
        if isinstance(spec.get("domain_filters"), list):
            new["domain_filters"] = [
                _normalize_predicate(p) for p in spec["domain_filters"]
                if isinstance(p, dict)
            ]
        must = spec.get("must_exist")
        if isinstance(must, dict) and must.get("target_table"):
            new["must_exist"] = _normalize_subspec(must)
        bad = spec.get("bad_match")
        if isinstance(bad, dict) and bad.get("target_table"):
            new["bad_match"] = _normalize_subspec(bad)
        if isinstance(spec.get("inner"), list):
            norm_inner = []
            for cond in spec["inner"]:
                if not isinstance(cond, dict):
                    continue
                if isinstance(cond.get("exists"), dict) and cond["exists"].get("target_table"):
                    norm_inner.append({"exists": _normalize_subspec(cond["exists"])})
                elif isinstance(cond.get("not_exists"), dict) and cond["not_exists"].get("target_table"):
                    norm_inner.append({"not_exists": _normalize_subspec(cond["not_exists"])})
                else:
                    norm_inner.append(_normalize_predicate(cond))
            new["inner"] = norm_inner

        domain_form = new.get("domain_table") and (new.get("must_exist") or new.get("inner"))
        bad_only = (not new.get("domain_table")
                    and isinstance(new.get("bad_match"), dict)
                    and new["bad_match"].get("target_table"))
        if domain_form or bad_only:
            out.append(new)
    return out


def _normalize_set_division(specs):
    """Lowercase identifiers inside each set-division spec (group_by refs, left
    aggregate, right_subquery aggregate + from_table/joins/where). function,
    distinct, and op are preserved. Specs without left + right_subquery dropped."""
    out = []
    for spec in specs or []:
        if not isinstance(spec, dict):
            continue
        left = spec.get("left")
        right = spec.get("right_subquery")
        if not isinstance(left, dict) or not isinstance(right, dict):
            continue
        new = dict(spec)
        new["left"] = _normalize_colref(left)            # keeps function/distinct
        nr = _normalize_colref(right)
        if right.get("from_table") is not None:
            nr["from_table"] = _lower(right["from_table"])
        joins = []
        for j in right.get("joins") or []:
            if not isinstance(j, dict):
                continue
            nj = dict(j)
            for k in ("from_table", "from_column", "to_table", "to_column"):
                if nj.get(k) is not None:
                    nj[k] = _lower(nj[k])
            joins.append(nj)
        if joins or "joins" in right:
            nr["joins"] = joins
        for key in ("join_conditions", "where", "filters"):
            preds = right.get(key)
            if isinstance(preds, list):
                nr[key] = [_normalize_predicate(p) for p in preds if isinstance(p, dict)]
        new["right_subquery"] = nr
        new["group_by"] = [_normalize_colref(g) for g in (spec.get("group_by") or [])
                           if isinstance(g, dict)]
        out.append(new)
    return out


def _normalize_aliasref(r):
    """Lowercase an {alias, column} reference (returns a new dict)."""
    if not isinstance(r, dict):
        return r
    out = dict(r)
    if out.get("alias") is not None:
        out["alias"] = _lower(out["alias"])
    if out.get("column") is not None:
        out["column"] = _lower(out["column"])
    return out


def _normalize_aliases(specs):
    out = []
    for a in specs or []:
        if not isinstance(a, dict) or not a.get("alias") or not a.get("table"):
            continue
        out.append({"alias": _lower(a["alias"]), "table": _lower(a["table"])})
    return out


def _normalize_alias_joins(joins):
    out = []
    for j in joins or []:
        if not isinstance(j, dict):
            continue
        nj = dict(j)
        nj["from"] = _normalize_aliasref(j.get("from"))
        nj["to"] = _normalize_aliasref(j.get("to"))
        out.append(nj)
    return out


def _normalize_alias_filters(filters):
    out = []
    for f in filters or []:
        if not isinstance(f, dict):
            continue
        nf = dict(f)
        if isinstance(f.get("left"), dict):
            nf["left"] = _normalize_aliasref(f["left"])
        if isinstance(f.get("right"), dict):
            nf["right"] = _normalize_aliasref(f["right"])
        out.append(nf)
    return out


def _normalize_alias_select(sel):
    out = []
    for s in sel or []:
        if not isinstance(s, dict):
            continue
        ns = _normalize_aliasref(s)   # lowercases alias/column, keeps 'as'
        out.append(ns)
    return out


def _normalize_any_pred(c):
    """Lowercase identifiers in a predicate of either shape: column-form
    ({left,right}) or filter-form ({table,column}). Op/value preserved."""
    if not isinstance(c, dict):
        return c
    nc = dict(c)
    if isinstance(nc.get("left"), dict):
        nc["left"] = _normalize_colref(nc["left"])
    if isinstance(nc.get("right"), dict):
        nc["right"] = _normalize_colref(nc["right"])
    if nc.get("table") is not None:
        nc["table"] = _lower(nc["table"])
    if nc.get("column") is not None and not isinstance(nc.get("column"), dict):
        nc["column"] = _lower(nc["column"])
    return nc


def _normalize_explicit_joins(joins):
    out = []
    for j in joins or []:
        if not isinstance(j, dict) or not j.get("to_table"):
            continue
        nj = dict(j)
        if j.get("from_table") is not None:
            nj["from_table"] = _lower(j["from_table"])
        nj["to_table"] = _lower(j["to_table"])
        nj["conditions"] = [_normalize_any_pred(c) for c in (j.get("conditions") or [])
                            if isinstance(c, dict)]
        out.append(nj)
    return out


def _normalize_null_filters(filters):
    out = []
    for f in filters or []:
        if not isinstance(f, dict):
            continue
        nf = dict(f)
        if f.get("table") is not None:
            nf["table"] = _lower(f["table"])
        if f.get("column") is not None:
            nf["column"] = _lower(f["column"])
        out.append(nf)
    return out


def _normalize_compound_filters(groups):
    out = []
    for g in groups or []:
        if not isinstance(g, dict):
            continue
        ng = dict(g)
        ng["conditions"] = [_normalize_any_pred(c) for c in (g.get("conditions") or [])
                            if isinstance(c, dict)]
        out.append(ng)
    return out


def _normalize_derived_relations(specs):
    """Lowercase identifiers inside each CTE spec. The body (from_table, joins,
    select, aggregations, group_by, filters) references REAL tables. name is
    lowercased. Specs without a name + from_table + something to project are
    dropped."""
    out = []
    for r in specs or []:
        if not isinstance(r, dict) or not r.get("name") or not r.get("from_table"):
            continue
        if not (r.get("select") or r.get("aggregations")):
            continue
        nr = dict(r)
        nr["name"] = _lower(r["name"])
        nr["from_table"] = _lower(r["from_table"])
        joins = []
        for j in r.get("joins") or []:
            if not isinstance(j, dict):
                continue
            nj = dict(j)
            for k in ("from_table", "from_column", "to_table", "to_column"):
                if nj.get(k) is not None:
                    nj[k] = _lower(nj[k])
            joins.append(nj)
        nr["joins"] = joins
        nr["select"] = _normalize_list(r.get("select"))
        nr["aggregations"] = _normalize_list(r.get("aggregations"))
        nr["group_by"] = _normalize_list(r.get("group_by"))
        nr["filters"] = _normalize_list(r.get("filters"))
        out.append(nr)
    return out


def _derived_real_tables(derived_relations):
    """Underlying REAL tables across all CTE bodies (for the planner)."""
    real = []
    for r in derived_relations:
        for t in [r.get("from_table")] + [j.get("to_table") for j in r.get("joins") or []] \
                + [j.get("from_table") for j in r.get("joins") or []]:
            if t and t not in real:
                real.append(t)
    return real


def _normalize_top_per_group(specs):
    """Lowercase identifiers inside each top-per-group spec (table, order_by
    table/column, partition_by refs). rank/direction/method/include_ties are
    preserved. Malformed entries (no table or no order_by column) are dropped."""
    out = []
    for spec in specs or []:
        if not isinstance(spec, dict) or not spec.get("table"):
            continue
        ob = spec.get("order_by")
        if not isinstance(ob, dict) or not ob.get("column"):
            continue
        new = dict(spec)
        new["table"] = _lower(spec["table"])
        new["order_by"] = _normalize_colref(ob)
        if ob.get("direction") is not None:
            new["order_by"]["direction"] = str(ob["direction"]).strip().lower()
        new["partition_by"] = [
            _normalize_colref(pc) for pc in (spec.get("partition_by") or [])
            if isinstance(pc, dict)
        ]
        out.append(new)
    return out


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
def build_from_extraction(database_id, extraction, graph=None, question=None):
    """Build a MultiTableSemanticIR from an extraction dict.

    `tables` is derived as the union of the model-provided tables and every
    table referenced in select, filters, aggregations, group_by, having, and
    order_by. This fills in a list the model sometimes omits even though its
    columns are already table-qualified; it is lossless and never remaps or
    invents column references. If `graph` is provided, direct relationship
    hints between the resulting tables are attached; otherwise relationship_hints
    is empty. No path search, no table inference beyond the union, no validation.

    When `question` and `graph` are both provided, question-aware semantic
    rewrites (ir_semantics) are applied first to correct common intent errors.
    """
    extraction = extraction or {}

    if question and graph:
        extraction = apply_question_semantics(question, extraction, graph)

    select = _normalize_list(extraction.get("select"))
    filters = _normalize_list(extraction.get("filters"))
    aggregations = _normalize_list(extraction.get("aggregations"))
    group_by = _normalize_list(extraction.get("group_by"))
    having = _normalize_list(extraction.get("having"))
    order_by = _normalize_list(extraction.get("order_by"))

    provided = [_lower(t) for t in (extraction.get("tables") or [])]

    # Tables in play, used to scope bare-column resolution in column-vs-column
    # detection. Computed before normalization (group-by injection only adds
    # already-referenced tables, so this set is complete for that purpose).
    pre_tables = _union_tables(
        provided,
        [select, filters, aggregations, group_by, having, order_by],
    )

    # Deterministic, schema-aware clean-ups (year ranges, GROUP BY label in
    # SELECT, stored-value casing/booleans, column-vs-column predicates). No-op
    # when graph is None.
    select, filters, group_by = normalize_ir(
        select, filters, group_by, graph, ir_tables=pre_tables)
    # Derived output aliases (aggregate/percentage/formula names) that the
    # extractor mislabeled as physical columns are dropped from the SELECT so
    # the renderer never emits a nonexistent `table.<alias>`; the aggregation
    # carrying the alias still projects the value. A bad synthetic column can no
    # longer make the whole candidate fail with a no-such-column error.
    select = sanitize_derived_output_columns(select, aggregations, graph)

    tables = _union_tables(
        provided,
        [select, filters, aggregations, group_by, having, order_by],
    )
    # Self-join pair queries reference base tables only through aliases, so add
    # those base tables here — the planner needs real tables to resolve even
    # though the alias render path supplies its own join structure.
    aliases = _normalize_aliases(extraction.get("aliases"))
    for a in aliases:
        if a["table"] not in tables:
            tables.append(a["table"])
    # Explicit (outer) join tables: the planner needs them as real tables even
    # though the explicit-join render path supplies its own FROM/JOIN structure.
    explicit_joins = _normalize_explicit_joins(extraction.get("explicit_joins"))
    for j in explicit_joins:
        for t in (j.get("from_table"), j.get("to_table")):
            if t and t not in tables:
                tables.append(t)
    # Derived relations (CTEs): their NAMES are not real tables (the main query
    # references them), so drop any that leaked into the union, and add the CTEs'
    # underlying REAL tables so the planner can still resolve.
    derived_relations = _normalize_derived_relations(extraction.get("derived_relations"))
    main_from = _lower(extraction.get("main_from")) if extraction.get("main_from") else None
    cte_names = {r["name"] for r in derived_relations}
    tables = [t for t in tables if t not in cte_names]
    for t in _derived_real_tables(derived_relations):
        if t not in tables and t not in cte_names:
            tables.append(t)
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
        anti_exists=_normalize_anti_exists(extraction.get("anti_exists")),
        top_per_group=_normalize_top_per_group(extraction.get("top_per_group")),
        universal=_normalize_universal(extraction.get("universal")),
        set_division=_normalize_set_division(extraction.get("set_division")),
        aliases=aliases,
        alias_joins=_normalize_alias_joins(extraction.get("alias_joins")),
        alias_filters=_normalize_alias_filters(extraction.get("alias_filters")),
        alias_select=_normalize_alias_select(extraction.get("alias_select")),
        explicit_joins=explicit_joins,
        null_filters=_normalize_null_filters(extraction.get("null_filters")),
        compound_filters=_normalize_compound_filters(extraction.get("compound_filters")),
        derived_relations=derived_relations,
        main_from=main_from,
    )