"""Graph-forcing / metadata-gap regressions for the live Query-1 failure."""

import os
import sqlite3
import tempfile

import pytest

import schema.named_table_forcing as M
from schema.named_table_forcing import force_named_tables, physical_tables
from schema.query_context import _explicitly_named_tables

_Q = ("Using indiv20, zipcode_to_census_tracts, census_tracts_new_york, and "
      "censustract_2018_5yr, list Kings County census tracts with the average "
      "2020 individual donation amount and 2018 median income.")
_ALL_FOUR = {"census_tracts_new_york", "censustract_2018_5yr", "indiv20",
             "zipcode_to_census_tracts"}


@pytest.fixture
def phys_db(tmp_path):
    path = os.path.join(str(tmp_path), "db38.sqlite")
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE indiv20 (zip_code INTEGER, transaction_amt INTEGER, "
        "transaction_dt TEXT);"
        "CREATE TABLE zipcode_to_census_tracts (zip_code INTEGER, tract_ce INTEGER);"
        "CREATE TABLE census_tracts_new_york (tract_ce INTEGER, tract_name TEXT);"
        "CREATE TABLE census_tracts_california (tract_ce INTEGER, tract_name TEXT);"
        "CREATE TABLE censustract_2018_5yr (tract_ce INTEGER, median_income INTEGER);")
    conn.commit()
    conn.close()
    return path


def test_exact_underscore_names_detected_despite_commas():
    all_names = list(_ALL_FOUR) + ["census_tracts_alabama"]
    found = set(_explicitly_named_tables(_Q, all_names))
    assert _ALL_FOUR <= found
    assert "census_tracts_alabama" not in found


def test_forcing_uses_full_db_list_not_only_topk(phys_db, monkeypatch):
    # metadata lists ALL physical tables; the retrieved graph has only top-k (2)
    all_meta = [{"table_name": n} for n in
                ["indiv20", "zipcode_to_census_tracts", "census_tracts_new_york",
                 "census_tracts_california", "censustract_2018_5yr"]]
    monkeypatch.setattr(M, "get_database_tables", lambda dbid: all_meta)
    graph = {"tables": [
        {"table_name": "census_tracts_new_york", "columns": [{"column_name": "tract_ce"}]},
        {"table_name": "indiv20", "columns": [{"column_name": "zip_code"}]},
    ], "relationships": []}
    g, dbg = force_named_tables(graph, _Q, 38, db_path=phys_db)
    assert _ALL_FOUR <= set(dbg["found_named"])
    assert _ALL_FOUR <= set(dbg["final_subgraph_tables"])


def test_physical_only_table_injected_when_metadata_missing(phys_db, monkeypatch):
    # metadata is MISSING the bridge + ACS tables (the real db38 bug)
    monkeypatch.setattr(M, "get_database_tables", lambda dbid: [
        {"table_name": "census_tracts_new_york"}, {"table_name": "indiv20"}])
    graph = {"tables": [
        {"table_name": "census_tracts_new_york", "columns": [{"column_name": "tract_ce"}]},
        {"table_name": "indiv20", "columns": [{"column_name": "zip_code"}]},
    ], "relationships": []}
    g, dbg = force_named_tables(graph, _Q, 38, db_path=phys_db)
    assert set(dbg["metadata_missing"]) == {"zipcode_to_census_tracts",
                                            "censustract_2018_5yr"}
    assert _ALL_FOUR <= set(dbg["final_subgraph_tables"])
    # the injected tables carry real columns from the physical schema
    names = {t["table_name"] for t in g["tables"]}
    assert _ALL_FOUR <= names


def test_graph_includes_all_four_before_checklist(phys_db, monkeypatch):
    monkeypatch.setattr(M, "get_database_tables", lambda dbid: [
        {"table_name": "census_tracts_new_york"}, {"table_name": "indiv20"}])
    graph = {"tables": [
        {"table_name": "census_tracts_new_york", "columns": [{"column_name": "tract_ce"},
                                                             {"column_name": "tract_name"}]},
        {"table_name": "indiv20", "columns": [{"column_name": "zip_code"}]},
    ], "relationships": []}
    g, dbg = force_named_tables(graph, _Q, 38, db_path=phys_db)
    graph_tables = {t.get("table_name") for t in g["tables"]}
    assert _ALL_FOUR <= graph_tables            # what [GRAPH] would print


def test_physical_tables_reads_columns(phys_db):
    phys = physical_tables(phys_db)
    assert "zipcode_to_census_tracts" in phys
    cols = {c["column_name"] for c in phys["zipcode_to_census_tracts"]}
    assert {"zip_code", "tract_ce"} <= cols


def test_no_named_tables_no_change():
    g0 = {"tables": [{"table_name": "orders", "columns": []}], "relationships": []}
    g, dbg = force_named_tables(g0, "count all rows", 1, db_path=None)
    assert dbg["found_named"] == []
    assert dbg["final_subgraph_tables"] == ["orders"]
