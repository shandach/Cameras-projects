import sqlite3
import sys
import os

# Add parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_PATH

def fix_sessions_schema():
    print(f"Fixing sessions schema for {DATABASE_PATH}...")
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        # 1. Check if fix is needed
        cursor.execute("PRAGMA table_info(sessions)")
        cols = cursor.fetchall()
        place_id_col = next((c for c in cols if c[1] == 'place_id'), None)
        
        if place_id_col and place_id_col[3] == 0:
            print("'place_id' is already nullable. No action needed.")
            return

        print("'place_id' is NOT NULL. Starting migration...")
        
        # 2. Rename existing table
        cursor.execute("ALTER TABLE sessions RENAME TO sessions_old")
        
        # 3. Create new table with correct schema (nullable place_id)
        create_sql = """
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            place_id INTEGER,
            employee_id INTEGER,
            start_time DATETIME NOT NULL,
            end_time DATETIME,
            duration_seconds FLOAT,
            session_date DATE,
            is_synced INTEGER DEFAULT 0,
            created_at DATETIME,
            FOREIGN KEY(place_id) REFERENCES places(id) ON DELETE SET NULL,
            FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE SET NULL
        )
        """
        cursor.execute(create_sql)
        
        # 4. Copy data
        cursor.execute("""
            INSERT INTO sessions (id, place_id, employee_id, start_time, end_time, duration_seconds, session_date, is_synced, created_at)
            SELECT id, place_id, employee_id, start_time, end_time, duration_seconds, session_date, is_synced, created_at
            FROM sessions_old
        """)
        
        # 5. Drop old table
        cursor.execute("DROP TABLE sessions_old")
        
        conn.commit()
        print("Sessions schema fixed successfully.")
        
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_sessions_schema()
