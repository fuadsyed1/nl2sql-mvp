import json
import requests
from datetime import datetime

API_URL = "http://127.0.0.1:8000/query"

USER_ID = 4
CONVERSATION_ID = 52

queries = [
    "Which extension has the most files?",
    "Which extension has the least files?",
    "Top 5 extensions by size",
    "Top 10 extensions by allocated",
    "Average size by extension",
    "Average allocated space by extension",
    "Highest allocated space",
    "Lowest allocated space",
    "Highest size",
    "Lowest size",
    "Top 5 file types by size",
    "Top 5 file types by files",
    "Average size by file_type",
    "Average allocated by file_type",
    "Which file_type has the most files?",
    "Which file_type has the least files?",
    "Show files where size > 1000000",
    "Show files where allocated > 1000000",
    "Show files where files > 1000",
    "Show files where percent > 1",
    "Top 3 extensions by percent",
    "Top 3 file types by percent",
    "Average percent by extension",
    "Which extension has the highest allocated space?",
    "Which extension has the lowest allocated space?",
]

output_file = f"ir_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

with open(output_file, "w", encoding="utf-8") as f:
    f.write("IR QUERY TEST RESULTS\n")
    f.write("=" * 80 + "\n\n")

    for i, question in enumerate(queries, start=1):
        f.write(f"TEST {i}\n")
        f.write("-" * 80 + "\n")
        f.write(f"QUESTION:\n{question}\n\n")

        payload = {
            "question": question,
            "user_id": USER_ID,
            "conversation_id": CONVERSATION_ID,
        }

        try:
            response = requests.post(API_URL, json=payload, timeout=120)

            f.write(f"HTTP STATUS:\n{response.status_code}\n\n")

            try:
                data = response.json()
            except Exception:
                f.write("RAW RESPONSE:\n")
                f.write(response.text + "\n\n")
                continue

            f.write("FRONTEND DISPLAY DATA\n")
            f.write("-" * 40 + "\n")
            f.write(f"TYPE:\n{data.get('type')}\n\n")
            f.write(f"CLEAN QUERY:\n{data.get('clean_query')}\n\n")
            f.write(f"SQL:\n{data.get('sql')}\n\n")
            f.write("RESULTS:\n")
            f.write(json.dumps(data.get("results"), indent=2) + "\n\n")

            f.write("BACKEND SEMANTIC DATA\n")
            f.write("-" * 40 + "\n")
            f.write("SEMANTIC:\n")
            f.write(json.dumps(data.get("semantic"), indent=2) + "\n\n")

            if data.get("error"):
                f.write("ERROR:\n")
                f.write(str(data.get("error")) + "\n\n")

        except Exception as e:
            f.write("REQUEST FAILED:\n")
            f.write(str(e) + "\n\n")

        f.write("=" * 80 + "\n\n")

print(f"Saved test results to: {output_file}")