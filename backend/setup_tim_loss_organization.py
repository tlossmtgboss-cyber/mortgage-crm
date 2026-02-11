#!/usr/bin/env python3
"""
Setup Tim Loss Organization
===========================
Creates the CMG Financial organization and assigns Tim Loss to it.

Run this script after deploying to set up the first tenant.

Usage:
    python setup_tim_loss_organization.py

Or via the API:
    POST /api/v1/public/migrations/setup-tim-loss-organization
"""

import os
import sys
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def get_database_url():
    """Get database URL from environment."""
    url = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
    # Fix Railway postgres URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def setup_tim_loss_organization():
    """
    Create CMG Financial organization and assign Tim Loss.

    Returns:
        dict: Result with organization and user info
    """
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        print("=" * 60)
        print("SETTING UP TIM LOSS ORGANIZATION")
        print("=" * 60)

        # Step 1: Check if organization already exists
        print("\n1. Checking for existing organization...")

        result = db.execute(text("""
            SELECT id, name, slug, domain, is_active
            FROM organizations
            WHERE slug = 'cmg-financial' OR domain = 'cmgfi.com'
            LIMIT 1
        """))
        existing_org = result.fetchone()

        if existing_org:
            org_id = existing_org[0]
            print(f"   Organization already exists:")
            print(f"   - ID: {org_id}")
            print(f"   - Name: {existing_org[1]}")
            print(f"   - Slug: {existing_org[2]}")
        else:
            # Create the organization
            print("\n2. Creating CMG Financial organization...")

            db.execute(text("""
                INSERT INTO organizations (name, slug, domain, subscription_tier, is_active, settings, created_at, updated_at)
                VALUES (
                    'CMG Financial - Tim Loss Team',
                    'cmg-financial',
                    'cmgfi.com',
                    'professional',
                    true,
                    :settings,
                    :now,
                    :now
                )
            """), {
                "settings": '{"branding": {"primary_color": "#1976D2", "company_name": "Tim Loss Team"}, "features": {"ai_assistant": true, "voicemail_drops": true, "sms_campaigns": true}}',
                "now": datetime.now(timezone.utc)
            })
            db.commit()

            # Get the newly created org ID
            result = db.execute(text("SELECT id FROM organizations WHERE slug = 'cmg-financial'"))
            org_id = result.fetchone()[0]

            print(f"   Organization created with ID: {org_id}")

        # Step 3: Find Tim Loss user
        print("\n3. Finding Tim Loss user...")

        result = db.execute(text("""
            SELECT id, email, first_name, last_name, organization_id, permission_role
            FROM users
            WHERE email = 'tloss@cmgfi.com' OR id = 57
            LIMIT 1
        """))
        user = result.fetchone()

        if not user:
            print("   ERROR: Tim Loss user not found!")
            print("   Looking for any admin user...")

            result = db.execute(text("""
                SELECT id, email, first_name, last_name, organization_id, permission_role
                FROM users
                WHERE permission_role IN ('admin', 'site_admin')
                ORDER BY id
                LIMIT 1
            """))
            user = result.fetchone()

            if not user:
                print("   ERROR: No admin user found!")
                return {"error": "No admin user found to assign"}

        user_id = user[0]
        user_email = user[1]
        user_name = f"{user[2] or ''} {user[3] or ''}".strip() or user_email
        current_org_id = user[4]
        permission_role = user[5]

        print(f"   Found user:")
        print(f"   - ID: {user_id}")
        print(f"   - Email: {user_email}")
        print(f"   - Name: {user_name}")
        print(f"   - Current org ID: {current_org_id}")
        print(f"   - Permission role: {permission_role}")

        # Step 4: Assign user to organization
        if current_org_id == org_id:
            print(f"\n4. User already assigned to organization {org_id}")
        else:
            print(f"\n4. Assigning user to organization {org_id}...")

            db.execute(text("""
                UPDATE users
                SET organization_id = :org_id,
                    permission_role = CASE
                        WHEN permission_role IS NULL THEN 'site_admin'
                        WHEN permission_role = 'sales' THEN 'site_admin'
                        ELSE permission_role
                    END
                WHERE id = :user_id
            """), {"org_id": org_id, "user_id": user_id})

            db.commit()
            print(f"   User assigned to organization {org_id}")

        # Step 5: Backfill user's data
        print("\n5. Backfilling user's data to organization...")

        tables_to_update = [
            ("leads", "owner_id"),
            ("loans", "loan_officer_id"),
            ("tasks", "owner_id"),
            ("activities", "user_id"),
            ("referral_partners", "owner_id"),
        ]

        for table, user_col in tables_to_update:
            try:
                result = db.execute(text(f"""
                    UPDATE {table}
                    SET organization_id = :org_id
                    WHERE {user_col} = :user_id
                        AND (organization_id IS NULL OR organization_id != :org_id)
                """), {"org_id": org_id, "user_id": user_id})

                if result.rowcount > 0:
                    print(f"   Updated {result.rowcount} rows in {table}")
                db.commit()
            except Exception as e:
                print(f"   Warning: Could not update {table}: {e}")
                db.rollback()

        # Step 6: Create default branch if none exists
        print("\n6. Checking for default branch...")

        result = db.execute(text("""
            SELECT id, name FROM branches
            WHERE organization_id = :org_id
            LIMIT 1
        """), {"org_id": org_id})
        branch = result.fetchone()

        if not branch:
            print("   Creating default branch...")
            db.execute(text("""
                INSERT INTO branches (name, organization_id, created_at)
                VALUES ('Main Office', :org_id, :now)
            """), {"org_id": org_id, "now": datetime.now(timezone.utc)})
            db.commit()

            result = db.execute(text("SELECT id FROM branches WHERE organization_id = :org_id"), {"org_id": org_id})
            branch_id = result.fetchone()[0]

            # Assign user to branch
            db.execute(text("UPDATE users SET branch_id = :branch_id WHERE id = :user_id"),
                      {"branch_id": branch_id, "user_id": user_id})
            db.commit()
            print(f"   Branch created with ID: {branch_id}")
        else:
            print(f"   Branch already exists: {branch[1]} (ID: {branch[0]})")

        # Step 7: Summary
        print("\n" + "=" * 60)
        print("SETUP COMPLETE")
        print("=" * 60)

        # Get final counts
        result = db.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM users WHERE organization_id = :org_id) as users,
                (SELECT COUNT(*) FROM leads WHERE organization_id = :org_id) as leads,
                (SELECT COUNT(*) FROM loans WHERE organization_id = :org_id) as loans,
                (SELECT COUNT(*) FROM branches WHERE organization_id = :org_id) as branches
        """), {"org_id": org_id})
        counts = result.fetchone()

        print(f"\nOrganization: CMG Financial - Tim Loss Team")
        print(f"Organization ID: {org_id}")
        print(f"Slug: cmg-financial")
        print(f"Domain: cmgfi.com")
        print(f"\nAssigned User: {user_name} ({user_email})")
        print(f"User ID: {user_id}")
        print(f"\nData Counts:")
        print(f"  - Users: {counts[0]}")
        print(f"  - Leads: {counts[1]}")
        print(f"  - Loans: {counts[2]}")
        print(f"  - Branches: {counts[3]}")

        return {
            "success": True,
            "organization": {
                "id": org_id,
                "name": "CMG Financial - Tim Loss Team",
                "slug": "cmg-financial",
                "domain": "cmgfi.com"
            },
            "user": {
                "id": user_id,
                "email": user_email,
                "name": user_name
            },
            "counts": {
                "users": counts[0],
                "leads": counts[1],
                "loans": counts[2],
                "branches": counts[3]
            }
        }

    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return {"error": "Internal server error"}

    finally:
        db.close()


if __name__ == "__main__":
    result = setup_tim_loss_organization()

    if result.get("error"):
        print(f"\nSetup failed: {result['error']}")
        sys.exit(1)
    else:
        print("\nSetup completed successfully!")
        sys.exit(0)
