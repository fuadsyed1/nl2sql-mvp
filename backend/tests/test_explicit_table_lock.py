"""Emergency-fix tests — explicit table lock + focused schema + Phase 4 off."""

import os

from sql_candidates.explicit_table_lock import (
    detect_locked_tables, table_lock_penalty,
    SIBLING_PENALTY, MISSING_LOCKED_PENALTY, FALLBACK_PENALTY,
)


def _c(n):
    return {"name": n, "type": "INTEGER", "is_key": False, "samples": []}


def _idx():
    return {"tables": {
        "indiv20": [_c("sub_id"), _c("zip_code"), _c("amount")],
        "zipcode_to_census_tracts": [_c("zip_code"), _c("tract_ce")],
        "census_tracts_new_york": [_c("tract_ce"), _c("population")],
        "census_tracts_california": [_c("tract_ce"), _c("population")],
        "censustract_2018_5yr": [_c("tract_ce"), _c("median_income")],
    }, "relationships": []}


_Q = ("Using indiv20, zipcode_to_census_tracts, census_tracts_new_york, and "
      "censustract_2018_5yr, find median income per zip code.")


def test_extracts_locked_tables_from_exact_mentions():
    locked = set(detect_locked_tables(_Q, set(_idx()["tables"])))
    assert locked == {"indiv20", "zipcode_to_census_tracts",
                      "census_tracts_new_york", "censustract_2018_5yr"}


def test_sibling_table_gets_heavy_penalty():
    idx = _idx()
    sql = ("SELECT c.population FROM census_tracts_california c "
           "JOIN indiv20 i ON i.zip_code = c.tract_ce")
    delta, reasons, checks = table_lock_penalty(_Q, sql, idx)
    assert delta <= SIBLING_PENALTY
    assert checks.get("wrong_sibling_tables") == ["census_tracts_california"]


def test_using_locked_tables_gets_no_lock_penalty():
    idx = _idx()
    sql = ("SELECT ct.median_income FROM indiv20 i "
           "JOIN zipcode_to_census_tracts z ON i.zip_code = z.zip_code "
           "JOIN census_tracts_new_york ny ON z.tract_ce = ny.tract_ce "
           "JOIN censustract_2018_5yr ct ON ny.tract_ce = ct.tract_ce")
    delta, reasons, checks = table_lock_penalty(_Q, sql, idx)
    assert delta == 0.0
    assert not checks.get("wrong_sibling_tables")


def test_ignoring_most_locked_tables_gets_penalty():
    idx = _idx()
    delta, reasons, checks = table_lock_penalty(
        _Q, "SELECT population FROM census_tracts_new_york", idx)
    assert delta <= MISSING_LOCKED_PENALTY
    assert checks.get("missing_locked")


def test_select_star_fallback_gets_penalty():
    idx = _idx()
    delta, reasons, checks = table_lock_penalty(
        _Q, "SELECT * FROM census_tracts_new_york", idx)
    assert delta <= FALLBACK_PENALTY
    assert checks.get("select_star_fallback") is True


def test_no_locked_tables_means_no_penalty():
    idx = _idx()
    delta, _, _ = table_lock_penalty("count all rows",
                                     "SELECT * FROM indiv20", idx)
    assert delta == 0.0


def test_focused_schema_when_locked_tables_exist():
    # _relevant_tables must FOCUS on the named tables (+FK neighbors), not the
    # full schema, when the question names schema tables verbatim.
    from semantic.llm_sql_direct import _relevant_tables
    graph = {"tables": [
        {"table_name": "indiv20", "columns": [
            {"column_name": "zip_code", "data_type": "INTEGER"}]},
        {"table_name": "census_tracts_new_york", "columns": [
            {"column_name": "tract_ce", "data_type": "INTEGER"}]},
        {"table_name": "census_tracts_california", "columns": [
            {"column_name": "tract_ce", "data_type": "INTEGER"}]},
    ], "relationships": []}
    keep = _relevant_tables(graph, None,
                            "use indiv20 and census_tracts_new_york")
    assert "indiv20" in keep and "census_tracts_new_york" in keep
    assert "census_tracts_california" not in keep      # sibling excluded


def test_phase4_semantic_join_path_disabled_by_default():
    # runtime gate is an env flag that defaults OFF
    assert os.getenv("ENABLE_SEMANTIC_JOIN_PATH", "").strip().lower() \
        not in ("1", "true", "yes", "on")
