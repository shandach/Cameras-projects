import sys
from pathlib import Path
from datetime import datetime, date, timedelta
import time

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import db
from database.models import ClientVisit, Place, Employee

def test_client_visit_recording():
    print("🧪 Testing Client Visit Recording...")
    
    # 1. Setup Test Data
    print("\n[1] Setting up test data...")
    test_emp_name = "Test Employee"
    
    # Clean previous test data
    with db.get_session() as session:
        # Remove old test employee
        session.query(Employee).filter(Employee.name == test_emp_name).delete()
        session.commit()
    
    # Create Employee
    print(f"Creating employee: {test_emp_name}")
    employee_id = db.create_employee(test_emp_name, "Tester")
    
    # Create Place (Client Zone)
    place_name = "Test Client Zone"
    print(f"Creating place: {place_name}")
    place = db.save_place(
        camera_id=999,
        name=place_name,
        roi_coordinates=[(0,0), (100,0), (100,100), (0,100)],
        zone_type="client",
        linked_employee_id=employee_id
    )
    place_id = place.id
    
    # 2. Verify initial stats
    print("\n[2] Checking initial stats...")
    today = date.today()
    stats = db.get_client_stats_for_employee(employee_id, today)
    print(f"Initial Stats: {stats}")
    assert stats['client_count'] == 0, "Client count should be 0"

    # 3. Simulate Visit (Completed)
    print("\n[3] Simulating COMPLETED visit (70s duration)...")
    # Simulate DB save directly since we want to test DB retrieval logic first
    # In main.py this happens when client leaves
    visit_start = datetime.now() - timedelta(seconds=100)
    visit_end = datetime.now() - timedelta(seconds=30)
    duration = 70.0 # > 60s threshold
    
    db.save_client_visit(
        place_id=place_id,
        employee_id=employee_id,
        track_id=123,
        enter_time=visit_start,
        exit_time=visit_end,
        duration_seconds=duration
    )
    print("Saved completed visit to DB.")
    
    # Check stats again
    stats = db.get_client_stats_for_employee(employee_id, today)
    print(f"Stats after completed visit: {stats}")
    # Note: main.py subtracts threshold from duration for service time display?
    # db.py returns raw sum.
    assert stats['client_count'] == 1, "Client count should be 1"
    assert stats['total_service_time'] == 70.0, "Service time should include full duration (or at least be positive)"

    # 4. End-to-End Test with OccupancyEngine
    print("\n[4] Testing OccupancyEngine Logic...")
    from core.occupancy_engine import OccupancyEngine
    from config import CLIENT_ENTRY_THRESHOLD, CLIENT_EXIT_THRESHOLD
    
    engine = OccupancyEngine()
    
    # Update with person present (Entry)
    print("   -> Person enters...")
    engine.update(place_id, is_person_present=True, zone_type="client", linked_employee_id=employee_id)
    time.sleep(0.1)
    
    # Simulate time passing (Wait for entry threshold)
    print(f"   -> Waiting {CLIENT_ENTRY_THRESHOLD}s virtual time...")
    # Hack: Manually adjust start time to simulate passage of time
    tracker = engine.get_or_create_tracker(place_id)
    if tracker.entry_start_time:
        tracker.entry_start_time -= (CLIENT_ENTRY_THRESHOLD + 1)
        
    # Update again to confirm entry
    engine.update(place_id, is_person_present=True, zone_type="client", linked_employee_id=employee_id)
    assert tracker.state.name == "OCCUPIED", f"State should be OCCUPIED, got {tracker.state}"
    
    # Simulate session duration
    print("   -> Person stays for session...")
    tracker.session_start -= timedelta(seconds=60) # Add 60s duration
    
    # Person leaves
    print("   -> Person leaves...")
    engine.update(place_id, is_person_present=False, zone_type="client", linked_employee_id=employee_id)
    assert tracker.state.name == "CHECKING_EXIT", f"State should be CHECKING_EXIT, got {tracker.state}"
    
    # Simulate exit grace period expiry
    print(f"   -> Waiting {CLIENT_EXIT_THRESHOLD}s virtual time for exit...")
    if tracker.exit_start_time:
        tracker.exit_start_time -= (CLIENT_EXIT_THRESHOLD + 1)
        
    # Update to trigger save
    engine.update(place_id, is_person_present=False, zone_type="client", linked_employee_id=employee_id)
    assert tracker.state.name == "VACANT", f"State should be VACANT, got {tracker.state}"
    
    # 5. Check Final Stats
    print("\n[5] Checking stats after OccupancyEngine flow...")
    stats = db.get_client_stats_for_employee(employee_id, today)
    print(f"Final Stats: {stats}")
    
    # Should be 2 now (1 manual + 1 engine)
    assert stats['client_count'] == 2, f"Client count should be 2, got {stats['client_count']}"
    
    print("✅ End-to-End Test Complete")
if __name__ == "__main__":
    try:
        test_client_visit_recording()
    except AssertionError as e:
        print(f"❌ Test Failed: {e}")
    except Exception as e:
        print(f"⚠️ Error: {e}")
