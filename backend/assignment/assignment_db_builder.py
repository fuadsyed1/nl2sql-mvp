"""
assignment_db_builder.py

Mode B / Mode C - create EMPTY SQLite tables from a parsed assignment spec.

Given the spec produced by assignment_parser.extract_assignment_spec(), this
builds the relational schema with no data: one CREATE TABLE per table, zero
INSERTs. It is the schema-only counterpart to csv_to_sqlite_loader (which
always loads rows) and reuses that module's name-cleaning so assignment tables
follow the exact same lowercase identifier convention as CSV-loaded tables.

Pure and isolated: it touches only the SQLite file at db_path. It performs no
app-database registration, generates no SQL for the questions, and inserts no
sample rows. The caller (the Mode B/C endpoint) takes the returned normalized
manifest and registers schema + relationships through the existing services.
"""

import sqlite3

from schema.csv_to_sqlite_loader import clean_table_name, clean_column_name

__all__ = ["build_empty_database", "normalize_spec"]


def _quote(ident: str) -> str:
    return '"' + str(ident).replace('"', '""') + '"'


def _col_type(clean_name: str) -> str:
    """Light type choice for an empty (data-less) column. Key columns become
    INTEGER so the schema reads naturally; everything else is TEXT. Exact types
    are cosmetic in schema-only mode - no data is ever compared or stored."""
    return "INTEGER" if clean_name.endswith("id") else "TEXT"


def normalize_spec(spec: dict) -> dict:
    """Return the spec with table/column/relationship names normalized to the
    SQLite identifier convention (clean_table_name / clean_column_name), so the
    empty schema matches CSV-loaded tables. Pure: no database access.

    Duplicate tables (by normalized name) are dropped, keeping the first.
    Relationships are kept only when both endpoints resolve to a known table.
    """
    tables = []
    seen = set()
    for t in spec.get("tables") or []:
        tname = clean_table_name(t.get("name", ""))
        if not tname or tname in seen:
            continue
        seen.add(tname)
        cols = []
        col_seen = set()
        for c in t.get("columns") or []:
            cname = clean_column_name(c)
            if not cname or cname in col_seen:
                continue
            col_seen.add(cname)
            cols.append({"name": cname, "type": _col_type(cname)})
        if cols:
            tables.append({"name": tname, "columns": cols})

    known = {t["name"] for t in tables}
    rels = []
    rel_seen = set()
    for r in spec.get("relationships") or []:
        ft = clean_table_name(r.get("from_table", ""))
        tt = clean_table_name(r.get("to_table", ""))
        fc = clean_column_name(r.get("from_column", ""))
        tc = clean_column_name(r.get("to_column", ""))
        if ft not in known or tt not in known:
            continue
        key = (ft, fc, tt, tc)
        if key in rel_seen:
            continue
        rel_seen.add(key)
        rels.append({
            "from_table": ft, "from_column": fc,
            "to_table": tt, "to_column": tc,
        })

    return {
        "tables": tables,
        "relationships": rels,
        "questions": list(spec.get("questions") or []),
    }


def build_empty_database(spec: dict, db_path: str) -> dict:
    """Create empty SQLite tables from a parsed assignment spec at db_path.

    Inserts no rows. Idempotent: each target table is dropped and recreated, so
    re-importing the same assignment is safe. Returns the normalized manifest
    {tables, relationships, questions, db_path, executed: False}.
    """
    norm = normalize_spec(spec)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        for t in norm["tables"]:
            col_defs = ", ".join(
                f"{_quote(c['name'])} {c['type']}" for c in t["columns"]
            )
            cursor.execute(f"DROP TABLE IF EXISTS {_quote(t['name'])}")
            cursor.execute(f"CREATE TABLE {_quote(t['name'])} ({col_defs})")
        conn.commit()
    finally:
        conn.close()

    return {
        "db_path": db_path,
        "tables": norm["tables"],
        "relationships": norm["relationships"],
        "questions": norm["questions"],
        "executed": False,
    }
