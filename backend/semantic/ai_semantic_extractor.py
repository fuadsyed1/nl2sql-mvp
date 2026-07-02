import json
import re

from llm import get_provider
from llm.errors import ProviderError


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

        result = get_provider().generate(
            prompt,
            options={"temperature": 0, "num_predict": 500, "think": False},
        )

        raw_text = (result.text or "").strip()

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

    except ProviderError as exc:
        print(f"SEMANTIC EXTRACTOR ERROR (provider): {exc}", flush=True)
        return None
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
    "group_by", "having", "order_by", "limit", "distinct", "anti_exists",
    "top_per_group", "universal", "set_division",
    "aliases", "alias_joins", "alias_filters", "alias_select",
    "explicit_joins", "null_filters", "compound_filters",
    "derived_relations", "main_from",
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
- aggregations: {"function","table","column","alias"}; function in COUNT,SUM,AVG,MIN,MAX; COUNT(*) uses column "*". Add "distinct":true for "distinct/different X" (e.g. distinct brands -> COUNT(DISTINCT)).
- having compares an aggregation alias to a scalar value OR to ANOTHER aggregation alias via "right_aggregation_alias" (e.g. {"aggregation_alias":"fed_brands","op":">","right_aggregation_alias":"bought_brands"}).
- set_division: for "has/contains ALL <members of a set>" via distinct-count match. Item: {"group_by":[{"table","column"}],"left":{"function":"COUNT","distinct":true,"table","column"},"op":"=","right_subquery":{"function":"COUNT","distinct":true,"table","column"}}. Omit otherwise.
- aliases/alias_joins/alias_filters/alias_select: for PAIR / self-join questions ("pairs of X", "same/different owner", "compare two rows of the same table"). Declare each row copy in aliases:[{"alias":"p1","table":"pets"},{"alias":"p2","table":"pets"}]; connect them in alias_joins:[{"from":{"alias","column"},"to":{"alias","column"},"op":"=|<|<>","join_type":"inner"}] (use op "<" or "<>" between the two key columns to avoid duplicate/mirror pairs); compare in alias_filters:[{"left":{"alias","column"},"op":"=","right":{"alias","column"}}]; output via alias_select:[{"alias","column","as":"label"}]. When aliases is used, leave select/filters/aggregations empty. Omit all four otherwise.
- explicit_joins/null_filters/compound_filters: for OUTER joins ("include X without Y", "show all X even when no Y", "no matching record"). Use explicit_joins:[{"join_type":"left|inner","from_table","to_table","conditions":[{"left":{"table","column"},"op":"=","right":{"table","column"}}]}] to spell out the join chain (root = first from_table); test unmatched rows with null_filters:[{"table","column","op":"IS NULL"}]; for "null OR mismatch" use compound_filters:[{"connector":"OR","conditions":[{"table","column","op":"IS NULL"},{"left":{...},"op":"<>","right":{...}}]}]. When explicit_joins is set, still fill normal select. Omit otherwise.
- derived_relations/main_from: for per-entity AGGREGATE totals then compared/ranked ("total per X", "highest total per group", "more distinct A than B"). Each CTE: {"name":"owner_totals","from_table":"owners","joins":[...],"select":[{"table","column","alias"}],"aggregations":[{"function":"SUM","table","column","alias"}],"group_by":[{"table","column"}]}. Then read it: set "main_from":"owner_totals" and reference CTE columns by {"table":"owner_totals","column":"<alias>"} in select/top_per_group/filters. For "more distinct A than B per key", define TWO CTEs and join them with explicit_joins on the key, comparing their aliased counts in filters via value_ref. Omit when no per-group aggregate is needed.
- group_by: {"table","column"}. order_by: {"table","column","direction"} or {"aggregation_alias","direction"}.
- having MUST reference an aggregation alias: {"aggregation_alias":"alias_from_aggregations","op":">=","value":2,"connector":"AND"}.
- Never put HAVING aliases in {"table":"","column":"alias"} form.
- Do not add joins or relationship fields. If unsure, use empty lists.
- anti_exists: for "never / no matching / not <verbed> / does not exist / without" absence checks. Each item: {"target_table":"..","joins":[{"from_table","from_column","to_table","to_column"}],"where":[{"left":{"table","column"},"op":"=","right":{"table","column"}},{"left":{"table","column"},"op":"=","value":"x"}]}. Correlate to the outer table in "where". Omit (empty list) when the question has no absence requirement.
- top_per_group: for "highest/lowest/most/least/latest/earliest/second-highest PER <group>" (extrema or N-th within a group). Each item: {"table":"..","partition_by":[{"table","column"}],"order_by":{"table","column","direction":"desc|asc"},"rank":1,"include_ties":true}. Use desc for highest/most/latest, asc for lowest/least/earliest; rank=2 for "second". Omit (empty list) otherwise. (Ranking by an AGGREGATE total per group is not supported here.)
- universal: for "every/all/for all/only". "every X has Y": {"domain_table":"X","domain_filters":[{"left":{"table","column"},"op":"=","right":{outer ref}}],"must_exist":{"target_table":"..","joins":[...],"where":[...]}}. "only Z" (all rows good): {"bad_match":{"target_table":"..","joins":[...],"where":[<the forbidden condition>]}}. Compound per-element ("no pets OR has purchase"): use "inner":[{"exists":{...}},{"not_exists":{...}}] instead of must_exist. Use "domain_alias" when domain_table equals an outer table. Omit otherwise. (COUNT-DISTINCT "for all members of a set" is NOT handled here.)

Example - "Which owners have dogs?":
{"tables":["owners","pets"],"select":[{"table":"owners","column":"lastname"}],"filters":[{"table":"pets","column":"species","op":"=","value":"dog","connector":"AND"}],"aggregations":[],"group_by":[],"having":[],"order_by":[],"limit":null,"distinct":true}

Example - "Count pets by city":
{"tables":["owners","pets"],"select":[{"table":"owners","column":"city"}],"filters":[],"aggregations":[{"function":"COUNT","table":"pets","column":"petid","alias":"pet_count"}],"group_by":[{"table":"owners","column":"city"}],"having":[],"order_by":[{"aggregation_alias":"pet_count","direction":"DESC"}],"limit":null,"distinct":false}

Example - "List owners who own at least two pets":
{"tables":["owners","pets"],"select":[{"table":"owners","column":"oid"},{"table":"owners","column":"lastname"}],"filters":[],"aggregations":[{"function":"COUNT","table":"pets","column":"petid","alias":"pet_count"}],"group_by":[{"table":"owners","column":"oid"},{"table":"owners","column":"lastname"}],"having":[{"aggregation_alias":"pet_count","op":">=","value":2,"connector":"AND"}],"order_by":[],"limit":null,"distinct":false}

Example - "List foods never purchased":
{"tables":["foods"],"select":[{"table":"foods","column":"food_name"}],"filters":[],"aggregations":[],"group_by":[],"having":[],"order_by":[],"limit":null,"distinct":false,"anti_exists":[{"target_table":"purchases","where":[{"left":{"table":"purchases","column":"food_id"},"op":"=","right":{"table":"foods","column":"food_id"}}]}]}

Example - "Highest priced food per brand":
{"tables":["foods"],"select":[{"table":"foods","column":"food_name"},{"table":"foods","column":"price"}],"filters":[],"aggregations":[],"group_by":[],"having":[],"order_by":[],"limit":null,"distinct":false,"top_per_group":[{"table":"foods","partition_by":[{"table":"foods","column":"brand"}],"order_by":{"table":"foods","column":"price","direction":"desc"},"rank":1,"include_ties":true}]}

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
        "anti_exists": [],
        "top_per_group": [],
        "universal": [],
        "set_division": [],
        "aliases": [],
        "alias_joins": [],
        "alias_filters": [],
        "alias_select": [],
        "explicit_joins": [],
        "null_filters": [],
        "compound_filters": [],
        "derived_relations": [],
        "main_from": None,
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
                "group_by", "having", "order_by", "anti_exists", "top_per_group",
                "universal", "set_division", "aliases", "alias_joins",
                "alias_filters", "alias_select", "explicit_joins",
                "null_filters", "compound_filters", "derived_relations"):
        value = data.get(key)
        if isinstance(value, list):
            result[key] = value
    if isinstance(data.get("main_from"), str) and data["main_from"].strip():
        result["main_from"] = data["main_from"]

    limit = data.get("limit")
    if isinstance(limit, bool):          # guard against true/false
        limit = None
    elif limit is not None and not isinstance(limit, int):
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = None
    result["limit"] = limit

    # Repair common model mistake:
    # HAVING must use aggregation_alias, but models sometimes emit
    # {"table": "", "column": "pet_count", ...}. Convert that safely
    # when the column value matches one of the aggregation aliases.
    aliases = {
        agg.get("alias")
        for agg in result["aggregations"]
        if isinstance(agg, dict) and agg.get("alias")
    }
    repaired_having = []
    for item in result["having"]:
        if not isinstance(item, dict):
            continue

        if item.get("aggregation_alias"):
            repaired_having.append(item)
            continue

        column = item.get("column")
        if column in aliases:
            repaired_having.append({
                "aggregation_alias": column,
                "op": item.get("op"),
                "value": item.get("value"),
                "connector": item.get("connector") or "AND",
            })
            continue

        repaired_having.append(item)

    result["having"] = repaired_having
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


def _call_ir_model(prompt, num_predict, temperature=0):
    """One model call. Returns a parsed dict, or None if the response is empty,
    has no JSON, or the request fails."""
    try:
        print("CALLING MULTITABLE IR EXTRACTOR...", flush=True)
        result = get_provider().generate(
            prompt,
            options={"temperature": temperature, "num_predict": num_predict,
                     "think": False},
        )

        raw_text = (result.text or "").strip()
        print("RAW MULTITABLE IR EXTRACTOR:", raw_text, flush=True)
        if not raw_text:
            return None
        return extract_json(raw_text)
    except ProviderError as exc:
        print(f"MULTITABLE IR EXTRACTOR ERROR (provider): {exc}", flush=True)
        return None
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
    data = _call_ir_model(_primary_ir_prompt(question, tables_block, rel_block), 700)

    # Attempt 2: even shorter prompt when the first yields nothing usable.
    if not data:
        print("MULTITABLE IR EXTRACTOR: retrying with a shorter prompt", flush=True)
        data = _call_ir_model(_fallback_ir_prompt(question, tables_block), 500)

    if not data:
        print("MULTITABLE IR EXTRACTOR: no valid JSON after retry", flush=True)
        return _empty_ir_extraction()

    extraction = _normalize_ir_extraction(data)
    print("MULTITABLE IR EXTRACTION:", extraction, flush=True)
    return extraction


# ---------------------------------------------------------------------------
# Variant extraction (multi-candidate SQL selection)
# ---------------------------------------------------------------------------
# Each variant reframes the SAME task with a different emphasis + a non-zero
# temperature, so the model explores a different structural reading of the
# question. Diversity is the point: the candidate selector compares the
# variants' executed results against the primary path and the query-family
# builder, and agreement between independently-produced candidates is strong
# evidence of correctness.
_VARIANT_HINTS = {
    1: ("First decide which ONE structural construct fits the question best: "
        "anti_exists (absence: never/no/not), top_per_group (extremum per "
        "group), universal (every/all/only), set_division (has ALL members "
        "of a set), derived_relations (per-entity totals that are compared "
        "or ranked), explicit_joins+null_filters (outer join / include "
        "unmatched), aliases (pairs / self-join). Then fill ONLY that "
        "construct plus plain select/filters."),
    2: ("Be literal and minimal: prefer plain select/filters/aggregations, "
        "and use the special constructs ONLY when the question's wording "
        "forces them (never -> anti_exists, extremum per group -> "
        "top_per_group, every/all -> universal, pairs -> aliases, "
        "include-even-without -> explicit_joins)."),
}
_VARIANT_TEMPERATURES = {1: 0.3, 2: 0.55}


def extract_multitable_ir_extraction_variant(question: str, graph, variant: int = 1):
    """Variant LLM extraction for multi-candidate selection.

    Same output contract as extract_multitable_ir_extraction, but with a
    reframed prompt and a mild temperature so a second/third candidate can
    disagree with the primary one. Returns None (instead of an empty
    extraction) when the model yields nothing usable, so callers can simply
    skip the dead candidate.
    """
    tables_block, rel_block = _describe_graph(graph)
    hint = _VARIANT_HINTS.get(variant, _VARIANT_HINTS[1])
    temperature = _VARIANT_TEMPERATURES.get(variant, 0.3)

    prompt = (
        "/no_think\n"
        "Extract the query meaning as JSON only. No SQL, no prose.\n"
        f"{hint}\n\n"
        f"Tables:\n{tables_block}\n\n"
        f"Relationships (context only, do not invent joins):\n{rel_block}\n\n"
        f"Question: {question}\n"
        f"{_MULTITABLE_IR_GUIDE}"
    )
    data = _call_ir_model(prompt, 700, temperature=temperature)
    if not data:
        print(f"MULTITABLE IR VARIANT {variant}: no valid JSON", flush=True)
        return None
    extraction = _normalize_ir_extraction(data)
    print(f"MULTITABLE IR VARIANT {variant}:", extraction, flush=True)
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