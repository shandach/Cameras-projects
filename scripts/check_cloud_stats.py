
import sys
import os
import time
from sqlalchemy import create_engine, text
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env manually to get DB_DSN
load_dotenv()

def check_cloud_db():
    print("\n☁️  CHECKING CLOUD DATABASE STATS...\n")
    
    dsn = os.getenv("DB_DSN")
    if not dsn:
        print("❌ DB_DSN not found in .env file!")
        return

    # Fix postgres:// for SQLAlchemy
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)
        
    try:
        engine = create_engine(dsn)
        with engine.connect() as conn:
            # 1. Check Connection
            print("✅ Connected to Cloud DB!")
            
            # 2. Count Total Records
            result = conn.execute(text("SELECT COUNT(*) FROM client_visits"))
            total_visits = result.scalar()
            
            result = conn.execute(text("SELECT COUNT(*) FROM sessions"))
            total_sessions = result.scalar()
            
            print(f"📊 Total Client Visits: {total_visits}")
            print(f"📊 Total Work Sessions: {total_sessions}")
            print("-" * 40)
            
            # 3. Show Latest 5 Client Visits
            print("🕒 Latest 5 Client Visits in Cloud:")
            query = text("""
                SELECT v.id, v.visit_date, v.duration_seconds, e.name 
                FROM client_visits v
                LEFT JOIN employees e ON v.employee_id = e.id
                ORDER BY v.enter_time DESC 
                LIMIT 5
            """)
            rows = conn.execute(query).fetchall()
            
            if not rows:
                print("   (No visits found)")
            else:
                for row in rows:
                    visit_id, date, duration, name = row
                    print(f"   [ID {visit_id}] {date} | {duration:.0f}s | Emp: {name or 'Unknown'}")

            print("-" * 40)
            print("✅ Cloud Check Complete.")
            
    except Exception as e:
        print(f"\n❌ FAILED to connect to Cloud DB:\n{e}")

if __name__ == "__main__":
    check_cloud_db()
