"""
test_profile_local_benchmark_db.py — offline tests for the local-benchmark
profiler. Builds a tiny SQLite database and checks the counts + quality label.

    python -m pytest backend/tests/test_profile_local_benchmark_db.py -q
"""

import os
import sqlite3
import tempfile

import pytest

from scripts.profile_local_benchmark_db import (
    profile_db,
    quality_label,
    build_schema_json,
    build_relationships_json,
    build_markdown_report,
)


@pytest.fixture()
def tiny_db():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE t1(id INTEGER PRIMARY KEY, a TEXT, b INTEGER);
        CREATE TABLE t2(
            id INTEGER PRIMARY KEY,
            t1_id INTEGER,
            c TEXT,
            FOREIGN KEY (t1_id) REFERENCES t1(id)
        );
        INSERT INTO t1 VALUES (1,'x',10),(2,'y',20),(3,'z',30);
        INSERT INTO t2 VALUES (1,1,'p'),(2,1,'q');
        """
    )
    conn.commit()
    conn.close()
    yield path
    os.remove(path)


def test_profile_counts(tiny_db):
    p = profile_db(tiny_db)
    assert p["table_count"] == 2
    assert p["total_columns"] == 6           # t1: 3 + t2: 3
    assert p["total_rows"] == 5              # 3 + 2
    assert p["declared_pk_count"] == 2       # one PK column per table
    assert p["declared_fk_count"] == 1       # t2.t1_id -> t1.id
    # per-table detail
    by_name = {t["name"]: t for t in p["tables"]}
    assert by_name["t1"]["row_count"] == 3
    assert by_name["t2"]["row_count"] == 2
    assert by_name["t1"]["primary_keys"] == ["id"]
    assert by_name["t1"]["column_count"] == 3


def test_relationships_captured(tiny_db):
    p = profile_db(tiny_db)
    rels = p["relationships"]
    assert len(rels) == 1
    r = rels[0]
    assert r["from_table"] == "t2"
    assert r["to_table"] == "t1"
    assert r["from_columns"] == ["t1_id"]
    assert r["to_columns"] == ["id"]


def test_missing_db_raises():
    with pytest.raises(FileNotFoundError):
        profile_db("/nonexistent/path/to.sqlite")


@pytest.mark.parametrize("tables,cols,expected", [
    (10, 300, "reject"),   # too few tables
    (100, 300, "reject"),  # too many tables
    (30, 100, "reject"),   # too few columns
    (30, 149, "reject"),   # just below usable
    (20, 150, "usable"),   # lower boundary usable
    (80, 199, "usable"),   # upper table boundary, below strong
    (30, 200, "strong"),   # strong
    (80, 250, "strong"),   # upper boundary strong
])
def test_quality_label(tables, cols, expected):
    assert quality_label(tables, cols) == expected


def test_builders_produce_expected_shape(tiny_db):
    p = profile_db(tiny_db)
    label = quality_label(p["table_count"], p["total_columns"])
    assert label == "reject"  # tiny db is far below thresholds

    schema = build_schema_json(p, "tiny")
    assert schema["name"] == "tiny"
    assert schema["table_count"] == 2
    assert len(schema["tables"]) == 2

    rels = build_relationships_json(p, "tiny")
    assert rels["declared_fk_count"] == 1

    md = build_markdown_report(p, "tiny", label)
    assert "Quality label: REJECT" in md
    assert "| t1 |" in md
