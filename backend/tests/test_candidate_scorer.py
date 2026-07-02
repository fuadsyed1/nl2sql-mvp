"""Unit tests for sql_candidates.candidate_scorer.

Each test builds a hand-made candidate (extraction + SQL + fake execution
result) against a small petshop-style schema graph and asserts the scoring
contract: illegal joins, missing required SQL shapes, and alias errors sink
a candidate; a structurally correct candidate scores high. No LLM and no
database are involved.
"""

from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_scorer import score_candidate, LOW_SCORE_THRESHOLD


# ---------------------------------------------------------------------------
# fixture schema graph
# ---------------------------------------------------------------------------
def _col(name, dtype="TEXT", pk=False):
    return {"column_name": name, "data_type": dtype, "is_primary_key_candidate": pk}


GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [
            _col("oid", "INTEGER", pk=True), _col("lastname"), _col("city"),
            _col("annual_income", "REAL"),
        ]},
        {"table_name": "pets", "columns": [
            _col("petid", "INTEGER", pk=True), _col("oid", "INTEGER"),
            _col("name"), _col("species"),
        ]},
        {"table_name": "foods", "columns": [
            _col("food_id", "INTEGER", pk=True), _col("brand"),
            _col("food_name"), _col("price", "REAL"), _col("food_type"),
            _col("flavor"),
        ]},
        {"table_name": "purchases", "columns": [
            _col("purchase_id", "INTEGER", pk=True), _col("oid", "INTEGER"),
            _col("food_id", "INTEGER"), _col("quantity", "INTEGER"),
            _col("total", "REAL"),
        ]},
    ],
    "relationships": [
        {"from_table": "pets", "from_column": "oid",
         "to_table": "owners", "to_column": "oid"},
        {"from_table": "purchases", "from_column": "oid",
         "to_table": "owners", "to_column": "oid"},
        {"from_table": "purchases", "from_column": "food_id",
         "to_table": "foods", "to_column": "food_id"},
    ],
}


def _exec_ok(columns=("name",), rows=(("rex",),)):
    rows = [list(r) for r in rows]
    return {"executed": True, "columns": list(columns), "rows": rows,
            "row_count": len(rows), "truncated": False, "diagnostics": {}}


def _cand(sql, extraction=None, execution=None, source="llm_primary",
          label="llm_primary", family_info=None):
    return SqlCandidate(source=source, label=label, sql=sql,
                        extraction=extraction or {},
                        execution=execution if execution is not None else _exec_ok(),
                        family_info=family_info)


def _score(question, cand):
    return score_candidate(question, cand, GRAPH).score


# ---------------------------------------------------------------------------
# 1. illegal join gets a very low score
# ---------------------------------------------------------------------------
def test_illegal_join_gets_very_low_score():
    question = "List pets with purchases"
    bad = _cand(
        "SELECT p.name FROM pets p JOIN purchases pu ON p.petid = pu.quantity",
        extraction={"tables": ["pets", "purchases"], "anti_exists": [{
            "target_table": "purchases",
            "where": [{"left": {"table": "purchases", "column": "quantity"},
                       "op": "=",
                       "right": {"table": "pets", "column": "petid"}}],
        }]},
    )
    good = _cand(
        "SELECT foods.food_name FROM foods JOIN purchases "
        "ON purchases.food_id = foods.food_id",
        extraction={"tables": ["foods", "purchases"]},
    )
    bad_score = _score(question, bad)
    good_score = _score("List foods with purchases", good)

    assert bad_score < LOW_SCORE_THRESHOLD          # very low: below selection confidence
    assert bad_score <= good_score - 30
    assert any("illegal join" in r for r in bad.reasons)
    assert not any("illegal join" in r for r in good.reasons)


def test_sql_level_suspicious_join_is_caught_without_extraction_edge():
    # The join appears ONLY in the SQL text (extraction has no edges).
    cand = _cand(
        "SELECT o.lastname FROM owners o JOIN purchases pu ON o.oid = pu.total",
        extraction={"tables": ["owners", "purchases"]},
    )
    _score("List owners with purchases", cand)
    assert any("illegal join" in r for r in cand.reasons)


# ---------------------------------------------------------------------------
# 2. missing NOT EXISTS for "never" gets a low score
# ---------------------------------------------------------------------------
def test_missing_not_exists_for_never_scores_low():
    question = "List foods never purchased"
    without = _cand(
        "SELECT foods.food_name FROM foods JOIN purchases "
        "ON purchases.food_id = foods.food_id",
        extraction={"tables": ["foods", "purchases"]},
        execution=_exec_ok(("food_name",), (("kibble",),)),
    )
    with_ne = _cand(
        "SELECT foods.food_name FROM foods WHERE NOT EXISTS "
        "(SELECT 1 FROM purchases WHERE purchases.food_id = foods.food_id)",
        extraction={"tables": ["foods"], "anti_exists": [{
            "target_table": "purchases",
            "where": [{"left": {"table": "purchases", "column": "food_id"},
                       "op": "=",
                       "right": {"table": "foods", "column": "food_id"}}],
        }]},
        execution=_exec_ok(("food_name",), (("treats",),)),
    )
    s_without = _score(question, without)
    s_with = _score(question, with_ne)

    assert s_with > s_without
    assert s_with - s_without >= 25   # -20 penalty vs +8 bonus
    assert any("absence intent" in r for r in without.reasons)


# ---------------------------------------------------------------------------
# 3. missing LEFT JOIN for outer-join intent gets a low score
# ---------------------------------------------------------------------------
def test_missing_left_join_for_outer_intent_scores_low():
    question = ("List all owners and their pets using an outer join "
                "so owners without pets are still visible")
    inner = _cand(
        "SELECT owners.lastname, pets.name FROM owners "
        "JOIN pets ON pets.oid = owners.oid",
        extraction={"tables": ["owners", "pets"]},
        execution=_exec_ok(("lastname", "name"), (("smith", "rex"),)),
    )
    outer = _cand(
        "SELECT owners.lastname, pets.name FROM owners "
        "LEFT JOIN pets ON pets.oid = owners.oid",
        extraction={"tables": ["owners", "pets"], "explicit_joins": [{
            "join_type": "left", "from_table": "owners", "to_table": "pets",
            "conditions": [{"left": {"table": "pets", "column": "oid"},
                            "op": "=",
                            "right": {"table": "owners", "column": "oid"}}],
        }]},
        execution=_exec_ok(("lastname", "name"), (("smith", "rex"), ("jones", None))),
    )
    s_inner = _score(question, inner)
    s_outer = _score(question, outer)

    assert s_outer > s_inner
    assert any("outer-join intent" in r for r in inner.reasons)
    assert not any("outer-join intent" in r for r in outer.reasons)


# ---------------------------------------------------------------------------
# 4. correct top-per-group gets a high score
# ---------------------------------------------------------------------------
def test_correct_top_per_group_scores_high():
    question = "List the highest priced food per brand"
    cand = _cand(
        'WITH ranked AS (SELECT foods.food_name, foods.brand, foods.price, '
        'ROW_NUMBER() OVER (PARTITION BY foods.brand ORDER BY foods.price DESC) '
        'AS rn FROM foods) SELECT food_name, brand, price FROM ranked WHERE rn = 1',
        extraction={"tables": ["foods"],
                    "select": [{"table": "foods", "column": "food_name"},
                               {"table": "foods", "column": "price"}],
                    "top_per_group": [{
                        "table": "foods",
                        "partition_by": [{"table": "foods", "column": "brand"}],
                        "order_by": {"table": "foods", "column": "price",
                                     "direction": "desc"},
                        "rank": 1, "include_ties": True}]},
        execution=_exec_ok(("food_name", "brand", "price"),
                           (("kibble", "acme", 9.5),)),
    )
    score = _score(question, cand)
    assert score >= 70
    assert cand.validation["required_shapes"].get("top_per_group") is True
    assert not cand.reasons  # nothing to complain about


def test_top_per_group_intent_without_structure_is_penalized():
    question = "List the highest priced food per brand"
    flat = _cand(
        "SELECT foods.food_name, foods.brand, MAX(foods.price) FROM foods",
        extraction={"tables": ["foods"],
                    "select": [{"table": "foods", "column": "food_name"},
                               {"table": "foods", "column": "brand"}]},
        execution=_exec_ok(("food_name", "brand", "MAX(price)"),
                           (("kibble", "acme", 9.5),)),
    )
    _score(question, flat)
    assert any("top-per-group intent" in r for r in flat.reasons)


# ---------------------------------------------------------------------------
# 5. duplicate table alias gets a low score
# ---------------------------------------------------------------------------
def test_duplicate_alias_scores_low():
    question = "List pets and owners"
    dup = _cand(
        "SELECT p.name FROM pets p JOIN owners p ON p.oid = p.oid",
        extraction={"tables": ["pets", "owners"]},
    )
    ok = _cand(
        "SELECT p.name FROM pets p JOIN owners o ON p.oid = o.oid",
        extraction={"tables": ["pets", "owners"]},
    )
    s_dup = _score(question, dup)
    s_ok = _score(question, ok)

    assert s_dup <= s_ok - 25
    assert any("duplicate table alias" in r for r in dup.reasons)


def test_same_alias_in_sibling_subqueries_is_not_a_duplicate():
    # NOT EXISTS subqueries may legitimately reuse an alias in separate scopes.
    cand = _cand(
        "SELECT o.lastname FROM owners o "
        "WHERE NOT EXISTS (SELECT 1 FROM purchases x WHERE x.oid = o.oid) "
        "AND NOT EXISTS (SELECT 1 FROM pets x WHERE x.oid = o.oid)",
        extraction={"tables": ["owners"]},
    )
    _score("List owners", cand)
    assert not any("duplicate table alias" in r for r in cand.reasons)


# ---------------------------------------------------------------------------
# 6. undefined alias gets a low score
# ---------------------------------------------------------------------------
def test_undefined_alias_scores_low():
    question = "List pets"
    bad = _cand(
        "SELECT x.name FROM pets p WHERE p.species = 'dog'",
        extraction={"tables": ["pets"]},
    )
    ok = _cand(
        "SELECT p.name FROM pets p WHERE p.species = 'dog'",
        extraction={"tables": ["pets"]},
    )
    s_bad = _score(question, bad)
    s_ok = _score(question, ok)

    assert s_bad <= s_ok - 25
    assert any("undefined alias" in r for r in bad.reasons)
    assert not any("undefined alias" in r for r in ok.reasons)


# ---------------------------------------------------------------------------
# supporting contract checks
# ---------------------------------------------------------------------------
def test_execution_failure_scores_below_executed_equivalent():
    question = "List pets"
    failed = _cand(
        "SELECT pets.name FROM pets",
        extraction={"tables": ["pets"]},
        execution={"executed": False, "reason": "sql_error",
                   "error": "no such column: nam", "columns": [], "rows": [],
                   "row_count": 0, "diagnostics": {}},
    )
    ok = _cand("SELECT pets.name FROM pets", extraction={"tables": ["pets"]})
    assert _score(question, failed) < _score(question, ok) - 50


def test_no_sql_candidate_scores_near_zero():
    cand = SqlCandidate(source="llm_variant", label="llm_variant_1",
                        sql=None, extraction={"tables": []})
    score = score_candidate("List pets", cand, GRAPH).score
    assert score <= 10


def test_unknown_column_is_penalized():
    cand = _cand(
        "SELECT pets.nickname FROM pets",
        extraction={"tables": ["pets"],
                    "select": [{"table": "pets", "column": "nickname"}]},
        execution=_exec_ok(("nickname",), ()),
    )
    _score("List pets", cand)
    assert any("does not exist" in r for r in cand.reasons)


def test_count_distinct_intent_requires_count_distinct():
    question = "How many distinct brands has each owner purchased?"
    plain = _cand(
        "SELECT owners.lastname, COUNT(foods.brand) FROM owners "
        "JOIN purchases ON purchases.oid = owners.oid "
        "JOIN foods ON purchases.food_id = foods.food_id GROUP BY owners.lastname",
        extraction={"tables": ["owners", "purchases", "foods"],
                    "aggregations": [{"function": "COUNT", "table": "foods",
                                      "column": "brand", "alias": "n"}]},
        execution=_exec_ok(("lastname", "n"), (("smith", 3),)),
    )
    distinct = _cand(
        "SELECT owners.lastname, COUNT(DISTINCT foods.brand) FROM owners "
        "JOIN purchases ON purchases.oid = owners.oid "
        "JOIN foods ON purchases.food_id = foods.food_id GROUP BY owners.lastname",
        extraction={"tables": ["owners", "purchases", "foods"],
                    "aggregations": [{"function": "COUNT", "table": "foods",
                                      "column": "brand", "alias": "n",
                                      "distinct": True}]},
        execution=_exec_ok(("lastname", "n"), (("smith", 2),)),
    )
    s_plain = _score(question, plain)
    s_distinct = _score(question, distinct)
    assert s_distinct > s_plain
    assert any("COUNT(DISTINCT" in r for r in plain.reasons)


def test_guard_rejected_family_candidate_is_penalized():
    question = "List pets"
    plain = _cand("SELECT pets.name FROM pets", extraction={"tables": ["pets"]},
                  source="query_family", label="query_family",
                  family_info={"family": "x", "confidence": 0.9,
                               "guard_valid": True, "guard_reasons": []})
    rejected = _cand("SELECT pets.name FROM pets", extraction={"tables": ["pets"]},
                     source="query_family", label="query_family",
                     family_info={"family": "x", "confidence": 0.9,
                                  "guard_valid": False,
                                  "guard_reasons": ["shape mismatch"]})
    assert _score(question, rejected) == _score(question, plain) - 15
    assert any("family guard rejected" in r for r in rejected.reasons)
