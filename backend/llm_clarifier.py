import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2"

def clarify_query(user_query: str) -> dict:
    prompt = f"""
    You are a query claridier for a Natural Language to SQL research project.

    Yout job is NOT to write SQL.

    You only check if the user's request is clear enough for a semantic parser.

    Return ONLY valid JSON.

    Allowed formats:

    If clear, you MUST use this exact status:
    {{
        "status": "ready",
        "clean_query": "clean rewritten version of the user query"
    }}

    If unclear:
    {{
        "status": "need_clarification",
        "question": "short question asking what is missing"
    }}

    Rules:
    - Do not generate SQL.
    - Do not invent database results.
    - Do not explain anything.
    - Only return JSON
    - If the query says "best", "top", or "highest" and includes "by GPA", "by grade", "by score" or another clear field, than it is clear.
    - If the query says "best", "top", or "highest" but does NOT includes a clear field, ask for clarification.
    - If the query is clear, rewrite it in simple clean English.

    User query:
    {user_query}
    """

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=30)
    response.raise_for_status()

    data = response.json()
    text = data.get("response", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "status": "error",
            "message": "LLM did not return valid JSON",
            "raw_response": text
        }