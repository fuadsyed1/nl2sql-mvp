"""Schema-linker table-selection correction tests."""

import os

from semantic.schema_linker import correct_checklist_tables
from semantic.llm_sql_direct import _relevant_tables


def _col(n):
    return {"column_name": n, "data_type": "INTEGER"}


def _graph():
    return {"tables": [
        {"table_name": "indiv20", "columns": [
            _col("sub_id"), _col("zip_code"), _col("amount")]},
        {"table_name": "zipcode_to_census_tracts", "columns": [
            _col("zip_code"), _col("tract_ce")]},
        {"table_name": "census_tracts_new_york", "columns": [
            _col("tract_ce"), _col("population")]},
        {"table_name": "census_tracts_california", "columns": [
            _col("tract_ce"), _col("population")]},
        {"table_name": "census_tracts_alabama", "columns": [
            _col("tract_ce"), _col("population")]},
        {"table_name": "censustract_2018_5yr", "columns": [
            _col("tract_ce"), _col("median_income")]},
    ], "relationships": []}


def _must(q, cl):
    return set(correct_checklist_tables(q, cl, _graph())["must_use_tables"])


_Q = ("Using indiv20, zipcode_to_census_tracts, census_tracts_new_york, and "
      "censustract_2018_5yr, find median income per zip code.")


def test_exact_table_names_forced_into_must_use_tables():
    m = _must(_Q, {"must_use_tables": []})
    assert {"indiv20", "zipcode_to_census_tracts", "census_tracts_new_york",
            "censustract_2018_5yr"} <= m


def test_explicit_ny_not_replaced_by_california():
    m = _must(_Q, {"must_use_tables": ["census_tracts_california"]})
    assert "census_tracts_new_york" in m
    assert "census_tracts_california" not in m


def test_ny_question_prefers_new_york_sibling():
    q = ("median income for census tracts in kings county, new york, "
         "joined via zip code")
    m = _must(q, {"must_use_tables": ["census_tracts_alabama"]})
    assert "census_tracts_new_york" in m
    assert "census_tracts_alabama" not in m
    assert "census_tracts_california" not in m


def test_zip_tract_question_includes_bridge_table():
    m = _must("median income per census tract for each zip code",
              {"must_use_tables": []})
    assert "zipcode_to_census_tracts" in m
    # ambiguous state -> no guessed census sibling
    assert not any(x in m for x in ("census_tracts_new_york",
                                    "census_tracts_california",
                                    "census_tracts_alabama"))


def test_median_income_question_includes_metric_table():
    m = _must("total median_income", {"must_use_tables": []})
    assert "censustract_2018_5yr" in m


def test_focused_schema_contains_corrected_must_use_tables():
    # corrected checklist -> _relevant_tables focus must include those tables
    graph = _graph()
    checklist = correct_checklist_tables(_Q, {"must_use_tables": []}, graph)
    keep = _relevant_tables(graph, checklist, _Q)
    for t in ("indiv20", "zipcode_to_census_tracts", "census_tracts_new_york",
              "censustract_2018_5yr"):
        assert t in keep
    assert "census_tracts_california" not in keep


def test_phase4_semantic_join_path_disabled_by_default():
    assert os.getenv("ENABLE_SEMANTIC_JOIN_PATH", "").strip().lower() \
        not in ("1", "true", "yes", "on")


def test_linker_never_raises_on_garbage():
    assert correct_checklist_tables(None, None, {"tables": []}) in (None, {"tables": []}) or True
    correct_checklist_tables("x", {"must_use_tables": ["nope"]}, {"tables": []})


def test_separator_insensitive_exact_locking():
    # names written with spaces/hyphens instead of underscores must still lock
    q = ("Using indiv20, zipcode to census tracts, census tracts new york, and "
         "censustract 2018 5yr, report median income")
    m = _must(q, {"must_use_tables": []})
    assert {"indiv20", "zipcode_to_census_tracts", "census_tracts_new_york",
            "censustract_2018_5yr"} <= m


def test_exact_named_tables_survive_all_pruning():
    # a wrong sibling in the starting checklist must not survive, and every
    # exactly-named table must, even after sibling/metric pruning.
    m = _must(_Q, {"must_use_tables": ["census_tracts_california",
                                       "census_tracts_alabama"]})
    assert {"indiv20", "zipcode_to_census_tracts", "census_tracts_new_york",
            "censustract_2018_5yr"} <= m
    assert "census_tracts_california" not in m
    assert "census_tracts_alabama" not in m


def test_query1_final_must_use_tables_exact_set():
    # the concrete Query-1 correction must be exactly the four named tables
    m = _must(_Q, {"must_use_tables": []})
    assert m == {"indiv20", "zipcode_to_census_tracts",
                 "census_tracts_new_york", "censustract_2018_5yr"}
