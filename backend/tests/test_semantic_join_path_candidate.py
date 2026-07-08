"""Phase 4 tests — semantic_join_path candidate (deterministic planner)."""

from sql_candidates.semantic_join_path_candidate import plan_semantic_join_path
from sql_candidates.candidate_types import SqlCandidate, SOURCES
from sql_candidates.candidate_selector import select_best, _SOURCE_PRIORITY


def _c(n, key=False, dtype="INTEGER"):
    return {"name": n, "type": dtype, "is_key": key, "samples": []}


def _idx():
    return {"tables": {
        "individual_contributions": [_c("contribution_id", True), _c("zip_code"),
                                     _c("amount", dtype="REAL")],
        "zipcode_to_census_tracts": [_c("zip_code"), _c("tract_ce")],
        "census_tracts_new_york": [_c("tract_ce", True), _c("population")],
        "census_tracts_california": [_c("tract_ce", True), _c("population")],
    }, "relationships": []}


def test_finds_bridge_table_with_zip_and_tract_columns():
    plan = plan_semantic_join_path(
        "population per census tract for each zip code in new york", None, _idx())
    assert plan is not None
    assert "zipcode_to_census_tracts" in plan["tables"]


def test_builds_source_bridge_target_path_with_safe_edges():
    plan = plan_semantic_join_path(
        "population per census tract for each zip code in new york", None, _idx())
    assert plan["tables"] == ["individual_contributions",
                              "zipcode_to_census_tracts", "census_tracts_new_york"]
    # every join edge is a same-named key (safe), not a raw zip=tract guess
    for (t1, c1, t2, c2) in plan["join_edges"]:
        assert c1 == c2
    assert any("direct" in f for f in plan["forbidden"])


def test_returns_none_when_no_safe_bridge_exists():
    idx = {"tables": {
        "zip_codes": [_c("zip_code", True), _c("city", dtype="TEXT")],
        "census_tracts_new_york": [_c("tract_ce", True), _c("population")],
    }, "relationships": []}
    assert plan_semantic_join_path(
        "population per census tract for each zip code", None, idx) is None


def test_does_not_choose_wrong_same_family_geography_table():
    plan = plan_semantic_join_path(
        "population per census tract for each zip code in new york", None, _idx())
    assert plan["tables"][2] == "census_tracts_new_york"
    # with no state token, the ambiguous same-family target is refused
    assert plan_semantic_join_path(
        "population per census tract for each zip code", None, _idx()) is None


def test_source_registers_and_selector_accepts_it():
    assert "semantic_join_path" in SOURCES
    assert "semantic_join_path" in _SOURCE_PRIORITY
    good = SqlCandidate(source="semantic_join_path", label="semantic_join_path",
                        sql="SELECT 1",
                        execution={"executed": True, "columns": ["x"],
                                   "rows": [[1]], "row_count": 1})
    good.score = 80.0
    weak = SqlCandidate(source="llm_primary", label="llm_primary", sql="SELECT 2",
                        execution={"executed": True, "columns": ["x"],
                                   "rows": [[2]], "row_count": 1})
    weak.score = 60.0
    selected, meta = select_best([good, weak])
    assert selected is good
    assert meta["selected_candidate_source"] == "semantic_join_path"


def test_planner_never_raises_on_garbage():
    assert plan_semantic_join_path(None, None, None) is None
    assert plan_semantic_join_path("x", None, {"tables": {}}) is None
