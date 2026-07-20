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
import re as _re

from llm import get_provider
from llm.errors import ProviderError
from semantic.ai_semantic_extractor import extract_json, _describe_graph
from query_families import slot_extractor as se

__all__ = ["generate_checklist", "checklist_alignment", "grain_alignment",
           "literal_group_violations", "REQUIRED_SHAPES"]

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
        "Typed grain requirements (use null when unsure — never guess):\n"
        '- "grain_requirements": a list with ONE entry for EACH aggregate\n'
        "  comparison in the question (a question can contain several\n"
        "  independent ones — include them all). Each entry:\n"
        '  {"measure_column": "table.column" being aggregated/compared,\n'
        '   "aggregation": sum | count | avg | min | max | none —\n'
        "     the aggregation that builds ONE entity's own value, NOT the\n"
        '     aggregation of the comparison side ("has spent" / "total\n'
        '     spending" / "lifetime amount" -> sum, even when compared to an\n'
        '     average),\n'
        '   "entity_key": "table.column" key the measure is aggregated per\n'
        "     (the parent a lifetime/total/overall amount belongs to),\n"
        '   "measure_scope": all_entity_rows | filtered_entity_rows |\n'
        "     latest_event | current_event | qualifying_event_only\n"
        "     (lifetime/total/overall = all_entity_rows; a condition that\n"
        "     only QUALIFIES the entity must NOT narrow the measure scope),\n"
        '   "comparison_right_kind": aggregate_of_entity_totals (an average/\n'
        "     total OF the per-entity totals) | aggregate_of_rows | constant\n"
        "     | null,\n"
        '   "population_key": "table.column" the comparison group is formed\n'
        '     within — ONLY when the question says "same <group>"; when the\n'
        '     comparison is against ALL entities ("more than the average\n'
        '     patient/customer") use null; NEVER repeat the entity_key here,\n'
        '   "distinct": true when different/unique VALUES are counted\n'
        '     ("more than one type/category/specialty"), else null,\n'
        '   "comparison_operator": ">" | ">=" | "<" | "<=" | "=" | "!=" and\n'
        '   "comparison_constant": <number> when the aggregate is compared\n'
        '     to a constant ("more than one" -> ">" and 1), else null,\n'
        '   "measure_expression": {"operation": "subtract", "components":\n'
        '     ["table.colA", "table.colB"]} when the measure is a DIFFERENCE\n'
        "     (e.g. outstanding balance = total - paid), else null,\n"
        '   "confidence": high | medium | low}\n'
        '- "temporal_requirements": when the question QUALIFIES an entity by\n'
        '  its latest/earliest event, one entry per qualification:\n'
        '  [{"event_table": "table", "entity_key": "table.column",\n'
        '    "order_column": "table.column" (the event date/time),\n'
        '    "direction": latest | earliest,\n'
        '    "qualifier_column": "table.column",\n'
        '    "qualifier_values": ["value", ...],\n'
        '    "qualifier_timing": after_extremum | before_extremum,\n'
        '    "confidence": high | medium | low}]\n'
        '  "whose most recent X WAS <state>" = after_extremum (pick the\n'
        "  latest event across ALL events FIRST, then test its state);\n"
        '  "most recent <state> X" = before_extremum; else []\n'
        '- "required_literal_groups": when the question uses a CATEGORY word\n'
        "  (e.g. \"abnormal\", \"active\") that the known column values above\n"
        "  resolve to specific literals, emit one group per category:\n"
        '  [{"concept": "abnormal", "column": "table.column",\n'
        '    "literals": ["value1", "value2", ...],\n'
        '    "confidence": high | medium | low}] — literals MUST be copied\n'
        "  exactly from the known values; never invent values; else []\n"
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


# Stage 1C — conservative, question-anchored normalization of one grain
# requirement. Deterministic, generic (no schema/domain names), and only
# applied when the meaning is high-confidence from the question wording;
# anything uncertain is left exactly as the model produced it.
_TOTAL_WORDS_RE = re.compile(r"\b(spent|spending|total|totals|lifetime|overall)\b")
_LIFETIME_WORDS_RE = re.compile(r"\b(lifetime|overall|all[- ]time|total|totals)\b")
_DISTINCT_COUNT_RE = re.compile(
    r"\b(?:more than one|multiple|different|distinct|unique|number of)\s+"
    r"(?:\w+\s+){0,2}?(?:type|types|kind|kinds|categor\w*|specialt\w*|"
    r"product|products|value|values)\b"
    r"|\btypes?\s+of\b")
_MORE_THAN_ONE_RE = re.compile(r"\bmore than one\b")
# temporal qualification wording (final temporal patch):
# "whose most recent X was Y" -> the extremum is selected FIRST
_AFTER_EXTREMUM_RE = re.compile(
    r"\bwhose\s+(?:most\s+recent|latest|last|first|earliest)\b"
    r"[^,;.?]{0,40}?\b(?:was|is|were|are)\b")
# "most recent completed X" / "earliest cancelled X" -> filter first is OK
_BEFORE_EXTREMUM_RE = re.compile(
    r"\b(?:most\s+recent|latest|last|first|earliest)\s+"
    r"[a-z]+(?:ed|ful)\s+[a-z]+")
_EARLIEST_WORD_RE = re.compile(r"\b(?:first|earliest)\b")
_SAME_PHRASE_RE = re.compile(r"\bsame\s+((?:[a-z0-9]+[ \-]){0,3}[a-z0-9]+)")
_GENERIC_KEY_TOKENS = {"id", "key", "code", "name", "number", "no"}
# words that END a "same <group>" noun phrase (so "same test and whose
# patient ..." only contributes "test", never "patient")
_SAME_PHRASE_STOP = {"and", "or", "than", "whose", "which", "that", "who",
                     "but", "with", "as", "is", "are", "has", "have", "the"}


def _same_phrase_supports(question_l, col_spec):
    """True when the question contains a "same <...>" phrase whose noun words
    (truncated at the first stopword) overlap the population column's
    distinctive name tokens."""
    col = col_spec.split(".")[-1]
    toks = {t for t in re.split(r"[_\s]+", col)
            if t and t not in _GENERIC_KEY_TOKENS}
    if not toks:
        toks = {t for t in re.split(r"[_\s]+", col) if t}
    stems = {t.rstrip("s") for t in toks}
    for m in _SAME_PHRASE_RE.finditer(question_l):
        words = []
        for w in re.findall(r"[a-z0-9]+", m.group(1)):
            if w in _SAME_PHRASE_STOP:
                break
            words.append(w)
        phrase = {w.rstrip("s") for w in words}
        if stems & phrase:
            return True
    return False


def _normalize_grain_entry(entry, question):
    """Deterministic, question-anchored normalization of one cleaned entry
    (Stage 1C + final stabilization Part G). Only high-confidence wording
    patterns are corrected; everything else is left as the model produced it.
    Returns (entry, reasons). Every correction is logged so raw vs normalized
    contracts stay auditable. Rules:
      * total/spent/lifetime wording + aggregate_of_entity_totals
        => per-entity SUM (never the comparison side's AVG);
      * population key kept ONLY when a "same <group>" phrase names it;
        the entity key never doubles as its own population;
      * "more than one type/category/specialty/..." + count
        => distinct=true, operator ">", constant 1;
      * lifetime wording + aggregate_of_entity_totals => measure scope
        all_entity_rows (a latest-event QUALIFIER never narrows the measure).
    Dropping a population key or widening scope only affects which checks
    run — normalization can never create a new fatal by itself."""
    q = " " + str(question or "").lower() + " "
    reasons = []
    if entry.get("aggregation") == "avg" \
            and entry.get("comparison_right_kind") == "aggregate_of_entity_totals" \
            and _TOTAL_WORDS_RE.search(q):
        entry["aggregation"] = "sum"
        reasons.append("aggregation avg->sum (total/spent wording with "
                       "aggregate_of_entity_totals)")
    pop = entry.get("population_key")
    if pop and not _same_phrase_supports(q, pop):
        entry["population_key"] = None
        reasons.append(f"population_key '{pop}' dropped (no matching "
                       f"'same <group>' phrase)")
    if entry.get("aggregation") == "count" and _DISTINCT_COUNT_RE.search(q):
        if entry.get("distinct") is not True:
            entry["distinct"] = True
            reasons.append("distinct=true (different/unique-types wording)")
        if _MORE_THAN_ONE_RE.search(q):
            if entry.get("comparison_operator") is None:
                entry["comparison_operator"] = ">"
                reasons.append("comparison_operator '>' (more than one)")
            if entry.get("comparison_constant") is None:
                entry["comparison_constant"] = 1
                reasons.append("comparison_constant 1 (more than one)")
    if entry.get("comparison_right_kind") == "aggregate_of_entity_totals" \
            and entry.get("measure_scope") in (None, "latest_event",
                                               "current_event",
                                               "qualifying_event_only") \
            and _LIFETIME_WORDS_RE.search(q):
        entry["measure_scope"] = "all_entity_rows"
        reasons.append("measure_scope=all_entity_rows (lifetime/total "
                       "wording; a latest-event qualifier never narrows "
                       "the measure)")
    return entry, reasons


def _normalize_temporal_entry(entry, question):
    """Deterministic timing/direction normalization for one temporal entry
    (final temporal patch). Only unambiguous high-confidence wording is
    corrected; conflicts leave the model's value untouched. Returns
    (entry, reasons).

      "whose most recent X was Y"  => qualifier_timing = after_extremum
        (select the latest event across ALL events, then test it);
      "most recent <qualifier>ed X" => qualifier_timing = before_extremum
        (filtering to qualifying events first is the intended meaning)."""
    q = " " + str(question or "").lower() + " "
    reasons = []
    after_m = _AFTER_EXTREMUM_RE.search(q) is not None
    before_m = _BEFORE_EXTREMUM_RE.search(q) is not None
    if not before_m and entry.get("qualifier_values"):
        # "...latest <value-word> event..." also means filter-first
        for val in entry["qualifier_values"]:
            tok = re.escape(str(val).lower())
            if re.search(r"\b(?:most\s+recent|latest|last|first|earliest)\s+"
                         + tok + r"\s+[a-z]+", q):
                before_m = True
                break
    if after_m and not before_m:
        if entry.get("qualifier_timing") != "after_extremum":
            entry["qualifier_timing"] = "after_extremum"
            reasons.append("qualifier_timing=after_extremum "
                           "('whose latest/most recent X was Y' wording)")
    elif before_m and not after_m:
        if entry.get("qualifier_timing") != "before_extremum":
            entry["qualifier_timing"] = "before_extremum"
            reasons.append("qualifier_timing=before_extremum "
                           "('latest <qualifier> X' wording)")
    if entry.get("direction") is None:
        if _EARLIEST_WORD_RE.search(q):
            entry["direction"] = "earliest"
            reasons.append("direction=earliest (first/earliest wording)")
        elif re.search(r"\b(?:most\s+recent|latest|last)\b", q):
            entry["direction"] = "latest"
            reasons.append("direction=latest (latest/most recent wording)")
    return entry, reasons


def _clean_checklist(data, idx, question=None):
    """Validate raw model JSON against the schema; drop anything unknown.
    When `question` is provided, grain_requirements entries additionally get
    the conservative Stage 1C normalization (total-wording => sum; population
    key requires a matching "same <group>" phrase)."""
    if not isinstance(data, dict):
        return None
    schema = set(idx["tables"])
    out = {
        "target_entity": None, "output_columns": [], "must_use_tables": [],
        "must_use_columns": [], "measure_column": None, "group_by_entity": None,
        "comparison_logic": None, "required_sql_shape": None, "literals": [],
        "row_grain": None, "universe": None, "required_group_keys": [],
        "forbidden_hardcoded_universe": False,
        # typed grain fields (Stage 0/1B semantic contract) — ALL optional; a
        # missing/invalid value stays None/[] and old behavior is preserved
        "measure_aggregation": None, "measure_entity_key": None,
        "comparison_right_kind": None, "grain_confidence": None,
        "grain_requirements": [],
        # final stabilization: resolved categorical literal groups + the
        # audit log of deterministic grain normalizations
        "required_literal_groups": [],
        "grain_normalization": [],
        # final temporal patch: latest/earliest-event qualifications
        "temporal_requirements": [],
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
    # Typed grain fields (Stage 0) ---------------------------------------
    # Validated exactly like the legacy fields: enums checked, columns
    # schema-checked via _norm_col; anything unknown is dropped to None so
    # the typed contract stays optional and can never poison the checklist.
    agg = str(data.get("measure_aggregation") or "").strip().lower()
    if agg in ("sum", "count", "avg", "min", "max", "none"):
        out["measure_aggregation"] = agg
    nc = _norm_col(data.get("measure_entity_key"), idx)
    if nc:
        out["measure_entity_key"] = f"{nc[0]}.{nc[1]}" if nc[0] else nc[1]
    kind = str(data.get("comparison_right_kind") or "").strip().lower()
    if kind in ("aggregate_of_entity_totals", "aggregate_of_rows", "constant"):
        out["comparison_right_kind"] = kind
    conf = str(data.get("grain_confidence") or "").strip().lower()
    if conf in ("high", "medium", "low"):
        out["grain_confidence"] = conf
    # Stage 1B: list of independent grain requirements. Each entry is
    # validated the same way (enums checked, columns schema-checked); an
    # invalid subfield becomes None so the contract builder downgrades that
    # requirement's confidence instead of the checklist failing.
    for entry in (data.get("grain_requirements") or [])[:4]:
        if not isinstance(entry, dict):
            continue
        cleaned = {}
        for key in ("measure_column", "entity_key", "population_key"):
            nc = _norm_col(entry.get(key), idx)
            cleaned[key] = (f"{nc[0]}.{nc[1]}" if nc[0] else nc[1]) if nc else None
        a = str(entry.get("aggregation") or "").strip().lower()
        cleaned["aggregation"] = a if a in (
            "sum", "count", "avg", "min", "max", "none") else None
        k = str(entry.get("comparison_right_kind") or "").strip().lower()
        cleaned["comparison_right_kind"] = k if k in (
            "aggregate_of_entity_totals", "aggregate_of_rows", "constant") else None
        s = str(entry.get("measure_scope") or "").strip().lower()
        cleaned["measure_scope"] = s if s in (
            "all_entity_rows", "filtered_entity_rows", "current_event",
            "latest_event", "qualifying_event_only") else None
        # distinct / comparison-operator / constant (Part C) — optional
        d = entry.get("distinct")
        cleaned["distinct"] = d if isinstance(d, bool) else None
        op = str(entry.get("comparison_operator") or "").strip()
        op = "!=" if op == "<>" else op
        cleaned["comparison_operator"] = op if op in (
            ">", ">=", "<", "<=", "=", "!=") else None
        cc = entry.get("comparison_constant")
        try:
            cleaned["comparison_constant"] = (float(cc) if cc is not None
                                              else None)
        except (TypeError, ValueError):
            cleaned["comparison_constant"] = None
        # derived additive measure (Part D) — optional
        cleaned["measure_expression"] = None
        expr = entry.get("measure_expression")
        if isinstance(expr, dict):
            oper = str(expr.get("operation") or "").strip().lower()
            comps = []
            for spec in (expr.get("components") or [])[:4]:
                nc2 = _norm_col(spec, idx)
                if nc2 and nc2[0]:
                    comps.append(f"{nc2[0]}.{nc2[1]}")
            if oper in ("subtract", "add") and len(comps) >= 2:
                cleaned["measure_expression"] = {"operation": oper,
                                                 "components": comps}
        cf = str(entry.get("confidence") or "").strip().lower()
        cleaned["confidence"] = cf if cf in ("high", "medium", "low") else None
        if question is not None:
            cleaned, norm_reasons = _normalize_grain_entry(cleaned, question)
            out["grain_normalization"].extend(norm_reasons)
        out["grain_requirements"].append(cleaned)
    # temporal requirements (final temporal patch): latest/earliest-event
    # qualification. Schema-checked like everything else; the deterministic
    # timing normalization runs only when the question is available.
    for entry in (data.get("temporal_requirements") or [])[:2]:
        if not isinstance(entry, dict):
            continue
        t = {}
        ev = str(entry.get("event_table") or "").strip().lower()
        t["event_table"] = ev if ev in schema else None
        for key in ("entity_key", "order_column", "qualifier_column"):
            nc4 = _norm_col(entry.get(key), idx)
            t[key] = (f"{nc4[0]}.{nc4[1]}" if nc4[0] else nc4[1]) if nc4 else None
        d4 = str(entry.get("direction") or "").strip().lower()
        t["direction"] = d4 if d4 in ("latest", "earliest") else None
        tm = str(entry.get("qualifier_timing") or "").strip().lower()
        t["qualifier_timing"] = tm if tm in ("after_extremum",
                                             "before_extremum") else None
        t["qualifier_values"] = [str(x) for x in
                                 (entry.get("qualifier_values") or [])[:4]
                                 if isinstance(x, (str, int, float))
                                 and str(x).strip()]
        tc = str(entry.get("confidence") or "").strip().lower()
        t["confidence"] = tc if tc in ("high", "medium", "low") else None
        if question is not None:
            t, t_reasons = _normalize_temporal_entry(t, question)
            out["grain_normalization"].extend(t_reasons)
        out["temporal_requirements"].append(t)
    # required literal groups (Part E): resolved categorical literal sets.
    # Column schema-checked; literals kept as strings; capped small.
    for grp in (data.get("required_literal_groups") or [])[:4]:
        if not isinstance(grp, dict):
            continue
        nc3 = _norm_col(grp.get("column"), idx)
        lits = [str(x) for x in (grp.get("literals") or [])[:8]
                if isinstance(x, (str, int, float)) and str(x).strip()]
        gconf = str(grp.get("confidence") or "").strip().lower()
        if nc3 and nc3[0] and lits and gconf in ("high", "medium", "low"):
            out["required_literal_groups"].append({
                "concept": str(grp.get("concept") or "").strip()[:40],
                "column": f"{nc3[0]}.{nc3[1]}",
                "literals": lits,
                "confidence": gconf,
            })
    return out


def literal_group_violations(checklist, sql, params=None):
    """Part E — categorical literal completeness (fatal reasons list).

    A HIGH-confidence required literal group means the question's category
    word was resolved to explicit sampled values (e.g. "abnormal" ->
    ['high','low','critical']). A candidate that ignores the resolved set AND
    substitutes the unresolved category word as a literal is provably wrong.
    Absence alone (no substitute) stays nonfatal; medium/low confidence
    groups are never fatal."""
    out = []
    groups = (checklist or {}).get("required_literal_groups") or []
    if not groups or not sql:
        return out
    text = sql.lower() + " " + " ".join(str(p).lower() for p in params or [])
    for g in groups:
        if g.get("confidence") != "high":
            continue
        lits = [str(x).lower() for x in g.get("literals") or []]
        concept = str(g.get("concept") or "").strip().lower()
        if not lits or not concept:
            continue
        if any(re.search(r"(?<![a-z0-9_])" + re.escape(l) + r"(?![a-z0-9_])",
                         text) for l in lits):
            continue                      # resolved set is applied
        if re.search(r"(?<![a-z0-9_])" + re.escape(concept) + r"(?![a-z0-9_])",
                     text):
            out.append(
                f"semantic violation: literal '{concept}' is not a valid "
                f"value of {g.get('column')} — the question's category "
                f"resolves to {g.get('literals')} and none of those literals "
                f"is used")
    return out


def generate_checklist(question, graph, value_hints=""):
    """One LLM call -> validated checklist dict, or None on any failure."""
    tables_block, rel_block = _describe_graph(graph)
    idx = se.index_schema(graph)
    try:
        result = get_provider().generate(
            _checklist_prompt(question, tables_block, rel_block, value_hints),
            options={"temperature": 0, "num_predict": 900, "think": False},
        )
        raw = (result.text or "").strip()
        try:                                   # diagnostics only (full trace)
            from diagnostics import full_trace
            full_trace.note("layer2", "checklist_raw", raw)
        except Exception:
            pass
        if not raw:
            return None
        data = extract_json(raw)
        if isinstance(data, dict) and data.get("grain_requirements"):
            print("RAW GRAIN REQUIREMENTS:", data.get("grain_requirements"),
                  flush=True)
        if isinstance(data, dict) and data.get("temporal_requirements"):
            print("RAW TEMPORAL REQUIREMENTS:",
                  data.get("temporal_requirements"), flush=True)
        checklist = _clean_checklist(data, idx, question=question)
        if checklist and checklist.get("grain_normalization"):
            print("GRAIN NORMALIZATION:", checklist["grain_normalization"],
                  flush=True)
        if checklist and checklist.get("grain_requirements"):
            print("NORMALIZED GRAIN REQUIREMENTS:",
                  checklist["grain_requirements"], flush=True)
        if checklist and checklist.get("temporal_requirements"):
            print("NORMALIZED TEMPORAL REQUIREMENTS:",
                  checklist["temporal_requirements"], flush=True)
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
        # RC2 — provenance + equivalence. Treat the column as EXPLICITLY named
        # only when its full name (underscored or spaced) appears as a phrase in
        # the question. A single generic token overlap (e.g. "total" matching an
        # inferred `line_total`, or "shipment" matching an inferred
        # `shipment_id`) is a model-inferred mapping, NOT an explicit reference,
        # and must never be fatal. Even when explicitly named, a semantically
        # equivalent expression (a COUNT for an entity-row/id count) satisfies it.
        col_spaced = col.replace("_", " ")
        explicitly_named = (col in q) or (f" {col_spaced} " in q)
        count_equivalent = (
            (col == "id" or col.endswith("id") or col.endswith("_id"))
            and _re.search(r"\bcount\s*\(", sql_lower) is not None)
        if explicitly_named and not count_equivalent:
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
