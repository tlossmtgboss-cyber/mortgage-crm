#!/usr/bin/env python3
"""
Run Email Monitor Migration
Creates 12 tables for intelligent email filtering with AI
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import engine, SessionLocal
from sqlalchemy import text

def run_migration():
    """Execute the email monitor migration SQL"""

    migration_path = os.path.join(
        os.path.dirname(__file__),
        "migrations",
        "add_email_monitor_tables.sql"
    )

    if not os.path.exists(migration_path):
        print(f"Error: Migration file not found at {migration_path}")
        return False

    print("Running Email Monitor migration...")
    print(f"Database: {engine.url}")

    with open(migration_path, 'r') as f:
        sql = f.read()

    # Split into individual statements
    statements = [s.strip() for s in sql.split(';') if s.strip()]

    db = SessionLocal()
    try:
        for i, statement in enumerate(statements):
            if statement and not statement.startswith('--'):
                try:
                    db.execute(text(statement))
                    db.commit()
                except Exception as e:
                    # Skip "already exists" errors
                    if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
                        db.rollback()
                        continue
                    else:
                        print(f"Error in statement {i+1}: {e}")
                        db.rollback()

        print("✅ Email Monitor migration completed successfully!")
        print("\nTables created:")
        print("  - email_monitor_addresses")
        print("  - email_monitor_keywords")
        print("  - email_monitor_rules")
        print("  - email_monitor_captured")
        print("  - email_crm_links")
        print("  - email_relevance_analysis")
        print("  - email_filter_whitelist")
        print("  - email_filter_blacklist")
        print("  - email_provider_config")
        print("  - gmail_oauth_tokens")
        print("  - outlook_oauth_tokens")
        print("  - email_monitor_log")
        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
