"""Regression for the LIVE Query-1 failure: the exact bad SQL must be rejected,
and explicitly-named tables must be forced into the retrieved sub-graph so the
checklist / linker / enforcement can see them."""

from schema.query_context import _explicitly_named_tables
from semantic.schema_linker import correct_checklist_tables
from sql_candidates.direct_sql_enforcement import (
    direct_sql_violations, required_tables_for,
)
from query_families.slot_extractor import index_schema


def _col(n):
    return {"column_name": n, "data_type": "INTEGER"}


def _full_graph():
    # the FULL schema (what the sub-graph must include after the fix)
    return {"tables": [
        {"table_name": "indiv20", "columns": [
            _col("sub_id"), _col("zip_code"), _col("transaction_amt"),
            _col("transaction_dt")]},
        {"table_name": "zipcode_to_census_tracts", "columns": [
            _col("zip_code"), _col("tract_ce")]},
        {"table_name": "census_tracts_new_york", "columns": [
            _col("tract_ce"), _col("tract_name")]},
        {"table_name": "census_tracts_california", "columns": [
            _col("tract_ce"), _col("tract_name")]},
        {"table_name": "censustract_2018_5yr", "columns": [
            _col("tract_ce"), _col("median_income")]},
    ], "relationships": []}


_Q = ("Using indiv20, zipcode_to_census_tracts, census_tracts_new_york, and "
      "censustract_2018_5yr, list Kings County census tracts with the average "
      "2020 individual donation amount and 2018 median income.")

# the EXACT SQL that won live and should have been rejected
_LIVE_BAD_SQL = (
    "SELECT c.tract_ce, c.tract_name FROM census_tracts_new_york c "
    "JOIN indiv20 i ON i.zip_code = c.tract_ce "
    "WHERE c.tract_name LIKE '%Kings County%' AND i.transaction_dt LIKE '2020%' "
    "GROUP BY c.tract_ce, c.tract_name HAVING AVG(i.transaction_amt) > 0"
)

_ALL_FOUR = {"indiv20", "zipcode_to_census_tracts", "census_tracts_new_york",
             "censustract_2018_5yr"}


def test_named_tables_forced_into_subgraph_selection():
    # simulate top-k retrieval that dropped the bridge + ACS tables
    all_names = [t["table_name"] for t in _full_graph()["tables"]]
    retrieved = ["census_tracts_new_york", "indiv20"]      # what the retriever kept
    forced = set(retrieved) | set(_explicitly_named_tables(_Q, all_names))
    assert _ALL_FOUR <= forced                              # all four now present
    assert "census_tracts_california" not in forced         # sibling not forced


def test_live_bad_sql_rejected_when_full_schema_visible():
    graph = _full_graph()
    checklist = correct_checklist_tables(_Q, {"must_use_tables": []}, graph)
    assert _ALL_FOUR <= set(checklist["must_use_tables"])
    # enforcement is active (question names tables) ...
    assert required_tables_for(_Q, checklist, index_schema(graph))
    v = direct_sql_violations(_LIVE_BAD_SQL, _Q, checklist, graph)
    assert v, "live bad SQL must be rejected"
    joined = " ".join(v)
    assert "zipcode_to_census_tracts" in joined
    assert "censustract_2018_5yr" in joined
    assert "directly" in joined                            # direct zip=tract join


def test_live_bad_sql_not_rejected_when_subgraph_missing_tables_reproduces_bug():
    # the ORIGINAL bug: if the sub-graph omits the bridge/ACS tables, enforcement
    # cannot require them -> this is exactly what the sub-graph fix prevents.
    partial = {"tables": [t for t in _full_graph()["tables"]
                          if t["table_name"] in ("census_tracts_new_york", "indiv20")],
               "relationships": []}
    checklist = {"must_use_tables": ["census_tracts_new_york", "indiv20"]}
    v = direct_sql_violations(_LIVE_BAD_SQL, _Q, checklist, partial)
    # with the tables absent from the graph, nothing forces them -> demonstrates
    # why forcing named tables into the sub-graph is required.
    assert v == [] or all("directly" not in r for r in v)


def test_valid_four_table_sql_allowed():
    graph = _full_graph()
    checklist = correct_checklist_tables(_Q, {"must_use_tables": []}, graph)
    good = (
        "SELECT c.tract_ce, AVG(i.transaction_amt) AS avg_donation, a.median_income "
        "FROM census_tracts_new_york c "
        "JOIN zipcode_to_census_tracts z ON z.tract_ce = c.tract_ce "
        "JOIN indiv20 i ON i.zip_code = z.zip_code "
        "JOIN censustract_2018_5yr a ON a.tract_ce = c.tract_ce "
        "WHERE c.tract_name LIKE '%Kings County%' "
        "GROUP BY c.tract_ce, a.median_income")
    assert direct_sql_violations(good, _Q, checklist, graph) == []


# --------------------------------------------------------------------------
# live-route regressions: graph building + final (post-repair) enforcement
# --------------------------------------------------------------------------
def test_forcing_helper_matches_comma_separated_underscore_names():
    # exact reason Bug 1 existed: named tables must be recoverable from the
    # comma-separated, underscore NL against the real schema names.
    all_names = [t["table_name"] for t in _full_graph()["tables"]]
    forced = set(_explicitly_named_tables(_Q, all_names))
    assert _ALL_FOUR <= forced


def test_endpoint_style_graph_forcing_adds_missing_named_tables():
    # simulate the endpoint: a retrieved graph missing the bridge/ACS tables,
    # then force the explicitly-named ones back in (name list from the full DB).
    all_names = [t["table_name"] for t in _full_graph()["tables"]]
    retrieved_tables = [t for t in _full_graph()["tables"]
                        if t["table_name"] in ("census_tracts_new_york", "indiv20")]
    present = {t["table_name"].lower() for t in retrieved_tables}
    missing = [n for n in _explicitly_named_tables(_Q, all_names)
               if n.lower() not in present]
    final_tables = {t["table_name"] for t in retrieved_tables} | set(missing)
    assert _ALL_FOUR <= final_tables            # [GRAPH] would show all four


def test_final_repair_sql_rejected_if_missing_required_tables():
    graph = _full_graph()
    checklist = correct_checklist_tables(_Q, {"must_use_tables": []}, graph)
    repair_bad = ("SELECT c.tract_ce FROM census_tracts_new_york c "
                  "JOIN indiv20 i ON i.zip_code = c.tract_ce GROUP BY c.tract_ce")
    assert direct_sql_violations(repair_bad, _Q, checklist, graph)


def test_final_repair_sql_rejected_for_direct_zip_tract_join():
    graph = _full_graph()
    checklist = correct_checklist_tables(_Q, {"must_use_tables": []}, graph)
    # includes all four tables but STILL joins zip directly to tract -> rejected
    repair_bad = (
        "SELECT c.tract_ce, a.median_income FROM census_tracts_new_york c "
        "JOIN zipcode_to_census_tracts z ON z.tract_ce = c.tract_ce "
        "JOIN indiv20 i ON i.zip_code = c.tract_ce "
        "JOIN censustract_2018_5yr a ON a.tract_ce = c.tract_ce")
    v = direct_sql_violations(repair_bad, _Q, checklist, graph)
    assert any("directly" in r for r in v)


def test_exact_live_bad_sql_cannot_be_final():
    # end-to-end style: the exact live SQL, with the full schema + corrected
    # checklist, is always a violation -> the FINAL ENFORCE gate rejects it.
    graph = _full_graph()
    checklist = correct_checklist_tables(_Q, {"must_use_tables": []}, graph)
    assert direct_sql_violations(_LIVE_BAD_SQL, _Q, checklist, graph) != []
