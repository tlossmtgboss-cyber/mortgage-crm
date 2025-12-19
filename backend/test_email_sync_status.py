#!/usr/bin/env python3
"""
Test Email Sync and Reconciliation Status
Verifies emails are syncing and populating the reconciliation tab
"""
import os
import sys
from sqlalchemy import create_engine, text
from datetime import datetime, timezone


def main():
    # Get database URL
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment")
        sys.exit(1)

    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    print("=" * 70)
    print("📧 EMAIL SYNC AND RECONCILIATION STATUS TEST")
    print("=" * 70)
    print()

    try:
        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            # Test 1: Check incoming_data_events table
            print("1️⃣  INCOMING DATA EVENTS (Raw Emails)")
            print("-" * 70)

            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN processed = true THEN 1 END) as processed,
                    COUNT(CASE WHEN processed = false THEN 1 END) as pending,
                    COUNT(CASE WHEN external_message_id IS NOT NULL THEN 1 END) as with_message_id
                FROM incoming_data_events
                WHERE source = 'microsoft365'
            """))
            row = result.fetchone()

            print(f"   Total emails received: {row[0]}")
            print(f"   ✅ Processed: {row[1]}")
            print(f"   ⏳ Pending: {row[2]}")
            print(f"   🔑 With Message ID: {row[3]}")
            print()

            # Show recent emails
            if row[0] > 0:
                result = conn.execute(text("""
                    SELECT subject, sender, received_at, processed, external_message_id
                    FROM incoming_data_events
                    WHERE source = 'microsoft365'
                    ORDER BY received_at DESC
                    LIMIT 5
                """))
                print("   Recent emails:")
                for email in result:
                    status = "✅" if email[3] else "⏳"
                    subject = email[0][:50] if email[0] else "No subject"
                    print(f"   {status} {subject} (from: {email[1]})")
                print()

            # Test 2: Check reconciliation_items table
            print("2️⃣  RECONCILIATION ITEMS (AI Extracted Data)")
            print("-" * 70)

            result = conn.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                    COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected
                FROM reconciliation_items
            """))
            row = result.fetchone()

            print(f"   Total reconciliation items: {row[0]}")
            print(f"   ⏳ Pending Review: {row[1]}")
            print(f"   ✅ Approved: {row[2]}")
            print(f"   ❌ Rejected: {row[3]}")
            print()

            # Show recent reconciliation items
            if row[0] > 0:
                result = conn.execute(text("""
                    SELECT
                        entity_type,
                        confidence_score,
                        status,
                        created_at,
                        extracted_data::jsonb->>'borrower_name' as borrower,
                        extracted_data::jsonb->>'property_address' as property
                    FROM reconciliation_items
                    ORDER BY created_at DESC
                    LIMIT 5
                """))
                print("   Recent reconciliation items:")
                for item in result:
                    confidence = int(item[1] * 100) if item[1] else 0
                    entity_type = item[0] or "unknown"
                    status_icon = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(item[2], "❓")
                    borrower = item[4] or "N/A"
                    print(f"   {status_icon} {entity_type.upper()} | Confidence: {confidence}% | Borrower: {borrower}")
                print()

            # Test 3: Check external_message_id column exists
            print("3️⃣  DATABASE SCHEMA CHECK")
            print("-" * 70)

            result = conn.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'incoming_data_events'
                AND column_name = 'external_message_id'
            """))

            if result.fetchone():
                print("   ✅ external_message_id column EXISTS")
            else:
                print("   ❌ external_message_id column MISSING")
            print()

            # Test 4: Summary
            print("=" * 70)
            print("📊 SUMMARY")
            print("=" * 70)

            # Get counts again for summary
            emails = conn.execute(text("SELECT COUNT(*) FROM incoming_data_events WHERE source = 'microsoft365'")).fetchone()[0]
            reconciliation = conn.execute(text("SELECT COUNT(*) FROM reconciliation_items")).fetchone()[0]
            pending = conn.execute(text("SELECT COUNT(*) FROM reconciliation_items WHERE status = 'pending'")).fetchone()[0]

            if emails == 0:
                print("⚠️  No emails found - Click 'Sync Now' in Settings to pull emails")
            elif reconciliation == 0:
                print("⚠️  Emails found but no reconciliation items - AI processing may have failed")
            elif pending > 0:
                print(f"✅ System working! {emails} emails synced, {pending} items awaiting review in Reconciliation tab")
            else:
                print(f"✅ All items processed! {emails} emails synced, {reconciliation} items reviewed")

            print()
            print("🔗 Next step: Open CRM → Reconciliation tab to review pending items")
            print("=" * 70)

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
