"""Phase 2 tests — semantic relationship / table-choice verifier (advisory)."""

from sql_candidates.semantic_relationship_verifier import (
    verify_semantic_relationships,
    BAD_JOIN_PENALTY,
)


def _col(name, key=False, dtype="INTEGER"):
    return {"name": name, "type": dtype, "samples": [],
            "is_date": False, "is_numeric": dtype == "INTEGER", "is_key": key}


# schema: a postal table and a census-tract table, same-shaped integer keys.
def _idx(relationships=None):
    return {
        "tables": {
            "zip_codes": [_col("zip_code", key=True), _col("city", dtype="TEXT")],
            "census_tracts": [_col("tract_ce", key=True),
                              _col("population")],
            "contributions": [_col("contribution_id", key=True),
                              _col("zip_code"), _col("amount", dtype="REAL")],
        },
        "relationships": relationships or [],
    }


def test_unsupported_zip_to_tract_join_is_penalized():
    idx = _idx()
    sql = ("SELECT z.city FROM zip_codes z "
           "JOIN census_tracts t ON z.zip_code = t.tract_ce")
    edges = [("zip_codes", "zip_code", "census_tracts", "tract_ce")]
    delta, reasons, checks = verify_semantic_relationships(
        "population by city", None, sql, idx, sql_edges=edges)
    # advisory only: small penalty, exactly the (reduced) join penalty
    assert delta == BAD_JOIN_PENALTY
    assert -8.0 <= BAD_JOIN_PENALTY <= -3.0
    assert any("not supported" in r for r in reasons)
    assert checks.get("unsupported_joins")


def test_declared_fk_join_is_not_penalized():
    idx = _idx(relationships=[{
        "from_table": "contributions", "from_column": "zip_code",
        "to_table": "zip_codes", "to_column": "zip_code",
        "relationship_type": "foreign_key", "source": "declared_fk"}])
    sql = ("SELECT c.contribution_id FROM contributions c "
           "JOIN zip_codes z ON c.zip_code = z.zip_code")
    edges = [("contributions", "zip_code", "zip_codes", "zip_code")]
    delta, reasons, _ = verify_semantic_relationships(
        "contributions by zip", None, sql, idx, sql_edges=edges)
    assert delta == 0.0
    assert not any("not supported" in r for r in reasons)


def test_high_confidence_hopf_link_is_not_penalized():
    idx = _idx(relationships=[{
        "from_table": "zip_codes", "from_column": "zip_code",
        "to_table": "census_tracts", "to_column": "tract_ce",
        "source": "hopf_inferred", "confidence": 0.95}])
    sql = ("SELECT z.city FROM zip_codes z "
           "JOIN census_tracts t ON z.zip_code = t.tract_ce")
    edges = [("zip_codes", "zip_code", "census_tracts", "tract_ce")]
    delta, _, checks = verify_semantic_relationships(
        "by area", None, sql, idx, sql_edges=edges)
    assert delta == 0.0
    assert not checks.get("unsupported_joins")


def test_weak_hopf_link_does_not_approve_bad_join():
    idx = _idx(relationships=[{
        "from_table": "zip_codes", "from_column": "zip_code",
        "to_table": "census_tracts", "to_column": "tract_ce",
        "source": "hopf_inferred", "confidence": 0.55}])
    sql = ("SELECT z.city FROM zip_codes z "
           "JOIN census_tracts t ON z.zip_code = t.tract_ce")
    edges = [("zip_codes", "zip_code", "census_tracts", "tract_ce")]
    delta, _, checks = verify_semantic_relationships(
        "by area", None, sql, idx, sql_edges=edges)
    assert delta <= BAD_JOIN_PENALTY
    assert checks.get("unsupported_joins")


def test_wrong_same_shaped_table_choice_gets_warning():
    idx = _idx()
    # question is about zip codes, but SQL builds on census_tracts instead.
    sql = "SELECT COUNT(*) FROM census_tracts"
    delta, reasons, checks = verify_semantic_relationships(
        "How many contributions came from each zip_code?", None, sql, idx)
    assert delta < 0
    assert checks.get("table_choice_mismatch")


def test_dummy_sql_where_0_gt_0_gets_warning():
    idx = _idx()
    sql = "SELECT SUM(amount) FROM contributions WHERE 0 > 0"
    delta, reasons, checks = verify_semantic_relationships(
        "total contributions", None, sql, idx)
    assert delta < 0
    assert checks.get("dummy_sql") is True


def test_simple_valid_single_table_aggregate_is_unaffected():
    idx = _idx()
    sql = "SELECT city, COUNT(*) FROM zip_codes GROUP BY city"
    delta, reasons, checks = verify_semantic_relationships(
        "count of cities per zip_code area",
        {"must_use_tables": ["zip_codes"]}, sql, idx, sql_edges=[])
    assert delta == 0.0
    assert reasons == []


def test_verifier_never_raises_on_garbage():
    delta, reasons, checks = verify_semantic_relationships(
        None, None, None, None, sql_edges=None)
    assert delta == 0.0


def test_generic_select_star_fallback_loses_to_useful_join_sql():
    from sql_candidates.semantic_relationship_verifier import GENERIC_FALLBACK_PENALTY
    idx = _idx()
    checklist = {"must_use_tables": ["contributions", "zip_codes"],
                 "required_sql_shape": "group_by_having"}
    q = "How many contributions came from each zip_code?"
    star_delta, _, star_checks = verify_semantic_relationships(
        q, checklist, 'SELECT * FROM census_tracts', idx, sql_edges=[])
    assert star_checks.get("generic_fallback")
    join_sql = ("SELECT z.city, COUNT(*) FROM contributions c "
                "JOIN zip_codes z ON c.zip_code = z.zip_code GROUP BY z.city")
    join_delta, _, _ = verify_semantic_relationships(
        q, checklist, join_sql, idx,
        sql_edges=[("contributions", "zip_code", "zip_codes", "zip_code")])
    # useful-but-imperfect SQL must be penalized far LESS than the fallback
    assert join_delta > star_delta
    assert star_delta <= GENERIC_FALLBACK_PENALTY


def test_generic_fallback_is_strong_and_join_penalty_is_small():
    from sql_candidates.semantic_relationship_verifier import (
        GENERIC_FALLBACK_PENALTY, BAD_JOIN_PENALTY,
        TABLE_CHOICE_PENALTY, MISSING_TABLES_PENALTY)
    assert GENERIC_FALLBACK_PENALTY <= -12.0
    assert -8.0 <= BAD_JOIN_PENALTY <= -3.0
    assert -6.0 <= TABLE_CHOICE_PENALTY <= -3.0
    assert -5.0 <= MISSING_TABLES_PENALTY <= -2.0
