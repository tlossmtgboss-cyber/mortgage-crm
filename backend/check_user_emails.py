#!/usr/bin/env python
"""Check user account and unprocessed emails in Railway database"""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# This script runs in Railway environment with DATABASE_URL set
database_url = os.getenv("DATABASE_URL")

if not database_url:
    print("❌ DATABASE_URL not set")
    exit(1)

print("="*80)
print("CHECKING tloss@cmgfi.com ACCOUNT")
print("="*80)

engine = create_engine(database_url)

# Check if user exists
print("\n1️⃣  Looking for user account...")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT id, email, username, is_admin, created_at
        FROM users
        WHERE email = 'tloss@cmgfi.com' OR username = 'tloss@cmgfi.com'
        LIMIT 1
    """))
    user = result.fetchone()

    if user:
        user_id = user[0]
        print(f"✅ User found!")
        print(f"   ID: {user_id}")
        print(f"   Email: {user[1]}")
        print(f"   Username: {user[2]}")
        print(f"   Admin: {user[3]}")
        print(f"   Created: {user[4]}")
    else:
        print(f"❌ User not found")
        print(f"   Creating test query to see all users...")
        result = conn.execute(text("SELECT id, email FROM users LIMIT 5"))
        users = result.fetchall()
        print(f"\n   Available users:")
        for u in users:
            print(f"   - {u[1]} (ID: {u[0]})")
        exit(1)

    # Check for unprocessed emails
    print(f"\n2️⃣  Checking for unprocessed emails for user {user_id}...")
    result = conn.execute(text("""
        SELECT COUNT(*)
        FROM incoming_data_events ide
        LEFT JOIN extracted_data ed ON ide.id = ed.event_id
        WHERE ed.id IS NULL AND ide.user_id = :user_id
    """), {"user_id": user_id})

    unprocessed_count = result.fetchone()[0]
    print(f"   Unprocessed emails: {unprocessed_count}")

    # Check for Microsoft OAuth connection
    print(f"\n3️⃣  Checking Microsoft 365 connection...")
    result = conn.execute(text("""
        SELECT id, access_token IS NOT NULL as has_token, created_at, expires_at
        FROM microsoft_oauth_tokens
        WHERE user_id = :user_id
        LIMIT 1
    """), {"user_id": user_id})

    oauth = result.fetchone()
    if oauth:
        print(f"✅ Microsoft 365 connected!")
        print(f"   Has valid token: {oauth[1]}")
        print(f"   Connected: {oauth[2]}")
        print(f"   Expires: {oauth[3]}")
    else:
        print(f"⚠️  No Microsoft 365 connection")
        print(f"   User needs to connect Microsoft 365 in Settings")

    # Check recent incoming emails
    print(f"\n4️⃣  Recent incoming emails...")
    result = conn.execute(text("""
        SELECT id, subject, sender, received_at, processed
        FROM incoming_data_events
        WHERE user_id = :user_id
        ORDER BY received_at DESC
        LIMIT 5
    """), {"user_id": user_id})

    emails = result.fetchall()
    if emails:
        print(f"   Found {len(emails)} recent emails:")
        for email in emails:
            status = "✅ Processed" if email[4] else "⏳ Pending"
            print(f"   - [{status}] {email[1][:50]} (from: {email[2]})")
    else:
        print(f"   No emails found")

print(f"\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"\nUser: {user[1]}")
print(f"Unprocessed emails: {unprocessed_count}")
print(f"Microsoft 365: {'Connected' if oauth else 'Not connected'}")
print(f"\n💡 To test Claude:")
if unprocessed_count > 0:
    print(f"   - Call /api/v1/microsoft/reprocess-emails to process {unprocessed_count} emails with Claude")
elif oauth:
    print(f"   - Call /api/v1/microsoft/sync-emails to fetch new emails")
    print(f"   - Or send a test email to your connected inbox")
else:
    print(f"   - Connect Microsoft 365 in CRM Settings first")
    print(f"   - Then send a test email")
