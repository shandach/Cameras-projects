"""
Full sync pipeline audit:
1. Check old cloud data (branch_id/local_id state of 413 existing sessions)
2. Check for duplication risk between old migrated data and new sync
3. Check mock_mode flag
4. Check OccupancyEngine session creation / checkpoint flow
5. Check if end_time=None sessions can block sync
6. Check session_date field
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from database.db import db
from database.models import Session, ClientVisit
from sqlalchemy import create_engine, text

def audit():
    dsn = os.getenv("DB_DSN")
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)
    
    branch_id = int(os.getenv("BRANCH_ID", "1"))
    engine = create_engine(dsn)
    
    print("=" * 60)
    print("  FULL SYNC PIPELINE AUDIT")
    print("=" * 60)
    
    # --- 1. Cloud data state ---
    print("\n[1] CLOUD DATA: branch_id distribution in existing sessions")
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT branch_id, COUNT(*) FROM sessions GROUP BY branch_id ORDER BY branch_id"
        )).fetchall()
        for r in rows:
            label = "(NULL)" if r[0] is None else str(r[0])
            print(f"  branch_id={label}: {r[1]} sessions")
        
        rows = c.execute(text(
            "SELECT branch_id, COUNT(*) FROM client_visits GROUP BY branch_id ORDER BY branch_id"
        )).fetchall()
        for r in rows:
            label = "(NULL)" if r[0] is None else str(r[0])
            print(f"  branch_id={label}: {r[1]} client_visits")
    
    # --- 2. Duplication risk ---
    print("\n[2] DUPLICATION RISK: old data local_id vs new data local_id")
    with engine.connect() as c:
        # Check if old 413 sessions have local_id values that overlap with new unsynced
        old_local_ids = c.execute(text(
            "SELECT local_id FROM sessions WHERE branch_id IS NULL OR branch_id != :bid"
        ), {"bid": branch_id}).fetchall()
        old_ids = set(r[0] for r in old_local_ids if r[0] is not None)
        
        new_unsynced = db.get_unsynced_sessions(limit=1000)
        new_ids = set(s['id'] for s in new_unsynced)
        
        overlap = old_ids & new_ids
        if overlap:
            print(f"  [WARN] {len(overlap)} overlapping local_ids between old and new data")
            print(f"  Sample: {sorted(list(overlap))[:10]}")
            print(f"  BUT: ON CONFLICT uses (branch_id, local_id), so no collision if branch_id differs")
        else:
            print(f"  [OK] No overlapping local_ids")
    
    # --- 3. Mock mode ---
    print("\n[3] MOCK MODE CHECK")
    cloud_api = os.getenv("CLOUD_API_URL", "http://localhost:8000/api/v1")
    has_dsn = bool(os.getenv("DB_DSN"))
    is_localhost = "localhost" in cloud_api
    mock_mode = is_localhost and not has_dsn
    print(f"  CLOUD_API_URL: {cloud_api}")
    print(f"  DB_DSN exists: {has_dsn}")
    print(f"  mock_mode = ('localhost' in URL) AND (no DB_DSN) = {mock_mode}")
    if mock_mode:
        print(f"  [CRITICAL] mock_mode=True! sync_service marks as synced WITHOUT sending to cloud!")
    else:
        print(f"  [OK] mock_mode=False, real cloud sync active")
    
    # --- 4. Local sessions with potential issues ---
    print("\n[4] LOCAL DB: sessions that might block sync")
    with db.get_session() as s:
        # Sessions with end_time = None and is_checkpoint=0
        no_end = s.query(Session).filter(
            Session.is_synced == 0,
            Session.is_checkpoint == 0,
            Session.end_time == None
        ).count()
        print(f"  Unsynced sessions with end_time=NULL (not checkpoint): {no_end}")
        if no_end > 0:
            print(f"  [WARN] sync_service will send end_time=None -> cloud gets NULL end_time")
        
        # Sessions with place_id = None
        no_place = s.query(Session).filter(
            Session.is_synced == 0,
            Session.place_id == None
        ).count()
        print(f"  Unsynced sessions with place_id=NULL: {no_place}")
        if no_place > 0:
            print(f"  [WARN] FK on cloud may reject NULL place_id")
        
        # Sessions with employee_id = None
        no_emp = s.query(Session).filter(
            Session.is_synced == 0,
            Session.employee_id == None
        ).count()
        print(f"  Unsynced sessions with employee_id=NULL: {no_emp}")
        
        # Sessions with duration_seconds = 0 or NULL
        zero_dur = s.query(Session).filter(
            Session.is_synced == 0,
            Session.is_checkpoint == 0,
            Session.duration_seconds == 0
        ).count()
        null_dur = s.query(Session).filter(
            Session.is_synced == 0,
            Session.is_checkpoint == 0,
            Session.duration_seconds == None
        ).count()
        print(f"  Unsynced sessions with duration=0: {zero_dur}")
        print(f"  Unsynced sessions with duration=NULL: {null_dur}")
    
    # --- 5. Sequence check ---
    print("\n[5] SEQUENCE STATE (post-fix)")
    with engine.connect() as c:
        for table in ["sessions", "client_visits"]:
            seq = c.execute(text(f"SELECT last_value FROM {table}_id_seq")).scalar()
            max_id = c.execute(text(f"SELECT COALESCE(MAX(id),0) FROM {table}")).scalar()
            status = "[OK]" if seq > max_id else "[FAIL] seq <= max_id!"
            print(f"  {table}: sequence={seq}, max_id={max_id} {status}")
    
    # --- 6. Cloud FK constraints check ---
    print("\n[6] CLOUD FK CONSTRAINTS on sessions/client_visits")
    with engine.connect() as c:
        for table in ["sessions", "client_visits"]:
            fks = c.execute(text("""
                SELECT kcu.column_name, ccu.table_name, ccu.column_name as ref_col
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                WHERE tc.table_name = :tbl AND tc.constraint_type = 'FOREIGN KEY'
            """), {"tbl": table}).fetchall()
            if fks:
                for fk in fks:
                    print(f"  {table}.{fk[0]} -> {fk[1]}.{fk[2]}")
            else:
                print(f"  {table}: no FK constraints")
    
    # --- 7. Test batch of 5 inserts ---
    print("\n[7] TEST: insert 5 unsynced sessions to cloud")
    sessions_data = db.get_unsynced_sessions(limit=5)
    if not sessions_data:
        print("  No unsynced sessions to test")
    else:
        from datetime import datetime
        with engine.connect() as c:
            success = 0
            for r in sessions_data:
                try:
                    c.execute(text("""
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
                    success += 1
                except Exception as e:
                    print(f"  [FAIL] id={r['id']}: {e}")
            c.commit()
            print(f"  [OK] {success}/{len(sessions_data)} inserted successfully")
            
            # Mark them as synced locally
            if success == len(sessions_data):
                ids = [r['id'] for r in sessions_data]
                db.mark_as_synced("session", ids)
                print(f"  [OK] Marked {len(ids)} as synced in local DB")
    
    print("\n" + "=" * 60)
    print("  AUDIT COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    audit()
