"""
Migration Script: Delete Sample Data

This script removes all sample/test data from the database:
- Tasks (all)
- Extracted Data / Reconciliation items (all)
- Referral Partners (all)
- Team Members (all except Admin User)
- Users (all except admin@perenniaai.com)
- Suspended accounts
- Cancelled accounts

Run with: python -m migrations.delete_sample_data
Or via Railway: railway run python -m migrations.delete_sample_data
"""

import logging
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment."""
    database_url = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def delete_sample_data():
    """Delete all sample data from the database."""
    database_url = get_database_url()
    print(f"Connecting to database...")

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Admin email to KEEP - only this user will remain
        admin_email_to_keep = 'admin@perenniaai.com'

        print("\n=== Starting Complete Sample Data Cleanup ===\n")

        # 1. Delete all tasks
        print("1. Deleting ALL tasks...")
        try:
            result = session.execute(text("DELETE FROM tasks"))
            print(f"   Deleted {result.rowcount} tasks")
        except Exception as e:
            print(f"   Error deleting tasks: {e}")

        # 2. Delete all extracted_data (reconciliation items)
        print("2. Deleting extracted_data (reconciliation items)...")
        try:
            result = session.execute(text("DELETE FROM extracted_data"))
            print(f"   Deleted {result.rowcount} extracted data items")
        except Exception as e:
            print(f"   Error: {e}")

        # 3. Delete incoming_data_events if they exist
        print("3. Deleting incoming_data_events...")
        try:
            result = session.execute(text("DELETE FROM incoming_data_events"))
            print(f"   Deleted {result.rowcount} incoming data events")
        except Exception as e:
            print(f"   (Table may not exist: {e})")

        # 4. Delete all referral partners
        print("4. Deleting referral partners...")
        try:
            result = session.execute(text("DELETE FROM referral_partners"))
            print(f"   Deleted {result.rowcount} referral partners")
        except Exception as e:
            print(f"   Error: {e}")

        # 5. Delete ALL team_members
        print("5. Deleting ALL team_members...")
        try:
            result = session.execute(text("DELETE FROM team_members"))
            print(f"   Deleted {result.rowcount} team members")
        except Exception as e:
            print(f"   Error: {e}")

        # 6. Delete workflow-related sample data
        print("6. Deleting workflow instances...")
        try:
            result = session.execute(text("DELETE FROM workflow_instances"))
            print(f"   Deleted {result.rowcount} workflow instances")
        except Exception as e:
            print(f"   (Table may not exist: {e})")

        # 7. Delete ALL users EXCEPT admin@perenniaai.com
        print(f"7. Deleting ALL users except {admin_email_to_keep}...")
        try:
            # First show what will be deleted
            result = session.execute(text("""
                SELECT id, email, full_name, role FROM users
                WHERE email != :admin_email
            """), {"admin_email": admin_email_to_keep})
            users_to_delete = result.fetchall()

            if users_to_delete:
                print(f"   Users to be deleted:")
                for user in users_to_delete:
                    user_id, email, name, role = user
                    print(f"     - {email} ({name or 'No name'}) [Role: {role or 'N/A'}]")

                # Delete all users except admin
                result = session.execute(text("""
                    DELETE FROM users WHERE email != :admin_email
                """), {"admin_email": admin_email_to_keep})
                print(f"   Deleted {result.rowcount} users")
            else:
                print("   No users to delete (only admin exists)")
        except Exception as e:
            print(f"   Error deleting users: {e}")

        # 8. Delete sample leads
        print("8. Deleting sample leads...")
        try:
            result = session.execute(text("""
                DELETE FROM leads WHERE
                first_name IN ('Test', 'Sample', 'Demo', 'John', 'Jane') AND
                last_name IN ('User', 'Lead', 'Test', 'Sample', 'Doe')
            """))
            print(f"   Deleted {result.rowcount} sample leads")
        except Exception as e:
            print(f"   Error: {e}")

        # 9. Delete sample loans
        print("9. Deleting sample loans...")
        try:
            result = session.execute(text("""
                DELETE FROM loans WHERE
                borrower_name LIKE '%Test%' OR
                borrower_name LIKE '%Sample%' OR
                borrower_name LIKE '%Demo%'
            """))
            print(f"   Deleted {result.rowcount} sample loans")
        except Exception as e:
            print(f"   Error: {e}")

        # 10. Delete suspended and cancelled accounts from tenant_accounts
        print("10. Deleting suspended and cancelled accounts...")
        try:
            # First show what will be deleted
            result = session.execute(text("""
                SELECT id, name, status, suspended_at, canceled_at
                FROM tenant_accounts
                WHERE status IN ('suspended', 'canceled')
            """))
            accounts_to_delete = result.fetchall()

            if accounts_to_delete:
                print(f"    Accounts to be deleted:")
                for acct in accounts_to_delete:
                    acct_id, name, status, suspended_at, canceled_at = acct
                    print(f"      - {name} (Status: {status})")

                result = session.execute(text("""
                    DELETE FROM tenant_accounts
                    WHERE status IN ('suspended', 'canceled')
                """))
                print(f"    Deleted {result.rowcount} suspended/cancelled accounts")
            else:
                print("    No suspended/cancelled accounts found")
        except Exception as e:
            print(f"    Error: {e}")

        # 11. Delete ALL Account Management sample data (optional - related tables)
        print("11. Cleaning up Account Management related tables...")

        # Delete related tables first (due to foreign key constraints)
        _ACCOUNT_SAFE_TABLES = frozenset({
            'subscription_events',
            'account_subscriptions',
            'account_invoices',
            'cost_ledger_monthly',
            'usage_events',
            'login_events',
            'admin_audit_log',
            'impersonation_sessions',
            'user_activity_stats',
            'account_kpi_snapshots',
            'account_user_roles',
        })
        account_tables = [
            'subscription_events',
            'account_subscriptions',
            'account_invoices',
            'cost_ledger_monthly',
            'usage_events',
            'login_events',
            'admin_audit_log',
            'impersonation_sessions',
            'user_activity_stats',
            'account_kpi_snapshots',
            'account_user_roles',
        ]

        for table in account_tables:
            if table not in _ACCOUNT_SAFE_TABLES:
                raise ValueError(f"Blocked SQL on non-whitelisted table: {table}")
            try:
                result = session.execute(text(f"DELETE FROM {table}"))
                if result.rowcount > 0:
                    print(f"    Deleted {result.rowcount} rows from {table}")
            except Exception as e:
                pass  # Table may not exist, silently continue

        # 12. Delete task_instances (portal tasks)
        print("12. Deleting task_instances (portal tasks)...")
        try:
            result = session.execute(text("DELETE FROM task_instances"))
            print(f"    Deleted {result.rowcount} task instances")
        except Exception as e:
            print(f"    (Table may not exist: {e})")

        # 13. Delete purl_tasks (PURL portal tasks)
        print("13. Deleting purl_tasks...")
        try:
            result = session.execute(text("DELETE FROM purl_tasks"))
            print(f"    Deleted {result.rowcount} PURL tasks")
        except Exception as e:
            print(f"    (Table may not exist: {e})")

        # 14. Delete team_member_profiles
        print("14. Deleting team_member_profiles...")
        try:
            result = session.execute(text("DELETE FROM team_member_profiles"))
            print(f"    Deleted {result.rowcount} team member profiles")
        except Exception as e:
            print(f"    (Table may not exist: {e})")

        # 15. Delete onboarding user profiles (except admin)
        print("15. Cleaning up onboarding user profiles...")
        try:
            # Get admin user ID first
            admin_result = session.execute(text("""
                SELECT id FROM users WHERE email = :admin_email
            """), {"admin_email": admin_email_to_keep})
            admin_row = admin_result.fetchone()

            if admin_row:
                admin_id = admin_row[0]
                result = session.execute(text("""
                    DELETE FROM onboarding_user_profiles
                    WHERE user_id != :admin_id
                """), {"admin_id": admin_id})
                print(f"    Deleted {result.rowcount} onboarding profiles")
            else:
                result = session.execute(text("DELETE FROM onboarding_user_profiles"))
                print(f"    Deleted {result.rowcount} onboarding profiles")
        except Exception as e:
            print(f"    (Table may not exist: {e})")

        # Commit all changes
        session.commit()
        print("\n=== Sample Data Cleanup Complete ===\n")

        # Print remaining counts
        print("Remaining data counts:")
        tables_to_check = [
            'users', 'tasks', 'task_instances', 'purl_tasks',
            'extracted_data', 'referral_partners', 'team_members',
            'team_member_profiles', 'leads', 'loans',
            'tenant_accounts', 'account_subscriptions',
            'onboarding_user_profiles'
        ]
        for table in tables_to_check:
            try:
                result = session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print(f"  {table}: {count}")
            except Exception as e:
                logger.error(f"Error counting rows in {table}: {e}")

        # Show remaining admin user
        print("\nRemaining users:")
        try:
            result = session.execute(text("""
                SELECT id, email, full_name, role FROM users
            """))
            remaining_users = result.fetchall()
            for user in remaining_users:
                user_id, email, name, role = user
                print(f"  - ID: {user_id}, Email: {email}, Name: {name}, Role: {role}")
        except Exception as e:
            print(f"  Error: {e}")

    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    delete_sample_data()
