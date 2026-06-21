"""
ai_semantic_extractor.py
────────────────────────
Calls the local Ollama LLM to perform semantic understanding of a
natural-language question against a known schema.

Responsibilities:
  - Send question + schema to the model
  - Parse the model's JSON response
  - Return a raw dict that semantic_parser.validate_and_normalise() will
    validate and schema-bind

This module does NOT validate column names against the schema.
That is validate_and_normalise()'s job.
"""

import json
import re
import requests

from config import OLLAMA_URL, MODEL_NAME, DEFAULT_OPTIONS


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> blocks that qwen3 emits."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> dict | None:
    """
    Extract the first valid JSON object from raw LLM output.
    Uses bracket-depth walking so nested objects are handled correctly.
    Returns None if no valid JSON object is found.
    """
    clean = _strip_think_blocks(text)
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
                candidate = clean[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = None   # keep scanning for a later object

    return None


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
/no_think

You are an IR extractor for a natural-language database query system.

Your job is to understand the user's question and convert it into a simple backend-independent IR.

Do NOT generate SQL.
Do NOT explain anything.
Return ONLY one valid JSON object.
No markdown.
No extra text.

Schema:
{schema}

Question:
{question}

Return JSON exactly in this IR shape:

{{
  "operation": "retrieve",
  "entity": "table_name",
  "answer": "column_or_*",
  "measure": null,
  "measure_operation": null,
  "group_by": null,
  "order": null,
  "limit": null,
  "filters": []
}}

Meaning of each field:

operation:
- retrieve = simple select query
- filter = query with where/filter condition
- rank = top/bottom/best/worst/highest/lowest/most/least query
- aggregate = one summary value
- group_aggregate = summary grouped by a category

entity:
- table name from the schema

answer:
- the column the user wants to see in the final answer
- use "*" only if the user wants all columns

measure:
- numeric column being counted, summed, averaged, ranked, compared, or summarized
- null if no numeric measure is involved

measure_operation:
- SUM, AVG, COUNT, MIN, MAX, or null
- Use SUM when the measure column already stores counts, totals, quantities, sizes, amounts, or file counts
- Use AVG when the user asks for average or mean
- Use COUNT when the user asks how many rows/items exist and there is no numeric count column
- Use MIN or MAX when the user asks for minimum or maximum value

group_by:
- category column used for grouping
- usually same as answer for grouped/ranking-by-category questions
- null if no grouping is needed

order:
- "desc" for highest, largest, most, top, maximum
- "asc" for lowest, smallest, least, minimum
- null if no ordering is needed

limit:
- integer if user asks for one result, top N, first N, etc.
- use 1 for a single best/worst/highest/lowest answer
- null if no limit is implied

filters:
- list of filter objects
- each filter must look like:
  {{"field": "column_name", "operator": ">", "value": 1000}}
- use [] if there are no filters

Important:
- Use only table and column names from the schema.
- Do not return SQL-style aggregation objects.
- Do not return "aggregation".
- Do not return "select".
- Do not return "sort".
- Return only the IR fields listed above.

Examples:

Question:
Which extension has the most files?

JSON:
{{
  "operation": "rank",
  "entity": "uploaded_data",
  "answer": "extension",
  "measure": "files",
  "measure_operation": "SUM",
  "group_by": "extension",
  "order": "desc",
  "limit": 1,
  "filters": []
}}

Question:
Which extension has the least files?

JSON:
{{
  "operation": "rank",
  "entity": "uploaded_data",
  "answer": "extension",
  "measure": "files",
  "measure_operation": "SUM",
  "group_by": "extension",
  "order": "asc",
  "limit": 1,
  "filters": []
}}

Question:
Top 5 extensions by size

JSON:
{{
  "operation": "rank",
  "entity": "uploaded_data",
  "answer": "extension",
  "measure": "size",
  "measure_operation": "SUM",
  "group_by": "extension",
  "order": "desc",
  "limit": 5,
  "filters": []
}}

Question:
Average size by extension

JSON:
{{
  "operation": "group_aggregate",
  "entity": "uploaded_data",
  "answer": "extension",
  "measure": "size",
  "measure_operation": "AVG",
  "group_by": "extension",
  "order": null,
  "limit": null,
  "filters": []
}}

Question:
show files where size > 1000000

JSON:
{{
  "operation": "filter",
  "entity": "uploaded_data",
  "answer": "*",
  "measure": null,
  "measure_operation": null,
  "group_by": null,
  "order": null,
  "limit": 50,
  "filters": [
    {{"field": "size", "operator": ">", "value": 1000000}}
  ]
}}

Now return only the final JSON object.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_semantics(question: str, schema_text: str) -> dict | None:
    """
    Ask the LLM to extract the semantic meaning of *question* given *schema_text*.

    Returns a raw dict (not yet schema-validated) or None on any failure.
    The caller (app.py) passes the result to validate_and_normalise() before use.
    """
    prompt = _PROMPT_TEMPLATE.format(
        schema=schema_text.strip(),
        question=question.strip(),
    )

    try:
        print("CALLING SEMANTIC EXTRACTOR...", flush=True)

        response = requests.post(
            OLLAMA_URL,
            json={
                "model":  MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    **DEFAULT_OPTIONS,
                    "temperature": 0,
                    # qwen3:1.7b emits a <think> block even with /no_think.
                    # Give it enough budget: ~500 think + ~300 JSON = 800.
                    "num_predict": 800,
                },
            },
            timeout=90,
        )
        response.raise_for_status()

        raw_text = response.json().get("response", "").strip()
        print("RAW EXTRACTOR RESPONSE:", raw_text, flush=True)

        if not raw_text:
            print("SEMANTIC EXTRACTOR: empty response, retrying once...", flush=True)

            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        **DEFAULT_OPTIONS,
                        "temperature": 0,
                        "num_predict": 1000,
                    },
                },
                timeout=90,
            )

            response.raise_for_status()
            raw_text = response.json().get("response", "").strip()

            print("RAW EXTRACTOR RETRY RESPONSE:", raw_text, flush=True)

            if not raw_text:
                print("SEMANTIC EXTRACTOR: retry also empty", flush=True)
                return None

        data = _extract_json(raw_text)

        if data is None:
            print("SEMANTIC EXTRACTOR: no valid JSON found in response", flush=True)
            return None

        print("EXTRACTED SEMANTICS:", data, flush=True)
        return data

    except Exception as exc:
        print(f"SEMANTIC EXTRACTOR ERROR: {exc}", flush=True)
        return None


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    schema = "uploaded_data(extension, file_type, percent, size, allocated, files)"

    tests = [
        "show all files",
        "show top 5 files by size",
        "show files where extension is .dll",
        "show the largest allocated files",
        "which extension has the most files?",
        "which extension has the fewest files?",
        "average size by extension",
        "show files where size > 1000000",
    ]

    for question in tests:
        print(f"\nQ: {question!r}")
        result = extract_semantics(question, schema)
        print("RESULT:", json.dumps(result, indent=2))