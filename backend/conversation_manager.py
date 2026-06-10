import json
import re
import requests

from config import OLLAMA_URL, MODEL_NAME, DEFAULT_OPTIONS


# ---------------------------------------------------------------------------
# Fast keyword classifiers (no LLM needed for obvious replies)
# ---------------------------------------------------------------------------

_YES_PHRASES = frozenset({
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay",
    "go ahead", "create it", "generate it", "yes please",
    "do it", "sounds good", "alright", "fine",
})

_NO_PHRASES = frozenset({
    "no", "nope", "nah", "don't", "do not", "dont",
    "i will upload", "my own dataset", "i'll upload",
    "i have my own", "never mind", "cancel",
})

# A schema-like string: word( ... , ... )
_SCHEMA_RE = re.compile(r"^\s*\w+\s*\([^)]+,[^)]+\)\s*$")


def _keyword_classify(reply: str, pending_action: str) -> dict | None:
    """
    Try to classify the reply using simple rules before calling the LLM.
    Returns a result dict, or None if the reply is too ambiguous for keywords.
    """
    lowered = reply.strip().lower()

    # Clarification answers are always passed straight through
    if pending_action == "clarification_needed":
        return {"intent": "answer_clarification", "clarification": reply}

    # Schema in standard format: table(col1, col2, ...)
    if _SCHEMA_RE.match(reply):
        return {"intent": "provide_schema", "schema_text": reply.strip()}

    # Explicit yes / no words
    words = set(re.split(r"\W+", lowered))
    if words & _YES_PHRASES:
        return {"intent": "confirm_generate_schema"}
    if words & _NO_PHRASES:
        return {"intent": "deny_generate_schema"}

    return None  # ambiguous — let the LLM decide


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------

def _llm_classify(user_reply: str, pending_action: str, last_question: str) -> dict:
    """Call the LLM when keyword classification could not produce a confident result."""
    prompt = f"""\
/no_think

You are a conversation state classifier for a Natural Language to SQL system.

The system is waiting for a follow-up reply from the user.

Pending action: {pending_action}
Original user query: {last_question}
User's reply: {user_reply}

Classify the reply and return ONLY a single valid JSON object.

Possible outputs:

1. User agrees to generate a schema automatically:
{{"intent": "confirm_generate_schema"}}

2. User refuses and wants to provide their own data:
{{"intent": "deny_generate_schema"}}

3. User provides a schema string directly:
{{"intent": "provide_schema", "schema_text": "table_name(col1, col2, col3)"}}

4. User is answering a clarification question:
{{"intent": "answer_clarification", "clarification": "<their answer>"}}

5. User is asking a completely new, unrelated question:
{{"intent": "new_query"}}

Rules:
- Return only JSON. No explanation, no markdown.
- "yes", "sure", "go ahead", "create it" → confirm_generate_schema
- "no", "cancel", "I'll upload", "my own dataset" → deny_generate_schema
- A string like "orders(id, user_id, total)" → provide_schema
- An answer that directly addresses the pending clarification → answer_clarification
- Anything unrelated to the pending action → new_query
"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model":   MODEL_NAME,
                "prompt":  prompt,
                "stream":  False,
                "options": DEFAULT_OPTIONS,
            },
            timeout=60,
        )
        response.raise_for_status()
        raw = response.json().get("response", "").strip()
        print("RAW CONVERSATION MANAGER TEXT:", raw, flush=True)

        # try to find JSON anywhere in the response
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))

    except (requests.exceptions.RequestException, json.JSONDecodeError) as exc:
        print(f"CONVERSATION MANAGER LLM ERROR: {exc}", flush=True)

    # safe fallback: treat as a new query so the user isn't stuck
    return {"intent": "new_query"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def understand_followup(user_reply: str, pending_action: str, last_question: str) -> dict:
    """
    Classify a follow-up reply in the context of a pending conversation state.

    Returns one of:
      {"intent": "confirm_generate_schema"}
      {"intent": "deny_generate_schema"}
      {"intent": "provide_schema",       "schema_text": "..."}
      {"intent": "answer_clarification", "clarification": "..."}
      {"intent": "new_query"}
    """
    # Fast path: keyword / pattern matching
    result = _keyword_classify(user_reply, pending_action)
    if result is not None:
        print(f"CONVERSATION MANAGER (keyword): {result}", flush=True)
        return result

    # Slow path: LLM classification
    result = _llm_classify(user_reply, pending_action, last_question)
    print(f"CONVERSATION MANAGER (LLM): {result}", flush=True)
    return result