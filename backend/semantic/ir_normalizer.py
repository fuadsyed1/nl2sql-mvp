"""
ir_normalizer.py

Deterministic, schema-aware IR clean-ups applied after extraction and before
validation/generation. Every rule keys off column metadata (data type, sample
values, primary-key flag) or the IR's own structure — never off specific table,
column, domain, or question text. The three normalizations fix recurring SQL
weaknesses generically:

  1. expand_year_filters   — "in <YEAR>" on a date column becomes a half-open
                             range  >= 'YYYY-01-01' AND < 'YYYY+1-01-01', and any
                             filter with a missing/unknown operator is repaired
                             so the renderer never emits  col ?  (a syntax error).
  2. ensure_group_by_in_select — every GROUP BY column missing from SELECT is
                             prepended, so "<aggregate> by X" actually selects X.
  3. normalize_string_values — an equality literal is mapped to the value as it
                             is actually stored, using the column's sample values
                             (boolean synonyms true/1/yes -> 'yes', and
                             case-folding 'Dessert' -> 'dessert'). High-cardinality
                             / unmatched values are left untouched.

Pure functions: no database access, no model calls, no SQL generation.
"""

import re

__all__ = ["normalize_ir", "build_column_index"]


_KNOWN_OPS = {
    "=", "==", "!=", "<>", "<", ">", "<=", ">=",
    "LIKE", "IN", "IS NULL", "IS NOT NULL",
}
_EQUALITY_OPS = {"=", "=="}
_EQUALITY_LIKE_OPS = {"", "=", "==", "IN", "LIKE"}
_DATE_SAMPLE = re.compile(r"^\s*\d{4}-\d{2}-\d{2}")
_YEAR = re.compile(r"^\s*\d{4}\s*$")
_YEAR_IN_VALUE = re.compile(r"(?:19|20)\d{2}")
_TRUTHY = {"true", "t", "1", "yes", "y"}
_FALSY = {"false", "f", "0", "no", "n"}


def _lower(value):
    return str(value).strip().lower() if value is not None else ""


def _norm_op(op):
    return str(op or "").strip().upper()


# ---------------------------------------------------------------------------
# Column index from the schema graph
# ---------------------------------------------------------------------------
def build_column_index(graph):
    """Return {(table_lower, column_lower): {data_type, sample_values, is_pk}}.

    Tolerates the raw schema graph (dict with 'tables') or one wrapped under a
    'database' key; returns {} for anything else."""
    if isinstance(graph, dict) and isinstance(graph.get("database"), dict):
        graph = graph["database"]
    tables = graph.get("tables") if isinstance(graph, dict) else None

    index = {}
    for table in tables or []:
        if not isinstance(table, dict):
            continue
        tname = _lower(table.get("table_name"))
        for col in table.get("columns") or []:
            if not isinstance(col, dict):
                continue
            cname = _lower(col.get("column_name"))
            index[(tname, cname)] = {
                "data_type": str(col.get("data_type") or "").upper(),
                "sample_values": col.get("sample_values") or [],
                "is_pk": bool(col.get("is_primary_key_candidate")),
            }
    return index


def _meta_for(index, entry):
    return index.get((_lower(entry.get("table")), _lower(entry.get("column"))))


# ---------------------------------------------------------------------------
# 1. Year / missing-operator filter repair
# ---------------------------------------------------------------------------
def _is_date_column(meta):
    if not meta:
        return False
    dt = meta.get("data_type", "")
    if "DATE" in dt or "TIME" in dt:
        return True
    for sample in meta.get("sample_values") or []:
        if sample is not None and _DATE_SAMPLE.match(str(sample)):
            return True
    return False


def _extract_year(value):
    """Return a 4-digit year (int) found in `value`, or None. Handles a bare
    year ('2025'), a full date ('2025-01-01'), and patterns like '2025%'."""
    if value is None:
        return None
    m = _YEAR_IN_VALUE.search(str(value))
    return int(m.group()) if m else None


def expand_year_filters(filters, index):
    """Collapse year filters on a date column into a half-open range
    (>= 'Y-01-01' AND < '(Y+1)-01-01'), and repair empty/unknown operators so the
    renderer never produces a bare `col ?`.

    A date column's filters collapse only when they all resolve to the SAME year
    and use equality/membership operators (=, ==, IN, LIKE, or empty). This
    handles a single bare year, a single full date, a LIKE 'YYYY%', and two
    equality filters for the same year. Filters that already form a directional
    range (>=, <, <=, >) are left untouched, so a correct range is never
    re-collapsed.
    """
    filters = list(filters or [])

    # Group date-column filter positions by (table, column), capturing the year
    # detected in each value and the operators used.
    groups = {}
    for i, f in enumerate(filters):
        if not isinstance(f, dict):
            continue
        if not _is_date_column(_meta_for(index, f)):
            continue
        year = _extract_year(f.get("value"))
        if year is None:
            continue
        key = (_lower(f.get("table")), _lower(f.get("column")))
        g = groups.setdefault(key, {"indices": [], "years": set(), "ops": set()})
        g["indices"].append(i)
        g["years"].add(year)
        g["ops"].add(_norm_op(f.get("op")))

    # Decide which groups collapse: a single year, equality/membership ops only.
    collapse_at = {}   # first index -> year
    drop = set()       # the other indices of a collapsing group
    for g in groups.values():
        if len(g["years"]) != 1:
            continue
        if not g["ops"] <= _EQUALITY_LIKE_OPS:
            continue  # leave a real >=/< range alone
        first = min(g["indices"])
        collapse_at[first] = next(iter(g["years"]))
        for i in g["indices"]:
            if i != first:
                drop.add(i)

    out = []
    for i, f in enumerate(filters):
        if i in drop:
            continue
        if i in collapse_at:
            year = collapse_at[i]
            lo = dict(f)
            lo["op"] = ">="
            lo["value"] = f"{year}-01-01"
            lo["connector"] = "AND"
            hi = dict(f)
            hi["op"] = "<"
            hi["value"] = f"{year + 1}-01-01"
            hi["connector"] = f.get("connector")  # link to whatever followed
            out.append(lo)
            out.append(hi)
            continue
        # Non-collapsing filter: repair an empty/unknown operator so it never
        # renders as `col ?`.
        if isinstance(f, dict):
            op = _norm_op(f.get("op"))
            if not op or op not in _KNOWN_OPS:
                fixed = dict(f)
                fixed["op"] = "="
                out.append(fixed)
                continue
        out.append(f)
    return out


# ---------------------------------------------------------------------------
# 2. GROUP BY label in SELECT
# ---------------------------------------------------------------------------
def ensure_group_by_in_select(select, group_by):
    """Prepend any GROUP BY column that is not already selected, so a grouped
    query returns its grouping label and not only the aggregate."""
    select = list(select or [])
    have = {(_lower(s.get("table")), _lower(s.get("column"))) for s in select
            if isinstance(s, dict)}
    prepend = []
    for g in group_by or []:
        if not isinstance(g, dict):
            continue
        key = (_lower(g.get("table")), _lower(g.get("column")))
        if key in have:
            continue
        have.add(key)
        prepend.append({"table": g.get("table"), "column": g.get("column")})
    return prepend + select


# ---------------------------------------------------------------------------
# 3. Equality value -> stored representation (boolean + categorical casing)
# ---------------------------------------------------------------------------
def normalize_string_values(filters, index):
    """Map an equality filter's literal to the value as actually stored, using
    the column's sample values. Boolean synonyms (true/1/yes...) resolve to the
    matching sample; otherwise a case-insensitive match case-folds to the stored
    casing. Unmatched values are left unchanged."""
    out = []
    for f in filters or []:
        if not isinstance(f, dict) or _norm_op(f.get("op")) not in {"="} | {"=="}:
            out.append(f)
            continue

        value = f.get("value")
        if isinstance(value, (list, tuple, dict)) or value is None:
            out.append(f)
            continue

        meta = _meta_for(index, f)
        if not meta:
            out.append(f)
            continue

        samples = [str(s) for s in (meta.get("sample_values") or [])
                   if s is not None and str(s).strip() != ""]
        if not samples:
            out.append(f)
            continue

        sample_by_lower = {}
        for s in samples:
            sample_by_lower.setdefault(s.strip().lower(), s)

        sval = str(value).strip().lower()
        new_value = None

        if sval in sample_by_lower:
            new_value = sample_by_lower[sval]            # case-fold to stored
        elif sval in _TRUTHY or sval in _FALSY:
            want = _TRUTHY if sval in _TRUTHY else _FALSY
            for low, original in sample_by_lower.items():
                if low in want:
                    new_value = original
                    break

        if new_value is not None and new_value != value:
            fixed = dict(f)
            fixed["value"] = new_value
            out.append(fixed)
        else:
            out.append(f)
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def normalize_ir(select, filters, group_by, graph):
    """Apply all deterministic normalizations. Returns (select, filters, group_by)
    new lists; inputs are not mutated. `graph` may be None (no-op for the
    schema-aware rules)."""
    index = build_column_index(graph)

    filters = expand_year_filters(filters, index)
    filters = normalize_string_values(filters, index)
    select = ensure_group_by_in_select(select, group_by)

    return select, filters, group_by
