#!/usr/bin/env python3
"""
Run Email Identity Resolution Migration
Executes the SQL migration for email identity resolution tables and indexes.
"""

import os
import sys
import logging
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_migration():
    """Execute the email identity resolution migration."""
    from database import engine
    from sqlalchemy import text

    logger.info("=" * 60)
    logger.info("Email Identity Resolution Migration")
    logger.info("=" * 60)

    # Read the SQL migration file
    migration_file = Path(__file__).parent / "migrations" / "add_email_identity_resolution.sql"

    if not migration_file.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False

    with open(migration_file, 'r') as f:
        sql_content = f.read()

    logger.info(f"Loaded migration file: {migration_file}")
    logger.info(f"SQL content length: {len(sql_content)} characters")

    # Execute the entire migration as a single transaction
    try:
        with engine.connect() as conn:
            # Execute the full SQL script
            conn.execute(text(sql_content))
            conn.commit()
            logger.info("✅ Migration executed successfully!")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def verify_migration():
    """Verify the migration was successful."""
    from database import engine
    from sqlalchemy import text

    logger.info("")
    logger.info("Verifying migration...")

    checks = []

    with engine.connect() as conn:
        # Check known_client_emails table exists
        try:
            result = conn.execute(text(
                "SELECT COUNT(*) FROM known_client_emails"
            )).scalar()
            checks.append(("known_client_emails table", True, f"{result} records"))
        except Exception as e:
            checks.append(("known_client_emails table", False, str(e)))

        # Check email_identity_resolution_log table exists
        try:
            result = conn.execute(text(
                "SELECT COUNT(*) FROM email_identity_resolution_log"
            )).scalar()
            checks.append(("email_identity_resolution_log table", True, f"{result} records"))
        except Exception as e:
            checks.append(("email_identity_resolution_log table", False, str(e)))

        # Check new columns on email_reconciliation_queue
        try:
            conn.execute(text(
                "SELECT match_evidence, match_client_name, match_loan_number, is_priority "
                "FROM email_reconciliation_queue LIMIT 1"
            ))
            checks.append(("email_reconciliation_queue columns", True, "All columns present"))
        except Exception as e:
            checks.append(("email_reconciliation_queue columns", False, str(e)))

        # Check coborrower_email column on loans
        try:
            conn.execute(text("SELECT coborrower_email FROM loans LIMIT 1"))
            checks.append(("loans.coborrower_email column", True, "Present"))
        except Exception as e:
            checks.append(("loans.coborrower_email column", False, str(e)))

        # Check views exist
        try:
            conn.execute(text("SELECT 1 FROM v_priority_emails LIMIT 1"))
            checks.append(("v_priority_emails view", True, "Exists"))
        except Exception as e:
            checks.append(("v_priority_emails view", False, str(e)))

        try:
            conn.execute(text("SELECT 1 FROM v_email_match_stats LIMIT 1"))
            checks.append(("v_email_match_stats view", True, "Exists"))
        except Exception as e:
            checks.append(("v_email_match_stats view", False, str(e)))

        # Check functions exist
        try:
            conn.execute(text("SELECT get_client_emails(1, NULL, NULL, NULL)"))
            checks.append(("get_client_emails function", True, "Exists"))
        except Exception as e:
            if "does not exist" in str(e).lower():
                checks.append(("get_client_emails function", False, str(e)))
            else:
                checks.append(("get_client_emails function", True, "Exists (no data)"))

        try:
            conn.execute(text("SELECT sync_entity_emails(1, 'lead', 1)"))
            checks.append(("sync_entity_emails function", True, "Exists"))
        except Exception as e:
            if "does not exist" in str(e).lower():
                checks.append(("sync_entity_emails function", False, str(e)))
            else:
                checks.append(("sync_entity_emails function", True, "Exists (no matching entity)"))

    # Print results
    logger.info("")
    logger.info("Verification Results:")
    logger.info("-" * 50)

    all_passed = True
    for name, passed, detail in checks:
        status = "✅" if passed else "❌"
        logger.info(f"  {status} {name}: {detail}")
        if not passed:
            all_passed = False

    return all_passed


def show_stats():
    """Show current statistics."""
    from database import engine
    from sqlalchemy import text

    logger.info("")
    logger.info("Current Statistics:")
    logger.info("-" * 50)

    with engine.connect() as conn:
        try:
            # Email queue stats
            total = conn.execute(text(
                "SELECT COUNT(*) FROM email_reconciliation_queue"
            )).scalar() or 0

            matched = conn.execute(text("""
                SELECT COUNT(*) FROM email_reconciliation_queue
                WHERE matched_contact_id IS NOT NULL
                   OR matched_loan_id IS NOT NULL
                   OR matched_lead_id IS NOT NULL
            """)).scalar() or 0

            priority = conn.execute(text("""
                SELECT COUNT(*) FROM email_reconciliation_queue
                WHERE is_priority = TRUE
            """)).scalar() or 0

            logger.info(f"  Email Queue: {total} total, {matched} matched, {priority} priority")

            # Known clients stats
            known = conn.execute(text(
                "SELECT COUNT(*) FROM known_client_emails"
            )).scalar() or 0

            logger.info(f"  Known Clients: {known} email addresses")

            # Match method breakdown
            methods = conn.execute(text("""
                SELECT match_method, COUNT(*) as cnt
                FROM email_reconciliation_queue
                WHERE match_method IS NOT NULL
                GROUP BY match_method
                ORDER BY cnt DESC
            """)).fetchall()

            if methods:
                logger.info("  Match Methods:")
                for method, count in methods:
                    logger.info(f"    - {method}: {count}")

        except Exception as e:
            logger.error(f"Error getting stats: {e}")


if __name__ == "__main__":
    try:
        success = run_migration()

        if success:
            verify_success = verify_migration()
            show_stats()

            if verify_success:
                logger.info("")
                logger.info("=" * 60)
                logger.info("✅ Migration completed and verified successfully!")
                logger.info("")
                logger.info("Next steps:")
                logger.info("  1. Deploy the updated backend")
                logger.info("  2. Call POST /api/v1/email-intelligence/sync-known-clients")
                logger.info("     to populate the known_client_emails table")
                logger.info("=" * 60)
                sys.exit(0)
            else:
                logger.error("❌ Migration completed but verification found issues")
                sys.exit(1)
        else:
            logger.error("❌ Migration failed")
            sys.exit(1)

    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
