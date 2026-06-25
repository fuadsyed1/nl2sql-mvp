import sqlite3

conn = sqlite3.connect("app_data.db")
cursor = conn.cursor()

# datasets table
try:
    cursor.execute(
        "ALTER TABLE datasets ADD COLUMN conversation_id INTEGER"
    )
    print("Added conversation_id to datasets")
except Exception as e:
    print("datasets:", e)

# queries table
try:
    cursor.execute(
        "ALTER TABLE queries ADD COLUMN conversation_id INTEGER"
    )
    print("Added conversation_id to queries")
except Exception as e:
    print("queries:", e)

conn.commit()
conn.close()

print("Migration complete")