#!/usr/bin/env python3
"""
Clear ALL data from a specific user's organization, EXCEPT team members (users).

Dynamically discovers all tables with organization_id and deletes org-scoped rows.
Also cleans up user-scoped tables (owner_id, user_id) for the same org's users.

Run: railway run python clear_org_data.py
"""

import os
import sys
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is required")
    sys.exit(1)

TARGET_USER_EMAIL = "tloss@cmgfi.com"

# Tables to NEVER delete from
PROTECTED_TABLES = {
    "users",
    "organizations",
    "branches",
    "onboarding_roles",
    "permission_templates",
    "permission_template_permissions",
    "feature_tier_configs",
    "alembic_version",
    "spatial_ref_sys",
}

# Tables where we delete by user_id/owner_id instead of (or in addition to) organization_id
USER_SCOPED_COLUMNS = ["owner_id", "user_id", "loan_officer_id", "assigned_to"]


def main():
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # 1. Find the target user and their org
        user_row = conn.execute(text(
            "SELECT id, email, organization_id, first_name, last_name FROM users WHERE email = :e"
        ), {"e": TARGET_USER_EMAIL}).fetchone()

        if not user_row:
            print(f"User '{TARGET_USER_EMAIL}' not found.")
            return

        user_id = user_row[0]
        org_id = user_row[2]
        print(f"Target user: {user_row[1]} (ID: {user_id}, org: {org_id})")

        if not org_id:
            print("ERROR: User has no organization_id. Cannot scope deletion.")
            return

        # Get org name
        org_row = conn.execute(text(
            "SELECT name, slug FROM organizations WHERE id = :oid"
        ), {"oid": org_id}).fetchone()
        print(f"Organization: {org_row[0]} (slug: {org_row[1]})" if org_row else f"Org ID: {org_id}")

        # Get all user IDs in this org (for user-scoped table cleanup)
        org_user_ids = [r[0] for r in conn.execute(text(
            "SELECT id FROM users WHERE organization_id = :oid"
        ), {"oid": org_id}).fetchall()]
        print(f"Users in org (PRESERVED): {len(org_user_ids)} team members")

        # 2. Find all tables with organization_id column
        org_tables = conn.execute(text("""
            SELECT table_name
            FROM information_schema.columns
            WHERE column_name = 'organization_id'
              AND table_schema = 'public'
            ORDER BY table_name
        """)).fetchall()
        org_table_names = [r[0] for r in org_tables if r[0] not in PROTECTED_TABLES]

        # 3. Find user-scoped tables (owner_id, user_id columns) for additional cleanup
        user_tables = {}
        for col in USER_SCOPED_COLUMNS:
            rows = conn.execute(text("""
                SELECT table_name
                FROM information_schema.columns
                WHERE column_name = :col
                  AND table_schema = 'public'
                ORDER BY table_name
            """), {"col": col}).fetchall()
            for r in rows:
                tname = r[0]
                if tname not in PROTECTED_TABLES and tname not in org_table_names:
                    user_tables.setdefault(tname, []).append(col)

        print(f"\nFound {len(org_table_names)} org-scoped tables")
        print(f"Found {len(user_tables)} additional user-scoped tables")

        # 4. Count data before deletion
        print("\n--- Current data counts ---")
        for tname in sorted(org_table_names):
            try:
                cnt = conn.execute(text(
                    f'SELECT COUNT(*) FROM "{tname}" WHERE organization_id = :oid'
                ), {"oid": org_id}).scalar()
                if cnt > 0:
                    print(f"  {tname}: {cnt} rows")
            except Exception:
                pass

        for tname, cols in sorted(user_tables.items()):
            for col in cols:
                try:
                    if org_user_ids:
                        placeholders = ",".join(str(uid) for uid in org_user_ids)
                        cnt = conn.execute(text(
                            f'SELECT COUNT(*) FROM "{tname}" WHERE {col} IN ({placeholders})'
                        )).scalar()
                        if cnt > 0:
                            print(f"  {tname} (by {col}): {cnt} rows")
                except Exception:
                    pass

        # 5. Delete org-scoped data with retry loop for FK ordering
        print("\n--- Deleting org-scoped data ---")
        remaining = list(org_table_names)
        max_passes = 5
        total_deleted = 0

        for pass_num in range(max_passes):
            if not remaining:
                break
            failed = []
            for tname in remaining:
                try:
                    result = conn.execute(text(
                        f'DELETE FROM "{tname}" WHERE organization_id = :oid'
                    ), {"oid": org_id})
                    if result.rowcount > 0:
                        print(f"  ✅ {tname}: {result.rowcount} rows deleted")
                        total_deleted += result.rowcount
                except Exception as e:
                    err_str = str(e)
                    if "violates foreign key" in err_str or "update or delete" in err_str:
                        failed.append(tname)
                        conn.rollback()
                    else:
                        print(f"  ⚠️  {tname}: {e}")
                        conn.rollback()

            if failed and pass_num < max_passes - 1:
                remaining = failed
                conn.commit()
            else:
                if failed:
                    print(f"\n  ⚠️  Could not delete from (FK constraints): {', '.join(failed)}")
                remaining = []
                conn.commit()

        # 6. Delete user-scoped data
        print("\n--- Deleting user-scoped data ---")
        if org_user_ids:
            placeholders = ",".join(str(uid) for uid in org_user_ids)
            for tname, cols in sorted(user_tables.items()):
                for col in cols:
                    try:
                        result = conn.execute(text(
                            f'DELETE FROM "{tname}" WHERE {col} IN ({placeholders})'
                        ))
                        if result.rowcount > 0:
                            print(f"  ✅ {tname} (by {col}): {result.rowcount} rows deleted")
                            total_deleted += result.rowcount
                    except Exception as e:
                        print(f"  ⚠️  {tname}: {e}")
                        conn.rollback()
            conn.commit()

        # 7. Verify
        print(f"\n--- Verification ---")
        print(f"Total rows deleted: {total_deleted}")

        remaining_data = 0
        for tname in sorted(org_table_names):
            try:
                cnt = conn.execute(text(
                    f'SELECT COUNT(*) FROM "{tname}" WHERE organization_id = :oid'
                ), {"oid": org_id}).scalar()
                if cnt > 0:
                    print(f"  ⚠️  {tname}: {cnt} rows remaining")
                    remaining_data += cnt
            except Exception:
                pass

        if remaining_data == 0:
            print("  ✅ All org data cleared successfully!")

        # Show preserved team members
        team = conn.execute(text(
            "SELECT email, first_name, last_name, role, permission_role FROM users WHERE organization_id = :oid"
        ), {"oid": org_id}).fetchall()
        print(f"\n--- Preserved team members ({len(team)}) ---")
        for t in team:
            print(f"  {t[0]} — {t[1]} {t[2]} ({t[3]}/{t[4]})")


if __name__ == "__main__":
    main()
