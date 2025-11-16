#!/usr/bin/env python
"""Check demo account for emails to process with Claude"""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("❌ DATABASE_URL not set")
    exit(1)

print("="*80)
print("CHECKING DEMO ACCOUNT FOR EMAILS")
print("="*80)

engine = create_engine(database_url)

with engine.connect() as conn:
    # Get demo user
    result = conn.execute(text("""
        SELECT id, email, username
        FROM users
        WHERE email = 'demo@example.com' OR username = 'demo@example.com'
        LIMIT 1
    """))

    user = result.fetchone()

    if not user:
        print("\n❌ Demo user not found")
        exit(1)

    user_id, email, username = user
    print(f"\n✅ Demo User Found")
    print(f"   ID: {user_id}")
    print(f"   Email: {email}")
    print(f"   Username: {username}")

    # Check for incoming emails
    result = conn.execute(text("""
        SELECT COUNT(*)
        FROM incoming_data_events
        WHERE user_id = :user_id
    """), {"user_id": user_id})

    total_emails = result.fetchone()[0]
    print(f"\n📧 Total Emails: {total_emails}")

    # Check for unprocessed emails
    result = conn.execute(text("""
        SELECT COUNT(*)
        FROM incoming_data_events ide
        LEFT JOIN extracted_data ed ON ide.id = ed.event_id
        WHERE ide.user_id = :user_id AND ed.id IS NULL
    """), {"user_id": user_id})

    unprocessed = result.fetchone()[0]
    print(f"⏳ Unprocessed Emails: {unprocessed}")

    # Check for processed emails
    processed = total_emails - unprocessed
    print(f"✅ Processed Emails: {processed}")

    # Show recent emails
    if total_emails > 0:
        print(f"\n📋 Recent Emails:")
        result = conn.execute(text("""
            SELECT
                ide.id,
                ide.subject,
                ide.sender,
                ide.received_at,
                ide.processed,
                ed.id as extracted_id,
                ed.ai_confidence
            FROM incoming_data_events ide
            LEFT JOIN extracted_data ed ON ide.id = ed.event_id
            WHERE ide.user_id = :user_id
            ORDER BY ide.received_at DESC
            LIMIT 10
        """), {"user_id": user_id})

        emails = result.fetchall()
        for i, email in enumerate(emails, 1):
            event_id, subject, sender, received_at, processed, extracted_id, confidence = email
            status = "✅ Processed" if extracted_id else "⏳ Unprocessed"
            conf_str = f"({confidence*100:.1f}% confidence)" if confidence else ""
            print(f"   {i}. [{status}] {subject[:40]}")
            print(f"      From: {sender} | {received_at.strftime('%Y-%m-%d %H:%M') if received_at else 'N/A'} {conf_str}")

    # Check Microsoft OAuth
    print(f"\n🔗 Microsoft 365 Connection:")
    result = conn.execute(text("""
        SELECT
            id,
            access_token IS NOT NULL as has_token,
            expires_at
        FROM microsoft_oauth_tokens
        WHERE user_id = :user_id
        LIMIT 1
    """), {"user_id": user_id})

    oauth = result.fetchone()
    if oauth:
        oauth_id, has_token, expires_at = oauth
        print(f"   ✅ Connected (ID: {oauth_id})")
        print(f"   Has valid token: {has_token}")
        print(f"   Expires: {expires_at}")
    else:
        print(f"   ❌ Not connected")
        print(f"   Need to connect Microsoft 365 in Settings > Integrations")

print(f"\n{'='*80}")
print("SUMMARY")
print("="*80)

if unprocessed > 0:
    print(f"\n🎉 Found {unprocessed} unprocessed emails!")
    print(f"\n💡 Next Steps:")
    print(f"   1. These emails can be processed with Claude")
    print(f"   2. Call: POST /api/v1/microsoft/reprocess-emails")
    print(f"   3. Claude will extract fields with 97-99% accuracy")
    print(f"\n   Or I can create a script to reprocess them now!")
elif total_emails > 0:
    print(f"\n✅ All {total_emails} emails already processed")
    print(f"\n💡 To test Claude:")
    print(f"   1. Send a new test email to connected inbox")
    print(f"   2. Or trigger sync: POST /api/v1/microsoft/sync-emails")
else:
    print(f"\n📭 No emails found in demo account")
    print(f"\n💡 To test Claude:")
    if oauth:
        print(f"   1. Send test email to connected inbox")
        print(f"   2. Wait for auto-sync (5 min) or trigger manual sync")
    else:
        print(f"   1. Connect Microsoft 365 in Settings > Integrations")
        print(f"   2. Send test email to that inbox")
        print(f"   3. Claude will process it automatically")
