"""
Migration: Fix Company Admin Role
Ensures the Company Admin role exists in onboarding_roles and is properly configured.
This role is assigned to users who sign up via subscription invitation (tenant admins).

Run with: railway run python migrations/fix_company_admin_role.py
"""

import os
import sys
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Add or fix Company Admin role in the database."""
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable not set")
        return False

    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        print("=" * 60)
        print("Fix Company Admin Role Migration")
        print("=" * 60)

        # 1. Check if Company Admin role exists
        print("\n1. Checking for Company Admin role...")
        existing = session.execute(
            text("SELECT id, name, description, is_active FROM onboarding_roles WHERE name = :name"),
            {"name": "Company Admin"}
        ).fetchone()

        if existing:
            print(f"   Found existing role: ID={existing[0]}, active={existing[3]}")

            # Ensure it's active
            if not existing[3]:
                print("   Activating Company Admin role...")
                session.execute(
                    text("UPDATE onboarding_roles SET is_active = true, updated_at = :now WHERE id = :id"),
                    {"id": existing[0], "now": datetime.now(timezone.utc)}
                )
                print("   Role activated")

            company_admin_id = existing[0]
        else:
            print("   Company Admin role not found, creating...")
            result = session.execute(
                text("""
                    INSERT INTO onboarding_roles (name, description, is_active, created_at, updated_at)
                    VALUES (:name, :description, true, :now, :now)
                    RETURNING id
                """),
                {
                    "name": "Company Admin",
                    "description": "Company/Organization administrator with full tenant-level access. Assigned to users who sign up via subscription invitation.",
                    "now": datetime.now(timezone.utc)
                }
            )
            company_admin_id = result.fetchone()[0]
            print(f"   Created Company Admin role with ID: {company_admin_id}")

        # 2. Also ensure Site Administrator exists (for master admins)
        print("\n2. Checking for Site Administrator role...")
        site_admin = session.execute(
            text("SELECT id, is_active FROM onboarding_roles WHERE name = :name"),
            {"name": "Site Administrator"}
        ).fetchone()

        if site_admin:
            print(f"   Found Site Administrator role: ID={site_admin[0]}")
            if not site_admin[1]:
                session.execute(
                    text("UPDATE onboarding_roles SET is_active = true, updated_at = :now WHERE id = :id"),
                    {"id": site_admin[0], "now": datetime.now(timezone.utc)}
                )
                print("   Site Administrator role activated")
        else:
            print("   Site Administrator role not found, creating...")
            session.execute(
                text("""
                    INSERT INTO onboarding_roles (name, description, is_active, created_at, updated_at)
                    VALUES (:name, :description, true, :now, :now)
                """),
                {
                    "name": "Site Administrator",
                    "description": "Master site administrator with system-wide access across all tenants.",
                    "now": datetime.now(timezone.utc)
                }
            )
            print("   Created Site Administrator role")

        # 3. Commit changes
        session.commit()
        print("\n3. Changes committed successfully")

        # 4. Show all admin-related roles
        print("\n4. Current admin-related roles:")
        print("-" * 50)
        roles = session.execute(
            text("""
                SELECT id, name, description, is_active
                FROM onboarding_roles
                WHERE name ILIKE '%admin%' OR name ILIKE '%site%'
                ORDER BY name
            """)
        ).fetchall()

        for r in roles:
            status = "ACTIVE" if r[3] else "inactive"
            print(f"   [{status:8}] ID={r[0]:3d} | {r[1]}")
            if r[2]:
                print(f"              {r[2][:60]}...")

        print("\n" + "=" * 60)
        print("Migration completed successfully!")
        print("=" * 60)
        return True

    except Exception as e:
        session.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


def check_status():
    """Check current status of Company Admin role."""
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        return

    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id, name, is_active FROM onboarding_roles WHERE name IN ('Company Admin', 'Site Administrator') ORDER BY name")
        ).fetchall()

        print("Current admin roles:")
        for r in result:
            print(f"  {r[1]}: ID={r[0]}, active={r[2]}")

        if not result:
            print("  No admin roles found - migration needed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        check_status()
    else:
        success = run_migration()
        sys.exit(0 if success else 1)
