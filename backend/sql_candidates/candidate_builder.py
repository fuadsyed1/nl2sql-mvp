"""
sql_candidates/candidate_builder.py

Run ONE extraction through the existing IR -> plan -> SQL -> execute pipeline
and package the outcome as a SqlCandidate. This adds no new SQL generation
logic: it reuses build_from_extraction / validate_ir / resolve_plan /
apply_left_join_for_each / generate_sql / execute_sql exactly as app.py does,
so every candidate is produced by the same trusted machinery.

A candidate NEVER raises: any pipeline failure is captured in .reasons /
.diagnostics and the candidate simply scores low.
"""

from semantic.ir_builder import build_from_extraction
from semantic.ir_validator import validate_ir
from semantic.semantic_ir import to_dict as ir_to_dict
from planning.plan_resolver import resolve_plan
from planning.plan_postprocess import apply_left_join_for_each
from planning.query_plan import to_dict as plan_to_dict
from generation.multitable_sql_generator import generate_sql
from generation.relational_algebra import to_relational_algebra
from generation.sql_types import to_dict as sql_to_dict
from generation.sql_executor import execute_sql
from generation.execution_result import to_dict as execution_to_dict

from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.name_normalizer import normalize_schema_prefixes

__all__ = ["build_candidate", "build_direct_sql_candidate"]

import sqlite3 as _sqlite3


def _physical_table_names(db_path):
    """Real table names in the SQLite file (read-only, empty on any problem)."""
    if not db_path:
        return []
    try:
        conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3.0)
    except _sqlite3.Error:
        return []
    try:
        return [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")]
    except _sqlite3.Error:
        return []
    finally:
        conn.close()


def build_direct_sql_candidate(*, label, sql, db_path, source="llm_sql_direct"):
    """Package a direct LLM-written SQL string as a candidate: execute it
    (read-only) and record the outcome. No IR, no plan — the scorer judges it
    purely on the SQL text, execution, and checklist alignment. Never raises.

    Before execution, hallucinated SQL-Server schema prefixes
    (`Purchasing.PurchaseOrderHeader`) are normalized to the flat physical name
    (`PurchaseOrderHeader`) when — and only when — the physical schema confirms
    the mapping, so a semantically-correct candidate is not lost to a bare
    qualification error."""
    sql = normalize_schema_prefixes(sql, _physical_table_names(db_path))
    cand = SqlCandidate(source=source, label=label,
                        sql=(sql or "").strip() or None)
    if not cand.sql:
        cand.diagnostics["stage"] = "no_sql"
        return cand
    try:
        generated = {"generated": True, "sql": cand.sql, "params": []}
        cand.generated_sql = generated
        cand.execution = execution_to_dict(execute_sql(generated, db_path))
        cand.diagnostics["stage"] = ("executed" if cand.executed_ok
                                     else "execution_failed")
    except Exception as exc:
        cand.diagnostics["stage"] = "pipeline_error"
        cand.diagnostics["pipeline_error"] = f"{type(exc).__name__}: {exc}"
    return cand


def build_candidate(
    *,
    source,
    label,
    question,
    database_id,
    extraction,
    graph,
    db_path,
    question_aware=True,
    family_info=None,
    ir_postprocess=None,
):
    """extraction -> IR -> validate -> plan -> SQL -> execute, as a candidate.

    question_aware=False reproduces the family path (the builder already
    produced the exact structure, so question-driven IR rewrites are skipped).
    ir_postprocess(ir) may mutate the IR (large-mode table fallback, partition
    filter) and return a diagnostics dict merged into candidate.diagnostics.
    """
    cand = SqlCandidate(source=source, label=label, extraction=extraction,
                        family_info=family_info)
    try:
        ir = build_from_extraction(
            database_id, extraction, graph,
            question=question if question_aware else None,
        )

        if ir_postprocess is not None:
            try:
                diag = ir_postprocess(ir)
                if isinstance(diag, dict):
                    cand.diagnostics.update(diag)
            except Exception as exc:
                cand.diagnostics["ir_postprocess_error"] = f"{type(exc).__name__}: {exc}"

        ir_validation = validate_ir(ir, graph)
        cand.ir = ir_to_dict(ir)
        cand.ir_validation = ir_validation
        if not ir_validation.get("valid"):
            cand.diagnostics["stage"] = "invalid_ir"
            return cand

        plan_obj = resolve_plan(ir, graph)
        apply_left_join_for_each(question, plan_obj)
        cand.plan = plan_to_dict(plan_obj)
        if not cand.plan.get("resolved"):
            cand.diagnostics["stage"] = "plan_unresolved"
            cand.diagnostics["plan_reason"] = cand.plan.get("reason")
            return cand

        generated = sql_to_dict(generate_sql(plan_obj))
        cand.generated_sql = generated
        if not generated.get("generated"):
            cand.diagnostics["stage"] = "sql_not_generated"
            cand.diagnostics["sql_reason"] = generated.get("reason")
            return cand

        cand.sql = generated.get("sql")
        cand.params = generated.get("params") or []
        cand.relational_algebra = to_relational_algebra(plan_obj)
        cand.execution = execution_to_dict(execute_sql(generated, db_path))
        cand.diagnostics["stage"] = "executed" if cand.executed_ok else "execution_failed"
        return cand
    except Exception as exc:
        cand.diagnostics["stage"] = "pipeline_error"
        cand.diagnostics["pipeline_error"] = f"{type(exc).__name__}: {exc}"
        return cand
