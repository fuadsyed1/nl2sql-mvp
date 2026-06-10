import json
import re
import requests


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3:1.7b"


def extract_json(text: str, original_query: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        return {
            "status": "ready",
            "clean_query": original_query,
            "question": None,
            "error": "No complete JSON found in clarifier response."
        }

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {
            "status": "ready",
            "clean_query": original_query,
            "question": None,
            "error": "Invalid JSON from clarifier."
        }

    if parsed.get("status") == "ready":
        return {
            "status": "ready",
            "clean_query": parsed.get("clean_query") or original_query,
        }

    if parsed.get("status") == "need_clarification":
        return {
            "status": "need_clarification",
            "question": parsed.get("question") or "What information should I use to answer this query?"
        }

    return {
        "status": "ready",
        "clean_query": original_query,
        "question": None,
        "error": "Unknown clarifier status."
    }


def clarify_query(
    user_query: str,
    schema_text: str | None = None,
    output_template: str | None = None
) -> dict:
    schema_context = schema_text if schema_text else "No schema was provided."

    template_context = output_template if output_template else """
{
  "status": "ready" or "need_clarification",
  "clean_query": "clear version of the user's query",
  "question": "only if clarification is needed"
}
"""

    prompt = f"""
/no_think

You are a clarification decision system.

Your job is NOT to write SQL.
Your job is NOT to invent database results.
Your job is NOT to use hardcoded domain rules.

You will receive:
1. A user query
2. An available dataset schema, if provided
3. An expected output template

Your task:
Decide whether the user query has enough information to fill the expected output template.

If the query is clear enough:
Return JSON with:
{{
  "status": "ready",
  "clean_query": "minimal cleaned version of the user query"
}}

If the query is not clear enough:
Return JSON with:
{{
  "status": "need_clarification",
  "question": "short follow-up question asking only for the missing information"
}}

Decision principles:
- Use the provided schema if available.
- Do not ask for clarification if there is one clearly dominant interpretation.
- Ask for clarification when a term could reasonably mean multiple things.
- When clarification is needed, ask one short question that identifies the ambiguity.
- If no schema is provided, judge clarity from the natural language only.
- Do not ask for clarification only because a schema is missing.
- If the query clearly states a direction like lowest, highest, cheapest, most expensive, newest, oldest, treat it as clear.
- If status is "need_clarification", the JSON must include a specific "question" field.
- Ask clarification only when required information is missing.
- Ask the smallest possible follow-up question.
- Do not force the user to rewrite the whole query unless necessary.
- Do not add examples unless they are necessary.
- Do not rename tables, fields, entities, or attributes.
- Keep the user's original meaning.
- Return ONLY valid JSON.

Dataset schema:
{schema_context}

Expected output template:
{template_context}

User query:
{user_query}
"""

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 200
        }
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=60
        )
        response.raise_for_status()

        data = response.json()
        text = data.get("response", "").strip()

        print("RAW CLARIFIER TEXT:", text, flush=True)
        return extract_json(text, user_query)

    except requests.exceptions.RequestException:
        return {
            "status": "ready",
            "clean_query": user_query,
            "question": None,
            "error": "Clarifier unavailable, using original query."
        }

    except json.JSONDecodeError:
        return {
            "status": "ready",
            "clean_query": user_query,
            "question": None,
            "error": "Clarifier returned invalid JSON, using original query."
        }