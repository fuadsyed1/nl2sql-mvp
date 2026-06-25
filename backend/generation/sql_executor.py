"""
sql_executor.py

Phase 8, step 2 — execute a GeneratedSQL against a SQLite database file.

execute_sql(generated_sql, db_path, *, row_limit=DEFAULT_ROW_LIMIT):
  * declines when the SQL was never generated (not_generated),
  * opens the database read-only via a file URI (mode=ro) so it can never
    write, reporting db_unavailable if the file cannot be opened,
  * binds params (never string-interpolated), runs the SQL unchanged, fetches
    row_limit + 1 rows to detect truncation, and returns columns + rows,
  * converts any SQLite error into a sql_error result rather than raising.

It receives a db_path directly: it does not know database_id, workspace folder
structure, the IR, the plan, the graph, or how the SQL was produced. It imports
only sqlite3 and the execution_result helpers.
"""

import sqlite3

from generation.execution_result import success_result, failure_result, DEFAULT_ROW_LIMIT

__all__ = ["execute_sql"]


def _get(obj, key, default=None):
    """Read a field from either a GeneratedSQL object or a plain dict."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def execute_sql(generated_sql, db_path, *, row_limit=DEFAULT_ROW_LIMIT):
    """Run a GeneratedSQL against db_path (read-only) and return an
    ExecutionResult. Never raises SQLite errors to the caller."""
    # 1) Nothing to run.
    if not _get(generated_sql, "generated", False):
        diagnostics = {"generated": False}
        gen_reason = _get(generated_sql, "reason")
        if gen_reason:
            diagnostics["generated_sql_reason"] = gen_reason
        return failure_result("not_generated", diagnostics=diagnostics)

    sql = _get(generated_sql, "sql")
    params = list(_get(generated_sql, "params") or [])

    if not sql:
        return failure_result("sql_error", error="no SQL to execute")

    # 2) Open the database read-only. A missing/unopenable file fails here.
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        return failure_result("db_unavailable", error=str(exc))

    # 3) Execute with bound params; convert any SQLite error to sql_error.
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [d[0] for d in (cursor.description or [])]

        fetched = cursor.fetchmany(row_limit + 1)
        truncated = len(fetched) > row_limit
        kept = fetched[:row_limit] if truncated else fetched
        rows = [list(r) for r in kept]

        return success_result(
            columns,
            rows,
            truncated=truncated,
            diagnostics={"param_count": len(params)},
        )
    except sqlite3.Error as exc:
        return failure_result("sql_error", error=str(exc))
    finally:
        conn.close()