"""
semantic/llm_sql_repair.py

One-shot SQL repair (candidate source "llm_sql_repair").

After normal selection, when the winner looks unreliable (fatal, low score,
missing concepts, empty result, or a weak family pick while direct SQL
exists), ONE additional LLM call is made. The model sees the question, the
schema, the value hints, the semantic checklist, the TYPED SEMANTIC CONTRACT
(final stabilization, Part F), the selected SQL, and every candidate's
diagnostics (scores, errors, fatal reasons), and returns a corrected SQLite
query. The repaired SQL is packaged as a normal candidate, scored like every
other candidate (all validators rerun), and selection re-runs once. Exactly
one round — never a loop.

Part F: the repair prompt derives GENERIC decomposition instructions from the
typed contract and the observed fatal reasons — independent CTEs for
qualification vs all-row measures, two-level entity-total aggregation,
COUNT(DISTINCT ...), explicit comparison application, and latest-event
separation. No database-specific SQL templates.
"""

from llm import get_provider
from llm.errors import ProviderError
from semantic.llm_sql_direct import (
    _relevant_tables,
    _schema_blocks,
    _checklist_block,
    _clean_sql,
)

__all__ = ["should_repair", "generate_repair_sql", "SCORE_TRIGGER",
           "_contract_block", "_repair_instructions"]

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


# ---------------------------------------------------------------------------
# Part F — typed-contract blocks for the repair prompt (pure text builders,
# unit-testable without any LLM call)
# ---------------------------------------------------------------------------
def _req_line(n, r):
    parts = [f"REQUIRED SEMANTICS {n}:"]
    agg = (r.measure_aggregation or "?").upper()
    measure = f"{r.measure_table}.{r.measure_column}"
    if r.measure_components and len(r.measure_components) >= 2:
        op = " - " if r.measure_operation == "subtract" else " + "
        measure = op.join(f"{t}.{c}" for t, c in r.measure_components)
    if r.distinct and r.measure_aggregation == "count":
        parts.append(f"COUNT(DISTINCT {measure})")
    else:
        parts.append(f"{agg}({measure})")
    if r.entity_table and r.entity_key_column:
        parts.append(f"per {r.entity_table}.{r.entity_key_column}")
    if r.comparison_right_kind == "aggregate_of_entity_totals":
        parts.append("compared against an aggregate OF those per-entity "
                     "totals (two levels — never an aggregate of raw rows)")
    elif r.comparison_right_kind == "aggregate_of_rows":
        parts.append("compared against the group aggregate of rows")
    if r.comparison_operator is not None and r.comparison_constant is not None:
        parts.append(f"with the comparison {r.comparison_operator} "
                     f"{r.comparison_constant:g}")
    if r.population_table and r.population_column:
        parts.append(f"within the same {r.population_table}."
                     f"{r.population_column}")
    if r.measure_scope == "all_entity_rows":
        parts.append("over ALL rows of the entity (lifetime — a qualifying "
                     "condition must NOT filter these rows)")
    elif r.measure_scope == "filtered_entity_rows":
        parts.append("over the question's filtered rows only")
    return " ".join(parts)


def _temporal_line(t):
    ext = "EARLIEST" if t.direction == "earliest" else "LATEST"
    order = f"{t.order_table or t.event_table}.{t.order_column}"
    qual = f"{t.qualifier_table or t.event_table}.{t.qualifier_column}"
    vals = (" = " + "/".join(str(v) for v in t.qualifier_values)
            if t.qualifier_values else "")
    per = (f" per {t.entity_table}.{t.entity_key_column}"
           if t.entity_table and t.entity_key_column else " per entity")
    return (f"REQUIRED EVENT SEMANTICS: select the {ext} {t.event_table} row"
            f"{per} (by {order}) across ALL {t.event_table} rows FIRST, and "
            f"only then test {qual}{vals} on that selected row — never "
            f"filter by {qual} before the MAX/MIN/ROW_NUMBER that picks the "
            f"{ext.lower()} event")


def _contract_block(contract):
    """Compact structured summary of every actionable grain + temporal
    requirement."""
    reqs = list(getattr(contract, "actionable_requirements", []) or [])
    t_reqs = list(getattr(contract, "actionable_temporal", []) or [])
    if not reqs and not t_reqs:
        return ""
    lines = ["The corrected SQL MUST satisfy every requirement below:"]
    for n, r in enumerate(reqs, start=1):
        lines.append("- " + _req_line(n, r))
    for t in t_reqs:
        lines.append("- " + _temporal_line(t))
    return "\n".join(lines) + "\n\n"


def _repair_instructions(selected, candidates, contract):
    """Generic repair instructions derived from the observed fatal reasons +
    the typed contract. No schema names beyond the contract's own columns."""
    text = []
    for c in [selected] + list(candidates or []):
        if c is None:
            continue
        text.extend((c.validation or {}).get("fatal") or [])
    blob = " ".join(text).lower()
    reqs = list(getattr(contract, "actionable_requirements", []) or [])
    instr = []
    if "restricted scope" in blob or "qualifying condition" in blob or any(
            r.measure_scope == "all_entity_rows" for r in reqs):
        instr.append(
            "Compute the lifetime/all-row aggregate in its OWN CTE over the "
            "measure's table(s) with NO qualifying filters; compute each "
            "qualification (status/flag/latest-event conditions) in a "
            "SEPARATE CTE or subquery; then JOIN them by the entity key and "
            "apply both conditions in the final WHERE/HAVING.")
    if "per-entity totals" in blob or "raw rows" in blob or any(
            r.comparison_right_kind == "aggregate_of_entity_totals"
            for r in reqs):
        instr.append(
            "For an 'above the average entity' comparison: FIRST aggregate "
            "the measure per entity (GROUP BY the entity key), THEN take the "
            "AVG of those per-entity totals for the comparison population. "
            "Never compare against AVG(raw row values).")
    if "distinct" in blob or any(r.distinct for r in reqs):
        instr.append(
            "Counting kinds/types/categories requires COUNT(DISTINCT "
            "<the type column>) — COUNT(column) or COUNT(*) is wrong.")
    if "never applied" in blob or "boolean predicate" in blob:
        instr.append(
            "Every required comparison must appear as an explicit Boolean "
            "predicate in WHERE or HAVING (e.g. total > threshold). An "
            "aggregate alias listed only in SELECT, or a bare arithmetic "
            "expression without a comparison operator, answers nothing.")
    if "max-equality" in blob or "extremum" in blob or "latest" in blob:
        instr.append(
            "'Most recent / latest X' is a QUALIFICATION: find the true "
            "latest event per entity in its own subquery and test it there. "
            "Do NOT restrict a lifetime/all-history aggregate to that one "
            "event.")
    t_reqs = list(getattr(contract, "actionable_temporal", []) or [])
    if "temporal violation" in blob or t_reqs:
        instr.append(
            "Determine the latest/earliest event ACROSS ALL EVENTS for each "
            "entity (correlated MAX/MIN over the unfiltered event table, or "
            "ROW_NUMBER over all events); apply the qualifying condition "
            "ONLY AFTER that event has been selected; never place the "
            "qualifying condition inside the scope used by MAX, MIN, or "
            "ROW_NUMBER; keep lifetime/all-history aggregates in their own "
            "independent scope.")
    if "fanout" in blob:
        instr.append(
            "Never aggregate a measure after joining a one-to-many child "
            "that multiplies its rows: pre-aggregate each measure in its own "
            "CTE at its own grain, then join the aggregated results.")
    if not instr:
        return ""
    return ("Decomposition rules derived from the failed attempts:\n"
            + "\n".join(f"{i}. {s}" for i, s in enumerate(instr, start=1))
            + "\n\n")


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


# Generic repair guidance + safety rails (schema-independent; no DB names).
_DAY2_REPAIR_REMINDERS = (
    "- A repair MAY add a missing computed formula, a missing output, a missing\n"
    "  explicit filter, correct WHERE/HAVING placement, the right set operator,\n"
    "  NOT EXISTS for absence, or safe (REAL, zero-guarded) division.\n"
    "- If the question asks for a ratio/percentage/difference/profit, compute it\n"
    "  in the SELECT; returning only the operands is wrong.\n"
    "- Use UNION or independent EXISTS for 'either'; two independent EXISTS when\n"
    "  two conditions may hold on different child rows; NOT EXISTS (never an\n"
    "  inner join) for 'without/no/never'.\n"
    "- A repair MUST NOT change the target entity, remove a required table or a\n"
    "  required filter, change a ratio denominator, add unrelated filters,\n"
    "  collapse independent EXISTS clauses, or replace UNION semantics with an\n"
    "  inner join.\n"
    "- HAVING filters GROUPED / aggregate results; WHERE filters rows or columns\n"
    "  already computed by joined CTEs/subqueries. A non-aggregate outer SELECT\n"
    "  (no GROUP BY, no aggregate in its own SELECT) must NOT use HAVING to filter\n"
    "  a precomputed CTE/subquery column — use WHERE.\n"
    "- For a ratio whose numerator and denominator come from DIFFERENT row\n"
    "  populations, pre-aggregate the numerator and the denominator INDEPENDENTLY\n"
    "  (each in its own CTE at its own grain) and then join; do NOT compute the\n"
    "  denominator from rows already filtered by the numerator's fact table, and\n"
    "  count the qualifying population with COUNT(DISTINCT key) so unmatched\n"
    "  population rows are still counted.\n"
    "- When a fact/event table carries its own entity foreign key, attribute the\n"
    "  fact by THAT key rather than deriving the entity from a mutable parent.\n"
    "- Categorical concepts MUST use the column's known stored values. A concept\n"
    "  named by negation/complement (e.g. 'abnormal' = not 'normal', 'inactive'\n"
    "  = not 'active') enumerates ALL known non-base categories with IN (...);\n"
    "  never assume a boolean 0/1 for a TEXT status column, and keep the\n"
    "  numerator and denominator populations grounded independently.\n"
)


def _repair_prompt(question, tables_block, fk_block, value_hints, checklist,
                   issues_block, contract_block="", instructions_block=""):
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
        f"{contract_block}"
        f"{instructions_block}"
        f"{issues_block}\n\n"
        "Rules:\n"
        "- Fix EVERY issue listed above; do not repeat the same mistake.\n"
        "- SQLite dialect only; a single statement (WITH ... SELECT allowed).\n"
        "- Use only the tables and columns listed above; join only along the\n"
        "  edges above; never join a key column to a quantity/measure column.\n"
        "- String literals spelled EXACTLY as in the known column values.\n"
        "- Apply the comparison/aggregation the question asks for — never end\n"
        "  with a bare SELECT * FROM cte, and never leave an arithmetic\n"
        "  expression without a comparison operator in WHERE/HAVING.\n"
        + _DAY2_REPAIR_REMINDERS
        + "\n"
        f"Question: {question}\n"
        "Corrected SQL:"
    )


def generate_repair_sql(question, graph, value_hints, checklist, selected,
                        candidates, contract=None):
    """One LLM call -> corrected SQL string, or None. Never raises."""
    try:
        keep = _relevant_tables(graph, checklist)
        tables_block, fk_block = _schema_blocks(graph, keep)
        issues = _issues_block(selected, candidates)
        cblock = _contract_block(contract) if contract is not None else ""
        iblock = _repair_instructions(selected, candidates, contract)
        prompt = _repair_prompt(question, tables_block, fk_block, value_hints,
                                checklist, issues, cblock, iblock)
        print("CALLING SQL REPAIR...", flush=True)
        result = get_provider().generate(
            prompt,
            options={"temperature": 0, "num_predict": 700, "think": False},
        )
        sql = _clean_sql((result.text or "").strip())
        print("REPAIR SQL:", sql, flush=True)
        try:                                   # diagnostics only (full trace)
            from diagnostics import full_trace
            full_trace.note("layer5", "raw::llm_sql_repair",
                            (result.text or "").strip())
        except Exception:
            pass
        return sql
    except ProviderError as exc:
        print(f"REPAIR SQL ERROR (provider): {exc}", flush=True)
        return None
    except Exception as exc:
        print(f"REPAIR SQL ERROR: {exc}", flush=True)
        return None
