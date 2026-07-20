"""
sql_candidates/day2_semantic_rules.py

Day 2 generic NL->SQL semantic obligations + alias-insensitive static validators.

Everything here is derived from natural-language semantics and generic SQL
structure. NOTHING is database-specific: no benchmark table/column names, no test
ids, no expected SQL. Obligations are read from the question wording; validators
inspect the SQL AST (sqlglot). Each rule carries a severity; only rules proven to
flag ZERO protected-correct queries in the static replay are promoted to FATAL.

Severities:
  * "diagnostic" - informational only
  * "warning"    - surfaced, never blocks
  * "fatal"      - contributes a rejection reason (enforcement)
"""
import re

try:
    import sqlglot
    from sqlglot import exp
except Exception:                                    # pragma: no cover
    sqlglot = None
    exp = None

__all__ = [
    "derived_metric_obligation", "set_intent_obligation",
    "explicit_condition_obligation", "requested_output_obligation",
    "evaluate_rules", "day2_fatal_reasons", "RULE_SEVERITY", "RULES",
]

# --------------------------------------------------------------------------
# Rule catalogue + severity. Promotion to "fatal" is data-driven: a rule may be
# fatal ONLY after replay_day2_validators.py shows 0 protected queries flagged.
# --------------------------------------------------------------------------
RULES = [
    "missing_requested_derived_expression",
    "missing_required_output",
    "missing_explicit_filter",
    "unrequested_filter",
    "row_level_predicate_in_having",
    "aggregate_predicate_in_where",
    "either_or_as_intersection",
    "both_as_union",
    "negative_existence_inner_join",
    "independent_exists_collapsed",
    "unsafe_integer_division",
    "missing_zero_denominator_handling",
]
# initial severities; replay promotes clean high-coverage rules to fatal below.
RULE_SEVERITY = {r: "warning" for r in RULES}
RULE_SEVERITY.update({
    "missing_required_output": "diagnostic",
    "unrequested_filter": "diagnostic",
    "missing_explicit_filter": "diagnostic",
    "independent_exists_collapsed": "diagnostic",
    "missing_zero_denominator_handling": "diagnostic",
})
# FATAL only after the static protected replay confirmed protected_flagged == 0
# AND the rule actually discriminates (incorrect_flagged > 0). Only both_as_union
# qualifies: 0 protected, 1 incorrect, precision 1.0. aggregate_predicate_in_where
# flagged 0/0 (not fatal_eligible) and is kept WARNING to avoid a fatal rule with
# no demonstrated discrimination. All other rules flag some protected query and
# stay warning/diagnostic.
_FATAL_PROMOTED = {"both_as_union"}
for _r in _FATAL_PROMOTED:
    RULE_SEVERITY[_r] = "fatal"


# --------------------------------------------------------------------------
# NL obligation extraction (generic, schema-independent)
# --------------------------------------------------------------------------
_RATIO_WORDS = ("ratio", "divided by", "per capita", "share of", "as a share",
                "proportion", "rate of", "per unit")
_PERCENT_WORDS = ("percentage", "percent", "% ", "share")
_DIFF_WORDS = ("difference", "minus", "net ", "gross profit", "profit",
               "markup", "margin", "remaining", "change from")
_SUM_WORDS = ("plus", "added to", "adding", "add ", "combined", "sum of",
              "total of", "formed by adding")
_MUL_WORDS = ("multiplied by", "times ", "product of")
_PER_ENTITY = ("per ", "for each", "average.*per", "per distinct", "per order",
               "per customer", "per group")


def derived_metric_obligation(question):
    """Detect whether the question asks the engine to CALCULATE an expression
    (ratio/percentage/difference/profit/per-entity) rather than merely RETURN
    operands. Generic; returns a dict of booleans + a coarse operation."""
    q = (question or "").lower()
    wants_ratio = any(w in q for w in _RATIO_WORDS)
    wants_percent = any(w in q for w in _PERCENT_WORDS)
    wants_diff = any(w in q for w in _DIFF_WORDS)
    wants_sum = any(w in q for w in _SUM_WORDS)
    wants_mul = any(w in q for w in _MUL_WORDS)
    wants_per_entity = bool(re.search(r"\bper\b|\bfor each\b", q))
    op = None
    if wants_percent:
        op = "percentage"
    elif wants_ratio:
        op = "ratio"
    elif wants_diff:
        op = "difference"
    elif wants_sum:
        op = "add"
    elif wants_mul:
        op = "multiply"
    calc = wants_ratio or wants_percent or wants_diff or wants_sum or wants_mul
    return {
        "calculate_expression": calc,
        "return_operands_only_insufficient": calc,
        "wants_ratio": wants_ratio, "wants_percentage": wants_percent,
        "wants_difference": wants_diff, "wants_sum": wants_sum,
        "wants_multiply": wants_mul, "wants_per_entity": wants_per_entity,
        "operation": op,
        "percentage_or_ratio": wants_ratio or wants_percent,
        "zero_denominator_behavior": "guard" if (wants_ratio or wants_percent) else None,
    }


def set_intent_obligation(question):
    """Generic set / existential intent from the wording."""
    q = " " + (question or "").lower() + " "
    both = bool(re.search(r"\bboth\b|\band also\b", q))
    but_not = bool(re.search(r"\bbut not\b|\bexcept\b|\bexcluding\b", q))
    without = bool(re.search(r"\bwithout\b|\bnever\b|\bno\s|\bnot\s|have not|has not|"
                             r"do not|does not|didn't|never placed|never had", q))
    neither = "neither" in q
    either = bool(re.search(r"\beither\b|\bat least one of\b|\bor\b", q)) and not both
    # two independent child conditions that may live on different rows
    independent = bool(re.search(r"(has|have|placed|received|with)\b.*\band\b.*"
                                 r"(has|have|placed|received|order|item)", q))
    return {"either": either, "both": both, "but_not": but_not,
            "without": without, "neither": neither,
            "independent_existential": independent,
            "negative_existence": without or neither or but_not}


def explicit_condition_obligation(question):
    """Explicit conditions the SQL must preserve (generic, literal-anchored)."""
    q = (question or "")
    years = re.findall(r"\b(?:19|20)\d\d\b", q)
    thresholds = re.findall(r"\b(?:more than|at least|greater than|above|below|"
                            r"less than|over|under|exceeds?)\b\s+\d[\d,\.]*", q, re.I)
    quoted = re.findall(r"['\"]([^'\"]{1,40})['\"]", q)
    return {"years": years, "thresholds": thresholds, "quoted_literals": quoted,
            "has_explicit_condition": bool(years or thresholds or quoted)}


def requested_output_obligation(question):
    """Coarse set of requested output concepts (generic)."""
    q = (question or "").lower()
    return {
        "wants_name": bool(re.search(r"\bname[sd]?\b", q)),
        "wants_count": bool(re.search(r"\bhow many\b|\bnumber of\b|\bcount\b", q)),
        "wants_ranking": bool(re.search(r"\btop \d+\b|\bhighest\b|\blowest\b|\bmost\b|"
                                        r"\bleast\b|\brank", q)),
        "wants_each_entity": bool(re.search(r"\bfor each\b|\beach\b|\bper \b|\bby \b", q)),
    }


# --------------------------------------------------------------------------
# SQL AST helpers (alias-insensitive)
# --------------------------------------------------------------------------
def _parse(sql):
    if not sqlglot or not sql:
        return None
    # defensive: some captured candidate strings append a "normalized_sql:" echo
    # of the same query; keep only the first statement (harmless for real SQL,
    # which never contains this diagnostic marker).
    m = re.search(r"(?im)^\s*normalized_sql\s*:", sql)
    if m:
        sql = sql[:m.start()]
    try:
        return sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        try:
            return sqlglot.parse_one(sql)
        except Exception:
            return None


def _selects(tree):
    return list(tree.find_all(exp.Select)) if tree is not None else []


def _is_agg(node):
    return isinstance(node, exp.AggFunc)


def _projections(select):
    return [e.this if isinstance(e, exp.Alias) else e for e in select.expressions]


def _has_arith_projection(select):
    """True if any output projection computes an arithmetic expression combining
    two value operands (Div/Sub/Add/Mul), i.e. a real derived expression."""
    for p in _projections(select):
        for n in [p] + list(p.find_all(exp.Binary)):
            if isinstance(n, (exp.Div, exp.Sub, exp.Add, exp.Mul)):
                return True
    return False


def _same_scope(node, select):
    try:
        return node.parent_select is select
    except Exception:
        return True


def _group_columns(select):
    g = select.args.get("group")
    cols = set()
    if g:
        for c in g.find_all(exp.Column):
            cols.add(c.name.lower())
    return cols


# --------------------------------------------------------------------------
# individual rule checks -> return message or None
# --------------------------------------------------------------------------
def _r_missing_derived(tree, dm):
    if not dm["calculate_expression"]:
        return None
    # any select scope with an arithmetic projection satisfies the obligation
    if any(_has_arith_projection(s) for s in _selects(tree)):
        return None
    return ("question requests a calculated %s but no output expression computes "
            "it (only operands returned)" % (dm["operation"] or "metric"))


def _r_aggregate_in_where(tree, _o):
    for s in _selects(tree):
        w = s.args.get("where")
        if not w:
            continue
        for agg in w.find_all(exp.AggFunc):
            if _same_scope(agg, s):
                return "aggregate function used in WHERE (belongs in HAVING)"
    return None


def _r_rowlevel_in_having(tree, _o):
    for s in _selects(tree):
        h = s.args.get("having")
        if not h:
            continue
        gcols = _group_columns(s)
        for cmp in h.find_all(exp.Condition):
            if not isinstance(cmp, (exp.EQ, exp.GT, exp.LT, exp.GTE, exp.LTE, exp.NEQ)):
                continue
            if not _same_scope(cmp, s):
                continue
            if next(cmp.find_all(exp.AggFunc), None) is not None:
                continue                              # legit aggregate condition
            cols = [c for c in cmp.find_all(exp.Column)]
            if cols and all(c.name.lower() not in gcols for c in cols):
                return ("row-level predicate on a non-grouped column placed in "
                        "HAVING (belongs in WHERE)")
    return None


def _r_either_as_intersection(tree, si):
    if not si["either"] or si["both"]:
        return None
    if tree is not None and next(tree.find_all(exp.Intersect), None) is not None:
        return "question expresses 'either/or' but SQL uses INTERSECT"
    return None


def _r_both_as_union(tree, si):
    if not si["both"]:
        return None
    if tree is not None and next(tree.find_all(exp.Union), None) is not None:
        return "question expresses 'both' but SQL uses UNION"
    return None


def _r_negative_existence_inner_join(tree, si):
    if not si["negative_existence"] or tree is None:
        return None
    has_not_exists = any(isinstance(n, exp.Not) and
                         next(n.find_all(exp.Exists), None) is not None
                         for n in tree.find_all(exp.Not))
    has_except = next(tree.find_all(exp.Except), None) is not None
    has_left_null = next(tree.find_all(exp.Is), None) is not None
    inner_joins = [j for j in tree.find_all(exp.Join)
                   if (j.kind or "").upper() in ("", "INNER")
                   and (j.side or "") == ""]
    if inner_joins and not (has_not_exists or has_except or has_left_null):
        return ("question expresses absence (never/without/no) but SQL uses an "
                "inner join instead of NOT EXISTS / anti-join")
    return None


def _r_unsafe_integer_division(tree, dm):
    if tree is None:
        return None
    for d in tree.find_all(exp.Div):
        txt = d.sql().lower()
        guarded = ("cast(" in txt or "1.0" in txt or "* 1.0" in txt
                   or "real" in txt or "*1.0" in txt)
        if not guarded:
            return "integer division without REAL cast may truncate a ratio"
    return None


def _r_missing_zero_denom(tree, dm):
    if tree is None or not dm["percentage_or_ratio"]:
        return None
    for d in tree.find_all(exp.Div):
        denom = d.expression
        if denom is None:
            continue
        txt = denom.sql().lower()
        if "nullif" in txt:
            continue
        return "division denominator is not guarded against zero (NULLIF/CASE)"
    return None


_RULE_FUNCS = {
    "missing_requested_derived_expression": ("dm", _r_missing_derived),
    "aggregate_predicate_in_where": ("_", _r_aggregate_in_where),
    "row_level_predicate_in_having": ("_", _r_rowlevel_in_having),
    "either_or_as_intersection": ("si", _r_either_as_intersection),
    "both_as_union": ("si", _r_both_as_union),
    "negative_existence_inner_join": ("si", _r_negative_existence_inner_join),
    "unsafe_integer_division": ("dm", _r_unsafe_integer_division),
    "missing_zero_denominator_handling": ("dm", _r_missing_zero_denom),
}


def evaluate_rules(sql, question):
    """Return a list of {rule, severity, message} for every rule that fires.
    Never raises; a parse failure yields no findings."""
    tree = _parse(sql)
    if tree is None:
        return []
    ctx = {"dm": derived_metric_obligation(question),
           "si": set_intent_obligation(question),
           "_": None}
    out = []
    for rule, (which, fn) in _RULE_FUNCS.items():
        try:
            msg = fn(tree, ctx[which])
        except Exception:
            msg = None
        if msg:
            out.append({"rule": rule, "severity": RULE_SEVERITY.get(rule, "warning"),
                        "message": msg})
    return out


def day2_fatal_reasons(sql, question):
    """FATAL-severity day2 findings only, as reason strings for enforcement."""
    return [f["message"] for f in evaluate_rules(sql, question)
            if f["severity"] == "fatal"]


# --------------------------------------------------------------------------
# Day 2B: generic pool-relative derived-expression penalty (selection input)
#
# STATUS: NOT ENABLED / NOT WIRED. This function is retained for reference only.
# The static safety replay over the 2,000 captured pools showed it would change
# 38 protected-correct best-scored winners while flipping only 10 incorrect
# selections, and it did not recover the trace-verified selection-loss cases
# (whose loss came from consensus/RC grouping, not raw score). It therefore FAILS
# the "0 protected regressions" gate and is deliberately left unconnected to the
# selection path. See day2b_selection_fix_safety_replay.json.
# --------------------------------------------------------------------------
DERIVED_OPERAND_ONLY_PENALTY = 20.0


def _computes_arithmetic(sql):
    tree = _parse(sql)
    return bool(tree) and any(_has_arith_projection(s) for s in _selects(tree))


def derived_operand_only_penalties(question, sqls):
    """Given a question and the pool's candidate SQLs, return a list of penalty
    amounts (>=0), one per input SQL. A penalty is applied ONLY when (1) the
    question requests a calculated expression AND (2) at least one candidate in
    the pool actually computes an arithmetic expression AND (3) this candidate
    does NOT — i.e. it returns operands only while a sibling computes the formula.
    Pool evidence (a sibling computes it) keeps this from firing on questions that
    merely mention a ratio word but whose correct answer is operand-only. Fully
    schema-independent; no per-question or per-database constants."""
    dm = derived_metric_obligation(question)
    n = len(sqls)
    if not dm["calculate_expression"] or n < 2:
        return [0.0] * n
    computes = [_computes_arithmetic(s) for s in sqls]
    if not any(computes):
        return [0.0] * n           # no sibling computes it -> no evidence, no penalty
    return [0.0 if computes[i] else DERIVED_OPERAND_ONLY_PENALTY for i in range(n)]
