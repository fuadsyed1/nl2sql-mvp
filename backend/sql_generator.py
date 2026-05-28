import re
def generate_sql_from_prompt(prompt: str) -> str:
    prompt = prompt.lower()

    columns = []

    if "student id" in prompt or "id" in prompt:
        columns.append("student_id")

    if "name" in prompt:
        columns.append("name")

    if "gpa" in prompt:
        columns.append("gpa")

    if not columns:
        columns = ["*"]

    selected_columns = ", ".join(columns)

    where_clause = ""

    gpa_match = re.search(r"gpa above (\d+(\.\d+)?)", prompt)

    if gpa_match:
        gpa_value = gpa_match.group(1)
        where_clause = f" WHERE gpa > {gpa_value}"

    sql = f"SELECT {selected_columns} FROM students{where_clause};"

    return sql