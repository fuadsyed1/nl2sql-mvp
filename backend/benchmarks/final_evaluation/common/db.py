"""
final_evaluation/common/db.py

Frozen benchmark database registry + read-only reference execution.

The three evaluation databases are discovered from the repository's own
registry (app_data.db `databases` table) and pinned here by ID. Reference
SQL is ALWAYS executed read-only (file:...?mode=ro) — benchmark construction
can never modify a database.
"""

import os
import sqlite3
import time

# id -> (registry name, path relative to backend/)
BENCHMARK_DATABASES = {
    46: ("appointments", "uploads/user_4/databases/db_46/data.db"),
    49: ("Lahman Baseball", "uploads/user_4/databases/db_49/data.db"),
    50: ("AdventureWorks CTU", "uploads/user_4/databases/db_50/data.db"),
}

_BACKEND_DIR = os.environ.get("FINAL_EVAL_BACKEND_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def db_path(database_id: int) -> str:
    name, rel = BENCHMARK_DATABASES[database_id]
    return os.path.join(_BACKEND_DIR, *rel.split("/"))


def db_name(database_id: int) -> str:
    return BENCHMARK_DATABASES[database_id][0]


def execute_readonly(database_id: int, sql: str, params=None, limit=20000):
    """Execute reference SQL read-only. Returns a dict:
    {ok, columns, rows, row_count, elapsed_ms, error}."""
    path = db_path(database_id)
    started = time.time()
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
        cur = con.cursor()
        cur.execute(sql, list(params or []))
        rows = cur.fetchmany(limit + 1)
        cols = [d[0] for d in cur.description] if cur.description else []
        con.close()
        truncated = len(rows) > limit
        rows = rows[:limit]
        return {"ok": True, "columns": cols,
                "rows": [list(r) for r in rows],
                "row_count": len(rows), "truncated": truncated,
                "elapsed_ms": round((time.time() - started) * 1000, 1),
                "error": None}
    except Exception as exc:
        return {"ok": False, "columns": [], "rows": [], "row_count": 0,
                "truncated": False,
                "elapsed_ms": round((time.time() - started) * 1000, 1),
                "error": f"{type(exc).__name__}: {exc}"}
