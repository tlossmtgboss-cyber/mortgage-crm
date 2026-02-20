"""
Database Migration Script
Adds missing onboarding_completed column to users table
"""

import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    exit(1)

# Replace postgres:// with postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def add_onboarding_completed_column():
    """Add onboarding_completed column if it doesn't exist"""
    with engine.connect() as conn:
        try:
            # Check if column exists
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='users'
                AND column_name='onboarding_completed'
            """))

            if result.fetchone() is None:
                print("Adding onboarding_completed column...")
                conn.execute(text("""
                    ALTER TABLE users
                    ADD COLUMN onboarding_completed BOOLEAN DEFAULT FALSE
                """))
                conn.commit()
                print("✓ Column added successfully")
            else:
                print("✓ Column already exists")

        except Exception as e:
            print(f"Error: {e}")
            conn.rollback()
            raise

def add_user_roles_tables():
    """Create user roles tables if they don't exist"""
    print("Checking user roles tables...")
    with engine.connect() as conn:
        try:
            # Check if user_assigned_roles table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'user_assigned_roles'
                )
            """))
            
            if not result.fetchone()[0]:
                print("Creating user roles tables...")
                # Read and execute the migration SQL
                import os
                migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations')
                sql_file = os.path.join(migrations_dir, 'add_user_roles_tables.sql')
                
                with open(sql_file, 'r') as f:
                    sql = f.read()
                
                # Execute each statement separately
                for statement in sql.split(';'):
                    statement = statement.strip()
                    if statement:
                        conn.execute(text(statement))
                
                conn.commit()
                print("✓ User roles tables created successfully")
            else:
                print("✓ User roles tables already exist")
        except Exception as e:
            print(f"Error: {e}")
            conn.rollback()
            raise


if __name__ == "__main__":
    print("Running database migration...")
    add_onboarding_completed_column()
    add_user_roles_tables()
    print("Migration complete!")
