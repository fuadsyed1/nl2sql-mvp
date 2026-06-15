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