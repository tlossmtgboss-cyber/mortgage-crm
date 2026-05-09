#!/usr/bin/env python3
"""
Fix script to ensure demo user data is properly scoped to the demo organization.

SAFE VERSION: Only touches records that already belong to the demo user or have
NULL ownership. Never reassigns data owned by other users/orgs.

Run: railway run python fix_demo_user_ownership.py
"""

import os
import sys
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is required")
    sys.exit(1)


DEMO_ORG_SLUG = "demo-mortgage"
DEMO_USER_EMAIL = "admin@perenniaai.com"


def main():
    print("Fixing demo user data ownership (safe mode)...")

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Find the demo organization by slug — never fall back to LIMIT 1
        org_row = conn.execute(text(
            "SELECT id, name FROM organizations WHERE slug = :slug"
        ), {"slug": DEMO_ORG_SLUG}).fetchone()

        if not org_row:
            print(f"Demo org '{DEMO_ORG_SLUG}' not found. Nothing to fix.")
            return
        demo_org_id = org_row[0]
        print(f"Demo org: {org_row[1]} (ID: {demo_org_id})")

        # Find demo user
        demo_user = conn.execute(text(
            "SELECT id, email, organization_id FROM users WHERE email = :e"
        ), {"e": DEMO_USER_EMAIL}).fetchone()

        if not demo_user:
            print(f"Demo user '{DEMO_USER_EMAIL}' not found. Nothing to fix.")
            return

        demo_user_id = demo_user[0]
        current_org = demo_user[2]
        print(f"Demo user: {demo_user[1]} (ID: {demo_user_id}, org: {current_org})")

        # Ensure demo user is in the demo org
        if current_org != demo_org_id:
            conn.execute(text(
                "UPDATE users SET organization_id = :oid WHERE id = :uid"
            ), {"oid": demo_org_id, "uid": demo_user_id})
            print(f"Moved demo user to demo org (was: {current_org})")

        # Only fix records that belong to the demo user but have wrong/null org_id.
        # NEVER touch records owned by other users.
        result = conn.execute(text("""
            UPDATE leads SET organization_id = :oid
            WHERE owner_id = :uid AND (organization_id IS NULL OR organization_id != :oid)
        """), {"uid": demo_user_id, "oid": demo_org_id})
        print(f"Fixed {result.rowcount} leads (demo user, wrong org)")

        result = conn.execute(text("""
            UPDATE loans SET organization_id = :oid
            WHERE loan_officer_id = :uid AND (organization_id IS NULL OR organization_id != :oid)
        """), {"uid": demo_user_id, "oid": demo_org_id})
        print(f"Fixed {result.rowcount} loans (demo user, wrong org)")

        result = conn.execute(text("""
            UPDATE tasks SET organization_id = :oid
            WHERE owner_id = :uid AND (organization_id IS NULL OR organization_id != :oid)
        """), {"uid": demo_user_id, "oid": demo_org_id})
        print(f"Fixed {result.rowcount} tasks (demo user, wrong org)")

        result = conn.execute(text("""
            UPDATE mum_clients SET organization_id = :oid
            WHERE user_id = :uid AND (organization_id IS NULL OR organization_id != :oid)
        """), {"uid": demo_user_id, "oid": demo_org_id})
        print(f"Fixed {result.rowcount} MUM clients (demo user, wrong org)")

        conn.commit()

        # Verify
        counts = conn.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM leads WHERE owner_id = :uid AND organization_id = :oid) as leads,
                (SELECT COUNT(*) FROM loans WHERE loan_officer_id = :uid AND organization_id = :oid) as loans,
                (SELECT COUNT(*) FROM tasks WHERE owner_id = :uid AND organization_id = :oid) as tasks,
                (SELECT COUNT(*) FROM mum_clients WHERE user_id = :uid AND organization_id = :oid) as mum
        """), {"uid": demo_user_id, "oid": demo_org_id}).fetchone()

        print(f"\nDemo user now owns (in demo org):")
        print(f"  {counts[0]} leads, {counts[1]} loans, {counts[2]} tasks, {counts[3]} MUM clients")


if __name__ == "__main__":
    main()
