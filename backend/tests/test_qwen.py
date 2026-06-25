import requests

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "qwen3:4b",
        "prompt": """
Return ONLY valid JSON.

{
  "status": "ready"
}
""",
        "stream": False
    }
)

print(response.json()["response"])