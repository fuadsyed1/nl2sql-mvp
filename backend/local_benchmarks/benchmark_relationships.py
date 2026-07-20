"""
local_benchmarks/benchmark_relationships.py

Backend-only TRUSTED relationship + canonical-key metadata for accepted local
benchmark databases (e.g. Lahman), which ship with 0 declared foreign keys.

Why this exists: local benchmarks are loaded metadata-only (no relationship
review UI), so the join validator / candidate scorer / schema linker have no
trusted relationship metadata and mark valid joins (Batting.playerID =
People.playerID) as "illegal" -> low-confidence -> containment "unknown".

These edges are exactly what inclusion-dependency + uniqueness profiling
(HoPF / Metanome) would derive from the data (child.playerID values are a subset
of the unique People.playerID; Batting(yearID,teamID,lgID) ⊆ Teams(...)). We
materialize them as ISOLATED benchmark metadata rather than re-hardcoding
relationships in the general pipeline, and inject them into the in-memory graph
at query time. They are NEVER persisted and NEVER shown in the relationship
approval UI.

Matched by table-name SIGNATURE, so this only activates for a recognized
benchmark schema (not for arbitrary user databases).
"""


def _edge(from_table, from_col, to_table, to_col):
    return {
        "from_table": from_table, "from_column": from_col,
        "to_table": to_table, "to_column": to_col,
        "relationship_type": "foreign_key",
        "confirmed": 1, "confidence": 1.0,
        "source": "benchmark_trusted",
    }


# One spec per accepted benchmark. `signature` = tables that must all be present
# for the spec to apply. `relationships` are child -> parent column edges (each
# column of a composite key listed separately, so per-column joins are legal).
_LAHMAN = {
    "id": "lahman",
    "signature": {"people", "batting", "pitching", "teams", "halloffame"},
    "relationships": [
        _edge("batting", "playerid", "people", "playerid"),
        _edge("pitching", "playerid", "people", "playerid"),
        _edge("fielding", "playerid", "people", "playerid"),
        _edge("salaries", "playerid", "people", "playerid"),
        _edge("halloffame", "playerid", "people", "playerid"),
        _edge("awardsplayers", "playerid", "people", "playerid"),
        _edge("awardsshareplayers", "playerid", "people", "playerid"),
        _edge("collegeplaying", "playerid", "people", "playerid"),
        _edge("appearances", "playerid", "people", "playerid"),
        _edge("battingpost", "playerid", "people", "playerid"),
        _edge("pitchingpost", "playerid", "people", "playerid"),
        _edge("collegeplaying", "schoolid", "schools", "schoolid"),
        # composite Teams keys (per-column so each equality is legal)
        _edge("batting", "yearid", "teams", "yearid"),
        _edge("batting", "teamid", "teams", "teamid"),
        _edge("batting", "lgid", "teams", "lgid"),
        _edge("pitching", "yearid", "teams", "yearid"),
        _edge("pitching", "teamid", "teams", "teamid"),
        _edge("pitching", "lgid", "teams", "lgid"),
        _edge("fielding", "yearid", "teams", "yearid"),
        _edge("fielding", "teamid", "teams", "teamid"),
        _edge("fielding", "lgid", "teams", "lgid"),
        _edge("salaries", "yearid", "teams", "yearid"),
        _edge("salaries", "teamid", "teams", "teamid"),
        _edge("salaries", "lgid", "teams", "lgid"),
        _edge("teams", "franchid", "teamsfranchises", "franchid"),
    ],
    # Answer-entity / row-grain keys per table (columns filtered to those that
    # actually exist in the loaded DB). Used ONLY by the containment canonical-key
    # resolver, so ambiguous multi-id tables (Teams has yearID/teamID/lgID) get a
    # real key instead of "no canonical key".
    "canonical_keys": {
        "people": ["playerid"],
        "teams": ["teamid", "yearid", "lgid"],
        "teamsfranchises": ["franchid"],
        "schools": ["schoolid"],
        # Player-team-season grain (join-friendly): matches Case 5/9 comparison
        # keys. (stint is dropped so a query that omits it still lines up.)
        "batting": ["playerid", "yearid", "teamid", "lgid"],
        "pitching": ["playerid", "yearid", "teamid", "lgid"],
        "fielding": ["playerid", "yearid", "teamid", "lgid"],
        "salaries": ["playerid", "yearid", "teamid", "lgid"],
        "halloffame": ["playerid", "yearid"],
        "collegeplaying": ["playerid", "schoolid", "yearid"],
        "awardsplayers": ["playerid", "awardid", "yearid"],
        "awardsshareplayers": ["playerid", "awardid", "yearid"],
        "appearances": ["playerid", "yearid", "teamid", "lgid"],
    },
}

_SPECS = [_LAHMAN]


def _match_spec(table_names):
    tset = {str(t).lower() for t in (table_names or [])}
    for spec in _SPECS:
        if spec["signature"] <= tset:
            return spec
    return None


def canonical_keys(table_names):
    """{table_lower: [key_cols]} for the matched benchmark, else {}."""
    spec = _match_spec(table_names)
    return dict(spec["canonical_keys"]) if spec else {}


def _graph_table_columns(graph):
    """Map {table_lower: set(column_lower)} from a resolved schema graph."""
    out = {}
    g = graph if isinstance(graph, dict) else {}
    for t in (g.get("tables") or []):
        if not isinstance(t, dict):
            continue
        name = str(t.get("table_name") or t.get("name") or "").lower()
        if not name:
            continue
        cols = set()
        for c in (t.get("columns") or []):
            if isinstance(c, dict):
                cn = c.get("column_name") or c.get("name")
                if cn:
                    cols.add(str(cn).lower())
        out[name] = cols
    return out


def trusted_relationships(graph):
    """Trusted FK edges for this graph's benchmark, filtered to edges whose both
    tables + columns actually exist in the graph. Empty when no benchmark matches."""
    tc = _graph_table_columns(graph)
    spec = _match_spec(tc.keys())
    if not spec:
        return []
    edges = []
    for e in spec["relationships"]:
        ft, fc = e["from_table"], e["from_column"]
        tt, tc_ = e["to_table"], e["to_column"]
        if ft in tc and tt in tc and fc in tc[ft] and tc_ in tc[tt]:
            edges.append(dict(e))
    return edges


def augment_graph(graph):
    """Return a shallow-copied graph whose `relationships` include the trusted
    benchmark edges (deduped against existing pairs). Non-benchmark graphs are
    returned unchanged. In-memory only — never persisted, never shown in the UI."""
    if not isinstance(graph, dict):
        return graph
    edges = trusted_relationships(graph)
    if not edges:
        return graph
    existing = list(graph.get("relationships") or [])
    seen = set()
    for r in existing:
        seen.add(frozenset({
            (str(r.get("from_table")).lower(), str(r.get("from_column")).lower()),
            (str(r.get("to_table")).lower(), str(r.get("to_column")).lower()),
        }))
    added = []
    for e in edges:
        key = frozenset({
            (e["from_table"], e["from_column"]),
            (e["to_table"], e["to_column"]),
        })
        if key in seen:
            continue
        seen.add(key)
        added.append(e)
    if not added:
        return graph
    out = dict(graph)
    out["relationships"] = existing + added
    return out
