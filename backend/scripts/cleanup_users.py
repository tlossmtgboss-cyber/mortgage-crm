"""
User Cleanup Script
Deletes all users except those with @cmgfi.com email addresses

Usage:
    python scripts/cleanup_users.py

This script will:
1. Connect to the database
2. Find all users without @cmgfi.com email
3. Display the users to be deleted
4. Ask for confirmation
5. Delete the users

Author: System
Date: 2025-11-15
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def get_database_url():
    """Get database URL from environment"""
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return db_url

def cleanup_users(dry_run=False):
    """
    Delete all users except @cmgfi.com emails

    Args:
        dry_run: If True, only show what would be deleted without actually deleting
    """

    # Get database URL
    database_url = get_database_url()

    # Create engine and session
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    print("🔍 Finding users to remove...")
    print("-" * 60)

    try:
        # Find all users that don't have @cmgfi.com email
        result = session.execute(text("""
            SELECT id, email, first_name, last_name, created_at
            FROM users
            WHERE email NOT LIKE '%@cmgfi.com'
            ORDER BY created_at DESC
        """))

        users_to_delete = result.fetchall()

        if not users_to_delete:
            print("✅ No users to delete. All existing users have @cmgfi.com emails.")
            return

        print(f"\n📋 Found {len(users_to_delete)} users to delete:\n")

        for user in users_to_delete:
            user_id, email, first_name, last_name, created_at = user
            name = f"{first_name or ''} {last_name or ''}".strip() or "No name"
            print(f"   • ID: {user_id:4d} | {email:40s} | {name:30s} | Created: {created_at}")

        print("\n" + "-" * 60)

        # Get @cmgfi.com users count for reference
        cmgfi_result = session.execute(text("""
            SELECT COUNT(*) as count FROM users WHERE email LIKE '%@cmgfi.com'
        """))
        cmgfi_count = cmgfi_result.fetchone()[0]

        print(f"\n✅ Users to KEEP (@cmgfi.com): {cmgfi_count}")
        print(f"❌ Users to DELETE (non-@cmgfi.com): {len(users_to_delete)}")

        if dry_run:
            print("\n🔍 DRY RUN MODE - No users will be deleted")
            print("   Run without --dry-run to actually delete these users")
            return

        # Ask for confirmation
        print("\n⚠️  WARNING: This action cannot be undone!")
        confirmation = input("\nType 'DELETE' to confirm deletion: ")

        if confirmation != 'DELETE':
            print("\n❌ Deletion cancelled. No users were deleted.")
            return

        # Delete users
        print("\n🗑️  Deleting users...")

        deleted_count = 0
        for user in users_to_delete:
            user_id, email = user[0], user[1]

            try:
                # Delete user (cascade will handle related records)
                session.execute(text("""
                    DELETE FROM users WHERE id = :user_id
                """), {'user_id': user_id})

                deleted_count += 1
                print(f"   ✓ Deleted: {email} (ID: {user_id})")

            except Exception as e:
                print(f"   ✗ Failed to delete {email}: {e}")

        # Commit the transaction
        session.commit()

        print(f"\n✅ Successfully deleted {deleted_count} users")
        print(f"✅ Remaining @cmgfi.com users: {cmgfi_count}")

        # Show remaining users
        print("\n📋 Remaining users:")
        remaining_result = session.execute(text("""
            SELECT id, email, first_name, last_name
            FROM users
            WHERE email LIKE '%@cmgfi.com'
            ORDER BY email
        """))

        remaining_users = remaining_result.fetchall()
        for user in remaining_users:
            user_id, email, first_name, last_name = user
            name = f"{first_name or ''} {last_name or ''}".strip() or "No name"
            print(f"   ✓ ID: {user_id:4d} | {email:40s} | {name}")

        print("\n✅ Cleanup completed successfully!")

    except Exception as e:
        session.rollback()
        print(f"\n❌ Error during cleanup: {e}")
        raise
    finally:
        session.close()

if __name__ == '__main__':
    """
    Run the cleanup script

    Usage:
        python scripts/cleanup_users.py            # Interactive deletion
        python scripts/cleanup_users.py --dry-run  # Show what would be deleted
    """

    # Check for dry-run flag
    dry_run = '--dry-run' in sys.argv

    print("=" * 60)
    print("🧹 User Cleanup Script")
    print("=" * 60)
    print("\nThis script will DELETE all users except @cmgfi.com emails")

    if dry_run:
        print("\n🔍 DRY RUN MODE - No actual deletions will occur\n")

    try:
        cleanup_users(dry_run=dry_run)
    except KeyboardInterrupt:
        print("\n\n❌ Script cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Script failed: {e}")
        sys.exit(1)
