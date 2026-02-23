"""
Check what tables and their row counts exist in the cloud PostgreSQL database
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

def check_cloud_tables():
    dsn = os.getenv("DB_DSN")
    if not dsn:
        print("❌ DB_DSN not found in .env")
        return

    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)

    try:
        engine = create_engine(dsn)
        with engine.connect() as conn:
            print("✅ Connected to Cloud DB\n")

            # 1. List all tables
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]
            print(f"📋 Tables found ({len(tables)}):")
            
            for table in tables:
                try:
                    count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
                    print(f"   • {table}: {count} rows")
                except Exception as e:
                    print(f"   • {table}: ERROR reading ({e})")

            # 2. Check FK constraints
            print(f"\n🔗 Foreign Key Constraints:")
            fk_result = conn.execute(text("""
                SELECT
                    tc.table_name AS source_table,
                    kcu.column_name AS source_column,
                    ccu.table_name AS target_table,
                    ccu.column_name AS target_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                ORDER BY tc.table_name
            """))
            fks = fk_result.fetchall()
            if fks:
                for fk in fks:
                    print(f"   {fk[0]}.{fk[1]} → {fk[2]}.{fk[3]}")
            else:
                print("   (No FK constraints found)")

    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    check_cloud_tables()
