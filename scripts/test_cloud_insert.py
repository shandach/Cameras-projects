"""
Test: try to insert one session into cloud DB manually
to see exactly what error sync_service would get
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from database.db import db
from sqlalchemy import create_engine, text
from datetime import datetime

def test_insert():
    # 1. Get one unsynced session
    sessions = db.get_unsynced_sessions(limit=1)
    if not sessions:
        print("[INFO] No unsynced sessions")
        return
    
    r = sessions[0]
    branch_id = int(os.getenv("BRANCH_ID", "1"))
    print(f"Testing INSERT with: local_id={r['id']}, branch_id={branch_id}")
    print(f"  place_id={r['place_id']}, employee_id={r['employee_id']}")
    print(f"  start_time={r['start_time']}")
    print(f"  end_time={r['end_time']}")
    
    # 2. Connect to cloud and try INSERT
    dsn = os.getenv("DB_DSN")
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)
    
    engine = create_engine(dsn)
    
    # Check if sessions table has branch_id FK
    with engine.connect() as conn:
        fk = conn.execute(text("""
            SELECT tc.constraint_name, ccu.table_name 
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu 
                ON tc.constraint_name = ccu.constraint_name
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'sessions' 
                AND tc.constraint_type = 'FOREIGN KEY'
                AND kcu.column_name = 'branch_id'
        """)).fetchall()
        print(f"\n  sessions.branch_id FK constraints: {fk}")
    
    # 3. Try the exact same INSERT that sync_service uses
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                INSERT INTO sessions 
                    (local_id, branch_id, place_id, employee_id,
                     start_time, end_time, duration_seconds,
                     session_date, is_synced, is_checkpoint, created_at)
                VALUES 
                    (:local_id, :branch_id, :place_id, :employee_id,
                     :start_time, :end_time, :duration_seconds,
                     :session_date, 1, 0, NOW())
                ON CONFLICT (branch_id, local_id) DO UPDATE SET
                    end_time = EXCLUDED.end_time,
                    duration_seconds = EXCLUDED.duration_seconds,
                    is_synced = 1,
                    is_checkpoint = 0
            """), {
                "local_id": r['id'],
                "branch_id": branch_id,
                "place_id": r['place_id'],
                "employee_id": r['employee_id'],
                "start_time": datetime.fromisoformat(r['start_time']),
                "end_time": (datetime.fromisoformat(r['end_time'])
                            if r['end_time'] else None),
                "duration_seconds": r['duration_seconds'],
                "session_date": datetime.fromisoformat(r['start_time']).date(),
            })
            conn.commit()
            print("\n[OK] INSERT succeeded!")
            
            # Verify
            count = conn.execute(text(
                "SELECT COUNT(*) FROM sessions WHERE branch_id=:bid AND local_id=:lid"
            ), {"bid": branch_id, "lid": r['id']}).scalar()
            print(f"[OK] Verified: found {count} row(s) with branch_id={branch_id}, local_id={r['id']}")
            
        except Exception as e:
            print(f"\n[FAIL] INSERT failed with error:")
            print(f"  {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_insert()
