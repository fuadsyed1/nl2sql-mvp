import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3:4b"

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
        "clean_query": "user query with only minimal clarification if needed"
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
    - If the query is clear, preserve the original meaning exactly.
    - Do not rename tables, entities, fields, or attributes.
    - Keep database words exactly as written by the user whenever possible.
    - Do not replace field names with synonyms.
    - Do not beautify or expand the query.
    - Only make minimal changes needed to remove ambiguity.
    - "customers" must stay "customers".
    - "income" must stay "income".
    - "employees" must stay "employees".
    - "salary" must stay "salary".
    - If the query is already clear, return it unchanged.
    - If clarification is required, ask a specific question about the missing field or condition.
    -  Do not ask generic questions like "What is missing?"
    - Always ask the user to rewrite the full query.
    - End every clarification question with: "Please write the full query again."
    - Example:
        "show best students"
        ->
        "What does best mean? GPA, grade, or score? Please write the full query again, for example: show top students by gpa."

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