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

__all__ = ["generate_direct_sql", "generate_direct_sql_grain",
           "generate_direct_sql_variant"]

_MAX_FULL_SCHEMA_TABLES = 10


def _relevant_tables(graph, checklist, question=None):
    """Table names to show the model: checklist must_use tables + their one-hop
    FK neighbors; the full schema when it is small or the checklist is empty.
    If the question NAMES real schema tables verbatim, the schema is FOCUSED
    to those locked tables + their declared-FK neighbors (no full schema)."""
    idx = se.index_schema(graph)
    all_tables = list(idx["tables"])
    # Focus = corrected must_use_tables (schema-linker) UNION any tables named
    # verbatim in the question, plus their declared-FK neighbors. This is what
    # carries the corrected table set into the direct-SQL prompt.
    focus = {t.lower() for t in ((checklist or {}).get("must_use_tables") or [])
             if str(t).lower() in idx["tables"]}
    if question:
        try:
            from sql_candidates.explicit_table_lock import detect_locked_tables
            focus |= set(detect_locked_tables(question, set(all_tables)))
        except Exception:
            pass
    if focus:
        keep = set(focus)
        for t in list(focus):
            keep.update(se.neighbors(t, idx))
        return keep
    if len(all_tables) <= _MAX_FULL_SCHEMA_TABLES:
        return set(all_tables)
    return set(all_tables)


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
                "comparison_logic", "required_sql_shape", "literals",
                "row_grain", "universe", "required_group_keys",
                "forbidden_hardcoded_universe"):
        val = checklist.get(key)
        if val:
            lines.append(f"- {key}: {val}")
    return "\n".join(lines) + "\n\n"


_DAY2_SEMANTIC_REMINDERS = (
    "- If the question asks for a ratio, percentage, share, rate, difference or\n"
    "  profit, COMPUTE that expression in the SELECT (e.g. a / b, a - b); returning\n"
    "  the operands separately is NOT enough. For a percentage multiply by 100.\n"
    "- Cast ratio operands to REAL and guard the denominator against zero so\n"
    "  integer division does not truncate (e.g. CAST(a AS REAL) / NULLIF(b, 0)).\n"
    "- Preserve EVERY explicit condition (status, year, threshold, literal). Put\n"
    "  row-level conditions in WHERE and aggregate conditions in HAVING. Do NOT\n"
    "  add filters the question does not state, and do not drop stated ones.\n"
    "- 'either/or/at least one' -> UNION or OR or separate EXISTS; 'both' ->\n"
    "  INTERSECT or two independent EXISTS; 'A but not B' -> EXCEPT or\n"
    "  EXISTS(A) AND NOT EXISTS(B); 'without/no/never' -> NOT EXISTS (never an\n"
    "  inner join to prove a row is absent).\n"
    "- When two conditions may hold on DIFFERENT child rows (e.g. 'has X and has\n"
    "  Y'), use TWO independent EXISTS clauses; do not force both onto one child\n"
    "  row unless the question says the same record must satisfy both.\n"
    "- Output EVERY explicitly requested value (identifier, name, attribute,\n"
    "  aggregate, derived metric, ranking metric).\n"
)


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
        "- Your SQL MUST reference EVERY table listed under must_use_tables\n"
        "  in a FROM/JOIN clause; do not omit or substitute any of them.\n"
        "- If the question names specific tables, use exactly those; do NOT\n"
        "  replace them with similar or sibling tables.\n"
        "- If a ZIP/postal-to-tract/census mapping (bridge) table is present,\n"
        "  join THROUGH it; never join a ZIP/postal column directly to a\n"
        "  tract/census/geography id (no zip_code = tract_ce, no SUBSTR(geo_id)).\n"
        "- Never join a key column to a quantity/measure column.\n"
        "- Choose GROUP BY from row_grain: output one row per that entity,\n"
        "  and include every required_group_key.\n"
        "- For every/all/each questions, compare a per-group COUNT against a\n"
        "  universe SUBQUERY (e.g. = (SELECT COUNT(DISTINCT ...) FROM ...));\n"
        "  do NOT hardcode the universe size as a constant unless the\n"
        "  question states that number.\n"
        "- String literals in single quotes, spelled EXACTLY as in the known\n"
        "  column values above when the column is listed there.\n"
        "- If the question needs absence, use NOT EXISTS; extremum-per-group,\n"
        "  use a window function or correlated subquery; a comparison against\n"
        "  a computed value, use a subquery or CTE and APPLY the comparison.\n\n"
        + _DAY2_SEMANTIC_REMINDERS
        + f"Question: {question}\n"
        "SQL:"
    )


def _grain_prompt(question, tables_block, fk_block, checklist, value_hints=""):
    """Grain-aware variant: the model first fixes the row grain in its head,
    then emits ONLY the SQL. Same schema/edges/checklist/rules as the base."""
    hints = f"{value_hints}\n\n" if value_hints else ""
    return (
        "/no_think\n"
        "Write ONE SQLite query that answers the question.\n"
        "Before writing, silently decide (do NOT print your reasoning):\n"
        "  1. the row GRAIN of the answer — what a single output row represents\n"
        "     (e.g. one event, one attendee, one department);\n"
        "  2. the table whose rows are at that grain, and the level any\n"
        "     COUNT/SUM/AVG must be grouped to so it is not over- or\n"
        "     under-counted.\n"
        "Then output ONLY the final SQL statement — no markdown, no code\n"
        "fences, no explanation, no comments.\n\n"
        f"Tables:\n{tables_block}\n\n"
        f"Valid join edges (join ONLY along these, or self-joins):\n{fk_block}\n\n"
        f"{hints}"
        f"{_checklist_block(checklist)}"
        "Rules:\n"
        "- SQLite dialect only; a single statement (WITH ... SELECT allowed).\n"
        "- Use only the tables and columns listed above.\n"
        "- Your SQL MUST reference EVERY table listed under must_use_tables\n"
        "  in a FROM/JOIN clause; do not omit or substitute any of them.\n"
        "- If the question names specific tables, use exactly those; do NOT\n"
        "  replace them with similar or sibling tables.\n"
        "- If a ZIP/postal-to-tract/census mapping (bridge) table is present,\n"
        "  join THROUGH it; never join a ZIP/postal column directly to a\n"
        "  tract/census/geography id (no zip_code = tract_ce, no SUBSTR(geo_id)).\n"
        "- Never join a key column to a quantity/measure column.\n"
        "- Choose GROUP BY from row_grain: output one row per that entity,\n"
        "  and include every required_group_key.\n"
        "- For every/all/each questions, compare a per-group COUNT against a\n"
        "  universe SUBQUERY (e.g. = (SELECT COUNT(DISTINCT ...) FROM ...));\n"
        "  do NOT hardcode the universe size as a constant unless the\n"
        "  question states that number.\n"
        "- Aggregate at the grain you identified; GROUP BY the entity the\n"
        "  question counts, not an incidental detail row.\n"
        "- String literals in single quotes, spelled EXACTLY as in the known\n"
        "  column values above when the column is listed there.\n"
        "- If the question needs absence, use NOT EXISTS; extremum-per-group,\n"
        "  use a window function or correlated subquery; a comparison against\n"
        "  a computed value, use a subquery or CTE and APPLY the comparison.\n\n"
        + _DAY2_SEMANTIC_REMINDERS
        + f"Question: {question}\n"
        "SQL:"
    )


def _variant_prompt(question, tables_block, fk_block, checklist, value_hints=""):
    """Reworded phrasing of the direct task, run at a mild temperature so the
    sample explores an alternative structure. Same constraints as the base."""
    hints = f"{value_hints}\n\n" if value_hints else ""
    return (
        "/no_think\n"
        "You are turning a question into ONE correct SQLite SELECT query.\n"
        "Return the SQL statement by itself — no prose, no code fences, no\n"
        "explanation.\n\n"
        f"Schema (table(columns)):\n{tables_block}\n\n"
        f"Only these join paths are allowed (or a self-join):\n{fk_block}\n\n"
        f"{hints}"
        f"{_checklist_block(checklist)}"
        "Constraints:\n"
        "- SQLite only; exactly one statement (a leading WITH is fine).\n"
        "- Reference only the tables and columns shown above.\n"
        "- Your SQL MUST reference EVERY table listed under must_use_tables\n"
        "  in a FROM/JOIN clause; do not omit or substitute any of them.\n"
        "- Do not equate a key/id column with a numeric quantity/measure.\n"
        "- Choose GROUP BY from row_grain: output one row per that entity,\n"
        "  and include every required_group_key.\n"
        "- For every/all/each questions, compare a per-group COUNT against a\n"
        "  universe SUBQUERY (e.g. = (SELECT COUNT(DISTINCT ...) FROM ...));\n"
        "  do NOT hardcode the universe size as a constant unless the\n"
        "  question states that number.\n"
        "- Quote string literals with single quotes, matching the known\n"
        "  column values above verbatim when that column is listed.\n"
        "- Absence -> NOT EXISTS; top/bottom per group -> window or correlated\n"
        "  subquery; comparing to a computed value -> compute it in a subquery\n"
        "  or CTE and actually apply the comparison.\n\n"
        + _DAY2_SEMANTIC_REMINDERS
        + f"Question: {question}\n"
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
        keep = _relevant_tables(graph, checklist, question)
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
        try:                                   # diagnostics only (full trace)
            from diagnostics import full_trace
            full_trace.note("layer5", "raw::llm_sql_direct",
                            (result.text or "").strip())
        except Exception:
            pass
        return sql
    except ProviderError as exc:
        print(f"DIRECT SQL ERROR (provider): {exc}", flush=True)
        return None
    except Exception as exc:
        print(f"DIRECT SQL ERROR: {exc}", flush=True)
        return None


def _run_direct(question, graph, checklist, value_hints, prompt_fn, options, tag):
    """Shared body for the alternate direct-SQL samplers: build the schema
    blocks, render `prompt_fn`, call the model with `options`, clean the SQL.
    Returns the SQL string or None on ANY failure. Never raises — an extra
    sampler must not be able to break the endpoint."""
    try:
        keep = _relevant_tables(graph, checklist, question)
        tables_block, fk_block = _schema_blocks(graph, keep)
        prompt = prompt_fn(question, tables_block, fk_block, checklist,
                           value_hints)
        print(f"CALLING DIRECT SQL GENERATOR [{tag}]...", flush=True)
        result = get_provider().generate(prompt, options=options)
        sql = _clean_sql((result.text or "").strip())
        print(f"DIRECT SQL [{tag}]:", sql, flush=True)
        try:                                   # diagnostics only (full trace)
            from diagnostics import full_trace
            full_trace.note("layer5", f"raw::llm_sql_direct_{tag}",
                            (result.text or "").strip())
        except Exception:
            pass
        return sql
    except ProviderError as exc:
        print(f"DIRECT SQL ERROR [{tag}] (provider): {exc}", flush=True)
        return None
    except Exception as exc:
        print(f"DIRECT SQL ERROR [{tag}]: {exc}", flush=True)
        return None


def generate_direct_sql_grain(question, graph, checklist=None, value_hints=""):
    """Grain-aware direct sample (source llm_sql_direct_grain). Deterministic
    (temperature 0): the model fixes the row grain before writing the SQL."""
    return _run_direct(
        question, graph, checklist, value_hints, _grain_prompt,
        {"temperature": 0, "num_predict": 700, "think": False}, "grain")


def generate_direct_sql_variant(question, graph, checklist=None, value_hints="",
                                temperature=0.35):
    """Reworded direct sample at a mild temperature (source
    llm_sql_direct_variant). Diversifies the direct-SQL pool so selection does
    not hinge on the single temperature-0 candidate."""
    return _run_direct(
        question, graph, checklist, value_hints, _variant_prompt,
        {"temperature": temperature, "num_predict": 700, "think": False},
        "variant")
