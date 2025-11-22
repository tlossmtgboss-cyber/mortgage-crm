"""
Migration: Add AI Task Automation Tables
Creates tables for AI task learning and automation system
"""
import sys
sys.path.append('..')

from sqlalchemy import create_engine, text
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


def run_migration():
    """Create AI Task Automation tables"""
    
    # Read the SQL file
    migration_dir = os.path.dirname(__file__)
    sql_file = os.path.join(migration_dir, 'add_ai_task_automation.sql')
    
    with open(sql_file, 'r') as f:
        sql_content = f.read()
    
    # Split into individual statements and execute
    # We need to handle this carefully because of multi-line statements
    with engine.connect() as conn:
        try:
            # Execute the entire SQL file
            # PostgreSQL can handle multiple statements
            conn.execute(text(sql_content))
            conn.commit()
            logger.info("AI Task Automation tables created successfully")
            
            # Verify tables were created
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name LIKE 'ai_%'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]
            
            logger.info(f"Created AI tables: {tables}")
            
            # Check tasks table columns
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'tasks' 
                AND column_name LIKE 'ai_%'
                ORDER BY column_name
            """))
            columns = [row[0] for row in result]
            
            logger.info(f"Added columns to tasks table: {columns}")
            
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            conn.rollback()
            raise


if __name__ == "__main__":
    try:
        success = run_migration()
        if success:
            print("Migration completed successfully!")
        else:
            print("Migration failed")
            sys.exit(1)
    except Exception as e:
        print(f"Migration error: {e}")
        sys.exit(1)
