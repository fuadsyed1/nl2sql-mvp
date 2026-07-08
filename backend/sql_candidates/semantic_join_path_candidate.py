"""
sql_candidates/semantic_join_path_candidate.py

Phase 4 — one extra candidate source: "semantic_join_path".

Candidate GENERATION (not just scoring). The correct multi-hop path — e.g.
source -> bridge/mapping table -> geography/census table -> optional
demographic/ACS table — is often never produced by the direct LLM samples, so
the scorer never sees it. This module builds that path DETERMINISTICALLY from
tokens + trusted relationships (declared FK / confirmed / Phase 1 HoPF / Phase 3
bridge detection), then asks the LLM ONCE to write SQL constrained to exactly
that path (forbidding the known bad joins). If no SAFE path exists it returns
None — never a dummy/SELECT * fallback, never a fabricated bad join.

Generic only: no table, domain, or place name is hardcoded. Small-DB behavior is
unchanged because a candidate is produced only when a genuine bridge/mapping (or
a trusted multi-table) path is found.
"""

import re

from query_families.slot_extractor import index_schema
from sql_candidates.semantic_relationship_verifier import _rel_supported, _checklist_text
from sql_candidates.semantic_join_discovery import (
    _GEO, _BRIDGEABLE, _is_bridge_table, _ctoks, _big_toks,
    _table_all_tokens, _concepts_of, _PURPOSE, _BRIDGE_NAME_TOKENS,
)

__all__ = ["plan_semantic_join_path", "build_semantic_join_path_sql"]

# deterministic concept order (finer -> coarser): source concept first,
# target/geography concept second. Avoids frozenset hash-order flakiness.
_GEO_ORDER = {"zip": 0, "tract": 1, "county": 2, "state": 3}


# ---------------------------------------------------------------------------
# deterministic planner (pure — no LLM, unit-testable)
# ---------------------------------------------------------------------------
def _concept_col(idx, table, concept):
    for col in idx["tables"].get(table, []):
        if _ctoks(col.get("name")) & _GEO[concept]:
            return col["name"]
    return None


def _safe_edge(idx, t1, c1, t2, c2):
    """A join is safe only if it is a same-named key or a trusted relationship
    (declared FK / confirmed / high-confidence HoPF). Never a raw cross-concept
    guess — that is exactly the bad join Phase 4 must avoid."""
    if c1 == c2:
        return True
    return _rel_supported(idx, t1, c1, t2, c2)


def _family_tokens(idx):
    tok_tables = {}
    for t in idx["tables"]:
        for tok in _big_toks(t):
            tok_tables.setdefault(tok, set()).add(t)
    return {tok for tok, ts in tok_tables.items() if len(ts) >= 2}


def _pick_target(idx, concept, qtoks, exclude):
    """Choose the geography/census table for `concept`, honoring same-family
    disambiguation: prefer the sibling whose distinguishing token is in the
    question; if none matches and siblings are ambiguous, return None rather
    than guess the wrong state/region table."""
    cands = [t for t in idx["tables"]
             if t not in exclude and _concept_col(idx, t, concept)]
    if not cands:
        return None
    fam = _family_tokens(idx)
    matching = [t for t in cands if (_big_toks(t) - fam) & qtoks]
    if matching:
        return sorted(matching)[0]
    generic = [t for t in cands if not (_big_toks(t) - fam)]
    if generic:
        return sorted(generic)[0]
    if len(cands) == 1:
        return cands[0]
    return None                      # ambiguous same-family -> do not guess


def _pick_source(idx, concept, qpurpose, exclude):
    cands = [t for t in idx["tables"]
             if t not in exclude and _concept_col(idx, t, concept)]
    if not cands:
        return None
    if qpurpose:
        pref = [t for t in cands
                if _concepts_of(_table_all_tokens(idx, t), _PURPOSE) & qpurpose]
        if pref:
            return sorted(pref)[0]
    return sorted(cands)[0]


def _pick_bridge(idx, a, b):
    bridges = [t for t in idx["tables"] if _is_bridge_table(idx, t, a, b)]
    if not bridges:
        return None
    named = [t for t in bridges if _ctoks(t) & _BRIDGE_NAME_TOKENS]
    return sorted(named or bridges)[0]


def plan_semantic_join_path(question, checklist, idx):
    """Build a SAFE multi-hop plan, or None. Pure (no LLM).

    Returns {tables, join_edges:[(t1,c1,t2,c2)], forbidden:[...],
             grain, measure} where every join_edge is a same-named key or a
             trusted relationship."""
    if not idx or not idx.get("tables"):
        return None
    qtext = (question or "") + " " + _checklist_text(checklist)
    qtoks = _ctoks(qtext)
    qgeo = _concepts_of(qtoks, _GEO)
    qpurpose = _concepts_of(qtoks, _PURPOSE) - {"geography"}

    for pair in sorted(_BRIDGEABLE, key=lambda p: sorted(p)):
        a, b = sorted(pair, key=lambda x: _GEO_ORDER.get(x, 9))
        if not (a in qgeo and b in qgeo):
            continue
        bridge = _pick_bridge(idx, a, b)
        if not bridge:
            continue
        target = _pick_target(idx, b, qtoks, exclude={bridge})
        source = _pick_source(idx, a, qpurpose, exclude={bridge, target})
        if not (target and source) or len({source, bridge, target}) < 3:
            continue
        s_a = _concept_col(idx, source, a)
        b_a = _concept_col(idx, bridge, a)
        b_b = _concept_col(idx, bridge, b)
        t_b = _concept_col(idx, target, b)
        if not all((s_a, b_a, b_b, t_b)):
            continue
        e1 = (source, s_a, bridge, b_a)
        e2 = (bridge, b_b, target, t_b)
        if not (_safe_edge(idx, *e1) and _safe_edge(idx, *e2)):
            continue                     # would require a bad join -> skip
        grain = (checklist or {}).get("group_by_entity") or None
        if not grain:
            rgk = (checklist or {}).get("required_group_keys") or []
            grain = rgk[0] if rgk else None
        return {
            "tables": [source, bridge, target],
            "join_edges": [e1, e2],
            "forbidden": [f"{source}.{s_a} = {target}.{t_b} (direct {a}<->{b})",
                          f"substr()/expression joins on {a}/{b} ids"],
            "grain": grain,
            "measure": (checklist or {}).get("measure_column"),
        }
    return None


# ---------------------------------------------------------------------------
# constrained SQL generation (one LLM call)
# ---------------------------------------------------------------------------
def _tables_block(idx, tables):
    lines = []
    for t in tables:
        cols = ", ".join(c["name"] for c in idx["tables"].get(t, []))
        lines.append(f"- {t}({cols})")
    return "\n".join(lines)


def _path_prompt(question, checklist, value_hints, plan, idx):
    hints = f"{value_hints}\n\n" if value_hints else ""
    joins = "\n".join(
        f"  {t1}.{c1} = {t2}.{c2}" for (t1, c1, t2, c2) in plan["join_edges"])
    forbidden = "\n".join(f"  - {f}" for f in plan["forbidden"])
    cl = []
    if plan.get("measure"):
        cl.append(f"- measure: {plan['measure']}")
    if plan.get("grain"):
        cl.append(f"- group results per: {plan['grain']}")
    for k in ("comparison_logic", "required_sql_shape", "literals",
              "output_columns"):
        v = (checklist or {}).get(k)
        if v:
            cl.append(f"- {k}: {v}")
    cl_block = ("Requirements:\n" + "\n".join(cl) + "\n\n") if cl else ""
    return (
        "/no_think\n"
        "Write ONE SQLite query that answers the question by joining EXACTLY\n"
        "along the join path below. Output ONLY the SQL — no markdown, no\n"
        "explanation.\n\n"
        f"Tables:\n{_tables_block(idx, plan['tables'])}\n\n"
        f"Required join path (use these ON conditions, in this order):\n{joins}\n\n"
        f"FORBIDDEN — never do any of these:\n{forbidden}\n"
        "  - SELECT * ; a bare single-table scan; inventing columns.\n\n"
        f"{hints}{cl_block}"
        "Rules:\n"
        "- SQLite dialect; a single statement (WITH ... SELECT allowed).\n"
        "- Use only the tables/columns above and only the join path above.\n"
        "- Apply the required aggregation/grouping/filter the question needs.\n\n"
        f"Question: {question}\n"
        "SQL:"
    )


def build_semantic_join_path_sql(question, graph, checklist=None, value_hints=""):
    """Deterministic path plan + ONE constrained LLM call -> SQL string, or
    None (no safe path / any failure). Never raises."""
    try:
        idx = index_schema(graph)
        plan = plan_semantic_join_path(question, checklist, idx)
        if not plan:
            return None
        from llm import get_provider
        from semantic.llm_sql_direct import _clean_sql
        prompt = _path_prompt(question, checklist, value_hints, plan, idx)
        print("CALLING SEMANTIC JOIN PATH GENERATOR...", flush=True)
        result = get_provider().generate(
            prompt, options={"temperature": 0, "num_predict": 700,
                             "think": False})
        sql = _clean_sql((result.text or "").strip())
        print("SEMANTIC JOIN PATH SQL:", sql, flush=True)
        return sql
    except Exception as exc:
        print(f"SEMANTIC JOIN PATH ERROR: {exc}", flush=True)
        return None
