"""
Migration: Add enterprise-grade DB constraints to employee_invites and users tables.

Idempotent -- safe to run multiple times.

Adds:
  1. ON DELETE CASCADE / SET NULL for all foreign keys on employee_invites
  2. Partial unique index preventing duplicate pending invites per org
  3. CHECK constraints on users.first_name / last_name (non-empty)
  4. Makes invite_token nullable (tokens cleared after use)

Usage:
    python -m migrations.add_employee_invite_constraints
    # or
    from migrations.add_employee_invite_constraints import run_migration
    run_migration(engine)
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


# Foreign key definitions: (column, referenced_table, referenced_column, on_delete, desired_constraint_name)
FK_DEFINITIONS = [
    ("invited_by_user_id", "users", "id", "SET NULL", "fk_employee_invites_invited_by_user_id"),
    ("user_id", "users", "id", "SET NULL", "fk_employee_invites_user_id"),
    ("branch_id", "branches", "id", "SET NULL", "fk_employee_invites_branch_id"),
    ("organization_id", "organizations", "id", "CASCADE", "fk_employee_invites_organization_id"),
]


def run_migration(engine=None):
    """Add enterprise constraints to employee_invites and users tables."""
    if engine is None:
        from db import get_engine
        engine = get_engine()

    with engine.connect() as conn:
        # ------------------------------------------------------------------
        # Step 1: Recreate foreign keys with ON DELETE behaviour
        # ------------------------------------------------------------------
        for col, ref_table, ref_col, on_delete, fk_name in FK_DEFINITIONS:
            # First, find and drop any existing FK constraint on this column.
            # Constraint names vary across environments so we look them up from
            # the information_schema.
            try:
                existing = conn.execute(text("""
                    SELECT tc.constraint_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    WHERE tc.table_name = 'employee_invites'
                        AND tc.constraint_type = 'FOREIGN KEY'
                        AND kcu.column_name = :col
                """), {"col": col}).fetchall()

                for row in existing:
                    old_name = row[0]
                    try:
                        conn.execute(text(
                            f"ALTER TABLE employee_invites DROP CONSTRAINT IF EXISTS {old_name}"
                        ))
                        logger.info(f"  Dropped old FK {old_name} on employee_invites.{col}")
                    except Exception as drop_err:
                        logger.warning(f"  Could not drop FK {old_name}: {drop_err}")

                # Add the new FK with ON DELETE clause
                conn.execute(text(f"""
                    ALTER TABLE employee_invites
                    ADD CONSTRAINT {fk_name}
                    FOREIGN KEY ({col}) REFERENCES {ref_table}({ref_col})
                    ON DELETE {on_delete}
                """))
                conn.commit()
                logger.info(f"  Added FK {fk_name} ON DELETE {on_delete}")

            except Exception as e:
                conn.rollback()
                error_str = str(e).lower()
                if "already exists" in error_str:
                    logger.info(f"  FK {fk_name} already exists, skipping")
                else:
                    logger.warning(f"  Could not set FK on employee_invites.{col}: {e}")

        # ------------------------------------------------------------------
        # Step 2: Partial unique index -- one pending invite per email per org
        # ------------------------------------------------------------------
        try:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_invite_per_org
                ON employee_invites (email, organization_id)
                WHERE status = 'pending'
            """))
            conn.commit()
            logger.info("  Created partial unique index uq_pending_invite_per_org")
        except Exception as e:
            conn.rollback()
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  Partial unique index uq_pending_invite_per_org already exists")
            else:
                logger.warning(f"  Could not create partial unique index: {e}")

        # ------------------------------------------------------------------
        # Step 3: CHECK constraints on users.first_name / last_name
        # ------------------------------------------------------------------
        for col_name in ("first_name", "last_name"):
            constraint_name = f"chk_user_{col_name}_not_empty"
            try:
                conn.execute(text(f"""
                    ALTER TABLE users
                    ADD CONSTRAINT {constraint_name}
                    CHECK ({col_name} IS NOT NULL AND {col_name} != '')
                """))
                conn.commit()
                logger.info(f"  Added CHECK constraint {constraint_name}")
            except Exception as e:
                conn.rollback()
                error_str = str(e).lower()
                if "already exists" in error_str:
                    logger.info(f"  CHECK constraint {constraint_name} already exists")
                elif "violates check constraint" in error_str or "check constraint" in error_str:
                    logger.warning(
                        f"  Cannot add {constraint_name}: existing data violates the constraint. "
                        f"Clean up NULL/empty {col_name} values in users table first."
                    )
                else:
                    logger.warning(f"  Could not add CHECK constraint {constraint_name}: {e}")

        # ------------------------------------------------------------------
        # Step 4: Make invite_token nullable (tokens cleared after use)
        # ------------------------------------------------------------------
        try:
            conn.execute(text("""
                ALTER TABLE employee_invites
                ALTER COLUMN invite_token DROP NOT NULL
            """))
            conn.commit()
            logger.info("  Made invite_token nullable")
        except Exception as e:
            conn.rollback()
            error_str = str(e).lower()
            # If the column is already nullable, Postgres silently succeeds,
            # so this branch is unlikely but kept for safety.
            if "already" in error_str:
                logger.info("  invite_token is already nullable")
            else:
                logger.warning(f"  Could not make invite_token nullable: {e}")

    logger.info("Employee invite constraints migration complete")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
