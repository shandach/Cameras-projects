"""Check PRIMARY KEY constraints on all cloud tables"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
from sqlalchemy import create_engine, text

dsn = os.getenv("DB_DSN").replace("postgres://", "postgresql://", 1)
engine = create_engine(dsn)

with engine.connect() as c:
    tables = c.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' ORDER BY table_name"
    )).fetchall()
    
    print(f"{'Table':<20} {'PK Constraint':<30} {'PK Column(s)':<20} {'Data Type':<15} {'Auto-inc?'}")
    print("-" * 100)
    
    for (table_name,) in tables:
        # Find PK constraint and its columns
        pk_info = c.execute(text("""
            SELECT tc.constraint_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = :tbl 
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
        """), {"tbl": table_name}).fetchall()
        
        if pk_info:
            pk_name = pk_info[0][0]
            pk_cols = ", ".join(r[1] for r in pk_info)
            
            # Check data type and default (serial/identity)
            col_details = []
            for _, col_name in pk_info:
                col = c.execute(text("""
                    SELECT data_type, column_default
                    FROM information_schema.columns
                    WHERE table_name = :tbl AND column_name = :col
                """), {"tbl": table_name, "col": col_name}).fetchone()
                
                dtype = col[0] if col else "?"
                default = col[1] if col else ""
                is_auto = "YES" if default and "nextval" in str(default) else "no"
                col_details.append((dtype, is_auto))
            
            dtype_str = col_details[0][0] if col_details else "?"
            auto_str = col_details[0][1] if col_details else "?"
            print(f"  {table_name:<18} {pk_name:<30} {pk_cols:<20} {dtype_str:<15} {auto_str}")
        else:
            print(f"  {table_name:<18} {'*** NO PRIMARY KEY ***':<30}")
