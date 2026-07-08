"""
semantic/llm_sql_repair.py

One-shot SQL repair (candidate source "llm_sql_repair").

After normal selection, when the winner looks unreliable (fatal, low score,
missing concepts, empty result, or a weak family pick while direct SQL
exists), ONE additional LLM call is made. The model sees the question, the
schema, the value hints, the semantic checklist, the selected SQL, and every
candidate's diagnostics (scores, errors, fatal reasons), and returns a
corrected SQLite query. The repaired SQL is packaged as a normal candidate,
scored like every other candidate, and selection re-runs once. Exactly one
round — never a loop.
"""

from llm import get_provider
from llm.errors import ProviderError
from semantic.llm_sql_direct import (
    _relevant_tables,
    _schema_blocks,
    _checklist_block,
    _clean_sql,
)

__all__ = ["should_repair", "generate_repair_sql", "SCORE_TRIGGER"]

SCORE_TRIGGER = 75.0


def _fatal(c):
    return bool((c.validation or {}).get("fatal"))


def should_repair(selected, candidates, checklist):
    """(bool, [trigger reasons]) — whether the one repair round should run."""
    triggers = []
    if selected is None:
        return True, ["no candidate selected"]
    val = selected.validation or {}
    if val.get("fatal"):
        triggers.append("selected candidate failed hard semantic checks")
    if not selected.executed_ok:
        triggers.append("selected SQL did not execute")
    if selected.score < SCORE_TRIGGER:
        triggers.append(f"selected score {selected.score} < {SCORE_TRIGGER}")
    cl_checks = val.get("checklist") or {}
    if cl_checks.get("missing_columns") or val.get("missing_concepts"):
        triggers.append("selected SQL is missing required concepts/columns")
    if val.get("unseen_literals"):
        triggers.append("selected SQL uses literals not seen in the sampled data")
    if selected.executed_ok and (selected.row_count or 0) == 0:
        triggers.append("selected returned zero rows (weak signal)")
    directs = [c for c in candidates if c.source == "llm_sql_direct"]
    if selected.source == "query_family" and any(not _fatal(c) for c in directs):
        triggers.append("query_family selected while a non-fatal direct SQL exists")
    return bool(triggers), triggers


def _issues_block(selected, candidates):
    """Compact diagnostics: the selected SQL's problems + every candidate."""
    lines = []
    if selected is not None:
        lines.append("Previously selected SQL (source "
                     f"{selected.source}, score {selected.score}):")
        lines.append(selected.sql or "(no SQL was produced)")
        val = selected.validation or {}
        for r in (val.get("fatal") or [])[:3]:
            lines.append(f"- FATAL: {r}")
        err = (selected.execution or {}).get("error")
        if err:
            lines.append(f"- execution error: {err}")
        if selected.executed_ok and (selected.row_count or 0) == 0:
            lines.append("- executed but returned ZERO rows")
        for r in (selected.reasons or [])[:4]:
            lines.append(f"- issue: {r}")
        mc = (val.get("checklist") or {}).get("missing_columns") or []
        if mc:
            lines.append(f"- missing required columns: {mc}")
    lines.append("")
    lines.append("All candidate attempts:")
    for c in candidates[:5]:
        err = (c.execution or {}).get("error") if c.execution else None
        fatal = (c.validation or {}).get("fatal") or []
        lines.append(f"- {c.label}: score={c.score} executed={c.executed_ok} "
                     f"rows={c.row_count}"
                     + (f" error={err}" if err else "")
                     + (f" fatal={fatal[:2]}" if fatal else ""))
        for r in (c.reasons or [])[:2]:
            lines.append(f"    issue: {r}")
    return "\n".join(lines)


def _repair_prompt(question, tables_block, fk_block, value_hints, checklist,
                   issues_block):
    hints = f"{value_hints}\n\n" if value_hints else ""
    return (
        "/no_think\n"
        "You are fixing a wrong SQL query. Write ONE corrected SQLite query\n"
        "that answers the question. Output ONLY the SQL statement — no\n"
        "markdown, no code fences, no explanation.\n\n"
        f"Tables:\n{tables_block}\n\n"
        f"Valid join edges (join ONLY along these, or self-joins):\n{fk_block}\n\n"
        f"{hints}"
        f"{_checklist_block(checklist)}"
        f"{issues_block}\n\n"
        "Rules:\n"
        "- Fix EVERY issue listed above; do not repeat the same mistake.\n"
        "- SQLite dialect only; a single statement (WITH ... SELECT allowed).\n"
        "- Use only the tables and columns listed above; join only along the\n"
        "  edges above; never join a key column to a quantity/measure column.\n"
        "- String literals spelled EXACTLY as in the known column values.\n"
        "- Apply the comparison/aggregation the question asks for — never end\n"
        "  with a bare SELECT * FROM cte.\n\n"
        f"Question: {question}\n"
        "Corrected SQL:"
    )


def generate_repair_sql(question, graph, value_hints, checklist, selected,
                        candidates):
    """One LLM call -> corrected SQL string, or None. Never raises."""
    try:
        keep = _relevant_tables(graph, checklist)
        tables_block, fk_block = _schema_blocks(graph, keep)
        issues = _issues_block(selected, candidates)
        prompt = _repair_prompt(question, tables_block, fk_block, value_hints,
                                checklist, issues)
        print("CALLING SQL REPAIR...", flush=True)
        result = get_provider().generate(
            prompt,
            options={"temperature": 0, "num_predict": 700, "think": False},
        )
        sql = _clean_sql((result.text or "").strip())
        print("REPAIR SQL:", sql, flush=True)
        return sql
    except ProviderError as exc:
        print(f"REPAIR SQL ERROR (provider): {exc}", flush=True)
        return None
    except Exception as exc:
        print(f"REPAIR SQL ERROR: {exc}", flush=True)
        return None
