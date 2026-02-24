"""
Clean legacy cloud data:
1. Show what's inconsistent (NULL branch_id, NULL local_id)
2. Delete those records
3. Fix sequences
4. Verify final state
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
from sqlalchemy import create_engine, text

dsn = os.getenv("DB_DSN")
if dsn.startswith("postgres://"):
    dsn = dsn.replace("postgres://", "postgresql://", 1)

BRANCH_ID = int(os.getenv("BRANCH_ID", "1"))
engine = create_engine(dsn)

with engine.connect() as c:
    print("=" * 60)
    print("  CLOUD DB CLEANUP")
    print("=" * 60)

    # --- BEFORE ---
    print("\n[BEFORE] Current state:")
    for table in ["sessions", "client_visits"]:
        total = c.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        null_branch = c.execute(text(
            f"SELECT COUNT(*) FROM {table} WHERE branch_id IS NULL"
        )).scalar()
        good = c.execute(text(
            f"SELECT COUNT(*) FROM {table} WHERE branch_id = :bid"
        ), {"bid": BRANCH_ID}).scalar()
        null_local = c.execute(text(
            f"SELECT COUNT(*) FROM {table} WHERE local_id IS NULL"
        )).scalar()
        print(f"  {table}: {total} total | {good} with branch_id={BRANCH_ID} | "
              f"{null_branch} with branch_id=NULL | {null_local} with local_id=NULL")

    # --- CHECK for duplicates before deleting ---
    print("\n[CHECK] Are NULL-branch records duplicates of existing branch_id records?")
    for table in ["sessions", "client_visits"]:
        # Records with NULL branch that also exist with correct branch (by local_id match)
        dupes = c.execute(text(f"""
            SELECT COUNT(*) FROM {table} a 
            WHERE a.branch_id IS NULL 
            AND EXISTS (
                SELECT 1 FROM {table} b 
                WHERE b.branch_id = :bid AND b.local_id = a.local_id
            )
        """), {"bid": BRANCH_ID}).scalar()
        
        orphans = c.execute(text(f"""
            SELECT COUNT(*) FROM {table} a 
            WHERE a.branch_id IS NULL 
            AND NOT EXISTS (
                SELECT 1 FROM {table} b 
                WHERE b.branch_id = :bid AND b.local_id = a.local_id
            )
        """), {"bid": BRANCH_ID}).scalar()
        
        null_total = c.execute(text(
            f"SELECT COUNT(*) FROM {table} WHERE branch_id IS NULL"
        )).scalar()
        
        print(f"  {table} (NULL branch): {null_total} total = "
              f"{dupes} duplicates + {orphans} unique orphans")

    # --- DELETE records with NULL branch_id ---
    print("\n[DELETE] Removing records with branch_id IS NULL...")
    for table in ["sessions", "client_visits"]:
        count = c.execute(text(
            f"DELETE FROM {table} WHERE branch_id IS NULL"
        )).rowcount
        print(f"  Deleted {count} rows from {table}")
    c.commit()
    print("  [OK] Committed")

    # --- FIX sequences ---
    print("\n[FIX] Resetting sequences...")
    for table in ["sessions", "client_visits"]:
        seq_name = f"{table}_id_seq"
        max_id = c.execute(text(f"SELECT COALESCE(MAX(id),0) FROM {table}")).scalar()
        new_val = max_id + 1
        c.execute(text(f"SELECT setval('{seq_name}', {new_val})"))
        print(f"  {seq_name} -> {new_val} (max_id was {max_id})")
    c.commit()

    # --- AFTER ---
    print("\n[AFTER] Final state:")
    for table in ["sessions", "client_visits"]:
        total = c.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        null_branch = c.execute(text(
            f"SELECT COUNT(*) FROM {table} WHERE branch_id IS NULL"
        )).scalar()
        null_local = c.execute(text(
            f"SELECT COUNT(*) FROM {table} WHERE local_id IS NULL"
        )).scalar()
        seq = c.execute(text(f"SELECT last_value FROM {table}_id_seq")).scalar()
        max_id = c.execute(text(f"SELECT COALESCE(MAX(id),0) FROM {table}")).scalar()
        print(f"  {table}: {total} rows | NULL branch: {null_branch} | "
              f"NULL local_id: {null_local} | seq={seq} max_id={max_id}")

    # --- CONSTRAINT CHECK ---
    print("\n[VERIFY] Constraints:")
    for table in ["sessions", "client_visits"]:
        constraints = c.execute(text("""
            SELECT constraint_name, constraint_type 
            FROM information_schema.table_constraints 
            WHERE table_name = :tbl AND constraint_type IN ('UNIQUE', 'PRIMARY KEY')
        """), {"tbl": table}).fetchall()
        for con in constraints:
            print(f"  {table}: {con[1]} -> {con[0]}")

    print("\n" + "=" * 60)
    print("  CLEANUP COMPLETE")
    print("=" * 60)
