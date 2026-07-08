"""
sql_candidates/semantic_join_discovery.py

Phase 3 — lightweight Aurum/WarpGate-style semantic join discovery (advisory).

This does NOT plan SQL and adds NO LLM call. Given the question, the semantic
checklist, the candidate SQL, the schema index (declared FK / confirmed / Phase 1
HoPF evidence already attached), and the already-parsed join edges, it scores
how well the candidate's TABLE and JOIN-PATH choices match the semantics of the
question — using only name tokens. Unlike Phase 2 it can also REWARD a candidate
that takes the right bridge/mapping table or the right table-purpose path, so
selection prefers a semantically correct query rather than merely punishing.

All signals are generic token comparisons; no database, domain, table, or place
name is hardcoded. It never raises and never marks anything fatal.

Signals:
  1. Mapping-table preference — when the question spans two geo granularities
     that need a crosswalk (zip vs tract/census, zip/tract vs county), and a
     bridge table carrying BOTH concept tokens exists: reward using the bridge,
     penalize a direct cross-granularity join that bypasses it.
  2. Wrong same-family table — sibling tables share a structural token (e.g.
     census_tracts_*) but differ by a distinguishing token; using the sibling
     whose distinguishing token is NOT in the question, while another sibling's
     IS, is penalized.
  3. Required path coverage — a bridge in must_use_tables that the SQL ignores
     while doing a direct risky join is penalized; including it is rewarded.
  4. Table-purpose scoring — infer a generic purpose from tokens (individual/
     person/contribution vs committee vs candidate vs expenditure/transfer vs
     geography); a purpose that conflicts with the question is penalized, a
     matching one is (mildly) rewarded.
  5. Join-path support — a cross-concept direct join not backed by a declared
     FK / confirmed / high-confidence HoPF link / same-named key / bridge is
     penalized (small; complements Phase 2).
"""

import re

try:  # reuse Phase 2 helpers + Phase 1 confidence (all already present here)
    from sql_candidates.semantic_relationship_verifier import (
        _rel_supported, _tables_used, _checklist_text,
    )
except Exception:  # pragma: no cover
    def _rel_supported(idx, t1, c1, t2, c2):
        return False

    def _tables_used(sql, idx):
        low = " " + sql.lower() + " "
        return {t for t in idx["tables"]
                if re.search(r"(?<![a-z0-9_])" + re.escape(t) + r"(?![a-z0-9_])", low)}

    def _checklist_text(checklist):
        return " ".join(str((checklist or {}).get(k) or "") for k in
                        ("target_entity", "must_use_tables", "must_use_columns",
                         "row_grain", "universe", "comparison_logic"))

__all__ = ["discover_semantic_join_issues",
           "BRIDGE_USED_BONUS", "DIRECT_CROSS_PENALTY", "MISSING_BRIDGE_PENALTY",
           "WRONG_FAMILY_PENALTY", "PURPOSE_MISMATCH_PENALTY",
           "PURPOSE_MATCH_BONUS", "UNSUPPORTED_JOIN_PENALTY"]

BRIDGE_USED_BONUS = 6.0
PURPOSE_MATCH_BONUS = 4.0
DIRECT_CROSS_PENALTY = -8.0
MISSING_BRIDGE_PENALTY = -6.0
WRONG_FAMILY_PENALTY = -6.0
PURPOSE_MISMATCH_PENALTY = -8.0
UNSUPPORTED_JOIN_PENALTY = -5.0
_DELTA_LO, _DELTA_HI = -24.0, 8.0

_NAME_RE = re.compile(r"[a-z0-9]+")

# geo granularity concepts (order = specific -> generic)
_GEO = {
    "zip":    {"zip", "zipcode", "zcta", "postal", "postcode", "zip5", "zips"},
    "tract":  {"tract", "tracts", "census", "geoid", "geo", "geography",
               "blockgroup", "cbg", "fips", "bg"},
    "county": {"county", "counties", "borough", "parish"},
    "state":  {"state", "states", "province"},
}
# concept pairs that generally require a crosswalk/mapping table
_BRIDGEABLE = {frozenset({"zip", "tract"}), frozenset({"zip", "county"}),
               frozenset({"tract", "county"})}
_BRIDGE_NAME_TOKENS = {"map", "mapping", "bridge", "crosswalk", "xref",
                       "lookup", "link", "xwalk", "cw"}

# generic table-purpose families
_PURPOSE = {
    "individual":  {"individual", "individuals", "person", "people", "donor",
                    "donors", "contributor", "contributors", "contribution",
                    "contributions", "indiv"},
    "committee":   {"committee", "committees", "pac", "cmte"},
    "candidate":   {"candidate", "candidates", "cand"},
    "expenditure": {"expenditure", "expenditures", "operating", "disbursement",
                    "disbursements", "transfer", "transfers", "spending",
                    "expense", "expenses", "payment", "payments", "outlay"},
    "geography":   set().union(*_GEO.values()),
}
# purposes that must NOT be substituted for each other
_PURPOSE_CONFLICTS = {"individual": {"expenditure", "committee"}}


def _ctoks(text):
    return set(_NAME_RE.findall(str(text or "").lower()))


def _big_toks(text):
    return {t for t in _NAME_RE.findall(str(text or "").lower()) if len(t) >= 4}


def _table_all_tokens(idx, table):
    toks = _ctoks(table)
    for col in idx["tables"].get(table, []):
        toks |= _ctoks(col.get("name"))
    return toks


def _concepts_of(tokens, families):
    return {fam for fam, keys in families.items() if tokens & keys}


def _col_geo_concept(col):
    ct = _ctoks(col)
    for fam in ("zip", "tract", "county", "state"):
        if ct & _GEO[fam]:
            return fam
    return None


def _is_bridge_table(idx, table, a, b):
    toks = _table_all_tokens(idx, table)
    has_pair = bool(toks & _GEO[a]) and bool(toks & _GEO[b])
    named = bool(_ctoks(table) & _BRIDGE_NAME_TOKENS)
    return has_pair or (named and (bool(toks & _GEO[a]) or bool(toks & _GEO[b])))


def discover_semantic_join_issues(question, checklist, sql, idx, sql_edges=None):
    """Return (delta, reasons, checks). Advisory: delta may be negative
    (penalty) or mildly positive (reward). Never fatal, never raises."""
    delta, reasons, checks = 0.0, [], {}
    try:
        if not sql or not idx or not idx.get("tables"):
            return 0.0, reasons, checks
        edges = sql_edges or []
        used = _tables_used(sql, idx)
        qtext = (question or "") + " " + _checklist_text(checklist)
        qtoks = _ctoks(qtext)
        qbig = _big_toks(qtext)
        must = {str(t).lower() for t in ((checklist or {}).get("must_use_tables")
                                         or []) if str(t).lower() in idx["tables"]}

        # -- (1)+(3)+(5-geo) mapping/bridge preference ------------------------
        qgeo = _concepts_of(qtoks, _GEO)
        for pair in _BRIDGEABLE:
            a, b = tuple(pair)
            if not (a in qgeo and b in qgeo):
                continue
            bridges = [t for t in idx["tables"]
                       if _is_bridge_table(idx, t, a, b)]
            if not bridges:
                continue
            used_bridge = [t for t in bridges if t in used]
            direct = any(
                {_col_geo_concept(c1), _col_geo_concept(c2)} == {a, b}
                for (_t1, c1, _t2, c2) in edges)
            if not direct:
                # also catch substr()/expression cross-granularity hacks
                low = sql.lower()
                if re.search(r"(zip\w*|postal\w*|zcta\w*)\s*=\s*substr", low) or \
                   re.search(r"substr\([^)]*(geoid|geo_id|tract|census|fips)", low):
                    direct = True
            if used_bridge:
                delta += BRIDGE_USED_BONUS
                reasons.append(f"uses semantic bridge/mapping table "
                               f"'{used_bridge[0]}' for {a}<->{b}")
                checks["bridge_used"] = used_bridge[0]
            elif direct:
                delta += DIRECT_CROSS_PENALTY
                reasons.append(
                    f"direct {a}<->{b} join bypasses available mapping "
                    f"table(s) {sorted(bridges)}")
                checks["direct_cross_join"] = {"pair": [a, b],
                                               "bridges": sorted(bridges)}
            elif must & set(bridges) and not used_bridge:
                delta += MISSING_BRIDGE_PENALTY
                reasons.append("SQL ignores the required bridge table "
                               f"{sorted(must & set(bridges))}")
                checks["missing_bridge"] = sorted(must & set(bridges))

        # -- (2) wrong same-family table (sibling token mismatch) -------------
        tok_tables = {}
        for t in idx["tables"]:
            for tok in _big_toks(t):
                tok_tables.setdefault(tok, set()).add(t)
        family_tokens = {tok for tok, ts in tok_tables.items() if len(ts) >= 2}
        for u in used:
            u_toks = _big_toks(u)
            u_family = u_toks & family_tokens
            if not u_family:
                continue
            u_distinct = u_toks - family_tokens
            if u_distinct & qtoks:
                continue                         # this sibling matches the question
            siblings = set()
            for tok in u_family:
                siblings |= tok_tables[tok]
            better = [v for v in siblings if v != u
                      and (_big_toks(v) - family_tokens) & qtoks]
            if better:
                delta += WRONG_FAMILY_PENALTY
                reasons.append(
                    f"'{u}' is the wrong member of the '{sorted(u_family)[0]}' "
                    f"table family; '{sorted(better)[0]}' matches the question")
                checks["wrong_family_table"] = {"used": u,
                                                 "better": sorted(better)}
                break

        # -- (4) table-purpose scoring ----------------------------------------
        qpurpose = _concepts_of(qtoks, _PURPOSE) - {"geography"}
        if qpurpose:
            for u in used:
                tp = _concepts_of(_table_all_tokens(idx, u), _PURPOSE) - {"geography"}
                if not tp:
                    continue
                conflict = any(c in tp for p in qpurpose
                               for c in _PURPOSE_CONFLICTS.get(p, set()))
                if conflict and not (tp & qpurpose):
                    delta += PURPOSE_MISMATCH_PENALTY
                    reasons.append(
                        f"question asks about {sorted(qpurpose)} but '{u}' is a "
                        f"{sorted(tp)} table")
                    checks["purpose_mismatch"] = {"table": u,
                                                  "question": sorted(qpurpose),
                                                  "table_purpose": sorted(tp)}
                    break
            else:
                if any(_concepts_of(_table_all_tokens(idx, u), _PURPOSE) & qpurpose
                       for u in used):
                    delta += PURPOSE_MATCH_BONUS
                    checks["purpose_match"] = True

        # -- (5) unsupported cross-concept direct join ------------------------
        bad = []
        for (t1, c1, t2, c2) in edges:
            if t1 == t2:
                continue
            g1, g2 = _col_geo_concept(c1), _col_geo_concept(c2)
            if not (g1 and g2 and g1 != g2):
                continue                          # only cross-concept geo joins
            if c1 == c2 or _rel_supported(idx, t1, c1, t2, c2):
                continue
            bad.append(f"{t1}.{c1} = {t2}.{c2}")
        if bad:
            delta += UNSUPPORTED_JOIN_PENALTY
            reasons.append("cross-granularity join without a trusted "
                           f"relationship/bridge: {bad[0]}")
            checks["unsupported_cross_join"] = bad

        delta = max(_DELTA_LO, min(_DELTA_HI, round(delta, 1)))
        checks["delta"] = delta
        return delta, reasons, checks
    except Exception as exc:  # advisory: never break scoring
        return 0.0, reasons, {"error": f"{type(exc).__name__}: {exc}"}
