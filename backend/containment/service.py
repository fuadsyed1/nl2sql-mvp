"""
containment/service.py

Orchestration for Natural-Language Query Containment Checking.

The service is deliberately decoupled from app.py: it receives the shared
`run_nl_sql_pipeline` callable (dependency injection) instead of importing it,
which avoids a circular import and keeps this module unit-testable with a stub
pipeline. It does NOT re-implement any SQL generation — it projects the
pipeline's output, applies the safety gate, and (Step 2) runs a live-database
EXCEPT containment check via containment.checker.
"""

from collections import defaultdict  # noqa
from typing import Callable

from .models import (
    ContainmentRequest,
    ContainmentQueryResult,
    ContainmentResponse,
    ContainmentBatchRequest,
    BatchQueryResult,
    PairwiseRelationship,
    QuerySummary,
    ContainmentBatchResponse,
    ContainmentAnalysis,
    MainQuery,
    ContainmentEdge,
    UnknownPair,
    IncomparablePair,
)
from . import checker

# Type of the injected pipeline: (database_id, question) -> execute_sql-shaped dict
PipelineFn = Callable[[int, str], dict]

_LIMITATIONS = (
    "Live-database check only. 'not_contained' is backed by a real counterexample, "
    "but 'contained_on_current_database' / 'equivalent_on_current_database' hold only "
    "for the rows currently in this database - they are not a general or symbolic proof. "
    "Randomized test databases and symbolic proof are planned for later steps."
)


def _project_query_result(question: str, pipeline_result: dict | None) -> ContainmentQueryResult:
    """Project one execute_sql-shaped pipeline dict down to a
    ContainmentQueryResult. Every field is read defensively so early-return
    pipeline shapes (db-not-found, no candidates, ambiguity) never raise."""
    result = pipeline_result or {}

    generated_sql = result.get("generated_sql") or {}
    sql = generated_sql.get("sql") if isinstance(generated_sql, dict) else None
    sql = (sql or "").strip() or None

    execution = result.get("execution") or {}
    columns = execution.get("columns") or []
    row_count = execution.get("row_count")
    if row_count is None:
        row_count = len(execution.get("rows") or [])

    params = generated_sql.get("params") if isinstance(generated_sql, dict) else None

    score = result.get("selected_candidate_score")
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None

    # A fatal validation item on the selected candidate blocks the check.
    validation = result.get("selected_candidate_validation") or {}
    has_fatal = bool(isinstance(validation, dict) and validation.get("fatal"))

    return ContainmentQueryResult(
        question=question,
        success=bool(result.get("success")),
        sql=sql,
        params=list(params or []),
        selected_candidate_source=result.get("selected_candidate_source"),
        selected_candidate_score=score,
        low_confidence=bool(result.get("low_confidence", False)),
        has_fatal_validation=has_fatal,
        warnings=list(result.get("warnings") or []),
        execution_columns=[str(c) for c in columns],
        row_count=int(row_count or 0),
    )


def _safety_reasons(q1: ContainmentQueryResult, q2: ContainmentQueryResult) -> list[str]:
    """First-step safety gate. Returns the reasons containment cannot be safely
    attempted yet. An empty list means both SQLs are clearly safe."""
    reasons: list[str] = []

    for label, q in (("query1", q1), ("query2", q2)):
        if not q.sql:
            reasons.append(f"{label} produced no SQL text")
            continue  # nothing more to say about an empty query
        if not q.success:
            reasons.append(f"{label} SQL failed validation or execution")
        if q.low_confidence:
            reasons.append(f"{label} SQL was generated with low confidence")
        if q.has_fatal_validation:
            reasons.append(f"{label} SQL has fatal validation items")
        shape = checker.unsupported_shape(q.sql)
        if shape:
            reasons.append(f"{label} {shape}")

    # Output columns must line up (same names, same count) for a containment
    # comparison to be meaningful.
    if q1.sql and q2.sql and q1.execution_columns != q2.execution_columns:
        if len(q1.execution_columns) != len(q2.execution_columns):
            reasons.append(
                "the two queries return a different number of output columns "
                f"({len(q1.execution_columns)} vs {len(q2.execution_columns)})"
            )
        else:
            reasons.append(
                "the two queries return different output columns "
                f"({q1.execution_columns} vs {q2.execution_columns})"
            )

    return reasons


def check_containment(
    database_id: int,
    request: ContainmentRequest,
    pipeline_fn: PipelineFn,
) -> ContainmentResponse:
    """Run the shared NL->SQL pipeline for both questions, project the results,
    apply the safety gate, and — when both SQLs are safe — run a live-database
    EXCEPT containment check.

    Verdicts: "contained_on_current_database", "equivalent_on_current_database",
    "not_contained" (with counterexample rows), or "unknown" (gate blocked or
    the EXCEPT errored). Never claims a general/symbolic proof.
    """
    raw1 = pipeline_fn(database_id, request.query1)
    raw2 = pipeline_fn(database_id, request.query2)

    q1 = _project_query_result(request.query1, raw1)
    q2 = _project_query_result(request.query2, raw2)

    reasons = _safety_reasons(q1, q2)

    # Surface per-query pipeline warnings at the top level, tagged by query.
    warnings = [f"query1: {w}" for w in q1.warnings] + [f"query2: {w}" for w in q2.warnings]

    def _respond(containment_result, explanation, **extra):
        return ContainmentResponse(
            success=bool(q1.success and q2.success),
            database_id=database_id,
            query1_result=q1,
            query2_result=q2,
            containment_result=containment_result,
            explanation=explanation,
            warnings=warnings,
            **extra,
        )

    # -- Safety gate: never guess. ------------------------------------------
    if reasons:
        return _respond(
            "unknown",
            "Containment cannot be safely checked because "
            + "; ".join(reasons)
            + ". Returning 'unknown' instead of guessing.",
        )

    # -- Live-database EXCEPT check. ----------------------------------------
    live = checker.check_live_containment(
        database_id, q1.sql, q1.params, q2.sql, q2.params
    )

    if not live.get("ran"):
        # The EXCEPT itself could not run — do not guess a verdict.
        return _respond(
            "unknown",
            "Both SQLs were generated, but the EXCEPT containment check could not "
            f"run on the current database ({live.get('error')}). Returning 'unknown'.",
            checked_on_current_database=False,
            limitations=_LIMITATIONS,
        )

    columns = [str(c) for c in live.get("columns") or []]
    forward = live.get("forward_rows") or []
    reverse = live.get("reverse_rows") or []
    trunc_note = ""
    if live.get("forward_truncated") or live.get("reverse_truncated"):
        trunc_note = (
            f" (counterexample rows shown are capped at {checker.COUNTEREXAMPLE_ROW_LIMIT})"
        )

    if not forward and not reverse:
        containment_result = "equivalent_on_current_database"
        explanation = (
            "Neither query returned any row the other was missing on the current "
            "database, so the two queries are equivalent on the current database."
        )
    elif not forward:
        containment_result = "contained_on_current_database"
        explanation = (
            "No rows from Query 1 were missing from Query 2 on the current database."
        )
    else:
        containment_result = "not_contained"
        explanation = "These rows appear in Query 1 but not in Query 2." + trunc_note

    return _respond(
        containment_result,
        explanation,
        counterexample_columns=columns,
        counterexample_rows=forward,
        reverse_counterexample_rows=reverse,
        checked_on_current_database=True,
        proof_type="live_database_except",
        limitations=_LIMITATIONS,
    )


# ---------------------------------------------------------------------------
# Batch containment: N queries, every safe pair compared in both directions.
# ---------------------------------------------------------------------------

_BATCH_LIMITATIONS = (
    "Live-database check only. Not-contained and incomparable results are backed by "
    "counterexample rows. Contained/equivalent results are only verified on the current "
    "database, not as full symbolic proofs."
)


def _single_query_safety_reason(q: ContainmentQueryResult) -> str | None:
    """Per-query safety gate (same rules as the pairwise gate, applied once).
    Returns None when the query is safe to compare, else a human reason."""
    if not q.sql:
        return "no SQL text was generated"
    if not q.success:
        return "SQL failed validation or execution"
    if q.low_confidence:
        return "SQL was generated with low confidence"
    if q.has_fatal_validation:
        return "SQL has fatal validation items"
    shape = checker.unsupported_shape(q.sql)
    if shape:
        return shape
    return None


def _project_batch_query_result(query_id, question, pipeline_result) -> BatchQueryResult:
    b = _project_query_result(question, pipeline_result)
    reason = _single_query_safety_reason(b)
    return BatchQueryResult(
        query_id=query_id,
        question=b.question,
        success=b.success,
        sql=b.sql,
        params=b.params,
        selected_candidate_source=b.selected_candidate_source,
        selected_candidate_score=b.selected_candidate_score,
        low_confidence=b.low_confidence,
        has_fatal_validation=b.has_fatal_validation,
        warnings=b.warnings,
        execution_columns=b.execution_columns,
        row_count=b.row_count,
        empty_result=bool(b.success and b.sql and b.row_count == 0),
        safe=(reason is None),
        safety_reason=reason,
    )


def _verdict_from_live(a, b, live, compared_on):
    """Turn a live EXCEPT result into a 5-tuple
    (relationship, explanation, a_minus_b_rows, b_minus_a_rows, compared_on)."""
    a_minus_b = live.get("forward_rows") or []   # rows in A missing from B
    b_minus_a = live.get("reverse_rows") or []   # rows in B missing from A
    a_in_b = len(a_minus_b) == 0
    b_in_a = len(b_minus_a) == 0

    suffix = ""
    if compared_on and compared_on.startswith("canonical_key:"):
        suffix = f" (compared on canonical key {compared_on.split(':', 1)[1]})"
    elif compared_on and compared_on.startswith("group_key:"):
        suffix = f" (compared on group key {compared_on.split(':', 1)[1]})"
    elif compared_on and compared_on.startswith("group_keys:"):
        suffix = f" (compared on group keys {compared_on.split(':', 1)[1]})"
    elif compared_on and compared_on.startswith("distinct_key:"):
        suffix = f" (compared on distinct key {compared_on.split(':', 1)[1]})"
    elif compared_on and compared_on.startswith("distinct_keys:"):
        suffix = f" (compared on distinct keys {compared_on.split(':', 1)[1]})"

    if a_in_b and b_in_a:
        return ("equivalent_on_current_database",
                f"Query {a} and Query {b} are equivalent on the current database.{suffix}",
                a_minus_b, b_minus_a, compared_on)
    if a_in_b:
        return ("query_a_contained_in_query_b",
                f"Query {a} is contained in Query {b} on the current database.{suffix}",
                a_minus_b, b_minus_a, compared_on)
    if b_in_a:
        return ("query_b_contained_in_query_a",
                f"Query {b} is contained in Query {a} on the current database.{suffix}",
                a_minus_b, b_minus_a, compared_on)
    return ("incomparable_on_current_database",
            f"Query {a} and Query {b} are incomparable on the current database; "
            f"each returned rows missing from the other.{suffix}",
            a_minus_b, b_minus_a, compared_on)


def _classify_grouped(database_id, qa: BatchQueryResult, qb: BatchQueryResult):
    """Step 2: compare two GROUP BY queries on their group keys only. Returns the
    same 5-tuple shape as _classify_pair. Aggregate values are never compared."""
    a, b = qa.query_id, qb.query_id
    ga = checker.build_group_key_comparison(database_id, qa.sql, qa.execution_columns)
    gb = checker.build_group_key_comparison(database_id, qb.sql, qb.execution_columns)

    if not ga.get("ok") or not gb.get("ok"):
        reasons = []
        if not ga.get("ok"):
            reasons.append(f"Query {a} ({ga.get('reason')})")
        if not gb.get("ok"):
            reasons.append(f"Query {b} ({gb.get('reason')})")
        return "unknown", f"Cannot compare grouped queries: {'; '.join(reasons)}.", [], [], None

    # Choose the comparison basis: a shared single canonical group key if both
    # grouped on one, otherwise the full group-key set (bare names must match).
    # The comparison SQL REWRITES the projection to the GROUP BY expression(s),
    # so the group key need not appear in the query's output.
    if ga["canonical_key"] and gb["canonical_key"] and ga["canonical_key"] == gb["canonical_key"]:
        exprs_a = [ga["canonical_expr"]]
        exprs_b = [gb["canonical_expr"]]
        label = f"group_key:{ga['canonical_key']}"
    else:
        set_a = sorted(ga["group_key_bare"])
        set_b = sorted(gb["group_key_bare"])
        if set_a != set_b:
            return ("unknown",
                    f"Cannot compare grouped queries: different group keys "
                    f"({ga['group_key_bare']} vs {gb['group_key_bare']}).",
                    [], [], None)
        order = set_a  # aligned bare-name order for both sides
        a_by = {b: e for b, e in zip(ga["group_key_bare"], ga["group_key_exprs"])}
        b_by = {b: e for b, e in zip(gb["group_key_bare"], gb["group_key_exprs"])}
        exprs_a = [a_by[name] for name in order]
        exprs_b = [b_by[name] for name in order]
        label = f"group_keys:{','.join(order)}"

    comp_a = checker._project_replace(ga["clean_sql"], ", ".join(exprs_a))
    comp_b = checker._project_replace(gb["clean_sql"], ", ".join(exprs_b))
    if not comp_a or not comp_b:
        return ("unknown",
                "Cannot compare grouped queries: projection could not be rewritten "
                "to the group key.", [], [], None)
    live = checker.check_live_containment(
        database_id, comp_a, qa.params, comp_b, qb.params
    )
    if not live.get("ran"):
        return ("unknown",
                f"Cannot compare: grouped-key comparison could not run ({live.get('error')}).",
                [], [], None)
    return _verdict_from_live(a, b, live, label)


def _classify_distinct(database_id, qa: BatchQueryResult, qb: BatchQueryResult):
    """Step 3: compare two SELECT DISTINCT queries on their distinct key set.
    Returns the same 5-tuple shape as _classify_pair."""
    a, b = qa.query_id, qb.query_id
    da = checker.build_distinct_key_comparison(database_id, qa.sql, qa.execution_columns)
    dbb = checker.build_distinct_key_comparison(database_id, qb.sql, qb.execution_columns)

    if not da.get("ok") or not dbb.get("ok"):
        reasons = []
        if not da.get("ok"):
            reasons.append(f"Query {a} ({da.get('reason')})")
        if not dbb.get("ok"):
            reasons.append(f"Query {b} ({dbb.get('reason')})")
        return "unknown", f"Cannot compare DISTINCT queries: {'; '.join(reasons)}.", [], [], None

    # Prefer a shared canonical key; otherwise require the exact same selected
    # (distinct) column set so different-entity DISTINCTs are not compared.
    if da["canonical_key"] and dbb["canonical_key"] and da["canonical_key"] == dbb["canonical_key"]:
        cols_a = [da["canonical_col"]]
        cols_b = [dbb["canonical_col"]]
        label = f"distinct_key:{da['canonical_key']}"
    else:
        set_a = sorted(c.lower() for c in da["distinct_key_cols"])
        set_b = sorted(c.lower() for c in dbb["distinct_key_cols"])
        if set_a != set_b:
            return ("unknown",
                    f"Cannot compare DISTINCT queries: different selected columns "
                    f"({da['distinct_key_cols']} vs {dbb['distinct_key_cols']}).",
                    [], [], None)
        order = sorted(da["distinct_key_cols"], key=lambda c: c.lower())
        b_by_lower = {c.lower(): c for c in dbb["distinct_key_cols"]}
        cols_a = order
        cols_b = [b_by_lower[c.lower()] for c in order]
        label = f"distinct_keys:{','.join(c.lower() for c in order)}"

    comp_a = f"SELECT {', '.join(cols_a)} FROM (\n{da['clean_sql']}\n) AS __d"
    comp_b = f"SELECT {', '.join(cols_b)} FROM (\n{dbb['clean_sql']}\n) AS __d"
    live = checker.check_live_containment(
        database_id, comp_a, qa.params, comp_b, qb.params
    )
    if not live.get("ran"):
        return ("unknown",
                f"Cannot compare: DISTINCT-key comparison could not run ({live.get('error')}).",
                [], [], None)
    return _verdict_from_live(a, b, live, label)


def _classify_pair(database_id, qa: BatchQueryResult, qb: BatchQueryResult):
    """Compare two queries both ways. Returns 5-tuple
    (relationship, explanation, a_minus_b_rows, b_minus_a_rows, compared_on)."""
    a, b = qa.query_id, qb.query_id

    if not qa.safe or not qb.safe:
        why = []
        if not qa.safe:
            why.append(f"Query {a} ({qa.safety_reason})")
        if not qb.safe:
            why.append(f"Query {b} ({qb.safety_reason})")
        return "unknown", f"Cannot compare: {'; '.join(why)}.", [], [], None

    # Step 4: centralized safe refusals (set operations, LIMIT/top-k, scalar
    # aggregate outputs) for EITHER query — deterministic reasons, checked
    # before any Step 1-3 normalization is attempted.
    for qid, q in ((a, qa), (b, qb)):
        shape = checker.unsupported_containment_shape(q.sql)
        if shape:
            return "unknown", f"Cannot compare: Query {qid} ({shape}).", [], [], None

    # Step 2: both queries are GROUP BY / aggregate — compare on GROUP KEYS only
    # (never aggregate values). This must run before the column checks below so
    # that grouped queries with identical columns still compare keys, not counts.
    if checker.is_group_by(qa.sql) and checker.is_group_by(qb.sql):
        return _classify_grouped(database_id, qa, qb)

    # Step 3: both queries are SELECT DISTINCT — compare the distinct key set
    # only (a shared canonical key, or the exact same selected columns). Runs
    # before the column checks so canonical-key DISTINCTs with different
    # descriptive columns still line up.
    if checker.is_distinct(qa.sql) and checker.is_distinct(qb.sql):
        return _classify_distinct(database_id, qa, qb)

    # Matching output columns: compare full tuples exactly as before (unchanged).
    if qa.execution_columns == qb.execution_columns:
        live = checker.check_live_containment(
            database_id, qa.sql, qa.params, qb.sql, qb.params
        )
        if not live.get("ran"):
            return ("unknown",
                    f"Comparison could not run on the current database ({live.get('error')}).",
                    [], [], None)
        return _verdict_from_live(a, b, live, "output_columns")

    # -- Step 1: output columns differ. Try a canonical-key projection so
    #    same-entity queries (key+name vs name) can still be compared. --------
    ca = checker.build_key_comparison(database_id, qa.sql, qa.execution_columns)
    cb = checker.build_key_comparison(database_id, qb.sql, qb.execution_columns)

    if ca.get("ok") and cb.get("ok") and ca["key"] == cb["key"]:
        live = checker.check_live_containment(
            database_id, ca["comparison_sql"], qa.params, cb["comparison_sql"], qb.params
        )
        if not live.get("ran"):
            return ("unknown",
                    f"Cannot compare: canonical-key comparison could not run "
                    f"({live.get('error')}).",
                    [], [], None)
        return _verdict_from_live(a, b, live, f"canonical_key:{ca['key']}")

    # -- Could not normalize: explain why, still return unknown. --------------
    reasons = []
    if not ca.get("ok"):
        reasons.append(f"Query {a} ({ca.get('reason')})")
    if not cb.get("ok"):
        reasons.append(f"Query {b} ({cb.get('reason')})")
    if ca.get("ok") and cb.get("ok") and ca["key"] != cb["key"]:
        reasons.append(
            f"{checker.REASON_NO_COMMON_KEY} (key {ca['key']} vs {cb['key']})")
    detail = "; ".join(reasons) if reasons else (
        f"different output columns ({qa.execution_columns} vs {qb.execution_columns})")
    return "unknown", f"Cannot compare: {detail}.", [], [], None


def _build_analysis(results, pairwise) -> ContainmentAnalysis:
    """Step 5: derive a batch-level hierarchy from the pairwise relationships.
    Only proven relationships create edges/groups; unknown pairs never do.
    Empty-result queries are tracked but never promoted to a 'main' query."""
    ids = [q.query_id for q in results]
    empty = {q.query_id for q in results if q.empty_result}

    # Union-find over equivalence edges.
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    edges = []          # (superset, subset)
    incomparable = []   # (a, b)
    unknown = []        # (a, b, reason)
    for p in pairwise:
        a, b, rel = p.query_a, p.query_b, p.relationship
        if rel == "equivalent_on_current_database":
            union(a, b)
        elif rel == "query_a_contained_in_query_b":
            edges.append((b, a))   # b is superset, a is subset
        elif rel == "query_b_contained_in_query_a":
            edges.append((a, b))
        elif rel == "incomparable_on_current_database":
            incomparable.append((a, b))
        else:  # unknown
            unknown.append((a, b, p.explanation))

    groups = defaultdict(list)
    for i in ids:
        groups[find(i)].append(i)
    equivalent_groups = sorted(
        (sorted(g) for g in groups.values() if len(g) > 1), key=lambda g: g[0])

    succ = defaultdict(set)          # superset -> direct subsets
    contained_by = defaultdict(set)  # subset -> supersets
    for sup, sub in edges:
        succ[sup].add(sub)
        contained_by[sub].add(sup)

    def reachable(x):
        seen, stack = set(), list(succ[x])
        while stack:
            y = stack.pop()
            if y not in seen:
                seen.add(y)
                stack.extend(succ[y])
        return seen

    def is_maximal(i):
        # Not contained by any query outside its own equivalence class.
        return all(find(sup) == find(i) for sup in contained_by[i])

    main_queries = []
    seen_groups = set()
    for i in sorted(ids):
        if i in empty or not is_maximal(i):
            continue
        g = find(i)
        if g in seen_groups:
            continue
        seen_groups.add(g)
        main_queries.append({
            "index": i,
            "equivalent_to": sorted(j for j in ids if j != i and find(j) == g),
            "contains": sorted(reachable(i)),
            "contained_by": sorted(contained_by[i]),
        })

    in_edge = {x for e in edges for x in e}
    in_equiv = {i for g in equivalent_groups for i in g}
    independent = sorted(i for i in ids if i not in in_edge and i not in in_equiv)

    unknown_pairs = [{"left": a, "right": b, "reason": r} for a, b, r in unknown]
    incomparable_pairs = [{"left": a, "right": b} for a, b in incomparable]
    containment_edges = [
        {"superset": s, "subset": b, "relationship_source": "pairwise"}
        for s, b in edges
    ]
    empty_queries = sorted(empty)
    summary_text = _analysis_summary(
        main_queries, equivalent_groups, independent, empty_queries,
        incomparable_pairs, unknown_pairs)

    return ContainmentAnalysis(
        query_count=len(ids),
        main_queries=[MainQuery(**m) for m in main_queries],
        equivalent_groups=equivalent_groups,
        containment_edges=[ContainmentEdge(**e) for e in containment_edges],
        independent_queries=independent,
        unknown_pairs=[UnknownPair(**u) for u in unknown_pairs],
        incomparable_pairs=[IncomparablePair(**p) for p in incomparable_pairs],
        empty_queries=empty_queries,
        summary_text=summary_text,
    )


def _analysis_summary(main_queries, equivalent_groups, independent,
                      empty_queries, incomparable_pairs, unknown_pairs) -> str:
    qlist = lambda xs: ", ".join(f"Query {i}" for i in xs)
    parts = []
    if main_queries:
        for m in main_queries:
            s = f"Query {m['index']} is a main (broadest) query"
            if m["contains"]:
                s += f"; it contains {qlist(m['contains'])}"
            if m["equivalent_to"]:
                s += f" (equivalent to {qlist(m['equivalent_to'])})"
            parts.append(s + ".")
    else:
        parts.append("No main query could be identified.")
    for g in equivalent_groups:
        parts.append(f"{qlist(g)} are equivalent on the current database.")
    if independent:
        parts.append(f"Independent (no proven containment): {qlist(independent)}.")
    if empty_queries:
        parts.append(f"Empty-result queries: {qlist(empty_queries)}.")
    if incomparable_pairs:
        pairs = "; ".join(
            f"Query {p['left']} vs Query {p['right']}" for p in incomparable_pairs)
        parts.append(f"Incomparable: {pairs}.")
    if unknown_pairs:
        parts.append(f"{len(unknown_pairs)} pair(s) could not be compared (unknown).")
    return " ".join(parts)


def _summary_status(q, contained_in, contains, equivalent_to, incomparable_with) -> str:
    if not q.safe:
        return "excluded_unsafe"
    if q.empty_result:
        return "empty_result_query"
    if contains and contained_in:
        return "broader_and_narrower"
    if contains:
        return "broader_query_for_some_queries"
    if contained_in:
        return "narrower_query"
    if equivalent_to:
        return "equivalent_to_some"
    if incomparable_with:
        return "incomparable_with_all_tested"
    return "no_containment_relationship"


def check_containment_batch(
    database_id: int,
    request: ContainmentBatchRequest,
    pipeline_fn: PipelineFn,
) -> ContainmentBatchResponse:
    """Generate SQL for every question, then compare every safe pair in both
    directions with live-database EXCEPT. Produces pairwise relationships and a
    per-query rollup (contained_in / contains / equivalent_to / incomparable_with /
    unknown_with) without declaring any single 'main' query."""
    questions = [(q or "").strip() for q in (request.queries or [])]
    questions = [q for q in questions if q]

    if len(questions) < 2:
        return ContainmentBatchResponse(
            success=False,
            database_id=database_id,
            warnings=["Provide at least two non-empty queries, one per line."],
            limitations=_BATCH_LIMITATIONS,
        )

    results = [
        _project_batch_query_result(i, q, pipeline_fn(database_id, q))
        for i, q in enumerate(questions, start=1)
    ]

    contained_in = defaultdict(set)
    contains = defaultdict(set)
    equivalent_to = defaultdict(set)
    incomparable_with = defaultdict(set)
    unknown_with = defaultdict(set)

    pairwise = []
    n = len(results)
    for ia in range(n):
        for ib in range(ia + 1, n):
            qa, qb = results[ia], results[ib]
            a, b = qa.query_id, qb.query_id
            rel, expl, amb, bma, compared_on = _classify_pair(database_id, qa, qb)
            pairwise.append(
                PairwiseRelationship(
                    query_a=a,
                    query_b=b,
                    compared_on=compared_on,
                    relationship=rel,
                    explanation=expl,
                    a_minus_b_rows=amb,
                    b_minus_a_rows=bma,
                )
            )
            if rel == "equivalent_on_current_database":
                equivalent_to[a].add(b)
                equivalent_to[b].add(a)
            elif rel == "query_a_contained_in_query_b":
                contained_in[a].add(b)
                contains[b].add(a)
            elif rel == "query_b_contained_in_query_a":
                contained_in[b].add(a)
                contains[a].add(b)
            elif rel == "incomparable_on_current_database":
                incomparable_with[a].add(b)
                incomparable_with[b].add(a)
            else:  # unknown
                unknown_with[a].add(b)
                unknown_with[b].add(a)

    summaries = []
    for q in results:
        i = q.query_id
        ci = sorted(contained_in[i])
        cs = sorted(contains[i])
        eq = sorted(equivalent_to[i])
        inc = sorted(incomparable_with[i])
        unk = sorted(unknown_with[i])
        summaries.append(
            QuerySummary(
                query_id=i,
                contained_in=ci,
                contains=cs,
                equivalent_to=eq,
                incomparable_with=inc,
                unknown_with=unk,
                status=_summary_status(q, ci, cs, eq, inc),
                empty_result=q.empty_result,
            )
        )

    analysis = _build_analysis(results, pairwise)

    return ContainmentBatchResponse(
        success=True,
        database_id=database_id,
        query_results=results,
        pairwise_relationships=pairwise,
        query_summaries=summaries,
        analysis=analysis,
        checked_on_current_database=True,
        proof_type="live_database_except_pairwise",
        limitations=_BATCH_LIMITATIONS,
        warnings=[],
    )
