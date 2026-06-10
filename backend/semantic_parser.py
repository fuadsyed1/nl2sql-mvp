import re
from functools import lru_cache
from typing import Any

# ---------------------------------------------------------------------------
# Constants – compiled once at import time
# ---------------------------------------------------------------------------

# Single-pass pattern — longer/higher-priority alternatives must come first
# so that ">=" is never shadowed by a bare ">", etc.
_OPERATOR_RE = re.compile(
    r">=|<=|>|<|="                                          # symbolic  (longest first)
    r"|\bgreater than or equal\b|\bat least\b"             # verbal >=
    r"|\bless than or equal\b|\bat most\b"                 # verbal <=
    r"|\bgreater than\b|\babove\b|\bover\b"                # verbal >
    r"|\bless than\b|\bbelow\b|\bunder\b"                  # verbal <
    r"|\bequal to\b|\bequals\b"                            # verbal =
)

_OPERATOR_NORMALISE: dict[str, str] = {
    # symbolic pass-through
    ">=": ">=", "<=": "<=", ">": ">", "<": "<", "=": "=",
    # verbal aliases
    "greater than or equal": ">=", "at least":        ">=",
    "less than or equal":    "<=", "at most":         "<=",
    "greater than":          ">",  "above":           ">",  "over":   ">",
    "less than":             "<",  "below":           "<",  "under":  "<",
    "equal to":              "=",  "equals":          "=",
}

_NUMBER_RE = re.compile(r"\d+\.?\d*")
_TOP_N_RE = re.compile(r"\btop\s+(\d+)\b")

_AGGREGATION_MAP: dict[str, tuple[str, str]] = {
    # keyword -> (function, default_field)
    "how many": ("COUNT", "*"),
    "count":    ("COUNT", "*"),
    "average":  ("AVG",   None),
    "avg":      ("AVG",   None),
    "sum":      ("SUM",   None),
    "total":    ("SUM",   None),
    "minimum":  ("MIN",   None),
    "maximum":  ("MAX",   None),
}

_SORT_DESC_WORDS = frozenset({"highest", "largest", "top"})
_SORT_ASC_WORDS  = frozenset({"lowest",  "smallest"})

_DESIGN_SIGNALS = frozenset({
    "design", "generate molecule", "generate material", "optimize",
    "subject to", "prefer", "avoid", "validate", "correct", "return top",
})

_VALID_AGG_FUNCTIONS = frozenset({"COUNT", "AVG", "SUM", "MIN", "MAX"})


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_semantic_object() -> dict[str, Any]:
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
# Low-level helpers
# ---------------------------------------------------------------------------

def detect_operator(text: str) -> str | None:
    """Return the first comparison operator found in *text*, or None.

    Accepts both symbolic forms (``>=``, ``<=``, ``>``, ``<``, ``=``) and
    their natural-language equivalents ("at least", "greater than", …).
    """
    m = _OPERATOR_RE.search(text)
    return _OPERATOR_NORMALISE.get(m.group()) if m else None


def extract_number(text: str) -> int | float | None:
    """Return the first numeric value in *text*, or None."""
    m = _NUMBER_RE.search(text)
    if not m:
        return None
    v = float(m.group())
    return int(v) if v.is_integer() else v


@lru_cache(maxsize=256)
def _normalize_column(col: str) -> str:
    return col.strip().lower()


def normalize_columns(columns: list[str]) -> list[str]:
    return [_normalize_column(c) for c in columns if c and c.strip()]


def find_mentioned_columns(text: str, columns: list[str]) -> list[str]:
    """Return columns that appear as substrings in *text* (preserves order)."""
    return [col for col in columns if col in text]


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def detect_aggregation(
    text: str,
    columns: list[str],
    override: str | None = None,
) -> dict[str, Any] | None:
    """
    Build an aggregation descriptor.

    *override* is an already-validated aggregation function name (e.g. "AVG")
    supplied by the caller from schema_info; it takes priority over text signals.
    """
    if override:
        func = override
        field = "*"
        # For non-COUNT functions try to resolve a numeric column from text
        if func != "COUNT":
            mentioned = find_mentioned_columns(text, columns)
            field = mentioned[0] if mentioned else "*"
        return {"function": func, "field": field}

    for keyword, (func, default_field) in _AGGREGATION_MAP.items():
        if keyword in text:
            field = default_field
            if field is None:
                mentioned = find_mentioned_columns(text, columns)
                field = mentioned[0] if mentioned else "*"
            return {"function": func, "field": field}

    return None


def detect_group_by(text: str, columns: list[str]) -> str | None:
    """Return a group-by column only when an aggregation keyword AND ' by ' are present."""
    has_agg = any(kw in text for kw in _AGGREGATION_MAP)
    if not has_agg or " by " not in text:
        return None

    after_by = text.split(" by ", 1)[1]
    for col in columns:
        if col in after_by:
            return col
    return None


def detect_limit(text: str) -> int | None:
    m = _TOP_N_RE.search(text)
    return int(m.group(1)) if m else None


def detect_sort(
    text: str,
    columns: list[str],
    group_by: str | None = None,
) -> dict[str, str] | None:
    """Detect sort direction and field; prefer the group-by column when present."""
    words = set(text.split())

    if words & _SORT_DESC_WORDS:
        direction = "DESC"
    elif words & _SORT_ASC_WORDS:
        direction = "ASC"
    else:
        return None

    # Prefer the group-by column as the sort target
    field = group_by or next(iter(find_mentioned_columns(text, columns)), None)
    if not field:
        return None

    return {"field": field, "direction": direction}


def detect_filters(text: str, columns: list[str]) -> list[dict[str, Any]]:
    operator = detect_operator(text)
    value    = extract_number(text)

    if operator is None or value is None:
        return []

    return [
        {"field": col, "operator": operator, "value": value}
        for col in columns
        if col in text
    ]


def detect_selected_columns(
    text: str,
    columns: list[str],
    aggregation: dict | None,
    group_by: str | None,
    sort: dict | None,
    filters: list[dict],
) -> list[str]:
    """
    Determine which columns to SELECT.

    Rules (in priority order):
    1. Aggregation present  → select only the group-by column (or '*').
    2. Mentioned columns used *only* for filtering / sorting → fall back to '*'.
    3. Explicitly mentioned columns → return them.
    4. Default → '*'.
    """
    if aggregation:
        return [group_by] if group_by else ["*"]

    mentioned = find_mentioned_columns(text, columns)
    if not mentioned:
        return ["*"]

    sort_field    = sort.get("field")  if sort    else None
    filter_fields = {f["field"] for f in filters}

    # Keep only columns that carry query information beyond sort/filter
    payload_cols = [
        col for col in mentioned
        if col != sort_field and col not in filter_fields
    ]

    return payload_cols if payload_cols else ["*"]


# ---------------------------------------------------------------------------
# Top-level parsers
# ---------------------------------------------------------------------------

def parse_relational_query(
    text: str,
    semantic: dict[str, Any],
    schema_info: dict[str, Any],
) -> dict[str, Any]:
    table_name = schema_info["table"].strip().lower()
    columns    = normalize_columns(schema_info.get("columns") or [])

    # Schema-supplied aggregation takes priority
    schema_agg = schema_info.get("aggregation")
    agg_override = schema_agg if schema_agg in _VALID_AGG_FUNCTIONS else None

    aggregation = detect_aggregation(text, columns, override=agg_override)
    group_by    = schema_info.get("group_by") or (
        detect_group_by(text, columns) if aggregation else None
    )
    filters     = detect_filters(text, columns)
    sort        = detect_sort(text, columns, group_by=group_by)
    limit       = detect_limit(text)
    select      = detect_selected_columns(text, columns, aggregation, group_by, sort, filters)

    semantic.update({
        "query_type": "relational_query",
        "domain":     "database",
        "intent":     "retrieve",
    })
    semantic["relational"].update({
        "entity":      table_name,
        "select":      select,
        "filters":     filters,
        "sort":        sort,
        "limit":       limit,
        "aggregation": aggregation,
        "group_by":    group_by,
    })
    return semantic


def parse_design_query(text: str, semantic: dict[str, Any]) -> dict[str, Any]:
    semantic.update({
        "query_type": "inverse_design",
        "domain":     "materials_design",
        "intent":     "design",
    })
    semantic["design"]["target"] = "candidate_materials"
    return semantic


def parse_natural_language(
    prompt: str,
    schema_info: dict[str, Any],
) -> dict[str, Any]:
    text     = prompt.lower()
    semantic = create_semantic_object()

    if any(signal in text for signal in _DESIGN_SIGNALS):
        return parse_design_query(text, semantic)

    return parse_relational_query(text, semantic, schema_info)