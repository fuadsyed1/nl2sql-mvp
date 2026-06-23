"""
test_execution_result.py — offline test for Phase 8 step 1 (execution_result.py).

Runnable as a plain script (no server, no LLM, no DB, no pytest):

    python test_execution_result.py
"""

from execution_result import (
    success_result,
    failure_result,
    to_dict,
    ExecutionResult,
    FAILURE_REASONS,
    DEFAULT_ROW_LIMIT,
)

SUCCESS_KEYS = ["executed", "columns", "rows", "row_count", "truncated", "diagnostics"]
FAILURE_KEYS = ["executed", "reason", "error", "columns", "rows", "row_count", "diagnostics"]


def test_success_constructor():
    r = success_result(["lastname"], [["Smith"], ["Jones"]],
                       diagnostics={"param_count": 1})
    assert isinstance(r, ExecutionResult) and r.executed is True
    d = to_dict(r)
    assert list(d.keys()) == SUCCESS_KEYS, list(d.keys())
    assert d["columns"] == ["lastname"]
    assert d["rows"] == [["Smith"], ["Jones"]]
    assert d["row_count"] == 2          # derived from rows
    assert d["truncated"] is False
    assert d["diagnostics"]["param_count"] == 1
    print("[1] success constructor + to_dict shape + derived row_count -> OK")


def test_truncated_flag():
    d = to_dict(success_result(["x"], [[1], [2]], truncated=True))
    assert d["truncated"] is True and d["row_count"] == 2
    print("[2] truncated flag honored -> OK")


def test_failure_constructor():
    r = failure_result("sql_error", error="no such column: pets.species",
                       diagnostics={"sql_present": True})
    assert r.executed is False
    d = to_dict(r)
    assert list(d.keys()) == FAILURE_KEYS, list(d.keys())
    assert d["reason"] == "sql_error"
    assert d["error"] == "no such column: pets.species"
    assert d["columns"] == [] and d["rows"] == [] and d["row_count"] == 0
    print("[3] failure constructor + to_dict shape -> OK")


def test_all_failure_reasons():
    for reason in ("not_generated", "db_unavailable", "sql_error"):
        assert reason in FAILURE_REASONS
        d = to_dict(failure_result(reason))
        assert d["executed"] is False and d["reason"] == reason
        assert d["columns"] == [] and d["rows"] == [] and d["row_count"] == 0
    print("[4] all three failure reasons supported (enum) -> OK")


def test_inputs_copied():
    cols = ["a"]
    rows = [[1]]
    r = success_result(cols, rows)
    cols.append("b")          # mutating caller inputs must not affect the result
    rows.append([2])
    d = to_dict(r)
    assert d["columns"] == ["a"] and d["rows"] == [[1]] and d["row_count"] == 1
    print("[5] columns/rows copied, not aliased -> OK")


def test_defaults_and_constants():
    d = to_dict(success_result([], []))
    assert d["columns"] == [] and d["rows"] == [] and d["row_count"] == 0
    assert d["truncated"] is False and d["diagnostics"] == {}
    assert DEFAULT_ROW_LIMIT == 1000
    print("[6] empty defaults + DEFAULT_ROW_LIMIT == 1000 -> OK")


def main():
    tests = [
        test_success_constructor,
        test_truncated_flag,
        test_failure_constructor,
        test_all_failure_reasons,
        test_inputs_copied,
        test_defaults_and_constants,
    ]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed — execution_result.py verified")


if __name__ == "__main__":
    main()