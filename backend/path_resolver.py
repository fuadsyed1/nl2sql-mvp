"""
path_resolver.py

Phase 6, step 3 — find the best path between two tables.

Given the deterministic adjacency from schema_graph_adapter, enumerate the
simple (cycle-free) paths between a source and target table and return the
single best one by the approved ranking tuple (lower wins):

    ( hop_count,
      unconfirmed_edge_count,
      -min_edge_confidence,      # MIN aggregation; higher confidence wins
      hint_mismatch,             # 0 if every edge matches a hint, else 1
      path_signature )           # total, deterministic lexical tie-break

A path is an ordered list of edge dicts (as produced by the adapter). Returns
None when no path exists, and [] for the trivial source == target case.

Confidence only ranks paths — a low-confidence edge never blocks the only
available path. Relationship hints are advisory and rank just above the lexical
tie-break. This module reads adjacency only: it never mutates it, touches the
IR, builds a join tree, or generates SQL.
"""

__all__ = ["find_best_path"]


def _lower(value):
    return str(value).strip().lower()


def _edge_confidence(edge):
    c = edge.get("confidence")
    if isinstance(c, bool):          # bool is an int subclass; exclude it
        return 0.0
    return c if isinstance(c, (int, float)) else 0.0


def _edge_key(edge):
    """Undirected connection key for hint matching."""
    a = (_lower(edge.get("from_table", "")), _lower(edge.get("from_column", "")))
    b = (_lower(edge.get("to_table", "")), _lower(edge.get("to_column", "")))
    return frozenset((a, b))


def _hint_keys(hints):
    keys = set()
    for h in hints or []:
        if not isinstance(h, dict):
            continue
        a = (_lower(h.get("from_table", "")), _lower(h.get("from_column", "")))
        b = (_lower(h.get("to_table", "")), _lower(h.get("to_column", "")))
        keys.add(frozenset((a, b)))
    return keys


def _path_signature(path):
    return "|".join(
        f"{e.get('from_table')}.{e.get('from_column')}->"
        f"{e.get('to_table')}.{e.get('to_column')}#{e.get('relationship_id', '')}"
        for e in path
    )


def _rank_key(path, hint_keys):
    hop = len(path)
    unconfirmed = sum(1 for e in path if not e.get("confirmed"))
    min_conf = min((_edge_confidence(e) for e in path), default=1.0)
    hint_mismatch = 0 if all(_edge_key(e) in hint_keys for e in path) else 1
    return (hop, unconfirmed, -min_conf, hint_mismatch, _path_signature(path))


def _all_simple_paths(adjacency, source, target):
    """Yield every simple (no repeated table) path of edges source -> target."""
    if source == target:
        yield []
        return

    visited = {source}

    def dfs(current, path):
        for edge in adjacency.get(current, []):
            nbr = edge.get("to_table")
            if nbr in visited:
                continue
            if nbr == target:
                yield path + [edge]
                continue
            visited.add(nbr)
            yield from dfs(nbr, path + [edge])
            visited.discard(nbr)

    yield from dfs(source, [])


def find_best_path(adjacency, source, target, hints=None):
    """Return the best path (ordered list of edge dicts) from source to target,
    None if unreachable, or [] when source == target.

    adjacency is read-only and never modified.
    """
    s, t = _lower(source), _lower(target)
    if s == t:
        return []

    hint_keys = _hint_keys(hints)

    best = None
    best_key = None
    for path in _all_simple_paths(adjacency, s, t):
        key = _rank_key(path, hint_keys)
        if best_key is None or key < best_key:
            best_key = key
            best = path

    return best
