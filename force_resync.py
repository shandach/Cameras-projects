"""
Script to force re-synchronization of ALL data.
Sets is_synced=0 for all sessions and client visits in the local SQLite DB.
"""
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load config
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from database.db import db
from database.models import Session, ClientVisit

def force_resync():
    print("🔄 Resetting sync status for ALL records...")
    
    with db.get_session() as session:
        # Reset Sessions
        count_s = session.query(Session).update({Session.is_synced: 0})
        
        # Reset Client Visits
        count_v = session.query(ClientVisit).update({ClientVisit.is_synced: 0})
        
        session.commit()
        
        print(f"✅ Reset complete.")
        print(f"   Sessions to resync: {count_s}")
        print(f"   Client Visits to resync: {count_v}")
        print("\n🚀 Startup the application now, and it will upload everything to Cloud DB.")

if __name__ == "__main__":
    force_resync()
