"""
Multi-Role System Migration
Creates tables to support users having multiple roles with role switching.

Tables:
- user_assigned_roles: Many-to-many relationship between users and roles
- user_active_role: Tracks which role the user is currently viewing as
"""

import os
import logging
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def run_migration():
    """Run the multi-role system migration."""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    # Fix postgres:// prefix for SQLAlchemy
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url)

    try:
        with engine.begin() as conn:
            # 1. Create user_assigned_roles table
            logger.info("Creating user_assigned_roles table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_assigned_roles (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    role_id INTEGER NOT NULL REFERENCES onboarding_roles(id) ON DELETE CASCADE,
                    assigned_at TIMESTAMP DEFAULT NOW(),
                    assigned_by INTEGER REFERENCES users(id),
                    is_primary BOOLEAN DEFAULT FALSE,
                    UNIQUE(user_id, role_id)
                );

                CREATE INDEX IF NOT EXISTS idx_user_assigned_roles_user_id
                    ON user_assigned_roles(user_id);
                CREATE INDEX IF NOT EXISTS idx_user_assigned_roles_role_id
                    ON user_assigned_roles(role_id);
            """))
            logger.info("user_assigned_roles table created")

            # 2. Create user_active_role table
            logger.info("Creating user_active_role table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_active_role (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    active_role_id INTEGER NOT NULL REFERENCES onboarding_roles(id),
                    switched_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_user_active_role_user_id
                    ON user_active_role(user_id);
            """))
            logger.info("user_active_role table created")

            # 3. Migrate existing users from onboarding_user_profiles
            logger.info("Migrating existing users...")
            conn.execute(text("""
                INSERT INTO user_assigned_roles (user_id, role_id, assigned_at, is_primary)
                SELECT
                    oup.user_id,
                    oup.role_id,
                    COALESCE(oup.created_at, NOW()),
                    TRUE
                FROM onboarding_user_profiles oup
                WHERE oup.user_id IS NOT NULL
                    AND oup.role_id IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM user_assigned_roles uar
                        WHERE uar.user_id = oup.user_id AND uar.role_id = oup.role_id
                    )
            """))

            # 4. Set active roles for migrated users
            logger.info("Setting active roles for existing users...")
            conn.execute(text("""
                INSERT INTO user_active_role (user_id, active_role_id, switched_at)
                SELECT
                    uar.user_id,
                    uar.role_id,
                    NOW()
                FROM user_assigned_roles uar
                WHERE uar.is_primary = TRUE
                    AND NOT EXISTS (
                        SELECT 1 FROM user_active_role uac
                        WHERE uac.user_id = uar.user_id
                    )
            """))

            logger.info("Multi-role system migration completed successfully")
            return True

    except SQLAlchemyError as e:
        logger.error(f"Migration failed: {e}")
        return False


def check_migration_status():
    """Check if the migration has been applied."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return {"applied": False, "error": "DATABASE_URL not set"}

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url)

    try:
        with engine.connect() as conn:
            # Check if tables exist
            result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                    AND table_name IN ('user_assigned_roles', 'user_active_role')
            """))
            tables = [row[0] for row in result.fetchall()]

            return {
                "applied": len(tables) == 2,
                "tables_found": tables,
                "missing": [t for t in ['user_assigned_roles', 'user_active_role'] if t not in tables]
            }
    except Exception as e:
        return {"applied": False, "error": str(e)}


if __name__ == "__main__":
    run_migration()
