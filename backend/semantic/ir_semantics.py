"""
ir_semantics.py

Question-aware IR rewrites (Tier 1). The structural normalizer (ir_normalizer)
only sees the IR + schema; these rewrites additionally use the user's QUESTION to
correct intent that the extractor commonly gets wrong. Every trigger keys off
generic wording + schema (column types, names, foreign keys) — never off a
specific dataset, table, column, or question.

Classes handled:
  1. Row-level "more than N ... in one purchase/order/session/..." -> a row-level
     WHERE on the quantity column (not GROUP BY / HAVING COUNT).
  2. "most purchased/sold/ordered/shipped" -> SUM(quantity) instead of COUNT
     when the transaction table has a quantity column.
  5. "not returned/completed/shipped before YEAR" -> use the completion-date
     column with  <date> IS NULL OR <date> >= 'YEAR-01-01'.
  7. Entity completeness: a SELECT of only a foreign-key id whose target is a
     parent entity with a readable name/title column -> select the parent's
     id + name (schema-only; needs no question).

Pure functions: no database access, no model calls, no SQL generation.
"""

import re

from semantic.ir_normalizer import build_column_index

__all__ = ["apply_question_semantics"]

_NUMERIC = {"INTEGER", "REAL"}
_QTY_NAME = re.compile(r"(quantity|qty|units|num_items|item_count)", re.I)
_NAME_COL = re.compile(r"(name|title)$", re.I)
_DATE_SAMPLE = re.compile(r"^\s*\d{4}-\d{2}-\d{2}")

# wording triggers
_MORE_THAN = re.compile(r"\b(more than|over|greater than|at least)\s+(\d+)\b", re.I)
_IN_ONE_TXN = re.compile(
    r"\b(?:in|per)\s+(?:a\s+|one\s+|a\s+single\s+|each\s+)?"
    r"(purchase|order|session|transaction|visit|booking|trip|stay|rental|ride|sale)\b",
    re.I,
)
_MOST_TXN = re.compile(
    r"(most\s+\w*\s*(purchased|sold|ordered|shipped|bought|rented|booked)"
    r"|(purchased|sold|ordered|shipped|bought|rented|booked)\s+the\s+most)",
    re.I,
)
_NOT_DONE_BEFORE = re.compile(
    r"\bnot\s+(returned|completed|shipped|delivered|finished|ended|paid|sent)\s+"
    r"before\s+(\d{4})\b",
    re.I,
)
_REVENUE = re.compile(r"\b(revenue|sales|spend|spent|total\s+price)", re.I)
_PRICE_NAME = re.compile(r"(unit_price|price|cost)", re.I)
_DISCOUNT_NAME = re.compile(r"(discount_percent|discount_pct|discount)", re.I)
_COMPARE_OPS = {"=", "==", ">", "<", ">=", "<="}
_OPPOSITE = {
    "home": "away", "away": "home", "start": "end", "end": "start",
    "first": "last", "last": "first", "min": "max", "max": "min",
    "origin": "destination", "destination": "origin", "source": "dest",
    "dest": "source", "before": "after", "after": "before",
    "left": "right", "right": "left",
}
_DESCRIPTORS = ("preferred_", "favorite_", "favourite_", "primary_",
                "chosen_", "desired_", "matching_")
# Comparison-intent wording (lets field-to-field fire even when the extractor put
# a non-empty placeholder value on the filter).
_VICTORY = re.compile(r"\b(won|wins|winner|win|beat|beats|defeat|defeated)\b", re.I)
_RELATIONAL = re.compile(r"\b(their|matching|same|equal|equals)\b", re.I)


def _lower(v):
    return str(v).strip().lower() if v is not None else ""


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------
def _table_columns(graph):
    """{table_lower: [{'name': col_lower, 'meta': meta}]} from the schema graph."""
    if isinstance(graph, dict) and isinstance(graph.get("database"), dict):
        graph = graph["database"]
    out = {}
    for t in (graph.get("tables") if isinstance(graph, dict) else None) or []:
        if not isinstance(t, dict):
            continue
        tname = _lower(t.get("table_name"))
        cols = []
        for c in t.get("columns") or []:
            if isinstance(c, dict):
                cols.append({
                    "name": _lower(c.get("column_name")),
                    "meta": {
                        "data_type": str(c.get("data_type") or "").upper(),
                        "sample_values": c.get("sample_values") or [],
                    },
                })
        out[tname] = cols
    return out


def _is_numeric(meta):
    return meta and meta.get("data_type") in _NUMERIC


def _is_date(meta):
    if not meta:
        return False
    dt = meta.get("data_type", "")
    if "DATE" in dt or "TIME" in dt:
        return True
    return any(s is not None and _DATE_SAMPLE.match(str(s))
               for s in meta.get("sample_values") or [])


def _find_quantity_column(tables, tcols):
    """Return (table, column) of a numeric quantity-like column among `tables`."""
    for t in tables:
        for c in tcols.get(_lower(t), []):
            if _is_numeric(c["meta"]) and _QTY_NAME.search(c["name"]):
                return _lower(t), c["name"]
    return None


def _find_name_column(table, tcols):
    """A readable display column (…name / …title) for a table."""
    for c in tcols.get(_lower(table), []):
        if _NAME_COL.search(c["name"]):
            return c["name"]
    return None


def _relationships(graph):
    if isinstance(graph, dict) and isinstance(graph.get("database"), dict):
        graph = graph["database"]
    return (graph.get("relationships") if isinstance(graph, dict) else None) or []


def _fk_target(table, column, graph):
    """If (table, column) is a foreign key, return (to_table, to_column)."""
    t, c = _lower(table), _lower(column)
    for r in _relationships(graph):
        if _lower(r.get("from_table")) == t and _lower(r.get("from_column")) == c:
            return _lower(r.get("to_table")), _lower(r.get("to_column"))
    return None


# ---------------------------------------------------------------------------
# Clause helpers
# ---------------------------------------------------------------------------
def _entity_table(entries):
    """First table appearing among select / group_by entries."""
    for e in entries or []:
        if isinstance(e, dict) and e.get("table"):
            return _lower(e.get("table"))
    return None


def _select_has(select, table, column):
    return any(
        isinstance(s, dict)
        and _lower(s.get("table")) == _lower(table)
        and _lower(s.get("column")) == _lower(column)
        for s in select or []
    )


# ---------------------------------------------------------------------------
# 1. Row-level "more than N in one <txn>"
# ---------------------------------------------------------------------------
def rewrite_row_level_quantity(question, extraction, tcols):
    m_more = _MORE_THAN.search(question or "")
    if not m_more or not _IN_ONE_TXN.search(question or ""):
        return extraction

    n = int(m_more.group(2))
    op = ">=" if m_more.group(1).lower() == "at least" else ">"

    tables = [_lower(t) for t in (extraction.get("tables") or [])]
    qty = _find_quantity_column(tables, tcols)
    if not qty:
        return extraction
    qt, qc = qty

    ex = dict(extraction)
    # A row-level filter, no aggregation/grouping.
    ex["aggregations"] = []
    ex["group_by"] = []
    ex["having"] = []
    ex["distinct"] = True

    # Keep entity columns; if select is empty, promote the group_by entity.
    select = [s for s in (extraction.get("select") or []) if isinstance(s, dict)]
    if not select:
        select = [dict(g) for g in (extraction.get("group_by") or []) if isinstance(g, dict)]
    # Add a readable name column for the entity if available.
    ent = _entity_table(select) or _entity_table(extraction.get("group_by"))
    if ent:
        name_col = _find_name_column(ent, tcols)
        if name_col and not _select_has(select, ent, name_col):
            select.append({"table": ent, "column": name_col})
    ex["select"] = select

    filters = [f for f in (extraction.get("filters") or []) if isinstance(f, dict)]
    filters.append({"table": qt, "column": qc, "op": op, "value": n})
    ex["filters"] = filters
    return ex


# ---------------------------------------------------------------------------
# 2. "most purchased/sold/..." -> SUM(quantity)
# ---------------------------------------------------------------------------
def prefer_sum_quantity(question, extraction, tcols):
    if not _MOST_TXN.search(question or ""):
        return extraction

    aggs = [a for a in (extraction.get("aggregations") or []) if isinstance(a, dict)]
    count_idx = next(
        (i for i, a in enumerate(aggs)
         if str(a.get("function", "")).upper() == "COUNT"),
        None,
    )
    if count_idx is None:
        return extraction

    tables = [_lower(t) for t in (extraction.get("tables") or [])]
    qty = _find_quantity_column(tables, tcols)
    if not qty:
        return extraction
    qt, qc = qty

    new_aggs = [dict(a) for a in aggs]
    a = new_aggs[count_idx]
    a["function"] = "SUM"
    a["table"] = qt
    a["column"] = qc
    # keep the original alias so ORDER BY referencing it still resolves
    ex = dict(extraction)
    ex["aggregations"] = new_aggs
    return ex


# ---------------------------------------------------------------------------
# 5. "not returned/completed/... before YEAR"
# ---------------------------------------------------------------------------
def rewrite_completion_date_null_or_after(question, extraction, tcols):
    m = _NOT_DONE_BEFORE.search(question or "")
    if not m:
        return extraction

    verb_stem = m.group(1).lower()[:5]   # return->retur, complete->compl, ship->ship
    year = int(m.group(2))

    tables = [_lower(t) for t in (extraction.get("tables") or [])]
    target = None
    for t in tables:
        for c in tcols.get(t, []):
            if _is_date(c["meta"]) and verb_stem in c["name"]:
                target = (t, c["name"])
                break
        if target:
            break
    if not target:
        return extraction
    dt, dc = target

    # Drop any existing filters on date columns of the same table (the extractor
    # often picked the wrong start-date column); keep non-date filters.
    date_cols = {c["name"] for c in tcols.get(dt, []) if _is_date(c["meta"])}
    kept = [
        f for f in (extraction.get("filters") or [])
        if not (isinstance(f, dict) and _lower(f.get("table")) == dt
                and _lower(f.get("column")) in date_cols)
    ]
    kept.append({"table": dt, "column": dc, "op": "IS NULL", "connector": "OR"})
    kept.append({"table": dt, "column": dc, "op": ">=", "value": f"{year}-01-01"})

    ex = dict(extraction)
    ex["filters"] = kept
    return ex


# ---------------------------------------------------------------------------
# 7. Entity completeness (schema-only)
# ---------------------------------------------------------------------------
def add_entity_display_columns(extraction, graph, tcols):
    select = [s for s in (extraction.get("select") or []) if isinstance(s, dict)]
    aggregations = extraction.get("aggregations") or []
    if not select or aggregations:
        return extraction  # only for plain entity projections

    # already has a readable column?
    if any(_NAME_COL.search(_lower(s.get("column"))) for s in select):
        return extraction

    # exactly one selected column, and it is a FK id pointing to a parent entity
    if len(select) != 1:
        return extraction
    s = select[0]
    target = _fk_target(s.get("table"), s.get("column"), graph)
    if not target:
        return extraction
    pt, pc = target
    name_col = _find_name_column(pt, tcols)
    if not name_col:
        return extraction

    ex = dict(extraction)
    ex["select"] = [{"table": pt, "column": pc}, {"table": pt, "column": name_col}]
    tables = [_lower(t) for t in (extraction.get("tables") or [])]
    if pt not in tables:
        tables.append(pt)
    ex["tables"] = tables
    return ex


# ---------------------------------------------------------------------------
# 3A. Derived monetary metric: revenue/spend -> SUM(quantity * price [* discount])
# ---------------------------------------------------------------------------
def _find_price_column(qty_table, tables, tcols, graph):
    """A numeric price-like column, preferring tables already in the IR, then
    the quantity table's foreign-key targets (the item/product table)."""
    def scan(t):
        for c in tcols.get(_lower(t), []):
            if (_is_numeric(c["meta"]) and _PRICE_NAME.search(c["name"])
                    and not _DISCOUNT_NAME.search(c["name"])):
                return _lower(t), c["name"]
        return None
    for t in tables:
        hit = scan(t)
        if hit:
            return hit
    for r in _relationships(graph):
        if _lower(r.get("from_table")) == _lower(qty_table):
            hit = scan(_lower(r.get("to_table")))
            if hit:
                return hit
    return None


def _find_discount_column(qty_table, tcols):
    for c in tcols.get(_lower(qty_table), []):
        if _is_numeric(c["meta"]) and _DISCOUNT_NAME.search(c["name"]):
            return _lower(qty_table), c["name"]
    return None


def rewrite_revenue_metric(question, extraction, graph, tcols):
    if not _REVENUE.search(question or ""):
        return extraction

    aggs = [a for a in (extraction.get("aggregations") or []) if isinstance(a, dict)]
    idx = next(
        (i for i, a in enumerate(aggs)
         if str(a.get("function", "")).upper() == "SUM"
         and _lower(a.get("column")) and _QTY_NAME.search(_lower(a.get("column")))),
        None,
    )
    if idx is None:
        return extraction

    qt, qc = _lower(aggs[idx].get("table")), _lower(aggs[idx].get("column"))
    tables = [_lower(t) for t in (extraction.get("tables") or [])]
    price = _find_price_column(qt, tables, tcols, graph)
    if not price:
        return extraction  # back off: cannot find a price column confidently
    pt, pc = price

    expr = {"op": "*",
            "left": {"col": {"table": qt, "column": qc}},
            "right": {"col": {"table": pt, "column": pc}}}
    disc = _find_discount_column(qt, tcols)
    if disc:
        dt, dc = disc
        expr = {"op": "*", "left": expr,
                "right": {"op": "-", "left": {"lit": 1},
                          "right": {"op": "/",
                                    "left": {"col": {"table": dt, "column": dc}},
                                    "right": {"lit": 100.0}}}}

    new_aggs = [dict(a) for a in aggs]
    a = new_aggs[idx]
    a["function"] = "SUM"
    a["expr"] = expr
    a["table"] = None
    a["column"] = None

    ex = dict(extraction)
    ex["aggregations"] = new_aggs
    if pt not in tables:
        tables = tables + [pt]
    ex["tables"] = tables
    return ex


# ---------------------------------------------------------------------------
# 3B. Field-to-field comparisons (column reference instead of a parameter)
# ---------------------------------------------------------------------------
def _is_empty_value(v):
    return v is None or (isinstance(v, str) and v.strip() in ("", "?"))


def _col_meta(table, column, tcols):
    for c in tcols.get(_lower(table), []):
        if c["name"] == _lower(column):
            return c["meta"]
    return None


def _reachable_tables(ir_tables, graph):
    """Tables reachable from the IR tables over relationships (undirected)."""
    adj = {}
    for r in _relationships(graph):
        a, b = _lower(r.get("from_table")), _lower(r.get("to_table"))
        if a and b:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    seen = {_lower(t) for t in ir_tables}
    stack = list(seen)
    while stack:
        cur = stack.pop()
        for nb in adj.get(cur, ()):
            if nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return seen


def _opposite_sibling(ftab, fcol, tcols):
    """Same-table opposite-prefix numeric sibling (home_score -> away_score)."""
    if "_" not in fcol:
        return None
    prefix, base = fcol.split("_", 1)
    opp = _OPPOSITE.get(prefix)
    if not opp:
        return None
    if not _is_numeric(_col_meta(ftab, fcol, tcols)):
        return None
    sib = f"{opp}_{base}"
    if any(c["name"] == sib and _is_numeric(c["meta"]) for c in tcols.get(ftab, [])):
        return ftab, sib
    return None


def _descriptor_target(fcol, ir_tables, tcols, graph):
    """Descriptor-prefix base noun (preferred_cuisine -> cuisine) in a table that
    is reachable from the IR. Returns (table, column) or None."""
    for d in _DESCRIPTORS:
        if not fcol.startswith(d):
            continue
        noun = fcol[len(d):]
        if not noun:
            return None
        reach = _reachable_tables(ir_tables, graph)
        for t, cols in tcols.items():
            if t in reach and any(c["name"] == noun for c in cols):
                return t, noun
        return None
    return None


def rewrite_field_to_field(question, extraction, graph, tcols):
    filters = extraction.get("filters") or []
    ir_tables = [_lower(t) for t in (extraction.get("tables") or [])]
    victory = bool(_VICTORY.search(question or ""))
    relational = bool(_RELATIONAL.search(question or ""))

    out = []
    changed = False
    to_add = []
    for f in filters:
        if (not isinstance(f, dict) or f.get("value_ref")
                or str(f.get("op") or "").strip() not in _COMPARE_OPS):
            out.append(f)
            continue
        ftab, fcol = _lower(f.get("table")), _lower(f.get("column"))
        empty = _is_empty_value(f.get("value"))

        ref = None
        sib = _opposite_sibling(ftab, fcol, tcols)
        if sib and (empty or victory):
            ref = sib
        if ref is None:
            desc = _descriptor_target(fcol, ir_tables, tcols, graph)
            if desc and (empty or relational):
                ref = desc
                if desc[0] not in ir_tables and desc[0] not in to_add:
                    to_add.append(desc[0])

        if ref:
            nf = dict(f)
            nf.pop("value", None)
            nf["value_ref"] = {"table": ref[0], "column": ref[1]}
            out.append(nf)
            changed = True
        else:
            out.append(f)

    if not changed:
        return extraction
    ex = dict(extraction)
    ex["filters"] = out
    if to_add:
        ex["tables"] = ir_tables + to_add
    return ex


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def apply_question_semantics(question, extraction, graph):
    """Apply the question-aware rewrites. Returns a new extraction dict;
    a no-op when nothing matches or graph/question is missing."""
    if not isinstance(extraction, dict):
        return extraction
    tcols = _table_columns(graph)

    extraction = rewrite_row_level_quantity(question, extraction, tcols)
    extraction = prefer_sum_quantity(question, extraction, tcols)
    extraction = rewrite_revenue_metric(question, extraction, graph, tcols)
    extraction = rewrite_completion_date_null_or_after(question, extraction, tcols)
    extraction = rewrite_field_to_field(question, extraction, graph, tcols)
    extraction = add_entity_display_columns(extraction, graph, tcols)
    return extraction
