"""
local_benchmarks/benchmark_loader.py

Load one local benchmark SQLite database into the app: create a database
record, COPY the read-only benchmark file into the per-database uploads folder,
inspect its real tables, and register metadata.

Metadata-ONLY relationship policy (differs from a normal upload): benchmark
databases are large and pre-vetted, so we NEVER run relationship auto-detection
(relationship_detector) and never create suggested/inferred relationships. Only
relationships DECLARED in the SQLite file itself (real foreign keys, read by
create_metadata via PRAGMA) are kept — empty for Lahman/TPC-DS/OMOP, the 90
declared FKs for AdventureWorks. The load response sets
`skip_relationship_review=true` so the UI activates the database directly and
skips the relationship-review step.

The pipeline functions are injected (dependency injection) so this module stays
unit-testable without the auth DB, and reuses the same create_database /
create_metadata registration path (no separate execution path).
"""

import os
import shutil

from .benchmark_registry import get_benchmark


def load_benchmark(
    benchmark_id,
    user_id,
    conversation_id=None,
    *,
    create_database,
    set_database_path,
    inspect_sqlite_file,
    is_large_database,
    create_metadata,
    uploads_root="uploads",
    base_dir=None,
):
    """Register a benchmark as a database (metadata + DECLARED FKs only; no
    relationship auto-detection). Returns an upload_sqlite-shaped dict plus
    `skip_relationship_review` / `source_type` so the frontend activates the DB
    directly without the review step. Never modifies the source benchmark file."""
    entry = get_benchmark(benchmark_id, base_dir=base_dir)
    if entry is None:
        return {"success": False, "message": f"Unknown benchmark: {benchmark_id}"}
    if not entry.get("available"):
        return {"success": False,
                "message": f"Local benchmark file is missing: {entry['sqlite_filename']}"}

    db_name = entry["display_name"]
    database_id = create_database(user_id, db_name, conversation_id)

    db_dir = os.path.join(uploads_root, f"user_{user_id}", "databases",
                          f"db_{database_id}")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "data.db")
    set_database_path(database_id, db_path)

    # COPY (never move) the read-only template into the database's own file.
    shutil.copyfile(entry["sqlite_path"], db_path)

    try:
        table_specs = inspect_sqlite_file(db_path)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"Could not read SQLite database: {exc}"}
    if not table_specs:
        return {"success": False,
                "message": "No tables found in the benchmark SQLite database."}

    for spec in table_specs:
        spec["source_filename"] = db_name
        spec["file_path"] = db_path

    large = is_large_database(len(table_specs))
    # Metadata-only: pass an EMPTY relationship list. create_metadata still keeps
    # any REAL declared foreign keys it reads from the DB (AdventureWorks), but
    # with no provider it never runs inference/detection (Lahman/TPC-DS/OMOP stay
    # empty). relationship_detector is never invoked here.
    result = create_metadata(database_id, db_path, db_name, table_specs, [], large)

    rels = result.get("relationships") or []
    return {
        "success": True,
        "database_id": database_id,
        "name": db_name,
        "benchmark_id": benchmark_id,
        "source_type": "local_benchmark",
        "skip_relationship_review": True,
        "table_count": result.get("table_count", len(table_specs)),
        "relationship_count": len(rels),
        "tables": result.get("tables", []),
        "relationships": rels,
        "message": f"Loaded {db_name} ({result.get('table_count', len(table_specs))} "
                   f"tables, {len(rels)} declared relationships).",
    }
