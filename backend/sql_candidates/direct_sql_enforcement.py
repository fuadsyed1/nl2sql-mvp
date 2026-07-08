"""
sql_candidates/direct_sql_enforcement.py

Post-generation enforcement for DIRECT-SQL candidates (Query-1 class bug).

The schema-linker now puts the right tables in must_use_tables, but the direct
LLM can still ignore them (e.g. join indiv20.zip_code = census_tracts.tract_ce
and never touch zipcode_to_census_tracts / censustract_2018_5yr). This checks a
generated SQL string against the corrected checklist and returns the list of
VIOLATIONS; the caller drops (rejects) a violating direct candidate so it can
never win. NOT a scorer change — it filters candidate generation.

Enforcement ONLY activates when the question EXPLICITLY names schema tables
(separator-insensitive), so normal / small-DB questions are unaffected.

Rules:
  * every required table (explicitly-named + must_use_tables) must appear in a
    FROM/JOIN of the SQL;
  * if a ZIP<->tract/county bridge table is required, the SQL must not join a
    ZIP/postal column DIRECTLY to a tract/census/geo id (incl. SUBSTR(geo_id));
  * (metric/ACS tables are covered by the "required table must appear" rule
    since the linker put them in must_use_tables).
"""

import re

from query_families.slot_extractor import index_schema
from sql_candidates.semantic_relationship_verifier import _tables_used
from sql_candidates.semantic_join_discovery import _GEO, _is_bridge_table
from semantic.schema_linker import _exact_named_tables

__all__ = ["direct_sql_violations", "required_tables_for"]

_ZIP_COL = r"(?:\w+\.)?\w*(?:zip|postal|zcta)\w*"
_TRACT_COL = r"(?:\w+\.)?\w*(?:tract|census|geoid|geo_id|fips)\w*"
_DIRECT_JOIN_RES = [
    re.compile(_ZIP_COL + r"\s*=\s*" + _TRACT_COL, re.I),
    re.compile(_TRACT_COL + r"\s*=\s*" + _ZIP_COL, re.I),
    re.compile(r"(?:\w+\.)?\w*(?:zip|postal|zcta)\w*\s*=\s*substr\s*\(", re.I),
    re.compile(r"substr\s*\([^)]*(?:geo_?id|geoid|tract|census|fips)", re.I),
]


def required_tables_for(question, checklist, idx):
    """The tables the SQL MUST use, or empty set when enforcement is inactive
    (i.e. the question named no schema table verbatim)."""
    names = set(idx.get("tables") or {})
    locked = _exact_named_tables(question, names)
    if not locked:
        return set()
    must = {str(t).lower() for t in (checklist or {}).get("must_use_tables") or []
            if str(t).lower() in names}
    return must | locked


def _required_bridges(idx, required):
    out = set()
    for t in required:
        if any(_is_bridge_table(idx, t, "zip", b) for b in ("tract", "county")):
            out.add(t)
    return out


def direct_sql_violations(sql, question, checklist, graph):
    """List of violation strings (empty => candidate is acceptable). Never
    raises. Inactive (returns []) unless the question explicitly named tables."""
    try:
        idx = index_schema(graph)
    except Exception:
        return []
    if not sql or not idx.get("tables"):
        return []
    required = required_tables_for(question, checklist, idx)
    if not required:
        return []                                  # enforcement inactive
    reasons = []
    used = _tables_used(sql, idx)
    missing = sorted(required - used)
    if missing:
        reasons.append("omits explicitly required table(s): " + ", ".join(missing))
    if _required_bridges(idx, required):
        low = sql.lower()
        if any(rx.search(low) for rx in _DIRECT_JOIN_RES):
            reasons.append("joins a ZIP/postal column directly to a tract/census/"
                           "geo id instead of going through the required bridge "
                           "table")
    return reasons
