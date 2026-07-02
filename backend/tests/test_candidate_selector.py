"""Unit tests for sql_candidates.candidate_selector + result_equivalence.

Selection policy contract:
  * agreeing executed candidates (equivalent result sets) win as a group;
  * a much-higher-scored outlier overrides the consensus group;
  * when nothing executes, the least-bad candidate is returned WITH a warning;
  * a low-scoring winner carries a low-confidence warning.
"""

from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best
from sql_candidates.result_equivalence import result_signature, group_candidates


def _exec(rows, columns=("a",)):
    rows = [list(r) for r in rows]
    return {"executed": True, "columns": list(columns), "rows": rows,
            "row_count": len(rows), "truncated": False, "diagnostics": {}}


def _fail():
    return {"executed": False, "reason": "sql_error", "error": "boom",
            "columns": [], "rows": [], "row_count": 0, "diagnostics": {}}


def _cand(label, source, score, execution, sql="SELECT 1"):
    c = SqlCandidate(source=source, label=label, sql=sql, execution=execution)
    c.score = score
    return c


# ---------------------------------------------------------------------------
# result equivalence
# ---------------------------------------------------------------------------
def test_signature_normalizes_case_whitespace_floats_and_row_order():
    a = _exec([["  Rex ", 2.0], ["ash", 1]], columns=("name", "n"))
    b = _exec([["ash", 1.0], ["rex", 2]], columns=("name", "n"))
    assert result_signature(a) == result_signature(b)


def test_signature_distinguishes_different_data():
    a = _exec([["rex"]])
    b = _exec([["ash"]])
    assert result_signature(a) != result_signature(b)


def test_not_executed_has_no_signature():
    assert result_signature(_fail()) is None
    assert result_signature(None) is None


def test_grouping_falls_back_to_relaxed_column_order():
    # same data, columns swapped -> strict differs, relaxed agrees
    a = _cand("x", "llm_primary", 70, _exec([["rex", "dog"]], ("name", "species")))
    b = _cand("y", "llm_variant", 68, _exec([["dog", "rex"]], ("species", "name")))
    groups = group_candidates([a, b])
    assert len(groups[0]) == 2


# ---------------------------------------------------------------------------
# selection
# ---------------------------------------------------------------------------
def test_consensus_group_wins():
    agree1 = _cand("query_family", "query_family", 72, _exec([["rex"]]))
    agree2 = _cand("llm_variant_1", "llm_variant", 70, _exec([["rex"]]))
    loner = _cand("llm_primary", "llm_primary", 74, _exec([["ash"]]))

    selected, meta = select_best([agree1, agree2, loner])

    assert selected is agree1                       # highest-priority member of group
    assert meta["selection_reason"] == "consensus_group"
    assert meta["consensus_group_size"] == 2
    assert meta["selected_candidate_source"] == "query_family"
    assert meta["candidate_count"] == 3
    assert len(meta["rejected_candidates"]) == 2


def test_validation_score_override_beats_consensus():
    # two candidates agree but both look structurally poor; a much better
    # scored outlier must win (agreement on a wrong answer happens).
    agree1 = _cand("llm_primary", "llm_primary", 50, _exec([["ash"]]))
    agree2 = _cand("llm_variant_1", "llm_variant", 48, _exec([["ash"]]))
    strong = _cand("query_family", "query_family", 85, _exec([["rex"]]))

    selected, meta = select_best([agree1, agree2, strong])

    assert selected is strong
    assert meta["selection_reason"] == "validation_score_override"


def test_small_score_gap_does_not_override_consensus():
    agree1 = _cand("llm_primary", "llm_primary", 70, _exec([["ash"]]))
    agree2 = _cand("llm_variant_1", "llm_variant", 69, _exec([["ash"]]))
    slightly_better = _cand("query_family", "query_family", 75, _exec([["rex"]]))

    selected, meta = select_best([agree1, agree2, slightly_better])

    assert selected is agree1
    assert meta["selection_reason"] == "consensus_group"


def test_no_execution_returns_least_bad_with_warning():
    a = _cand("llm_primary", "llm_primary", 20, _fail())
    b = _cand("llm_variant_1", "llm_variant", 35, _fail())

    selected, meta = select_best([a, b])

    assert selected is b
    assert meta["selection_reason"] == "least_bad_no_execution"
    assert any("least-bad" in w for w in meta["warnings"])
    assert any("low confidence" in w for w in meta["warnings"])


def test_single_executed_candidate_is_selected():
    only = _cand("llm_primary", "llm_primary", 75, _exec([["rex"]]))
    dead = _cand("llm_variant_1", "llm_variant", 10, _fail())

    selected, meta = select_best([only, dead])

    assert selected is only
    assert meta["selection_reason"] == "best_scored_executed"
    assert meta["warnings"] == []


def test_empty_candidate_list():
    selected, meta = select_best([])
    assert selected is None
    assert meta["candidate_count"] == 0
    assert meta["warnings"]


def test_metadata_shape():
    a = _cand("llm_primary", "llm_primary", 75, _exec([["rex"]]))
    _, meta = select_best([a])
    for key in ("selected_candidate_source", "candidate_count",
                "candidate_scores", "candidate_reasons", "rejected_candidates",
                "selection_reason", "consensus_group_size", "warnings"):
        assert key in meta
    assert meta["candidate_scores"][0]["score"] == 75
