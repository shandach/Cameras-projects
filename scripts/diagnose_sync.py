"""
Diagnostic script: Check local DB state and test cloud sync flow
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from database.db import db
from database.models import Session, ClientVisit
from sqlalchemy import create_engine, text

def diagnose():
    print("=" * 60)
    print("  SYNC DIAGNOSTIC: Local DB -> Cloud DB")
    print("=" * 60)

    # === 1. LOCAL DB STATE ===
    print("\n[1] LOCAL DB STATE")
    with db.get_session() as sess:
        total_sessions = sess.query(Session).count()
        synced_sessions = sess.query(Session).filter(Session.is_synced == 1).count()
        unsynced_nocheck = sess.query(Session).filter(
            Session.is_synced == 0, Session.is_checkpoint == 0
        ).count()
        unsynced_checkpoint = sess.query(Session).filter(
            Session.is_synced == 0, Session.is_checkpoint == 1
        ).count()
        
        total_visits = sess.query(ClientVisit).count()
        synced_visits = sess.query(ClientVisit).filter(ClientVisit.is_synced == 1).count()
        unsynced_visits_nocheck = sess.query(ClientVisit).filter(
            ClientVisit.is_synced == 0, ClientVisit.is_checkpoint == 0
        ).count()
        unsynced_visits_check = sess.query(ClientVisit).filter(
            ClientVisit.is_synced == 0, ClientVisit.is_checkpoint == 1
        ).count()
    
    print(f"  Sessions:      {total_sessions} total")
    print(f"    is_synced=1: {synced_sessions}")
    print(f"    is_synced=0, is_checkpoint=0: {unsynced_nocheck}  <-- THESE should be sent")
    print(f"    is_synced=0, is_checkpoint=1: {unsynced_checkpoint}  <-- active checkpoints (skipped)")
    print(f"  Client Visits: {total_visits} total")
    print(f"    is_synced=1: {synced_visits}")
    print(f"    is_synced=0, is_checkpoint=0: {unsynced_visits_nocheck}  <-- THESE should be sent")
    print(f"    is_synced=0, is_checkpoint=1: {unsynced_visits_check}  <-- active checkpoints (skipped)")

    # === 2. SAMPLE UNSYNCED DATA ===
    print("\n[2] SAMPLE UNSYNCED SESSIONS (what sync_service would send)")
    sessions_data = db.get_unsynced_sessions(limit=5)
    if sessions_data:
        for s in sessions_data:
            print(f"  id={s['id']} place_id={s['place_id']} employee_id={s['employee_id']}")
            print(f"    start={s['start_time']} end={s['end_time']} dur={s['duration_seconds']}")
    else:
        print("  (EMPTY - no unsynced sessions to send!)")

    print("\n[3] SAMPLE UNSYNCED CLIENT VISITS")
    visits_data = db.get_unsynced_client_visits(limit=5)
    if visits_data:
        for v in visits_data:
            print(f"  id={v['id']} place_id={v['place_id']} employee_id={v['employee_id']}")
            print(f"    enter={v['enter_time']} exit={v['exit_time']} dur={v['duration_seconds']}")
    else:
        print("  (EMPTY - no unsynced visits to send!)")

    # === 3. CHECK CLOUD CONNECTION ===
    print("\n[4] CLOUD DB CONNECTION TEST")
    dsn = os.getenv("DB_DSN")
    if not dsn:
        print("  [FAIL] DB_DSN not found in .env!")
        return
    
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)
    
    try:
        engine = create_engine(dsn, connect_args={"connect_timeout": 10})
        with engine.connect() as conn:
            print("  [OK] Connected to Cloud DB")
            
            cloud_sessions = conn.execute(text("SELECT COUNT(*) FROM sessions")).scalar()
            cloud_visits = conn.execute(text("SELECT COUNT(*) FROM client_visits")).scalar()
            print(f"  Cloud sessions: {cloud_sessions}")
            print(f"  Cloud visits:   {cloud_visits}")
            
            # Check if local_id column exists
            cols = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='sessions' AND column_name='local_id'"
            )).fetchone()
            print(f"  sessions.local_id column exists: {cols is not None}")
            
            # Check UNIQUE constraint
            constraint = conn.execute(text(
                "SELECT constraint_name FROM information_schema.table_constraints "
                "WHERE table_name='sessions' AND constraint_name='uq_sessions_branch_local'"
            )).fetchone()
            print(f"  uq_sessions_branch_local constraint: {constraint is not None}")
            
            # Check BRANCH_ID
            branch_id = int(os.getenv("BRANCH_ID", "1"))
            print(f"\n  BRANCH_ID from .env: {branch_id}")
            
            # Check if branch exists in branches table
            branch = conn.execute(text(
                "SELECT id, name FROM branches WHERE id = :bid"
            ), {"bid": branch_id}).fetchone()
            if branch:
                print(f"  Branch in cloud: id={branch[0]} name='{branch[1]}'")
            else:
                print(f"  [WARN] Branch ID {branch_id} NOT FOUND in branches table!")
            
            # === 5. SIMULATE UPLOAD of first unsynced session ===
            print("\n[5] SIMULATE UPLOAD (DRY RUN)")
            if sessions_data:
                r = sessions_data[0]
                from datetime import datetime
                print(f"  Would send: local_id={r['id']}, branch_id={branch_id}")
                print(f"    place_id={r['place_id']}, employee_id={r['employee_id']}")
                print(f"    start_time={r['start_time']}")
                print(f"    end_time={r['end_time']}")
                
                # Check if place_id exists in cloud
                place = conn.execute(text(
                    "SELECT id, name FROM places WHERE id = :pid"
                ), {"pid": r['place_id']}).fetchone()
                if place:
                    print(f"  [OK] place_id={r['place_id']} exists in cloud: '{place[1]}'")
                else:
                    print(f"  [FAIL] place_id={r['place_id']} NOT in cloud places table!")
                    print(f"         INSERT will FAIL due to FK constraint!")
                
                # Check if employee_id exists in cloud
                if r['employee_id']:
                    emp = conn.execute(text(
                        "SELECT id, name FROM employees WHERE id = :eid"
                    ), {"eid": r['employee_id']}).fetchone()
                    if emp:
                        print(f"  [OK] employee_id={r['employee_id']} exists: '{emp[1]}'")
                    else:
                        print(f"  [FAIL] employee_id={r['employee_id']} NOT in cloud!")
                        print(f"         INSERT will FAIL due to FK constraint!")
                else:
                    print(f"  [WARN] employee_id is None")
            else:
                print("  No unsynced data to simulate")

    except Exception as e:
        print(f"  [FAIL] Cloud connection error: {e}")

    # === 6. CHECK FK CONSTRAINTS ===
    print("\n[6] FK CONSTRAINT CHECK: local place_ids vs cloud places")
    try:
        with engine.connect() as conn:
            cloud_place_ids = set(
                row[0] for row in conn.execute(text("SELECT id FROM places")).fetchall()
            )
        
        # Get all unique place_ids from unsynced local sessions
        all_unsynced = db.get_unsynced_sessions(limit=1000)
        local_place_ids = set(s['place_id'] for s in all_unsynced if s['place_id'])
        
        missing = local_place_ids - cloud_place_ids
        if missing:
            print(f"  [CRITICAL] {len(missing)} place_ids in local sessions NOT in cloud!")
            print(f"  Missing IDs: {sorted(missing)}")
            print(f"  These sessions will FAIL to sync due to FK constraint!")
        else:
            if local_place_ids:
                print(f"  [OK] All {len(local_place_ids)} local place_ids exist in cloud")
            else:
                print(f"  (No unsynced sessions with place_id)")
        
        # Same for employee_ids
        cloud_emp_ids = set(
            row[0] for row in engine.connect().execute(text("SELECT id FROM employees")).fetchall()
        )
        local_emp_ids = set(s['employee_id'] for s in all_unsynced if s['employee_id'])
        missing_emp = local_emp_ids - cloud_emp_ids
        if missing_emp:
            print(f"  [CRITICAL] {len(missing_emp)} employee_ids in local sessions NOT in cloud!")
            print(f"  Missing IDs: {sorted(missing_emp)}")
        else:
            if local_emp_ids:
                print(f"  [OK] All {len(local_emp_ids)} local employee_ids exist in cloud")
                
    except Exception as e:
        print(f"  [ERROR] FK check failed: {e}")
    
    print("\n" + "=" * 60)
    print("  DIAGNOSTIC COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    diagnose()
