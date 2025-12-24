"""
Migration: Add workflow role assignment tables

Creates the lead_workflow_role_assignments and loan_workflow_role_assignments
tables needed for the workflow task generation system.

Run with:
    python -m migrations.add_role_assignment_tables
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


MIGRATION_SQL = """
-- Lead-level role assignments
CREATE TABLE IF NOT EXISTS lead_workflow_role_assignments (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by_id INTEGER REFERENCES users(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    deactivated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Loan-level role assignments
CREATE TABLE IF NOT EXISTS loan_workflow_role_assignments (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    loan_id INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by_id INTEGER REFERENCES users(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    deactivated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS ix_lead_role_assignments_lead
    ON lead_workflow_role_assignments(lead_id, is_active);

CREATE INDEX IF NOT EXISTS ix_lead_role_assignments_user
    ON lead_workflow_role_assignments(assigned_user_id, is_active);

CREATE INDEX IF NOT EXISTS ix_loan_role_assignments_loan
    ON loan_workflow_role_assignments(loan_id, is_active);

CREATE INDEX IF NOT EXISTS ix_loan_role_assignments_user
    ON loan_workflow_role_assignments(assigned_user_id, is_active);
"""


def run_migration(db: Session = None) -> dict:
    """
    Run the role assignment tables migration.

    Args:
        db: Optional SQLAlchemy session. If not provided, creates a new connection.

    Returns:
        dict with migration results
    """
    results = {
        'success': True,
        'tables_created': [],
        'errors': [],
        'warnings': []
    }

    if db is not None:
        # Use provided session
        try:
            conn = db.connection()
            _execute_migration(conn, results)
            db.commit()
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            results['success'] = False
            results['errors'].append(str(e))
            db.rollback()
    else:
        # Create new connection
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            try:
                _execute_migration(conn, results)
                conn.commit()
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                results['success'] = False
                results['errors'].append(str(e))
                conn.rollback()
                raise

    return results


def _execute_migration(conn, results: dict):
    """Execute the migration SQL."""
    # Check if tables already exist
    for table_name in ['lead_workflow_role_assignments', 'loan_workflow_role_assignments']:
        result = conn.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :name AND table_schema = 'public'
        """), {'name': table_name})

        if result.fetchone():
            logger.info(f"Table {table_name} already exists")
            results['warnings'].append(f"Table {table_name} already exists")
        else:
            logger.info(f"Table {table_name} will be created")

    # Execute migration
    logger.info("Executing role assignment tables migration...")
    conn.execute(text(MIGRATION_SQL))

    # Verify tables were created
    for table_name in ['lead_workflow_role_assignments', 'loan_workflow_role_assignments']:
        result = conn.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :name AND table_schema = 'public'
        """), {'name': table_name})

        if result.fetchone():
            results['tables_created'].append(table_name)
            logger.info(f"Table {table_name} verified")
        else:
            results['errors'].append(f"Table {table_name} not found after migration")

    logger.info(f"Migration complete: {results}")


def check_status() -> dict:
    """Check if the role assignment tables exist."""
    engine = create_engine(DATABASE_URL)

    status = {
        'tables': {},
        'needs_migration': False
    }

    with engine.connect() as conn:
        for table_name in ['lead_workflow_role_assignments', 'loan_workflow_role_assignments']:
            result = conn.execute(text("""
                SELECT 1 FROM information_schema.tables
                WHERE table_name = :name AND table_schema = 'public'
            """), {'name': table_name})

            exists = result.fetchone() is not None
            status['tables'][table_name] = exists

            if not exists:
                status['needs_migration'] = True

    return status


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Add workflow role assignment tables")
    parser.add_argument('--check', action='store_true', help='Check status without running migration')
    args = parser.parse_args()

    if args.check:
        status = check_status()
        print(f"Status: {status}")
        if status['needs_migration']:
            print("Migration needed - run without --check to apply")
    else:
        result = run_migration()
        print(f"Migration result: {result}")
        if result['success']:
            print("Migration completed successfully!")
        else:
            print("Migration failed!")
            sys.exit(1)
