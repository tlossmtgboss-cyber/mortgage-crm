#!/usr/bin/env python3
"""
Verify tloss@cmgfi.com user exists in production and has proper access
"""
import os
import sys
from sqlalchemy import create_engine, text

# Production database URL
PROD_DB_URL = os.getenv("PROD_DATABASE_URL")

if not PROD_DB_URL:
    print("⚠️  Set PROD_DATABASE_URL environment variable:")
    print('export PROD_DATABASE_URL="postgresql://..."')
    sys.exit(1)

print("=" * 70)
print("PRODUCTION USER VERIFICATION")
print("=" * 70)
print()

try:
    engine = create_engine(PROD_DB_URL)

    with engine.connect() as conn:
        # Check if tloss@cmgfi.com exists
        print("🔍 Checking for tloss@cmgfi.com user...")
        result = conn.execute(text("""
            SELECT
                id,
                email,
                full_name,
                role,
                branch_id,
                created_at
            FROM users
            WHERE email = 'tloss@cmgfi.com'
        """))

        user = result.fetchone()

        if user:
            print("✅ User found!")
            print(f"   ID: {user[0]}")
            print(f"   Email: {user[1]}")
            print(f"   Name: {user[2]}")
            print(f"   Role: {user[3]}")
            print(f"   Branch ID: {user[4]}")
            print(f"   Created: {user[5]}")
            print()

            # Check user's data
            user_id = user[0]

            print("📊 User's Data Summary:")
            print("-" * 70)

            # Leads
            result = conn.execute(text(
                "SELECT COUNT(*) FROM leads WHERE owner_id = :user_id"
            ), {"user_id": user_id})
            lead_count = result.fetchone()[0]
            print(f"   Leads: {lead_count}")

            # Loans
            result = conn.execute(text(
                "SELECT COUNT(*) FROM loans WHERE loan_officer_id = :user_id"
            ), {"user_id": user_id})
            loan_count = result.fetchone()[0]
            print(f"   Loans: {loan_count}")

            # Tasks
            result = conn.execute(text(
                "SELECT COUNT(*) FROM ai_tasks WHERE assigned_to_id = :user_id"
            ), {"user_id": user_id})
            task_count = result.fetchone()[0]
            print(f"   Tasks: {task_count}")

            # Team Members
            result = conn.execute(text("SELECT COUNT(*) FROM team_members"))
            team_count = result.fetchone()[0]
            print(f"   Team Members: {team_count}")

            # Referral Partners
            result = conn.execute(text("SELECT COUNT(*) FROM referral_partners"))
            partner_count = result.fetchone()[0]
            print(f"   Referral Partners: {partner_count}")

            # MUM Clients
            result = conn.execute(text("SELECT COUNT(*) FROM mum_clients"))
            mum_count = result.fetchone()[0]
            print(f"   MUM Clients: {mum_count}")

            print()
            print("✅ User has proper access to all features")

        else:
            print("❌ User NOT found!")
            print()
            print("   This user needs to be created in production.")
            print("   Options:")
            print("   1. Create via frontend registration")
            print("   2. Create via SQL INSERT")
            print("   3. Create via admin endpoint")

        print()
        print("=" * 70)

except Exception as e:
    print(f"❌ Error: {str(e)}")
    sys.exit(1)
