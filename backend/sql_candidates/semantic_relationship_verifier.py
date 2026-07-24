"""
sql_candidates/semantic_relationship_verifier.py

Phase 2 — lightweight semantic relationship / table-choice verifier.

Advisory ONLY: given the question, the semantic checklist, the candidate SQL,
and the schema index (which already carries declared FK + confirmed + Phase 1
HoPF relationships), it flags a few semantically-wrong patterns and returns a
small score penalty plus human-readable reasons. It never marks anything fatal,
never raises, and adds NO LLM call — it reuses signals already computed.

Patterns detected (all generic — no table names / domains are hardcoded):
  1. Wrong geography/table-family choice: the SQL builds on a table unrelated
     to the question's vocabulary while a better-matching table sits unused.
  2. Bad semantic joins: a key<->key join (e.g. a postal/zip-like id equated to
     a tract/census id) that is NOT backed by a declared FK, a confirmed
     relationship, a high-confidence HoPF link, or clearly compatible
     names/types.
  3. Wrong measure/business table: covered by (1)+(4) — the checklist's
     must_use_tables encodes the intended business table; ignoring them or
     swapping in an unrelated same-shaped table is penalized.
  4. Dummy/placeholder SQL: WHERE 0>0 / 1=0, AVG(0.0)/SUM(0)/COUNT(0),
     SELECT 0/NULL, or SQL that ignores most of the checklist's must_use_tables.

Advisory penalties are deliberately small so a weak suspicion never buries
genuinely useful SQL; only outright non-answers (dummy SQL, generic SELECT-* /
no-aggregation fallback) are penalized strongly. Declared FK and confirmed
relationships always pass; weak inferred links never approve a suspicious join.
"""

import re

try:  # Phase 1 evidence layer (optional; used only as evidence)
    from schema.hopf_relationship_evidence import (
        USABLE_CONFIDENCE as _HOPF_USABLE,
        name_similarity as _name_sim,
        types_compatible as _types_ok,
    )
except Exception:  # pragma: no cover - Phase 1 module always present here
    _HOPF_USABLE = 0.92

    def _name_sim(a, b, t):
        return 1.0 if re.sub(r"[^a-z0-9]", "", str(a).lower()) == \
            re.sub(r"[^a-z0-9]", "", str(b).lower()) else 0.0

    def _types_ok(a, b):
        return True

__all__ = ["verify_semantic_relationships",
           "BAD_JOIN_PENALTY", "TABLE_CHOICE_PENALTY",
           "MISSING_TABLES_PENALTY", "DUMMY_SQL_PENALTY",
           "GENERIC_FALLBACK_PENALTY"]

# Advisory penalties are intentionally SMALL: a weak semantic suspicion must
# never overpower genuinely useful SQL (a risky-but-real join should still beat
# a generic fallback). The two patterns that ARE strong are the ones that only
# ever indicate a non-answer: dummy SQL and generic SELECT-* / no-aggregation
# fallback.
BAD_JOIN_PENALTY = -5.0         # per unsupported key<->key join (max 2)
TABLE_CHOICE_PENALTY = -4.0     # wrong same-shaped / unrelated table choice
MISSING_TABLES_PENALTY = -3.0   # ignores most checklist must_use_tables
DUMMY_SQL_PENALTY = -12.0       # placeholder / dummy SQL (still strong)
GENERIC_FALLBACK_PENALTY = -15.0  # generic SELECT * / no-aggregation non-answer
_DELTA_FLOOR = -30.0

_AGG_RE = re.compile(r"\b(count|sum|avg|min|max|group_concat|total)\s*\(", re.I)
_GROUP_RE = re.compile(r"\bgroup\s+by\b", re.I)
_SELECT_STAR_RE = re.compile(r"^\s*select\s+\*\s+from\b", re.I)
_NEED_WORDS_RE = re.compile(
    r"\b(count|number of|how many|how much|total|sum|average|avg|mean|per |"
    r"each |most |least |top |highest|lowest|rank|distinct|group|compare|"
    r"more than|fewer than|at least|at most)\b", re.I)
_AGG_SHAPES = {"group_by_having", "order_by_limit", "count_distinct",
               "comparison_subquery", "window_or_cte"}

_STOP = {"the", "and", "for", "with", "that", "this", "each", "all", "per",
         "how", "many", "much", "list", "show", "find", "what", "which",
         "who", "whom", "count", "number", "total", "table", "tables",
         "data", "value", "values", "name", "names", "id", "ids", "of",
         "in", "on", "by", "to", "from", "are", "is", "was", "were", "have"}

_STRING_RE = re.compile(r"'(?:[^']|'')*'")
_NAME_RE = re.compile(r"[a-z0-9]+")

_DUMMY_RES = [
    re.compile(r"\bwhere\b[^;]*?\b0\s*[<>]\s*0", re.I),
    re.compile(r"\bwhere\b[^;]*?\b1\s*=\s*0", re.I),
    re.compile(r"\bwhere\b[^;]*?\b0\s*=\s*1", re.I),
    re.compile(r"\bwhere\b\s+false\b", re.I),
    re.compile(r"\b(avg|sum|count|min|max)\s*\(\s*0(?:\.0+)?\s*\)", re.I),
    re.compile(r"\bselect\s+0(?:\.0+)?\s*(?:,|from|$)", re.I),
    re.compile(r"\bselect\s+null\b", re.I),
]


def _tokens(text):
    return {t for t in _NAME_RE.findall(str(text or "").lower())
            if len(t) >= 4 and t not in _STOP}


def _table_tokens(name):
    return {t for t in _NAME_RE.findall(str(name or "").lower()) if len(t) >= 4}


def _checklist_text(checklist):
    if not checklist:
        return ""
    parts = [str(checklist.get(k) or "") for k in
             ("target_entity", "must_use_tables", "must_use_columns",
              "row_grain", "universe", "output_columns", "comparison_logic")]
    return " ".join(parts)


def _tables_used(sql, idx):
    low = " " + sql.lower() + " "
    used = set()
    for t in idx["tables"]:
        if re.search(r"(?<![a-z0-9_])" + re.escape(t) + r"(?![a-z0-9_])", low):
            used.add(t)
    return used


def _col(idx, t, c):
    for col in idx["tables"].get(t, []):
        if col["name"] == c:
            return col
    return None


def _key_like(col, c):
    return bool(col and (col.get("is_key") or c.endswith("_id") or c == "id"
                         or c.endswith("id")))


def _rel_supported(idx, t1, c1, t2, c2):
    """A join is 'supported' iff a matching relationship edge is present in the
    finalized stored graph (either direction). Membership is authority; edge
    labels/confidence do not gate legality."""
    want = {(t1, c1), (t2, c2)}
    for r in idx["relationships"]:
        ft = str(r.get("from_table") or "").lower()
        fc = str(r.get("from_column") or "").lower()
        tt = str(r.get("to_table") or "").lower()
        tc = str(r.get("to_column") or "").lower()
        # Membership IS authority: queries run only on a finalized relationship
        # set, so any edge present between these endpoints (either direction) is
        # approved. Edge type / confirmed / confidence no longer gate legality —
        # that would let a weak, unreviewed inferred edge become a legal join
        # before approval.
        if {(ft, fc), (tt, tc)} == want:
            return True
    return False


def _needs_structure(question, checklist, must):
    """True when the question/checklist clearly asks for aggregation, grouping,
    a join, or a specific SQL shape — i.e. a bare projection is a non-answer."""
    if _NEED_WORDS_RE.search(question or ""):
        return True
    if len(must) >= 2:
        return True
    if checklist:
        if (checklist.get("measure_column") or checklist.get("group_by_entity")
                or checklist.get("required_group_keys")
                or checklist.get("forbidden_hardcoded_universe")):
            return True
        if str(checklist.get("required_sql_shape") or "") in _AGG_SHAPES:
            return True
    return False


def _generic_fallback(sql):
    """(is_fallback, kind): a generic non-answer — a bare `SELECT * FROM t`, or
    a single-table query with no aggregation and no GROUP BY. Only meaningful
    when the question actually needs structure (checked by the caller)."""
    low = sql.lower()
    structure = (
        re.search(r"\bjoin\b", low) is not None
        or _GROUP_RE.search(sql) is not None
        or _AGG_RE.search(sql) is not None
        or "(select" in re.sub(r"\s+", "", low)          # subquery
        or low.lstrip().startswith("with ")               # CTE
        or re.search(r"\bover\s*\(", low) is not None   # window function
        or re.search(r"\bdistinct\b", low) is not None
        or re.search(r"\border\s+by\b", low) is not None
        or re.search(r"\bhaving\b", low) is not None
    )
    if structure:
        return False, None
    if _SELECT_STAR_RE.search(sql):
        return True, "select_star"
    return True, "no_aggregation"


def _row_level_formula_ok(question, sql, idx):
    """True when the question requests a row-level derived formula (add / subtract
    / ratio) and the candidate PROJECTS the grounded formula — so a query with no
    cross-row aggregation is a correct answer, not a collapsed non-answer.
    Reuses the generic derived-output obligation; never raises."""
    try:
        from sql_candidates.semantic_obligations import (
            derived_output_satisfied as _dos, _parse as _dp)
        applies, satisfied = _dos(_dp(sql), question, idx)
        return bool(applies and satisfied)
    except Exception:
        return False


def verify_semantic_relationships(question, checklist, sql, idx, sql_edges=None):
    """Return (delta, reasons, checks). Penalty-only, never fatal, never raises."""
    delta, reasons, checks = 0.0, [], {}
    try:
        if not sql or not idx or not idx.get("tables"):
            return 0.0, reasons, checks
        clean = _STRING_RE.sub("''", sql)
        used = _tables_used(sql, idx)
        must = [str(t).lower() for t in ((checklist or {}).get("must_use_tables")
                                         or []) if str(t).lower() in idx["tables"]]

        # -- (4a) dummy / placeholder SQL -------------------------------------
        for rx in _DUMMY_RES:
            if rx.search(clean):
                delta += DUMMY_SQL_PENALTY
                reasons.append("dummy/placeholder SQL pattern "
                               f"('{rx.pattern}') detected")
                checks["dummy_sql"] = True
                break

        # -- (4c) generic fallback non-answer (STRONG): a bare SELECT * or a
        #    single-table query with no aggregation/join/group when the question
        #    clearly needs structure. This is what a collapsed candidate looks
        #    like; it must lose to any real (even risky) SQL.
        if not checks.get("dummy_sql") and _needs_structure(question, checklist, must):
            is_fb, kind = _generic_fallback(sql)
            # A ROW-LEVEL derived-arithmetic answer (a projected a+b / a-b / a/b
            # per entity, no aggregation across rows) is NOT a collapsed
            # non-answer: it computes the requested value. Suppress the
            # "no_aggregation" fallback penalty when the candidate satisfies the
            # grounded derived obligation. SELECT-* fallbacks are never suppressed.
            if is_fb and kind == "no_aggregation" and _row_level_formula_ok(question, sql, idx):
                is_fb = False
                checks["no_aggregation_suppressed_row_level_formula"] = True
            if is_fb:
                delta += GENERIC_FALLBACK_PENALTY
                reasons.append(
                    "generic fallback SQL (" + kind + ") ignores the requested "
                    "aggregation/join/filter the question needs")
                checks["generic_fallback"] = kind

        # -- (2) bad semantic joins (unsupported key<->key) -------------------
        bad_joins = []
        for (t1, c1, t2, c2) in (sql_edges or []):
            if t1 == t2:
                continue
            col1, col2 = _col(idx, t1, c1), _col(idx, t2, c2)
            if not col1 or not col2:
                continue
            if not (_key_like(col1, c1) and _key_like(col2, c2)):
                continue                       # only scrutinize id/key <-> id/key
            if c1 == c2:
                continue                       # same-named key join (compatible)
            if _rel_supported(idx, t1, c1, t2, c2):
                continue                       # declared FK / confirmed / high-conf HoPF
            nsim = max(_name_sim(c1, c2, t2), _name_sim(c2, c1, t1))
            if nsim >= 0.8 and _types_ok(col1.get("type"), col2.get("type")):
                continue                       # clearly compatible names + types
            bad_joins.append(f"{t1}.{c1} = {t2}.{c2}")
        for bj in bad_joins[:2]:
            delta += BAD_JOIN_PENALTY
            reasons.append(f"join {bj} is not supported by a declared FK, a "
                           "confirmed relationship, or a high-confidence "
                           "inferred link")
        if bad_joins:
            checks["unsupported_joins"] = bad_joins

        # -- (1)+(3) table-family / measure-business choice -------------------
        qtokens = _tokens(question) | _tokens(_checklist_text(checklist))
        if qtokens:
            for u in used:
                if _table_tokens(u) & qtokens:
                    continue                   # used table matches the question
                better = [t for t in idx["tables"]
                          if t not in used and (_table_tokens(t) & qtokens)]
                if better:
                    delta += TABLE_CHOICE_PENALTY
                    reasons.append(
                        f"SQL builds on '{u}', unrelated to the question's "
                        f"terms; '{sorted(better)[0]}' matches them better")
                    checks["table_choice_mismatch"] = {"used": u,
                                                        "better": sorted(better)}
                    break

        # -- (4b) ignores most checklist must_use_tables ----------------------
        if len(must) >= 2:
            missing = [t for t in must if t not in used]
            if len(missing) > len(must) / 2:
                delta += MISSING_TABLES_PENALTY
                reasons.append("SQL ignores most checklist must_use_tables "
                               f"(missing: {missing})")
                checks["missing_must_tables"] = missing

        delta = max(_DELTA_FLOOR, round(delta, 1))
        checks["delta"] = delta
        return delta, reasons, checks
    except Exception as exc:  # advisory: never break scoring
        return 0.0, reasons, {"error": f"{type(exc).__name__}: {exc}"}
