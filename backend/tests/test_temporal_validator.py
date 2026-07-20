"""Final temporal patch — latest-event qualification contract + validator.

Generic members/visits/bills schema (nothing clinic-specific). Distinguishes
"whose most recent visit was completed" (select the latest visit across ALL
visits FIRST, then test it — after_extremum) from "most recent completed
visit" (filter first — before_extremum).
"""

from semantic.semantic_checklist import _clean_checklist
from semantic.semantic_contract import build_semantic_contract
from validators.grain_validator import validate_grain
from validators.temporal_validator import validate_temporal
from sql_candidates.candidate_selector import enforce_selection_safety
from sql_candidates.candidate_types import SqlCandidate

IDX = {
    "tables": {
        "members": [{"name": "member_id"}, {"name": "name"},
                    {"name": "plan"}],
        "visits": [{"name": "visit_id"}, {"name": "member_id"},
                   {"name": "visit_date"}, {"name": "outcome"}],
        "bills": [{"name": "bill_id"}, {"name": "member_id"},
                  {"name": "amount"}],
    },
    "relationships": [],
}

_T_ENTRY = {
    "event_table": "visits", "entity_key": "members.member_id",
    "order_column": "visits.visit_date", "direction": "latest",
    "qualifier_column": "visits.outcome",
    "qualifier_values": ["successful"],
    "qualifier_timing": None, "confidence": "high",
}


def _temporal_contract(**overrides):
    entry = dict(_T_ENTRY, qualifier_timing="after_extremum")
    entry.update(overrides)
    return build_semantic_contract({"temporal_requirements": [entry]}, IDX)


# 1. "whose most recent event was successful" => after_extremum ---------------
def test_whose_most_recent_was_produces_after_extremum():
    cl = _clean_checklist(
        {"temporal_requirements": [dict(_T_ENTRY)]}, IDX,
        "Find members whose most recent visit was successful.")
    t = cl["temporal_requirements"][0]
    assert t["qualifier_timing"] == "after_extremum"
    c = build_semantic_contract(cl, IDX)
    assert c is not None and c.actionable_temporal, c


# 2. "most recent successful event" => before_extremum -------------------------
def test_most_recent_qualified_produces_before_extremum():
    cl = _clean_checklist(
        {"temporal_requirements": [dict(_T_ENTRY)]}, IDX,
        "Show each member and their most recent successful visit.")
    t = cl["temporal_requirements"][0]
    assert t["qualifier_timing"] == "before_extremum"
    c = build_semantic_contract(cl, IDX)
    assert c is not None and not c.actionable_temporal


# 3. correlated MAX over ALL events followed by the qualifier passes ----------
_CORRECT_CORRELATED = (
    "SELECT m.member_id FROM members m JOIN visits v "
    "ON v.member_id = m.member_id "
    "WHERE v.outcome = 'successful' AND v.visit_date = "
    "(SELECT MAX(v2.visit_date) FROM visits v2 "
    " WHERE v2.member_id = m.member_id)")


def test_correlated_max_over_all_events_passes():
    v = validate_temporal(_temporal_contract(), _CORRECT_CORRELATED, IDX)
    assert v.fatal == [], v


# 4. the qualifier filtered before the correlated MAX fails --------------------
def test_filter_before_correlated_max_fails():
    sql = (
        "SELECT m.member_id FROM members m JOIN visits v "
        "ON v.member_id = m.member_id "
        "WHERE v.outcome = 'successful' AND v.visit_date = "
        "(SELECT MAX(v2.visit_date) FROM visits v2 "
        " WHERE v2.member_id = m.member_id AND v2.outcome = 'successful')")
    v = validate_temporal(_temporal_contract(), sql, IDX)
    assert any("temporal violation" in f for f in v.fatal), v


# 5. ROW_NUMBER over all events, qualifier tested outside, passes --------------
def test_row_number_over_all_events_passes():
    sql = (
        "WITH ranked AS (SELECT v.member_id, v.outcome, "
        "ROW_NUMBER() OVER (PARTITION BY v.member_id "
        "ORDER BY v.visit_date DESC) AS rn FROM visits v) "
        "SELECT member_id FROM ranked WHERE rn = 1 "
        "AND outcome = 'successful'")
    v = validate_temporal(_temporal_contract(), sql, IDX)
    assert v.fatal == [], v


# 6. ROW_NUMBER computed only over qualifying events fails ----------------------
def test_row_number_after_filter_fails():
    sql = (
        "WITH ranked AS (SELECT v.member_id, "
        "ROW_NUMBER() OVER (PARTITION BY v.member_id "
        "ORDER BY v.visit_date DESC) AS rn FROM visits v "
        "WHERE v.outcome = 'successful') "
        "SELECT member_id FROM ranked WHERE rn = 1")
    v = validate_temporal(_temporal_contract(), sql, IDX)
    assert any("temporal violation" in f for f in v.fatal), v


# 7. all-event MAX CTE joined back, qualifier applied after, passes -------------
def test_all_event_max_cte_passes():
    sql = (
        "WITH latest AS (SELECT member_id, MAX(visit_date) AS max_date "
        "FROM visits GROUP BY member_id) "
        "SELECT m.member_id FROM members m "
        "JOIN latest l ON l.member_id = m.member_id "
        "JOIN visits v ON v.member_id = m.member_id "
        "AND v.visit_date = l.max_date "
        "WHERE v.outcome = 'successful'")
    v = validate_temporal(_temporal_contract(), sql, IDX)
    assert v.fatal == [], v


# 8. MAX CTE built only from qualifying events fails ----------------------------
def test_max_cte_from_filtered_events_fails():
    sql = (
        "WITH latest AS (SELECT member_id, MAX(visit_date) AS max_date "
        "FROM visits WHERE outcome = 'successful' GROUP BY member_id) "
        "SELECT m.member_id FROM members m "
        "JOIN latest l ON l.member_id = m.member_id")
    v = validate_temporal(_temporal_contract(), sql, IDX)
    assert any("temporal violation" in f for f in v.fatal), v


# 9. NOT EXISTS a later event passes --------------------------------------------
def test_not_exists_later_event_passes():
    sql = (
        "SELECT m.member_id FROM members m JOIN visits v "
        "ON v.member_id = m.member_id "
        "WHERE v.outcome = 'successful' AND NOT EXISTS "
        "(SELECT 1 FROM visits later WHERE later.member_id = v.member_id "
        " AND later.visit_date > v.visit_date)")
    v = validate_temporal(_temporal_contract(), sql, IDX)
    assert v.fatal == [], v


# 10. WHERE qualifier GROUP BY entity HAVING date = MAX(date) fails --------------
def test_where_filter_having_max_fails():
    sql = (
        "SELECT m.member_id FROM members m JOIN visits v "
        "ON v.member_id = m.member_id WHERE v.outcome = 'successful' "
        "GROUP BY m.member_id HAVING v.visit_date = MAX(v.visit_date)")
    v = validate_temporal(_temporal_contract(), sql, IDX)
    assert any("temporal violation" in f for f in v.fatal), v


def _combined_contract():
    return build_semantic_contract({
        "grain_requirements": [
            {"measure_column": "bills.amount", "aggregation": "sum",
             "entity_key": "members.member_id",
             "comparison_right_kind": "aggregate_of_entity_totals",
             "measure_scope": "all_entity_rows", "confidence": "high"}],
        "temporal_requirements": [dict(_T_ENTRY,
                                       qualifier_timing="after_extremum")],
    }, IDX)


# 11. latest-event qualification + lifetime aggregation in separate CTEs pass ---
def test_separate_qualification_and_lifetime_pass():
    sql = (
        "WITH totals AS (SELECT member_id, SUM(amount) AS total FROM bills "
        "GROUP BY member_id) "
        "SELECT m.member_id FROM members m "
        "JOIN totals t ON t.member_id = m.member_id "
        "WHERE m.member_id IN (SELECT v.member_id FROM visits v "
        "  WHERE v.outcome = 'successful' AND v.visit_date = "
        "  (SELECT MAX(v2.visit_date) FROM visits v2 "
        "   WHERE v2.member_id = v.member_id)) "
        "AND t.total > (SELECT AVG(total) FROM totals)")
    c = _combined_contract()
    assert validate_temporal(c, sql, IDX).fatal == []
    assert validate_grain(c, sql, IDX).fatal == []


# 12. latest-event filter contaminating the lifetime aggregate stays fatal ------
def test_latest_filter_contaminating_lifetime_stays_fatal():
    sql = (
        "SELECT m.member_id FROM members m "
        "JOIN visits v ON v.member_id = m.member_id "
        "AND v.visit_date = (SELECT MAX(v2.visit_date) FROM visits v2 "
        "  WHERE v2.member_id = m.member_id) "
        "JOIN bills b ON b.member_id = m.member_id "
        "WHERE v.outcome = 'successful' "
        "GROUP BY m.member_id "
        "HAVING SUM(b.amount) > (SELECT AVG(t.total) FROM "
        "  (SELECT member_id, SUM(amount) AS total FROM bills "
        "   GROUP BY member_id) t)")
    c = _combined_contract()
    assert validate_temporal(c, sql, IDX).fatal == []   # extremum is clean
    g = validate_grain(c, sql, IDX)
    assert any("restricted scope" in f for f in g.fatal), g


# 13. before_extremum allows the qualifier-first shape ---------------------------
def test_before_extremum_allows_filter_first():
    c = _temporal_contract(qualifier_timing="before_extremum")
    sql = (
        "WITH latest AS (SELECT member_id, MAX(visit_date) AS max_date "
        "FROM visits WHERE outcome = 'successful' GROUP BY member_id) "
        "SELECT m.member_id FROM members m "
        "JOIN latest l ON l.member_id = m.member_id")
    v = validate_temporal(c, sql, IDX)
    assert v.fatal == [] and v.skipped is not None


# 14. ordinary MAX queries without a temporal requirement do not regress --------
def test_plain_max_queries_not_affected():
    sql = "SELECT member_id, MAX(visit_date) FROM visits GROUP BY member_id"
    v = validate_temporal(None, sql, IDX)
    assert v.fatal == [] and v.skipped is not None
    # with a temporal requirement but no qualifier filter anywhere: clean
    v = validate_temporal(_temporal_contract(), sql, IDX)
    assert v.fatal == [], v


# 15. low-confidence temporal extraction stays nonfatal --------------------------
def test_low_confidence_temporal_nonfatal():
    for conf in ("medium", "low", None):
        c = _temporal_contract(confidence=conf)
        sql = (
            "WITH latest AS (SELECT member_id, MAX(visit_date) AS md "
            "FROM visits WHERE outcome = 'successful' GROUP BY member_id) "
            "SELECT member_id FROM latest")
        v = validate_temporal(c, sql, IDX)
        assert v.fatal == [] and v.skipped is not None, (conf, v)


# 16. all candidates temporally fatal => controlled failure ----------------------
def test_all_temporal_fatal_controlled_failure():
    def _cand(label):
        c = SqlCandidate(
            source="llm_sql_direct", label=label, sql="SELECT 1",
            execution={"executed": True, "columns": ["x"], "rows": [[1]],
                       "row_count": 1, "truncated": False, "diagnostics": {}})
        c.score = 60.0
        c.validation = {"fatal": [
            "temporal violation: the qualifying condition is applied before "
            "selecting the latest event, so the SQL finds the latest "
            "qualifying event instead of checking whether the latest event "
            "qualifies"]}
        return c
    cands = [_cand("a"), _cand("b")]
    safe, controlled, reasons = enforce_selection_safety(cands[0], cands)
    assert safe is None and controlled is True
    assert any("temporal violation" in r for r in reasons)


# 17. the exact CORRECT Q13-shaped pattern (run 2) passes ------------------------
def test_run2_correct_shape_passes():
    sql = (
        "WITH lifetime AS (SELECT m.member_id, m.plan, "
        "SUM(b.amount) AS total FROM members m "
        "JOIN bills b ON b.member_id = m.member_id "
        "GROUP BY m.member_id, m.plan), "
        "avg_by_plan AS (SELECT plan, AVG(total) AS avg_total FROM lifetime "
        "GROUP BY plan), "
        "latest_ok AS (SELECT m.member_id FROM members m "
        "JOIN visits v ON v.member_id = m.member_id "
        "WHERE v.outcome = 'successful' AND v.visit_date = "
        "(SELECT MAX(v2.visit_date) FROM visits v2 "
        " WHERE v2.member_id = m.member_id)) "
        "SELECT m.member_id FROM members m "
        "JOIN lifetime lt ON lt.member_id = m.member_id "
        "JOIN avg_by_plan ap ON ap.plan = lt.plan "
        "JOIN latest_ok lo ON lo.member_id = m.member_id "
        "WHERE lt.total > ap.avg_total")
    c = _combined_contract()
    assert validate_temporal(c, sql, IDX).fatal == []
    assert validate_grain(c, sql, IDX).fatal == []


# 18. the exact WRONG Q13-shaped pattern (run 3) fails ---------------------------
def test_run3_wrong_shape_fails():
    sql = (
        "WITH lifetime AS (SELECT m.member_id, m.plan, "
        "SUM(b.amount) AS total FROM members m "
        "JOIN bills b ON b.member_id = m.member_id "
        "GROUP BY m.member_id, m.plan), "
        "avg_by_plan AS (SELECT plan, AVG(total) AS avg_total FROM lifetime "
        "GROUP BY plan), "
        "latest_ok AS (SELECT m.member_id FROM members m "
        "JOIN visits v ON v.member_id = m.member_id "
        "WHERE v.outcome = 'successful' "
        "GROUP BY m.member_id "
        "HAVING v.visit_date = MAX(v.visit_date)) "
        "SELECT m.member_id FROM members m "
        "JOIN lifetime lt ON lt.member_id = m.member_id "
        "JOIN avg_by_plan ap ON ap.plan = lt.plan "
        "JOIN latest_ok lo ON lo.member_id = m.member_id "
        "WHERE lt.total > ap.avg_total")
    v = validate_temporal(_combined_contract(), sql, IDX)
    assert any("temporal violation" in f for f in v.fatal), v
