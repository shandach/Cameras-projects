"""
Drop the legacy 'events' table from Cloud PostgreSQL (Railway).
This table is not used by the current sync_service.
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

def drop_events():
    dsn = os.getenv("DB_DSN")
    if not dsn:
        print("[ERROR] DB_DSN not found in .env")
        return

    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)

    try:
        engine = create_engine(dsn)
        with engine.connect() as conn:
            print("[OK] Connected to Cloud DB")

            # Check table exists and count rows
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='events'"
            ))
            if result.scalar() == 0:
                print("[INFO] Table 'events' does not exist. Nothing to do.")
                return

            count = conn.execute(text("SELECT COUNT(*) FROM events")).scalar()
            print(f"[INFO] Table 'events' has {count} rows")

            # Drop table
            print("[ACTION] Dropping table 'events'...")
            conn.execute(text("DROP TABLE events"))
            conn.commit()
            print("[OK] Table 'events' dropped successfully!")

    except Exception as e:
        print(f"[ERROR] Failed: {e}")

if __name__ == "__main__":
    drop_events()
