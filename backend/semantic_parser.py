import re
from functools import lru_cache
from typing import Any

# ---------------------------------------------------------------------------
# Constants – compiled once at import time
# ---------------------------------------------------------------------------

# Single-pass pattern — longer/higher-priority alternatives must come first
# so that ">=" is never shadowed by a bare ">", etc.
_OPERATOR_RE = re.compile(
    r">=|<=|>|<|="                                                    # symbolic  (longest first)
    r"|\bgreater than or equal\b|\bat least\b|\bno less than\b"    # verbal >=
    r"|\bless than or equal\b|\bat most\b|\bno more than\b"        # verbal <=
    r"|\bgreater than\b|\babove\b|\bover\b|\btaller than\b"       # verbal >
    r"|\bhigher than\b|\bolder than\b|\bmore than\b|\bexceeds\b"  # verbal >
    r"|\bless than\b|\bbelow\b|\bunder\b|\bshorter than\b"        # verbal <
    r"|\blower than\b|\byounger than\b|\bfewer than\b"              # verbal <
    r"|\bequal to\b|\bequals\b"                                       # verbal =
)

_OPERATOR_NORMALISE: dict[str, str] = {
    # symbolic pass-through
    ">=": ">=", "<=": "<=", ">": ">", "<": "<", "=": "=",
    # verbal >= aliases
    "greater than or equal": ">=", "at least":     ">=", "no less than": ">=",
    # verbal <= aliases
    "less than or equal":    "<=", "at most":      "<=", "no more than":  "<=",
    # verbal > aliases
    "greater than": ">", "above":       ">", "over":         ">",
    "taller than":  ">", "higher than": ">", "older than":   ">",
    "more than":    ">", "exceeds":     ">",
    # verbal < aliases
    "less than":     "<", "below":        "<", "under":        "<",
    "shorter than":  "<", "lower than":   "<", "younger than": "<",
    "fewer than":    "<",
    # verbal = aliases
    "equal to": "=", "equals": "=",
}

_NUMBER_RE = re.compile(r"\d+\.?\d*")
_TOP_N_RE = re.compile(    r"\btop\s+(\d+)\b"
    r"|\bfirst\s+(\d+)\b"
    r"|\b(\d+)\s+(?:longest|tallest|biggest|fastest|cheapest|oldest|highest|lowest|shortest|smallest|youngest|heaviest)\b"
)

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

_SORT_DESC_WORDS = frozenset({
    "highest", "largest", "top", "longest", "tallest", "oldest",
    "biggest", "heaviest", "fastest", "most", "greatest", "best",
    "richest", "deepest", "widest", "hottest", "coldest",
})
_SORT_ASC_WORDS = frozenset({
    "lowest", "smallest", "shortest", "youngest", "cheapest",
    "lightest", "slowest", "least", "fewest", "closest",
})

_DESIGN_SIGNALS = frozenset({
    "design", "generate molecule", "generate material", "optimize",
    "subject to", "prefer", "avoid", "validate", "correct", "return top",
})

_VALID_AGG_FUNCTIONS = frozenset({"COUNT", "AVG", "SUM", "MIN", "MAX"})

# ---------------------------------------------------------------------------
# Semantic column aliases
# Maps natural-language descriptors to the column names they most likely
# refer to when the column isn't literally named in the query.
# e.g. "taller than 3000" -> height column; "younger than 20" -> age column.
# ---------------------------------------------------------------------------
_SEMANTIC_ALIASES: dict[str, list[str]] = {
    # size / physical dimension
    "tall":     ["height", "elevation", "altitude"],
    "taller":   ["height", "elevation", "altitude"],
    "tallest":  ["height", "elevation", "altitude"],
    "high":     ["height", "elevation", "altitude", "score"],
    "higher":   ["height", "elevation", "altitude", "score"],
    "highest":  ["height", "elevation", "altitude", "score"],
    "short":    ["height", "length", "duration"],
    "shorter":  ["height", "length", "duration"],
    "long":     ["length", "duration", "distance"],
    "longer":   ["length", "duration", "distance"],
    "longest":  ["length", "duration", "distance"],
    "wide":     ["width", "size"],
    "wider":    ["width", "size"],
    "widest":   ["width", "size"],
    "deep":     ["depth", "score"],
    "deeper":   ["depth", "score"],
    "deepest":  ["depth", "score"],
    # weight
    "heavy":    ["weight", "mass"],
    "heavier":  ["weight", "mass"],
    "heaviest": ["weight", "mass"],
    "light":    ["weight", "mass"],
    "lighter":  ["weight", "mass"],
    "lightest": ["weight", "mass"],
    # speed
    "fast":     ["speed", "velocity", "rate"],
    "faster":   ["speed", "velocity", "rate"],
    "fastest":  ["speed", "velocity", "rate"],
    "slow":     ["speed", "velocity", "rate"],
    "slower":   ["speed", "velocity", "rate"],
    "slowest":  ["speed", "velocity", "rate"],
    # age / time
    "old":      ["age", "year", "date", "created_at"],
    "older":    ["age", "year", "date", "created_at"],
    "oldest":   ["age", "year", "date", "created_at"],
    "young":    ["age", "year", "date", "created_at"],
    "younger":  ["age", "year", "date", "created_at"],
    "youngest": ["age", "year", "date", "created_at"],
    "new":      ["created_at", "date", "year"],
    "newer":    ["created_at", "date", "year"],
    "newest":   ["created_at", "date", "year"],
    "recent":   ["created_at", "date", "year"],
    # money / cost
    "cheap":    ["price", "cost", "tuition", "fee", "salary", "wage", "amount"],
    "cheaper":  ["price", "cost", "tuition", "fee", "salary", "wage", "amount"],
    "cheapest": ["price", "cost", "tuition", "fee", "salary", "wage", "amount"],
    "expensive":["price", "cost", "tuition", "fee"],
    "costly":   ["price", "cost", "tuition", "fee"],
    "rich":     ["salary", "revenue", "income", "wealth"],
    "richer":   ["salary", "revenue", "income", "wealth"],
    "richest":  ["salary", "revenue", "income", "wealth"],
    # quantity
    "many":     ["count", "quantity", "amount", "total"],
    "most":     ["count", "quantity", "amount", "total", "score", "rating"],
    "least":    ["count", "quantity", "amount", "total", "score", "rating"],
    "few":      ["count", "quantity", "amount", "total"],
    "large":    ["size", "quantity", "amount", "population", "area"],
    "larger":   ["size", "quantity", "amount", "population", "area"],
    "largest":  ["size", "quantity", "amount", "population", "area"],
    "small":    ["size", "quantity", "amount", "population", "area"],
    "smaller":  ["size", "quantity", "amount", "population", "area"],
    "smallest": ["size", "quantity", "amount", "population", "area"],
    "big":      ["size", "quantity", "amount", "population", "area"],
    "bigger":   ["size", "quantity", "amount", "population", "area"],
    "biggest":  ["size", "quantity", "amount", "population", "area"],
    # temperature
    "hot":      ["temperature", "temp"],
    "hotter":   ["temperature", "temp"],
    "hottest":  ["temperature", "temp"],
    "cold":     ["temperature", "temp"],
    "colder":   ["temperature", "temp"],
    "coldest":  ["temperature", "temp"],
    # performance / score
    "good":     ["score", "rating", "gpa", "grade", "rank"],
    "best":     ["score", "rating", "gpa", "grade", "rank"],
    "worst":    ["score", "rating", "gpa", "grade", "rank"],
    "top":      ["score", "rating", "gpa", "grade", "rank", "salary"],
    # distance
    "close":    ["distance", "radius"],
    "closer":   ["distance", "radius"],
    "closest":  ["distance", "radius"],
    "far":      ["distance", "radius"],
    "farther":  ["distance", "radius"],
    "farthest": ["distance", "radius"],
}

def _resolve_semantic_column(words: list[str], columns: list[str]) -> str | None:
    """
    Given a list of words from a query clause, return the first column
    that matches via _SEMANTIC_ALIASES, or None.
    Prefers longer/more specific column names (e.g. agency_id over id).
    """
    candidates = []
    for word in words:
        aliases = _SEMANTIC_ALIASES.get(word.lower(), [])
        for alias in aliases:
            for col in columns:
                if alias in col or col in alias:
                    candidates.append(col)
    # Prefer the most specific (longest) candidate
    return max(candidates, key=len) if candidates else None


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
    """
    Return columns whose names appear as whole words in *text*.

    Uses word-boundary matching so 'id' won't match inside 'idaho',
    and 'name' won't match inside 'surname'.

    For multi-part column names (e.g. 'city_name') also matches when
    the user writes the parts separately ('city name') or mentions
    all parts anywhere in the text ('show city and name').
    """
    matched = []
    for col in columns:
        parts = col.split("_")

        singular_col = col.rstrip("s")
        plural_col = col + "s"

        # Try 1: exact whole-word match (handles both 'id' and 'city_name')
        exact_pattern = r"\b" + re.escape(col) + r"\b"
        if re.search(exact_pattern, text):
            matched.append(col)
            continue

        if re.search(r"\b" + re.escape(singular_col) + r"\b", text):
            matched.append(col)
            continue

        if re.search(r"\b" + re.escape(plural_col) + r"\b", text):
            matched.append(col)
            continue

        # Try 2: parts written with a space ('city name')
        if len(parts) > 1:
            spaced_pattern = r"\b" + r"\s+".join(re.escape(p) for p in parts) + r"\b"
            if re.search(spaced_pattern, text):
                matched.append(col)
                continue

        # Try 3: all parts appear somewhere in the text as whole words
        # (e.g. 'city_name' when user says 'show city and name')
        if len(parts) > 1 and all(
            re.search(r"\b" + re.escape(p) + r"\b", text) for p in parts
        ):
            matched.append(col)

    return matched


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
            mentioned = find_mentioned_columns(text, columns)

            # If user says "count files" and files is a numeric measure column,
            # use SUM(files), not COUNT(*).
            if func == "COUNT" and mentioned:
                before_by = text.split(" by ", 1)[0] if " by " in text else text
                measure_columns = find_mentioned_columns(before_by, columns)

                if measure_columns:
                    return {
                        "function": "SUM",
                        "field": measure_columns[0],
                    }

            field = default_field

            if field is None:
                before_by = text.split(" by ", 1)[0] if " by " in text else text
                measure_columns = find_mentioned_columns(before_by, columns)
                field = measure_columns[0] if measure_columns else (mentioned[0] if mentioned else "*")

            return {"function": func, "field": field}

    return None


def detect_group_by(text: str, columns: list[str]) -> str | None:
    """
    Return a group-by column when an aggregation keyword AND "by" are present.

    Matches both exact column names and semantically related words —
    e.g. "count missions by space agency" -> agency_id because "agency"
    is a substring of the column name "agency_id".
    """
    has_agg = any(kw in text for kw in _AGGREGATION_MAP)
    if not has_agg or " by " not in text:
        return None

    after_by = text.split(" by ", 1)[1]

    # Pass 1: exact whole-word match
    exact = find_mentioned_columns(after_by, columns)
    if exact:
        return exact[0]

    # Pass 2: partial / semantic match — any word in after_by that is a
    # substring of a column name (catches "agency" -> "agency_id")
    words_after = re.findall(r"[a-z]+", after_by.lower())
    for col in columns:
        if any(w in col for w in words_after if len(w) > 2):
            return col

    return None


def detect_limit(text: str) -> int | None:
    m = _TOP_N_RE.search(text)
    if not m:
        return None
    # _TOP_N_RE has 3 capture groups; return the first non-None one
    value = next((g for g in m.groups() if g is not None), None)
    return int(value) if value is not None else None


def detect_sort(
    text: str,
    columns: list[str],
    group_by: str | None = None,
) -> dict[str, str] | None:
    words = set(text.split())

    if words & _SORT_DESC_WORDS:
        direction = "DESC"
    elif words & _SORT_ASC_WORDS:
        direction = "ASC"
    else:
        return None

    if group_by:
        return {"field": group_by, "direction": direction}

    # For phrases like:
    # "top 10 extensions by size"
    # "largest files by allocated"
    # the column after "by" is the sort column.
    if " by " in text:
        after_by = text.split(" by ", 1)[1]
        cols_after_by = find_mentioned_columns(after_by, columns)

        if cols_after_by:
            return {
                "field": cols_after_by[0],
                "direction": direction,
            }

    sort_keyword_re = re.compile(
        r"\b(highest|largest|top|lowest|smallest|order(?:ed)?\s+by)\b"
    )

    m = sort_keyword_re.search(text)
    if m:
        after_keyword = text[m.end():]
        cols_after = find_mentioned_columns(after_keyword, columns)
        if cols_after:
            return {"field": cols_after[0], "direction": direction}

    field = next(iter(find_mentioned_columns(text, columns)), None)

    if not field:
        words = re.findall(r"[a-z]+", text.lower())
        field = _resolve_semantic_column(words, columns)

    if not field:
        return None

    return {"field": field, "direction": direction}


def extract_text_filter(clause: str, columns: list[str]) -> dict[str, Any] | None:
    """
    Detect text equality filters such as:
    extension is .dll
    extension equals .dll
    extension = .dll
    file type is image

    This is schema-driven, not domain-hardcoded.
    It works for any column name in any uploaded dataset.
    """
    clause = clause.strip().lower()

    equality_patterns = [
        r"\bis\b",
        r"\bequals\b",
        r"\bequal to\b",
        r"=",
    ]

    mentioned_columns = find_mentioned_columns(clause, columns)

    if not mentioned_columns:
        return None

    for col in mentioned_columns:
        column_text = col.replace("_", " ")

        for pattern in equality_patterns:
            regex = rf"\b{re.escape(column_text)}\b\s*{pattern}\s*(.+)$"
            match = re.search(regex, clause)

            if match:
                value = match.group(1).strip()

                if not value:
                    return None

                return {
                    "field": col,
                    "operator": "=",
                    "value": value,
                }

    return None


def detect_filters(text: str, columns: list[str]) -> list[dict[str, Any]]:
    """
    Extract WHERE-clause filters from *text*.

    Splits on AND/OR to handle multiple conditions independently.
    Within each clause, a filter is only attached to a column if that column
    is plausibly the subject of the comparison — i.e. it appears in the same
    clause as both a comparison operator and a numeric value.

    A column is treated as the filter subject when:
      - It is the ONLY column mentioned in the clause, OR
      - It appears within a short window (≤5 tokens) before the operator/value.
    """
    clause_texts = re.split(r"\band\b|\bor\b", text)
    filters = []
    seen    = set()

    for clause in clause_texts:
        operator = detect_operator(clause)
        value    = extract_number(clause)

        if operator is not None and value is not None:
            pass
        else:
            text_filter = extract_text_filter(clause, columns)

            if text_filter:
                key = (
                    text_filter["field"],
                    text_filter["operator"],
                    text_filter["value"],
                )

                if key not in seen:
                    seen.add(key)
                    filters.append(text_filter)

            continue

        clause_columns = find_mentioned_columns(clause, columns)
        clause_words   = re.findall(r"[a-z]+", clause.lower())

        if not clause_columns:
            # No column named directly — try semantic alias matching
            # e.g. "taller than 3000" -> height column
            sem_col = _resolve_semantic_column(clause_words, columns)
            if sem_col:
                target_columns = [sem_col]
            else:
                continue  # truly unresolvable — skip this clause
        elif len(clause_columns) == 1:
            # Unambiguous — only one column in this clause
            target_columns = clause_columns
        else:
            # Multiple columns: keep those closest to the operator/value
            op_match  = _OPERATOR_RE.search(clause)
            num_match = _NUMBER_RE.search(clause)
            ref_pos   = min(
                op_match.start()  if op_match  else len(clause),
                num_match.start() if num_match else len(clause),
            )

            before_op     = clause[:ref_pos]
            tokens_before = re.findall(r"\w+", before_op)
            window        = set(tokens_before[-5:])

            target_columns = [
                col for col in clause_columns
                if any(part in window for part in col.split("_"))
            ]

            # If window heuristic cleared everything, keep all clause columns
            if not target_columns:
                target_columns = clause_columns

        for col in target_columns:
            key = (col, operator, value)
            if key not in seen:
                seen.add(key)
                filters.append({"field": col, "operator": operator, "value": value})

    return filters


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
    1. Aggregation present -> select only the group-by column (or '*').
    2. Multiple columns mentioned -> return ALL of them; the user explicitly
       named them so they belong in the SELECT even if some are also used for
       sorting or filtering (e.g. 'show product_id and price ... order by price').
    3. Single column mentioned AND it is only there as a sort/filter target
       -> fall back to '*' (e.g. 'show products with lowest price').
    4. Default -> '*'.
    """
    if aggregation:
        return [group_by] if group_by else ["*"]

    mentioned = find_mentioned_columns(text, columns)
       
    if not mentioned:
        return ["*"]

    # If the user mentioned more than one column, keep them all —
    # they asked for those columns explicitly.
    if len(mentioned) > 1:
        return mentioned

    # Single mentioned column: check whether it is purely infrastructural
    sort_field    = sort.get("field")  if sort    else None
    filter_fields = {f["field"] for f in filters}

    only_col = mentioned[0]
    if only_col == sort_field or only_col in filter_fields:
        return ["*"]

    return mentioned


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
    if (
        aggregation
        and group_by
        and "most" in text
    ):
        sort = {
            "field": aggregation["field"],
            "direction": "DESC",
        }

        limit = 1
    else:
        sort = detect_sort(text, columns, group_by=group_by)
        limit = detect_limit(text)
    filters     = detect_filters(text, columns)
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