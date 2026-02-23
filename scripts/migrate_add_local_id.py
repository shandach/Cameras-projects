"""
Python equivalent of migrate_add_local_id.sql
Adds local_id + UNIQUE(branch_id, local_id) to sessions and client_visits in Cloud PostgreSQL.
Idempotent — safe to run multiple times.
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")


def run_migration():
    dsn = os.getenv("DB_DSN")
    if not dsn:
        print("[ERROR] DB_DSN not found in .env")
        return False

    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)

    try:
        engine = create_engine(dsn)
        with engine.connect() as conn:
            print("[OK] Connected to Cloud DB\n")

            # ===== Step 1: Check current columns =====
            for table in ["sessions", "client_visits"]:
                print(f"--- {table.upper()} ---")
                cols = conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:tbl"
                ), {"tbl": table}).fetchall()
                col_names = [c[0] for c in cols]
                print(f"  Columns: {col_names}")

                # Step 2: Add branch_id if missing
                if "branch_id" not in col_names:
                    print(f"  [ADD] branch_id column...")
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN branch_id INTEGER'))
                    conn.commit()
                    print(f"  [OK] branch_id added")
                else:
                    print(f"  [SKIP] branch_id already exists")

                # Step 3: Add local_id if missing
                if "local_id" not in col_names:
                    print(f"  [ADD] local_id column...")
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN local_id INTEGER'))
                    conn.commit()
                    print(f"  [OK] local_id added")
                else:
                    print(f"  [SKIP] local_id already exists")

                # Step 4: Copy id -> local_id where local_id IS NULL
                result = conn.execute(text(
                    f'UPDATE {table} SET local_id = id WHERE local_id IS NULL'
                ))
                conn.commit()
                updated = result.rowcount
                if updated > 0:
                    print(f"  [COPY] Copied id -> local_id for {updated} rows")
                else:
                    print(f"  [SKIP] All rows already have local_id")

                # Step 5: Add UNIQUE constraint on (branch_id, local_id) if missing
                constraint_name = f"uq_{table}_branch_local"
                exists = conn.execute(text(
                    "SELECT 1 FROM information_schema.table_constraints "
                    "WHERE constraint_name=:name AND table_name=:tbl"
                ), {"name": constraint_name, "tbl": table}).fetchone()

                if not exists:
                    print(f"  [ADD] UNIQUE constraint ({constraint_name})...")
                    try:
                        conn.execute(text(
                            f'ALTER TABLE {table} ADD CONSTRAINT {constraint_name} '
                            f'UNIQUE (branch_id, local_id)'
                        ))
                        conn.commit()
                        print(f"  [OK] Constraint added")
                    except Exception as e:
                        conn.rollback()
                        print(f"  [WARN] Constraint failed (duplicates?): {e}")
                else:
                    print(f"  [SKIP] Constraint {constraint_name} already exists")

                print()

            print("[DONE] Migration complete!")
            return True

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        return False


if __name__ == "__main__":
    run_migration()
