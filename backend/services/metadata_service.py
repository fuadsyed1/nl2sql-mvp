"""
services/metadata_service.py

Shared, code-only metadata builder for every database creation/import path
(CSV upload, schema DDL, Spider 2.0 import). This centralizes the previously
duplicated per-endpoint logic WITHOUT changing behavior:

  * register each table (add_database_table),
  * extract + save columns (small mode) or defer them (large mode -> columns_loaded=0),
  * persist relationships (provided by the caller, since detection differs per source),
  * set the database mode (small/large),
  * return a uniform metadata summary.

No LLM, no new behavior. Relationship detection itself still lives in the
existing detectors; this function only saves whatever the caller computed (or a
callable it can run after the tables are registered, e.g. value-overlap
detection that reads the just-saved metadata).
"""

from db.database_service import (
    add_database_table,
    add_table_columns,
    clear_relationships,
    add_relationships,
)
from schema.schema_extractor import extract_table_columns
from schema.database_mode import update_database_mode, set_table_columns_loaded
from schema.key_extractor import extract_foreign_keys

__all__ = ["create_metadata"]


def create_metadata(database_id, db_path, name, table_specs, relationships,
                    large, source=None):
    """Register tables + columns, persist relationships, set mode, and return a
    metadata summary.

    table_specs: list of dicts, each:
        {table_name, source_filename, file_path, row_count, schema_text?}
      - schema_text omitted/None -> built here (table_name in large mode, or
        "table(col, col)" from extracted columns in small mode).
    relationships: a list of edge dicts, OR a callable(database_id) -> list
        (used when detection must read the just-saved metadata).
    large: bool. When True, columns are NOT eagerly extracted (columns_loaded=0).
    source: optional dict included verbatim in the result (e.g. Spider 2.0 info).
    """
    registered = []
    for spec in table_specs:
        table_name = spec["table_name"]
        source_filename = spec.get("source_filename")
        file_path = spec.get("file_path", db_path)
        row_count = spec.get("row_count", 0)
        schema_text = spec.get("schema_text")

        if large:
            if schema_text is None:
                schema_text = table_name
            table_id = add_database_table(
                database_id, table_name, source_filename, file_path,
                schema_text, row_count,
            )
            set_table_columns_loaded(table_id, False)
            columns_meta = []
        else:
            columns_meta = extract_table_columns(db_path, table_name)
            if schema_text is None:
                schema_text = (
                    f"{table_name}("
                    + ", ".join(c["column_name"] for c in columns_meta)
                    + ")"
                )
            table_id = add_database_table(
                database_id, table_name, source_filename, file_path,
                schema_text, row_count,
            )
            add_table_columns(table_id, columns_meta)

        registered.append({
            "table_id": table_id,
            "table_name": table_name,
            "source_filename": source_filename,
            "file_path": file_path,
            "schema_text": schema_text,
            "rows_inserted": row_count,
            "columns": columns_meta,
            "success": True,
        })

    # Relationships. Prefer REAL declared foreign keys read straight from the
    # database (cheap PRAGMA, confidence 1.0, confirmed). Only when the database
    # declares none do we fall back to the caller's inferred relationships
    # (value-overlap / name-based / catalog) exactly as before.
    real_fks = extract_foreign_keys(db_path)
    if real_fks:
        rels = real_fks
    else:
        rels = relationships(database_id) if callable(relationships) else (relationships or [])
    clear_relationships(database_id)
    add_relationships(database_id, rels)

    table_count = len(table_specs)
    mode = update_database_mode(
        database_id, table_count, "large" if large else "small"
    )

    result = {
        "success": True,
        "database_id": database_id,
        "name": name,
        "mode": mode,
        "table_count": table_count,
        "db_path": db_path,
        "tables": registered,
        "relationships": rels,
    }
    if source is not None:
        result["source"] = source
    return result
