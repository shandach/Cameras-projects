
import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import DeclarativeMeta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_schema(engine: Engine, base_model: DeclarativeMeta):
    """
    Automatically adds missing columns to SQLite tables based on SQLAlchemy models.
    Does NOT support column removal or type changes due to SQLite limitations.
    """
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # Create a fresh connection for schema updates
    with engine.connect() as conn:
        for table_name, table_obj in base_model.metadata.tables.items():
            if table_name in existing_tables:
                # Get existing columns in DB (just names for now)
                existing_columns = [
                    col['name'] for col in inspector.get_columns(table_name)
                ]
                
                # Check model columns
                for column in table_obj.columns:
                    if column.name not in existing_columns:
                        # Found a missing column in DB!
                        
                        # Determine SQL type string
                        col_type = column.type.compile(engine.dialect)
                        
                        # Determine Default value SQL fragment
                        default_sql = ""
                        if column.default is not None:
                            arg = column.default.arg
                            # Only support simple scalar defaults for migration safety
                            if isinstance(arg, (str, int, float, bool)):
                                if isinstance(arg, bool):
                                    val = 1 if arg else 0
                                    default_sql = f"DEFAULT {val}"
                                elif isinstance(arg, str):
                                    default_sql = f"DEFAULT '{arg}'"
                                else:
                                    default_sql = f"DEFAULT {arg}"
                        
                        # SQLite ALTER TABLE ADD COLUMN syntax:
                        # ALTER TABLE table_name ADD COLUMN column_name column_type [DEFAULT default_value]
                        # Note: NOT NULL constraints on added columns are only allowed if there is a DEFAULT value
                        
                        try:
                            sql = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}"
                            if default_sql:
                                sql += f" {default_sql}"
                            
                            print(f"[MIGRATE] Adding column: {table_name}.{column.name} ({col_type})")
                            conn.execute(text(sql))
                            print(f"[MIGRATE] SUCCESS: Added {column.name}")
                        except Exception as e:
                            print(f"[MIGRATE] ERROR adding {column.name} to {table_name}: {e}")
            else:
                # Table doesn't exist - database.create_all() should have handled this, 
                # but if not, we leave it be as create_all is called before this function.
                pass
