"""
Add Password Policy Tables — SOC 2 Type II CC6.1

Creates:
  - password_history: stores bcrypt hashes for reuse prevention (last 12)
  - login_attempts: immutable audit log of authentication attempts

Adds columns to users table:
  - password_changed_at (if not already present)
  - failed_login_count (alias check — model uses failed_login_attempts)
  - locked_until (if not already present)

All three user columns may already exist from earlier enterprise-readiness
migrations; the script uses IF NOT EXISTS / duplicate-column guards.

Usage:
    python -m migrations.add_password_policy_tables
    # or
    from migrations.add_password_policy_tables import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Create password policy tables and ensure user columns exist."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        # ------------------------------------------------------------------
        # 1. Create password_history table
        # ------------------------------------------------------------------
        logger.info("Creating password_history table...")
        try:
            if is_sqlite:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS password_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        hashed_password TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS password_history (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        hashed_password VARCHAR NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                    )
                """))
            logger.info("  password_history table ready")
        except Exception as e:
            logger.error("  Failed to create password_history: %s", e)

        # Indexes for password_history
        for idx_name, idx_sql in [
            (
                "ix_password_history_user_id",
                "CREATE INDEX IF NOT EXISTS ix_password_history_user_id ON password_history (user_id)",
            ),
            (
                "ix_password_history_user_created",
                "CREATE INDEX IF NOT EXISTS ix_password_history_user_created ON password_history (user_id, created_at)",
            ),
        ]:
            try:
                conn.execute(text(idx_sql))
                logger.info("  Created index %s", idx_name)
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info("  Index %s already exists", idx_name)
                else:
                    logger.warning("  Could not create index %s: %s", idx_name, e)

        # ------------------------------------------------------------------
        # 2. Create login_attempts table
        # ------------------------------------------------------------------
        logger.info("Creating login_attempts table...")
        try:
            if is_sqlite:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS login_attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        ip_address VARCHAR(45),
                        success BOOLEAN NOT NULL DEFAULT 0,
                        failure_reason VARCHAR(100)
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS login_attempts (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        attempted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                        ip_address VARCHAR(45),
                        success BOOLEAN NOT NULL DEFAULT FALSE,
                        failure_reason VARCHAR(100)
                    )
                """))
            logger.info("  login_attempts table ready")
        except Exception as e:
            logger.error("  Failed to create login_attempts: %s", e)

        # Indexes for login_attempts
        for idx_name, idx_sql in [
            (
                "ix_login_attempts_user_id",
                "CREATE INDEX IF NOT EXISTS ix_login_attempts_user_id ON login_attempts (user_id)",
            ),
            (
                "ix_login_attempts_user_attempted",
                "CREATE INDEX IF NOT EXISTS ix_login_attempts_user_attempted ON login_attempts (user_id, attempted_at)",
            ),
        ]:
            try:
                conn.execute(text(idx_sql))
                logger.info("  Created index %s", idx_name)
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info("  Index %s already exists", idx_name)
                else:
                    logger.warning("  Could not create index %s: %s", idx_name, e)

        # ------------------------------------------------------------------
        # 3. Ensure user columns exist (idempotent)
        # ------------------------------------------------------------------
        user_columns = [
            ("password_changed_at", "TIMESTAMP WITH TIME ZONE", None),
            ("failed_login_count", "INTEGER", "0"),
            ("locked_until", "TIMESTAMP", None),
        ]

        logger.info("Ensuring password policy columns on users table...")
        for col_name, col_type, default_value in user_columns:
            try:
                default_clause = ""
                if default_value is not None:
                    default_clause = f" DEFAULT {default_value}"

                if is_sqlite:
                    conn.execute(text(
                        f"ALTER TABLE users ADD COLUMN {col_name} {col_type}{default_clause}"
                    ))
                    logger.info("  Added %s to users", col_name)
                else:
                    conn.execute(text(
                        f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default_clause}"
                    ))
                    logger.info("  Ensured %s on users", col_name)
            except Exception as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    logger.info("  %s already exists on users, skipping", col_name)
                else:
                    logger.warning("  Could not add %s to users: %s", col_name, e)

        conn.commit()

    logger.info("Password policy migration complete")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if success:
        print("Password policy migration completed successfully")
    else:
        print("Password policy migration failed")
        exit(1)
