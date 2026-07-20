"""Final stabilization Part A — hard selection invariant.

A candidate with fatal semantic violations can NEVER be returned as a normal
success: not via consensus, not via score, not via repair, not via the
low-confidence fallback. When no clean executed candidate exists, the caller
must return the controlled no_semantically_valid_sql failure.

The endpoint-level conversion lives in app.py (run_nl_sql_pipeline) and
requires a live DB + LLM; these tests cover the decision layer it delegates
to: select_best + enforce_selection_safety. app.py additionally asserts the
invariant immediately before response assembly and computes
success = executed_ok AND not fatal.
"""

from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best, enforce_selection_safety


def _cand(label, *, source="llm_sql_direct", score=50.0, fatal=None,
          executed=True, rows=None):
    c = SqlCandidate(
        source=source, label=label, sql=f"SELECT 1 -- {label}",
        execution={"executed": executed, "columns": ["x"],
                   "rows": rows if rows is not None else [[1]],
                   "row_count": len(rows) if rows is not None else 1,
                   "truncated": False, "diagnostics": {}}
        if executed else {"executed": False, "error": "boom"})
    c.score = score
    c.validation = {"fatal": list(fatal or [])}
    return c


# 1. a consensus group containing only fatal candidates cannot win ------------
def test_fatal_consensus_group_cannot_win():
    a = _cand("f1", score=80, fatal=["grain violation: x"], rows=[[1], [2]])
    b = _cand("f2", score=80, fatal=["grain violation: x"], rows=[[1], [2]])
    clean = _cand("ok", score=45, rows=[[3]])
    pick, meta = select_best([a, b, clean])
    assert pick is clean
    safe, controlled, _ = enforce_selection_safety(pick, [a, b, clean])
    assert safe is clean and controlled is False


# 2. the highest-scoring candidate with fatal reasons cannot win --------------
def test_highest_scoring_fatal_cannot_win():
    bad = _cand("bad", score=95, fatal=["grain violation: y"])
    clean = _cand("ok", score=50, rows=[[9]])
    pick, _ = select_best([bad, clean])
    assert pick is clean


# 3. a repaired candidate with fatal reasons cannot win ------------------------
def test_fatal_repair_cannot_win():
    bad_repair = _cand("llm_sql_repair", source="llm_sql_repair", score=90,
                       fatal=["grain violation: z"])
    clean = _cand("ok", score=55, rows=[[2]])
    pick, _ = select_best([bad_repair, clean])
    assert pick is clean
    # even if selection somehow returned it, the safety gate replaces it
    safe, controlled, _ = enforce_selection_safety(bad_repair,
                                                   [bad_repair, clean])
    assert safe is clean and controlled is False


# 4. the low-confidence fallback cannot override fatal disqualification -------
def test_low_confidence_fallback_cannot_override():
    a = _cand("f1", score=30, fatal=["grain violation: a"])
    b = _cand("f2", score=20, fatal=["grain violation: b"])
    pick, meta = select_best([a, b])
    assert meta["low_confidence"] is True          # selector flags it ...
    safe, controlled, reasons = enforce_selection_safety(pick, [a, b])
    assert safe is None and controlled is True     # ... and the gate blocks it
    assert reasons                                  # fatal reasons surfaced


# 5. success cannot be true when the selected validation has fatal reasons ----
def test_selected_fatal_never_a_success():
    bad = _cand("bad", score=88, fatal=["semantic violation: q"])
    safe, controlled, reasons = enforce_selection_safety(bad, [bad])
    assert safe is None and controlled is True
    # app.py: controlled failure response carries success=False +
    # error=no_semantically_valid_sql; the rejected SQL may only appear
    # under the explicitly labeled debug_rejected_sql field.
    assert "semantic violation: q" in reasons


# 6. when every executed candidate is fatal -> no_semantically_valid_sql ------
def test_all_fatal_is_controlled_failure():
    cands = [
        _cand("f1", score=39, fatal=["grain violation: raw rows"]),
        _cand("f2", score=39, fatal=["grain violation: raw rows"]),
        # a non-executed candidate must NOT mask the failure (the exact
        # Q40 run-2 bug: all() over non-executed candidates never fired)
        _cand("never_ran", executed=False, score=5),
    ]
    pick, _ = select_best(cands)
    safe, controlled, _ = enforce_selection_safety(pick, cands)
    assert controlled is True and safe is None


# a clean selected candidate passes through unchanged --------------------------
def test_clean_selection_unchanged():
    clean = _cand("ok", score=70)
    safe, controlled, reasons = enforce_selection_safety(clean, [clean])
    assert safe is clean and controlled is False and reasons == []
