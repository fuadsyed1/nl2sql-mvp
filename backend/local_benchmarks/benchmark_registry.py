"""
local_benchmarks/benchmark_registry.py

A small, static registry of the accepted SpiderSQL local benchmark databases.
It only DESCRIBES the databases and reports whether each SQLite file exists
locally; it never moves or modifies the files (they are read-only templates
under relational_sample_dbs/sqlite/).

The SQLite files themselves are NOT committed (gitignored) — the registry is
just metadata + a path, so a missing file is reported as available=false rather
than crashing.
"""

import os

# Metadata captured when each database was profiled + accepted.
_BENCHMARKS = [
    {
        "id": "lahman",
        "display_name": "Lahman Baseball",
        "sqlite_filename": "lahman.sqlite",
        "domain": "Baseball / sports statistics",
        "description": "Sean Lahman's baseball database: players, teams, batting, "
                       "pitching, fielding and awards since 1871.",
        "table_count": 27,
        "column_count": 374,
        "row_count": 610197,
        "pk_count": 0,
        "fk_count": 0,
        "quality_label": "STRONG",
    },
    {
        "id": "tpcds",
        "display_name": "TPC-DS",
        "sqlite_filename": "tpcds.sqlite",
        "domain": "Retail decision-support benchmark",
        "description": "TPC-DS retail data warehouse schema (store/web/catalog "
                       "sales and returns with shared dimensions), small scale factor.",
        "table_count": 24,
        "column_count": 425,
        "row_count": 277976,
        "pk_count": 0,
        "fk_count": 0,
        "quality_label": "STRONG",
    },
    {
        "id": "omop",
        "display_name": "OMOP / Eunomia",
        "sqlite_filename": "omop.sqlite",
        "domain": "Healthcare (OMOP CDM, synthetic)",
        "description": "OHDSI Eunomia (Synthea-derived) OMOP Common Data Model "
                       "sample: persons, visits, conditions, drugs, measurements, vocab.",
        "table_count": 37,
        "column_count": 395,
        "row_count": 411102,
        "pk_count": 0,
        "fk_count": 0,
        "quality_label": "STRONG",
    },
    {
        "id": "adventureworks",
        "display_name": "AdventureWorks CTU",
        "sqlite_filename": "adventureworks.sqlite",
        "domain": "Retail / manufacturing (OLTP)",
        "description": "Full AdventureWorks 2014 OLTP (bicycle manufacturer): sales, "
                       "purchasing, production, HR — with declared PK/FK constraints.",
        "table_count": 71,
        "column_count": 486,
        "row_count": 760838,
        "pk_count": 102,
        "fk_count": 90,
        "quality_label": "STRONG",
    },
]


def sqlite_dir() -> str:
    """Absolute path to relational_sample_dbs/sqlite/ (read-only templates)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "relational_sample_dbs", "sqlite")


def _entry_view(entry: dict, base_dir: str) -> dict:
    path = os.path.join(base_dir, entry["sqlite_filename"])
    view = dict(entry)
    view["sqlite_path"] = path
    view["available"] = os.path.isfile(path)
    return view


def list_benchmarks(base_dir: str | None = None) -> list:
    """All benchmark descriptors with resolved sqlite_path + `available` flag."""
    base = base_dir or sqlite_dir()
    return [_entry_view(e, base) for e in _BENCHMARKS]


def get_benchmark(benchmark_id: str, base_dir: str | None = None) -> dict | None:
    """One benchmark descriptor (with sqlite_path + available), or None."""
    base = base_dir or sqlite_dir()
    for e in _BENCHMARKS:
        if e["id"] == benchmark_id:
            return _entry_view(e, base)
    return None
