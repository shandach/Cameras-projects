"""
Cloud Synchronization Service v2.0
Handles robust "Store-and-Forward" data sync with:
- Exponential backoff with jitter on connection failure
- Rate limiting for bulk sync after outage
- Connection health monitoring
- Heartbeat/Status reports to cloud API
"""
import time
import threading
import random
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
CLOUD_API_BASE = os.getenv("CLOUD_API_URL", "http://localhost:8000/api/v1")
BRANCH_ID = int(os.getenv("BRANCH_ID", "1"))
BRANCH_NAME = os.getenv("BRANCH_NAME", "Unknown Branch")
AUTH_TOKEN = os.getenv("CLOUD_API_TOKEN", "files-secret-token")

# Sync tuning
SYNC_INTERVAL_NORMAL = 10.0       # Seconds between sync attempts (normal)
SYNC_INTERVAL_MAX = 300.0         # Max backoff interval (5 min cap)
HEARTBEAT_INTERVAL = 30.0         # Seconds between heartbeat/status reports
BATCH_SIZE = 50                   # Max records to send per batch
MAX_BATCHES_PER_CYCLE = 5         # Rate limit: max batches per sync cycle
BACKOFF_MULTIPLIER = 2.0          # Exponential growth factor
JITTER_MAX = 5.0                  # Random jitter (seconds) to prevent thundering herd


class CloudSyncService:
    """
    Background service that:
    1. Periodically sends 'Heartbeat/Status' to keep branch status Online
    2. Periodically sends 'Unsynced Data' to cloud (Store-and-Forward)
    3. Uses exponential backoff on connection failure
    4. Rate-limits catch-up sync after prolonged outage
    """
    
    def __init__(self):
        self.is_running = False
        self.thread = None
        self.last_status_report = 0.0
        self.last_sync = 0.0
        # Track when we last successfully UPLOADED data to cloud
        self.last_successful_upload_time = time.time()
        
        # Backoff state
        self._current_sync_interval = SYNC_INTERVAL_NORMAL
        self._consecutive_failures = 0
        self._is_healthy = True
        
        # Connection pool (lazy init)
        self._cloud_engine = None
        self._CloudSession = None
        
        # Check if we are in "Mock Mode" (no real URL configured + NO DB_DSN)
        self.mock_mode = "localhost" in CLOUD_API_BASE and not os.getenv("DB_DSN")
        
    def start(self):
        """Start the background sync thread"""
        if self.is_running:
            return
            
        print(f"[SyncV2] Starting for branch '{BRANCH_NAME}' (ID: {BRANCH_ID})...")
        self.is_running = True
        self.thread = threading.Thread(target=self._service_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop the service gracefully"""
        if not self.is_running:
            return
            
        print("[SyncV2] Stopping...")
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)
        
        # Force final sync: push any newly-finalized sessions to cloud
        print("[SyncV2] Running final sync before shutdown...")
        try:
            self._sync_data()
        except Exception as e:
            print(f"[SyncV2] Final sync failed: {e}")
        
        # Close ALL remaining checkpoints in the cloud for this branch
        self._close_cloud_checkpoints()
        
        # Dispose connection pool
        if self._cloud_engine:
            try:
                self._cloud_engine.dispose()
                print("[SyncV2] Cloud connection pool disposed.")
            except Exception:
                pass
            
    def _service_loop(self):
        """Main loop independent of UI"""
        while self.is_running:
            now = time.time()
            
            # 1. Sync Status Report / Heartbeat
            if now - self.last_status_report >= HEARTBEAT_INTERVAL:
                self._send_sync_status()
                self.last_status_report = now
                
            # 2. Data Sync (with adaptive interval from backoff)
            if now - self.last_sync >= self._current_sync_interval:
                success = self._sync_data()
                self.last_sync = now
                
                if success:
                    self._on_sync_success()
                else:
                    self._on_sync_failure()
            
            # 3. Checkpoint Sync (active sessions for real-time display)
            if now - getattr(self, '_last_checkpoint_sync', 0) >= 60:  # Every 1 min
                self._sync_checkpoints()
                self._last_checkpoint_sync = now
                
            time.sleep(1.0)  # Check every second
    
    # --- Backoff Logic ---
    
    def _on_sync_success(self):
        """Restore normal sync interval after successful sync"""
        if not self._is_healthy:
            print(f"[SyncV2] ✅ Connection restored after "
                  f"{self._consecutive_failures} failed attempts!")
        self._consecutive_failures = 0
        self._current_sync_interval = SYNC_INTERVAL_NORMAL
        self._is_healthy = True
        self.last_successful_upload_time = time.time()
    
    def _on_sync_failure(self):
        """Exponential backoff with jitter on failure"""
        self._consecutive_failures += 1
        self._is_healthy = False
        
        # Exponential growth: 10 → 20 → 40 → 80 → 160 → 300 (cap)
        backoff = min(
            SYNC_INTERVAL_NORMAL * (BACKOFF_MULTIPLIER ** self._consecutive_failures),
            SYNC_INTERVAL_MAX
        )
        # Jitter: prevents all branches from retrying at the exact same moment
        jitter = random.uniform(0, JITTER_MAX)
        self._current_sync_interval = backoff + jitter
        
        # Log less frequently as failures increase (every 5th attempt after 10)
        if self._consecutive_failures <= 10 or self._consecutive_failures % 5 == 0:
            print(f"[SyncV2] ⚠️ Sync failed (attempt #{self._consecutive_failures}). "
                  f"Next retry in {self._current_sync_interval:.0f}s")
    
    # --- Status/Heartbeat ---
            
    def _send_sync_status(self):
        """Send detailed status report to cloud API"""
        # Count unsynced items
        unsynced_sessions = len(db.get_unsynced_sessions(limit=1000))
        unsynced_visits = len(db.get_unsynced_client_visits(limit=1000))
        total_unsynced = unsynced_sessions + unsynced_visits
        
        payload = {
            "branch_id": BRANCH_ID,
            "branch_name": BRANCH_NAME,
            "status": "online",
            "is_healthy": self._is_healthy,
            "consecutive_failures": self._consecutive_failures,
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
                print(f"[SyncV2] [Status] OK. Last data sync: {last_sync_time}")
            else:
                print(f"[SyncV2] [Status] Server error: {response.status_code}")
                
        except Exception:
            pass  # Status report failures are non-critical

    # --- Cloud Connection ---
    
    def _get_cloud_session(self):
        """Create a session to the cloud DB with connection pooling"""
        if self.mock_mode:
            return None
        try:
            if self._cloud_engine is None:
                dsn = os.getenv("DB_DSN")
                if not dsn:
                    return None
                if dsn.startswith("postgres://"):
                    dsn = dsn.replace("postgres://", "postgresql://", 1)
                
                self._cloud_engine = create_engine(
                    dsn,
                    pool_pre_ping=True,
                    pool_size=2,              # Small pool for branch monoblock
                    max_overflow=3,
                    pool_recycle=1800,         # Recycle connections every 30 min
                    connect_args={
                        "connect_timeout": 10,
                        "options": "-c statement_timeout=30000"  # 30s query timeout
                    }
                )
                self._CloudSession = sessionmaker(bind=self._cloud_engine)
            
            return self._CloudSession()
        except Exception as e:
            print(f"[SyncV2] Cloud connection failed: {e}")
            return None

    # --- Data Sync ---

    def _sync_data(self):
        """Upload pending records with rate limiting"""
        if self.mock_mode:
            # In mock mode: still mark as synced for testing
            sessions_data = db.get_unsynced_sessions(limit=BATCH_SIZE)
            if sessions_data:
                ids = [r['id'] for r in sessions_data]
                db.mark_as_synced("session", ids)
            
            visits_data = db.get_unsynced_client_visits(limit=BATCH_SIZE)
            if visits_data:
                ids = [r['id'] for r in visits_data]
                db.mark_as_synced("client_visit", ids)
            return True
        
        batches_processed = 0
        any_success = False
        
        while batches_processed < MAX_BATCHES_PER_CYCLE:
            data_found = False
            
            # 1. Sync Sessions
            sessions_data = db.get_unsynced_sessions(limit=BATCH_SIZE)
            if sessions_data:
                data_found = True
                if self._upload_to_cloud_db("session", sessions_data):
                    ids = [r['id'] for r in sessions_data]
                    db.mark_as_synced("session", ids)
                    any_success = True
                    print(f"[SyncV2] ↑ {len(sessions_data)} sessions "
                          f"(batch {batches_processed+1})")
                else:
                    return any_success  # Stop on error
            
            # 2. Sync Client Visits
            visits_data = db.get_unsynced_client_visits(limit=BATCH_SIZE)
            if visits_data:
                data_found = True
                if self._upload_to_cloud_db("client_visit", visits_data):
                    ids = [r['id'] for r in visits_data]
                    db.mark_as_synced("client_visit", ids)
                    any_success = True
                    print(f"[SyncV2] ↑ {len(visits_data)} client visits "
                          f"(batch {batches_processed+1})")
                else:
                    return any_success  # Stop on error
                    
            if not data_found:
                # Nothing to sync — that's a success
                return True
            
            batches_processed += 1
            
            # Rate limiting: brief pause between batches to avoid DB overload
            if batches_processed < MAX_BATCHES_PER_CYCLE:
                time.sleep(0.5)
        
        if any_success:
            self.last_successful_upload_time = time.time()
        return any_success

    def _upload_to_cloud_db(self, data_type: str, records: List[Dict]) -> bool:
        """
        Push records to Cloud PostgreSQL using INSERT ... ON CONFLICT.
        Uses composite key (branch_id, local_id) to prevent ID collision
        between branches while allowing safe retry/upsert.
        """
        cloud_session = self._get_cloud_session()
        if not cloud_session:
            return False
            
        try:
            from sqlalchemy import text
            
            with cloud_session:
                for r in records:
                    if data_type == "session":
                        cloud_session.execute(text("""
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
                            "branch_id": BRANCH_ID,
                            "place_id": r['place_id'],
                            "employee_id": r['employee_id'],
                            "start_time": datetime.fromisoformat(r['start_time']),
                            "end_time": (datetime.fromisoformat(r['end_time'])
                                        if r['end_time'] else None),
                            "duration_seconds": r['duration_seconds'],
                            "session_date": datetime.fromisoformat(
                                r['start_time']).date(),
                        })
                        
                    elif data_type == "client_visit":
                        cloud_session.execute(text("""
                            INSERT INTO client_visits
                                (local_id, branch_id, place_id, employee_id,
                                 track_id, visit_date, enter_time, exit_time,
                                 duration_seconds, is_synced, is_checkpoint, created_at)
                            VALUES
                                (:local_id, :branch_id, :place_id, :employee_id,
                                 :track_id, :visit_date, :enter_time, :exit_time,
                                 :duration_seconds, 1, 0, NOW())
                            ON CONFLICT (branch_id, local_id) DO UPDATE SET
                                exit_time = EXCLUDED.exit_time,
                                duration_seconds = EXCLUDED.duration_seconds,
                                is_synced = 1,
                                is_checkpoint = 0
                        """), {
                            "local_id": r['id'],
                            "branch_id": BRANCH_ID,
                            "place_id": r['place_id'],
                            "employee_id": r['employee_id'],
                            "track_id": r['track_id'],
                            "visit_date": datetime.fromisoformat(
                                r['enter_time']).date(),
                            "enter_time": datetime.fromisoformat(r['enter_time']),
                            "exit_time": (datetime.fromisoformat(r['exit_time'])
                                         if r['exit_time'] else None),
                            "duration_seconds": r['duration_seconds'],
                        })
                
                cloud_session.commit()
            return True
            
        except Exception as e:
            print(f"[SyncV2] ❌ Cloud DB write failed: {e}")
            try:
                cloud_session.rollback()
            except Exception:
                pass
            return False
            
    def _upload_batch(self, data_type: str, records: List[Dict]) -> bool:
        """Alias for backward compatibility"""
        return self._upload_to_cloud_db(data_type, records)

    def _sync_checkpoints(self):
        """
        Sync active session checkpoints to cloud for real-time display.
        These are sessions where the employee is currently sitting.
        Uses is_checkpoint=1 in the cloud so the backend knows they're temporary.
        When the session finalizes, the normal sync overwrites with is_checkpoint=0.
        """
        if self.mock_mode:
            return
        
        checkpoints = db.get_active_checkpoints()
        if not checkpoints:
            return
        
        cloud_session = self._get_cloud_session()
        if not cloud_session:
            return
        
        try:
            from sqlalchemy import text
            from config import tashkent_now
            
            now = tashkent_now()
            
            with cloud_session:
                for r in checkpoints:
                    start_time = datetime.fromisoformat(r['start_time'])
                    duration = (now - start_time).total_seconds()
                    
                    cloud_session.execute(text("""
                        INSERT INTO sessions 
                            (local_id, branch_id, place_id, employee_id,
                             start_time, end_time, duration_seconds,
                             session_date, is_synced, is_checkpoint, created_at)
                        VALUES 
                            (:local_id, :branch_id, :place_id, :employee_id,
                             :start_time, NULL, :duration_seconds,
                             :session_date, 1, 1, NOW())
                        ON CONFLICT (branch_id, local_id) DO UPDATE SET
                            duration_seconds = EXCLUDED.duration_seconds,
                            is_checkpoint = 1
                        WHERE sessions.is_checkpoint = 1
                    """), {
                        "local_id": r['id'],
                        "branch_id": BRANCH_ID,
                        "place_id": r['place_id'],
                        "employee_id": r['employee_id'],
                        "start_time": start_time,
                        "duration_seconds": duration,
                        "session_date": start_time.date(),
                    })
                
                cloud_session.commit()
            print(f"[SyncV2] 🔄 {len(checkpoints)} active checkpoint(s) synced")
            
        except Exception as e:
            print(f"[SyncV2] ⚠️ Checkpoint sync failed: {e}")
            try:
                cloud_session.rollback()
            except Exception:
                pass

    def _close_cloud_checkpoints(self):
        """
        Close ALL checkpoint sessions in the cloud for this branch.
        Called on graceful shutdown. Handles the case where occupancy_engine
        finalized sessions locally but sync didn't push them yet, or
        where checkpoints were synced but never finalized.
        """
        if self.mock_mode:
            return
        
        cloud_session = self._get_cloud_session()
        if not cloud_session:
            return
        
        try:
            from sqlalchemy import text
            
            with cloud_session:
                result = cloud_session.execute(text("""
                    UPDATE sessions 
                    SET is_checkpoint = 0,
                        end_time = NOW(),
                        duration_seconds = EXTRACT(EPOCH FROM (NOW() - start_time))
                    WHERE branch_id = :branch_id 
                      AND is_checkpoint = 1
                """), {"branch_id": BRANCH_ID})
                
                cloud_session.commit()
                
                rows = result.rowcount
                if rows > 0:
                    print(f"[SyncV2] 🔒 Closed {rows} checkpoint(s) in cloud on shutdown")
                else:
                    print("[SyncV2] ✅ No open checkpoints in cloud")
                    
        except Exception as e:
            print(f"[SyncV2] ⚠️ Failed to close cloud checkpoints: {e}")
            try:
                cloud_session.rollback()
            except Exception:
                pass


# Global instance
sync_service = CloudSyncService()
