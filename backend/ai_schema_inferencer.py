import json
import re
import requests

from config import OLLAMA_URL, MODEL_NAME, DEFAULT_OPTIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """Pull the first {...} block out of a raw LLM response and parse it."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in AI response. Raw text: {text!r}")
    return json.loads(match.group(0))


def _normalize_nulls(value):
    """Recursively convert string 'null'/'None'/'' to Python None."""
    if value in ("null", "None", ""):
        return None
    if isinstance(value, dict):
        return {k: _normalize_nulls(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_nulls(item) for item in value]
    return value


_REQUIRED_KEYS = {"table", "columns", "schema", "aggregation", "group_by", "sort", "limit"}

def _validate_schema_info(data: dict) -> dict:
    """
    Make sure every required key is present and columns is always a list.
    Missing keys are filled with safe defaults so the rest of the pipeline
    never has to guard against KeyError.
    """
    defaults = {
        "table": "unknown_table",
        "columns": [],
        "schema": "",
        "aggregation": None,
        "group_by": None,
        "sort": None,
        "limit": None,
    }
    result = {**defaults, **data}

    # columns must be a non-empty list of strings
    if not isinstance(result["columns"], list) or not result["columns"]:
        # attempt to recover from a comma-separated string
        raw = result.get("columns", "")
        if isinstance(raw, str) and raw.strip():
            result["columns"] = [c.strip().lower() for c in raw.split(",") if c.strip()]
        else:
            result["columns"] = ["*"]

    # rebuild schema string if it looks wrong or is missing
    if not result["schema"] or "(" not in result["schema"]:
        cols = ", ".join(result["columns"])
        result["schema"] = f"{result['table']}({cols})"

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def infer_schema_with_ai(question: str) -> dict:
    """
    Ask the LLM to infer a plausible database schema from a natural-language
    question.  Returns a validated schema_info dict ready for the rest of the
    pipeline.  Never raises — falls back to a minimal safe default on any error.
    """
    prompt = f"""\
/no_think

You are a database schema inference assistant.

Given a natural language question, infer the most likely relational database \
schema that could answer it.

Return ONLY a single valid JSON object — no markdown, no explanation.

Required shape:
{{
  "table": "table_name",
  "columns": ["col1", "col2", "col3"],
  "schema": "table_name(col1, col2, col3)",
  "aggregation": "COUNT" | "AVG" | "SUM" | "MIN" | "MAX" | null,
  "group_by": "column_name" | null,
  "sort": {{"field": "column_name", "direction": "ASC" | "DESC"}} | null,
  "limit": <integer> | null
}}

Rules:
- Use snake_case for all table and column names.
- Include only columns that are relevant to the question.
- Set aggregation only when the question clearly asks for a count, average, sum, min, or max.
- Set group_by only when the question groups results by a category.
- Set sort only when the question implies an ordering.
- Set limit only when the question asks for a specific number of results (e.g. "top 5").

Question:
{question}
"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": DEFAULT_OPTIONS,
            },
            timeout=60,
        )
        response.raise_for_status()

        raw_text = response.json().get("response", "").strip()
        print("RAW SCHEMA INFERENCER TEXT:", raw_text, flush=True)

        raw_data   = _extract_json(raw_text)
        clean_data = _normalize_nulls(raw_data)
        return _validate_schema_info(clean_data)

    except (requests.exceptions.RequestException, ValueError, json.JSONDecodeError) as exc:
        print(f"SCHEMA INFERENCER ERROR: {exc}", flush=True)
        # safe fallback so the pipeline can continue
        fallback_table = "inferred_table"
        return {
            "table":       fallback_table,
            "columns":     ["*"],
            "schema":      f"{fallback_table}(*)",
            "aggregation": None,
            "group_by":    None,
            "sort":        None,
            "limit":       None,
        }