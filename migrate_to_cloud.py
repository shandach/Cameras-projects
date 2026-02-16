import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load config
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, Employee, Place, Session, ClientVisit
from database.db import db as local_db

# Cloud connection
CLOUD_DSN = os.getenv("DB_DSN")

if not CLOUD_DSN:
    print("❌ Error: DB_DSN not found in .env")
    sys.exit(1)

# Remove 'postgresql://' prefix if present to ensure psycopg2 usage explicitly if needed?
# SQLAlchemy handles it. 
# But Railway URLs sometimes use postgres:// which SQLAlchemy deprecated.
if CLOUD_DSN.startswith("postgres://"):
    CLOUD_DSN = CLOUD_DSN.replace("postgres://", "postgresql://", 1)

print(f"🌍 Connecting to Cloud DB: {CLOUD_DSN.split('@')[1]}")

def migrate():
    try:
        cloud_engine = create_engine(CLOUD_DSN)
        CloudSession = sessionmaker(bind=cloud_engine)
        
        # 1. Create Tables
        print("🏗️  Creating tables in Cloud DB...")
        Base.metadata.create_all(cloud_engine)
        print("✅ Schema created/verified.")
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return

    # 2. Migrate Data
    session_factory = CloudSession()
    with session_factory as cloud_session:
        # We need to query local DB inside the context
        
        # --- Migrating Employees ---
        employees = local_db.get_all_employees()
        print(f"📦 Migrating {len(employees)} employees...")
        
        # Note: generic get_all_employees returns dicts, not ORM objects.
        # We need raw ORM access or re-construct.
        # Let's use direct session for local DB to get full objects
        with local_db.get_session() as local_session:
            
            # EMPLOYEES
            for emp in local_session.query(Employee).all():
                new_emp = Employee(
                    id=emp.id,
                    name=emp.name,
                    position=emp.position,
                    is_active=emp.is_active,
                    created_at=emp.created_at
                )
                cloud_session.merge(new_emp)
            
            # PLACES
            places = local_session.query(Place).all()
            print(f"📦 Migrating {len(places)} places...")
            for p in places:
                new_place = Place(
                    id=p.id, 
                    camera_id=p.camera_id,
                    name=p.name,
                    roi_coordinates=p.roi_coordinates,
                    status=p.status,
                    zone_type=p.zone_type,
                    employee_id=p.employee_id,
                    linked_employee_id=p.linked_employee_id
                )
                cloud_session.merge(new_place)
                
            # SESSIONS
            sessions = local_session.query(Session).all()
            print(f"📦 Migrating {len(sessions)} sessions history...")
            for s in sessions:
                new_session = Session(
                    id=s.id,
                    place_id=s.place_id,
                    employee_id=s.employee_id,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    duration_seconds=s.duration_seconds,
                    session_date=s.session_date,
                    is_synced=1 
                )
                cloud_session.merge(new_session)
                
            # CLIENT VISITS
            visits = local_session.query(ClientVisit).all()
            print(f"📦 Migrating {len(visits)} client visits...")
            for v in visits:
                new_visit = ClientVisit(
                    id=v.id,
                    place_id=v.place_id,
                    employee_id=v.employee_id,
                    track_id=v.track_id,
                    visit_date=v.visit_date,
                    enter_time=v.enter_time,
                    exit_time=v.exit_time,
                    duration_seconds=v.duration_seconds,
                    is_synced=1
                )
                cloud_session.merge(new_visit)
            
            cloud_session.commit()
            
    print("\n✨ Migration Complete!")
    print("   Data from SQLite has been cloned to Railway Postgres.")

if __name__ == "__main__":
    migrate()
