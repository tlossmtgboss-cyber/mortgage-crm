"""
Migration: Add soft-delete columns to core CRM tables.

Adds `deleted_at` (TIMESTAMP, indexed) and `deleted_by_id` (INTEGER) to:
  - leads
  - loans
  - activities
  - stage_history
  - documents
  - tasks

These tables contain borrower-facing records subject to NMLS/RESPA/TRID
audit retention requirements. Hard-deleting these rows violates
regulatory record-keeping obligations. This migration enables the
SoftDeleteMixin pattern defined in database/mixins.py.

Idempotent: uses ADD COLUMN IF NOT EXISTS (PostgreSQL) or catches
duplicate-column errors (SQLite).

Usage:
    # Dry run (prints SQL, does not execute)
    python -m migrations.add_soft_delete_core_tables --dry-run

    # Execute
    python -m migrations.add_soft_delete_core_tables

    # From code
    from migrations.add_soft_delete_core_tables import run_migration
    run_migration(dry_run=False)
"""

import argparse
import os
import sys
import logging

# Allow running from the backend/ directory or from migrations/ directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tables and columns to add
# ---------------------------------------------------------------------------

TARGET_TABLES = [
    "leads",
    "loans",
    "activities",
    "stage_history",
    "documents",
    "tasks",
]

COLUMNS = [
    # (column_name, pg_type, sqlite_type, default)
    ("deleted_at", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP", None),
    ("deleted_by_id", "INTEGER", "INTEGER", None),
]


# ---------------------------------------------------------------------------
# Migration logic
# ---------------------------------------------------------------------------

def _build_statements(is_sqlite: bool):
    """Generate all DDL statements for the migration.

    Returns a list of (description, sql_text) tuples.
    """
    stmts = []

    for table in TARGET_TABLES:
        for col_name, pg_type, sqlite_type, default in COLUMNS:
            col_type = sqlite_type if is_sqlite else pg_type
            default_clause = f" DEFAULT {default}" if default is not None else ""

            if is_sqlite:
                # SQLite does not support IF NOT EXISTS on ADD COLUMN.
                # The caller wraps this in try/except to handle duplicates.
                sql = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}{default_clause}"
            else:
                sql = (
                    f"ALTER TABLE {table} "
                    f"ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default_clause}"
                )
            stmts.append((f"Add {col_name} to {table}", sql))

        # Index on deleted_at for query performance.
        # Partial index (WHERE deleted_at IS NOT NULL) keeps the index tiny
        # because most rows will have deleted_at = NULL.
        idx_name = f"ix_{table}_deleted_at"
        if is_sqlite:
            idx_sql = (
                f"CREATE INDEX IF NOT EXISTS {idx_name} "
                f"ON {table} (deleted_at)"
            )
        else:
            idx_sql = (
                f"CREATE INDEX IF NOT EXISTS {idx_name} "
                f"ON {table} (deleted_at) WHERE deleted_at IS NOT NULL"
            )
        stmts.append((f"Create index {idx_name}", idx_sql))

    return stmts


def run_migration(dry_run: bool = False) -> bool:
    """Execute the migration.

    Args:
        dry_run: If True, print the SQL statements without executing them.

    Returns:
        True on success, False on failure.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable is not set")
        return False

    # Fix Railway postgres:// prefix
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    is_sqlite = "sqlite" in database_url.lower()
    stmts = _build_statements(is_sqlite)

    if dry_run:
        logger.info("=== DRY RUN — no changes will be made ===")
        for desc, sql in stmts:
            logger.info(f"  [{desc}]  {sql}")
        logger.info(f"=== {len(stmts)} statements would be executed ===")
        return True

    engine = create_engine(database_url)
    added = 0
    skipped = 0
    errors = 0

    with engine.connect() as conn:
        for desc, sql in stmts:
            try:
                conn.execute(text(sql))
                added += 1
                logger.info(f"  OK  {desc}")
            except Exception as e:
                err_lower = str(e).lower()
                if "duplicate column" in err_lower or "already exists" in err_lower:
                    skipped += 1
                    logger.info(f"  SKIP  {desc} (already exists)")
                else:
                    errors += 1
                    logger.error(f"  FAIL  {desc}: {e}")

        conn.commit()

    logger.info(
        f"Migration complete: {added} applied, {skipped} skipped, {errors} errors "
        f"across {len(TARGET_TABLES)} tables"
    )
    return errors == 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add soft-delete columns (deleted_at, deleted_by_id) to core CRM tables."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SQL statements without executing them.",
    )
    args = parser.parse_args()

    success = run_migration(dry_run=args.dry_run)
    if success:
        print("Migration completed successfully.")
    else:
        print("Migration failed — see log output above.")
        sys.exit(1)
