"""
schema_graph_adapter.py

Phase 6, step 2 — turn the schema graph into a deterministic adjacency
structure for traversal.

Each detected relationship is made bidirectional: it yields one directed edge
under each endpoint table, oriented so `from_*` is the table that holds the
edge and `to_*` is the neighbour. Edge metadata (confirmed, confidence, and
relationship_id when present) is preserved for later ranking. Every declared
table is a node, so isolated tables appear with an empty edge list.

Pure structure. No graph search, no path ranking, no SQL, and it never touches
the IR. Its only job is to present the graph deterministically.
"""

__all__ = ["build_adjacency", "edges_for", "all_tables"]


def _lower(value):
    return str(value).strip().lower()


def _graph_root(graph):
    """Tolerate a graph wrapped under a 'database' key."""
    if isinstance(graph, dict) and isinstance(graph.get("database"), dict):
        return graph["database"]
    return graph if isinstance(graph, dict) else {}


def _make_edge(cur_table, cur_column, nbr_table, nbr_column, rel):
    """One directed edge oriented from the node holding it to its neighbour."""
    edge = {
        "from_table": cur_table,
        "from_column": cur_column,
        "to_table": nbr_table,
        "to_column": nbr_column,
        "confirmed": bool(rel.get("confirmed")),
        "confidence": rel.get("confidence"),
        "relationship_type": rel.get("relationship_type"),
    }
    rid = rel.get("relationship_id")
    if rid is not None:
        edge["relationship_id"] = rid
    return edge


def _edge_sort_key(edge):
    """Total, deterministic ordering of a node's outgoing edges."""
    return (
        edge["to_table"],
        edge["from_column"],
        edge["to_column"],
        edge.get("relationship_id", -1),
    )


def build_adjacency(graph):
    """Return {table_name: [edge, ...]} with bidirectional, sorted edges.

    Independent of the input ordering of tables/relationships: identical graph
    content always yields identical adjacency.
    """
    g = _graph_root(graph)
    adjacency = {}

    # Seed every declared table as a node (isolated tables -> empty list).
    for table in g.get("tables") or []:
        if isinstance(table, dict) and table.get("table_name") is not None:
            adjacency.setdefault(_lower(table["table_name"]), [])

    for rel in g.get("relationships") or []:
        if not isinstance(rel, dict):
            continue
        ft, fc = _lower(rel.get("from_table", "")), _lower(rel.get("from_column", ""))
        tt, tc = _lower(rel.get("to_table", "")), _lower(rel.get("to_column", ""))
        if not ft or not tt:
            continue

        adjacency.setdefault(ft, [])
        adjacency.setdefault(tt, [])

        # Bidirectional: an edge under each endpoint, oriented to that endpoint.
        adjacency[ft].append(_make_edge(ft, fc, tt, tc, rel))
        adjacency[tt].append(_make_edge(tt, tc, ft, fc, rel))

    for table in adjacency:
        adjacency[table].sort(key=_edge_sort_key)

    # Return with sorted keys so iteration order is deterministic too.
    return {key: adjacency[key] for key in sorted(adjacency)}


def edges_for(adjacency, table):
    """Outgoing edges for a table (case-insensitive); [] if absent."""
    return adjacency.get(_lower(table), [])


def all_tables(adjacency):
    """Sorted list of all node table names."""
    return sorted(adjacency.keys())