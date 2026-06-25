import sqlite3

conn = sqlite3.connect("app_data.db")
cursor = conn.cursor()

cursor.execute("""
DELETE FROM conversations
WHERE id NOT IN (
    SELECT DISTINCT conversation_id
    FROM queries
    WHERE conversation_id IS NOT NULL
)
""")

conn.commit()
conn.close()

print("Empty conversations deleted")