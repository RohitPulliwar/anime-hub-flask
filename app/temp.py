import sqlite3

conn = get_db_connection()
cursor = conn.cursor()


cursor.execute("""CREATE TABLE quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    exp_earned INTEGER NOT NULL,
    attempt_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);""")
conn.commit()
conn.close()

print("Columns added successfully!")