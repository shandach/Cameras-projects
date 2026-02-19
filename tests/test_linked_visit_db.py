
import sys
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import db
from database.models import ClientVisit, Place
from core.roi_manager import ROIManager

def test_linked_visit_persistence():
    print("🧪 Testing Client Visit Linkage Persistence...")
    
    # 1. Setup Data
    # Create dummy employee
    emp_name = f"TestEmp_{int(time.time())}"
    emp_id = db.create_employee(emp_name, "Tester")
    print(f"   Created Employee: {emp_name} (ID: {emp_id})")
    
    # Create Client Zone linked to this employee
    CAM_ID = 888
    manager = ROIManager(CAM_ID)
    manager.delete_all_rois()
    
    points = [(0,0), (100,0), (100,100), (0,100)]
    roi = manager.add_roi(points, "LinkedClientZone", "client", linked_employee_id=emp_id)
    roi_id = roi.id
    print(f"   Created Zone ID {roi_id} linked to Emp ID {emp_id}")

    # 2. Simulate Saving a Visit (Direct DB call as Engine would do)
    # We use the raw DB function to confirm the DB layer works
    print("   Saving Client Visit...")
    enter_time = datetime.now() - timedelta(minutes=5)
    exit_time = datetime.now()
    duration = 300.0
    
    visit_id = db.save_client_visit(
        place_id=roi_id,
        employee_id=emp_id, # This comes from roi.linked_employee_id in the Engine
        track_id=123,
        enter_time=enter_time,
        exit_time=exit_time,
        duration_seconds=duration
    )
    print(f"   Saved Visit ID: {visit_id}")
    
    # 3. Verify in DB
    print("   Verifying record in Database...")
    with db.get_session() as session:
        visit = session.query(ClientVisit).get(visit_id)
        
        print(f"   [Check] Visit ID: {visit.id}")
        print(f"   [Check] Linked Emp ID: {visit.employee_id}")
        
        assert visit.employee_id == emp_id, f"Expected Emp ID {emp_id}, got {visit.employee_id}"
        assert visit.place_id == roi_id, f"Expected Place ID {roi_id}, got {visit.place_id}"
        
        # Verify stats query also works
        stats = db.get_client_stats_for_employee(emp_id, enter_time.date())
        print(f"   [Stats Check] Count: {stats['client_count']}, Time: {stats['total_service_time']}")
        
        assert stats['client_count'] >= 1, "Stats should show at least 1 visit"
        
    print("✅ SUCCESS: Client visit correctly linked to employee in DB!")
    
    # Cleanup
    with db.get_session() as session:
        session.query(ClientVisit).filter(ClientVisit.id == visit_id).delete()
        session.query(Place).filter(Place.id == roi_id).delete()
        # Ensure we don't delete real employees? Just leave for now or delete
        # session.query(Employee).filter(Employee.id == emp_id).delete()
        session.commit()

if __name__ == "__main__":
    try:
        test_linked_visit_persistence()
    except AssertionError as e:
        print(f"❌ FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"⚠️ ERROR: {e}")
        sys.exit(1)
