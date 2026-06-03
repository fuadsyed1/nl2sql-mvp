import sqlite3

DB_PATH = "students.db"

def execute_query(query):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(query)

    results = cursor.fetchall()

    conn.close()

    return results