import re

def parse_schema(schema_text: str):
    tables = {}

    pattern = r"(\w+)\s*\((.*?)\)"
    matches = re.findall(pattern, schema_text)

    for table_name, columns_text in matches:
        columns = [col.strip() for col in columns_text.split(",")]
        tables[table_name.lower()] = columns

    return tables


def generate_sql(user_input: str, schema: str):
    user_input = user_input.lower()
    tables = parse_schema(schema)

    if not tables:
        return "ERROR: No valid schema found"

    # Use first table for now
    table_name = list(tables.keys())[0]
    columns = tables[table_name]

    base_query = f"SELECT * FROM {table_name}"

    words = user_input.split()

    # GPA / numeric comparison support
    for column in columns:
        clean_column = column.lower()

        if clean_column in user_input:
            for word in words:
                try:
                    number = float(word)

                    if "above" in user_input or "greater" in user_input or "over" in user_input:
                        return f"{base_query} WHERE {clean_column} > {number};"

                    if "below" in user_input or "less" in user_input or "under" in user_input:
                        return f"{base_query} WHERE {clean_column} < {number};"

                except ValueError:
                    pass

    return base_query + ";"