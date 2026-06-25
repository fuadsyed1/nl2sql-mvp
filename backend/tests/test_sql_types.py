"""
test_sql_types.py — offline test for Phase 7 step 1 (sql_types.py).

Runnable as a plain script (no server, no LLM, no SQL execution, no pytest):

    python test_sql_types.py
"""

from generation.sql_types import (
    generated_sql,
    failed_sql,
    to_dict,
    GeneratedSQL,
    FAILURE_REASONS,
)

SUCCESS_KEYS = ["generated", "sql", "params", "diagnostics"]
FAILURE_KEYS = ["generated", "reason", "sql", "params", "diagnostics"]


def test_success_constructor():
    r = generated_sql(
        'SELECT "owners"."lastname" FROM "owners" WHERE "owners"."city" = ?',
        params=["Moscow"],
        diagnostics={"clauses": ["select", "from", "where"], "join_count": 0},
    )
    assert isinstance(r, GeneratedSQL) and r.generated is True
    d = to_dict(r)
    assert list(d.keys()) == SUCCESS_KEYS, list(d.keys())
    assert d["generated"] is True
    assert d["sql"].startswith("SELECT")
    assert d["params"] == ["Moscow"]
    assert d["diagnostics"]["join_count"] == 0
    print("[1] success constructor + to_dict shape -> OK")


def test_success_defaults():
    r = generated_sql("SELECT 1")
    d = to_dict(r)
    assert d["params"] == [] and d["diagnostics"] == {}
    print("[2] success defaults (empty params/diagnostics) -> OK")


def test_failure_constructor():
    r = failed_sql("unresolved_plan", diagnostics={"note": "plan.resolved is false"})
    assert r.generated is False
    d = to_dict(r)
    assert list(d.keys()) == FAILURE_KEYS, list(d.keys())
    assert d["generated"] is False
    assert d["reason"] == "unresolved_plan"
    assert d["sql"] is None and d["params"] == []
    print("[3] failure constructor + to_dict shape -> OK")


def test_all_failure_reasons():
    for reason in ("unresolved_plan", "invalid_ir", "empty_select"):
        assert reason in FAILURE_REASONS
        d = to_dict(failed_sql(reason))
        assert d["generated"] is False and d["reason"] == reason
        assert d["sql"] is None and d["params"] == []
    print("[4] all three failure reasons supported (enum) -> OK")


def test_params_are_copied():
    src = ["dog"]
    r = generated_sql("... WHERE x = ?", params=src)
    src.append("cat")  # mutating the caller's list must not affect the result
    assert to_dict(r)["params"] == ["dog"]
    print("[5] params list is copied, not aliased -> OK")


def main():
    tests = [
        test_success_constructor,
        test_success_defaults,
        test_failure_constructor,
        test_all_failure_reasons,
        test_params_are_copied,
    ]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed — sql_types.py verified")


if __name__ == "__main__":
    main()