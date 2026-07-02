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

__all__ = ["normalize_ir", "build_column_index", "resolve_column_comparisons",
           "promote_dict_value_refs"]


_KNOWN_OPS = {
    "=", "==", "!=", "<>", "<", ">", "<=", ">=",
    "LIKE", "IN", "IS NULL", "IS NOT NULL",
}
# Scalar comparison operators eligible for column-vs-column rewriting. LIKE / IN
# / IS [NOT] NULL are intentionally excluded.
_COMPARISON_OPS = {"=", "==", "!=", "<>", "<", ">", "<=", ">="}
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
# 4. Column-vs-column predicate detection (RHS literal -> value_ref)
# ---------------------------------------------------------------------------
def _columns_by_name(index):
    """column_name_lower -> set(table_name_lower) of tables having that column."""
    by_name = {}
    for (tname, cname) in index:
        by_name.setdefault(cname, set()).add(tname)
    return by_name


def _strip_ident(text):
    return str(text or "").strip().strip('"').strip("`").strip()


def _resolve_value_ref(raw, index, by_name, ir_tables):
    """Resolve an RHS string to a (table, column) that exists in the schema, or
    None. Dotted 'table.column' must exist in the index; a bare 'column' is
    accepted only when it is unambiguous among the IR's tables (exactly one
    owner). Never guesses."""
    text = str(raw).strip()
    if not text:
        return None
    if "." in text:
        left, right = text.split(".", 1)
        t, c = _lower(_strip_ident(left)), _lower(_strip_ident(right))
        return (t, c) if (t, c) in index else None
    name = _lower(_strip_ident(text))
    owners = by_name.get(name)
    if not owners:
        return None
    candidates = (owners & ir_tables) if ir_tables else owners
    return (next(iter(candidates)), name) if len(candidates) == 1 else None


def _value_matches_samples(index, entry, raw):
    """True when the RHS equals one of the LEFT column's stored sample values —
    i.e. it is a data literal (e.g. city = 'Moscow'), not a column reference."""
    meta = _meta_for(index, entry)
    if not meta:
        return False
    low = str(raw).strip().lower()
    for s in meta.get("sample_values") or []:
        if s is not None and str(s).strip().lower() == low:
            return True
    return False


def promote_dict_value_refs(filters):
    """Safety pass: a filter whose `value` is a column-ref dict {table, column}
    (a common extractor slip for column-to-column / date comparisons) is promoted
    to a proper `value_ref`, so a dict can never be bound as a scalar SQL
    parameter. Schema-independent; runs before the other normalizations."""
    out = []
    for f in filters or []:
        if (isinstance(f, dict) and f.get("value_ref") is None
                and isinstance(f.get("value"), dict)):
            v = f["value"]
            if v.get("table") and v.get("column"):
                nf = dict(f)
                nf.pop("value", None)
                nf["value_ref"] = {"table": _lower(v["table"]),
                                   "column": _lower(v["column"])}
                out.append(nf)
                continue
        out.append(f)
    return out


def resolve_column_comparisons(filters, index, ir_tables=None):
    """Convert a filter's scalar RHS string into a column reference (`value_ref`)
    when it unambiguously names a real schema column, so the generator renders a
    column-to-column comparison instead of a parameter.

    Conservative by design: only scalar comparison ops; only string values;
    never overwrites an existing value_ref; never links a column to itself; and
    a RHS that matches the LEFT column's stored samples is kept as a literal
    (false-positive guard, so 'Moscow'/'yes'/'none' stay parameters). Keys only
    off the schema column index and the IR's own tables — no table/column/domain
    names are hardcoded."""
    if not index:
        return list(filters or [])
    tables_set = {_lower(t) for t in (ir_tables or [])}
    by_name = _columns_by_name(index)

    out = []
    for f in filters or []:
        if not isinstance(f, dict) or f.get("value_ref") is not None:
            out.append(f)
            continue
        if _norm_op(f.get("op")) not in _COMPARISON_OPS:
            out.append(f)
            continue
        value = f.get("value")
        if not isinstance(value, str) or not value.strip():
            out.append(f)
            continue
        if _value_matches_samples(index, f, value):
            out.append(f)
            continue
        ref = _resolve_value_ref(value, index, by_name, tables_set)
        if ref is None or ref == (_lower(f.get("table")), _lower(f.get("column"))):
            out.append(f)
            continue
        fixed = dict(f)
        fixed.pop("value", None)
        fixed["value_ref"] = {"table": ref[0], "column": ref[1]}
        out.append(fixed)
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def normalize_ir(select, filters, group_by, graph, ir_tables=None):
    """Apply all deterministic normalizations. Returns (select, filters, group_by)
    new lists; inputs are not mutated. `graph` may be None (no-op for the
    schema-aware rules). `ir_tables` (the IR's table set) scopes bare-column
    resolution in column-vs-column detection."""
    index = build_column_index(graph)

    filters = promote_dict_value_refs(filters)
    filters = expand_year_filters(filters, index)
    filters = normalize_string_values(filters, index)
    filters = resolve_column_comparisons(filters, index, ir_tables)
    select = ensure_group_by_in_select(select, group_by)

    return select, filters, group_by
