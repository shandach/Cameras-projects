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

    # 4. Cleanup
    print("\n[4] Cleanup...")
    # (Optional) delete test data
    
    print("✅ Test Complete")

if __name__ == "__main__":
    try:
        test_client_visit_recording()
    except AssertionError as e:
        print(f"❌ Test Failed: {e}")
    except Exception as e:
        print(f"⚠️ Error: {e}")
