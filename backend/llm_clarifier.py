import json
import re
import requests

from config import OLLAMA_URL, MODEL_NAME, DEFAULT_OPTIONS


# ---------------------------------------------------------------------------
# Schema mismatch detection (pure Python, no LLM)
# ---------------------------------------------------------------------------

# Common English stop-words to ignore when comparing query tokens to schema
_STOP_WORDS = frozenset({
    "a", "an", "the", "in", "on", "at", "of", "to", "for", "and", "or",
    "is", "are", "was", "were", "be", "been", "with", "from", "that",
    "this", "all", "show", "get", "list", "find", "give", "me", "i",
    "what", "which", "where", "how", "who", "do", "does", "can", "by",
    "have", "has", "their", "my", "your", "its", "it", "not", "no",
    # generic schema-agnostic query words — should never trigger a mismatch alone
    "count", "rows", "records", "entries", "data", "total", "number",
    "many", "much", "any", "some", "every", "each", "first", "last",
    "top", "bottom", "highest", "lowest", "most", "least", "average",
    "avg", "sum", "min", "max", "select", "distinct", "unique",
})

def _query_tokens(text: str) -> set[str]:
    """Return meaningful lowercase words from the query."""
    return {
        w for w in re.findall(r"[a-z]+", text.lower())
        if w not in _STOP_WORDS and len(w) > 2
    }

def _schema_tokens(schema_text: str) -> set[str]:
    """Return all lowercase identifier tokens from the schema string."""
    return set(re.findall(r"[a-z][a-z0-9_]*", schema_text.lower()))

def _is_schema_mismatch(query: str, schema_text: str) -> bool:
    """
    Return True when the query appears completely unrelated to the schema.

    Strategy: split both into meaningful tokens and check overlap.
    If the query has zero tokens in common with the schema, it almost
    certainly belongs to a different domain.
    """
    q_tokens = _query_tokens(query)
    s_tokens = _schema_tokens(schema_text)

    # Need at least 2 meaningful tokens to make a confident domain judgement;
    # a 0- or 1-token query (e.g. "show everything") is too generic to flag.
    if len(q_tokens) < 2 or not s_tokens:
        return False

    overlap = q_tokens & s_tokens
    return len(overlap) == 0


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def _extract_json(text: str, fallback_query: str) -> dict:
    """
    Pull the first JSON object from *text*.
    Returns a safe 'ready' dict on any parse failure so the pipeline
    always gets a usable result.
    """
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if not match:
        # Try again with a greedier match in case the model wrapped things oddly
        match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        print("CLARIFIER: no JSON block found, passing query through.", flush=True)
        return {"status": "ready", "clean_query": fallback_query}

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        print(f"CLARIFIER: JSON parse error ({exc}), passing query through.", flush=True)
        return {"status": "ready", "clean_query": fallback_query}

    status = parsed.get("status")

    if status == "ready":
        return {
            "status":      "ready",
            "clean_query": parsed.get("clean_query") or fallback_query,
        }

    if status == "need_clarification":
        question = parsed.get("question", "").strip()
        return {
            "status":   "need_clarification",
            "question": question or "Could you clarify what you mean?",
        }

    print(f"CLARIFIER: unknown status {status!r}, passing query through.", flush=True)
    return {"status": "ready", "clean_query": fallback_query}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clarify_query(
    user_query: str,
    schema_text: str | None = None,
) -> dict:
    """
    Check whether the user's query is clear and compatible with the active schema.

    Returns one of:
      {"status": "ready",            "clean_query": "..."}
      {"status": "need_clarification","question":   "..."}
      {"status": "schema_mismatch",  "question":   "..."}   ← new

    Never raises.
    """
    # ------------------------------------------------------------------
    # Fast-path: detect schema mismatch without calling the LLM
    # ------------------------------------------------------------------
    if schema_text and _is_schema_mismatch(user_query, schema_text):
        print(
            f"CLARIFIER: schema mismatch detected.\n"
            f"  Query  tokens: {_query_tokens(user_query)}\n"
            f"  Schema tokens: {_schema_tokens(schema_text)}",
            flush=True,
        )
        return {
            "status": "schema_mismatch",
            "question": (
                f"Your active schema is '{schema_text.strip()}', which doesn't seem "
                f"related to your question. Would you like me to generate a new schema "
                f"for this query instead?"
            ),
        }

    schema_context = schema_text.strip() if schema_text else "No schema provided."

    prompt = f"""\
/no_think

You are a query clarification assistant for a Natural Language to SQL system.

Given a user query and an optional database schema, decide if the query is \
clear enough to generate SQL, then return ONE JSON object.

RETURN FORMAT

If the query is clear enough:
{{"status": "ready", "clean_query": "<minimal unambiguous rewrite of the query>"}}

If a critical piece of information is genuinely missing:
{{"status": "need_clarification", "question": "<one short specific question>"}}

RULES
- Default to "ready". Only ask when you cannot make a reasonable assumption.
- NEVER ask about sort direction when the query says highest/lowest/most/least/newest/oldest.
- NEVER ask which table to use when the schema has exactly one table.
- NEVER ask about columns that exist in the schema and match the query naturally.
- Keep clean_query short — just the core intent, no rephrasing needed.
- Return ONLY the JSON object. No markdown, no extra text.

SCHEMA
{schema_context}

USER QUERY
{user_query}
"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model":   MODEL_NAME,
                "prompt":  prompt,
                "stream":  False,
                "options": {**DEFAULT_OPTIONS, "num_predict": 150},
            },
            timeout=60,
        )
        response.raise_for_status()

        raw_text = response.json().get("response", "").strip()
        print("RAW CLARIFIER TEXT:", raw_text, flush=True)

        if not raw_text:
            # Model returned nothing — safe pass-through
            print("CLARIFIER: empty response from model, passing query through.", flush=True)
            return {"status": "ready", "clean_query": user_query}

        return _extract_json(raw_text, user_query)

    except requests.exceptions.RequestException as exc:
        print(f"CLARIFIER UNAVAILABLE: {exc} — passing query through.", flush=True)
        return {"status": "ready", "clean_query": user_query}