"""
Migration: Add SLA Workflow Task Generation System

This migration creates the complete database schema for the SLA-driven workflow
task generation system, including:

- New enum types (workflow_instance_status, workflow_task_status, etc.)
- workflow_instances table for tracking workflow lifecycles
- Extended workflow_task_instances with AI confidence and routing
- workflow_ai_confidence table for AI decision tracking
- lead_workflow_role_assignments and loan_workflow_role_assignments tables
- Column additions to tasks, roles, leads, and workflow_configurations
- Performance indexes
- Row-Level Security (RLS) policies

Run with:
    python -m migrations.add_workflow_sla_system

Or import and call run_migration(db) from startup.
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


def run_migration(db: Session = None) -> dict:
    """
    Run the SLA Workflow System migration.

    Args:
        db: Optional SQLAlchemy session. If not provided, creates a new connection.

    Returns:
        dict with migration results
    """
    results = {
        'success': True,
        'tables_created': [],
        'columns_added': [],
        'indexes_created': [],
        'enums_created': [],
        'errors': [],
        'warnings': []
    }

    # Read the SQL migration file
    migration_dir = Path(__file__).parent
    sql_file = migration_dir / 'add_workflow_sla_system.sql'

    if not sql_file.exists():
        results['success'] = False
        results['errors'].append(f"SQL file not found: {sql_file}")
        return results

    with open(sql_file, 'r') as f:
        sql_content = f.read()

    # Execute migration
    if db is not None:
        # Use provided session
        try:
            _execute_migration(db, sql_content, results)
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
                _execute_migration(conn, sql_content, results)
                conn.commit()
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                results['success'] = False
                results['errors'].append(str(e))
                conn.rollback()
                raise

    return results


def _execute_migration(conn, sql_content: str, results: dict):
    """Execute the SQL migration and track results."""

    # Execute the full SQL content
    # PostgreSQL can handle multiple statements
    conn.execute(text(sql_content))

    # Verify what was created
    _verify_enums(conn, results)
    _verify_tables(conn, results)
    _verify_columns(conn, results)
    _verify_indexes(conn, results)


def _verify_enums(conn, results: dict):
    """Verify enum types were created."""
    expected_enums = [
        'workflow_instance_status',
        'workflow_task_status',
        'workflow_task_type',
        'workflow_route',
        'lead_source_category'
    ]

    result = conn.execute(text("""
        SELECT typname FROM pg_type
        WHERE typtype = 'e'
        AND typname = ANY(:enums)
    """), {'enums': expected_enums})

    created_enums = [row[0] for row in result]
    results['enums_created'] = created_enums

    missing = set(expected_enums) - set(created_enums)
    if missing:
        results['warnings'].append(f"Expected enums not found: {missing}")

    logger.info(f"Enum types verified: {created_enums}")


def _verify_tables(conn, results: dict):
    """Verify tables were created."""
    expected_tables = [
        'workflow_instances',
        'workflow_ai_confidence',
        'lead_workflow_role_assignments',
        'loan_workflow_role_assignments'
    ]

    result = conn.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = ANY(:tables)
    """), {'tables': expected_tables})

    created_tables = [row[0] for row in result]
    results['tables_created'] = created_tables

    missing = set(expected_tables) - set(created_tables)
    if missing:
        results['warnings'].append(f"Expected tables not found: {missing}")

    logger.info(f"Tables verified: {created_tables}")


def _verify_columns(conn, results: dict):
    """Verify columns were added to existing tables."""
    column_checks = [
        ('tasks', 'workflow_task_instance_id'),
        ('tasks', 'task_group_key'),
        ('roles', 'abbreviation'),
        ('leads', 'source_category'),
        ('leads', 'source_vendor'),
        ('leads', 'current_workflow_instance_id'),
        ('loans', 'current_workflow_instance_id'),
        ('workflow_configurations', 'organization_id'),
        ('workflow_configurations', 'user_id'),
        ('workflow_configurations', 'is_system_template'),
        ('workflow_configurations', 'parent_template_id'),
        ('workflow_task_instances', 'workflow_instance_id'),
        ('workflow_task_instances', 'organization_id'),
        ('workflow_task_instances', 'task_type'),
        ('workflow_task_instances', 'route'),
        ('workflow_task_instances', 'task_group_key'),
        ('workflow_task_instances', 'linked_task_id'),
        ('workflow_task_instances', 'ai_eligible'),
        ('workflow_task_instances', 'ai_confidence'),
    ]

    added_columns = []
    for table, column in column_checks:
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table
            AND column_name = :column
        """), {'table': table, 'column': column})

        if result.fetchone():
            added_columns.append(f"{table}.{column}")

    results['columns_added'] = added_columns
    logger.info(f"Columns verified: {len(added_columns)} columns")


def _verify_indexes(conn, results: dict):
    """Verify indexes were created."""
    result = conn.execute(text("""
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
        AND indexname LIKE 'ix_workflow_%'
           OR indexname LIKE 'ix_lead_role_%'
           OR indexname LIKE 'ix_loan_role_%'
           OR indexname LIKE 'ix_tasks_workflow_%'
           OR indexname LIKE 'ix_tasks_group_%'
           OR indexname LIKE 'ix_leads_source_%'
    """))

    indexes = [row[0] for row in result]
    results['indexes_created'] = indexes
    logger.info(f"Indexes verified: {len(indexes)} indexes")


def check_migration_status(db: Session = None) -> dict:
    """
    Check if migration has been applied.

    Returns dict with status of each component.
    """
    status = {
        'enums': {},
        'tables': {},
        'columns': {},
        'fully_applied': True
    }

    if db is None:
        engine = create_engine(DATABASE_URL)
        conn = engine.connect()
    else:
        conn = db

    try:
        # Check enums
        for enum_name in ['workflow_instance_status', 'workflow_task_status',
                          'workflow_task_type', 'workflow_route', 'lead_source_category']:
            result = conn.execute(text("""
                SELECT 1 FROM pg_type WHERE typname = :name
            """), {'name': enum_name})
            exists = result.fetchone() is not None
            status['enums'][enum_name] = exists
            if not exists:
                status['fully_applied'] = False

        # Check tables
        for table_name in ['workflow_instances', 'workflow_ai_confidence',
                           'lead_workflow_role_assignments', 'loan_workflow_role_assignments']:
            result = conn.execute(text("""
                SELECT 1 FROM information_schema.tables
                WHERE table_name = :name AND table_schema = 'public'
            """), {'name': table_name})
            exists = result.fetchone() is not None
            status['tables'][table_name] = exists
            if not exists:
                status['fully_applied'] = False

        # Check key columns
        key_columns = [
            ('tasks', 'workflow_task_instance_id'),
            ('roles', 'abbreviation'),
            ('leads', 'source_category'),
            ('workflow_configurations', 'organization_id'),
        ]
        for table, column in key_columns:
            result = conn.execute(text("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = :table AND column_name = :column
            """), {'table': table, 'column': column})
            exists = result.fetchone() is not None
            status['columns'][f"{table}.{column}"] = exists
            if not exists:
                status['fully_applied'] = False

    finally:
        if db is None:
            conn.close()

    return status


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Run SLA Workflow System migration')
    parser.add_argument('--check', action='store_true', help='Check migration status without applying')
    parser.add_argument('--dry-run', action='store_true', help='Parse SQL but do not execute')
    args = parser.parse_args()

    if args.check:
        print("Checking migration status...")
        status = check_migration_status()
        print("\n=== Migration Status ===")
        print(f"Fully Applied: {status['fully_applied']}")
        print("\nEnums:")
        for name, exists in status['enums'].items():
            print(f"  {'[x]' if exists else '[ ]'} {name}")
        print("\nTables:")
        for name, exists in status['tables'].items():
            print(f"  {'[x]' if exists else '[ ]'} {name}")
        print("\nKey Columns:")
        for name, exists in status['columns'].items():
            print(f"  {'[x]' if exists else '[ ]'} {name}")
        sys.exit(0 if status['fully_applied'] else 1)

    if args.dry_run:
        print("Dry run - parsing SQL only...")
        migration_dir = Path(__file__).parent
        sql_file = migration_dir / 'add_workflow_sla_system.sql'
        if sql_file.exists():
            with open(sql_file, 'r') as f:
                content = f.read()
            print(f"SQL file loaded: {len(content)} characters")
            print("Dry run complete - no changes made")
        else:
            print(f"ERROR: SQL file not found: {sql_file}")
            sys.exit(1)
        sys.exit(0)

    print("Running SLA Workflow System migration...")
    try:
        results = run_migration()

        print("\n=== Migration Results ===")
        print(f"Success: {results['success']}")

        if results['enums_created']:
            print(f"\nEnums created/verified: {len(results['enums_created'])}")
            for enum in results['enums_created']:
                print(f"  - {enum}")

        if results['tables_created']:
            print(f"\nTables created/verified: {len(results['tables_created'])}")
            for table in results['tables_created']:
                print(f"  - {table}")

        if results['columns_added']:
            print(f"\nColumns added/verified: {len(results['columns_added'])}")
            for col in results['columns_added']:
                print(f"  - {col}")

        if results['indexes_created']:
            print(f"\nIndexes created/verified: {len(results['indexes_created'])}")

        if results['warnings']:
            print(f"\nWarnings:")
            for warning in results['warnings']:
                print(f"  - {warning}")

        if results['errors']:
            print(f"\nErrors:")
            for error in results['errors']:
                print(f"  - {error}")
            sys.exit(1)

        print("\nMigration completed successfully!")

    except Exception as e:
        print(f"\nMigration failed: {e}")
        sys.exit(1)
