
import sys
import os
import shutil
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import db
from database.models import Place
from config import ROI_TEMPLATES, FRAME_WIDTH, FRAME_HEIGHT, DATABASE_PATH
from core.roi_manager import ROIManager

def reset_rois():
    print("🔄 Resetting ROI Zones from Config...")
    
    # 1. Wipe DB Places
    print(f"   [1/3] Wiping 'places' table in {DATABASE_PATH}...")
    try:
        with db.get_session() as session:
            count = session.query(Place).delete()
            session.commit()
            print(f"         Deleted {count} existing zones.")
    except Exception as e:
        print(f"❌ DB Error: {e}")
        return

    # 2. Delete rois.json (to prevent ROIManager from reloading old local cache)
    json_path = Path(__file__).parent.parent / "rois.json"
    print(f"   [2/3] Checking for {json_path}...")
    if json_path.exists():
        try:
            os.remove(json_path)
            print("         Deleted rois.json")
        except Exception as e:
            print(f"⚠️ Failed to delete rois.json: {e}")
    else:
        print("         rois.json not found (clean)")

    # 3. Import from Config
    print(f"   [3/3] Importing Templates (Target Res: {FRAME_WIDTH}x{FRAME_HEIGHT})...")
    
    total_imported = 0
    for cam_id, template in ROI_TEMPLATES.items():
        print(f"         Processing Camera {cam_id}...")
        
        # Init Manager (will correspond to empty env now)
        manager = ROIManager(cam_id)
        
        # Import
        imported = manager.import_predefined_rois(
            predefined_rois=template["rois"],
            ref_res=template["ref_res"],
            frame_res=(FRAME_WIDTH, FRAME_HEIGHT)
        )
        total_imported += imported
        
    print(f"\n✅ Reset Complete! Imported {total_imported} zones total.")
    print("   Please restart the application to reload changes.")

if __name__ == "__main__":
    reset_rois()
