
import sys
import os
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import db
from core.roi_manager import ROIManager
from database.models import Place

def test_client_zone_persistence():
    print("🧪 Testing Client Zone Persistence...")
    
    # 1. Setup Wrapper
    # We need to simulate the ROI Editor logic
    # Create a manager for a test camera
    CAM_ID = 999
    manager = ROIManager(CAM_ID)
    
    # Ensure clean slate
    manager.delete_all_rois()
    
    # 2. Add an Employee Zone (Default)
    # This calls add_roi -> saves to DB and JSON
    points = [(0,0), (100,0), (100,100), (0,100)]
    roi = manager.add_roi(points, "TestZone", "employee")
    roi_id = roi.id
    print(f"   Created Zone ID {roi_id} as 'employee'")
    
    # 3. Simulate Toggle to Client (Simulating UI Logic)
    print("   Simulating 'C' key toggle...")
    new_type = "client"
    
    # A. Update DB
    db.update_roi_type(roi_id, new_type)
    
    # B. Update In-Memory Object
    roi.zone_type = new_type
    
    # C. STEP ADDED: manager._save_to_json() 
    # This mimics the fix ensured in ROI Manager
    manager._save_to_json()
    
    print(f"   Switched Zone ID {roi_id} to 'client' (DB Updated, JSON Stale)")
    
    # 4. Verify DB State
    with db.get_session() as session:
        p = session.query(Place).get(roi_id)
        print(f"   [DB Check] Zone Type: {p.zone_type}")
        assert p.zone_type == "client", "DB should have 'client' type"

    # 5. Reload Manager (Simulate Restart)
    # This should load from JSON (which is stale)
    print("   Reloading ROIManager...")
    new_manager = ROIManager(CAM_ID)
    reloaded_roi = new_manager.get_roi(roi_id)
    
    print(f"   [Reload Check] Zone Type: {reloaded_roi.zone_type}")
    
    if reloaded_roi.zone_type == "client":
        print("✅ SUCCESS: Zone persisted as Client!")
        return True
    else:
        print("❌ FAILURE: Zone reverted to Employee (JSON took precedence over DB)")
        return False

if __name__ == "__main__":
    success = test_client_zone_persistence()
    if not success:
        sys.exit(1)
