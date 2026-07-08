"""Query-1 direct-SQL enforcement: required tables, bridge, metric."""

from sql_candidates.direct_sql_enforcement import direct_sql_violations
from semantic.schema_linker import correct_checklist_tables
from semantic.llm_sql_direct import _relevant_tables, _schema_blocks, _direct_prompt


def _col(n):
    return {"column_name": n, "data_type": "INTEGER"}


def _graph():
    return {"tables": [
        {"table_name": "indiv20", "columns": [
            _col("sub_id"), _col("zip_code"), _col("amount"),
            _col("donation_date")]},
        {"table_name": "zipcode_to_census_tracts", "columns": [
            _col("zip_code"), _col("tract_ce")]},
        {"table_name": "census_tracts_new_york", "columns": [
            _col("tract_ce"), _col("name")]},
        {"table_name": "census_tracts_california", "columns": [
            _col("tract_ce"), _col("name")]},
        {"table_name": "censustract_2018_5yr", "columns": [
            _col("tract_ce"), _col("median_income")]},
    ], "relationships": []}


_Q = ("Using indiv20, zipcode_to_census_tracts, census_tracts_new_york, and "
      "censustract_2018_5yr, list Kings County census tracts with the average "
      "2020 individual donation amount and 2018 median income.")

_ALL_FOUR = {"indiv20", "zipcode_to_census_tracts", "census_tracts_new_york",
             "censustract_2018_5yr"}

_GOOD = ("SELECT c.tract_ce, AVG(i.amount) AS avg_donation, a.median_income "
         "FROM census_tracts_new_york c "
         "JOIN zipcode_to_census_tracts z ON z.tract_ce = c.tract_ce "
         "JOIN indiv20 i ON i.zip_code = z.zip_code "
         "JOIN censustract_2018_5yr a ON a.tract_ce = c.tract_ce "
         "GROUP BY c.tract_ce, a.median_income")


def _checklist():
    return correct_checklist_tables(_Q, {"must_use_tables": []}, _graph())


def test_query1_focused_schema_contains_all_four_tables():
    keep = _relevant_tables(_graph(), _checklist(), _Q)
    assert _ALL_FOUR <= keep
    assert "census_tracts_california" not in keep


def test_query1_direct_prompt_contains_all_four_tables():
    keep = _relevant_tables(_graph(), _checklist(), _Q)
    tables_block, fk_block = _schema_blocks(_graph(), keep)
    prompt = _direct_prompt(_Q, tables_block, fk_block, _checklist())
    for t in _ALL_FOUR:
        assert t in prompt
    assert "must_use_tables" in prompt          # explicit requirement present


def test_candidate_missing_bridge_table_is_rejected():
    sql = ("SELECT c.tract_ce, AVG(i.amount), a.median_income "
           "FROM census_tracts_new_york c "
           "JOIN indiv20 i ON i.zip_code = c.tract_ce "
           "JOIN censustract_2018_5yr a ON a.tract_ce = c.tract_ce "
           "GROUP BY c.tract_ce")
    v = direct_sql_violations(sql, _Q, _checklist(), _graph())
    assert v
    assert any("zipcode_to_census_tracts" in r for r in v)


def test_candidate_missing_metric_table_is_rejected():
    sql = ("SELECT c.tract_ce, AVG(i.amount) FROM census_tracts_new_york c "
           "JOIN zipcode_to_census_tracts z ON z.tract_ce = c.tract_ce "
           "JOIN indiv20 i ON i.zip_code = z.zip_code GROUP BY c.tract_ce")
    v = direct_sql_violations(sql, _Q, _checklist(), _graph())
    assert v
    assert any("censustract_2018_5yr" in r for r in v)


def test_direct_zip_to_tract_join_is_rejected_when_bridge_exists():
    sql = ("SELECT c.tract_ce, AVG(i.amount), a.median_income "
           "FROM census_tracts_new_york c "
           "JOIN zipcode_to_census_tracts z ON z.tract_ce = c.tract_ce "
           "JOIN indiv20 i ON i.zip_code = c.tract_ce "
           "JOIN censustract_2018_5yr a ON a.tract_ce = c.tract_ce "
           "GROUP BY c.tract_ce")
    v = direct_sql_violations(sql, _Q, _checklist(), _graph())
    assert any("directly" in r for r in v)


def test_valid_candidate_using_all_four_tables_is_allowed():
    assert direct_sql_violations(_GOOD, _Q, _checklist(), _graph()) == []


def test_enforcement_inactive_without_explicit_table_mentions():
    # a normal question that names no schema table -> no enforcement
    q = "average donation amount per census tract"
    assert direct_sql_violations(
        "SELECT AVG(amount) FROM indiv20", q,
        {"must_use_tables": ["indiv20"]}, _graph()) == []


def test_never_raises_on_garbage():
    assert direct_sql_violations(None, None, None, {"tables": []}) == []
