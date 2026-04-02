"""
Migration: Create Onboarding Roles Table
Creates the onboarding_roles table which is required by the multi-role system.

This table stores available roles that can be assigned to users.
Must run BEFORE add_multi_role_system.py migration.

Run with: python migrations/create_onboarding_roles_table.py
"""

import os
import sys
import logging
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_database_url():
    """Get and fix database URL."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return None

    # Fix postgres:// prefix for SQLAlchemy
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    return database_url


def run_migration():
    """Create the onboarding_roles table and seed default roles."""
    database_url = get_database_url()
    if not database_url:
        return False

    engine = create_engine(database_url)

    try:
        with engine.begin() as conn:
            # Check if table already exists
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'onboarding_roles'
            """))

            if result.fetchone():
                logger.info("onboarding_roles table already exists, checking for missing roles...")
            else:
                # Create the onboarding_roles table
                logger.info("Creating onboarding_roles table...")
                conn.execute(text("""
                    CREATE TABLE onboarding_roles (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL UNIQUE,
                        description TEXT,
                        is_active BOOLEAN DEFAULT true,
                        display_order INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    );

                    CREATE INDEX idx_onboarding_roles_name ON onboarding_roles(name);
                    CREATE INDEX idx_onboarding_roles_active ON onboarding_roles(is_active);
                """))
                logger.info("onboarding_roles table created successfully")

            # Seed default roles
            logger.info("Seeding default roles...")

            default_roles = [
                ("Site Administrator", "Master site administrator with system-wide access across all tenants", 1),
                ("Company Admin", "Company/Organization administrator with full tenant-level access", 2),
                ("Admin", "System administrator with full access", 3),
                ("Executive Management", "Executive management team with reporting access", 10),
                ("Branch Manager", "Branch manager overseeing branch operations", 20),
                ("Operations Manager", "Operations manager overseeing daily operations", 25),
                ("Management", "Management role with team oversight", 30),
                ("Team Lead", "Team lead with limited management access", 35),
                ("Loan Officer", "Loan officer handling client relationships and loan origination", 40),
                ("Senior Loan Officer", "Senior loan officer with mentoring responsibilities", 41),
                ("Processor", "Loan processor handling file preparation and documentation", 50),
                ("Senior Processor", "Senior processor with quality review responsibilities", 51),
                ("Underwriter", "Loan underwriter reviewing and approving loans", 60),
                ("Senior Underwriter", "Senior underwriter with escalation authority", 61),
                ("Closer", "Loan closer handling closing process", 70),
                ("Funder", "Funder handling loan funding", 75),
                ("Post-Closer", "Post-closer handling post-closing tasks", 80),
                ("Shipper", "Shipper handling loan shipping to investors", 85),
                ("Compliance Officer", "Compliance officer ensuring regulatory compliance", 90),
                ("Marketing", "Marketing team member", 100),
                ("IT Support", "IT support staff", 110),
                ("Customer Service", "Customer service representative", 120),
            ]

            now = datetime.now(timezone.utc)
            added = []
            skipped = []

            for name, description, display_order in default_roles:
                # Check if role exists
                existing = conn.execute(
                    text("SELECT id FROM onboarding_roles WHERE name = :name"),
                    {"name": name}
                ).fetchone()

                if existing:
                    skipped.append(name)
                else:
                    conn.execute(
                        text("""
                            INSERT INTO onboarding_roles (name, description, display_order, is_active, created_at, updated_at)
                            VALUES (:name, :description, :display_order, true, :now, :now)
                        """),
                        {
                            "name": name,
                            "description": description,
                            "display_order": display_order,
                            "now": now
                        }
                    )
                    added.append(name)

            logger.info(f"Added {len(added)} roles: {added}")
            if skipped:
                logger.info(f"Skipped {len(skipped)} existing roles: {skipped}")

            # Now create the multi-role system tables if they don't exist
            logger.info("Creating multi-role system tables...")

            # Create user_assigned_roles table
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'user_assigned_roles'
            """))

            if not result.fetchone():
                logger.info("Creating user_assigned_roles table...")
                conn.execute(text("""
                    CREATE TABLE user_assigned_roles (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        role_id INTEGER NOT NULL REFERENCES onboarding_roles(id) ON DELETE CASCADE,
                        assigned_at TIMESTAMP DEFAULT NOW(),
                        assigned_by INTEGER REFERENCES users(id),
                        is_primary BOOLEAN DEFAULT FALSE,
                        UNIQUE(user_id, role_id)
                    );

                    CREATE INDEX idx_user_assigned_roles_user_id ON user_assigned_roles(user_id);
                    CREATE INDEX idx_user_assigned_roles_role_id ON user_assigned_roles(role_id);
                """))
                logger.info("user_assigned_roles table created")
            else:
                logger.info("user_assigned_roles table already exists")

            # Create user_active_role table
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'user_active_role'
            """))

            if not result.fetchone():
                logger.info("Creating user_active_role table...")
                conn.execute(text("""
                    CREATE TABLE user_active_role (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                        active_role_id INTEGER NOT NULL REFERENCES onboarding_roles(id),
                        switched_at TIMESTAMP DEFAULT NOW()
                    );

                    CREATE INDEX idx_user_active_role_user_id ON user_active_role(user_id);
                """))
                logger.info("user_active_role table created")
            else:
                logger.info("user_active_role table already exists")

            # Assign default role to existing users who don't have one
            logger.info("Assigning default roles to users without roles...")

            # Get Loan Officer role ID as default
            lo_role = conn.execute(
                text("SELECT id FROM onboarding_roles WHERE name = 'Loan Officer'")
            ).fetchone()

            if lo_role:
                lo_role_id = lo_role[0]

                # Find users without any role assignment
                users_without_roles = conn.execute(text("""
                    SELECT u.id FROM users u
                    WHERE NOT EXISTS (
                        SELECT 1 FROM user_assigned_roles uar WHERE uar.user_id = u.id
                    )
                """)).fetchall()

                for user_row in users_without_roles:
                    user_id = user_row[0]
                    conn.execute(
                        text("""
                            INSERT INTO user_assigned_roles (user_id, role_id, assigned_at, is_primary)
                            VALUES (:user_id, :role_id, :now, true)
                            ON CONFLICT (user_id, role_id) DO NOTHING
                        """),
                        {"user_id": user_id, "role_id": lo_role_id, "now": now}
                    )

                if users_without_roles:
                    logger.info(f"Assigned Loan Officer role to {len(users_without_roles)} users")

            # Set active role for users without one
            conn.execute(text("""
                INSERT INTO user_active_role (user_id, active_role_id, switched_at)
                SELECT uar.user_id, uar.role_id, NOW()
                FROM user_assigned_roles uar
                WHERE uar.is_primary = TRUE
                AND NOT EXISTS (
                    SELECT 1 FROM user_active_role uac WHERE uac.user_id = uar.user_id
                )
            """))

            logger.info("Migration completed successfully!")
            return True

    except SQLAlchemyError as e:
        logger.error(f"Migration failed: {e}")
        return False


def check_status():
    """Check the current status of onboarding roles tables."""
    database_url = get_database_url()
    if not database_url:
        return

    engine = create_engine(database_url)

    with engine.connect() as conn:
        print("\n" + "=" * 60)
        print("Onboarding Roles System Status")
        print("=" * 60)

        # Check tables
        tables = ['onboarding_roles', 'user_assigned_roles', 'user_active_role']
        print("\nTables:")
        for table in tables:
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :table_name
            """), {"table_name": table})
            exists = result.fetchone() is not None
            status = "EXISTS" if exists else "MISSING"
            print(f"  {table}: {status}")

        # Check roles count
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM onboarding_roles"))
            count = result.fetchone()[0]
            print(f"\nRoles defined: {count}")

            # List roles
            roles = conn.execute(text("""
                SELECT id, name, is_active FROM onboarding_roles
                ORDER BY display_order, name
            """)).fetchall()

            print("\nAvailable roles:")
            for r in roles:
                status = "active" if r[2] else "inactive"
                print(f"  [{r[0]:3d}] {r[1]} ({status})")

        except Exception as e:
            print(f"\nCould not query roles: {e}")

        # Check user role assignments
        try:
            result = conn.execute(text("""
                SELECT COUNT(DISTINCT user_id) FROM user_assigned_roles
            """))
            users_with_roles = result.fetchone()[0]

            result = conn.execute(text("SELECT COUNT(*) FROM users"))
            total_users = result.fetchone()[0]

            print(f"\nUsers with roles: {users_with_roles} / {total_users}")
        except Exception as e:
            print(f"\nCould not query user roles: {e}")

        print("\n" + "=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        check_status()
    else:
        success = run_migration()
        sys.exit(0 if success else 1)
