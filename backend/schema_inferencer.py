def infer_schema_from_prompt(prompt):
    text = prompt.lower()
    words = text.replace(",", "").replace("?", "").split()

    if "average" in words or "avg" in words:
        avg_index = words.index("average") if "average" in words else words.index("avg")

        if avg_index + 1 < len(words):
            field = words[avg_index + 1]

            if "of" in words:
                of_index = words.index("of")

                if of_index + 1 < len(words):
                    entity = words[of_index + 1]

                    table_name = entity if entity.endswith("s") else entity + "s"
                    columns = ["id", "name", field]
                    schema = f"{table_name}({', '.join(columns)})"

                    return {
                        "table": table_name,
                        "columns": columns,
                        "schema": schema
                    }

    entity = None
    columns = ["id", "name"]

    action_words = ["show", "list", "get", "find", "count"]
    skip_entity_words = ["top", "highest", "lowest", "average", "avg"]

    for i, word in enumerate(words):
        if word in action_words:
            j = i + 1

            while j < len(words) and (
                words[j] in skip_entity_words or words[j].isdigit()
            ):
                j += 1

            if j < len(words):
                entity = words[j]
                break

    if not entity:
        entity = "items"

    if not entity.endswith("s"):
        table_name = entity + "s"
    else:
        table_name = entity

    ignore_words = {
        "show", "list", "get", "find", "count",
        "all", "with", "where", "whose", "having",
        "above", "below", "over", "under",
        "greater", "less", "than", "equal", "to",
        "top", "by", "sorted", "order",
        "average", "avg", "highest", "lowest",
        "and", "or", "the", "a", "an", "of", "is", "are"
    }

    for word in words:
        if word.isdigit():
            continue

        if word in ignore_words:
            continue

        if word == table_name or word == table_name.rstrip("s"):
            continue

        if word not in columns:
            columns.append(word)

    schema = f"{table_name}({', '.join(columns)})"

    return {
        "table": table_name,
        "columns": columns,
        "schema": schema
    }