"""
schema/partition_filter.py

Large-mode helper: drop redundant date filters that merely restate the date
already encoded in a partition table name. Spider 2.0 / GA4-style datasets use
date-partitioned tables like ``events_20210110``; a filter such as
``event_date = '2021-01-10'`` on that table is redundant (and often wrong, since
the physical partition uses compact YYYYMMDD).

Conservative and generic — no table name or date is hardcoded. A filter is
removed only when ALL hold:
  1. the filter's table name contains a valid 8-digit YYYYMMDD token,
  2. the filter column is clearly date-like (event_date / *_date / date),
  3. the operator is equality, and
  4. the filter value normalizes to the SAME YYYYMMDD token.
Anything else (different date, range operator, non-date column, unparseable
value) is left untouched.
"""

import re

from retrieval.table_retriever import _date_tokens

__all__ = [
    "remove_redundant_partition_date_filters",
    "detect_partitioned_ambiguity",
]


def _ir_get(ir, key, default=None):
    if isinstance(ir, dict):
        return ir.get(key, default)
    return getattr(ir, key, default)


def _ir_set(ir, key, value):
    if isinstance(ir, dict):
        ir[key] = value
    else:
        setattr(ir, key, value)


def _fget(f, key, default=None):
    if isinstance(f, dict):
        return f.get(key, default)
    return getattr(f, key, default)


def _valid_yyyymmdd(tok):
    if not re.fullmatch(r"\d{8}", str(tok)):
        return False
    y, mo, d = int(tok[:4]), int(tok[4:6]), int(tok[6:8])
    return 1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31


def _partition_date_token(name):
    """Return the first valid 8-digit YYYYMMDD date embedded in a table name."""
    for m in re.finditer(r"(\d{8})", str(name or "")):
        if _valid_yyyymmdd(m.group(1)):
            return m.group(1)
    return None


def _is_date_like(col):
    c = str(col or "").lower()
    return c == "date" or c == "event_date" or c.endswith("_date") or c.startswith("date_")


def _value_date_tokens(value):
    s = "" if value is None else str(value).strip()
    toks = set(_date_tokens(s))
    if _valid_yyyymmdd(s):
        toks.add(s)
    return toks


def remove_redundant_partition_date_filters(ir):
    """Mutate ir.filters to drop redundant partition-date equality filters.
    Returns a diagnostics dict (empty when nothing was removed)."""
    diag = {}
    tables = _ir_get(ir, "tables") or []
    filters = _ir_get(ir, "filters") or []
    if not tables or not filters:
        return diag

    # Partition date token per table that has one.
    table_dates = {}
    for t in tables:
        tok = _partition_date_token(t)
        if tok:
            table_dates[t] = tok
    if not table_dates:
        return diag

    kept = []
    removed_token = None
    for f in filters:
        tbl = _fget(f, "table")
        ptoken = None
        if tbl and tbl in table_dates:
            ptoken = table_dates[tbl]
        elif tbl is None and len(table_dates) == 1:
            ptoken = next(iter(table_dates.values()))

        op = str(_fget(f, "op", "") or "").strip()
        col = _fget(f, "column")
        val = _fget(f, "value")

        if (
            ptoken
            and op == "="
            and _is_date_like(col)
            and ptoken in _value_date_tokens(val)
        ):
            removed_token = ptoken
            continue  # redundant — drop it

        kept.append(f)

    if removed_token is not None:
        _ir_set(ir, "filters", kept)
        diag["removed_redundant_partition_date_filter"] = True
        diag["partition_date"] = removed_token
    return diag


def _partition_prefix(name):
    """Return (prefix, token) if name is <prefix>_<YYYYMMDD> with a valid date,
    else (None, None)."""
    m = re.match(r"^(.*)_(\d{8})$", str(name or ""))
    if m and _valid_yyyymmdd(m.group(2)):
        return m.group(1), m.group(2)
    return None, None


def detect_partitioned_ambiguity(question, ir_tables):
    """Large-mode helper. Returns a diagnostics dict for an ambiguous
    partitioned-table query, or {} when not ambiguous.

    Ambiguous when the IR selected >= 2 date-partitioned tables (<prefix>_YYYYMMDD)
    that share a prefix, AND the question names neither a date nor an exact
    partition table. (If the question names a date, the missing-date guard
    handles it; if it names an exact table, that is unambiguous.)"""
    tables = list(ir_tables or [])
    if len(tables) < 2:
        return {}
    # A named date is handled elsewhere (date guard) — not this guard.
    if _date_tokens(question):
        return {}

    qlow = (question or "").lower()
    groups = {}
    for t in tables:
        prefix, _token = _partition_prefix(t)
        if prefix is None:
            continue
        if str(t).lower() in qlow:  # exact partition table named -> unambiguous
            return {}
        groups.setdefault(prefix, []).append(t)

    for prefix, members in groups.items():
        if len(members) >= 2:
            members_sorted = sorted(members)
            return {
                "error": "ambiguous_partitioned_table_query",
                "message": "Multiple date-partitioned tables matched. Please "
                           "specify a date or exact table name.",
                "matched_prefix": prefix,
                "candidate_tables": members_sorted,
                "example_table": members_sorted[0],
            }
    return {}
