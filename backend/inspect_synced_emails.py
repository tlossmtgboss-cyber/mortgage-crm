"""
Inspect Synced Emails
Check what content is in the 21 synced emails
"""
import os
import sys
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def inspect_emails():
    """Inspect the content of synced emails"""
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Use text-based imports to avoid SQLAlchemy model issues
        from sqlalchemy import text

        db = SessionLocal()

        print("=" * 70)
        print("INSPECTING SYNCED EMAILS")
        print("=" * 70)

        # Get recent emails using raw SQL
        result = db.execute(text("""
            SELECT id, subject, sender, received_at, processed,
                   SUBSTR(raw_text, 1, 200) as preview
            FROM incoming_data_events
            ORDER BY created_at DESC
            LIMIT 25
        """))

        emails = result.fetchall()

        print(f"\n📧 Found {len(emails)} recent emails\n")

        for email in emails:
            email_id, subject, sender, received_at, processed, preview = email

            # Check if extracted
            extracted = db.execute(text("""
                SELECT id, category, status, ai_confidence
                FROM extracted_data
                WHERE event_id = :event_id
                LIMIT 1
            """), {"event_id": email_id}).fetchone()

            print(f"\n{'='*70}")
            print(f"📧 Email ID: {email_id}")
            print(f"   Subject: {subject}")
            print(f"   From: {sender}")
            print(f"   Received: {received_at}")
            print(f"   Processed: {'Yes' if processed else 'No'}")

            if extracted:
                ext_id, category, status, confidence = extracted
                print(f"   ✅ EXTRACTED:")
                print(f"      ID: {ext_id}")
                print(f"      Category: {category}")
                print(f"      Status: {status}")
                print(f"      Confidence: {confidence}")
            else:
                print(f"   ❌ NOT EXTRACTED - AI didn't find loan data")

            print(f"\n   Preview (first 200 chars):")
            print(f"   {preview if preview else '(no text content)'}")

        # Summary
        total_count = db.execute(text("SELECT COUNT(*) FROM incoming_data_events")).scalar()
        extracted_count = db.execute(text("SELECT COUNT(*) FROM extracted_data")).scalar()
        pending_count = db.execute(text("""
            SELECT COUNT(*) FROM extracted_data
            WHERE status IN ('pending_review', 'needs_review')
        """)).scalar()

        print(f"\n{'='*70}")
        print(f"📊 SUMMARY:")
        print(f"   Total emails synced: {total_count}")
        print(f"   Successfully extracted: {extracted_count}")
        print(f"   Pending in Reconciliation: {pending_count}")
        print(f"   Failed extraction: {total_count - extracted_count}")
        print(f"={'='*70}\n")

        db.close()
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = inspect_emails()
    sys.exit(0 if success else 1)
