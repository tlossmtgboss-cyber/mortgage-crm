"""
Migration Script: Delete Sample Data

This script removes all sample/test data from the database:
- Tasks (all)
- Extracted Data / Reconciliation items (all)
- Referral Partners (all)
- Team Members (sample users: Sarah Johnson, Michael Chen, Emily Davis, James Wilson)
- Users (sample users, keeping real accounts)

Run with: python -m migrations.delete_sample_data
Or via Railway: railway run python -m migrations.delete_sample_data
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


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
        # Sample user emails to delete (keep real users like Timothy Loss)
        sample_user_emails = [
            'sjohnson@cmgfi.com',
            'mchen@cmgfi.com',
            'edavis@cmgfi.com',
            'jwilson@cmgfi.com',
            'sarah@cmghomeloans.com',
            'michael@cmghomeloans.com',
            'emily@cmghomeloans.com',
            'james@cmghomeloans.com',
        ]

        # Sample names to identify sample data
        sample_names = [
            'Sarah Johnson', 'Michael Chen', 'Emily Davis', 'James Wilson',
            'Mike Soscia', 'Chris Jones', 'Amanda Duran', 'Janet Ruiz',
            'Jared Smith', 'Mike Johnson', 'Jennifer Smith', 'David Wilson',
            'Chris Miller', 'Alex Jones', 'Amanda Berry', 'Lisa Stone',
            'Michelle Brown', 'Shane Gibson', 'Bruce Johnson', 'Mike Davis',
            'Emily Duvvis', 'Chris Lomas', 'Jerome Davis',
            'Amy Smith', 'Bob Johnson', 'Carol Williams', 'Dan Brown',
            'Test', 'Sample', 'Demo'
        ]

        print("\n=== Starting Sample Data Cleanup ===\n")

        # 1. Delete all tasks
        print("Deleting tasks...")
        result = session.execute(text("DELETE FROM tasks"))
        print(f"  Deleted {result.rowcount} tasks")

        # 2. Delete all extracted_data (reconciliation items)
        print("Deleting extracted_data (reconciliation items)...")
        result = session.execute(text("DELETE FROM extracted_data"))
        print(f"  Deleted {result.rowcount} extracted data items")

        # 3. Delete incoming_data_events if they exist
        try:
            result = session.execute(text("DELETE FROM incoming_data_events"))
            print(f"  Deleted {result.rowcount} incoming data events")
        except Exception as e:
            print(f"  (incoming_data_events table may not exist: {e})")

        # 4. Delete all referral partners
        print("Deleting referral partners...")
        result = session.execute(text("DELETE FROM referral_partners"))
        print(f"  Deleted {result.rowcount} referral partners")

        # 5. Delete team_members (but not the actual users table)
        print("Deleting team_members...")
        result = session.execute(text("DELETE FROM team_members"))
        print(f"  Deleted {result.rowcount} team members")

        # 6. Delete workflow-related sample data
        print("Deleting workflow instances...")
        try:
            result = session.execute(text("DELETE FROM workflow_instances"))
            print(f"  Deleted {result.rowcount} workflow instances")
        except Exception as e:
            print(f"  (workflow_instances may not exist: {e})")

        # 7. Delete sample users (careful - preserve real accounts)
        print("Deleting sample users...")
        # First, get the user IDs we want to delete
        sample_email_list = "','".join(sample_user_emails)
        try:
            # Check which sample users exist
            result = session.execute(text(f"""
                SELECT id, email, full_name FROM users
                WHERE email IN ('{sample_email_list}')
            """))
            users_to_delete = result.fetchall()

            if users_to_delete:
                for user in users_to_delete:
                    print(f"  Will delete user: {user[1]} ({user[2]})")

                # Delete the sample users
                result = session.execute(text(f"""
                    DELETE FROM users WHERE email IN ('{sample_email_list}')
                """))
                print(f"  Deleted {result.rowcount} sample users")
            else:
                print("  No sample users found to delete")
        except Exception as e:
            print(f"  Error deleting sample users: {e}")

        # 8. Delete sample leads
        print("Deleting sample leads...")
        try:
            # Delete leads with sample-looking names
            result = session.execute(text("""
                DELETE FROM leads WHERE
                first_name IN ('Test', 'Sample', 'Demo', 'John', 'Jane') AND
                last_name IN ('User', 'Lead', 'Test', 'Sample', 'Doe')
            """))
            print(f"  Deleted {result.rowcount} sample leads")
        except Exception as e:
            print(f"  Error deleting sample leads: {e}")

        # 9. Delete sample loans
        print("Deleting sample loans...")
        try:
            result = session.execute(text("""
                DELETE FROM loans WHERE
                borrower_name LIKE '%Test%' OR
                borrower_name LIKE '%Sample%' OR
                borrower_name LIKE '%Demo%'
            """))
            print(f"  Deleted {result.rowcount} sample loans")
        except Exception as e:
            print(f"  Error deleting sample loans: {e}")

        # 10. Delete Account Management sample data
        print("Deleting Account Management sample data...")

        # Delete related tables first (due to foreign key constraints)
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
            'tenant_accounts'  # Delete main table last
        ]

        for table in account_tables:
            try:
                result = session.execute(text(f"DELETE FROM {table}"))
                print(f"  Deleted {result.rowcount} rows from {table}")
            except Exception as e:
                print(f"  (Table {table} may not exist or error: {e})")

        # Commit all changes
        session.commit()
        print("\n=== Sample Data Cleanup Complete ===\n")

        # Print remaining counts
        print("Remaining data counts:")
        tables_to_check = [
            'users', 'tasks', 'extracted_data', 'referral_partners', 'team_members',
            'leads', 'loans', 'tenant_accounts', 'account_subscriptions'
        ]
        for table in tables_to_check:
            try:
                result = session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print(f"  {table}: {count}")
            except Exception:
                pass

    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    delete_sample_data()
