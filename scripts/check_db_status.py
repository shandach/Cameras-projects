
import sys
import os
from pathlib import Path
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import Place, Session, ClientVisit
from config import DATABASE_PATH

def check_database():
    print(f"📂 Checking Database at: {DATABASE_PATH}")
    
    if not os.path.exists(DATABASE_PATH):
        print("❌ Database file NOT found!")
        return

    # Connect
    engine = create_engine(f"sqlite:///{DATABASE_PATH}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # 1. Count ROIs (Places)
        roi_count = session.query(Place).count()
        print(f"\n🏷️  ROI Zones (Places): {roi_count}")
        
        if roi_count > 0:
            rois = session.query(Place).all()
            for r in rois:
                print(f"   - ID {r.id}: '{r.name}' (Cam {r.camera_id}, Type: {r.zone_type})")
        else:
            print("   ⚠️ No ROI zones found! You may need to run roizones.py or main.py to create them.")

        # 2. Count Sessions & Visits
        session_count = session.query(Session).count()
        visit_count = session.query(ClientVisit).count()
        print(f"\n📊 Data Records:")
        print(f"   - Employee Sessions: {session_count}")
        print(f"   - Client Visits: {visit_count}")
        
    except Exception as e:
        print(f"❌ Error reading database: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    check_database()
