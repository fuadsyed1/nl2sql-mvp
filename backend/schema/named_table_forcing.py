"""
schema/named_table_forcing.py

Guarantee that every table the question NAMES verbatim is present in the graph
handed to the checklist / schema-linker / enforcement — even when large-mode
top-k retrieval dropped it, AND even when it is missing from the `database_tables`
METADATA but exists physically in the SQLite file.

Why physical fallback: build_subgraph() silently drops any requested table that
is not registered in database_tables, so a physical-only table can never be
forced in through it. Here we read the physical schema (sqlite_master +
PRAGMA table_info) directly and inject a proper graph table entry.

Generic, read-only, never raises. Returns (graph, debug) so the caller can log.
"""

import sqlite3

from db.database_service import get_database_tables, get_database_path
from schema.subgraph_builder import build_subgraph
from schema.query_context import _explicitly_named_tables

__all__ = ["force_named_tables", "physical_tables"]


def physical_tables(db_path):
    """{real_table_name: [{column_name, data_type, is_primary_key_candidate}]}
    read read-only from the SQLite file. Empty on any problem."""
    out = {}
    if not db_path:
        return out
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3.0)
    except sqlite3.Error:
        return out
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'")
        for (name,) in cur.fetchall():
            try:
                cur.execute(f'PRAGMA table_info("{name}")')
                out[name] = [
                    {"column_name": r[1], "data_type": (r[2] or "TEXT"),
                     "is_primary_key_candidate": bool(r[5])}
                    for r in cur.fetchall()
                ]
            except sqlite3.Error:
                continue
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    return out


def force_named_tables(graph, question, database_id, db_path=None):
    """Return (graph, debug). `graph` is guaranteed to contain every
    explicitly-named table that exists in metadata OR the physical DB."""
    graph = graph or {"tables": [], "relationships": []}
    try:
        meta_names = [r["table_name"] for r in get_database_tables(database_id)]
    except Exception:
        meta_names = []
    if db_path is None:
        try:
            db_path = get_database_path(database_id)
        except Exception:
            db_path = None
    phys = physical_tables(db_path)

    meta_lower = {str(n).lower() for n in meta_names}
    real = {}
    for n in meta_names:
        real.setdefault(str(n).lower(), n)
    for n in phys:
        real.setdefault(str(n).lower(), n)

    all_names = list(dict.fromkeys(list(meta_names) + list(phys.keys())))
    named = _explicitly_named_tables(question, all_names)     # lowercased, in-DB

    present = {str(t.get("table_name") or "").lower()
               for t in (graph.get("tables") or [])}
    missing = [n for n in named if n not in present]

    # Inject each missing named table from the PHYSICAL schema first (works for
    # metadata-registered AND physical-only tables, and avoids a get_database
    # round-trip). Fall back to build_subgraph only for metadata tables whose
    # physical columns could not be read.
    metadata_missing = []
    need_rebuild = []
    for n in missing:
        cols = phys.get(real.get(n)) or phys.get(n)
        if cols:
            graph.setdefault("tables", []).append(
                {"table_name": real.get(n, n), "columns": cols})
            present.add(n)
            if n not in meta_lower:
                metadata_missing.append(real.get(n, n))
        elif n in meta_lower:
            need_rebuild.append(real[n])
    if need_rebuild:
        cur = [t.get("table_name") for t in (graph.get("tables") or [])
               if t.get("table_name")]
        try:
            rebuilt = build_subgraph(
                database_id, list(dict.fromkeys(cur + need_rebuild)))
            if rebuilt and rebuilt.get("tables"):
                graph = rebuilt
        except Exception as exc:
            print(f"NAMED-TABLE REBUILD ERROR: {exc}", flush=True)

    final = [t.get("table_name") for t in (graph.get("tables") or [])]
    debug = {
        "database_id": database_id,
        "all_db_tables": all_names,
        "explicit_names": sorted(named),
        "found_named": sorted(named),
        "missing_named": sorted(missing),
        "metadata_missing": sorted(metadata_missing),
        "final_subgraph_tables": final,
    }
    return graph, debug
