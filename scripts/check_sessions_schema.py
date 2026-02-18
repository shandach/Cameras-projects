import sqlite3
import sys
import os

# Add parent directory to sys.path to allow importing config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_PATH

def check_sessions_schema():
    print(f"Checking schema for {DATABASE_PATH}...")
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(sessions)")
    cols = cursor.fetchall()
    for col in cols:
        print(col)
        
    conn.close()

if __name__ == "__main__":
    check_sessions_schema()
