"""
Migration: Add Workflow Roles
Adds all workflow roles to the roles table for team member assignment.

Run with: python -m migrations.add_workflow_roles
"""

import os
import sys
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

# All workflow roles from the Active Loan Workflow page
WORKFLOW_ROLES = [
    {"name": "Admin", "code": "ADM", "description": "System administrator with full access"},
    {"name": "Application Analysis", "code": "AA", "description": "Analyzes and processes loan applications"},
    {"name": "Branch Manager", "code": "BM", "description": "Branch manager overseeing branch operations"},
    {"name": "Closer", "code": "CLO", "description": "Handles loan closing process"},
    {"name": "Concierge", "code": "CON", "description": "Client-facing concierge support"},
    {"name": "Executive Management", "code": "EM", "description": "Executive management team"},
    {"name": "Funder", "code": "FUN", "description": "Handles loan funding process"},
    {"name": "Jr. Loan Officer", "code": "JLO", "description": "Junior loan officer in training"},
    {"name": "Jr. Processor", "code": "JP", "description": "Junior processor in training"},
    {"name": "Loan Officer", "code": "LO", "description": "Primary loan officer handling client relationships"},
    {"name": "Loan Officer Assistant", "code": "LOA", "description": "Assists loan officer with administrative tasks"},
    {"name": "Management", "code": "MAN", "description": "Management role with oversight responsibilities"},
    {"name": "Operations Manager", "code": "OM", "description": "Oversees daily operations"},
    {"name": "Processing Assistant", "code": "PA", "description": "Assists processor with loan processing tasks"},
    {"name": "Processor", "code": "PRO", "description": "Handles loan processing and documentation"},
    {"name": "Production Assistant 1", "code": "PA1", "description": "First level production assistant"},
    {"name": "Production Assistant 2", "code": "PA2", "description": "Second level production assistant"},
    {"name": "Site Admin", "code": "SA", "description": "Site-level administrator"},
    {"name": "Underwriter", "code": "UND", "description": "Reviews and approves loan applications"},
]


def run_migration():
    """Add workflow roles to the database."""
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable not set")
        return False

    # Fix postgres:// to postgresql://
    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # First, ensure the roles table exists
        print("Checking if roles table exists...")
        result = session.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'roles' AND table_schema = 'public'
        """))

        if not result.fetchone():
            print("Creating roles table...")
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS roles (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    code VARCHAR(10),
                    description TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            session.commit()
            print("Roles table created.")

        # Also create default_role_assignments table if it doesn't exist
        result = session.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'default_role_assignments' AND table_schema = 'public'
        """))

        if not result.fetchone():
            print("Creating default_role_assignments table...")
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS default_role_assignments (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL DEFAULT 1,
                    role_id INTEGER NOT NULL,
                    user_id INTEGER,
                    assigned_by_id INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(organization_id, role_id)
                )
            """))
            session.commit()
            print("default_role_assignments table created.")

        print("\nAdding workflow roles...")
        added_count = 0
        updated_count = 0
        skipped_count = 0

        for role in WORKFLOW_ROLES:
            # Check if role already exists
            existing = session.execute(
                text("SELECT id, code FROM roles WHERE name = :name"),
                {"name": role["name"]}
            ).fetchone()

            if existing:
                # Update code if needed
                if existing[1] != role["code"]:
                    session.execute(
                        text("""
                            UPDATE roles SET code = :code, description = :description,
                            updated_at = :now WHERE name = :name
                        """),
                        {
                            "name": role["name"],
                            "code": role["code"],
                            "description": role["description"],
                            "now": datetime.now(timezone.utc)
                        }
                    )
                    print(f"  ~ {role['name']} ({role['code']}): Updated")
                    updated_count += 1
                else:
                    print(f"  - {role['name']} ({role['code']}): Already exists")
                    skipped_count += 1
            else:
                # Insert new role
                session.execute(
                    text("""
                        INSERT INTO roles (name, code, description, is_active, created_at, updated_at)
                        VALUES (:name, :code, :description, true, :now, :now)
                    """),
                    {
                        "name": role["name"],
                        "code": role["code"],
                        "description": role["description"],
                        "now": datetime.now(timezone.utc)
                    }
                )
                print(f"  + {role['name']} ({role['code']}): Added")
                added_count += 1

        session.commit()
        print(f"\nDone! Added {added_count}, updated {updated_count}, skipped {skipped_count} roles.")

        # Show all roles
        print("\nAll workflow roles in database:")
        roles = session.execute(
            text("SELECT id, name, code, is_active FROM roles ORDER BY name")
        ).fetchall()
        for r in roles:
            status = "active" if r[3] else "inactive"
            code = f"({r[2]})" if r[2] else ""
            print(f"  {r[0]:3d}. {r[1]} {code} - {status}")

        return True

    except Exception as e:
        session.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
