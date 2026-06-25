import sqlite3

conn = sqlite3.connect("app_data.db")
cursor = conn.cursor()

cursor.execute("DELETE FROM chat_state")

conn.commit()
conn.close()

print("Chat state cleared")