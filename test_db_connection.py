import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load env
load_dotenv(".env")

DB_DSN = os.getenv("DB_DSN")
print(f"[INFO] Testing connection to: {DB_DSN}")

if not DB_DSN:
    print("[ERROR] No DB_DSN found in .env")
    sys.exit(1)

# Fix postgres protocol if needed (handled in sync_service, doing it here too)
if DB_DSN.startswith("postgres://"):
    DB_DSN = DB_DSN.replace("postgres://", "postgresql://", 1)

try:
    print("[INFO] Connecting to Cloud DB...")
    engine = create_engine(DB_DSN, connect_args={"connect_timeout": 10})
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("[SUCCESS] Connection successful!")
        
        # Optional: Check if tables exist
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM sessions"))
            count = result.scalar()
            print(f"[INFO] Cloud 'sessions' table has {count} records.")
        except Exception as e:
            print(f"[WARN] Could not query sessions table (might be empty or missing): {e}")

except Exception as e:
    print(f"[ERROR] Connection failed: {e}")
    sys.exit(1)

# Check local UNSYNCED data
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from database.db import db
    
    unsynced_sess = len(db.get_unsynced_sessions())
    unsynced_visits = len(db.get_unsynced_client_visits())
    
    print(f"[INFO] Local Unsynced Sessions: {unsynced_sess}")
    print(f"[INFO] Local Unsynced Visits: {unsynced_visits}")
    
    if unsynced_sess > 0 or unsynced_visits > 0:
        print("[INFO] Data is waiting to be synced. Run the app to sync.")
    else:
        print("[INFO] No pending data to sync.")

except Exception as e:
    print(f"[WARN] Could not check local DB: {e}")
