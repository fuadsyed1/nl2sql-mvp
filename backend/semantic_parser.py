"""
semantic_parser.py
──────────────────
Role in the architecture:

    Natural Language
        → AI Semantic Extractor     (understands meaning — ai_semantic_extractor.py)
        → semantic_parser           (validates, normalises, schema-binds)
        → SQL Generator             (generates target query — sql_generator.py)

This file has two responsibilities:

  1. validate_and_normalise(ai_output, schema_info)
     Called when the AI extractor succeeds.
     Validates every field against the real schema, drops unknown columns,
     fixes structural inconsistencies (sort field vs agg field, missing
     group_by, etc.).  No linguistic knowledge needed here.

  2. parse_natural_language(question, schema_info)   [fallback only]
     Called when the AI extractor returns None.
     Does the minimum that can be done structurally:
       - Matches column names literally present in the question text
       - Detects symbolic comparison operators (>, <, >=, <=, =) and numbers
       - Produces SELECT * when nothing explicit is found
     Does NOT attempt to understand "most", "cheapest", "average", etc.
     Those are the AI's job.
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Semantic Object factory
# ---------------------------------------------------------------------------

def create_semantic_object() -> dict[str, Any]:
    """Return a blank Semantic Object with all fields at their zero value."""
    return {
        "query_type": None,
        "domain":     None,
        "intent":     None,
        "relational": {
            "entity":      None,
            "select":      [],
            "filters":     [],
            "sort":        None,
            "limit":       None,
            "aggregation": None,
            "group_by":    None,
        },
        "design": {
            "target":  None,
            "clauses": {
                "target":          [],
                "subject_to":      [],
                "prefer":          [],
                "avoid":           [],
                "using_knowledge": [],
                "validate":        [],
                "correct":         [],
                "return":          [],
            },
        },
    }


# ---------------------------------------------------------------------------
# Schema helpers  (pure string/structure work, no linguistic knowledge)
# ---------------------------------------------------------------------------

def normalize_columns(columns: list[str]) -> list[str]:
    """Return lower-cased, stripped column names, filtering empties."""
    return [c.strip().lower() for c in columns if c and c.strip()]


def find_mentioned_columns(text: str, columns: list[str]) -> list[str]:
    """
    Return the subset of *columns* whose names appear as whole words in *text*.

    Handles:
      - exact match:       "extension"   → extension
      - naive plural:      "extensions"  → extension
      - naive singular:    "file"        → files  (rstrip 's')
      - space-separated:   "file type"   → file_type
    """
    text = text.lower()
    matched = []

    for col in columns:
        parts = col.split("_")

        # Variants to try
        variants = [
            col,            # exact
            col.rstrip("s"),  # naive singular  (files → file)
            col + "s",        # naive plural    (file → files)
        ]

        found = False
        for v in variants:
            if v and re.search(r"\b" + re.escape(v) + r"\b", text):
                matched.append(col)
                found = True
                break

        if found:
            continue

        # Multi-part: try space-separated form  (city_name → "city name")
        if len(parts) > 1:
            spaced = r"\b" + r"\s+".join(re.escape(p) for p in parts) + r"\b"
            if re.search(spaced, text):
                matched.append(col)

    return matched


def extract_number(text: str) -> int | float | None:
    """Return the first numeric literal found in *text*, or None."""
    m = re.search(r"\d+\.?\d*", text)
    if not m:
        return None
    v = float(m.group())
    return int(v) if v.is_integer() else v


# ---------------------------------------------------------------------------
# Operator recognition  (symbols only — verbal forms are the AI's job)
# ---------------------------------------------------------------------------

_SYMBOLIC_OP_RE = re.compile(r">=|<=|>|<|=")
_SYMBOL_MAP     = {">=": ">=", "<=": "<=", ">": ">", "<": "<", "=": "="}


def detect_operator(text: str) -> str | None:
    """Return the first symbolic comparison operator in *text*, or None."""
    m = _SYMBOLIC_OP_RE.search(text)
    return _SYMBOL_MAP.get(m.group()) if m else None


# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

_VALID_AGG_FUNCTIONS = frozenset({"COUNT", "AVG", "SUM", "MIN", "MAX"})
_VALID_DIRECTIONS    = frozenset({"ASC", "DESC"})


# ---------------------------------------------------------------------------
# validate_and_normalise  — called after a successful AI extraction
# ---------------------------------------------------------------------------

def validate_and_normalise(
    ai_output: dict,
    schema_info: dict[str, Any],
) -> dict[str, Any]:
    table = schema_info.get("table", "").strip().lower()
    columns = normalize_columns(schema_info.get("columns") or [])

    out = create_semantic_object()
    out.update({
        "query_type": "relational_query",
        "domain": "database",
        "intent": "retrieve",
    })

    rel = out["relational"]
    rel["entity"] = table

    raw_select = ai_output.get("select") or ["*"]
    if raw_select in (["*"], "*"):
        rel["select"] = ["*"]
    else:
        rel["select"] = [
            c.lower() for c in raw_select
            if isinstance(c, str) and c.lower() in columns
        ] or ["*"]

    rel["filters"] = []
    for f in ai_output.get("filters") or []:
        if not isinstance(f, dict):
            continue

        field = (f.get("field") or "").lower()
        operator = f.get("operator")
        value = f.get("value")

        if field in columns and operator and value is not None:
            rel["filters"].append({
                "field": field,
                "operator": operator,
                "value": value,
            })

    raw_agg = ai_output.get("aggregation")

    if isinstance(raw_agg, dict):
        func = (raw_agg.get("function") or "").upper()
        field = (raw_agg.get("field") or "*").lower()

        if func in _VALID_AGG_FUNCTIONS:
            if field != "*" and field not in columns:
                field = "*"

            rel["aggregation"] = {
                "function": func,
                "field": field,
            }

    elif isinstance(raw_agg, str):
        func = raw_agg.upper()

        if func in _VALID_AGG_FUNCTIONS:
            field = "*"

            raw_sort = ai_output.get("sort")
            if isinstance(raw_sort, dict):
                sort_field = (raw_sort.get("field") or "").lower()
                if sort_field in columns:
                    field = sort_field

            if field == "*":
                valid_select = [c for c in rel["select"] if c != "*"]
                if valid_select:
                    field = valid_select[-1]

            rel["aggregation"] = {
                "function": func,
                "field": field,
            }

    raw_gb = ai_output.get("group_by")

    if isinstance(raw_gb, list):
        raw_gb = raw_gb[0] if raw_gb else None

    if isinstance(raw_gb, str):
        gb = raw_gb.lower()
        if gb in columns:
            rel["group_by"] = gb

    # If aggregation has group_by, select should show the group/category column
    if rel["aggregation"] and rel["group_by"]:
        rel["select"] = [rel["group_by"]]

    # Do NOT invent group_by for simple MAX/MIN/AVG/SUM over one column
    # Example: "Highest allocated space" should not become GROUP BY allocated

    raw_sort = ai_output.get("sort")
    if isinstance(raw_sort, dict):
        sf = (raw_sort.get("field") or "").lower()
        sd = (raw_sort.get("direction") or "DESC").upper()

        if sd not in _VALID_DIRECTIONS:
            sd = "DESC"

        if sf in columns:
            if rel["aggregation"] and rel["group_by"]:
                sf = rel["aggregation"]["field"]

            rel["sort"] = {
                "field": sf,
                "direction": sd,
            }

    raw_limit = ai_output.get("limit")
    if raw_limit is not None:
        try:
            lv = int(raw_limit)
            rel["limit"] = lv if lv > 0 else None
        except (TypeError, ValueError):
            rel["limit"] = None

    return out


# ---------------------------------------------------------------------------
# Structural fallback  — called only when AI extraction returns None
# ---------------------------------------------------------------------------

def _structural_fallback(
    question: str,
    schema_info: dict[str, Any],
) -> dict[str, Any]:
    """
    Minimal, deterministic fallback used when the AI extractor is unavailable.

    Only does what can be derived without linguistic knowledge:
      1. Finds column names that appear literally in the question text
      2. Detects symbolic comparison operators (>, <, >=, <=, =) and numbers
         to build a WHERE clause
      3. Decides SELECT columns:
           - If a WHERE filter is present: SELECT * (entity noun before WHERE
             is not a projection)
           - If generality word present (all, every, each): SELECT *
           - If columns appear with "and"/"," conjunction: keep them explicitly
           - Otherwise: SELECT *
      4. Everything else (aggregation, sort, group_by, limit) → null
         The AI must supply those; we do not guess.
    """
    table   = schema_info.get("table", "").strip().lower()
    columns = normalize_columns(schema_info.get("columns") or [])
    text    = question.lower()

    out = create_semantic_object()
    out.update({"query_type": "relational_query", "domain": "database", "intent": "retrieve"})
    rel = out["relational"]
    rel["entity"] = table

    # ── Step 1: detect symbolic filters ──────────────────────────────────────
    filters = []
    seen    = set()

    # Split on AND/OR conjunctions to handle multi-condition queries
    for clause in re.split(r"\band\b|\bor\b", text):
        op  = detect_operator(clause)
        val = extract_number(clause)

        if op is None or val is None:
            continue

        # Restrict column search to after "where" if present
        search_region = clause
        wm = re.search(r"\bwhere\b", clause)
        if wm:
            search_region = clause[wm.end():]

        # Find operator position to build a window of tokens before it
        op_m = _SYMBOLIC_OP_RE.search(search_region)
        if op_m:
            before_op = search_region[:op_m.start()]
            window_tokens = set(re.findall(r"\w+", before_op)[-5:])
        else:
            window_tokens = set()

        region_cols = find_mentioned_columns(search_region, columns)
        # Keep only columns in the 5-token window before the operator
        target_cols = [c for c in region_cols
                       if any(part in window_tokens for part in c.split("_"))]
        if not target_cols:
            target_cols = region_cols  # window cleared everything — use all

        for col in target_cols:
            key = (col, op, val)
            if key not in seen:
                seen.add(key)
                filters.append({"field": col, "operator": op, "value": val})

    rel["filters"] = filters

    # ── Step 2: decide SELECT columns ────────────────────────────────────────
    # If there are filters, the user's intent is "show WHERE ...", not
    # "show <column>". SELECT *.
    if filters:
        rel["select"] = ["*"]
        return out

    # Generality words → user wants all rows, not a single column
    if re.search(r"\b(all|every|each|entire|whole)\b", text):
        rel["select"] = ["*"]
        return out

    # Find columns literally mentioned
    mentioned = find_mentioned_columns(text, columns)

    if not mentioned:
        rel["select"] = ["*"]
        return out

    # Explicit conjunction → user named multiple columns deliberately
    if len(mentioned) > 1 and (" and " in text or "," in text):
        # If "by <col>" present, the col after "by" is sort infrastructure
        if " by " in text:
            before_by = text.split(" by ")[0]
            in_before = [c for c in mentioned
                         if re.search(r"\b" + re.escape(c) + r"\b", before_by)
                         or re.search(r"\b" + re.escape(c.rstrip("s")) + r"\b", before_by)
                         or re.search(r"\b" + re.escape(c + "s") + r"\b", before_by)]
            after_by_cols = [c for c in mentioned if c not in in_before]
            non_sort = [c for c in mentioned if c not in after_by_cols]
            rel["select"] = non_sort if non_sort else ["*"]
        else:
            rel["select"] = mentioned
        return out

    # Single column OR multiple columns with "by" but no "and":
    # e.g. "show top 5 extensions by size" → SELECT extension, not SELECT size
    # e.g. "show the largest allocated files" → SELECT * (ambiguous noun)
    if " by " in text:
        before_by = text.split(" by ")[0]
        in_before_by = [
            c for c in mentioned
            if re.search(r"\b" + re.escape(c) + r"\b", before_by)
            or re.search(r"\b" + re.escape(c.rstrip("s")) + r"\b", before_by)
            or re.search(r"\b" + re.escape(c + "s") + r"\b", before_by)
        ]
        after_by = text.split(" by ", 1)[1]
        in_after_by = find_mentioned_columns(after_by, columns)

        # Columns before "by" that are not the sort column → projections
        projections = [c for c in in_before_by if c not in in_after_by]
        if projections:
            rel["select"] = projections
            return out

    # Fallback: SELECT *
    # A single column match that could be an entity noun ("files" in
    # "show all files", "files" in "largest files") → don't project it alone
    rel["select"] = ["*"]
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_natural_language(
    prompt: str,
    schema_info: dict[str, Any],
) -> dict[str, Any]:
    """
    Structural fallback. Called by app.py only when AI extraction returns None.
    Does not perform linguistic understanding.
    """
    return _structural_fallback(prompt, schema_info)