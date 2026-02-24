"""Fix PostgreSQL sequences that are behind max(id) after bulk migration"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
from sqlalchemy import create_engine, text

dsn = os.getenv("DB_DSN")
if dsn.startswith("postgres://"):
    dsn = dsn.replace("postgres://", "postgresql://", 1)

engine = create_engine(dsn)
with engine.connect() as c:
    for table in ["sessions", "client_visits"]:
        seq_name = f"{table}_id_seq"
        curr = c.execute(text(f"SELECT last_value FROM {seq_name}")).scalar()
        max_id = c.execute(text(f"SELECT COALESCE(MAX(id),0) FROM {table}")).scalar()
        print(f"{table}: sequence_at={curr}, max(id)={max_id}")
        
        if max_id > curr:
            new_val = max_id + 1
            c.execute(text(f"SELECT setval('{seq_name}', {new_val})"))
            c.commit()
            print(f"  [FIXED] Sequence reset to {new_val}")
        else:
            print(f"  [OK] Sequence is ahead of max(id)")
