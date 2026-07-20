"""Focused structural tests for the Day 1 go-live audit tooling.
Hermetic: parsers are exercised on tiny synthetic fixtures (no benchmark data or
answers hardcoded), plus manifest-structure validation on synthetic dicts."""
import sys, importlib, json
from pathlib import Path

DAY1 = Path(__file__).resolve().parents[1] / "benchmarks" / "go_live_day1"
sys.path.insert(0, str(DAY1))
import day1_common as dc  # noqa: E402
check = importlib.import_module("check_protected_regressions")  # noqa: E402


def test_parse_result_file(tmp_path):
    p = tmp_path / "r.txt"
    p.write_text(
        "=" * 20 + "\nTEST 001\nCATEGORY: aggregation\nDIFFICULTY: easy\n"
        "STATUS: PASS\nQUERY:\nHow many rows?\nSQL:\nSELECT COUNT(*) FROM t\n"
        + "=" * 20 + "\nTEST 002\nCATEGORY: join\nDIFFICULTY: hard\n"
        "STATUS: FAIL\nQUERY:\nBad one?\nSQL:\n<NO SQL GENERATED>\n" + "=" * 20 + "\n",
        encoding="utf-8")
    recs = dc.parse_result_file(str(p))
    assert [r["test_id"] for r in recs] == [1, 2]
    assert [r["status"] for r in recs] == ["PASS", "FAIL"]
    assert recs[0]["question"] == "How many rows?"
    assert recs[0]["category"] == "aggregation"


def test_classify_fatal_layer():
    assert dc.classify_fatal_layer(["grain violation: x"]) == ("grain_contract", False)
    assert dc.classify_fatal_layer(["fanout violation: y"]) == ("grain_contract", False)
    assert dc.classify_fatal_layer(["required concept z not found"]) == \
        ("required_concept", False)
    lay, needs = dc.classify_fatal_layer(["grain violation: a", "illegal join: b"])
    assert needs is True and lay.startswith("mixed:")
    assert dc.classify_fatal_layer([]) == ("unknown", True)


def test_evaluate_designed_edge():
    def case(rel, qa=None, qb=None):
        return {"pairwise": {(1, 2): rel} if rel else {},
                "query_meta": {1: qa or {"success": True, "safe": True,
                                         "empty_result": False},
                               2: qb or {"success": True, "safe": True,
                                         "empty_result": False}}}
    assert dc.evaluate_designed_edge(case("query_a_contained_in_query_b"), 1, 2)[0] is True
    assert dc.evaluate_designed_edge(case("equivalent_on_current_database"), 1, 2)[0] is True
    ok, cause, _ = dc.evaluate_designed_edge(case("incomparable_on_current_database"), 1, 2)
    assert ok is False and cause == "incomparable"
    ok, cause, _ = dc.evaluate_designed_edge(case("query_b_contained_in_query_a"), 1, 2)
    assert ok is False and cause == "reversed_containment"
    ok, cause, _ = dc.evaluate_designed_edge(case(None), 1, 2)
    assert ok is False and cause == "missing_pairwise_entry"
    ok, cause, _ = dc.evaluate_designed_edge(
        case("unknown", qa={"success": False, "safe": True, "empty_result": False}), 1, 2)
    assert ok is False and cause == "endpoint_or_query_failure"


def test_parse_containment_file(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text(
        "CASE 001 | DB54 sales | easy | demo case\n"
        "DESIGNED LOGICAL RELATIONSHIPS\n- Q1 is logically contained in Q2.\n"
        "ENDPOINT SUCCESS: True\n"
        "RAW RESPONSE JSON\n"
        '{"query_results":[{"query_id":1,"success":true,"safe":true,'
        '"empty_result":false,"question":"q one"},{"query_id":2,"success":true,'
        '"safe":true,"empty_result":false,"question":"q two"}],'
        '"pairwise_relationships":[{"query_a":1,"query_b":2,'
        '"relationship":"query_a_contained_in_query_b"}]}\n',
        encoding="utf-8")
    cases = dc.parse_containment_file(str(p))
    assert len(cases) == 1
    c = cases[0]
    assert c["designed_edges"] == [(1, 2)]
    assert c["database_id"] == 54
    assert dc.evaluate_designed_edge(c, 1, 2)[0] is True


def test_manifest_validate_counts_and_duplicates():
    bad = {
        "schema_version": "x", "source_files": {},
        "protected_semantically_correct": {
            "by_database": {"54": {"count": 2, "test_ids": [1, 1]}}, "total": 3},
        "controlled_failures": {
            "by_database": {"54": {"count": 1, "test_ids": [9]}}, "total": 1},
        "protected_containment_recovered_edges": {
            "by_database": {"54": {"count": 1, "edges": [[1, 1, 2], [1, 1, 2]]}},
            "total": 1},
    }
    problems, _ = check.validate(bad)
    assert any("duplicate test_ids" in p for p in problems)
    assert any("protected_correct: total" in p for p in problems)
    assert any("duplicate edges" in p for p in problems)


def test_parse_semantic_audit_csv(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text(
        "test_id,category,difficulty,execution_status,semantic_audit,query,sql,audit_note\n"
        "1,aggregation,easy,PASS,CORRECT,Q one?,SELECT 1,\n"
        "2,join,hard,PASS,INCORRECT,Q two?,SELECT 2,wrong grain\n",
        encoding="utf-8")
    a = dc.parse_semantic_audit(str(p))
    assert a["format"] == "csv" and a["complete"] is True
    assert a["incorrect_ids"] == {2}
    vm = dc.build_verdict_map(a, [])
    assert vm[1]["semantic_verdict"] == "CORRECT"
    assert vm[2]["semantic_verdict"] == "INCORRECT"


def test_parse_semantic_audit_markdown_overlay(tmp_path):
    md = tmp_path / "s.md"
    md.write_text(
        "# audit\n\n- Fully semantically correct SQL: **2/3 (66.7%)**\n"
        "- Semantically incorrect or incomplete SQL: **1/3 (33.3%)**\n\n"
        "### Test 002 — join / hard\n\n**Query:** Q two?\n\n"
        "**Finding:** uses wrong grain\n\n**Generated SQL:** `SELECT 2`\n",
        encoding="utf-8")
    a = dc.parse_semantic_audit(str(md))
    assert a["format"] == "markdown" and a["complete"] is False
    assert a["incorrect_ids"] == {2}
    result_recs = [
        {"test_id": 1, "category": "agg", "difficulty": "easy", "status": "PASS",
         "question": "Q one?", "sql": "SELECT 1"},
        {"test_id": 2, "category": "join", "difficulty": "hard", "status": "PASS",
         "question": "Q two?", "sql": "SELECT 2"},
        {"test_id": 3, "category": "agg", "difficulty": "easy", "status": "PASS",
         "question": "Q three?", "sql": "SELECT 3"},
    ]
    vm = dc.build_verdict_map(a, result_recs)
    assert vm[1]["semantic_verdict"] == "CORRECT"
    assert vm[2]["semantic_verdict"] == "INCORRECT"
    assert vm[3]["semantic_verdict"] == "CORRECT"
    assert vm[2]["audit_note"] == "uses wrong grain"


def test_classify_containment_cause_covers_required_taxonomy():
    cases = {
        ("query_b_contained_in_query_a", "Query 2 is contained in Query 1"):
            "definite_wrong_relationship",
        ("incomparable_on_current_database", "each returned rows missing"):
            "definite_wrong_relationship",
        ("unknown", "Cannot compare: Query 1 (no SQL text was generated)."):
            "sql_generation_failure",
        ("unknown", "Cannot compare: Query 1 (no single recoverable base table)."):
            "base_entity_recovery",
        ("unknown", "Cannot compare: Query 1 (no canonical key for table 'x')."):
            "canonical_key_failure",
        ("unknown", "Cannot compare grouped queries: Query 1 (SELECT DISTINCT grouped query is not normalized)."):
            "distinct_groupby_normalization",
        ("unknown", "Cannot compare: Query 1 (aggregate/group-by/distinct/set-op cannot be key-normalized)."):
            "aggregate_normalization",
        ("unknown", "Cannot compare grouped queries: different group keys."):
            "group_key_mismatch",
    }
    for (actual, expl), want in cases.items():
        assert dc.classify_containment_cause(actual, expl)[0] == want


def test_manifest_validate_semantic_disjointness():
    good = {
        "schema_version": "day1.protected.v2", "source_files": {},
        "protected_semantically_correct": {
            "by_database": {"54": {"count": 2, "test_ids": [1, 2]}}, "total": 2},
        "controlled_failures": {
            "by_database": {"54": {"count": 1, "test_ids": [3]}}, "total": 1},
        "protected_containment_recovered_edges": {
            "by_database": {"54": {"count": 1, "edges": [[1, 1, 2]]}}, "total": 1},
    }
    problems, checks = check.validate(good)
    assert problems == [] and checks > 0
    # controlled id 2 also protected-correct -> disjointness violation
    bad = json.loads(json.dumps(good))
    bad["controlled_failures"]["by_database"]["54"] = {"count": 1, "test_ids": [2]}
    problems, _ = check.validate(bad)
    assert any("both protected-correct" in p for p in problems)


def test_normalize_source_strips_numeric_suffix():
    assert dc.normalize_source("llm_variant_1") == "llm_variant"
    assert dc.normalize_source("llm_variant_2") == "llm_variant"
    # non-numeric suffixes preserved
    assert dc.normalize_source("llm_sql_direct_variant") == "llm_sql_direct_variant"


def test_match_selected_candidate_by_number_with_suffixed_label():
    # label 'llm_variant_1' does not string-equal any candidate source, but the
    # authoritative selected_candidate_number resolves it.
    rec = {
        "selected_number": "2", "selected_label": "llm_variant_1",
        "selected_sql": "SELECT b",
        "candidates": [
            {"number": 1, "source": "llm_primary", "sql": "SELECT a"},
            {"number": 2, "source": "llm_variant", "sql": "SELECT b"},
            {"number": 3, "source": "llm_sql_direct", "sql": "SELECT c"},
        ],
    }
    c, method = dc.match_selected_candidate(rec)
    assert c["number"] == 2 and method == "selected_number"


def test_match_selected_candidate_sql_fallback_when_number_missing():
    rec = {
        "selected_number": None, "selected_label": "llm_variant_2",
        "selected_sql": "SELECT b",
        "candidates": [
            {"number": 1, "source": "llm_primary", "sql": "SELECT a"},
            {"number": 2, "source": "llm_variant", "sql": "select   b"},
        ],
    }
    c, method = dc.match_selected_candidate(rec)
    assert c["number"] == 2 and method in ("selected_sql", "normalized_source",
                                           "normalized_source+sql")


def test_candidate_disposition_uses_renamed_heuristic_labels():
    oracle = importlib.import_module("build_candidate_oracle_inventory")
    assert oracle.DISPOSITIONS == [
        "only_selected_candidate_available",
        "plausible_clean_alternative_available",
        "no_clean_different_alternative",
        "unresolved_manual_review",
    ]
    selected = {"sql": "SELECT wrong"}
    # a clean, differing, executed alternative -> plausible_clean_alternative_available
    d, plausible = oracle.classify_disposition(selected, [
        {"sql": "SELECT right", "execution_success": True, "fatal_count": 0}])
    assert d == "plausible_clean_alternative_available" and len(plausible) == 1
    # only the selected candidate's SQL reproduced -> only_selected_candidate_available
    d, _ = oracle.classify_disposition(selected, [
        {"sql": "select   wrong", "execution_success": True, "fatal_count": 0}])
    assert d == "only_selected_candidate_available"
    # a differing alternative existed but was dropped -> no_clean_different_alternative
    d, _ = oracle.classify_disposition(selected, [
        {"sql": "SELECT other", "execution_success": False, "fatal_count": 2}])
    assert d == "no_clean_different_alternative"
