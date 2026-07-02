"""
sql_candidates/result_equivalence.py

Execution-result equivalence for self-consistency voting.

Two candidates "agree" when their executed result sets are equivalent after
normalization (whitespace/case on strings, float rounding, row order). When
several independently-produced candidates return the same result set, the
odds that they are all wrong in the same way are low — so agreement is strong
evidence of correctness (CHESS/self-consistency style).

Two signatures are provided:
  * strict:  column order preserved, row order ignored
  * relaxed: values sorted within each row too (column order ignored) — used
             only as a fallback when strict grouping produces no agreement,
             since two SELECTs may emit the same data with columns swapped.

Pure functions only: no execution, no scoring, no selection policy.
"""

__all__ = ["result_signature", "group_candidates"]

_NULL = "∅"  # visible marker for NULL so it can't collide with "" or "None"


def _norm_value(v):
    if v is None:
        return _NULL
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        f = float(v)
        if f == int(f):
            return str(int(f))
        return f"{f:.6g}"
    return str(v).strip().lower()


def result_signature(execution: dict | None, relaxed: bool = False):
    """Hashable signature of an executed result set, or None if not executed.

    strict  : (n_cols, sorted rows, values in column order)
    relaxed : (n_cols, sorted rows, values sorted WITHIN each row)
    """
    if not execution or not execution.get("executed"):
        return None
    rows = execution.get("rows") or []
    columns = execution.get("columns") or []
    norm_rows = []
    for row in rows:
        vals = tuple(_norm_value(v) for v in row)
        if relaxed:
            vals = tuple(sorted(vals))
        norm_rows.append(vals)
    return (len(columns), tuple(sorted(norm_rows)))


def group_candidates(candidates):
    """Group executed candidates by result equivalence.

    Tries the strict signature first; when strict yields only singleton groups
    (no agreement) it retries with the relaxed signature. Returns a list of
    lists of candidates (only candidates whose execution succeeded), largest
    group first.
    """
    executed = [c for c in candidates if c.execution and c.execution.get("executed")]
    if not executed:
        return []

    def _group(relaxed):
        buckets = {}
        for c in executed:
            sig = result_signature(c.execution, relaxed=relaxed)
            buckets.setdefault(sig, []).append(c)
        return sorted(buckets.values(), key=len, reverse=True)

    groups = _group(relaxed=False)
    if groups and len(groups[0]) == 1 and len(executed) > 1:
        relaxed_groups = _group(relaxed=True)
        if relaxed_groups and len(relaxed_groups[0]) > 1:
            return relaxed_groups
    return groups
