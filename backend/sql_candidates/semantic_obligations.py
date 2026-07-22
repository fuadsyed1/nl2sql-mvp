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
# Derived-output & set-either obligations (generic, question + AST driven).
#
# These recover a class of selection losses where a candidate that COMPUTES and
# PROJECTS a requested derived value (an add/subtract/ratio/percentage/date
# expression) or realises an "either A or B" request with union-compatible set
# semantics is not distinguished from one that omits it. Detection of WHICH
# obligation the QUESTION imposes is linguistic (a detection cue, never a
# correctness verdict); WHETHER a candidate SATISFIES it is decided structurally
# on the parsed AST. Nothing here is schema/table/column/test specific, and both
# checks return neutral (no obligation) unless the cue is present, so a query
# with no derived/either request is never affected.
# ---------------------------------------------------------------------------
import re as _re

_DERIVED_ARITH_KINDS = ("add", "subtract", "ratio", "multiply")


def _qnorm(question):
    return " " + _re.sub(r"\s+", " ", (question or "").strip().lower()) + " "


# A value-measure noun near "per" marks the true division sense ("cost per
# appointment", "budget per student") and distinguishes it from the grouping
# sense ("highest price per brand", "orders per customer"). Superlative / top-
# per-group cues are excluded so a ranking question is never mistaken for a ratio.
_MEASURE_NOUNS = ("budget", "cost", "costs", "revenue", "salary", "salaries",
                  "payroll", "amount", "spend", "spending", "expense", "expenses",
                  "income", "profit", "balance", "fee", "fees", "capita",
                  "value")
_SUPERLATIVE = ("highest", "lowest", "most", "least", "top ", "maximum",
                "minimum", "latest", "earliest", "cheapest", "best", "largest",
                "smallest", "greatest", "biggest")


def question_derived_obligation(question):
    """Set of derived-output kinds the QUESTION asks to be computed and shown.
    High precision: a single-column total/average/count is NOT a derived formula
    (no cue), so 'total balance' / 'average gpa' return empty. Empty => no
    obligation (callers make no scoring change)."""
    q = _qnorm(question)

    def has(*subs):
        return any(s in q for s in subs)

    superlative = has(*_SUPERLATIVE)
    kinds = set()
    # addition of >= 2 named components / paraphrased sum
    if has(" adding ", " plus ", " combined ", " sum of the ") or \
            _re.search(r"\bformed by adding\b", q):
        kinds.add("add")
    # subtraction / difference / remaining amount (NOT a date-remaining phrase)
    if has(" minus ", " difference ", " unused ", " still needed",
           " subtract", " reduced by ", " net of "):
        kinds.add("subtract")
    if _re.search(r"\bremaining\b", q) and not _re.search(
            r"\b(year|day|month|week|time)s?\s+remaining\b", q):
        kinds.add("subtract")
    # ratio: an explicit percentage/markup/share/ratio cue, OR a "<measure> per
    # <entity>" division that is NOT a superlative ranking.
    if has(" percentage ", " percent ", "percentage of", " markup ",
           " share of ", " ratio ", " rate of ", " divided by "):
        kinds.add("ratio")
    if _re.search(r"(?<![a-z])per(?![a-z])", q) and not superlative \
            and has(*_MEASURE_NOUNS):
        kinds.add("ratio")
    # multiplication
    if has(" multiplied ", " product of "):
        kinds.add("multiply")
    # date-derived difference (years/days/months remaining/until/left, expiry)
    if _re.search(r"\b(year|day|month|week)s?\s+(remaining|until|left)\b", q) or \
            has(" years until ", " days until ", " time remaining",
                " time until ", " elapsed since ") or \
            (" until " in q and "expir" in q):
        kinds.add("date")
    return kinds


def question_either_union_obligation(question):
    """True when the question requests membership in EITHER of two sources
    ("appear either in A or B", "either X or Y"). Detection cue only."""
    q = _qnorm(question)
    if " either " in q and " or " in q:
        return True
    if " appear " in q and " or " in q and (" in " in q or " as " in q):
        return True
    return False


# Each requested arithmetic kind demands its OWN AST operator; an unrelated
# operator never satisfies it (an addition request is NOT met by a subtraction,
# a ratio is NOT met by a multiplication, etc.). A percentage is a ratio: it may
# additionally multiply by 100, but the DIVISION must be present.
_OP_FOR_KIND = {"add": exp.Add, "subtract": exp.Sub, "ratio": exp.Div,
                "multiply": exp.Mul}


def _op_over_column(node, op_cls):
    """True when `node` contains an `op_cls` (Add/Sub/Mul/Div) arithmetic node
    that references at least one column (a genuine derived operand, not a pure
    constant expression). CAST / NULLIF / aliases / aggregates / parentheses /
    nested CTE and subquery expressions are all transparently traversed by
    find_all, so every formulation of the operator is recognised."""
    if node is None:
        return False
    for n in ([node] + list(node.find_all(op_cls))):
        if isinstance(n, op_cls) and next(iter(n.find_all(exp.Column)), None) is not None:
            return True
    return False


def _has_date_function(node):
    if node is None:
        return False
    for fn in node.find_all(exp.Func):
        name = (getattr(fn, "sql_name", lambda: "")() or "").lower() \
            if hasattr(fn, "sql_name") else ""
        if name in ("julianday", "strftime", "date", "datetime", "julian",
                    "date_diff", "datediff"):
            return True
    txt = ""
    try:
        txt = node.sql(dialect="sqlite").lower()
    except Exception:
        txt = str(node).lower()
    return any(k in txt for k in ("julianday", "strftime", "date(", "datetime(",
                                  "date_diff", "datediff"))


def _projection_has_date_diff(node):
    """A date-DIFFERENCE structure: a date function AND a subtraction of two
    date terms (julianday(a)-julianday(b)) or an explicit date_diff/datediff.
    Ordinary numeric subtraction of two plain columns (no date function) does
    NOT count as a date calculation."""
    if node is None or not _has_date_function(node):
        return False
    if next(iter(node.find_all(exp.Sub)), None) is not None:
        return True
    for fn in node.find_all(exp.Func):
        nm = (getattr(fn, "sql_name", lambda: "")() or "").lower() \
            if hasattr(fn, "sql_name") else ""
        if nm in ("date_diff", "datediff"):
            return True
    return False


# -------- final-output lineage (BLOCKER 1) --------------------------------
# A derived expression counts ONLY when it reaches the query's FINAL output:
# directly in the outer projection, or projected as a CTE / subquery alias whose
# defining expression is derived, or in a UNION branch's projection. An
# expression that lives only in WHERE / HAVING / ORDER BY / JOIN, or in a CTE
# column the outer query never selects, does NOT satisfy the obligation.
def _query_output_selects(node):
    """The SELECT node(s) whose projections form the FINAL output of `node`
    (UNION branches are flattened; a subquery/paren unwraps to its inner)."""
    if node is None:
        return []
    if isinstance(node, exp.Union):
        return _query_output_selects(node.this) + _query_output_selects(node.expression)
    if isinstance(node, (exp.Subquery, exp.Paren)):
        return _query_output_selects(node.this)
    if isinstance(node, exp.Select):
        return [node]
    return []


def _output_name(e):
    if isinstance(e, exp.Alias):
        return (e.alias or "").lower()
    if isinstance(e, exp.Column):
        return (e.name or "").lower()
    return None


def _sfrom(select):
    """FROM clause, robust to sqlglot arg-key naming ('from' vs 'from_')."""
    return select.args.get("from") or select.args.get("from_")


def _select_sources(select):
    """alias/name -> defining query node for this select's CTEs and FROM/JOIN
    subqueries (the places an outer alias reference can resolve to)."""
    sources = {}
    for cte in (getattr(select, "ctes", None) or []):
        nm = (cte.alias or "").lower()
        if nm:
            sources[nm] = cte.this
    anon = 0
    for nd in ([_sfrom(select)] + (select.args.get("joins") or [])):
        if nd is None:
            continue
        for sub in nd.find_all(exp.Subquery):
            nm = (sub.alias or "").lower()
            if not nm:                       # unaliased FROM subquery
                nm = "__sub%d" % anon
                anon += 1
            sources[nm] = sub.this
    return sources


def _derived_node_operands(n):
    left = {(c.name or "").lower()
            for c in (n.this.find_all(exp.Column) if n.this is not None else [])}
    right = {(c.name or "").lower()
             for c in (n.expression.find_all(exp.Column) if n.expression is not None else [])}
    return {"operands": left | right, "left": left, "right": right, "date": False}


def _expr_final_derived(inner, kind, select, sources, seen):
    """Derived expressions of `kind` produced by projecting `inner` (resolving
    a CTE/subquery alias reference or a star to its source projection)."""
    res = []
    op = _OP_FOR_KIND.get(kind)
    if op is not None:
        for n in ([inner] + list(inner.find_all(op))):
            if isinstance(n, op) and next(iter(n.find_all(exp.Column)), None) is not None:
                res.append(_derived_node_operands(n))
    elif kind == "date" and _projection_has_date_diff(inner):
        cols = {(c.name or "").lower() for c in inner.find_all(exp.Column)}
        res.append({"operands": cols, "left": cols, "right": cols, "date": True})
    if isinstance(inner, exp.Column):
        res += _resolve_column_final_derived(inner, kind, select, sources, seen)
    elif isinstance(inner, exp.Star):
        for s in sources.values():
            res += _final_derived_exprs(s, kind, seen)
    return res


def _resolve_column_final_derived(col, kind, select, sources, seen):
    res = []
    tbl = (col.table or "").lower()
    name = (col.name or "").lower()
    if tbl and tbl in sources:
        targets = [sources[tbl]]
    elif not tbl:
        targets = list(sources.values())
    else:
        targets = []
    for tgt in targets:
        for tsel in _query_output_selects(tgt):
            if id(tsel) in seen:
                continue
            tsrc = _select_sources(tsel)
            for e in _output_expressions(tsel):
                inner = e.this if isinstance(e, exp.Alias) else e
                if _output_name(e) == name:
                    res += _expr_final_derived(inner, kind, tsel, tsrc,
                                               seen | {id(tsel)})
                elif isinstance(inner, exp.Star):
                    res += _final_derived_exprs(tgt, kind, seen)
    return res


def _final_derived_exprs(tree, kind, seen=None):
    """Every derived expression of `kind` that reaches the FINAL output of the
    query, each described by its operand columns (with left/right split for the
    ordered operators)."""
    seen = seen or set()
    out = []
    for sel in _query_output_selects(tree):
        if id(sel) in seen:
            continue
        src = _select_sources(sel)
        for e in _output_expressions(sel):
            inner = e.this if isinstance(e, exp.Alias) else e
            out += _expr_final_derived(inner, kind, sel, src, seen | {id(sel)})
    return out


def _final_output_projects(tree, kind):
    return len(_final_derived_exprs(tree, kind)) > 0


def _projects_derived_expression(tree, kinds):
    """Operator-specific AND final-output-lineage aware: EVERY requested derived
    kind must reach the final output. (No operand grounding here; that is applied
    by derived_output_satisfied.)"""
    ks = [k for k in kinds if k in _OP_FOR_KIND or k == "date"]
    if not ks:
        return False
    return all(_final_output_projects(tree, k) for k in ks)


def _projects_any_derived_expression(tree):
    """Kind-agnostic capability (advisory profile field): any final-output
    arithmetic-over-column or date-difference expression."""
    return any(_final_output_projects(tree, k)
               for k in ("add", "subtract", "ratio", "multiply", "date"))


# -------- requested operand grounding (BLOCKER 2) ------------------------
# A candidate satisfies a derived obligation only when its final-output derived
# expression uses the REQUESTED operands, grounded generically from the semantic
# contract's measure components, the checklist columns, or (schema-linked)
# question mentions. If the operands cannot be grounded, the obligation is
# NEUTRAL (it does not drive dominance) rather than satisfied by operator alone.
_OPT_SUFFIX = {"count", "date", "id", "flag", "status", "amount", "number",
               "total", "pct", "percentage", "rate", "num", "code", "key",
               "value", "score"}


def _schema_columns(idx):
    cols, keys = set(), set()
    for _t, cl in ((idx or {}).get("tables") or {}).items():
        for c in cl:
            nm = (c.get("name") or "").lower()
            if not nm:
                continue
            cols.add(nm)
            if c.get("is_key") or nm.endswith("_id") or nm == "id":
                keys.add(nm)
    return cols, keys


def _match_columns(phrase, cols):
    """Schema columns whose significant words all appear (singular/plural- and
    suffix-insensitively) in `phrase`. Suffix words (count/date/id/...) are
    optional so 'faculty count'->faculty_count and 'student'->student_count."""
    toks = set(_re.findall(r"[a-z]+", (phrase or "").lower()))
    forms = set(toks)
    for t in toks:
        forms.add(t[:-1] if t.endswith("s") else t + "s")
    out = set()
    for c in cols:
        words = [w for w in c.split("_") if len(w) > 2]
        if not words:
            continue
        req = [w for w in words if w not in _OPT_SUFFIX] or words

        def _hit(w):
            return w in forms or (w[:-1] if w.endswith("s") else w + "s") in forms
        if all(_hit(w) for w in req):
            out.add(c)
    return out


def _contract_operand_cols(contract):
    cols = set()
    for r in (getattr(contract, "requirements", ()) or ()):
        for tc in (getattr(r, "measure_components", ()) or ()):
            try:
                cols.add(str(tc[1]).lower())
            except Exception:
                pass
    return cols


def derived_operand_grounding(question, kind, cols, keys, checklist=None,
                              contract=None):
    """Grounded operand requirement for one derived kind, or None if the operands
    cannot be determined (=> neutral)."""
    q = _qnorm(question)
    nonkey = cols - keys
    mu = set()
    for c in ((checklist or {}).get("must_use_columns") or []):
        mu.add(str(c).split(".")[-1].strip('"').lower())
    contract_cols = _contract_operand_cols(contract)

    def cin(phrase):
        found = _match_columns(phrase, nonkey)
        # prefer contract / must-use grounding when it overlaps the phrase match
        pref = found & (contract_cols | mu)
        return pref or found

    if kind == "add":
        m = _re.search(r"(?:adding|plus|sum of|formed by adding)\s+(.+?)(?:[.,;]|$)", q)
        if not m:
            return None
        ops = cin(m.group(1))
        return {"kind": "set", "ops": ops} if len(ops) >= 2 else None
    if kind == "multiply":
        m = _re.search(r"(.+?)\s+(?:multiplied by|times)\s+(.+?)(?:[.,;]|$)", q)
        ops = (cin(m.group(1)) | cin(m.group(2))) if m else set()
        if not m:
            m2 = _re.search(r"product of\s+(.+?)(?:[.,;]|$)", q)
            ops = cin(m2.group(1)) if m2 else set()
        return {"kind": "set", "ops": ops} if len(ops) >= 2 else None
    if kind == "subtract":
        m = (_re.search(r"([\w ]+?)\s+minus\s+([\w ]+?)(?:[.,;]|$)", q)
             or _re.search(r"difference between\s+([\w ]+?)\s+and\s+([\w ]+?)(?:[.,;]|$)", q)
             or _re.search(r"([\w ]+?)\s+reduced by\s+([\w ]+?)(?:[.,;]|$)", q))
        if not m:
            return None
        L, R = cin(m.group(1)), cin(m.group(2))
        return {"kind": "ordered", "left": L, "right": R} if (L and R) else None
    if kind == "ratio":
        m = (_re.search(r"([\w ]+?)\s+per\s+([\w ]+?)(?:[.,;]|$)", q)
             or _re.search(r"([\w ]+?)\s+divided by\s+([\w ]+?)(?:[.,;]|$)", q))
        if not m:
            return None
        N, D = cin(m.group(1)), cin(m.group(2))
        return {"kind": "ratio", "num": N, "den": D} if (N and D) else None
    if kind == "date":
        dcols = {c for c in cols
                 if c.endswith("_date") or "date" in c.split("_") or "expiration" in c}
        ment = _match_columns(q, dcols)
        return {"kind": "date", "cols": ment} if ment else None
    return None


def _final_output_projects_grounded(tree, kind, g):
    for e in _final_derived_exprs(tree, kind):
        if g["kind"] == "set" and g["ops"] <= e["operands"]:
            return True
        if g["kind"] == "ordered" and (g["left"] & e["left"]) and (g["right"] & e["right"]):
            return True
        if g["kind"] == "ratio" and (g["num"] & e["left"]) and (g["den"] & e["right"]):
            return True
        if g["kind"] == "date" and (g["cols"] & e["operands"]):
            return True
    return False


def derived_output_satisfied(tree, question, idx, checklist=None, contract=None):
    """(applies, satisfied) for the derived-output obligation. Applies only when
    at least one requested kind's operands can be grounded; satisfied only when
    every grounded kind's requested formula reaches the final output with the
    requested operands (operator-specific, lineage- and grounding-checked)."""
    kinds = question_derived_obligation(question)
    if not kinds or tree is None:
        return (False, True)
    cols, keys = _schema_columns(idx)
    grounded = {}
    for k in kinds:
        g = derived_operand_grounding(question, k, cols, keys, checklist, contract)
        if g is not None:
            grounded[k] = g
    if not grounded:
        return (False, True)
    ok = all(_final_output_projects_grounded(tree, k, g)
             for k, g in grounded.items())
    return (True, ok)


def _outer_base_tables(tree):
    """Distinct real tables referenced in the OUTER-most query's FROM + JOINs
    (subquery/CTE tables excluded)."""
    selects = _select_scopes(tree)
    if not selects:
        return set()
    outer = selects[0]
    tabs = set()
    frm = _sfrom(outer)
    if frm is not None:
        for t in frm.find_all(exp.Table):
            tabs.add((t.name or "").lower())
    for j in (outer.args.get("joins") or []):
        for t in j.find_all(exp.Table):
            tabs.add((t.name or "").lower())
    return {t for t in tabs if t}


def _has_top_level_or(tree):
    """A top-level OR / IN(list) disjunction in a WHERE — the single-source way
    to express 'either A or B' membership."""
    for sel in _select_scopes(tree):
        where = sel.args.get("where")
        if where is None:
            continue
        for c in _split_and(where.this):
            if isinstance(c, exp.Or):
                return True
            if isinstance(c, exp.In) and (c.expressions or c.args.get("query")):
                return True
    return False


def _all_referenced_tables(tree):
    """Every real table referenced anywhere in the query (all scopes / union
    branches / subqueries)."""
    if tree is None:
        return set()
    return {(t.name or "").lower() for t in tree.find_all(exp.Table) if t.name}


def _either_source_phrases(question):
    """The two source phrases inside an 'either A or B' / 'appear in A or B'
    request, or None."""
    q = _qnorm(question)
    m = _re.search(r"\beither\b\s*(?:in\s+|as\s+|from\s+|within\s+)?"
                   r"(.+?)\s+\bor\b\s+(.+?)(?:[.,;]|\bfor\b|\bwith\b|$)", q)
    if not m:
        m = _re.search(r"\bappear(?:s|ing)?\b[^.]*?\bin\s+(.+?)\s+\bor\b\s+"
                       r"(.+?)(?:[.,;]|$)", q)
    return (m.group(1), m.group(2)) if m else None


def _phrase_tables(phrase, schema):
    toks = set(_re.findall(r"[a-z]+", phrase))
    out = set()
    for t in schema:
        words = [w for w in t.split("_") if len(w) > 2]
        if not words:
            continue

        def _hit(w):
            forms = {w, w[:-1] if w.endswith("s") else w + "s"}
            return bool(forms & toks) or w in toks
        if all(_hit(w) for w in words):
            out.add(t)
    return out


def either_required_sources(question, schema_tables):
    """The membership SOURCES named inside an 'either A or B' request, matched to
    schema tables — generically, with no hardcoded names. Only tables inside the
    'either ... or ...' disjunction are returned (the projected entity mentioned
    BEFORE 'either' is never a required source). A table matches a phrase when
    every significant word of its name appears (singular/plural-insensitively):
    'billing claims' -> billing_claims, but 'a pending order' does not cover
    sales_orders (missing 'sales')."""
    ph = _either_source_phrases(question)
    if not ph:
        return set()
    schema = [t.lower() for t in (schema_tables or [])]
    req = set()
    for phrase in ph:
        req |= _phrase_tables(phrase, schema)
    return req


def question_multi_source_either(question):
    """True when the 'either ... or ...' is phrased as membership in two SOURCES
    rather than single-source alternative predicates ('either smoke or have a
    condition'). A membership preposition (in / from / as / within) adjacent to
    'either' in EITHER order marks the source-membership reading:
      'either in A or B'   /  'appear either in A or B'
      'in either A or B'   /  'found in either A or B'  /  'from either A or B'."""
    q = _qnorm(question)
    if _re.search(r"\beither\s+(?:in|as|from|within)\b", q):
        return True
    if _re.search(r"\b(?:in|as|from|within)\s+either\b", q):
        return True
    return False


# -------- branch-level union provenance (BLOCKER 3) ----------------------
def _scope_tables(select):
    """alias/name -> base table for the tables directly in this select's FROM /
    JOIN (nested subqueries excluded)."""
    amap = {}
    items = []
    frm = _sfrom(select)
    if frm is not None:
        items.append(frm.this if hasattr(frm, "this") else frm)
    for j in (select.args.get("joins") or []):
        items.append(j.this if hasattr(j, "this") else j)
    for it in items:
        if isinstance(it, exp.Table):
            nm = (it.name or "").lower()
            if nm:
                amap[nm] = nm
                al = it.args.get("alias")
                an = getattr(al, "name", None) if al is not None else None
                if an:
                    amap[str(an).lower()] = nm
    return amap


def _projected_population_tables(select):
    """The base table(s) the PROJECTED output columns are rooted in — i.e. the
    tables that actually supply this select's result population (a table joined
    only as a filter, or referenced only in a subquery, is NOT counted)."""
    amap = _scope_tables(select)
    fromtabs = set(amap.values())
    cols = []
    for e in _output_expressions(select):
        inner = e.this if isinstance(e, exp.Alias) else e
        cols += list(inner.find_all(exp.Column))
    if not cols:
        return fromtabs
    tabs = set()
    for c in cols:
        t = (c.table or "").lower()
        if t and t in amap:
            tabs.add(amap[t])
        elif not t and len(fromtabs) == 1:
            tabs |= fromtabs
    return tabs or fromtabs


def _split_or(node):
    if node is None:
        return []
    if isinstance(node, exp.Or):
        return _split_or(node.this) + _split_or(node.expression)
    if isinstance(node, exp.Paren):
        return _split_or(node.this)
    return [node]


def _or_membership_sources(select, required):
    """Required sources reached through a TOP-LEVEL OR of EXISTS / IN membership
    predicates ('entity WHERE EXISTS(A) OR EXISTS(B)'). An AND (intersection)
    has no top-level OR, so it returns nothing."""
    where = select.args.get("where")
    if where is None:
        return set()
    disj = _split_or(where.this)
    if len(disj) < 2:
        return set()
    srcs = set()
    for d in disj:
        for sub in d.find_all(exp.Exists):
            for t in sub.find_all(exp.Table):
                srcs.add((t.name or "").lower())
        for inn in d.find_all(exp.In):
            for t in inn.find_all(exp.Table):
                srcs.add((t.name or "").lower())
    return srcs & required


def _branch_main_tables(select):
    """Base tables in this branch's own FROM / JOIN (nested subquery / EXISTS
    tables are excluded)."""
    return set(_scope_tables(select).values())


def _disjunct_sources(node):
    """Tables reached through EXISTS / IN subqueries inside one OR disjunct."""
    srcs = set()
    for sub in node.find_all(exp.Exists):
        for t in sub.find_all(exp.Table):
            srcs.add((t.name or "").lower())
    for inn in node.find_all(exp.In):
        for t in inn.find_all(exp.Table):
            srcs.add((t.name or "").lower())
    return srcs


def _sdr_separable(required, unit_sources):
    """System of distinct representatives: each required source S must have a
    DISTINCT unit (UNION branch or OR disjunct) whose required-source contribution
    is EXACTLY {S}. This is what makes 'either A or B' true — one alternative for
    A alone and a different alternative for B alone — so that A and B appearing
    TOGETHER in one intersection unit never satisfies the obligation."""
    req = list(required)
    cand = {S: [i for i, u in enumerate(unit_sources) if u == {S}] for S in req}
    match = {}                                   # unit_index -> source

    def _assign(S, seen):
        for i in cand[S]:
            if i in seen:
                continue
            seen.add(i)
            if i not in match or _assign(match[i], seen):
                match[i] = S
                return True
        return False

    for S in req:
        if not _assign(S, set()):
            return False
    return True


def _multi_source_union_ok(tree, required):
    """Multi-source 'either A or B' is satisfied only when the required sources
    are SEPARABLE across distinct alternatives: a UNION whose branches each
    contribute exactly one required source (common entity tables ignored), or a
    top-level OR whose disjuncts each carry exactly one required source's
    EXISTS/IN membership. A and B together in one branch/disjunct never counts."""
    branches = _query_output_selects(tree)
    if len(branches) >= 2:                        # UNION
        units = [_branch_main_tables(b) & required for b in branches]
        return _sdr_separable(required, units)
    sel = branches[0] if branches else None       # single query: top-level OR
    if sel is None:
        return False
    where = sel.args.get("where")
    if where is None:
        return False
    disj = _split_or(where.this)
    if len(disj) < 2:
        return False
    units = [_disjunct_sources(d) & required for d in disj]
    return _sdr_separable(required, units)


def either_union_satisfied(tree, required_sources=None):
    """AST verdict for the either-union obligation.

    MULTI-SOURCE membership (>= 2 required sources, e.g. 'appear either in A or
    B'): the required sources must be SEPARABLE across distinct alternatives —
    one UNION branch / OR disjunct contributing A (without B) and a different one
    contributing B (without A). An inner-join intersection, an AND of EXISTS, a
    repeated single source, A and B sharing one branch/disjunct, a source only in
    an unrelated subquery / filter join, and a missing source all FAIL.

    SINGLE-SOURCE alternative predicates (< 2 required sources, e.g. 'either
    smoke or have a chronic condition'): OR / IN within one source is valid and
    UNION is not required; only an inner-join intersection of >= 2 distinct base
    tables with no set operator and no disjunction fails."""
    if tree is None:
        return True
    required = {s.lower() for s in (required_sources or set())}
    if len(required) >= 2:
        return _multi_source_union_ok(tree, required)
    # single-source / unknown -> lenient
    if _set_operation(tree) is not None:
        return True
    if len(_outer_base_tables(tree)) <= 1:
        return True
    if _has_top_level_or(tree):
        return True
    return False


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

    # Derived-output & set-either structural capabilities. These are
    # question-INDEPENDENT AST facts (does the projection carry a derived
    # arithmetic/date expression; is the query union-compatible rather than an
    # intersection). The APPLICABLE obligation is decided with the question in
    # rc5_ranking; recording the facts here lets the profile/scorer reward a
    # candidate that projects a requested derived value or realises 'either' as
    # a union, and flags a repair that dropped a requested derived expression
    # (derived_output_projected becomes False).
    prof["derived_output_projected"] = _projects_any_derived_expression(tree)
    prof["either_union_satisfied"] = either_union_satisfied(tree)

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
