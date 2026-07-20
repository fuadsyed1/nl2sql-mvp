"""
sql_candidates/semantic_obligations.py

RC3 support — candidate semantic-obligation profiling, canonical AST signatures,
and generation-lineage keys used by the selector's consensus step.

Everything here is schema-generic and contract/AST-driven: no database id, test
id, table/column name, question text, literal, or source-specific preference is
hardcoded. The profile reuses the signals the scorer already computed
(candidate.validation: fatal, illegal_joins, grain_contract, fanout, checklist)
plus a few parsed-AST checks, so it never re-runs execution and never treats
execution success or table coverage as correctness.

Three things are exported:

  * compute_profile(...) -> a structured obligation profile + eligibility tier.
  * canonical_signature(sql) -> a hashable, meaning-preserving AST signature.
    Formatting, quoting, alias names and commutative ordering are normalized
    away; output columns, aggregate functions, formula operands, join type,
    join predicates, filters, grouping, HAVING and set operators are preserved.
  * lineage_family(source) -> the correlated generation lineage a candidate
    belongs to (direct/grain/variant/repair are one correlated family, the
    extraction variants another), so correlated duplicates cannot each count as
    independent consensus evidence.
"""

from sqlglot import exp, parse_one

__all__ = [
    "compute_profile", "canonical_signature", "lineage_family",
    "is_eligible", "dominates", "override_dominates", "MANDATORY", "GATING",
]

# The mandatory obligations that gate eligibility. A candidate that APPLIES a
# mandatory obligation but does not satisfy it is "semantically incomplete".
GATING = (
    "required_output_aggregate_satisfied",
    "required_formula_satisfied",
    "required_set_conditions_satisfied",
)

MANDATORY = (
    "required_outputs_satisfied",
    "required_aggregates_satisfied",
    "required_output_aggregate_satisfied",
    "required_formula_satisfied",
    "required_group_keys_satisfied",
    "required_set_conditions_satisfied",
    "required_relationship_roles_satisfied",
    "requested_grain_satisfied",
    "population_preserved",
)


# ---------------------------------------------------------------------------
# parsing + normalization helpers
# ---------------------------------------------------------------------------
def _parse(sql):
    try:
        return parse_one(sql, read="sqlite")
    except Exception:
        return None


def _norm(node):
    """Meaning-preserving normalized SQL string of an expression: table
    qualifiers dropped, identifiers unquoted + lowercased, alias names ignored
    (the underlying expression is kept), whitespace collapsed."""
    if node is None:
        return ""
    n = node.copy()
    if isinstance(n, exp.Alias):
        n = n.this.copy()
    for col in n.find_all(exp.Column):
        col.set("table", None)
        col.set("db", None)
        col.set("catalog", None)
    for ident in n.find_all(exp.Identifier):
        try:
            ident.set("quoted", False)
            if isinstance(ident.this, str):
                ident.set("this", ident.this.lower())
        except Exception:
            pass
    try:
        return " ".join(n.sql(dialect="sqlite").lower().split())
    except Exception:
        return " ".join(str(n).lower().split())


def _select_scopes(tree):
    """Every Select node (outer + subqueries + set-operation branches)."""
    return list(tree.find_all(exp.Select)) if tree is not None else []


def _output_expressions(select):
    return [e for e in (select.expressions or [])
            if not isinstance(e, exp.Star)]


def _has_aggregate(node):
    return node is not None and any(True for _ in node.find_all(exp.AggFunc))


def _aggregate_in_projection(select):
    return any(_has_aggregate(e) for e in (select.expressions or []))


def _referenced_columns(node):
    if node is None:
        return set()
    return {(c.name or "").lower() for c in node.find_all(exp.Column)}


def _set_operation(tree):
    for cls, name in ((exp.Union, "union"), (exp.Intersect, "intersect"),
                      (exp.Except, "except")):
        if tree is not None and isinstance(tree, cls):
            return name
        if tree is not None and next(iter(tree.find_all(cls)), None) is not None:
            return name
    return None


# ---------------------------------------------------------------------------
# canonical signature (semantic duplicate detection)
# ---------------------------------------------------------------------------
def canonical_signature(sql):
    """A hashable signature capturing the MEANING of the query. Two candidates
    with the same signature are semantic duplicates (formatting / quoting /
    alias / commutative-order differences only)."""
    tree = _parse(sql)
    if tree is None:
        return ("unparsed", " ".join((sql or "").lower().split()))
    setop = _set_operation(tree)
    parts = []
    for sel in _select_scopes(tree):
        outputs = frozenset(_norm(e) for e in _output_expressions(sel))
        froms = frozenset((t.name or "").lower() for t in sel.find_all(exp.Table))
        joins = frozenset(
            (str(j.args.get("kind") or j.args.get("side") or "inner").lower(),
             _norm(j.args.get("on"))) for j in sel.find_all(exp.Join))
        where = sel.args.get("where")
        wparts = frozenset(_norm(p) for p in _split_and(where.this)) \
            if where else frozenset()
        group = sel.args.get("group")
        gparts = frozenset(_norm(g) for g in (group.expressions if group else []))
        having = sel.args.get("having")
        hparts = frozenset(_norm(p) for p in _split_and(having.this)) \
            if having else frozenset()
        distinct = bool(sel.args.get("distinct"))
        parts.append((outputs, froms, joins, wparts, gparts, hparts, distinct))
    return (setop, tuple(parts))


def _split_and(node):
    """Flatten an AND tree into its conjuncts (order-insensitive downstream)."""
    if node is None:
        return []
    if isinstance(node, exp.And):
        return _split_and(node.this) + _split_and(node.expression)
    if isinstance(node, exp.Paren):
        return _split_and(node.this)
    return [node]


# ---------------------------------------------------------------------------
# generation lineage
# ---------------------------------------------------------------------------
def lineage_family(source):
    """Correlated generation lineage. direct SQL, its grain/variant siblings and
    a repair derived from them are ONE correlated family; the extraction
    variants (primary / variant_n) another. Independent agreement counts only
    across DIFFERENT families."""
    s = (source or "").lower()
    if s.startswith("llm_sql_direct") or s == "llm_sql_repair" or s == "repair":
        return "direct"
    if s in ("llm_primary",) or s.startswith("llm_variant"):
        return "extraction"
    if s == "query_family":
        return "family"
    if s == "semantic_join_path":
        return "semantic_path"
    return s or "unknown"


# ---------------------------------------------------------------------------
# obligation profile
# ---------------------------------------------------------------------------
def _applies(checklist, contract):
    """Which mandatory obligations the QUESTION imposes (only these gate
    eligibility; an obligation the question does not impose is trivially met)."""
    cl = checklist or {}
    shape = (cl.get("required_sql_shape") or "").lower()
    applies = set()
    if cl.get("output_columns"):
        applies.add("required_outputs_satisfied")
    if shape == "group_by_having" or cl.get("required_group_keys") \
            or (contract is not None and getattr(contract, "actionable_requirements", [])):
        applies.add("required_aggregates_satisfied")
    if cl.get("required_group_keys"):
        applies.add("required_group_keys_satisfied")
    if shape in ("set_operation",) or _formula_components(contract):
        if _formula_components(contract):
            applies.add("required_formula_satisfied")
        if shape == "set_operation":
            applies.add("required_set_conditions_satisfied")
    # grain / relationship / population always apply (they only ever fire on a
    # real defect; a clean query trivially satisfies them)
    applies.update({"required_relationship_roles_satisfied",
                    "requested_grain_satisfied", "population_preserved"})
    return applies


def _formula_components(contract):
    if contract is None:
        return []
    comps = []
    for r in getattr(contract, "requirements", ()) or ():
        for tc in getattr(r, "measure_components", ()) or ():
            comps.append(tuple(tc))
    return comps


def compute_profile(sql, validation, checklist, contract, idx=None):
    """Structured obligation profile for one candidate. Reuses the scorer's
    validation signals + parsed-AST checks. Never raises."""
    v = validation or {}
    cl = checklist or {}
    tree = _parse(sql)
    selects = _select_scopes(tree)
    outer = selects[0] if selects else None
    prof = {}

    # ---- required outputs: every checklist output column represented (by
    # column name OR as an aggregate/alias expression) somewhere in a SELECT.
    out_cols = [str(c).split(".")[-1].strip('"').lower()
                for c in (cl.get("output_columns") or [])]
    proj_text = " ".join(_norm(e) for sel in selects
                         for e in _output_expressions(sel))
    prof["required_outputs_satisfied"] = all(c in proj_text for c in out_cols) \
        if out_cols else True

    # ---- required aggregate output: a grouped/aggregate question must PROJECT
    # an aggregate, not only the group key (RC3 "count X by Y" defect).
    needs_agg = (cl.get("required_sql_shape") or "").lower() == "group_by_having" \
        or bool(cl.get("required_group_keys")) \
        or bool(_grain_requirements_aggs(contract))
    has_agg_proj = any(_aggregate_in_projection(s) for s in selects)
    prof["required_aggregates_satisfied"] = (has_agg_proj if needs_agg else True)

    # ---- required OUTPUT aggregate. A grouped answer that is NOT a top-k
    # ranking must PROJECT its aggregate rather than hide it in HAVING/ORDER BY
    # with only the group key output ("Count X by Y" -> the count is the point
    # of the grouping). This is a requested-output obligation, so it is skipped
    # for order/limit ranking shapes (there the aggregate is the ranking key and
    # need not be projected) and skipped when the grouping carries a REAL HAVING
    # filter (then only the key is requested and the aggregate is a threshold).
    shape = (cl.get("required_sql_shape") or "").lower()
    out_agg_applies = shape != "order_by_limit" and (
        bool(_output_aggregate_reqs(contract)) or _bare_key_grouping(selects))
    prof["required_output_aggregate_satisfied"] = (
        has_agg_proj if out_agg_applies else True)
    prof["_out_agg_applies"] = out_agg_applies

    # ---- required formula: all derived-measure components referenced somewhere.
    comps = _formula_components(contract)
    if comps:
        cols_used = set()
        for s in selects:
            for e in _output_expressions(s):
                cols_used |= _referenced_columns(e)
        prof["required_formula_satisfied"] = all(
            col.lower() in cols_used for (_t, col) in comps)
    else:
        prof["required_formula_satisfied"] = True

    # ---- required group keys present in a GROUP BY.
    gkeys = [str(g).split(".")[-1].strip('"').lower()
             for g in (cl.get("required_group_keys") or [])]
    if gkeys:
        group_cols = set()
        for s in selects:
            grp = s.args.get("group")
            if grp:
                for g in grp.expressions:
                    group_cols |= _referenced_columns(g)
        prof["required_group_keys_satisfied"] = all(k in group_cols for k in gkeys)
    else:
        prof["required_group_keys_satisfied"] = True

    # ---- required set conditions: a set-shape question must use a set operator.
    if (cl.get("required_sql_shape") or "").lower() == "set_operation":
        prof["required_set_conditions_satisfied"] = _set_operation(tree) is not None
    else:
        prof["required_set_conditions_satisfied"] = True

    # ---- RC4 advisory: a scalar "how many / count" question (no requested
    # group keys) must return ONE value; a candidate that emits an unrequested
    # GROUP BY projecting a dimension returns many rows instead. And a
    # distinct-count question must use COUNT(DISTINCT ...), not a plain COUNT.
    shape_l = (cl.get("required_sql_shape") or "").lower()
    if not cl.get("required_group_keys") and shape_l in (
            "count_distinct", "comparison_subquery", "aggregate", "scalar"):
        grouped_dim = any(
            s.args.get("group") and any(
                not _has_aggregate(e) for e in _output_expressions(s))
            for s in selects)
        prof["required_scalar_output_satisfied"] = not grouped_dim
    else:
        prof["required_scalar_output_satisfied"] = True
    if shape_l == "count_distinct":
        counts = [n for s in selects for n in s.find_all(exp.Count)]
        prof["required_distinct_count_satisfied"] = (
            (not counts) or any(bool(n.args.get("this") and
                isinstance(n.this, exp.Distinct)) for n in counts))
    else:
        prof["required_distinct_count_satisfied"] = True

    # ---- relationship roles / grain / population reuse the scorer's proofs.
    prof["required_relationship_roles_satisfied"] = not (v.get("illegal_joins") or [])
    prof["requested_grain_satisfied"] = not ((v.get("grain_contract") or {}).get("fatal"))
    prof["population_preserved"] = not ((v.get("fanout") or {}).get("fatal"))

    # ---- filters / literals present (advisory, not gating).
    prof["required_filters_satisfied"] = not (v.get("unseen_literals") or [])
    prof["required_literals_satisfied"] = prof["required_filters_satisfied"]
    prof["required_comparisons_satisfied"] = True  # gated by grain contract

    # ---- unrequested restrictions / many-side joins (soft signals).
    prof["unrequested_restrictions"] = len((v.get("fanout") or {}).get("warnings") or [])
    prof["unrequested_many_side_joins"] = prof["unrequested_restrictions"]
    prof["fatal_count"] = len(v.get("fatal") or [])

    # ---- RC4 advisory structural signals (never gate RC3 eligibility). These
    # capture the *shape* an override could silently change: the derived-formula
    # expression structure, the set operator, and clause counts used to detect
    # unrequested restrictions / population changes. Compared only pairwise in
    # the validation-score-override dominance test.
    prof["_formula_shape"] = _formula_shape(selects)
    prof["_set_operator"] = _set_operation(tree)
    prof["_status_predicates"] = _status_predicates(selects)
    prof["unrequested_having"] = sum(
        len(_split_and(s.args["having"].this)) for s in selects if s.args.get("having"))
    prof["unrequested_limits"] = sum(1 for s in selects if s.args.get("limit"))
    prof["unrequested_joins"] = sum(len(list(s.find_all(exp.Join))) for s in selects)
    prof["unrequested_filters"] = sum(
        len(_split_and(s.args["where"].this)) for s in selects if s.args.get("where"))
    prof["fanout_risk"] = prof["unrequested_restrictions"]
    prof["required_temporal_conditions_satisfied"] = not (
        (v.get("temporal") or {}).get("fatal"))

    applies_set = _applies(checklist, contract)
    if prof.get("_out_agg_applies"):
        applies_set.add("required_output_aggregate_satisfied")
    prof["_applies"] = sorted(applies_set)
    prof["_satisfied"] = sorted(
        o for o in MANDATORY if o in prof["_applies"] and prof.get(o))
    prof["_missing"] = sorted(
        o for o in MANDATORY if o in prof["_applies"] and not prof.get(o))
    # Eligibility GATES only on obligations that are reliably provable from the
    # AST and would make the answer wrong (a grouped/aggregate question that
    # projects no aggregate, a derived-metric question missing a formula
    # operand, or a set question with no set operator). Output/group-key/grain/
    # relationship/population signals stay ADVISORY here (grain/relationship/
    # population already surface as scorer fatals) to avoid demoting a correct
    # candidate on a noisy checklist. Fatal candidates are never eligible.
    gating_missing = [o for o in GATING
                      if o in prof["_applies"] and not prof.get(o)]
    prof["_gating_missing"] = gating_missing
    prof["eligibility"] = ("fatal" if prof["fatal_count"]
                           else ("eligible" if not gating_missing
                                 else "incomplete"))
    return prof


def _grain_requirements_aggs(contract):
    if contract is None:
        return []
    return [r for r in getattr(contract, "requirements", ()) or ()
            if getattr(r, "measure_aggregation", None) in
            ("sum", "count", "avg", "min", "max")]


def _is_vacuous_having(having):
    # A HAVING that cannot exclude any non-empty group imposes no real filter:
    # every GROUP BY group has at least one row, so COUNT(...) > 0, COUNT(...)
    # >= 1 and COUNT(...) <> 0 are always true. Such a HAVING is a no-op and
    # does not turn a bare-key grouping into a genuine threshold query.
    if having is None:
        return True
    conj = _split_and(having.this)
    if not conj:
        return True
    for c in conj:
        left = getattr(c, "this", None)
        right = getattr(c, "expression", None)
        agg = left if _has_aggregate(left) else (right if _has_aggregate(right) else None)
        lit = right if agg is left else left
        val = None
        if isinstance(lit, exp.Literal) and lit.is_number:
            try: val = float(lit.this)
            except Exception: val = None
        vacuous = False
        if agg is not None and val is not None:
            if isinstance(c, exp.GT) and val <= 0: vacuous = True
            elif isinstance(c, exp.GTE) and val <= 1: vacuous = True
            elif isinstance(c, exp.NEQ) and val == 0: vacuous = True
        if not vacuous:
            return False
    return True


def _bare_key_grouping(selects):
    # Narrow, high-precision signal for the "count/aggregate by <dimension> but
    # the aggregate was omitted" defect. Fires only on a pure single-source
    # grouping: exactly one table, no joins, no WHERE filter, a GROUP BY, NO
    # aggregate in the projection, and no real HAVING filter (absent or a
    # vacuous COUNT(...) > 0 existence check). Such a query is equivalent to
    # SELECT DISTINCT <key> -- the grouping does nothing, so a requested
    # aggregate output is missing. Any WHERE/JOIN/real-HAVING means the grouping
    # is doing set-membership / existence work and only the key is requested, so
    # those are excluded (no false demotion of list/"who has both" queries).
    for sel in selects:
        grp = sel.args.get("group")
        if not grp or not grp.expressions:
            continue
        if list(sel.find_all(exp.Join)):
            continue
        if len(list(sel.find_all(exp.Table))) != 1:
            continue
        if sel.args.get("where") is not None:
            continue
        if _aggregate_in_projection(sel):
            continue
        if not _is_vacuous_having(sel.args.get("having")):
            continue
        return True
    return False


def _output_aggregate_reqs(contract):
    # Grain requirements whose aggregate is a requested OUTPUT, not a filter.
    # Contract-driven and generic: a requirement carrying a comparison
    # threshold (operator/constant) is a HAVING/WHERE FILTER whose aggregate
    # need not be projected; a requirement carrying a measure aggregation but
    # NO threshold is a requested output value ("count X by Y", "top N by
    # <agg>", "avg <m> per <e>") and MUST appear in the SELECT projection.
    reqs = []
    for r in getattr(contract, "requirements", ()) or ():
        if getattr(r, "measure_aggregation", None) not in (
                "sum", "count", "avg", "min", "max"):
            continue
        if getattr(r, "comparison_operator", None) is None \
                and getattr(r, "comparison_constant", None) is None:
            reqs.append(r)
    return reqs


def is_eligible(profile):
    return profile.get("eligibility") == "eligible"


def _formula_shape(selects):
    """Multiset of normalized aggregate/arithmetic OUTPUT expressions. Captures
    derived-metric structure: SUM(a) differs from SUM(a - b) and from
    SUM(a) / SUM(b); numerator/denominator and add-vs-subtract are preserved by
    _norm. Used only to detect an override silently changing the formula."""
    shapes = []
    for sel in selects:
        for e in _output_expressions(sel):
            inner = e.this if isinstance(e, exp.Alias) else e
            # A derived-metric FORMULA is an arithmetic combination (ratio,
            # difference, product). A bare aggregate (COUNT(x)/SUM(x)/AVG(x)) is
            # NOT a formula, so distinct-count / plain-aggregate answers are not
            # compared here — only genuine arithmetic output expressions are.
            if isinstance(inner, (exp.Div, exp.Mul, exp.Sub, exp.Add)) or \
                    any(isinstance(n, (exp.Div, exp.Mul, exp.Sub, exp.Add))
                        for n in inner.find_all(exp.Binary)):
                shapes.append(_norm(inner))
    return frozenset(shapes)


def _status_predicates(selects):
    """Normalized equality/IN/comparison predicates over columns in WHERE/HAVING
    -- the status/membership conditions ("status = 'settled'") whose loss changes
    set semantics. Column-only comparisons (a = b joins) are excluded."""
    preds = set()
    for sel in selects:
        for clause in ("where", "having"):
            node = sel.args.get(clause)
            if not node:
                continue
            for c in _split_and(node.this):
                if isinstance(c, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.In, exp.Like)):
                    lits = [l for l in c.find_all(exp.Literal)]
                    if lits:  # compares a column to a constant => a real filter
                        preds.add(_norm(c))
    return frozenset(preds)


# RC4 — obligations and defect signals compared in the override dominance test.
_OVERRIDE_CRIT = (
    "required_outputs_satisfied", "required_aggregates_satisfied",
    "required_output_aggregate_satisfied", "required_formula_satisfied",
    "required_group_keys_satisfied", "required_set_conditions_satisfied",
    "required_relationship_roles_satisfied", "requested_grain_satisfied",
    "population_preserved", "required_filters_satisfied",
    "required_literals_satisfied", "required_temporal_conditions_satisfied",
    "required_scalar_output_satisfied", "required_distinct_count_satisfied",
)
# Only defect signals derived from the scorer's population/fanout analysis are
# compared. Raw AST clause counts (joins / having / limits) are deliberately NOT
# used: a candidate that correctly joins a needed table or adds a required
# HAVING has more clauses without being semantically worse, so raw counts
# produce false blocks. Genuine unrequested restriction / population
# multiplication surfaces through the scorer's fanout signals below.
_OVERRIDE_DEFECTS = (
    "fatal_count", "unrequested_restrictions", "unrequested_many_side_joins",
    "fanout_risk", "unrequested_having", "unrequested_limits",
)


def override_dominates(pb, pa):
    """RC4 semantic-dominance test for validation_score_override.

    Returns (allowed, reason, detail). A proposed higher-scored candidate B may
    replace the current selection A ONLY when B semantically dominates A: it
    loses no critical obligation A satisfied, changes no derived-formula or
    set-operator A already had, drops no status/membership filter, introduces no
    new fatal / unrequested restriction / population multiplication, AND makes a
    strict improvement (satisfies an obligation A missed, removes a defect, or
    supplies a required formula/set operator A lacked). A higher score alone is
    never sufficient. When B does not dominate, the override is BLOCKED and A is
    kept -- never a silent raw-score fall-through."""
    lost = [o for o in _OVERRIDE_CRIT if pa.get(o) and not pb.get(o)]
    if lost:
        return False, "proposed candidate loses required %s" % lost[0], {
            "obligations_lost": lost, "obligations_gained": []}

    # A derived-metric formula or a set operator that A already expresses must
    # not be silently replaced by a differently-shaped one (equal obligation
    # counts can hide a wrong numerator/denominator or join-for-union swap).
    if pa.get("_formula_shape") and pb.get("_formula_shape") != pa.get("_formula_shape"):
        return False, "proposed candidate changes the derived-metric formula", {
            "obligations_lost": ["required_formula_shape"], "obligations_gained": []}
    if pa.get("_set_operator") and pb.get("_set_operator") != pa.get("_set_operator"):
        return False, "proposed candidate changes required set semantics", {
            "obligations_lost": ["required_set_conditions"], "obligations_gained": []}
    dropped = set(pa.get("_status_predicates") or ()) - set(pb.get("_status_predicates") or ())
    if dropped:
        return False, "proposed candidate drops a required filter/status condition", {
            "obligations_lost": ["required_filters"], "obligations_gained": []}

    worse = [k for k in _OVERRIDE_DEFECTS
             if (pb.get(k, 0) or 0) > (pa.get(k, 0) or 0)]
    if worse:
        return False, "proposed candidate introduces %s" % worse[0], {
            "new_semantic_defects": worse, "obligations_gained": []}

    gained = [o for o in _OVERRIDE_CRIT if pb.get(o) and not pa.get(o)]
    reduced = [k for k in _OVERRIDE_DEFECTS
               if (pb.get(k, 0) or 0) < (pa.get(k, 0) or 0)]
    if not gained and not reduced:
        return False, ("proposed candidate does not semantically dominate the "
                       "current selection (higher score alone is insufficient)"), {
            "obligations_gained": [], "obligations_lost": []}
    return True, "proposed candidate semantically dominates the current selection", {
        "obligations_gained": gained, "reduced_defects": reduced}


def dominates(pb, pa):
    """Profile B semantically dominates A: B satisfies every mandatory
    obligation A satisfies, at least one more, and introduces no new defect."""
    sa, sb = set(pa.get("_satisfied") or []), set(pb.get("_satisfied") or [])
    if not sa <= sb or sb == sa:
        return False
    if pb.get("fatal_count", 0) > pa.get("fatal_count", 0):
        return False
    if pb.get("unrequested_restrictions", 0) > pa.get("unrequested_restrictions", 0):
        return False
    return True
