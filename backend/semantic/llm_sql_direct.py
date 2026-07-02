"""
semantic/llm_sql_direct.py

Stage 2 — direct LLM SQL candidate ("llm_sql_direct").

One model call that produces a complete SQLite query from: the question, the
relevant schema (columns + types), the valid FK/join edges, and the semantic
checklist. This bypasses the IR pipeline entirely, giving the candidate
selector one candidate whose structure is not limited by the query families
or the IR constructs. It is a CANDIDATE source only: the scorer and the
hard checks decide whether it wins.

The IR pipeline and the query families are untouched.
"""

import re

from llm import get_provider
from llm.errors import ProviderError
from semantic.ai_semantic_extractor import strip_think_blocks, _graph_root
from query_families import slot_extractor as se

__all__ = ["generate_direct_sql"]

_MAX_FULL_SCHEMA_TABLES = 10


def _relevant_tables(graph, checklist):
    """Table names to show the model: checklist must_use tables + their one-hop
    FK neighbors; the full schema when it is small or the checklist is empty."""
    idx = se.index_schema(graph)
    all_tables = list(idx["tables"])
    must = [t for t in ((checklist or {}).get("must_use_tables") or [])
            if t in idx["tables"]]
    if not must or len(all_tables) <= _MAX_FULL_SCHEMA_TABLES:
        return set(all_tables)
    keep = set(must)
    for t in must:
        keep.update(se.neighbors(t, idx))
    return keep


def _schema_blocks(graph, keep):
    """Render (tables_block, fk_block) for the kept tables, with column types."""
    g = _graph_root(graph)
    table_lines = []
    for table in g.get("tables") or []:
        if not isinstance(table, dict):
            continue
        name = str(table.get("table_name") or "").strip()
        if name.lower() not in keep:
            continue
        cols = []
        for c in table.get("columns") or []:
            if isinstance(c, dict) and c.get("column_name") is not None:
                dtype = str(c.get("data_type") or "").upper() or "TEXT"
                cols.append(f'{c["column_name"]} {dtype}')
        table_lines.append(f"- {name}({', '.join(cols)})")
    fk_lines = []
    for rel in g.get("relationships") or []:
        if not isinstance(rel, dict):
            continue
        ft = str(rel.get("from_table") or "").lower()
        tt = str(rel.get("to_table") or "").lower()
        if ft in keep and tt in keep:
            fk_lines.append(
                f"- {rel.get('from_table')}.{rel.get('from_column')} = "
                f"{rel.get('to_table')}.{rel.get('to_column')}")
    return ("\n".join(table_lines) or "(no tables)",
            "\n".join(fk_lines) or "(none)")


def _checklist_block(checklist):
    if not checklist:
        return ""
    lines = ["Semantic checklist (the correct SQL satisfies ALL of this):"]
    for key in ("target_entity", "output_columns", "must_use_tables",
                "must_use_columns", "measure_column", "group_by_entity",
                "comparison_logic", "required_sql_shape", "literals"):
        val = checklist.get(key)
        if val:
            lines.append(f"- {key}: {val}")
    return "\n".join(lines) + "\n\n"


def _direct_prompt(question, tables_block, fk_block, checklist, value_hints=""):
    hints = f"{value_hints}\n\n" if value_hints else ""
    return (
        "/no_think\n"
        "Write ONE SQLite query that answers the question. Output ONLY the SQL\n"
        "statement — no markdown, no code fences, no explanation.\n\n"
        f"Tables:\n{tables_block}\n\n"
        f"Valid join edges (join ONLY along these, or self-joins):\n{fk_block}\n\n"
        f"{hints}"
        f"{_checklist_block(checklist)}"
        "Rules:\n"
        "- SQLite dialect only; a single statement (WITH ... SELECT allowed).\n"
        "- Use only the tables and columns listed above.\n"
        "- Never join a key column to a quantity/measure column.\n"
        "- String literals in single quotes, spelled EXACTLY as in the known\n"
        "  column values above when the column is listed there.\n"
        "- If the question needs absence, use NOT EXISTS; extremum-per-group,\n"
        "  use a window function or correlated subquery; a comparison against\n"
        "  a computed value, use a subquery or CTE and APPLY the comparison.\n\n"
        f"Question: {question}\n"
        "SQL:"
    )


_FENCE_RE = re.compile(r"```(?:sql)?", re.IGNORECASE)


def _clean_sql(text):
    """Strip think blocks / fences / prose and return the SQL, or None."""
    if not text:
        return None
    clean = _FENCE_RE.sub("\n", strip_think_blocks(text)).strip()
    m = re.search(r"\b(WITH|SELECT)\b", clean, re.IGNORECASE)
    if not m:
        return None
    sql = clean[m.start():].strip()
    # cut anything after a statement-terminating semicolon
    if ";" in sql:
        sql = sql.split(";", 1)[0].strip()
    return sql or None


def generate_direct_sql(question, graph, checklist=None, value_hints=""):
    """One LLM call -> SQL string, or None on any failure. Never raises."""
    try:
        keep = _relevant_tables(graph, checklist)
        tables_block, fk_block = _schema_blocks(graph, keep)
        prompt = _direct_prompt(question, tables_block, fk_block, checklist,
                                value_hints)
        print("CALLING DIRECT SQL GENERATOR...", flush=True)
        result = get_provider().generate(
            prompt,
            options={"temperature": 0, "num_predict": 700, "think": False},
        )
        sql = _clean_sql((result.text or "").strip())
        print("DIRECT SQL:", sql, flush=True)
        return sql
    except ProviderError as exc:
        print(f"DIRECT SQL ERROR (provider): {exc}", flush=True)
        return None
    except Exception as exc:
        print(f"DIRECT SQL ERROR: {exc}", flush=True)
        return None
