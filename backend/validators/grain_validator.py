"""
validators/grain_validator.py

Stage 1/1B — GRAIN validator (RC1 of the semantic-contract plan).

Validates EVERY actionable GrainRequirement of the typed SemanticContract
against one generated SQL. A candidate must satisfy ALL high-confidence
requirements — satisfying one while ignoring another is a failure.

Fatal findings (each provable from the parsed AST + a high-confidence
requirement; aliases are always traced to their defining expression and
NEVER trusted by name):

  F1  the requirement needs AGG(measure) per entity, the SQL never computes
      that aggregate anywhere, yet it compares the raw row-level measure
      (single-row LIMIT 1 restriction is reported when present);
  F2  comparison_right_kind = aggregate_of_entity_totals, but a comparison
      side aggregates RAW measure rows: AVG(raw) — grouped or not — when the
      required per-entity aggregation is SUM/COUNT, or any groupless scalar
      aggregate over raw rows;
  F3  a query grouped by non-measure-table keys selects/filters the raw,
      nonaggregated measure column (bare child measure under grouping);
  F4  a provable two-level aggregate whose INNER aggregate is grouped
      without the entity key (totals at the wrong grain);
  F5  comparison_right_kind = aggregate_of_entity_totals with a known
      population key, but no two-level aggregate side references the
      population column anywhere in its computing scope (the "average per
      population group" is provably not population-scoped);
  F6  measure_scope = all_entity_rows (lifetime/overall), but every use of
      the required aggregate as a comparison side is computed from a
      RESTRICTED scope: LIMIT 1, MAX/MIN-equality, ROW_NUMBER()=1, a
      single-row source, or a literal qualifying-event filter on a table
      other than the measure/entity table. A side fed by one independent
      unrestricted entity-total scope passes.
  F7  (Stage 1C) comparison application: for aggregate_of_rows /
      aggregate_of_entity_totals requirements, the required measure must
      PARTICIPATE in at least one comparison predicate somewhere in the
      query (raw side, entity-total side, two-level side, or even a
      wrong-grain aggregate side — F2 handles that case). An aggregate that
      appears only in SELECT, or aliases that are never compared, do NOT
      satisfy the contract. Fatal only when every comparison side in the
      query is provably traced; any unprovable side downgrades to warning.

  F8  (final stabilization) distinct-count requirements: COUNT(column) never
      satisfies a required COUNT(DISTINCT column); a 'distinct'-looking alias
      proves nothing; and a required comparison operator/constant
      (e.g. "> 1" for "more than one type") must actually be applied.

  Derived additive measures (Stage 1C/D): SUM(x - y) and SUM(x) - SUM(y) are
  grain-equivalent; matching uses the requirement's measure_components (the
  primary column plus derived additive components), so a requirement on x is
  satisfied/validated through either form.

EVERY uncertain situation (missing/low-confidence requirement, parse
failure, unresolvable column, ambiguous grouping, unknown origin, ...)
produces at most a warning and never a fatal. No benchmark- or
domain-specific logic.
"""

from dataclasses import dataclass, field

from sqlglot import exp

from sql_analysis import ast_tools as at

__all__ = ["GrainValidation", "validate_grain"]


@dataclass
class GrainValidation:
    fatal: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    skipped: str | None = None      # reason grain validation did not apply


# ---------------------------------------------------------------------------
# evidence gathering helpers
# ---------------------------------------------------------------------------
def _same_scope_aggregates(node):
    """AggFunc nodes inside `node`'s subtree WITHOUT descending into nested
    SELECTs (those belong to other scopes)."""
    out = []
    for n in node.walk(prune=lambda x: isinstance(x, exp.Select)):
        if isinstance(n, exp.Select):
            continue
        if isinstance(n, exp.AggFunc):
            out.append(n)
    return out


def _req_targets(req):
    """All physical (table, column) pairs that count as 'the measure' for a
    requirement: the primary measure column plus any derived additive
    components (SUM(x-y) ≡ SUM(x)-SUM(y))."""
    targets = []
    if req.measure_table and req.measure_column:
        targets.append((req.measure_table, req.measure_column))
    for t, c in getattr(req, "measure_components", ()) or ():
        if (t, c) not in targets:
            targets.append((t, c))
    return targets


def _ranges_over_any(origin, targets):
    return any(at.origin_ranges_over(origin, t, c) for t, c in targets)


def _agg_over_measure(scope, agg_node, targets, idx):
    """True when this aggregate provably ranges over any requirement target —
    single-column or derived additive argument (SUM(x - y))."""
    cols = at.aggregate_arg_columns(agg_node)
    if not cols:
        return False
    for c in cols:
        origin = at.trace_column(scope, c, idx)
        if any(origin.is_physical(t, col) for t, col in targets):
            return True
    return False


def _required_agg_anywhere(parsed, targets, agg, idx):
    """AGG(<physical target>) computed in ANY scope of the query."""
    for scope in parsed.scopes:
        for node in at.scope_aggregates(scope):
            if at.aggregate_name(node) == agg \
                    and _agg_over_measure(scope, node, targets, idx):
                return True
    return False


_OP_OF = {exp.GT: ">", exp.GTE: ">=", exp.LT: "<", exp.LTE: "<=",
          exp.EQ: "=", exp.NEQ: "!="}
_FLIP = {">": "<", "<": ">", ">=": "<=", "<=": ">=", "=": "=", "!=": "!="}


def _literal_value(node):
    """Numeric value of a literal comparison side, or None (placeholder,
    string, expression, ...)."""
    while isinstance(node, exp.Paren):
        node = node.this
    if isinstance(node, exp.Literal) and not node.is_string:
        try:
            return float(node.this)
        except (TypeError, ValueError):
            return None
    return None


def _agg_side_provable(origin):
    """True when an aggregate origin's argument is fully traced: a physical
    inner column, provable additive components, or an inner aggregate that is
    itself provable (two-level). False = the aggregate could range over
    anything, so absence of the measure cannot be proven from it."""
    if origin is None or origin.kind != "aggregate":
        return True
    if origin.components:
        return True
    inner = origin.inner
    if inner is None:
        return False
    if inner.kind == "physical":
        return True
    if inner.kind == "aggregate":
        return _agg_side_provable(inner)
    return False


def _comparison_sides(parsed, idx):
    """Yield (scope, side_node, origin) for both sides of every comparison
    in every scope."""
    for scope in parsed.scopes:
        for comp in at.comparison_predicates(scope):
            for side in (comp.this, comp.expression):
                yield scope, side, at.side_origin(parsed, scope, side, idx)


def _scope_restrictions(parsed, scope, measure_table, entity_table, idx,
                        _depth=0):
    """Provable row restrictions of a scope that computes an all-entity-rows
    measure: LIMIT 1, extremum equality, ROW_NUMBER()=1, literal filters on
    tables OTHER than the measure/entity table (a qualifying-event condition
    contaminating the measure), and the same restrictions on source scopes
    that feed the measure."""
    notes = []
    if _depth > 3 or scope is None:
        return notes
    if at.scope_has_limit_one(scope):
        notes.append("LIMIT 1 restricts the measure to a single row")
    notes.extend(at.extremum_equalities(parsed, scope, idx))
    for t, c in at.literal_filters(scope, idx):
        if t not in (measure_table, entity_table):
            notes.append(f"measure scope is filtered by an unrelated "
                         f"qualifying condition on {t}.{c}")
    # restrictions of source scopes actually FEEDING this one (a CTE that is
    # merely visible to the scope, but never selected from, is not an input)
    for src in at.scope_selected_sources(scope).values():
        if not isinstance(src, at.Scope):
            continue
        notes.extend(_scope_restrictions(parsed, src, measure_table,
                                         entity_table, idx, _depth + 1))
    return notes


def _grouped_bare_measure(parsed, table, column, idx):
    """Scopes that GROUP BY keys of OTHER tables while using the raw measure
    column outside any aggregate (provable F3 evidence)."""
    hits = []
    for scope in parsed.scopes:
        gcols = at.group_by_columns(scope)
        if gcols is None or not gcols:
            continue
        gorigins = [at.trace_column(scope, g, idx) for g in gcols]
        if any(o.kind != "physical" for o in gorigins):
            continue
        if any(o.table == table for o in gorigins):
            continue
        for col in at.columns_outside_aggregates(scope):
            origin = at.trace_column(scope, col, idx)
            if origin.is_physical(table, column):
                keys = ", ".join(f"{o.table}.{o.column}" for o in gorigins)
                hits.append(f"query groups by {keys} but uses the "
                            f"nonaggregated child measure {table}.{column}")
                break
    return hits


def _has_comparison_obligation(req):
    """A requirement carries an actionable COMPARISON obligation ONLY when the
    question actually compares the measure: an explicit comparison operator, or
    a defined comparison constant. `comparison_right_kind` alone — populated
    merely because the measure is grouped by an entity, or because the phrase
    contains "per"/"ratio" — is NOT a comparison obligation. Output-only metrics
    (a value projected in SELECT) have no comparison obligation."""
    return req.comparison_operator is not None \
        or req.comparison_constant is not None


def _measure_projected(parsed, targets, agg, idx):
    """True when AGG(<measure>) is computed anywhere (an output-only metric is
    validated by its presence in the query's SELECT/computation, not by a
    comparison predicate)."""
    return _required_agg_anywhere(parsed, targets, agg, idx)


def _has_agg_ancestor(node):
    """True when `node` sits inside an aggregate function (e.g. a CASE-WHEN
    predicate inside SUM(CASE ...)). Such an inner predicate is part of a
    conditional aggregate, NOT a standalone grain comparison of the measure."""
    p = node.parent
    while p is not None:
        if isinstance(p, exp.AggFunc):
            return True
        p = p.parent
    return False


def _measure_in_compared_aggregate(parsed, targets, idx):
    """True when the measure participates in a comparison THROUGH an aggregate
    of any function — including a CONDITIONAL aggregate like
    SUM(CASE WHEN status = 'x' THEN 1 ELSE 0 END) > 0, a valid conditional count
    of the measure. The aggregate function need not equal the required one; what
    matters is that the measure appears inside an aggregate that is compared.
    Columns anywhere inside the aggregate (argument OR a CASE condition) count."""
    for scope in parsed.scopes:
        for comp in at.comparison_predicates(scope):
            if _has_agg_ancestor(comp):
                continue
            for side in (comp.this, comp.expression):
                for agg_node in _same_scope_aggregates(side):
                    for coln in agg_node.find_all(exp.Column):
                        origin = at.trace_column(scope, coln, idx)
                        if any(origin.is_physical(t, c) for t, c in targets):
                            return True
    return False


def _raw_comparisons_all_peer(pairs, targets):
    """True when EVERY comparison that uses the raw measure has its OTHER side
    also a raw physical value (a row-vs-peer/row-vs-raw comparison, e.g.
    'balance > one of their orders'). Such a comparison requires NO aggregate,
    so the 'aggregate never computed' rule must not fire on it."""
    saw = False
    for comp, lo, ro in pairs:
        for origin, other in ((lo, ro), (ro, lo)):
            if origin is not None and origin.kind == "physical" \
                    and any(origin.is_physical(t, c) for t, c in targets):
                saw = True
                if other is None or other.kind != "physical":
                    return False
    return saw


def _grouped_by_entity(parsed, req, idx):
    """True when some scope GROUPs BY the requirement's entity key — i.e. the
    query is a per-entity comparison context ("entities with >= N distinct X"),
    as opposed to a single scalar output ("how many distinct X")."""
    for scope in parsed.scopes:
        gcols = at.group_by_columns(scope)
        if not gcols:
            continue
        for gcol in gcols:
            o = at.trace_column(scope, gcol, idx)
            if getattr(o, "kind", None) == "physical" \
                    and o.column == req.entity_key_column:
                return True
    return False


def _scalar_distinct_count_present(parsed, req, idx):
    """True when a COUNT(DISTINCT x) exists where x is the measure OR the entity
    key. 'How many distinct carriers' is answered by COUNT(DISTINCT carrier)
    even when the contract's measure column is a proxy (e.g. shipment_id)."""
    targets = _req_targets(req)
    ek = req.entity_key_column
    for scope in parsed.scopes:
        for node in at.scope_aggregates(scope):
            if at.aggregate_name(node) != "count" \
                    or not isinstance(node.this, exp.Distinct):
                continue
            for coln in node.find_all(exp.Column):
                o = at.trace_column(scope, coln, idx)
                if any(o.is_physical(t, c) for t, c in targets) \
                        or getattr(o, "column", None) == ek:
                    return True
    return False


def _population_referenced(scope, pop_table, pop_column):
    """True when the population column is referenced ANYWHERE inside this
    scope's expression subtree (grouping, correlation, join — all count).
    Name-based and lenient on purpose: a false 'referenced' only suppresses
    a fatal, never creates one."""
    if scope is None:
        return False
    for coln in scope.expression.find_all(exp.Column):
        if (coln.name or "").lower() == pop_column:
            return True
    return False


# ---------------------------------------------------------------------------
# per-requirement validation
# ---------------------------------------------------------------------------
def _validate_requirement(parsed, req, idx, v, tag):
    T, C, A = req.measure_table, req.measure_column, req.measure_aggregation
    entity = f"{req.entity_table}.{req.entity_key_column}"
    required = f"{A.upper()}({T}.{C}) per {entity}"
    kind = req.comparison_right_kind
    pop = (req.population_column
           if req.population_column and req.population_table else None)
    rc = {"required": required}

    targets = _req_targets(req)
    agg_found = _required_agg_anywhere(parsed, targets, A, idx)
    rc["required_aggregate_found"] = agg_found

    raw_sides = []            # raw physical measure used as a comparison side
    entity_total_uses = []    # (computing_scope, origin|None) of AGG(T.C) sides
    two_level_sides = []      # outer aggregate over an inner AGG(T.C)
    agg_over_raw = []         # aggregates ranging over raw measure rows
    unproven_sides = 0        # comparison sides whose origin can't be traced
    pairs = []                # (comp_node, origin_left, origin_right)

    for scope in parsed.scopes:
        for comp in at.comparison_predicates(scope):
            if _has_agg_ancestor(comp):
                continue          # part of a conditional aggregate, not a grain comparison
            side_origins = []
            for side in (comp.this, comp.expression):
                origin = at.side_origin(parsed, scope, side, idx)
                side_origins.append(origin)
                if origin.kind in ("unknown", "window"):
                    unproven_sides += 1
                if origin.kind == "physical" \
                        and any(origin.is_physical(t, c) for t, c in targets):
                    raw_sides.append(origin)
                if origin.kind == "aggregate":
                    if _ranges_over_any(origin, targets):
                        if origin.aggregate == A:
                            entity_total_uses.append((origin.scope, origin))
                        if kind == "aggregate_of_entity_totals" and (
                                not origin.group_keys
                                or (origin.aggregate == "avg"
                                    and A in ("sum", "count"))):
                            agg_over_raw.append(origin)
                    elif origin.inner is not None \
                            and origin.inner.kind == "aggregate" \
                            and origin.inner.aggregate == A \
                            and _ranges_over_any(origin.inner, targets):
                        two_level_sides.append(origin)
                    elif not _agg_side_provable(origin):
                        # an aggregate over an unprovable argument could hide
                        # the measure — never treat as proof of absence
                        unproven_sides += 1
                # arithmetic sides not traced to a composite: inspect
                # same-scope aggregates inside the side itself (safety net)
                if origin.kind == "unknown" and isinstance(side, exp.Expression):
                    for agg_node in _same_scope_aggregates(side):
                        if at.aggregate_name(agg_node) == A \
                                and _agg_over_measure(scope, agg_node,
                                                      targets, idx):
                            entity_total_uses.append((scope, None))
                            break
            pairs.append((comp, side_origins[0], side_origins[1]))

    rc["raw_comparison_sides"] = len(raw_sides)
    rc["entity_total_uses"] = len(entity_total_uses)
    rc["two_level_sides"] = len(two_level_sides)

    # Comparison-obligation gating (RC1): comparison-application fatals fire
    # only when the question actually compares the measure. Output-only metrics,
    # scalar counts, row-vs-peer, and conditional aggregates are recognized.
    has_obl = _has_comparison_obligation(req)
    row_vs_peer = _raw_comparisons_all_peer(pairs, targets)
    cond_measure = _measure_in_compared_aggregate(parsed, targets, idx)
    rc["comparison_obligation"] = has_obl
    rc["row_vs_peer_comparison"] = row_vs_peer
    rc["conditional_aggregate_use"] = cond_measure

    # F1 — raw row-level measure compared; required aggregate NOWHERE -------
    # Fatal ONLY for a genuine aggregate-comparison obligation. A row-vs-peer
    # comparison ("balance > one of their orders": both sides raw) or a
    # conditional aggregate needs no standalone aggregate, so those are advisory.
    if raw_sides and not agg_found:
        if not row_vs_peer and not cond_measure:
            note = (" (and the value is restricted to a single row via LIMIT 1, "
                    "not the entity total)"
                    if any(s.limited_to_one_row for s in raw_sides) else "")
            v.fatal.append(
                f"grain violation{tag}: contract requires {required}, but the "
                f"SQL compares the raw row-level value {T}.{C} and never "
                f"computes {A.upper()}({C}){note}")
        else:
            v.warnings.append(
                f"grain note{tag}: {T}.{C} is compared as a raw value without a "
                f"standalone {A.upper()} — consistent with a row-vs-peer or "
                f"output-only reading; not treated as fatal")
    elif raw_sides and agg_found:
        v.warnings.append(
            f"grain note{tag}: {required} is computed, but a raw {T}.{C} "
            f"also appears in a comparison — verify the comparison grain")

    # F2 — aggregate over raw rows where entity totals were required --------
    if kind == "aggregate_of_entity_totals" and agg_over_raw:
        scale_mismatch = [o for o in agg_over_raw
                          if (o.aggregate == "avg" and A in ("sum", "count"))]
        if scale_mismatch:
            v.fatal.append(
                f"grain violation{tag}: the comparison uses AVG({T}.{C}) over "
                f"raw rows where a {A.upper()} of per-entity totals per {entity} "
                f"is required — an average of raw rows is a different scale than "
                f"a total of per-entity {A.upper()}s")
        else:
            aggname = (agg_over_raw[0].aggregate or "aggregate").upper()
            v.warnings.append(
                f"grain note{tag}: {aggname}({T}.{C}) is computed over raw rows; "
                f"for a row-vs-group-average or group-vs-global comparison of the "
                f"same measure this is the correct right side, so it is advisory "
                f"only, never fatal.")

    # F3 — grouped query uses the bare, nonaggregated child measure ---------
    # Not fatal for a row-vs-peer comparison (the raw measure is legitimately
    # compared row-to-row, e.g. "balance > one of their orders"), which needs
    # no aggregate.
    for msg in _grouped_bare_measure(parsed, T, C, idx):
        if row_vs_peer:
            v.warnings.append(f"grain note{tag}: {msg} — consistent with a "
                              f"row-vs-peer comparison; advisory only")
        else:
            v.fatal.append(f"grain violation{tag}: contract requires {required}, "
                           f"but the {msg}")

    # F4 — two-level side whose INNER aggregate is at the wrong grain -------
    # (the entity key is matched by column NAME as well — per-entity totals
    # legitimately group by the child table's FK copy of the key)
    for side in two_level_sides:
        gkeys = side.inner.group_keys or []
        if gkeys and all(k.kind == "physical" for k in gkeys):
            if not any(k.column == req.entity_key_column for k in gkeys):
                keys = ", ".join(f"{k.table}.{k.column}" for k in gkeys)
                v.fatal.append(
                    f"grain violation{tag}: the inner totals are grouped by "
                    f"{keys}, not by the required entity key {entity}")

    # F5 — entity-total aggregate ignores the required population -----------
    if kind == "aggregate_of_entity_totals" and pop and two_level_sides:
        if not any(_population_referenced(s.scope, req.population_table, pop)
                   for s in two_level_sides):
            v.fatal.append(
                f"grain violation{tag}: the aggregate of per-entity totals "
                f"never references the required comparison population "
                f"{req.population_table}.{pop} (no grouping, correlation, "
                f"or join on it)")

    # F6 — lifetime/all-rows measure computed from a restricted scope -------
    if req.measure_scope == "all_entity_rows" and entity_total_uses:
        side_restrictions = []
        for cscope, origin in entity_total_uses:
            notes = _scope_restrictions(parsed, cscope, T, req.entity_table, idx)
            if origin is not None and origin.inner is not None \
                    and origin.inner.limited_to_one_row \
                    and "LIMIT 1 restricts the measure to a single row" \
                    not in notes:
                notes.append("LIMIT 1 restricts the measure to a single row")
            side_restrictions.append(notes)
        rc["scope_restrictions"] = [n for notes in side_restrictions
                                    for n in notes]
        if side_restrictions and all(side_restrictions):
            uniq = list(dict.fromkeys(rc["scope_restrictions"]))
            v.fatal.append(
                f"grain violation{tag}: contract requires the measure over "
                f"ALL rows of the entity (lifetime/overall {required}), but "
                f"every {A.upper()}({C}) used in the comparison is computed "
                f"from a restricted scope: " + "; ".join(uniq))
        elif any(side_restrictions):
            v.warnings.append(
                f"grain note{tag}: one {A.upper()}({C}) is computed from a "
                f"restricted scope, but an unrestricted entity total is also "
                f"used — verify the measure scope")

    # F7 — the required comparison is never APPLIED in any predicate --------
    # (an aggregate that exists only in SELECT, or aliases that are never
    # compared, do not satisfy a comparison requirement)
    participated = bool(raw_sides or entity_total_uses
                        or two_level_sides or agg_over_raw) or cond_measure
    rc["comparison_applied"] = participated
    rc["unproven_comparison_sides"] = unproven_sides
    if kind in ("aggregate_of_rows", "aggregate_of_entity_totals") \
            and not participated:
        if not has_obl:
            # OUTPUT-ONLY metric: there is no comparison obligation, so validate
            # that the required aggregate is COMPUTED (projected in SELECT),
            # never demand it appear in WHERE/HAVING.
            rc["output_metric"] = True
            rc["output_metric_projected"] = agg_found
            if not agg_found:
                v.warnings.append(
                    f"grain note{tag}: output metric {required} is not clearly "
                    f"computed in the query — verify the SELECT expression")
        elif unproven_sides:
            v.warnings.append(
                f"grain note{tag}: cannot prove the required comparison "
                f"({required}) is applied — a comparison side could not be "
                f"traced")
        else:
            v.fatal.append(
                f"grain violation{tag}: the required aggregate comparison is "
                f"never applied in WHERE or HAVING (contract requires "
                f"comparing {required}, but no comparison predicate uses the "
                f"measure {T}.{C})")

    # F8 — distinct-count requirements (Part C) -----------------------------
    # COUNT(column) never satisfies COUNT(DISTINCT column); an alias name
    # containing "distinct" proves nothing (aliases are always traced); and a
    # required comparison operator/constant must actually be applied.
    if req.distinct and A == "count":
        count_sides = [o for _, o in entity_total_uses if o is not None]
        nondistinct = [o for o in count_sides if not o.distinct]
        rc["distinct_count_sides"] = len(count_sides) - len(nondistinct)
        if nondistinct:
            v.fatal.append(
                f"grain violation{tag}: contract requires COUNT(DISTINCT "
                f"{C}) per {entity}, but the SQL compares COUNT({C}) without "
                f"DISTINCT (a 'distinct'-looking alias proves nothing)")
        elif not count_sides:
            # A distinct count NOT used in any comparison predicate is a scalar
            # OUTPUT ("how many distinct X") ONLY when the query is not grouped
            # by the entity AND the correct distinct count is actually computed.
            # In that case validate it in SELECT, never demand a predicate (a
            # contract operator here is a population row-filter on another
            # column, e.g. "sale price above 500"). A per-entity grouped
            # comparison, or a missing/mis-columned count, remains fatal.
            scalar_ok = agg_found or _scalar_distinct_count_present(parsed, req, idx)
            if scalar_ok and not _grouped_by_entity(parsed, req, idx):
                rc["scalar_distinct_count_output"] = True
                rc["scalar_distinct_count_projected"] = True
            elif unproven_sides:
                v.warnings.append(
                    f"grain note{tag}: cannot prove the required "
                    f"COUNT(DISTINCT {C}) comparison is applied")
            else:
                v.fatal.append(
                    f"grain violation{tag}: contract requires a "
                    f"COUNT(DISTINCT {C}) comparison per {entity}, but no "
                    f"comparison predicate uses it")
        if count_sides and not nondistinct \
                and req.comparison_operator \
                and req.comparison_constant is not None:
            matched, mismatches, unprovable = False, 0, 0
            for comp, lo, ro in pairs:
                for origin, other_node, flipped in (
                        (lo, comp.expression, False),
                        (ro, comp.this, True)):
                    if origin.kind != "aggregate" or origin.aggregate != "count" \
                            or not origin.distinct \
                            or not _ranges_over_any(origin, targets):
                        continue
                    op = _OP_OF.get(type(comp))
                    if op is None:
                        unprovable += 1
                        continue
                    if flipped:
                        op = _FLIP[op]
                    val = _literal_value(other_node)
                    if val is None:
                        unprovable += 1        # placeholder / expression
                    elif op == req.comparison_operator \
                            and val == req.comparison_constant:
                        matched = True
                    else:
                        mismatches += 1
            if not matched and mismatches and not unprovable:
                v.fatal.append(
                    f"grain violation{tag}: the required comparison "
                    f"COUNT(DISTINCT {C}) {req.comparison_operator} "
                    f"{req.comparison_constant:g} is not applied "
                    f"(a different operator/constant is used)")
            rc["distinct_comparison_matched"] = matched

    return rc


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def validate_grain(contract, sql, idx=None) -> GrainValidation:
    """Validate one SQL string against every actionable requirement of the
    typed contract. Never raises; every uncertain path degrades to
    skip/warning."""
    v = GrainValidation()
    if contract is None:
        v.skipped = "no typed contract"
        return v
    reqs = list(getattr(contract, "actionable_requirements", []) or [])
    if not reqs:
        v.skipped = "contract not actionable (no high-confidence requirement)"
        return v

    parsed = at.parse_sql(sql)
    if not parsed.ok:
        v.skipped = f"SQL not analyzable: {parsed.error}"
        return v

    many = len(reqs) > 1
    for n, req in enumerate(reqs, start=1):
        tag = f" [requirement {n}/{len(reqs)}]" if many else ""
        try:
            rc = _validate_requirement(parsed, req, idx, v, tag)
        except Exception as exc:               # analysis bug → advisory only
            rc = {"error": f"{type(exc).__name__}: {exc}"}
            v.warnings.append(f"grain validation incomplete{tag}: "
                              f"{type(exc).__name__}: {exc}")
        v.checks[f"requirement_{n}"] = rc

    v.checks["fatal_count"] = len(v.fatal)
    return v
