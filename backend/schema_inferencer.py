def infer_schema(question: str):
    q = question.lower()

    table = "unknown_table"
    columns = ["*"]

    aggregation = None
    if "average" in q or "avg" in q:
        aggregation = "AVG"
    elif "count" in q:
        aggregation = "COUNT"

    group_by = None
    sort = None
    limit = None

    if "top" in q:
        words = q.split()

        for i, word in enumerate(words):
            if word == "top" and i + 1 < len(words):
                if words[i + 1].isdigit():
                    limit = int(words[i + 1])

    schema = f"{table}({', '.join(columns)})"

    return {
        "table": table,
        "columns": columns,
        "schema": schema,
        "aggregation": aggregation,
        "group_by": group_by,
        "sort": sort,
        "limit": limit,
    }