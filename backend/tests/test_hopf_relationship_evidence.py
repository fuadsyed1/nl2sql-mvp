"""Phase 1 tests — HoPF-style relationship evidence (advisory foundation).

Pure/scoring tests plus one tiny in-memory sqlite sampling test. No large
scans; declared FK always wins; weak schema-only links are never auto-used.
"""

import sqlite3
import tempfile
import os

from schema.hopf_relationship_evidence import (
    score_relationship,
    merge_relationships,
    is_measure_column,
    sample_column_stats,
    sampled_overlap,
    USABLE_CONFIDENCE,
)


def test_unique_parent_repeated_child_is_high_confidence_usable():
    r = score_relationship(
        child_table="orders", child_col="customer_id",
        parent_table="customers", parent_col="customer_id",
        child_type="INTEGER", parent_type="INTEGER",
        parent_uniqueness=1.0, value_overlap=1.0, child_repetition=0.8)
    assert r["source"] == "hopf_inferred"
    assert r["confidence"] >= USABLE_CONFIDENCE
    assert r["usable"] is True
    assert r["evidence"]["parent_uniqueness"] == 1.0


def test_measure_columns_are_rejected():
    for col in ("unit_price", "transaction_amt", "total_amount", "salary"):
        assert is_measure_column(col), col
    r = score_relationship(
        child_table="sales", child_col="unit_price",
        parent_table="products", parent_col="price",
        child_type="REAL", parent_type="REAL",
        parent_uniqueness=1.0, value_overlap=1.0, child_repetition=0.5)
    assert r["usable"] is False
    assert r["evidence"].get("rejected") == "measure_column"


def test_id_suffixed_names_are_not_measures():
    # a key named with a measure-ish stem but *_id is still a key
    assert not is_measure_column("price_id")
    assert not is_measure_column("customer_id")


def test_declared_fk_wins_over_inferred():
    declared = [{"from_table": "orders", "from_column": "customer_id",
                 "to_table": "customers", "to_column": "customer_id"}]
    inferred = [{"from_table": "orders", "from_column": "customer_id",
                 "to_table": "customers", "to_column": "customer_id",
                 "source": "hopf_inferred", "confidence": 0.99, "usable": True}]
    merged = merge_relationships(declared=declared, inferred=inferred)
    assert len(merged) == 1
    assert merged[0]["source"] == "declared_fk"
    assert merged[0]["confidence"] == 1.0


def test_confirmed_relationship_wins_and_usable_inferred_added():
    confirmed = [{"from_table": "a", "from_column": "b_id",
                  "to_table": "b", "to_column": "id",
                  "source": "confirmed", "confidence": 1.0}]
    inferred = [
        {"from_table": "a", "from_column": "b_id", "to_table": "b",
         "to_column": "id", "usable": True, "confidence": 0.99},   # dup -> dropped
        {"from_table": "x", "from_column": "y_id", "to_table": "y",
         "to_column": "id", "usable": True, "confidence": 0.95},   # new -> kept
        {"from_table": "p", "from_column": "q_id", "to_table": "q",
         "to_column": "id", "usable": False, "confidence": 0.5},   # weak -> dropped
    ]
    merged = merge_relationships(confirmed=confirmed, inferred=inferred)
    keys = {(e["from_table"], e["to_table"]) for e in merged}
    assert ("a", "b") in keys and ("x", "y") in keys
    assert ("p", "q") not in keys          # non-usable inferred never added


def test_weak_schema_only_link_is_not_auto_used():
    r = score_relationship(
        child_table="a", child_col="customer_id",
        parent_table="customers", parent_col="customer_id",
        child_type="INTEGER", parent_type="INTEGER", schema_only=True)
    assert r["usable"] is False
    assert r["evidence"]["schema_only"] is True


def test_non_unique_parent_is_damped_and_not_usable():
    # a "join" into a non-key parent (e.g. tract_ce = zip_code) must not qualify
    r = score_relationship(
        child_table="a", child_col="zip_code",
        parent_table="b", parent_col="tract_ce",
        child_type="INTEGER", parent_type="INTEGER",
        parent_uniqueness=0.3, value_overlap=0.9, child_repetition=0.4)
    assert r["usable"] is False


def test_sampling_helpers_are_bounded_and_readonly():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE customers (customer_id INTEGER, name TEXT);
            CREATE TABLE orders (order_id INTEGER, customer_id INTEGER);
            INSERT INTO customers VALUES (1,'a'),(2,'b'),(3,'c');
            INSERT INTO orders VALUES (10,1),(11,1),(12,2),(13,2),(14,3);
        """)
        conn.commit(); conn.close()
        pstats = sample_column_stats(path, "customers", "customer_id")
        cstats = sample_column_stats(path, "orders", "customer_id")
        assert pstats["uniqueness"] == 1.0 and pstats["schema_only"] is False
        assert cstats["repetition"] > 0.0          # children repeat -> many-to-one
        ov = sampled_overlap(path, "orders", "customer_id",
                             "customers", "customer_id")
        assert ov == 1.0
    finally:
        os.remove(path)


def test_schema_only_table_reports_schema_only_stats():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = sqlite3.connect(path)
        conn.executescript("CREATE TABLE t (id INTEGER, ref_id INTEGER);")
        conn.commit(); conn.close()
        st = sample_column_stats(path, "t", "id")
        assert st["schema_only"] is True and st["rows"] == 0
        assert sampled_overlap(path, "t", "ref_id", "t", "id") is None
    finally:
        os.remove(path)
