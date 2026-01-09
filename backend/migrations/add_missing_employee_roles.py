"""
Migration: Add Missing Employee Roles
Adds the missing employee roles to the onboarding_roles table.

Run with: python -m migrations.add_missing_employee_roles
"""

import os
import sys
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

# Roles to add (if they don't already exist)
MISSING_ROLES = [
    {"name": "Admin", "description": "System administrator with full access"},
    {"name": "Site Admin", "description": "Site-level administrator"},
    {"name": "Executive Management", "description": "Executive management team"},
    {"name": "Management", "description": "Management role"},
    {"name": "Operations Manager", "description": "Operations manager overseeing daily operations"},
    {"name": "Branch Manager", "description": "Branch manager overseeing branch operations"},
    {"name": "Underwriter", "description": "Loan underwriter"},
    {"name": "Closer", "description": "Loan closer handling closing process"},
    {"name": "Funder", "description": "Loan funder handling funding process"},
]


def run_migration():
    """Add missing employee roles to the database."""
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable not set")
        return False

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        print("Adding missing employee roles...")
        added_count = 0
        skipped_count = 0

        for role in MISSING_ROLES:
            # Check if role already exists
            existing = session.execute(
                text("SELECT id FROM onboarding_roles WHERE name = :name"),
                {"name": role["name"]}
            ).fetchone()

            if existing:
                print(f"  - {role['name']}: Already exists (skipped)")
                skipped_count += 1
            else:
                # Insert new role
                session.execute(
                    text("""
                        INSERT INTO onboarding_roles (name, description, is_active, created_at, updated_at)
                        VALUES (:name, :description, true, :now, :now)
                    """),
                    {
                        "name": role["name"],
                        "description": role["description"],
                        "now": datetime.now(timezone.utc)
                    }
                )
                print(f"  + {role['name']}: Added")
                added_count += 1

        session.commit()
        print(f"\nDone! Added {added_count} roles, skipped {skipped_count} existing roles.")

        # Show all roles
        print("\nAll employee roles in database:")
        roles = session.execute(
            text("SELECT id, name, is_active FROM onboarding_roles ORDER BY name")
        ).fetchall()
        for r in roles:
            status = "active" if r[2] else "inactive"
            print(f"  {r[0]:3d}. {r[1]} ({status})")

        return True

    except Exception as e:
        session.rollback()
        print(f"ERROR: {e}")
        return False
    finally:
        session.close()


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
