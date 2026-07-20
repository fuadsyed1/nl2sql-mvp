"""
schema/subgraph_builder.py

Build a query-time sub-graph for a large database: the SAME shape as
get_database_graph(database_id) but limited to a small set of selected tables.
This is what gets fed into the existing IR -> plan -> SQL pipeline for large DBs,
so the pipeline never sees the full 100-200 table schema.

- Columns for the selected tables are hydrated lazily via ensure_table_columns.
- Stored relationships are included only when BOTH endpoints are selected.
- No query-time relationship inference: only finalized stored edges whose
  both endpoints are selected are included.
"""

from db.database_service import (
    get_database,
    get_database_tables,
    get_relationships,
)
from schema.lazy_loader import ensure_table_columns

__all__ = ["build_subgraph"]


def build_subgraph(database_id, selected_tables):
    """Return a graph dict (same shape as get_database_graph) restricted to
    selected_tables, or None if the database is unknown. Always returns a valid
    graph even when there are no relationships."""
    db = get_database(database_id)
    if not db:
        return None

    by_name = {t["table_name"]: t for t in get_database_tables(database_id)}

    tables = []
    seen_names = set()
    for name in selected_tables or []:
        if not name or name in seen_names or name not in by_name:
            continue
        seen_names.add(name)
        ensured = ensure_table_columns(database_id, name)  # hydrate columns
        entry = dict(by_name[name])
        entry["columns"] = ensured["columns"] if ensured else []
        tables.append(entry)

    present = {t["table_name"] for t in tables}

    # Stored relationships fully inside the selected set.
    rels = [
        r for r in get_relationships(database_id)
        if r.get("from_table") in present and r.get("to_table") in present
    ]
    # Relationship lifecycle: NO query-time relationship inference. The subgraph
    # carries only the finalized stored edges whose BOTH endpoints are selected.
    # Relationship discovery happens exclusively at setup/redetection.

    graph = dict(db)
    graph["tables"] = tables
    graph["relationships"] = rels
    return graph
