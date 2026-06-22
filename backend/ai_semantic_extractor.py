import json
import re
import requests

from config import (
    OLLAMA_URL,
    MODEL_NAME,
    DEFAULT_OPTIONS,
)


def strip_think_blocks(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def extract_json(text: str) -> dict | None:
    clean = strip_think_blocks(text)

    depth = 0
    start = None

    for i, ch in enumerate(clean):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1

        elif ch == "}":
            depth -= 1

            if depth == 0 and start is not None:
                candidate = clean[start : i + 1]

                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = None

    return None

def repair_semantics(data: dict) -> dict:
    if isinstance(data.get("group_by"), list):
        data["group_by"] = data["group_by"][0] if data["group_by"] else None

    aggregation = data.get("aggregation")
    sort = data.get("sort")
    select = data.get("select") or []

    if aggregation and sort:
        agg_field = aggregation.get("field")
        if agg_field:
            sort["field"] = agg_field

    if aggregation and not data.get("group_by"):
        if select and select[0] != "*":
            data["group_by"] = select[0]

    return data

def extract_semantics(question: str, schema_text: str) -> dict | None:
    prompt = f"""
/no_think

You are a semantic meaning extractor for a natural-language database system.

Your task is not to guess SQL directly.
Your task is to understand the user's question and return the correct database meaning.

Return ONLY valid JSON.
No explanation.
No markdown.
No extra text.

Schema:
{schema_text}

Question:
{question}

Think about the question at the semantic level:

1. What table/entity is the user asking about?
2. What object should appear in the answer?
3. What value or measure is being compared, counted, totaled, averaged, filtered, or sorted?
4. Is the question asking about individual rows, or is it asking about groups/categories?
5. If a category is being compared by a numeric measure, represent that category-level comparison correctly.
6. If the question asks for a single best/worst/largest/smallest answer, return only one result.
7. The output JSON must preserve the real meaning of the question.
8. The generated SQL from this JSON should not change the user's intent.

Important semantic guidance:

- If the answer object is a category/text column and the comparison/sort measure is numeric,
  then the meaning is usually category-level, not row-level.
- In category-level comparison, use group_by on the answer object.
- In category-level comparison, aggregate the numeric measure.
- Use SUM when the numeric column already stores counts, totals, quantities, sizes, amounts, allocated space, or file counts.
- Use AVG only when the user asks for average/mean.
- Use COUNT only when the user asks how many rows/records/items exist and there is no count-like numeric column.
- Sorting direction should match the meaning of the question.
- Limit should match the amount of results requested by the user.
- If the user asks for one answer, set limit to 1.
- If the user asks for top N, set limit to N.
- If no limit is implied, set limit to null.

Return JSON exactly in this structure:

{{
  "entity": "table_name",
  "select": ["column_or_*"],
  "filters": [],
  "aggregation": null,
  "group_by": null,
  "sort": null,
  "limit": null
}}

Aggregation format, only when needed:

{{
  "function": "SUM",
  "field": "column_name"
}}

Sort format, only when needed:

{{
  "field": "column_name",
  "direction": "DESC"
}}

Before returning, silently check your JSON:

- Does select contain the object the user wants to see?
- Does aggregation represent the numeric measure being compared or summarized?
- Does group_by exist when a category is compared by a numeric measure?
- Does sort use the same field as the compared measure?
- Does direction match the meaning of the question?
- Does limit match the number of answers requested?
- Are all names from the provided schema only?

Now return only the final corrected JSON.
"""

    try:
        print("CALLING SEMANTIC EXTRACTOR...", flush=True)

        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    **DEFAULT_OPTIONS,
                    "temperature": 0,
                    "num_predict": 500,
                },
            },
            timeout=90,
        )

        response.raise_for_status()

        raw_text = response.json().get("response", "").strip()

        print("RAW SEMANTIC EXTRACTOR:", raw_text, flush=True)

        data = extract_json(raw_text)

        if not data:
            print("SEMANTIC EXTRACTOR ERROR: no valid JSON found", flush=True)
            return None

        data = repair_semantics(data)
        print("REPAIRED SEMANTICS:", data, flush=True)

        # Normalize group_by shape
        if isinstance(data.get("group_by"), list):
            data["group_by"] = data["group_by"][0] if data["group_by"] else None

        # If aggregation exists, sort should use aggregation field, not group/category field
        if data.get("aggregation") and data.get("sort"):
            agg_field = data["aggregation"].get("field")
            sort_field = data["sort"].get("field")

            if agg_field and sort_field != agg_field:
                data["sort"]["field"] = agg_field

        return data

    except Exception as exc:
        print(f"SEMANTIC EXTRACTOR ERROR: {exc}", flush=True)
        return None


# ===========================================================================
# Phase 5 — schema-graph-aware multi-table IR extraction (ADDITIVE)
#
# Produces an IR-shaped *extraction* dict only. It does NOT return SQL, invent
# joins, traverse the graph, or include relationship_hints (ir_builder adds
# those from the graph). It does not touch the single-table extractor above.
# ===========================================================================

# The output shape this extractor is contracted to return.
_IR_EXTRACTION_KEYS = (
    "tables", "select", "filters", "aggregations",
    "group_by", "having", "order_by", "limit", "distinct",
)

# Compact instruction block + two worked examples (filter, aggregate). Kept as
# a plain (non-f) string so the literal JSON braces need no escaping. Short on
# purpose: a long prompt makes the model spend its token budget before
# emitting JSON, which is the empty-response failure this guards against.
_MULTITABLE_IR_GUIDE = """
Return ONE JSON object with EXACTLY these keys:
{"tables":[],"select":[],"filters":[],"aggregations":[],"group_by":[],"having":[],"order_by":[],"limit":null,"distinct":false}

Rules:
- Use only the tables/columns listed above. Every column is {"table":"..","column":".."}.
- filters: {"table","column","op","value","connector"}.
- aggregations: {"function","table","column","alias"}; function in COUNT,SUM,AVG,MIN,MAX; COUNT(*) uses column "*".
- group_by: {"table","column"}. order_by: {"table","column","direction"} or {"aggregation_alias","direction"}.
- Do not add joins or relationship fields. If unsure, use empty lists.

Example - "Which owners have dogs?":
{"tables":["owners","pets"],"select":[{"table":"owners","column":"lastname"}],"filters":[{"table":"pets","column":"species","op":"=","value":"dog","connector":"AND"}],"aggregations":[],"group_by":[],"having":[],"order_by":[],"limit":null,"distinct":true}

Example - "Count pets by city":
{"tables":["owners","pets"],"select":[{"table":"owners","column":"city"}],"filters":[],"aggregations":[{"function":"COUNT","table":"pets","column":"petid","alias":"pet_count"}],"group_by":[{"table":"owners","column":"city"}],"having":[],"order_by":[{"aggregation_alias":"pet_count","direction":"DESC"}],"limit":null,"distinct":false}

Output JSON now:
"""


def _empty_ir_extraction() -> dict:
    return {
        "tables": [],
        "select": [],
        "filters": [],
        "aggregations": [],
        "group_by": [],
        "having": [],
        "order_by": [],
        "limit": None,
        "distinct": False,
    }


def _graph_root(graph) -> dict:
    """Tolerate a graph wrapped under a 'database' key."""
    if isinstance(graph, dict) and isinstance(graph.get("database"), dict):
        return graph["database"]
    return graph if isinstance(graph, dict) else {}


def _describe_graph(graph):
    """Render the schema graph into (tables_block, relationships_block) text."""
    g = _graph_root(graph)

    table_lines = []
    for table in g.get("tables") or []:
        if not isinstance(table, dict):
            continue
        name = table.get("table_name")
        cols = [
            c.get("column_name")
            for c in (table.get("columns") or [])
            if isinstance(c, dict) and c.get("column_name") is not None
        ]
        table_lines.append(f"- {name}({', '.join(cols)})")

    rel_lines = []
    for rel in g.get("relationships") or []:
        if not isinstance(rel, dict):
            continue
        rel_lines.append(
            f"- {rel.get('from_table')}.{rel.get('from_column')} -> "
            f"{rel.get('to_table')}.{rel.get('to_column')}"
        )

    tables_block = "\n".join(table_lines) if table_lines else "(no tables)"
    rel_block = "\n".join(rel_lines) if rel_lines else "(none detected)"
    return tables_block, rel_block


def _normalize_ir_extraction(data) -> dict:
    """Coerce raw model output into exactly the contracted extraction shape.

    Any extra keys (e.g. a stray 'sql' or 'relationship_hints') are dropped,
    list fields are guaranteed to be lists, and limit/distinct are coerced.
    """
    data = data if isinstance(data, dict) else {}
    result = _empty_ir_extraction()

    for key in ("tables", "select", "filters", "aggregations",
                "group_by", "having", "order_by"):
        value = data.get(key)
        if isinstance(value, list):
            result[key] = value

    limit = data.get("limit")
    if isinstance(limit, bool):          # guard against true/false
        limit = None
    elif limit is not None and not isinstance(limit, int):
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = None
    result["limit"] = limit

    result["distinct"] = bool(data.get("distinct", False))
    return result


def _primary_ir_prompt(question, tables_block, rel_block):
    """Compact primary prompt: schema + relationships-as-context + 2 examples."""
    return (
        "/no_think\n"
        "Extract the query meaning as JSON only. No SQL, no prose.\n\n"
        f"Tables:\n{tables_block}\n\n"
        f"Relationships (context only, do not invent joins):\n{rel_block}\n\n"
        f"Question: {question}\n"
        f"{_MULTITABLE_IR_GUIDE}"
    )


def _fallback_ir_prompt(question, tables_block):
    """Even shorter retry prompt: no relationships, no examples, inline shape."""
    return (
        "/no_think\n"
        "Output ONLY one JSON object, nothing else.\n\n"
        f"Tables:\n{tables_block}\n\n"
        f"Question: {question}\n\n"
        'Shape: {"tables":[],"select":[{"table":"t","column":"c"}],"filters":[],'
        '"aggregations":[],"group_by":[],"having":[],"order_by":[],"limit":null,"distinct":false}\n'
        'Use only the tables/columns above. Every column is {"table":..,"column":..}. '
        "No SQL. No joins. If unsure use empty lists.\nJSON:"
    )


def _call_ir_model(prompt, num_predict):
    """One model call. Returns a parsed dict, or None if the response is empty,
    has no JSON, or the request fails."""
    try:
        print("CALLING MULTITABLE IR EXTRACTOR...", flush=True)
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    **DEFAULT_OPTIONS,
                    "temperature": 0,
                    "num_predict": num_predict,
                },
            },
            timeout=90,
        )
        response.raise_for_status()

        raw_text = response.json().get("response", "").strip()
        print("RAW MULTITABLE IR EXTRACTOR:", raw_text, flush=True)
        if not raw_text:
            return None
        return extract_json(raw_text)
    except Exception as exc:
        print(f"MULTITABLE IR EXTRACTOR ERROR: {exc}", flush=True)
        return None


def extract_multitable_ir_extraction(question: str, graph) -> dict:
    """Schema-graph-aware extraction.

    Given a natural-language question and a schema graph, ask the model for an
    IR-shaped extraction dict (tables + table-qualified clauses). Returns ONLY
    the extraction shape - never SQL and never relationship_hints. Makes one
    retry with a shorter prompt when the model returns an empty / non-JSON
    response, and falls back to empty lists rather than inventing content.
    """
    tables_block, rel_block = _describe_graph(graph)

    # Attempt 1: compact prompt with two examples.
    data = _call_ir_model(_primary_ir_prompt(question, tables_block, rel_block), 2000)

    # Attempt 2: even shorter prompt when the first yields nothing usable.
    if not data:
        print("MULTITABLE IR EXTRACTOR: retrying with a shorter prompt", flush=True)
        data = _call_ir_model(_fallback_ir_prompt(question, tables_block), 1200)

    if not data:
        print("MULTITABLE IR EXTRACTOR: no valid JSON after retry", flush=True)
        return _empty_ir_extraction()

    extraction = _normalize_ir_extraction(data)
    print("MULTITABLE IR EXTRACTION:", extraction, flush=True)
    return extraction


if __name__ == "__main__":
    print("STARTING SEMANTIC TEST...", flush=True)

    tests = [
        "Which extension has the most files?",
        "Which extension has the least files?",
        "Top 5 extensions by size",
        "Average size by extension",
        "Highest allocated space",
    ]

    schema = "uploaded_data(extension, file_type, percent, size, allocated, files)"

    for question in tests:
        print("\nQUESTION:", question)
        result = extract_semantics(question, schema)
        print("FINAL RESULT:")
        print(json.dumps(result, indent=2))