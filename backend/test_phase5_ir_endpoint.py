import json
import requests


BASE_URL = "http://127.0.0.1:8000"
DATABASE_ID = 1

QUESTIONS = [
    "Show owners and their pets",
    "Which owners have dogs?",
    "Count pets by city",
    "List all owners",
    "Show all pets",
    "Which pets are dogs?",
    "Which owners live in Seattle?",
    "Show pet names and species",
    "Show owners, pets, and cities",
    "Count all pets",
    "Count pets by species",
    "Count owners by city",
    "Show distinct pet species",
]


def run_test(question):
    url = f"{BASE_URL}/database/{DATABASE_ID}/ir"
    response = requests.post(url, json={"question": question}, timeout=120)
    response.raise_for_status()
    data = response.json()

    extraction = data.get("ir", {})
    validation = data.get("validation", {})

    passed = (
        data.get("success") is True
        and validation.get("valid") is True
        and bool(extraction.get("tables"))
    )

    return {
        "question": question,
        "passed": passed,
        "tables": extraction.get("tables", []),
        "select": extraction.get("select", []),
        "filters": extraction.get("filters", []),
        "aggregations": extraction.get("aggregations", []),
        "group_by": extraction.get("group_by", []),
        "errors": validation.get("errors", []),
        "warnings": validation.get("warnings", []),
    }


def main():
    results = []

    for question in QUESTIONS:
        print(f"\nTesting: {question}")
        result = run_test(question)
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        print(status)
        print(json.dumps(result, indent=2))

    total = len(results)
    passed = sum(1 for item in results if item["passed"])

    print("\n==============================")
    print(f"Phase 5 IR tests passed: {passed}/{total}")
    print("==============================")


if __name__ == "__main__":
    main()