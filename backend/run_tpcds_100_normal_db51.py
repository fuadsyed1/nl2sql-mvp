#!/usr/bin/env python3
from __future__ import annotations

from spidersql_query_benchmark import run_query_cli
from spidersql_db51_catalog import (
    NORMAL_TESTS,
    DATABASE_ID,
    DATABASE_NAME,
    EXPECTED_RELATIONSHIPS,
    EXPECTED_TABLES,
)

if __name__ == "__main__":
    raise SystemExit(
        run_query_cli(
            tests=NORMAL_TESTS,
            database_id=DATABASE_ID,
            database_name=DATABASE_NAME,
            expected_tables=EXPECTED_TABLES,
            expected_relationships=EXPECTED_RELATIONSHIPS,
            suite_name='100_normal_nl',
            mode="normal",
        )
    )
