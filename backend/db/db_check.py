import sqlite3

conn = sqlite3.connect("app_data.db")
cursor = conn.cursor()

print("CONVERSATIONS:")
cursor.execute("SELECT id, user_id, title, created_at FROM conversations ORDER BY id DESC")
print(cursor.fetchall())

print("\nQUERIES:")
cursor.execute("SELECT id, user_id, conversation_id, dataset_id, question, sql FROM queries ORDER BY id DESC")
print(cursor.fetchall())

print("\nDATASETS:")
cursor.execute("SELECT id, user_id, conversation_id, name, schema_text, file_type, file_path FROM datasets ORDER BY id DESC")
print(cursor.fetchall())

conn.close()