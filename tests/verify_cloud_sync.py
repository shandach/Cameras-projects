
import sys
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import db
from core.sync_service import sync_service
from database.models import Session, ClientVisit

def test_sync_lifecycle():
    print("☁️ Testing Cloud Sync Lifecycle...")
    
    # 1. Create Dummy Data
    print("[1] Creating unsynced records...")
    with db.get_session() as session:
        # Create Employee Session
        new_session = Session(
            place_id=1,
            employee_id=1,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(minutes=30),
            duration_seconds=1800,
            is_synced=0
        )
        session.add(new_session)
        
        # Create Client Visit
        new_visit = ClientVisit(
            place_id=1,
            employee_id=1,
            track_id=999,
            enter_time=datetime.now(),
            exit_time=datetime.now() + timedelta(minutes=5),
            duration_seconds=300,
            is_synced=0
        )
        session.add(new_visit)
        session.commit()
        
        # Get IDs
        session_id = new_session.id
        visit_id = new_visit.id
        print(f"    -> Created Session ID: {session_id}")
        print(f"    -> Created Visit ID: {visit_id}")

    # 2. Verify Unsynced State
    unsynced_sessions = db.get_unsynced_sessions(limit=10)
    unsynced_visits = db.get_unsynced_client_visits(limit=10)
    
    sess_found = any(s['id'] == session_id for s in unsynced_sessions)
    visit_found = any(v['id'] == visit_id for v in unsynced_visits)
    
    assert sess_found, "Session should be in unsynced list"
    assert visit_found, "Visit should be in unsynced list"
    print("[2] ✅ Records found in unsynced queue")
    
    # 3. Trigger Sync (Mock Mode)
    # Ensure mock mode is ON
    sync_service.mock_mode = True
    print("[3] Triggering Sync (Mock Mode)...")
    
    sync_service._sync_data()
    
    # 4. Verify Synced State
    with db.get_session() as session:
        s = session.query(Session).get(session_id)
        v = session.query(ClientVisit).get(visit_id)
        
        assert s.is_synced == 1, f"Session {session_id} should be synced (is_synced=1), got {s.is_synced}"
        assert v.is_synced == 1, f"Visit {visit_id} should be synced (is_synced=1), got {v.is_synced}"
        
        print(f"    -> Session {session_id} is_synced: {s.is_synced}")
        print(f"    -> Visit {visit_id} is_synced: {v.is_synced}")

    print("[4] ✅ Records successfully marked as synced!")
    
    # Cleanup
    with db.get_session() as session:
        session.query(Session).filter(Session.id == session_id).delete()
        session.query(ClientVisit).filter(ClientVisit.id == visit_id).delete()
        session.commit()
    print("[5] Cleanup complete.")

if __name__ == "__main__":
    try:
        test_sync_lifecycle()
    except AssertionError as e:
        print(f"❌ Test Failed: {e}")
    except Exception as e:
        print(f"⚠️ Error: {e}")
