import sqlite3

conn = sqlite3.connect("students.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY,
    name TEXT,
    age INTEGER,
    major TEXT,
    gpa REAL
)
""")

cursor.execute("""
INSERT INTO students (name, age, major, gpa)
VALUES
('Alice', 20, 'Computer Science', 3.8),
('Bob', 22, 'Mathematics', 3.4),
('Charlie', 21, 'Physics', 3.9)
""")

conn.commit()
conn.close()

print("Database creater successfully")