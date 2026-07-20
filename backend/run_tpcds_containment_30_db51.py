#!/usr/bin/env python3
from __future__ import annotations

from spidersql_containment_benchmark import run_containment_cli
from spidersql_db51_catalog import (
    CONTAINMENT_CASES,
    DATABASE_ID,
    DATABASE_NAME,
    EXPECTED_RELATIONSHIPS,
    EXPECTED_TABLES,
)

if __name__ == "__main__":
    raise SystemExit(
        run_containment_cli(
            cases=CONTAINMENT_CASES,
            database_id=DATABASE_ID,
            database_name=DATABASE_NAME,
            expected_tables=EXPECTED_TABLES,
            expected_relationships=EXPECTED_RELATIONSHIPS,
            suite_name='30_containment_cases',
            
        )
    )
