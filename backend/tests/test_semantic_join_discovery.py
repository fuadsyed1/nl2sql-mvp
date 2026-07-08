"""Phase 3 tests — semantic join discovery (advisory reward/penalty)."""

from sql_candidates.semantic_join_discovery import (
    discover_semantic_join_issues,
    DIRECT_CROSS_PENALTY,
    PURPOSE_MISMATCH_PENALTY,
    WRONG_FAMILY_PENALTY,
)


def _c(name, key=False, dtype="INTEGER"):
    return {"name": name, "type": dtype, "is_key": key, "samples": []}


def _idx(relationships=None):
    return {
        "tables": {
            "individual_contributions": [_c("contribution_id", True),
                                         _c("zip_code"), _c("committee_id"),
                                         _c("amount", dtype="REAL")],
            "operating_expenditures": [_c("expenditure_id", True),
                                       _c("committee_id"),
                                       _c("amount", dtype="REAL")],
            "zipcode_to_census_tracts": [_c("zip_code"), _c("tract_ce")],
            "census_tracts_new_york": [_c("tract_ce", True), _c("population")],
            "census_tracts_california": [_c("tract_ce", True), _c("population")],
            "zip_codes": [_c("zip_code", True), _c("city", dtype="TEXT")],
            "committees": [_c("committee_id", True), _c("name", dtype="TEXT")],
        },
        "relationships": relationships or [],
    }


def test_direct_zip_tract_join_penalized_when_mapping_exists():
    idx = _idx()
    sql = ("SELECT t.population FROM zip_codes z "
           "JOIN census_tracts_new_york t ON z.zip_code = t.tract_ce")
    edges = [("zip_codes", "zip_code", "census_tracts_new_york", "tract_ce")]
    delta, reasons, checks = discover_semantic_join_issues(
        "population per census tract for each zip code", None, sql, idx, edges)
    assert delta <= DIRECT_CROSS_PENALTY
    assert checks.get("direct_cross_join")


def test_zip_tract_via_mapping_table_is_rewarded_not_penalized():
    idx = _idx()
    sql = ("SELECT t.population FROM zip_codes z "
           "JOIN zipcode_to_census_tracts mp ON z.zip_code = mp.zip_code "
           "JOIN census_tracts_new_york t ON mp.tract_ce = t.tract_ce")
    edges = [("zip_codes", "zip_code", "zipcode_to_census_tracts", "zip_code"),
             ("zipcode_to_census_tracts", "tract_ce",
              "census_tracts_new_york", "tract_ce")]
    delta, reasons, checks = discover_semantic_join_issues(
        "population per census tract for each zip code", None, sql, idx, edges)
    assert delta >= 0
    assert checks.get("bridge_used") == "zipcode_to_census_tracts"


def test_wrong_same_family_geography_table_penalized():
    idx = _idx()
    sql = "SELECT population FROM census_tracts_california"
    delta, reasons, checks = discover_semantic_join_issues(
        "population of census tracts in new york", None, sql, idx, [])
    assert delta <= WRONG_FAMILY_PENALTY
    assert checks.get("wrong_family_table")


def test_individual_question_using_expenditure_table_penalized():
    idx = _idx()
    sql = "SELECT SUM(amount) FROM operating_expenditures"
    delta, reasons, checks = discover_semantic_join_issues(
        "total individual contributions", None, sql, idx, [])
    assert delta <= PURPOSE_MISMATCH_PENALTY
    assert checks.get("purpose_mismatch")


def test_valid_fk_path_is_not_penalized():
    idx = _idx(relationships=[{
        "from_table": "individual_contributions", "from_column": "committee_id",
        "to_table": "committees", "to_column": "committee_id",
        "source": "declared_fk", "relationship_type": "foreign_key"}])
    sql = ("SELECT c.name, SUM(i.amount) FROM individual_contributions i "
           "JOIN committees c ON i.committee_id = c.committee_id "
           "GROUP BY c.name")
    edges = [("individual_contributions", "committee_id",
              "committees", "committee_id")]
    delta, reasons, checks = discover_semantic_join_issues(
        "total contributions per committee", None, sql, idx, edges)
    assert delta >= 0
    assert not checks.get("direct_cross_join")
    assert not checks.get("purpose_mismatch")


def test_select_star_fallback_gets_no_reward():
    # a generic fallback must never be rescued by Phase 3 (no positive reward)
    idx = _idx()
    delta, reasons, checks = discover_semantic_join_issues(
        "total individual contributions per census tract",
        None, "SELECT * FROM operating_expenditures", idx, [])
    assert delta <= 0


def test_simple_single_table_aggregate_unaffected():
    idx = {"tables": {"contributions": [_c("id", True), _c("zip_code"),
                                        _c("amount", dtype="REAL")]},
           "relationships": []}
    sql = "SELECT zip_code, COUNT(*) FROM contributions GROUP BY zip_code"
    delta, reasons, checks = discover_semantic_join_issues(
        "count of contributions per zip code", None, sql, idx, [])
    assert delta >= 0
    assert not checks.get("direct_cross_join")
    assert not checks.get("wrong_family_table")
    assert not checks.get("purpose_mismatch")


def test_never_raises_on_garbage():
    delta, reasons, checks = discover_semantic_join_issues(None, None, None, None)
    assert delta == 0.0
