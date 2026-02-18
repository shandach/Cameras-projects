import sqlite3
from config import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(client_visits)")
cols = cursor.fetchall()
for col in cols:
    print(col)
conn.close()
