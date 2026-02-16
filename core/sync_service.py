"""
Cloud Synchronization Service
Handles robust "Store-and-Forward" data sync and Heartbeat signals.
"""
import time
import threading
import requests
import os
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent))
from datetime import datetime
from database.db import db
from config import BASE_DIR
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# --- Synchronization Configuration ---
# You should configure these URLs in your .env or backend code
# For now we use placeholders that will just print logs
CLOUD_API_BASE = os.getenv("CLOUD_API_URL", "http://localhost:8000/api/v1")
BRANCH_ID = int(os.getenv("BRANCH_ID", "1"))
AUTH_TOKEN = os.getenv("CLOUD_API_TOKEN", "files-secret-token")

SYNC_INTERVAL = 10.0      # Seconds between data sync attempts
HEARTBEAT_INTERVAL = 30.0 # Seconds between heartbeats
BATCH_SIZE = 50           # Max records to send per batch

class CloudSyncService:
    """
    Background service that:
    1. Periodically sends 'Heartbeat' to keep branch status Online (Green)
    2. Periodically sends 'Unsynced Data' to cloud (Store-and-Forward)
    """
    
    def __init__(self):
        self.is_running = False
        self.thread = None
        self.last_status_report = 0.0
        self.last_sync = 0.0
        # Track when we last successfully UPLOADED data to cloud
        # If never migrated, assume now to avoid scary warnings initially
        self.last_successful_upload_time = time.time()
        
        # Check if we are in "Mock Mode" (no real URL configured)
        self.mock_mode = "localhost" in CLOUD_API_BASE
        
    def start(self):
        """Start the background sync thread"""
        if self.is_running:
            return
            
        print("[INFO] [SyncService] Starting background synchronization...")
        self.is_running = True
        self.thread = threading.Thread(target=self._service_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop the service gracefully"""
        if not self.is_running:
            return
            
        print("[INFO] [SyncService] Stopping...")
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
            
    def _service_loop(self):
        """Main loop independent of UI"""
        while self.is_running:
            now = time.time()
            
            # 1. Sync Status Report (Instead of empty Heartbeat)
            if now - self.last_status_report >= HEARTBEAT_INTERVAL:
                self._send_sync_status()
                self.last_status_report = now
                
            # 2. Data Sync
            if now - self.last_sync >= SYNC_INTERVAL:
                self._sync_data()
                self.last_sync = now
                
            time.sleep(1.0) # Check every second
            
    def _send_sync_status(self):
        """Send detailed status report to cloud"""
        # Count unsynced items
        unsynced_sessions = len(db.get_unsynced_sessions(limit=1000))
        unsynced_visits = len(db.get_unsynced_client_visits(limit=1000))
        total_unsynced = unsynced_sessions + unsynced_visits
        
        payload = {
            "branch_id": BRANCH_ID,
            "status": "online",
            "last_successful_sync_timestamp": self.last_successful_upload_time,
            "unsynced_count": total_unsynced,
            "timestamp": time.time()
        }
        
        try:
            if self.mock_mode:
                return

            response = requests.post(
                f"{CLOUD_API_BASE}/status", 
                json=payload, 
                timeout=5,
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"}
            )
            if response.status_code == 200:
                last_sync_time = time.ctime(self.last_successful_upload_time)
                print(f"[INFO] [Status] OK. Last data sync: {last_sync_time}")
            else:
                print(f"[WARN] [Status] Server error: {response.status_code}")
                
        except Exception:
            print("[ERROR] [Status] Failed to send status report")

    # --- Cloud Connection ---
    def _get_cloud_session(self):
        """Create a session to the cloud DB"""
        if self.mock_mode:
            return None
        try:
            # Lazy init engine
            if not hasattr(self, 'cloud_engine'):
                # Ensure DSN is valid
                dsn = os.getenv("DB_DSN")
                if not dsn:
                    return None
                if dsn.startswith("postgres://"):
                    dsn = dsn.replace("postgres://", "postgresql://", 1)
                
                self.cloud_engine = create_engine(dsn, pool_pre_ping=True)
                self.CloudSession = sessionmaker(bind=self.cloud_engine)
            
            return self.CloudSession()
        except Exception as e:
            print(f"[ERROR] [Sync] Failed to connect to cloud: {e}")
            return None

    def _sync_data(self):
        """Upload pending records from DB (Direct to Cloud DB)"""
        max_batches_per_cycle = 20 
        batches_processed = 0
        
        while batches_processed < max_batches_per_cycle:
            has_success = False
            data_found = False
            
            # 1. Sync Sessions
            sessions_data = db.get_unsynced_sessions(limit=BATCH_SIZE)
            if sessions_data:
                data_found = True
                if self._upload_to_cloud_db("session", sessions_data):
                    ids = [r['id'] for r in sessions_data]
                    db.mark_as_synced("session", ids)
                    print(f"[INFO] [Sync] Uploaded {len(sessions_data)} sessions (Batch {batches_processed+1})")
                    has_success = True
                else:
                    break
            
            # 2. Sync Client Visits
            visits_data = db.get_unsynced_client_visits(limit=BATCH_SIZE)
            if visits_data:
                data_found = True
                if self._upload_to_cloud_db("client_visit", visits_data):
                    ids = [r['id'] for r in visits_data]
                    db.mark_as_synced("client_visit", ids)
                    print(f"[INFO] [Sync] Uploaded {len(visits_data)} client visits (Batch {batches_processed+1})")
                    has_success = True
                else:
                    break
                    
            if has_success:
                self.last_successful_upload_time = time.time()
                batches_processed += 1
            elif not data_found:
                self.last_successful_upload_time = time.time()
                break 
            else:
                break

    def _upload_to_cloud_db(self, data_type: str, records: List[Dict]) -> bool:
        """Push records directly to Cloud PostgreSQL"""
        if self.mock_mode:
            return True

        cloud_session = self._get_cloud_session()
        if not cloud_session:
            return False
            
        try:
            # We must import models inside here or at top level if not circular
            # To be safe, we import inside
            from database.models import Session as SessionModel, ClientVisit as VisitModel
            
            with cloud_session:
                for r in records:
                    if data_type == "session":
                        # Convert ISO strings back to datetime if necessary, 
                        # BUT get_unsynced_sessions returns ISO strings.
                        # We need to parse them.
                        orm_obj = SessionModel(
                            id=r['id'], # Keep same ID
                            place_id=r['place_id'],
                            employee_id=r['employee_id'],
                            start_time=datetime.fromisoformat(r['start_time']),
                            end_time=datetime.fromisoformat(r['end_time']) if r['end_time'] else None,
                            duration_seconds=r['duration_seconds'],
                            session_date=datetime.fromisoformat(r['start_time']).date(),
                            is_synced=1
                        )
                    elif data_type == "client_visit":
                        orm_obj = VisitModel(
                            id=r['id'],
                            place_id=r['place_id'],
                            employee_id=r['employee_id'],
                            track_id=r['track_id'],
                            visit_date=datetime.fromisoformat(r['enter_time']).date(),
                            enter_time=datetime.fromisoformat(r['enter_time']),
                            exit_time=datetime.fromisoformat(r['exit_time']) if r['exit_time'] else None,
                            duration_seconds=r['duration_seconds'],
                            is_synced=1
                        )
                    
                    # Merge prevents error if ID exists
                    cloud_session.merge(orm_obj)
                
                cloud_session.commit()
            return True
            
        except Exception as e:
            print(f"[ERROR] [Sync] Cloud DB Write Failed: {e}")
            return False
            
    def _upload_batch(self, data_type: str, records: List[Dict]) -> bool:
        """Deprecated HTTP upload (kept for interface compatibility if needed)"""
        return self._upload_to_cloud_db(data_type, records)

# Global instance
sync_service = CloudSyncService()
