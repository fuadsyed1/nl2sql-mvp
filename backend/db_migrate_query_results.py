import sqlite3

conn = sqlite3.connect("app_data.db")
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE queries ADD COLUMN results TEXT")
    print("Added results column to queries")
except Exception as e:
    print("queries:", e)

conn.commit()
conn.close()

print("Migration complete")