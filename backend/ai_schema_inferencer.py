import json
import re
import requests


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3:1.7b"


def extract_json(text: str):
    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise ValueError("No JSON object found in AI response.")

    return json.loads(match.group(0))

def extract_json(text: str):
    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise ValueError("No JSON object found in AI response.")

    return json.loads(match.group(0))


def normalize_nulls(value):
    if value == "null" or value == "None" or value == "":
        return None

    if isinstance(value, dict):
        return {
            key: normalize_nulls(val)
            for key, val in value.items()
        }

    if isinstance(value, list):
        return [
            normalize_nulls(item)
            for item in value
        ]

    return value

def infer_schema_with_ai(question: str):
    prompt = f"""
/no_think

You are an AI query-schema inferencer.

Infer a possible database-style schema and query metadata from the user's natural language question.

Return ONLY valid JSON.

Required JSON shape:
{{
  "table": "table_name",
  "columns": ["column1", "column2"],
  "schema": "table_name(column1, column2)",
  "aggregation": "COUNT | AVG | SUM | MIN | MAX | null",
  "group_by": "column_name | null",
  "sort": {{
    "field": "column_name",
    "direction": "ASC | DESC"
  }},
  "limit": null
}}

User question:
{question}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False
        },
        timeout=60
    )

    response.raise_for_status()

    raw_text = response.json()["response"].strip()

    schema_info = extract_json(raw_text)

    return normalize_nulls(schema_info)