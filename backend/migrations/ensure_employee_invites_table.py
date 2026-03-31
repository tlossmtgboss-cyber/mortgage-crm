"""
Migration: Ensure employee_invites table exists with all columns

Creates the employee_invites table IF NOT EXISTS, matching the EmployeeInvite
model in database/models/permission.py. Also adds the organization_id column
(for multi-tenant isolation) if missing, and creates relevant indexes.

Uses VARCHAR for the status column instead of a PostgreSQL ENUM type to avoid
enum creation/migration issues.

Usage:
    python -m migrations.ensure_employee_invites_table
    # or
    from migrations.ensure_employee_invites_table import run_migration
    run_migration(engine)
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


# Columns to ensure exist via ADD COLUMN IF NOT EXISTS (for cases where
# the table was previously created without these columns).
ADDITIONAL_COLUMNS = [
    ("organization_id", "INTEGER REFERENCES organizations(id)"),
    ("job_title", "VARCHAR(100)"),
    ("initial_config", "JSONB DEFAULT '{}'"),
]

# Indexes to create
INDEXES = [
    ("ix_employee_invites_email", "employee_invites", "email"),
    ("ix_employee_invites_invite_token", "employee_invites", "invite_token"),
    ("ix_employee_invites_status", "employee_invites", "status"),
    ("ix_employee_invites_organization_id", "employee_invites", "organization_id"),
]


def run_migration(engine=None):
    """Create employee_invites table if it doesn't exist and ensure all columns."""
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    with engine.connect() as conn:
        # ------------------------------------------------------------------
        # Step 1: Create the table if it doesn't exist
        # ------------------------------------------------------------------
        logger.info("Ensuring employee_invites table exists...")
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS employee_invites (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    job_title VARCHAR(100),
                    permission_role VARCHAR(50) NOT NULL DEFAULT 'sales',
                    invite_token VARCHAR(64) UNIQUE NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    accepted_at TIMESTAMPTZ,
                    invited_by_user_id INTEGER REFERENCES users(id),
                    user_id INTEGER REFERENCES users(id),
                    branch_id INTEGER REFERENCES branches(id),
                    organization_id INTEGER REFERENCES organizations(id),
                    initial_config JSONB DEFAULT '{}'
                )
            """))
            conn.commit()
            logger.info("  employee_invites table created/verified")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  employee_invites table already exists")
            else:
                logger.error(f"Failed to create employee_invites table: {e}")
                return False

        # ------------------------------------------------------------------
        # Step 2: Ensure additional columns exist (for tables created before
        #         organization_id or other columns were added to the model)
        # ------------------------------------------------------------------
        added = 0
        skipped = 0
        for col_name, col_type in ADDITIONAL_COLUMNS:
            try:
                conn.execute(text(
                    f"ALTER TABLE employee_invites ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                added += 1
            except Exception as e:
                error_str = str(e).lower()
                if "duplicate column" in error_str or "already exists" in error_str:
                    skipped += 1
                else:
                    logger.warning(f"Could not add {col_name} to employee_invites: {e}")

        if added > 0 or skipped > 0:
            conn.commit()
            logger.info(f"  employee_invites columns: {added} ensured, {skipped} already existed")

        # ------------------------------------------------------------------
        # Step 3: Create indexes
        # ------------------------------------------------------------------
        for idx_name, table, column in INDEXES:
            try:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})"
                ))
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str:
                    pass
                else:
                    logger.warning(f"Could not create index {idx_name}: {e}")

        conn.commit()
        logger.info("  employee_invites indexes ensured")

    logger.info("Employee invites migration complete")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
