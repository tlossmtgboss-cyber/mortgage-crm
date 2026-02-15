#!/usr/bin/env python3
"""
Grant full admin access to a user.
Usage: python grant_admin_access.py [user_email_or_id]
"""

import os
import sys
from sqlalchemy import create_engine, text

# Use production database — requires PROD_DATABASE_URL or DATABASE_URL to be set
DATABASE_URL = os.getenv("PROD_DATABASE_URL") or os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: Set PROD_DATABASE_URL or DATABASE_URL environment variable")
    sys.exit(1)

def get_engine():
    return create_engine(DATABASE_URL)

def list_users():
    """List all users in the system."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, email, full_name, role, permission_role, is_active
            FROM users
            ORDER BY id
            LIMIT 20
        """))
        users = result.fetchall()

        print("\n=== Current Users ===")
        print(f"{'ID':<5} {'Email':<35} {'Name':<25} {'Role':<15} {'Perm Role':<15} {'Active':<8}")
        print("-" * 105)
        for user in users:
            print(f"{user[0]:<5} {user[1]:<35} {(user[2] or '')[:24]:<25} {(user[3] or ''):<15} {(user[4] or ''):<15} {str(user[5]):<8}")

        return users

def grant_admin_access(user_identifier):
    """Grant full admin access to a user."""
    engine = get_engine()

    with engine.connect() as conn:
        # Find the user
        if user_identifier.isdigit():
            result = conn.execute(text("SELECT id, email, full_name FROM users WHERE id = :id"), {"id": int(user_identifier)})
        else:
            result = conn.execute(text("SELECT id, email, full_name FROM users WHERE email = :email"), {"email": user_identifier})

        user = result.fetchone()
        if not user:
            print(f"Error: User '{user_identifier}' not found")
            return False

        user_id, email, full_name = user
        print(f"\n=== Granting Admin Access ===")
        print(f"User: {full_name} ({email}) - ID: {user_id}")

        # Update user role
        conn.execute(text("""
            UPDATE users
            SET role = 'admin',
                permission_role = 'admin',
                is_active = true
            WHERE id = :user_id
        """), {"user_id": user_id})

        print("✓ Updated user role to 'admin'")
        print("✓ Updated permission_role to 'admin'")

        # Grant all management permissions
        management_permissions = [
            # Dashboard & Analytics
            ("dashboard.view_all_widgets", True),
            ("analytics.view_all", True),
            ("analytics.export", True),

            # Leads
            ("leads.view_all", True),
            ("leads.create", True),
            ("leads.edit_all", True),
            ("leads.delete", True),
            ("leads.assign", True),
            ("leads.import", True),
            ("leads.export", True),

            # Clients & Loans
            ("clients.view_all", True),
            ("clients.create", True),
            ("clients.edit_all", True),
            ("clients.delete", True),
            ("loans.view_all", True),
            ("loans.create", True),
            ("loans.edit_all", True),
            ("loans.delete", True),
            ("loans.process", True),

            # Team Management
            ("team.view_all", True),
            ("team.edit_members", True),
            ("team.manage_permissions", True),
            ("team.impersonate", True),

            # Settings & Admin
            ("settings.view", True),
            ("settings.edit", True),
            ("permissions.view_all", True),
            ("permissions.manage", True),
            ("admin.manage", True),
            ("accounts.manage", True),
            ("accounts.view", True),
            ("system.admin", True),

            # Tasks
            ("tasks.view_all", True),
            ("tasks.create", True),
            ("tasks.edit_all", True),
            ("tasks.delete", True),

            # Marketing
            ("marketing.view_all", True),
            ("marketing.create", True),
            ("marketing.edit", True),

            # Reports
            ("reports.view_all", True),
            ("reports.create", True),
            ("reports.export", True),

            # Integrations
            ("integrations.view", True),
            ("integrations.manage", True),
        ]

        # Check if user_permissions table exists
        try:
            result = conn.execute(text("SELECT 1 FROM user_permissions LIMIT 1"))
            table_exists = True
        except Exception:
            table_exists = False

        if table_exists:
            # Delete existing permissions for user
            conn.execute(text("DELETE FROM user_permissions WHERE user_id = :user_id"), {"user_id": user_id})

            # Insert new permissions
            for perm_key, granted in management_permissions:
                conn.execute(text("""
                    INSERT INTO user_permissions (user_id, permission_key, granted, source, created_at)
                    VALUES (:user_id, :perm_key, :granted, 'admin_grant', NOW())
                    ON CONFLICT (user_id, permission_key) DO UPDATE SET granted = :granted
                """), {"user_id": user_id, "perm_key": perm_key, "granted": granted})

            print(f"✓ Granted {len(management_permissions)} permissions")
        else:
            print("⚠ user_permissions table not found, skipping individual permissions")

        conn.commit()

        print("\n✅ Full admin access granted successfully!")
        print(f"   User {email} now has admin role and all management permissions.")
        return True

def main():
    print("=" * 60)
    print("  Perennia AI - Admin Access Grant Tool")
    print("=" * 60)

    # List current users
    users = list_users()

    if len(sys.argv) > 1:
        user_identifier = sys.argv[1]
    else:
        print("\nEnter user ID or email to grant admin access:")
        user_identifier = input("> ").strip()

    if user_identifier:
        grant_admin_access(user_identifier)
    else:
        print("No user specified. Exiting.")

if __name__ == "__main__":
    main()
