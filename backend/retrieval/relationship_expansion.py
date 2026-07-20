"""
retrieval/relationship_expansion.py

Relationship-aware retrieval closure + physical-FK graph augmentation.

Large-mode retrieval (retrieval/table_retriever) is purely lexical: it returns
only the tables whose NAMES/columns match the question. So a question like
"customers who spent > 100000 across 3 categories" retrieves [Customer, Product]
and never the SalesOrderHeader / SalesOrderDetail / ProductSubcategory bridge or
the PurchaseOrderHeader measure table — the join/measure path is simply absent
from the graph, and every downstream layer is then stuck.

This module closes that gap using the database's REAL foreign keys (read via
`PRAGMA foreign_key_list`, no hardcoding):

  * `physical_fk_edges(db_path)` — declared FK edges from the SQLite file.
  * `augment_graph_with_physical_fks(graph, db_path)` — inject those edges into
    the in-memory graph's `relationships` (deduped) so the join validator /
    scorer / schema-linker treat the real join path as legal. In-memory only.
  * `expand_tables_along_fks(seeds, edges, all_names, question, ...)` — grow the
    retrieved seed set along FK edges to include (a) BRIDGE tables on the join
    path between seeds and (b) FK-neighbors that the question lexically points
    at (the measure/history/lookup tables), capped so the graph stays focused.
"""

import re
import sqlite3
from collections import deque

__all__ = [
    "physical_fk_edges",
    "augment_graph_with_physical_fks",
    "expand_tables_along_fks",
    "fk_adjacency",
]

_TOK = re.compile(r"[a-z0-9]+")
# Split CamelCase / flat table names into sub-words so "ProductCategory" ->
# ["product", "category"] and a question token "categories" can match.
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


# ---------------------------------------------------------------------------
# physical FK reading
# ---------------------------------------------------------------------------
def physical_fk_edges(db_path):
    """List of declared FK edges [{from_table, from_column, to_table,
    to_column, relationship_type, confirmed, confidence, source}]. Empty on any
    problem. Read-only."""
    if not db_path:
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=4.0)
    except sqlite3.Error:
        return []
    edges = []
    try:
        tabs = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")]
        for t in tabs:
            try:
                for fk in conn.execute(f'PRAGMA foreign_key_list("{t}")'):
                    parent, from_col, to_col = fk[2], fk[3], fk[4]
                    if not parent or not from_col:
                        continue
                    edges.append({
                        "from_table": t, "from_column": from_col,
                        "to_table": parent, "to_column": to_col,
                        "relationship_type": "foreign_key",
                        "confirmed": 1, "confidence": 1.0,
                        "source": "physical_fk",
                    })
            except sqlite3.Error:
                continue
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    return edges


def augment_graph_with_physical_fks(graph, db_path, edges=None):
    """Return a shallow-copied graph whose `relationships` also include the
    physical FK edges (filtered to tables present in the graph, deduped).
    Non-dict graphs / no edges -> returned unchanged. In-memory only."""
    if not isinstance(graph, dict):
        return graph
    if edges is None:
        edges = physical_fk_edges(db_path)
    if not edges:
        return graph
    present = {str(t.get("table_name") or t.get("name") or "").lower()
               for t in (graph.get("tables") or []) if isinstance(t, dict)}
    existing = list(graph.get("relationships") or [])
    seen = set()
    for r in existing:
        seen.add(frozenset({
            (str(r.get("from_table")).lower(), str(r.get("from_column")).lower()),
            (str(r.get("to_table")).lower(), str(r.get("to_column")).lower()),
        }))
    added = []
    for e in edges:
        ft, tt = e["from_table"].lower(), e["to_table"].lower()
        if present and (ft not in present or tt not in present):
            continue
        key = frozenset({(ft, e["from_column"].lower()),
                         (tt, e["to_column"].lower())})
        if key in seen:
            continue
        seen.add(key)
        added.append(dict(e))
    if not added:
        return graph
    out = dict(graph)
    out["relationships"] = existing + added
    return out


# ---------------------------------------------------------------------------
# FK-closure table expansion
# ---------------------------------------------------------------------------
def fk_adjacency(edges):
    """Undirected {table_lower: set(neighbor_lower)} from FK edges."""
    adj = {}
    for e in edges or []:
        a = str(e.get("from_table") or "").lower()
        b = str(e.get("to_table") or "").lower()
        if not a or not b or a == b:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def _bfs_dist(adj, sources, cap=3):
    """Min hop distance from any source, up to cap."""
    dist = {s: 0 for s in sources}
    dq = deque(sources)
    while dq:
        u = dq.popleft()
        if dist[u] >= cap:
            continue
        for v in adj.get(u, ()):
            if v not in dist:
                dist[v] = dist[u] + 1
                dq.append(v)
    return dist


def _shortest_path(adj, a, b, max_len=5):
    """One shortest path (list of tables incl. endpoints) from a to b, or []."""
    if a == b:
        return [a]
    prev = {a: None}
    dq = deque([a])
    while dq:
        u = dq.popleft()
        for v in adj.get(u, ()):
            if v not in prev:
                prev[v] = u
                if v == b:
                    path = [v]
                    while prev[path[-1]] is not None:
                        path.append(prev[path[-1]])
                    path.reverse()
                    return path if len(path) <= max_len else []
                dq.append(v)
    return []


def _stem(tok):
    """Very light singular stem so 'categories' matches 'category', 'orders'
    matches 'order'."""
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 4 and tok.endswith("es"):
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s"):
        return tok[:-1]
    return tok


def _question_stems(question):
    return {_stem(t) for t in _TOK.findall((question or "").lower()) if len(t) >= 3}


def _name_words(name):
    """CamelCase / flat table name -> lowercase sub-words."""
    ws = [w.lower() for w in _CAMEL.findall(str(name or ""))]
    return ws or [str(name or "").lower()]


def _rel(name, qstems):
    """Stemmed sub-word overlap between a (real-cased) table name and the
    question's new concept tokens."""
    toks = {_stem(w) for w in _name_words(name)}
    return len(toks & qstems)


def expand_tables_along_fks(seeds, edges, all_names, question="",
                            max_add=12, max_dist=3):
    """Return an ordered real-cased table list: the seeds plus a FOCUSED FK
    closure. What gets added:

      * BRIDGE tables — on a shortest FK path between two seeds (the join path).
      * RELEVANT leaves — tables within `max_dist` whose name shares a *new*
        concept token with the question (seed tokens excluded, so a hub like
        Product does not drag in all its lookup children), PLUS the connector
        tables on the shortest path from the nearest seed to each such leaf
        (so e.g. ProductCategory also pulls in ProductSubcategory).

    Structural tables (bridges + connectors) are always kept; relevant leaves
    fill the remaining budget by relevance. This keeps the graph small while
    guaranteeing the join/measure path exists."""
    real = {}
    for n in (all_names or []):
        real.setdefault(str(n).lower(), str(n))
    for e in edges or []:
        for k in ("from_table", "to_table"):
            real.setdefault(str(e[k]).lower(), str(e[k]))

    seed_l = list(dict.fromkeys(str(s).lower() for s in seeds if s))
    if not seed_l:
        return []
    adj = fk_adjacency(edges)
    seedset = set(seed_l)

    # NEW concept tokens only: drop tokens already represented by a seed name
    # (CamelCase-aware, so a hub like Product does not drag in its lookups).
    seed_tokens = {_stem(w) for s in seeds for w in _name_words(s)}
    qstems = _question_stems(question) - seed_tokens

    # (a) bridges between seed pairs
    bridges = set()
    for i in range(len(seed_l)):
        for j in range(i + 1, len(seed_l)):
            for t in _shortest_path(adj, seed_l[i], seed_l[j], max_len=max_dist + 2):
                if t not in seedset:
                    bridges.add(t)

    # (b) relevant leaves within max_dist + their connector paths
    dist = _bfs_dist(adj, seed_l, cap=max_dist)
    connectors = set()
    leaves = []            # (rel, dist, table)
    for t, d in dist.items():
        if t in seedset or d == 0:
            continue
        rel = _rel(real.get(t, t), qstems)
        if rel <= 0:
            continue
        leaves.append((rel, d, t))
        best = None
        for s in seed_l:
            p = _shortest_path(adj, s, t, max_len=max_dist + 1)
            if p and (best is None or len(p) < len(best)):
                best = p
        for u in (best or []):
            if u not in seedset:
                connectors.add(u)

    structural = bridges | connectors            # always keep (join path)
    leaf_only = [t for (_, _, t) in sorted(leaves, key=lambda x: (-x[0], x[1], x[2]))
                 if t not in structural]

    added = []
    for t in list(structural) + leaf_only:       # structural first
        if t not in seedset and t not in added:
            added.append(t)
        if len(added) >= max_add:
            break

    ordered = list(seed_l) + added
    return [real.get(t, t) for t in dict.fromkeys(ordered)]
