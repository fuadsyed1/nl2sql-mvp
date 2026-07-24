"""
sql_candidates/set_fallback.py

Deterministic SET-UNION candidate fallback.

The selector and the either/or semantic obligation already prefer a correct
separable UNION when one exists — but sometimes the LLM emits ONLY intersection
candidates (INNER JOIN of the two sources) and the pool contains no valid set
candidate at all. For a high-confidence "identifiers appearing either in source
A or source B" request whose alternatives are unambiguously grounded and whose
output is just the shared identifier, we can synthesize the obviously-correct
UNION deterministically and drop it into the normal candidate pool.

    SELECT DISTINCT <col_A> AS <id> FROM <source_A> WHERE <col_A> IS NOT NULL
    UNION
    SELECT DISTINCT <col_B> AS <id> FROM <source_B> WHERE <col_B> IS NOT NULL

The synthesized SQL is returned as a plain string; the caller builds it through
the SAME direct-SQL path (parse -> validate -> execute -> score -> RC5 -> select)
as every other candidate, so it never bypasses selection.

Everything is schema-generic and driven by the existing role/either grounding
(`ground_either_roles`) plus the checklist. Nothing about any table, column,
identifier, database id, or test id is hardcoded. The function returns
(None, reason) whenever any eligibility condition is not met, so a query that is
not a clean either/or membership list is never touched.
"""
from sqlglot import parse_one

from sql_candidates.semantic_obligations import (
    ground_either_roles, role_either_satisfied,
    question_either_union_obligation, question_multi_source_either,
    _entity_id_from_checklist, _qnorm)

__all__ = ["synthesize_set_union"]

# Cues that mean INTERSECTION / conjunction rather than either-or union.
_INTERSECTION_CUES = (
    " both ", " in both ", " common to both ", " all of ", " as well as ",
    " intersection", " and also appear", " that also appear", " appear in all ",
    " present in both ", " and appear in ")
# Cues that the answer is an AGGREGATE / scalar rather than a list of ids.
_AGG_CUES = (" how many ", " number of ", " count of ", " count the ",
            " total number ", " average ", " sum of ", " percentage ")


def _is_id_like(name):
    n = (name or "").lower()
    return n.endswith("_id") or n == "id" or n.endswith("_key")


def synthesize_set_union(question, checklist, idx, existing_sqls):
    """Return (union_sql, meta) or (None, reason).

    meta = {"identifier": <alias>, "alternatives": [{table, column, provenance}],
            "reason": "..."} describing what was synthesized and why.
    """
    q = _qnorm(question)
    # (1) explicit either/or union membership semantics; not an intersection.
    if not (question_either_union_obligation(question)
            and question_multi_source_either(question)):
        return None, "not_a_multi_source_either_request"
    if any(c in q for c in _INTERSECTION_CUES):
        return None, "intersection_or_conjunction_semantics"
    # (7) aggregates requested -> the answer is a scalar, not an id list.
    if any(c in q for c in _AGG_CUES):
        return None, "aggregate_requested"
    cl = checklist or {}
    shape = str(cl.get("required_sql_shape") or "").lower()
    if shape in ("group_by_having", "aggregate", "count_distinct", "order_by_limit"):
        return None, f"shape_{shape}_not_a_plain_id_list"
    if cl.get("measure_column") or cl.get("grain_requirements"):
        return None, "measure_or_grain_requirement_present"

    # (2)/(7) unambiguous grounding of >= 2 source alternatives.
    grounded = ground_either_roles(question, checklist, idx)
    if not grounded or len(grounded) < 2:
        return None, "sources_not_unambiguously_grounded"

    # (3) the requested identifier alias; every output column must BE that id.
    _ent, idcol = _entity_id_from_checklist(checklist)
    out_cols = [str(c).split(".")[-1].strip().strip('"').lower()
                for c in (cl.get("output_columns") or [])]
    # (4) no source-specific attribute requested (only the identifier).
    non_id_outputs = [c for c in out_cols if not _is_id_like(c)]
    if non_id_outputs:
        return None, "source_attribute_requested"
    identifier = idcol or (out_cols[0] if out_cols else None)
    if not identifier or not _is_id_like(identifier):
        return None, "no_clear_identifier_output"

    # (5) branch-specific filters (literals / resolved categories) would need
    # more than 'IS NOT NULL' per branch -> do not use the simple fallback.
    if (cl.get("literals") or cl.get("required_literal_groups")):
        return None, "branch_specific_filters_present"

    # (6) an existing candidate already satisfies the set provenance obligation.
    for sql in existing_sqls or []:
        try:
            if role_either_satisfied(parse_one(sql, read="sqlite"), grounded):
                return None, "existing_candidate_already_satisfies_set"
        except Exception:
            continue

    # all columns must be mutually type-compatible (they are all identifiers, so
    # this holds by construction); build the separable UNION.
    branches = []
    alts = []
    for g in grounded:
        tbl, col = g["table"], g["column"]
        branch = (f"SELECT DISTINCT {col} AS {identifier} FROM {tbl} "
                  f"WHERE {col} IS NOT NULL")
        branches.append(branch)
        alts.append({"table": tbl, "column": col,
                     "provenance": g.get("provenance")})
    union_sql = "\nUNION\n".join(branches)
    # verify it parses.
    try:
        parse_one(union_sql, read="sqlite")
    except Exception as exc:  # pragma: no cover
        return None, f"synthesis_parse_error:{type(exc).__name__}"

    meta = {"identifier": identifier, "alternatives": alts,
            "reason": "no existing candidate satisfied the either/or set "
                      "provenance; synthesized a separable UNION over the "
                      "grounded source alternatives"}
    return union_sql, meta
