import sqlite3

conn = sqlite3.connect("app_data.db")
cursor = conn.cursor()

cursor.execute("DELETE FROM queries WHERE conversation_id IS NULL")
cursor.execute("DELETE FROM datasets WHERE conversation_id IS NULL")

conn.commit()
conn.close()

print("Legacy data cleaned.")