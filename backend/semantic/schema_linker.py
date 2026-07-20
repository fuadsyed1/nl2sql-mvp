"""
semantic/schema_linker.py

Schema-linker correction for the semantic checklist's `must_use_tables`.

The checklist LLM often links the WRONG table before any SQL is generated —
a sibling census table for the wrong state, a direct ZIP<->tract join instead
of the mapping table, or it drops a table the question named explicitly. Once a
wrong table enters `must_use_tables` / the focused schema, generation is
poisoned and scoring cannot recover.

This module deterministically CORRECTS `must_use_tables` (no LLM call) using:
  (1) exact table-name locking — a table whose name appears in the question,
      matched separator-INSENSITIVELY (so "census tracts new york" locks
      `census_tracts_new_york`), is forced in and never dropped/replaced;
  (2) sibling disambiguation — among a same-family/prefix group, keep the
      sibling whose distinguishing tokens match the question; drop siblings
      whose location/suffix tokens are absent from the question; never guess a
      random sibling when none matches;
  (3) ZIP->tract bridge detection — add an existing zip/postal <-> tract/census
      mapping table when the question spans both concepts;
  (4) ACS/metric table preservation — add a table that actually contains the
      requested metric column (e.g. median_income);
  (5) low-confidence safety — keep exact mentions + safe bridge/metric tables,
      never a guessed sibling.

IMPORTANT: the FINAL step re-adds the exact-named tables plus the required
bridge/metric tables, so no earlier pruning (sibling / metric / cleanup) can
ever drop them.

Everything is generic token logic — no table, state, or database is hardcoded.
Never raises: on any problem it returns the checklist unchanged.
"""

import re

from query_families.slot_extractor import index_schema
from schema.table_mention import explicit_table_mentions
from sql_candidates.explicit_table_lock import _toks, _family_tokens
from sql_candidates.semantic_join_discovery import (
    _GEO, _BRIDGEABLE, _is_bridge_table, _ctoks, _concepts_of,
)

__all__ = ["correct_checklist_tables"]

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")


def _name_tokens(s):
    return [t for t in _WORD_SPLIT.split(str(s or "").lower()) if t]


def _is_id_like(name):
    """True for key/id-like column names (playerID, teamID, id). These are
    SHARED KEYS and must never drive table expansion — many tables carry them."""
    n = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
    return n == "id" or n.endswith("id")


def _col_ref(item):
    """Parse a column reference into (table_or_None, column). Accepts
    'table.col', 'col', or a dict with 'column'/'table'."""
    if isinstance(item, dict):
        col = item.get("column")
        tbl = item.get("table")
        if isinstance(col, str) and col.strip():
            return ((str(tbl).strip().lower() or None) if tbl else None,
                    col.strip().lower())
        return None
    s = str(item or "").strip().lower()
    if not s:
        return None
    if "." in s:
        t, c = s.split(".", 1)
        return (t.strip() or None, c.strip())
    return (None, s)


def _required_column_refs(checklist):
    """Every column the query actually needs (output / filter / group / measure),
    as (table_or_None, column) pairs. Empty when the checklist has no columns."""
    refs = []
    cl = checklist or {}
    for key in ("must_use_columns", "output_columns", "required_group_keys",
                "filter_columns", "group_by_columns"):
        v = cl.get(key)
        if isinstance(v, list):
            for item in v:
                r = _col_ref(item)
                if r:
                    refs.append(r)
    mc = cl.get("measure_column")
    if mc:
        r = _col_ref(mc)
        if r:
            refs.append(r)
    return refs


def _col_in_tables(tables, col, idx):
    col = str(col or "").lower()
    for t in tables:
        for c in idx["tables"].get(t, []):
            if str(c.get("name") or "").lower() == col:
                return True
    return False


def _covers(tables, refs, idx):
    """True when `tables` already contain every required column: a qualified
    ref's table must be in `tables`; a bare column must exist in one of them.
    Returns False on empty refs (can't confirm self-sufficiency -> don't focus)."""
    if not refs:
        return False
    for (t, c) in refs:
        if c == "*":
            continue
        if t:
            if t not in tables:
                return False
        elif not _col_in_tables(tables, c, idx):
            return False
    return True


def _exact_named_tables(question, names):
    """Schema table names the question EXPLICITLY references (separator-
    insensitive). A distinctive name (multi-token / digit / underscore / very
    long token) locks on a bare mention; a plain single-word name (customer,
    employee, department) locks only with an explicit table cue ('customer
    table', 'from customer', 'customer.id'). Delegates to the shared detector so
    the linker, graph-forcing, and enforcement all agree on 'explicit'."""
    return {n.lower() for n in explicit_table_mentions(question, names)}


def correct_checklist_tables(question, checklist, graph):
    """Return a checklist dict whose `must_use_tables` has been corrected.
    Works even when `checklist` is None. Returns the original object on any
    failure or when there is nothing to add."""
    try:
        idx = index_schema(graph)
    except Exception:
        return checklist
    names = set(idx.get("tables") or {})
    if not names:
        return checklist

    # QUESTION-ONLY tokens: a wrong table already sitting in must_use_tables
    # must not be able to "defend itself" via the checklist text.
    qtoks = _ctoks(question or "")
    geo_all = set().union(*_GEO.values())

    must = {str(t).lower() for t in (checklist or {}).get("must_use_tables") or []
            if str(t).lower() in names}
    orig_must = set(must)   # the checklist's own target tables (pre-correction)

    # (1) exact table-name locking (separator-insensitive) ------------------
    locked = _exact_named_tables(question, names)
    must |= locked

    # Focused-schema guard: if the checklist already names the target table(s)
    # and EVERY required output/filter/group/measure column lives inside those
    # tables, keep ONLY those tables (plus any table the question names
    # verbatim). This stops shared keys (playerID, teamID, ...) from expanding
    # must_use_tables to the whole related-table neighborhood on big / local
    # benchmark schemas. Extra tables are added ONLY when a needed column is not
    # covered by the stated tables (handled by the normal steps below).
    refs = _required_column_refs(checklist)
    if orig_must and _covers(orig_must, refs, idx):
        focused = sorted(orig_must | (locked & names))
        print(f"FINAL must_use_tables (focused, no expansion): {focused}",
              flush=True)
        out = dict(checklist or {})
        out["must_use_tables"] = focused
        return out

    # (2) sibling disambiguation -------------------------------------------
    family = _family_tokens(names)
    fam_groups = {}
    for t in names:
        for tok in _toks(t) & family:
            fam_groups.setdefault(tok, set()).add(t)
    family_members = set().union(*fam_groups.values()) if fam_groups else set()

    def _distinct(t):
        return _toks(t) - family

    to_remove = set()
    for _tok, members in fam_groups.items():
        mentioned = members & locked
        matching = {t for t in members if _distinct(t) & qtoks}
        preferred = mentioned | matching
        if not preferred:
            continue                       # ambiguous -> do not guess a sibling
        for t in (members & must):
            if t not in preferred and t not in locked:
                to_remove.add(t)           # wrong sibling (tokens absent from Q)
        if not (members & must & preferred):
            best = sorted(mentioned) or sorted(matching)
            if best:
                must.add(best[0])          # bring in the best-matching sibling
    must -= to_remove

    # (3) ZIP->tract (etc.) bridge detection --------------------------------
    bridge_required = set()
    qgeo = _concepts_of(qtoks, _GEO)
    for pair in sorted(_BRIDGEABLE, key=lambda p: sorted(p)):
        a, b = sorted(pair)
        if a in qgeo and b in qgeo:
            bridges = [t for t in names if _is_bridge_table(idx, t, a, b)]
            if bridges:
                already = set(bridges) & (must | locked)
                bridge_required.add(sorted(already)[0] if already
                                    else sorted(bridges)[0])

    # (4) ACS / metric table preservation -----------------------------------
    #     Match specific metric words (>=5 chars, not geo/family tokens) against
    #     real MEASURE columns (non-key, non-geo). Never pull in an ambiguous
    #     same-family sibling: only tables outside a shared-prefix family (or one
    #     already kept/locked) may be added here.
    metric_required = set()
    metric_toks = {t for t in qtoks
                   if len(t) >= 5 and t not in geo_all and t not in family
                   and not _is_id_like(t)}
    mc = (checklist or {}).get("measure_column")
    if mc:
        metric_toks |= {t for t in _ctoks(mc)
                        if len(t) >= 5 and t not in geo_all and t not in family
                        and not _is_id_like(t)}
    if metric_toks:
        for t in names:
            if t in family_members and t not in (must | locked):
                continue                       # do not add an ambiguous sibling
            coltoks = set()
            for c in idx["tables"].get(t, []):
                # Skip declared keys AND id-like shared keys (playerID, teamID):
                # a shared key column must never make a table look "required".
                if c.get("is_key") or _is_id_like(c.get("name")):
                    continue
                ct = _ctoks(c.get("name"))
                if ct & geo_all:
                    continue                    # skip geo/id-ish key columns
                coltoks |= {tk for tk in ct if len(tk) >= 5}
            if metric_toks & coltoks:
                metric_required.add(t)

    # FINAL guaranteed re-add: exact-named tables + required bridge + required
    # metric tables survive ALL earlier pruning. Nothing below may drop them.
    must |= locked
    must |= bridge_required
    must |= metric_required

    corrected = sorted(must)
    if not corrected:
        return checklist
    print(f"FINAL must_use_tables (schema-linker corrected): {corrected}",
          flush=True)
    out = dict(checklist or {})
    out["must_use_tables"] = corrected
    return out
