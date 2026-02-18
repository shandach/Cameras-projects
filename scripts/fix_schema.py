import sqlite3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE_PATH

def fix_schema():
    print(f"Fixing schema for {DATABASE_PATH}...")
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        # 1. Check if fix is needed
        cursor.execute("PRAGMA table_info(client_visits)")
        cols = cursor.fetchall()
        place_id_col = next((c for c in cols if c[1] == 'place_id'), None)
        
        if place_id_col and place_id_col[3] == 0:
            print("'place_id' is already nullable. No action needed.")
            return

        print("'place_id' is NOT NULL. Starting migration...")
        
        # 2. Rename existing table
        cursor.execute("ALTER TABLE client_visits RENAME TO client_visits_old")
        
        # 3. Create new table with correct schema (nullable place_id)
        # We copy the CREATE statement from models.py logic manually
        create_sql = """
        CREATE TABLE client_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            place_id INTEGER,
            employee_id INTEGER,
            track_id INTEGER NOT NULL,
            visit_date DATE,
            enter_time DATETIME NOT NULL,
            exit_time DATETIME,
            duration_seconds FLOAT,
            is_synced INTEGER DEFAULT 0,
            created_at DATETIME,
            FOREIGN KEY(place_id) REFERENCES places(id) ON DELETE SET NULL,
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        )
        """
        cursor.execute(create_sql)
        
        # 4. Copy data
        # Note: columns must match. We assume order is same or we specify.
        # Let's verify columns in old table to be safe? 
        # Actually easier to just valid insert.
        cursor.execute("""
            INSERT INTO client_visits (id, place_id, employee_id, track_id, visit_date, enter_time, exit_time, duration_seconds, is_synced, created_at)
            SELECT id, place_id, employee_id, track_id, visit_date, enter_time, exit_time, duration_seconds, is_synced, created_at
            FROM client_visits_old
        """)
        
        # 5. Drop old table
        cursor.execute("DROP TABLE client_visits_old")
        
        conn.commit()
        print("Schema fixed successfully.")
        
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_schema()
