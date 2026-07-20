"""
final_evaluation/common/scoring.py

Execution-result scoring for the final NL-to-SQL benchmark.

Scores by RESULT, never by SQL text similarity. Four comparison modes:

  scalar        one row, one column; numeric tolerance applies
  ordered_rows  row values AND order must match
  multiset_rows order ignored, duplicate multiplicity preserved
  set_rows      order ignored, duplicates collapsed (question asks for a set)

Column ALIASES may differ; column COUNT may not (extra or missing output
columns are wrong). Normalization: NULL -> a stable marker; ints and equal
decimals unify; floats rounded into the configured tolerance; dates already
arrive as ISO text from SQLite; text is stripped of surrounding whitespace
but case/meaning are never changed.

Verdicts: correct | wrong_result | wrong_columns | execution_error |
controlled_failure | timeout | invalid_reference | manual_review_required.
"""

import hashlib
import json

_NULL = "∅"          # visible NULL marker; cannot collide with text
DEFAULT_TOLERANCE = 1e-6

VERDICTS = ("correct", "wrong_result", "wrong_columns", "execution_error",
            "controlled_failure", "timeout", "invalid_reference",
            "manual_review_required")


def normalize_value(v, tolerance=DEFAULT_TOLERANCE):
    if v is None:
        return _NULL
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        f = float(v)
        if f == int(f) and abs(f) < 1e15:
            return str(int(f))
        # bucket floats into tolerance-sized cells so 0.30000001 == 0.3
        digits = max(0, round(-1 * _log10(tolerance)))
        return f"{round(f, digits):.{digits}f}".rstrip("0").rstrip(".")
    s = str(v).strip()
    # numeric-looking text normalizes like a number ('42.0' == 42)
    try:
        return normalize_value(float(s), tolerance) if s and _numlike(s) else s
    except (ValueError, OverflowError):
        return s


def _numlike(s):
    t = s.lstrip("+-")
    return t.replace(".", "", 1).isdigit()


def _log10(x):
    import math
    return math.log10(x) if x > 0 else -6


def normalize_rows(rows, tolerance=DEFAULT_TOLERANCE):
    return [tuple(normalize_value(v, tolerance) for v in (row or []))
            for row in (rows or [])]


def result_hash(rows, mode="multiset_rows", tolerance=DEFAULT_TOLERANCE):
    """Stable SHA-256 of a normalized result under its comparison mode."""
    norm = normalize_rows(rows, tolerance)
    if mode == "ordered_rows":
        payload = list(norm)
    elif mode == "set_rows":
        payload = sorted(set(norm))
    else:                                # multiset_rows / scalar
        payload = sorted(norm)
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def compare_results(mode, expected_rows, actual_rows,
                    tolerance=DEFAULT_TOLERANCE):
    """(equal: bool, detail: str). Column-count mismatch is reported by the
    caller as wrong_columns before value comparison."""
    exp = normalize_rows(expected_rows, tolerance)
    act = normalize_rows(actual_rows, tolerance)
    if mode == "scalar":
        if len(exp) != 1 or len(exp[0]) != 1:
            return False, "reference is not scalar"
        if len(act) != 1 or len(act[0]) != 1:
            return False, f"expected one scalar, got {len(act)} row(s)"
        return (exp[0][0] == act[0][0],
                f"expected {exp[0][0]!r}, got {act[0][0]!r}")
    if mode == "ordered_rows":
        return (exp == act,
                f"{len(exp)} expected rows vs {len(act)} actual (ordered)")
    if mode == "set_rows":
        return (set(exp) == set(act),
                f"{len(set(exp))} expected distinct vs {len(set(act))} actual")
    # multiset_rows
    return (sorted(exp) == sorted(act),
            f"{len(exp)} expected rows vs {len(act)} actual (multiset)")


def classify(case, response, ref, timeout_hit=False,
             tolerance=DEFAULT_TOLERANCE):
    """Verdict for one benchmark case given the endpoint response and the
    stored reference. `ref` carries expected columns/rows; `case` carries
    comparison_mode."""
    if not ref or not ref.get("ok"):
        return "invalid_reference", "reference did not execute at build time"
    if timeout_hit:
        return "timeout", "endpoint call exceeded the timeout"
    if response is None:
        return "execution_error", "no response from endpoint"
    if response.get("error") == "no_semantically_valid_sql":
        return "controlled_failure", "pipeline returned controlled failure"
    if not response.get("success"):
        err = (response.get("execution") or {}).get("error") \
            or response.get("message") or "unknown"
        return "execution_error", f"pipeline failure: {err}"
    execution = response.get("execution") or {}
    actual_rows = execution.get("rows")
    actual_cols = execution.get("columns") or []
    if actual_rows is None:
        return "execution_error", "success without execution rows"
    exp_cols = ref.get("columns") or []
    if len(actual_cols) != len(exp_cols):
        return ("wrong_columns",
                f"expected {len(exp_cols)} column(s), got {len(actual_cols)}")
    if execution.get("truncated"):
        return "manual_review_required", "actual result was truncated"
    equal, detail = compare_results(case.get("comparison_mode",
                                             "multiset_rows"),
                                    ref.get("rows"), actual_rows, tolerance)
    return ("correct", detail) if equal else ("wrong_result", detail)
