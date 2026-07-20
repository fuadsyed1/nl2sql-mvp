"""
test_local_benchmark_registry.py — offline tests for the local benchmark
registry + loader.

    python -m pytest backend/tests/test_local_benchmark_registry.py -q
"""

import sqlite3

import pytest

from local_benchmarks.benchmark_registry import list_benchmarks, get_benchmark
from local_benchmarks.benchmark_loader import load_benchmark


def _make_sqlite(path):
    c = sqlite3.connect(str(path))
    c.executescript(
        "CREATE TABLE t1(id INTEGER PRIMARY KEY, a TEXT);"
        "CREATE TABLE t2(id INTEGER);"
        "INSERT INTO t1 VALUES (1,'x');"
    )
    c.commit()
    c.close()


class _Deps:
    """Fakes for the injected pipeline functions (no auth DB needed).

    `declared` simulates the DECLARED foreign keys create_metadata reads from the
    DB itself. `received_rel` records the relationship arg the loader passed, so a
    test can prove the loader never passes an inference provider."""
    def __init__(self, declared=None):
        self.declared = declared or []
        self.received_rel = "UNSET"
        self.detect_called = False

    def create_database(self, user_id, name, conversation_id=None):
        return 42

    def set_database_path(self, database_id, path):
        pass

    def inspect_sqlite_file(self, path):
        return [{"table_name": "t1"}, {"table_name": "t2"}]

    def is_large_database(self, n):
        return False

    def create_metadata(self, database_id, db_path, name, specs, rel, large):
        self.received_rel = rel
        # create_metadata keeps DECLARED FKs regardless of `rel`; only when there
        # are none would it use `rel` (which the loader passes as []).
        return {
            "success": True, "database_id": database_id, "name": name,
            "table_count": len(specs),
            "tables": [{"table_name": s["table_name"], "success": True} for s in specs],
            "relationships": self.declared,
        }


def _load(bid, base, uploads, deps):
    return load_benchmark(
        bid, 1, None,
        create_database=deps.create_database,
        set_database_path=deps.set_database_path,
        inspect_sqlite_file=deps.inspect_sqlite_file,
        is_large_database=deps.is_large_database,
        create_metadata=deps.create_metadata,
        uploads_root=uploads, base_dir=base,
    )


def test_registry_lists_exactly_four():
    dbs = list_benchmarks()
    assert len(dbs) == 4
    assert {d["id"] for d in dbs} == {"lahman", "tpcds", "omop", "adventureworks"}
    for d in dbs:
        for k in ("display_name", "domain", "table_count", "column_count",
                  "row_count", "pk_count", "fk_count", "quality_label",
                  "sqlite_path", "available"):
            assert k in d


def test_missing_file_available_false(tmp_path):
    dbs = list_benchmarks(base_dir=str(tmp_path))
    assert all(d["available"] is False for d in dbs)


def test_available_true_when_present(tmp_path):
    _make_sqlite(tmp_path / "lahman.sqlite")
    e = get_benchmark("lahman", base_dir=str(tmp_path))
    assert e["available"] is True
    assert get_benchmark("nope", base_dir=str(tmp_path)) is None


def test_load_rejects_unknown_id(tmp_path):
    r = _load("nope", str(tmp_path), str(tmp_path / "up"), _Deps())
    assert r["success"] is False
    assert "Unknown benchmark" in r["message"]


def test_load_rejects_missing_file(tmp_path):
    r = _load("lahman", str(tmp_path), str(tmp_path / "up"), _Deps())
    assert r["success"] is False
    assert "missing" in r["message"].lower()


def test_load_success_fixture(tmp_path):
    base = tmp_path / "sqlite"
    base.mkdir()
    src = base / "lahman.sqlite"
    _make_sqlite(src)
    uploads = tmp_path / "up"

    deps = _Deps()   # no declared FKs -> Lahman/TPC-DS/OMOP case
    r = _load("lahman", str(base), str(uploads), deps)
    assert r["success"] is True
    assert r["database_id"] == 42
    assert r["name"] == "Lahman Baseball"
    assert r["table_count"] == 2
    assert r["relationship_count"] == 0
    assert r["skip_relationship_review"] is True
    assert r["source_type"] == "local_benchmark"
    # source template is NOT modified/moved
    assert src.exists()
    # file was COPIED into the per-database uploads folder
    copied = uploads / "user_1" / "databases" / "db_42" / "data.db"
    assert copied.exists()


def test_load_never_runs_autodetection(tmp_path):
    base = tmp_path / "sqlite"
    base.mkdir()
    _make_sqlite(base / "lahman.sqlite")
    deps = _Deps()
    _load("lahman", str(base), str(tmp_path / "up"), deps)
    # The loader passed an EMPTY relationship list (never an inference callable),
    # so relationship_detector is never invoked.
    assert deps.received_rel == []


def test_load_adventureworks_keeps_declared_fks_no_suggestions(tmp_path):
    base = tmp_path / "sqlite"
    base.mkdir()
    _make_sqlite(base / "adventureworks.sqlite")
    declared = [{"from_table": "SalesOrderDetail", "from_column": "SalesOrderID",
                 "to_table": "SalesOrderHeader", "to_column": "SalesOrderID"}]
    deps = _Deps(declared=declared)
    r = _load("adventureworks", str(base), str(tmp_path / "up"), deps)
    assert r["success"] is True
    assert r["skip_relationship_review"] is True
    # declared FKs are kept, but no inference provider was passed
    assert deps.received_rel == []
    assert r["relationship_count"] == 1
    assert r["relationships"] == declared
