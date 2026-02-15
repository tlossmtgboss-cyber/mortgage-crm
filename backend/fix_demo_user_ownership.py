#!/usr/bin/env python3
"""
Fix script to update all leads and loans to be owned by the demo user.
This ensures the AI chat can properly query CRM data.
"""

import os
import sys
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is required")
    sys.exit(1)

def main():
    print("🔧 Fixing demo user data ownership...")

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Get demo user ID
        result = conn.execute(text("""
            SELECT id, email FROM users WHERE email = 'admin@perenniaai.com' LIMIT 1
        """))
        demo_user = result.fetchone()

        if not demo_user:
            print("❌ Demo user not found!")
            return

        demo_user_id = demo_user[0]
        print(f"📧 Found demo user: {demo_user[1]} (ID: {demo_user_id})")

        # Update leads owner_id
        result = conn.execute(text("""
            UPDATE leads
            SET owner_id = :user_id
            WHERE owner_id IS NULL OR owner_id != :user_id
        """), {"user_id": demo_user_id})
        leads_updated = result.rowcount

        # Update loans loan_officer_id
        result = conn.execute(text("""
            UPDATE loans
            SET loan_officer_id = :user_id
            WHERE loan_officer_id IS NULL OR loan_officer_id != :user_id
        """), {"user_id": demo_user_id})
        loans_updated = result.rowcount

        # Update tasks owner_id
        result = conn.execute(text("""
            UPDATE tasks
            SET owner_id = :user_id
            WHERE owner_id IS NULL OR owner_id != :user_id
        """), {"user_id": demo_user_id})
        tasks_updated = result.rowcount

        conn.commit()

        print(f"✅ Updated {leads_updated} leads")
        print(f"✅ Updated {loans_updated} loans")
        print(f"✅ Updated {tasks_updated} tasks")

        # Verify counts
        result = conn.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM leads WHERE owner_id = :user_id) as leads,
                (SELECT COUNT(*) FROM loans WHERE loan_officer_id = :user_id) as loans
        """), {"user_id": demo_user_id})
        counts = result.fetchone()

        print(f"\n📊 Demo user now owns:")
        print(f"   • {counts[0]} leads")
        print(f"   • {counts[1]} loans")

if __name__ == "__main__":
    main()
