
import unittest
import os
import time
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import Database, db as global_db
from database.models import Session, ClientVisit, Base, Employee, Camera, Place
from core.occupancy_engine import OccupancyEngine, ZoneState, ZoneTracker
import core.occupancy_engine

# Use a test database
TEST_DB_PATH = "test_checkpoint.db"

class TestCheckpoint(unittest.TestCase):
    
    def setUp(self):
        # Setup clean DB
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
            
        # Initialize the global db with test path
        # We can't easily swap the engine of the global 'db' object cleanly without 
        # potentially affecting other things if they held references, but 
        # since 'db' is a singleton instance, we can re-init it or swap its engine.
        
        # Create a FRESH database instance for testing
        self.test_db = Database()
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        self.test_db.engine = create_engine(f"sqlite:///{TEST_DB_PATH}")
        Base.metadata.create_all(self.test_db.engine)
        self.test_db.SessionLocal = sessionmaker(bind=self.test_db.engine)
        
        # PATCH the global db variable in occupancy_engine module
        self.original_db = core.occupancy_engine.db
        core.occupancy_engine.db = self.test_db
        
        # Creating dummy data
        with self.test_db.get_session() as session:
            # Employee
            emp = Employee(name="Test Employee", position="Tester")
            session.add(emp)
            session.commit()
            self.emp_id = emp.id
            
            # Camera
            cam = Camera(external_id=999, name="Test Cam", rtsp_url="rtsp://test")
            session.add(cam)
            session.commit()
            self.cam_id = cam.id
            
            # Place
            place = Place(camera_id=cam.id, name="Test Zone", roi_coordinates=[[0,0],[100,0],[100,100],[0,100]], employee_id=emp.id)
            session.add(place)
            session.commit()
            self.place_id = place.id

    def tearDown(self):
        # Restore original db
        core.occupancy_engine.db = self.original_db
        
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except:
                pass

    def test_db_methods_direct(self):
        """Test DB methods for checkpointing directly"""
        print("\n[TEST] DB Checkpoint CRUD")
        start = datetime.now()
        
        # Create
        cp_id = self.test_db.save_session_checkpoint(self.place_id, self.emp_id, start)
        self.assertIsNotNone(cp_id)
        
        # Verify
        with self.test_db.get_session() as s:
            rec = s.query(Session).get(cp_id)
            self.assertEqual(rec.is_checkpoint, 1)
            self.assertEqual(rec.duration_seconds, 0)
            
        # Update
        time.sleep(0.1)
        self.test_db.update_session_checkpoint(cp_id, datetime.now(), 5.0)
        with self.test_db.get_session() as s:
            rec = s.query(Session).get(cp_id)
            self.assertEqual(rec.duration_seconds, 5.0)
            
        # Finalize
        self.test_db.finalize_session_checkpoint(cp_id, datetime.now(), 10.0)
        with self.test_db.get_session() as s:
            rec = s.query(Session).get(cp_id)
            self.assertEqual(rec.is_checkpoint, 0)
            self.assertEqual(rec.duration_seconds, 10.0)
            
    def test_sync_filter(self):
        """Test that get_unsynced_sessions DOES NOT return active checkpoints"""
        print("\n[TEST] Sync Filter")
        
        # 1. Active Checkpoint
        self.test_db.save_session_checkpoint(self.place_id, self.emp_id, datetime.now())
        
        # 2. Finished Session (Normal)
        self.test_db.save_session(self.place_id, datetime.now(), datetime.now(), 100, self.emp_id)
        
        unsynced = self.test_db.get_unsynced_sessions()
        
        # Should only find the finished session (1), not the checkpoint
        self.assertEqual(len(unsynced), 1)
        self.assertEqual(unsynced[0]['duration_seconds'], 100)
        
    def test_engine_integration(self):
        """Test full integration with OccupancyEngine"""
        print("\n[TEST] OccupancyEngine Integration")
        
        # Patch CHECKPOINT_INTERVAL to be very short
        # Since it's imported in occupancy_engine, we must patch it THERE
        orig_interval = core.occupancy_engine.CHECKPOINT_INTERVAL
        core.occupancy_engine.CHECKPOINT_INTERVAL = 0.5 
        
        try:
            engine = OccupancyEngine()
            
            # Ensure engine uses the patched value
            print(f"   Engine Interval: {core.occupancy_engine.CHECKPOINT_INTERVAL}")

            zone_id = self.place_id
            
            # --- 1. Person Enters ---
            # Initial update to trigger 'CHECKING_ENTRY'
            engine.update(zone_id, True) 
            tracker = engine.get_or_create_tracker(zone_id)
            
            # Manually fast-forward entry logic to avoid waiting for entry threshold
            tracker.state = ZoneState.OCCUPIED
            tracker.session_start = datetime.now()
            tracker.entry_start_time = time.time()
            tracker.timer_start_time = time.time()
            tracker.last_checkpoint_time = time.time() # Checkpoint timer started
            
            # Verify no checkpoint yet
            self.assertIsNone(tracker.checkpoint_db_id)
            
            # --- 2. Checkpoint Trigger ---
            time.sleep(0.6) # Wait > 0.5s
            
            # Update: Person still present -> should save checkpoint
            engine.update(zone_id, True)
            
            cp_id = tracker.checkpoint_db_id
            self.assertIsNotNone(cp_id, "Checkpoint ID should be set in tracker")
            print(f"   Checkpoint ID: {cp_id}")
            
            # Verify DB has is_checkpoint=1
            with self.test_db.get_session() as s:
                rec = s.query(Session).get(cp_id)
                self.assertEqual(rec.is_checkpoint, 1)
                
            # --- 3. Person Leaves ---
            engine._complete_session(tracker, "employee")
            
            # Verify DB has is_checkpoint=0
            with self.test_db.get_session() as s:
                rec = s.query(Session).get(cp_id)
                self.assertEqual(rec.is_checkpoint, 0)
                print(f"   Finalized Duration: {rec.duration_seconds}s")
                
        finally:
            core.occupancy_engine.CHECKPOINT_INTERVAL = orig_interval

if __name__ == '__main__':
    unittest.main()
