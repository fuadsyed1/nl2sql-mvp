import json
import re
import requests

from config import OLLAMA_URL, MODEL_NAME, DEFAULT_OPTIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> reasoning blocks that qwen3 emits."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> dict:
    """
    Pull a JSON object out of a raw LLM response.

    Steps:
    1. Strip <think>...</think> blocks.
    2. Try to find a complete JSON object using a bracket-matching walk
       (handles nested objects like sort:{field:..., direction:...}).
    3. Fall back to greedy regex if the walk finds nothing.
    """
    clean = _strip_think_blocks(text)

    # Walk the string and find the outermost balanced {...}
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
                    # Not valid JSON yet — keep scanning for a later object
                    start = None

    raise ValueError(f"No valid JSON object found. Raw text: {text!r}")


def _normalize_nulls(value):
    """Recursively convert string 'null'/'None'/'' to Python None."""
    if value in ("null", "None", ""):
        return None
    if isinstance(value, dict):
        return {k: _normalize_nulls(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_nulls(item) for item in value]
    return value


def _validate_schema_info(data: dict) -> dict:
    """
    Guarantee every key the pipeline expects is present.
    Fills safe defaults for missing/empty values.
    """
    defaults = {
        "table":       "unknown_table",
        "columns":     [],
        "schema":      "",
        "aggregation": None,
        "group_by":    None,
        "sort":        None,
        "limit":       None,
    }
    result = {**defaults, **data}

    # columns must be a non-empty list of strings
    if not isinstance(result["columns"], list) or not result["columns"]:
        raw = result.get("columns", "")
        if isinstance(raw, str) and raw.strip():
            result["columns"] = [c.strip().lower() for c in raw.split(",") if c.strip()]
        else:
            result["columns"] = ["*"]

    # rebuild schema string if malformed
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
    question. Returns a validated schema_info dict. Never raises.
    """
    # Compact single-line example keeps the prompt small so the think block
    # (which qwen3 emits even with /no_think) doesn't eat the token budget.
    prompt = (
        "/no_think\n\n"
        "Return ONLY a JSON object inferring a database schema for the question below.\n"
        "No explanation, no markdown, no extra text — just the JSON.\n\n"
        'Example: {"table":"orders","columns":["id","user_id","total"],'
        '"schema":"orders(id,user_id,total)","aggregation":null,"group_by":null,"sort":null,"limit":null}\n\n'
        f"Question: {question}"
    )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model":   MODEL_NAME,
                "prompt":  prompt,
                "stream":  False,
                "options": {**DEFAULT_OPTIONS, "num_predict": 800},
            },
            timeout=90,
        )
        response.raise_for_status()

        raw_text = response.json().get("response", "").strip()
        print("RAW SCHEMA INFERENCER TEXT:", raw_text, flush=True)

        if not raw_text:
            raise ValueError("Empty response from model")

        raw_data   = _extract_json(raw_text)
        clean_data = _normalize_nulls(raw_data)
        result     = _validate_schema_info(clean_data)

        # Sanity check: reject the fallback sentinel in case the model
        # echoed our example values
        if result["table"] in ("unknown_table", "orders", "table_name"):
            raise ValueError(f"Model returned template/example table name: {result['table']!r}")

        print("SCHEMA INFERRED:", result["schema"], flush=True)
        return result

    except (requests.exceptions.RequestException, ValueError, json.JSONDecodeError) as exc:
        print(f"SCHEMA INFERENCER ERROR: {exc}", flush=True)
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