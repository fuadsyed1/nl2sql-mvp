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

from collections import defaultdict
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
            f"different answer entities (key {ca['key']} vs {cb['key']})")
    detail = "; ".join(reasons) if reasons else (
        f"different output columns ({qa.execution_columns} vs {qb.execution_columns})")
    return "unknown", f"Cannot compare: {detail}.", [], [], None


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

    return ContainmentBatchResponse(
        success=True,
        database_id=database_id,
        query_results=results,
        pairwise_relationships=pairwise,
        query_summaries=summaries,
        checked_on_current_database=True,
        proof_type="live_database_except_pairwise",
        limitations=_BATCH_LIMITATIONS,
        warnings=[],
    )
