def validate_query(query):
    blocked_words = [
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "ALTER",
        "TRUNCATE"
    ]

    upper_query = query.upper()

    for word in blocked_words:
        if word in upper_query:
            return False

    return True