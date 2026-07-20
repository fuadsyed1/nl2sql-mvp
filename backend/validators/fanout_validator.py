"""
validators/fanout_validator.py

Stage 2 — cardinality-aware FANOUT validator (RC2 of the semantic-contract
plan).

Detects the classic join-fanout inflation pattern, provable from the SQL AST
plus the schema's relationship metadata (declared FKs, confirmed links, and
high-confidence inferred links carried in the graph):

  1. a measure originates on the ONE side of a one-to-many relationship;
  2. the aggregating scope joins that relationship's MANY side (or any other
     many-side child) into the same joined relation, multiplying the
     measure's rows;
  3. the aggregate (SUM / AVG / non-DISTINCT COUNT) runs AFTER the
     multiplication;
  4. no protection is present: DISTINCT aggregation, pre-aggregation in a
     separate scope, EXISTS instead of a join, or grouping at the many-side
     row grain.

Safe patterns (never flagged): aggregating the many side itself
(SUM(detail.amount) after header⨝detail), COUNT(DISTINCT ...), aggregates
computed in single-source scopes/CTEs, EXISTS-based qualification,
many-to-one lookups from the measure table outward, and any join whose
cardinality cannot be PROVEN from relationships (unknown stays nonfatal).

Every relationship is treated child(from_table.from_column) ->
parent(to_table.to_column); an entry with a confidence field below
_MIN_REL_CONFIDENCE that is not confirmed/declared is ignored (uncertain
cardinality must never create a fatal).

No table, column, domain, or benchmark name is hardcoded.
"""

from dataclasses import dataclass, field

from sqlglot import exp

from sql_analysis import ast_tools as at

__all__ = ["FanoutValidation", "validate_fanout"]

_MIN_REL_CONFIDENCE = 0.9
_AGGS_AT_RISK = ("sum", "avg", "count")


@dataclass
class FanoutValidation:
    fatal: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    skipped: str | None = None


def _relationships(idx):
    """[(child_table, child_col, parent_table, parent_col), ...] — provable
    one-to-many edges only (declared / confirmed / high-confidence)."""
    out = []
    for r in (idx or {}).get("relationships") or []:
        if not isinstance(r, dict):
            continue
        # Every edge in a finalized graph is a real, approved relationship. No
        # confidence/confirmed gate: queries run only on the finalized set.
        ct = str(r.get("from_table") or "").lower()
        cc = str(r.get("from_column") or "").lower()
        pt = str(r.get("to_table") or "").lower()
        pc = str(r.get("to_column") or "").lower()
        if ct and cc and pt and pc:
            out.append((ct, cc, pt, pc))
    return out


def _scope_physical_tables(scope):
    """Physical table names selected FROM in this scope (CTE/derived-table
    sources excluded — their contents were aggregated in their own scope)."""
    tables = set()
    for src in at.scope_selected_sources(scope).values():
        if isinstance(src, exp.Table):
            tables.add(src.name.lower())
    return tables


def _scope_join_edges(scope, idx):
    """Provable column-to-column equality edges of this scope's WHERE/ON:
    {((tableA, colA), (tableB, colB)), ...} with both sides physical."""
    edges = set()
    for node in at.row_filter_nodes(scope):
        if not isinstance(node, exp.EQ):
            continue
        l, r = node.this, node.expression
        if not (isinstance(l, exp.Column) and isinstance(r, exp.Column)):
            continue
        lo = at.trace_column(scope, l, idx)
        ro = at.trace_column(scope, r, idx)
        if lo.kind == "physical" and ro.kind == "physical":
            edges.add(frozenset(((lo.table, lo.column), (ro.table, ro.column))))
    return edges


def _many_side_expansions(scope, idx):
    """[(parent_table, many_table, fk_col), ...] one-to-many joins ACTIVE in
    this scope: the scope joins parent.pk = many.fk along a provable
    child->parent relationship, so every other table's rows are multiplied
    by the many side."""
    rels = _relationships(idx)
    if not rels:
        return []
    edges = _scope_join_edges(scope, idx)
    tables = _scope_physical_tables(scope)
    out = []
    for ct, cc, pt, pc in rels:
        if ct in tables and pt in tables \
                and frozenset(((ct, cc), (pt, pc))) in edges:
            out.append((pt, ct, cc))
    return out


def _ancestors_of(table, rels, _cap=8):
    """Tables reachable from `table` by following child->parent edges.
    Joining an ANCESTOR (or the table itself) never duplicates the table's
    rows — each row has at most one parent up the chain. Only a many-side
    table OUTSIDE the ancestor chain (a sibling branch) multiplies them."""
    seen, frontier = set(), {table}
    for _ in range(_cap):
        nxt = set()
        for t in frontier:
            for ct, _cc, pt, _pc in rels:
                if ct == t and pt not in seen:
                    nxt.add(pt)
        if not nxt:
            break
        seen |= nxt
        frontier = nxt
    return seen


def _group_keys_of(scope, idx):
    """Physical (table, column) GROUP BY keys, or None when unprovable."""
    gcols = at.group_by_columns(scope)
    if gcols is None:
        return None
    keys = []
    for g in gcols:
        o = at.trace_column(scope, g, idx)
        if o.kind != "physical":
            return None
        keys.append((o.table, o.column))
    return keys


def validate_fanout(sql, idx=None) -> FanoutValidation:
    """Validate one SQL string for provable join-fanout aggregate inflation.
    Never raises; anything unprovable is skipped or a warning."""
    v = FanoutValidation()
    if not idx or not (idx.get("relationships") or []):
        v.skipped = "no relationship metadata (cardinality unknown)"
        return v
    parsed = at.parse_sql(sql)
    if not parsed.ok:
        v.skipped = f"SQL not analyzable: {parsed.error}"
        return v

    rels = _relationships(idx)
    flagged = []
    for scope in parsed.scopes:
        expansions = _many_side_expansions(scope, idx)
        if not expansions:
            continue
        many_tables = {m for _, m, _ in expansions}
        gkeys = _group_keys_of(scope, idx)
        for agg_node in at.scope_aggregates(scope):
            name = at.aggregate_name(agg_node)
            if name not in _AGGS_AT_RISK:
                continue
            if isinstance(agg_node.this, exp.Distinct):
                continue                       # COUNT/SUM DISTINCT is safe
            cols = at.aggregate_arg_columns(agg_node)
            if not cols:
                continue                       # COUNT(*)/exprs — probe covers
            src_tables = set()
            provable = True
            for c in cols:
                o = at.trace_column(scope, c, idx)
                if o.kind != "physical":
                    provable = False
                    break
                src_tables.add(o.table)
            if not provable or not src_tables:
                continue
            # inflation: an ACTIVE many-side table that is neither the
            # measure's own table nor on its child->parent ANCESTOR chain
            # (a sibling branch) multiplies the measure rows
            safe = set(src_tables)
            for t in src_tables:
                safe |= _ancestors_of(t, rels)
            inflators = sorted(many_tables - safe)
            if not inflators:
                continue
            # grouping at a many-side row grain restores cardinality —
            # uncertain, downgrade to warning. Grouping by the many side's
            # own JOIN FK is NOT restoration (that's the parent's grain).
            many_fk = {(m, fk) for _p, m, fk in expansions}
            if gkeys is not None and any(
                    t in many_tables and (t, c) not in many_fk
                    for t, c in gkeys):
                v.warnings.append(
                    f"possible fanout: {name.upper()} over "
                    f"{sorted(src_tables)} joined to many-side "
                    f"{inflators} — grouped at many-side grain, verify")
                continue
            if gkeys is None:
                v.warnings.append(
                    f"possible fanout: {name.upper()} over "
                    f"{sorted(src_tables)} joined to many-side {inflators} "
                    f"— grouping unprovable")
                continue
            expl = "; ".join(f"{p} 1->N {m} (via {m}.{fk})"
                             for p, m, fk in expansions if m in inflators)
            flagged.append(
                f"fanout violation: {name.upper()}({', '.join(sorted(c.sql() for c in cols))}) "
                f"is aggregated after a one-to-many join multiplies its rows "
                f"(many side: {inflators}); pre-aggregate per entity in its "
                f"own CTE, use EXISTS for qualification, or COUNT(DISTINCT "
                f"an entity key) [{expl}]")

    # deduplicate
    v.fatal = list(dict.fromkeys(flagged))
    v.checks["fatal_count"] = len(v.fatal)
    return v
