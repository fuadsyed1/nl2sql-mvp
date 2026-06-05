def infer_schema(question: str):
    q = question.lower()

    table_keywords = {
        "orders": ["order", "orders"],
        "customers": ["customer", "customers"],
        "employees": ["employee", "employees"],
        "products": ["product", "products"],
        "students": ["student", "students"],
    }

    field_keywords = {
        "id": ["id"],
        "name": ["name"],
        "customer": ["customer"],
        "income": ["income"],
        "salary": ["salary"],
        "price": ["price"],
        "gpa": ["gpa"],
        "department": ["department"],
    }

    table = None
    columns = []

    for table_name, keywords in table_keywords.items():
        if any(word in q for word in keywords):
            table = table_name
            break

    for field_name, keywords in field_keywords.items():
        if any(word in q for word in keywords):
            columns.append(field_name)

    aggregation = None
    if "average" in q or "avg" in q:
        aggregation = "AVG"
    elif "count" in q:
        aggregation = "COUNT"

    group_by = None

    if aggregation == "COUNT" and " by " in q:
        after_by = q.split(" by ", 1)[1].strip()

        for field_name in field_keywords:
            if field_name in after_by:
                group_by = field_name

                if field_name not in columns:
                    columns.append(field_name)

                break

    if table is None:
        table = "unknown_table"

    if not columns:
        columns = ["*"]

    sort = None
    limit = None

    if "top" in q:
        words = q.split()

        for i, word in enumerate(words):
            if word == "top" and i + 1 < len(words):
                if words[i + 1].isdigit():
                    limit = int(words[i + 1])

        if " by " in q:
            after_by = q.split(" by ", 1)[1].strip()

            for field_name in field_keywords:
                if field_name in after_by:
                    sort = {
                        "field": field_name,
                        "direction": "DESC"
                    }
                    break
    
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