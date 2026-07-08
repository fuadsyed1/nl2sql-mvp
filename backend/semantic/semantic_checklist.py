"""
semantic/semantic_checklist.py

Stage 2 — semantic checklist: one small LLM call that turns the question into
an explicit, schema-validated contract:

  {target_entity, output_columns, must_use_tables, must_use_columns,
   measure_column, group_by_entity, comparison_logic, required_sql_shape,
   literals}

The checklist is used two ways:
  * checklist_alignment(...) is the STRONGEST scoring signal in
    candidate_scorer (shape / measure / tables / columns / literals);
  * question-anchored must_use_columns that a candidate never touches are
    FATAL (hard disqualification in the selector).

Hallucination safety: every table/column the model names is validated against
the schema graph; anything unknown is dropped. A must_use_column is only
enforced as fatal when a word of that column's name actually appears in the
question, so a wrong checklist cannot sink a correct candidate.
"""

import json
import re

from llm import get_provider
from llm.errors import ProviderError
from semantic.ai_semantic_extractor import extract_json, _describe_graph
from query_families import slot_extractor as se

__all__ = ["generate_checklist", "checklist_alignment", "grain_alignment", "REQUIRED_SHAPES"]

REQUIRED_SHAPES = (
    "plain_select", "group_by_having", "order_by_limit", "not_exists",
    "left_join_null", "count_distinct", "window_or_cte",
    "comparison_subquery", "self_join",
)

# scoring weights (checklist is the strongest single signal in the scorer)
_SHAPE_OK, _SHAPE_MISS = +10, -12
_MEASURE_OK, _MEASURE_MISS = +6, -10
_TABLE_OK, _TABLE_MISS = +3, -8          # per table, max 3 counted
_COLUMN_OK, _COLUMN_MISS = +5, -10       # per column, max 3 counted
_LITERAL_OK, _LITERAL_MISS = +2, -4      # per literal, max 3 counted
_DELTA_MIN, _DELTA_MAX = -45.0, +30.0


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------
def _checklist_prompt(question, tables_block, rel_block, value_hints=""):
    hints = f"{value_hints}\n\n" if value_hints else ""
    return (
        "/no_think\n"
        "Return ONLY one JSON object. No SQL, no prose, no markdown.\n"
        "You are building a semantic checklist for a SQL generator: what the\n"
        "correct SQL for this question MUST contain.\n\n"
        f"Tables:\n{tables_block}\n\n"
        f"Foreign keys (only legal joins):\n{rel_block}\n\n"
        f"{hints}"
        f"Question: {question}\n\n"
        "Keys:\n"
        '- "target_entity": the table whose rows the answer is about\n'
        '- "output_columns": ["table.column", ...] the answer should show\n'
        '- "must_use_tables": every table the SQL must touch\n'
        '- "must_use_columns": ["table.column", ...] the question explicitly\n'
        "  names (e.g. a total, a code, a city) — only columns from the schema\n"
        '- "measure_column": "table.column" being compared/summed/averaged, or null\n'
        '- "group_by_entity": "table.column" the results are grouped per, or null\n'
        '- "comparison_logic": one short sentence of the comparison, or null\n'
        '- "required_sql_shape": one of plain_select | group_by_having |\n'
        "  order_by_limit | not_exists | left_join_null | count_distinct |\n"
        "  window_or_cte | comparison_subquery | self_join\n"
        '- "literals": constant values quoted in the question (strings/numbers)\n'
        '- "row_grain": one short phrase for what ONE output row represents,\n'
        '  e.g. "one row per customer", "one row per case_gdc_id"\n'
        '- "universe": for every/all/each questions, the complete set each\n'
        '  entity must cover, e.g. "all sponsor types", "all data categories";\n'
        "  else null\n"
        '- "required_group_keys": ["table.column", ...] the results must be\n'
        "  grouped by (the row_grain keys), or []\n"
        '- "forbidden_hardcoded_universe": true if the question says all/every/\n'
        "  each of some type/category/status (so the universe size must come\n"
        "  from a subquery, not a hardcoded constant); else false\n"
        "JSON:"
    )


def _norm_col(value, idx):
    """Normalize 'table.column'/'column' -> ('table' or None, 'column'), only
    if the column exists in the schema; else None."""
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip().lower().replace('"', "")
    table, col = (v.split(".", 1) + [None])[:2] if "." in v else (None, v)
    if col is None:
        table, col = None, v
    schema = idx["tables"]
    if table and table in schema:
        if any(c["name"] == col for c in schema[table]):
            return (table, col)
        table = None  # wrong table; try to keep the column
    for t, cols in schema.items():
        if any(c["name"] == col for c in cols):
            return (table if table in schema else None, col) if table else (None, col)
    return None


def _clean_checklist(data, idx):
    """Validate raw model JSON against the schema; drop anything unknown."""
    if not isinstance(data, dict):
        return None
    schema = set(idx["tables"])
    out = {
        "target_entity": None, "output_columns": [], "must_use_tables": [],
        "must_use_columns": [], "measure_column": None, "group_by_entity": None,
        "comparison_logic": None, "required_sql_shape": None, "literals": [],
        "row_grain": None, "universe": None, "required_group_keys": [],
        "forbidden_hardcoded_universe": False,
    }
    te = str(data.get("target_entity") or "").strip().lower()
    out["target_entity"] = te if te in schema else None
    for t in data.get("must_use_tables") or []:
        t = str(t).strip().lower()
        if t in schema and t not in out["must_use_tables"]:
            out["must_use_tables"].append(t)
    for key in ("output_columns", "must_use_columns"):
        for c in data.get(key) or []:
            nc = _norm_col(c, idx)
            if nc:
                s = f"{nc[0]}.{nc[1]}" if nc[0] else nc[1]
                if s not in out[key]:
                    out[key].append(s)
    for key in ("measure_column", "group_by_entity"):
        nc = _norm_col(data.get(key), idx)
        if nc:
            out[key] = f"{nc[0]}.{nc[1]}" if nc[0] else nc[1]
    cl = data.get("comparison_logic")
    if isinstance(cl, str) and cl.strip():
        out["comparison_logic"] = cl.strip()[:200]
    shape = str(data.get("required_sql_shape") or "").strip().lower()
    out["required_sql_shape"] = shape if shape in REQUIRED_SHAPES else None
    for lit in (data.get("literals") or [])[:6]:
        if isinstance(lit, (str, int, float)) and str(lit).strip():
            out["literals"].append(lit)
    # Option C advisory fields (row grain / universe) --------------------
    rg = data.get("row_grain")
    if isinstance(rg, str) and rg.strip():
        out["row_grain"] = rg.strip()[:120]
    uni = data.get("universe")
    if isinstance(uni, str) and uni.strip():
        out["universe"] = uni.strip()[:160]
    for c in data.get("required_group_keys") or []:
        nc = _norm_col(c, idx)
        if nc:
            spec = f"{nc[0]}.{nc[1]}" if nc[0] else nc[1]
            if spec not in out["required_group_keys"]:
                out["required_group_keys"].append(spec)
    out["forbidden_hardcoded_universe"] = bool(
        data.get("forbidden_hardcoded_universe"))
    return out


def generate_checklist(question, graph, value_hints=""):
    """One LLM call -> validated checklist dict, or None on any failure."""
    tables_block, rel_block = _describe_graph(graph)
    idx = se.index_schema(graph)
    try:
        result = get_provider().generate(
            _checklist_prompt(question, tables_block, rel_block, value_hints),
            options={"temperature": 0, "num_predict": 400, "think": False},
        )
        raw = (result.text or "").strip()
        if not raw:
            return None
        data = extract_json(raw)
        checklist = _clean_checklist(data, idx)
        print("SEMANTIC CHECKLIST:", checklist, flush=True)
        return checklist
    except ProviderError as exc:
        print(f"SEMANTIC CHECKLIST ERROR (provider): {exc}", flush=True)
        return None
    except Exception as exc:
        print(f"SEMANTIC CHECKLIST ERROR: {exc}", flush=True)
        return None


# ---------------------------------------------------------------------------
# alignment scoring (used by candidate_scorer)
# ---------------------------------------------------------------------------
def _word_in(text, word):
    return re.search(r"(?<![a-z0-9_])" + re.escape(word) + r"(?![a-z0-9_])",
                     text) is not None


def _col_name(spec):
    return spec.split(".", 1)[1] if "." in spec else spec


def _shape_present(shape, sql_upper):
    if shape == "group_by_having":
        return "GROUP BY" in sql_upper and "HAVING" in sql_upper
    if shape == "order_by_limit":
        return "ORDER BY" in sql_upper and "LIMIT" in sql_upper
    if shape == "not_exists":
        return "NOT EXISTS" in sql_upper or "NOT IN" in sql_upper
    if shape == "left_join_null":
        return "LEFT JOIN" in sql_upper
    if shape == "count_distinct":
        return bool(re.search(r"COUNT\s*\(\s*DISTINCT", sql_upper))
    if shape == "window_or_cte":
        return " OVER" in sql_upper or sql_upper.lstrip().startswith("WITH")
    if shape == "comparison_subquery":
        return bool(re.search(r"[<>=]\s*\(\s*SELECT", sql_upper)) \
            or "NOT EXISTS" in sql_upper or " OVER" in sql_upper \
            or sql_upper.lstrip().startswith("WITH")
    if shape == "self_join":
        return len(re.findall(r"\bJOIN\b", sql_upper)) >= 1 or "EXISTS" in sql_upper
    return True  # plain_select — anything qualifies


def checklist_alignment(question, checklist, sql, idx, params=None):
    """Compare one candidate's SQL (plus bound params) against the checklist.

    Returns (delta, reasons, fatal, checks):
      delta   bounded score adjustment (strongest scorer signal)
      reasons human-readable notes for score explanations
      fatal   hard-disqualification reasons (question-anchored missing concept)
      checks  machine-readable detail dict
    """
    delta, reasons, fatal = 0.0, [], []
    checks = {"missing_columns": [], "missing_tables": [], "shape_ok": None}
    if not checklist or not sql:
        return 0.0, reasons, fatal, checks
    sql_lower = sql.lower()
    sql_upper = sql.upper()
    q = " " + str(question or "").lower() + " "

    # required shape ------------------------------------------------------
    shape = checklist.get("required_sql_shape")
    if shape and shape != "plain_select":
        ok = _shape_present(shape, sql_upper)
        checks["shape_ok"] = ok
        delta += _SHAPE_OK if ok else _SHAPE_MISS
        if not ok:
            reasons.append(f"checklist requires shape '{shape}' but the SQL lacks it")

    # measure column --------------------------------------------------------
    measure = checklist.get("measure_column")
    if measure:
        if _word_in(sql_lower, _col_name(measure)):
            delta += _MEASURE_OK
        else:
            delta += _MEASURE_MISS
            reasons.append(f"checklist measure column '{measure}' is never used")

    # must-use tables --------------------------------------------------------
    miss_t = [t for t in checklist.get("must_use_tables") or []
              if not _word_in(sql_lower, t)]
    hit_t = len(checklist.get("must_use_tables") or []) - len(miss_t)
    delta += _TABLE_OK * min(hit_t, 3) + _TABLE_MISS * min(len(miss_t), 3)
    for t in miss_t[:3]:
        reasons.append(f"checklist table '{t}' is never used")
    checks["missing_tables"] = miss_t

    # must-use columns (question-anchored ones are FATAL when absent) --------
    miss_c = []
    for spec in checklist.get("must_use_columns") or []:
        col = _col_name(spec)
        if _word_in(sql_lower, col):
            delta += _COLUMN_OK
            continue
        miss_c.append(spec)
        delta += _COLUMN_MISS if len(miss_c) <= 3 else 0
        reasons.append(f"checklist column '{spec}' is never used")
        anchored = any(len(tok) > 3 and tok in q for tok in col.split("_"))
        if anchored:
            fatal.append(f"required concept '{spec}' named in the question "
                         "is missing from the SQL")
    checks["missing_columns"] = miss_c

    # literals (inline in the SQL text OR bound as a parameter) --------------
    param_text = " ".join(str(p).lower() for p in (params or []))
    for lit in (checklist.get("literals") or [])[:3]:
        s = str(lit).strip().lower()
        if s and (s in sql_lower or s in param_text):
            delta += _LITERAL_OK
        elif s:
            delta += _LITERAL_MISS
            reasons.append(f"literal '{lit}' from the question is missing")

    return max(_DELTA_MIN, min(_DELTA_MAX, delta)), reasons, fatal, checks


# ---------------------------------------------------------------------------
# Option C — advisory grain / universe alignment (used by candidate_scorer)
# ---------------------------------------------------------------------------
# Penalty-only signals; NEVER fatal, NEVER fired on simple non-aggregate SQL,
# and a no-op whenever the relevant checklist field is absent/uncertain.
_GRAIN_MISS = -10          # GROUP BY does not match the stated row_grain
_GROUP_KEY_MISS = -8       # a required_group_key is absent from GROUP BY
_HARDCODED_UNIVERSE = -12  # every/all query hardcodes the universe size

_GB_RE = re.compile(r"\bGROUP\s+BY\b", re.IGNORECASE)
_GB_TAIL_RE = re.compile(r"\b(HAVING|ORDER\s+BY|LIMIT|UNION|WINDOW)\b",
                         re.IGNORECASE)
_AGG_RE = re.compile(r"\b(count|sum|avg|min|max)\s*\(", re.IGNORECASE)
_SUBQUERY_RE = re.compile(r"\(\s*SELECT\b", re.IGNORECASE)
_COUNT_CMP_INT_RE = re.compile(
    r"\bCOUNT\s*\(\s*(?:DISTINCT\s+)?[^)]*\)\s*(?:=|>=|<=|>|<)\s*(\d+)",
    re.IGNORECASE)


def _identifier_from_grain(row_grain):
    """'one row per case_gdc_id' -> 'case_gdc_id' (lowercased), or None."""
    if not isinstance(row_grain, str):
        return None
    m = re.search(r"per\s+([a-z_][a-z0-9_]*)", row_grain.strip().lower())
    return m.group(1) if m else None


def _group_by_text(sql):
    """The GROUP BY clause text (up to the next clause keyword), or ''."""
    m = _GB_RE.search(sql)
    if not m:
        return ""
    tail = _GB_TAIL_RE.search(sql, m.end())
    end = tail.start() if tail else len(sql)
    return sql[m.end():end]


def grain_alignment(checklist, sql, idx=None):
    """Advisory row-grain / universe checks (Option C).

    Returns (delta, reasons, checks). Penalty-only — the caller must NOT treat
    any of this as fatal. Every check is gated so it cannot fire on a simple
    non-aggregate SELECT, and every field is optional: a missing/empty field
    contributes nothing.
    """
    delta, reasons, checks = 0.0, [], {}
    if not checklist or not sql:
        return 0.0, reasons, checks

    sql_l = sql.lower()
    has_group = _GB_RE.search(sql) is not None
    has_agg = has_group or (_AGG_RE.search(sql) is not None)
    gb = _group_by_text(sql)
    gb_l = gb.lower()

    keys = [k for k in (checklist.get("required_group_keys") or [])
            if isinstance(k, str) and k.strip()]

    # required_group_keys must all appear in GROUP BY (only when grouping) ----
    if keys and has_group:
        missing = [k for k in keys if not _word_in(gb_l, _col_name(k).lower())]
        if missing:
            delta += _GROUP_KEY_MISS
            reasons.append(f"required group key(s) {missing} not in GROUP BY")
            checks["missing_group_keys"] = missing

    # row_grain vs GROUP BY (fuzzy fallback, only when no structured keys) ----
    grain_id = _identifier_from_grain(checklist.get("row_grain"))
    if grain_id and len(grain_id) >= 4 and has_group and not keys:
        if grain_id not in gb_l:
            delta += _GRAIN_MISS
            actual = " ".join(gb.split()).strip()[:60]
            reasons.append(
                f"expected one row per {grain_id}, but SQL groups by {actual}")
            checks["grain_mismatch"] = {"expected": grain_id,
                                        "group_by": actual}

    # forbidden hardcoded universe for every/all questions -------------------
    if checklist.get("forbidden_hardcoded_universe") and has_agg:
        m = _COUNT_CMP_INT_RE.search(sql)
        if m and not _SUBQUERY_RE.search(sql):
            num = m.group(1)
            lits = {str(x).strip() for x in (checklist.get("literals") or [])}
            if num not in lits:
                delta += _HARDCODED_UNIVERSE
                reasons.append(
                    f"every/all query hardcodes a universe count (= {num}) "
                    "instead of comparing against a universe subquery")
                checks["hardcoded_universe"] = num

    return delta, reasons, checks
