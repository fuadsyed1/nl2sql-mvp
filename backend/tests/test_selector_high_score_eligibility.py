"""Regression tests for the deterministic selector defect (DB56 t52) and the
hardened promotion rule.

A non-fatal, executed candidate that RC3 demotes as "semantically incomplete"
ONLY because of a false-positive missing-output-aggregate gate — while it already
PROJECTS the requested per-entity derived value and strictly outscores every
eligible candidate — must be allowed to compete. The override pool is exactly
`eligible + promotable`: no unrelated incomplete candidate is reintroduced.
Fatal exclusion, genuine RC3 demotion, consensus, RC4/RC5, direct/repair
preference and deterministic tie-breaking are all preserved.
"""
from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best
from sql_candidates.semantic_obligations import compute_profile, is_eligible

# abstract schema — nothing DB / table / column / test specific
IDX = {"tables": {
    "t": [{"name": "tid", "is_key": True}, {"name": "a"}, {"name": "b"}],
    "x": [{"name": "xid", "is_key": True}, {"name": "tid"}],
}}

# per-entity derived-metric projection with GROUP BY and no aggregate -> RC3 marks
# it 'incomplete' (missing output aggregate) though it is non-fatal AND projects
# the derived value  ==> PROMOTABLE.
SQL_RATIO = ("SELECT t.a, t.b, CAST(t.a AS REAL) / NULLIF(t.b, 0) AS ratio "
             "FROM t GROUP BY t.tid, t.a, t.b")
SQL_RATIO2 = ("SELECT t.a, t.b, (t.a - t.b) AS diff "
              "FROM t GROUP BY t.tid, t.a, t.b")          # another promotable shape
# aggregate query -> RC3 eligible (different result).
SQL_AGG = ("SELECT t.a, COUNT(x.xid) AS n FROM t JOIN x ON t.tid = x.tid "
           "GROUP BY t.a")
# grouped answer that HIDES the count -> incomplete, derived_output_projected=FALSE
# ==> NOT promotable (condition 4).
SQL_HIDDEN = "SELECT t.a FROM t GROUP BY t.a HAVING COUNT(*) > 0"
SQL_PLAIN = "SELECT t.a FROM t"                            # eligible, no obligations


def _c(label, source, score, sql, rows, fatal=None):
    c = SqlCandidate(source=source, label=label, sql=sql,
                     execution={"executed": True, "columns": ["a"],
                                "rows": rows, "row_count": len(rows)})
    c.score = score
    c.validation = {"fatal": list(fatal or [])}
    return c


def _elig(sql, checklist=None):
    return is_eligible(compute_profile(sql, {"fatal": []}, checklist, None, IDX))


# ---- sanity: the fixtures really have the profiles we claim ----------------
def test_profiles_match_the_reported_defect():
    assert _elig(SQL_RATIO) is False and _elig(SQL_AGG) is True
    assert _elig(SQL_HIDDEN) is False        # incomplete, but derived_output_projected=False
    p = compute_profile(SQL_RATIO, {"fatal": []}, None, None, IDX)
    assert p.get("derived_output_projected") is True
    assert set(p.get("_gating_missing") or ()) == {"required_output_aggregate_satisfied"}
    assert set(p.get("_missing") or ()) <= {"required_output_aggregate_satisfied"}
    ph = compute_profile(SQL_HIDDEN, {"fatal": []}, None, None, IDX)
    assert ph.get("derived_output_projected") is False


# 1. eligible 86 vs promotable 94 -> the 94 candidate wins ---------------------
def test_1_promotable_94_beats_eligible_86():
    prim = _c("llm_primary", "llm_primary", 86, SQL_AGG, [[1], [2]])
    d1 = _c("llm_sql_direct", "llm_sql_direct", 94, SQL_RATIO, [[9]])
    d2 = _c("llm_sql_direct_grain", "llm_sql_direct_grain", 94, SQL_RATIO, [[9]])
    d3 = _c("llm_sql_direct_variant", "llm_sql_direct_variant", 94, SQL_RATIO, [[9]])
    sel, meta = select_best([prim, d1, d2, d3], idx=IDX, question="show a per b")
    assert sel.score == 94 and sel.source.startswith("llm_sql_direct")
    assert "incomplete_high_score_override" in meta


# 2. unrelated non-promotable incomplete score 99 is EXCLUDED ------------------
def test_2_unrelated_incomplete_99_cannot_win():
    prim = _c("llm_primary", "llm_primary", 86, SQL_AGG, [[1], [2]])
    promo = _c("llm_sql_direct", "llm_sql_direct", 94, SQL_RATIO, [[9]])
    # score-99 candidate is incomplete (hidden count) but NOT promotable
    junk = _c("llm_variant", "llm_variant", 99, SQL_HIDDEN, [[7]])
    sel, meta = select_best([prim, promo, junk], idx=IDX, question="show a per b")
    assert sel is promo                                   # the 94 promotable wins
    assert junk.label not in meta["incomplete_high_score_override"]["override_pool_labels"]
    # every candidate in the override pool is eligible OR explicitly promotable
    labels = set(meta["incomplete_high_score_override"]["override_pool_labels"])
    assert labels == {"llm_primary", "llm_sql_direct"}


# 3. incomplete for a DIFFERENT gating reason cannot enter the pool -----------
def test_3_different_gating_reason_not_promotable():
    ck = {"required_sql_shape": "set_operation"}
    # eligible: uses a set operator
    good = _c("llm_primary", "llm_primary", 60, "SELECT t.a FROM t UNION SELECT x.tid FROM x", [[1]])
    # incomplete because it is missing the set operation (gating != output_aggregate)
    bad = _c("llm_sql_direct", "llm_sql_direct", 95, "SELECT t.a FROM t WHERE t.b = 1", [[9]])
    assert _elig("SELECT t.a FROM t WHERE t.b = 1", ck) is False
    sel, meta = select_best([good, bad], checklist=ck, idx=IDX, question="a either x or y")
    assert sel is good
    assert "incomplete_high_score_override" not in meta


# 4. derived_output_projected = false cannot be promoted ----------------------
def test_4_no_derived_projection_not_promotable():
    good = _c("llm_primary", "llm_primary", 60, SQL_AGG, [[1], [2]])
    bad = _c("llm_sql_direct", "llm_sql_direct", 95, SQL_HIDDEN, [[9]])  # derived=False
    sel, meta = select_best([good, bad], idx=IDX, question="count a by b")
    assert sel is good
    assert "incomplete_high_score_override" not in meta


# 5. multiple gating failures cannot be promoted -----------------------------
def test_5_multiple_gating_failures_not_promotable():
    ck = {"required_sql_shape": "set_operation"}
    # ratio-group-by (missing output aggregate) AND missing the set operation
    both = "SELECT t.a, t.b, CAST(t.a AS REAL)/NULLIF(t.b,0) AS r FROM t GROUP BY t.tid, t.a, t.b"
    p = compute_profile(both, {"fatal": []}, ck, None, IDX)
    assert set(p.get("_gating_missing") or ()) == {
        "required_output_aggregate_satisfied", "required_set_conditions_satisfied"}
    good = _c("llm_primary", "llm_primary", 60, "SELECT t.a FROM t UNION SELECT x.tid FROM x", [[1]])
    bad = _c("llm_sql_direct", "llm_sql_direct", 95, both, [[9]])
    sel, meta = select_best([good, bad], checklist=ck, idx=IDX, question="a either x or y")
    assert sel is good
    assert "incomplete_high_score_override" not in meta


# 6. fatal score-100 candidate cannot win ------------------------------------
def test_6_fatal_100_cannot_win():
    bad = _c("llm_sql_direct", "llm_sql_direct", 100, SQL_RATIO, [[9]],
             fatal=["grain violation: raw child rows"])
    good = _c("llm_primary", "llm_primary", 50, SQL_PLAIN, [[2]])
    sel, meta = select_best([bad, good], idx=IDX, question="show a per b")
    assert sel is good and not (sel.validation or {}).get("fatal")
    assert "incomplete_high_score_override" not in meta


# 7. eligible score >= promotable -> normal RC3 behavior ---------------------
def test_7_eligible_ge_incomplete_keeps_rc3():
    inc = _c("llm_sql_direct", "llm_sql_direct", 80, SQL_RATIO, [[9]])
    elig = _c("llm_primary", "llm_primary", 90, SQL_AGG, [[1], [2]])
    sel, meta = select_best([inc, elig], idx=IDX, question="show a per b")
    assert sel is elig
    assert "incomplete_high_score_override" not in meta
    # equal score also keeps RC3 (strictly-greater rule)
    inc2 = _c("llm_sql_direct", "llm_sql_direct", 90, SQL_RATIO, [[9]])
    elig2 = _c("llm_primary", "llm_primary", 90, SQL_AGG, [[1], [2]])
    sel2, meta2 = select_best([inc2, elig2], idx=IDX, question="show a per b")
    assert sel2 is elig2 and "incomplete_high_score_override" not in meta2


# 8. multiple promotable candidates remain deterministic ---------------------
def test_8_multiple_promotable_deterministic():
    prim = _c("llm_primary", "llm_primary", 70, SQL_AGG, [[1], [2]])
    d1 = _c("llm_sql_direct", "llm_sql_direct", 94, SQL_RATIO, [[9]])
    d2 = _c("llm_sql_direct_grain", "llm_sql_direct_grain", 94, SQL_RATIO, [[9]])
    d3 = _c("llm_sql_direct_variant", "llm_sql_direct_variant", 96, SQL_RATIO2, [[8]])
    cands = [prim, d1, d2, d3]
    labels = {select_best(list(reversed(cands)) if i % 2 else list(cands),
                          idx=IDX, question="show a per b")[0].label for i in range(6)}
    assert len(labels) == 1                              # deterministic winner


# 9. tie-break asserts the exact expected label independent of order ----------
def test_9_tie_break_exact_label():
    # two promotable candidates, equal score, same result -> deterministic pick by
    # source priority then label (llm_sql_direct_grain > llm_sql_direct on label).
    a = _c("llm_sql_direct", "llm_sql_direct", 94, SQL_RATIO, [[9]])
    b = _c("llm_sql_direct_grain", "llm_sql_direct_grain", 94, SQL_RATIO, [[9]])
    elig = _c("llm_primary", "llm_primary", 80, SQL_AGG, [[1], [2]])
    for order in ([a, b, elig], [b, a, elig], [elig, a, b], [elig, b, a]):
        sel, _ = select_best(order, idx=IDX, question="show a per b")
        assert sel.label == "llm_sql_direct_grain"


# 10. consensus unchanged when the promotion rule does not apply --------------
def test_10_consensus_unchanged():
    p = _c("llm_primary", "llm_primary", 60, SQL_PLAIN, [[1], [2]])
    fam = _c("query_family", "query_family", 60, SQL_PLAIN, [[1], [2]])
    sel, meta = select_best([p, fam], idx=IDX, question="list a")
    assert meta["selection_reason"] == "consensus_group"
    assert "incomplete_high_score_override" not in meta


# 11. direct/repair preference unchanged when promotion does not apply --------
def test_11_direct_repair_preference_unchanged():
    # all eligible: an executed direct candidate with rows replaces a zero-row pick
    zero = _c("llm_primary", "llm_primary", 70, SQL_PLAIN, [])
    direct = _c("llm_sql_direct", "llm_sql_direct", 70, SQL_PLAIN, [[1]])
    sel, meta = select_best([zero, direct], idx=IDX, question="list a")
    assert sel is direct
    assert "incomplete_high_score_override" not in meta


# 12. every candidate in the override pool is eligible or promotable ----------
def test_12_override_pool_only_eligible_or_promotable():
    prim = _c("llm_primary", "llm_primary", 86, SQL_AGG, [[1], [2]])
    promo = _c("llm_sql_direct", "llm_sql_direct", 94, SQL_RATIO, [[9]])
    junk1 = _c("llm_variant", "llm_variant", 99, SQL_HIDDEN, [[7]])     # incomplete, not promotable
    junk2 = _c("llm_variant_2", "llm_variant", 40, SQL_HIDDEN, [[7]])   # incomplete, not promotable
    sel, meta = select_best([prim, promo, junk1, junk2], idx=IDX, question="show a per b")
    ov = meta["incomplete_high_score_override"]
    pool_labels = set(ov["override_pool_labels"])
    eligible_labels = {"llm_primary"}                    # SQL_AGG is eligible
    promotable_labels = set(ov["promoted"])
    assert pool_labels <= (eligible_labels | promotable_labels)
    assert "llm_variant" not in pool_labels and "llm_variant_2" not in pool_labels
    assert sel is promo
