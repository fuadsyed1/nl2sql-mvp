import re


def parse_schema(schema_text: str):
    tables = {}

    pattern = r"(\w+)\s*\((.*?)\)"
    matches = re.findall(pattern, schema_text)

    for table_name, columns_text in matches:
        columns = [col.strip().lower() for col in columns_text.split(",")]
        tables[table_name.lower()] = columns

    return tables


def generate_sql_from_semantic(semantic: dict, schema: str):
    tables = parse_schema(schema)

    if not tables:
        return "ERROR: No valid schema found"

    relational = semantic.get("relational", {})

    table_name = relational.get("entity")

    if not table_name:
        table_name = list(tables.keys())[0]

    table_name = table_name.lower()

    if table_name not in tables:
        return f"ERROR: Table '{table_name}' not found in schema"

    schema_columns = tables[table_name]

    selected_columns = relational.get("select", ["*"])

    if selected_columns == ["*"] or not selected_columns:
        select_part = "*"
    else:
        valid_columns = [
            col for col in selected_columns
            if col.lower() in schema_columns
        ]

        if not valid_columns:
            select_part = "*"
        else:
            select_part = ", ".join(valid_columns)

    aggregation = relational.get("aggregation")

    group_by = relational.get("group_by")

    if aggregation:
        function = aggregation.get("function")
        field = aggregation.get("field", "*")

        if field != "*" and field.lower() not in schema_columns:
            return f"ERROR: Column '{field}' not found in schema"

        select_part = f"{function}({field})"

    query = f"SELECT {select_part} FROM {table_name}"

    filters = relational.get("filters", [])

    if filters:
        where_parts = []

        for condition in filters:
            field = condition.get("field")
            operator = condition.get("operator")
            value = condition.get("value")

            if field not in schema_columns:
                return f"ERROR: Column '{field}' not found in schema"

            if isinstance(value, str):
                value = f"'{value}'"

            where_parts.append(f"{field} {operator} {value}")

        query += " WHERE " + " AND ".join(where_parts)

    group_by = relational.get("group_by")

    if group_by:
        if group_by not in schema_columns:
            return f"ERROR: Column '{group_by}' not found in schema"

        if aggregation:
            query = f"SELECT {group_by}, {select_part} FROM {table_name}"

        query += f" GROUP BY {group_by}"

    sort = relational.get("sort")

    if sort:
        field = sort.get("field")
        direction = sort.get("direction", "ASC")

        if field in schema_columns:
            query += f" ORDER BY {field} {direction}"

    limit = relational.get("limit")

    if limit:
        query += f" LIMIT {limit}"

    return query + ";"