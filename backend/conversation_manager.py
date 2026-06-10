import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3:1.7b"


def understand_followup(user_reply: str, pending_action: str, last_question: str) -> dict:
    
    
    reply = user_reply.strip()
    reply_lower = reply.lower()
    yes_words = [
        "yes",
        "yeah",
        "yep",
        "sure",
        "ok",
        "okay",
        "go ahead",
        "create it",
        "generate it",
        "yes please"
    ]

    for word in yes_words:
        if word in reply_lower:
            return {
                "intent": "confirm_generate_schema"
            }

    no_words = [
        "no",
        "don't",
        "do not",
        "i will upload",
        "my own dataset"
    ]

    if pending_action == "clarification_needed":
        return {
            "intent": "answer_clarification",
            "clarification": user_reply
        }

    for word in no_words:
        if word in reply_lower:
            return {
                "intent": "deny_generate_schema"
            }

    # existing schema detection continues below

    if (
        "(" in reply
        and ")" in reply
        and "," in reply
    ):
        return {
            "intent": "provide_schema",
            "schema_text": reply
        }
    if (
        "(" in reply
        and ")" in reply
        and "," in reply
    ):
        return {
            "intent": "provide_schema",
            "schema_text": reply
        }

    if (
        "=" in reply
        and "{" in reply
        and "}" in reply
    ):
        table_name = reply.split("=", 1)[0].strip()
        columns = (
            reply.split("{", 1)[1]
            .split("}", 1)[0]
            .strip()
        )

        return {
            "intent": "provide_schema",
            "schema_text": f"{table_name}({columns})"
        }
    prompt = f"""
You are a conversation manager for a Natural Language to SQL system.

Your job is NOT to generate SQL.

The system has a pending conversation state.

Pending action:
{pending_action}

Original user query:
{last_question}

User's latest reply:
{user_reply}

Return ONLY valid JSON.

Possible JSON outputs:

1. If user agrees to generate a schema:
{{
  "intent": "confirm_generate_schema"
}}

2. If user refuses schema generation:
{{
  "intent": "deny_generate_schema"
}}

3. If user provides schema manually:
{{
  "intent": "provide_schema",
  "schema_text": "customers(id, name, income)"
}}

4. If user is asking a completely new query:
{{
  "intent": "new_query"
}}

Rules:
- Return only JSON.
- Do not explain.
- Do not generate SQL.
- Do not use markdown.
- If the user says yes, yeah, sure, go ahead, create it, generate it, or similar, return confirm_generate_schema.
- If the user says no, don't, I will upload, or I will provide my own dataset, return deny_generate_schema.
- If the user gives a table structure, return provide_schema.
- If the message is unrelated to the pending question, return new_query.
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

    text = response.json().get("response", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "intent": "unknown",
            "raw_response": text
        }