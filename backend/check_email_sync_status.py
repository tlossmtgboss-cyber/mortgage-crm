"""
Check Email Sync Status
Diagnose why synced emails aren't appearing in Reconciliation
"""
import os
import sys
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def check_sync_status():
    """Check email sync and extraction status"""
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        from main import IncomingDataEvent, ExtractedData, User

        db = SessionLocal()

        print("=" * 70)
        print("EMAIL SYNC DIAGNOSTIC REPORT")
        print("=" * 70)

        # Get total counts
        total_incoming = db.query(IncomingDataEvent).count()
        total_extracted = db.query(ExtractedData).count()

        print(f"\n📊 OVERALL STATISTICS:")
        print(f"   Total incoming emails: {total_incoming}")
        print(f"   Total extracted data: {total_extracted}")
        print(f"   Extraction rate: {(total_extracted/total_incoming*100) if total_incoming > 0 else 0:.1f}%")

        # Check recent emails
        print(f"\n📧 RECENT INCOMING EMAILS (Last 10):")
        print("-" * 70)
        recent_emails = db.query(IncomingDataEvent).order_by(desc(IncomingDataEvent.created_at)).limit(10).all()

        for email in recent_emails:
            extracted = db.query(ExtractedData).filter(ExtractedData.event_id == email.id).first()
            status_icon = "✅" if extracted else "❌"
            print(f"\n   {status_icon} Email ID: {email.id}")
            print(f"      Subject: {email.subject}")
            print(f"      From: {email.sender}")
            print(f"      Received: {email.received_at}")
            print(f"      Processed: {email.processed}")
            if extracted:
                print(f"      Extracted: Yes (Status: {extracted.status})")
                print(f"      Category: {extracted.category}")
                print(f"      Confidence: {extracted.ai_confidence}")
            else:
                print(f"      Extracted: No - AI extraction failed or skipped")

        # Check extraction statuses
        print(f"\n📋 EXTRACTED DATA BY STATUS:")
        print("-" * 70)
        statuses = db.query(ExtractedData.status).distinct().all()
        for (status,) in statuses:
            count = db.query(ExtractedData).filter(ExtractedData.status == status).count()
            print(f"   {status}: {count}")

        # Check what would show in Reconciliation tab
        pending_count = db.query(ExtractedData).filter(
            ExtractedData.status.in_(['pending_review', 'needs_review'])
        ).count()
        print(f"\n🔍 RECONCILIATION TAB:")
        print(f"   Items that should appear: {pending_count}")

        if pending_count > 0:
            print(f"\n   Sample pending items:")
            pending_items = db.query(ExtractedData).filter(
                ExtractedData.status.in_(['pending_review', 'needs_review'])
            ).limit(5).all()
            for item in pending_items:
                event = db.query(IncomingDataEvent).filter(IncomingDataEvent.id == item.event_id).first()
                print(f"      - ID {item.id}: {event.subject if event else 'Unknown'} (Status: {item.status})")

        # Check for errors
        print(f"\n⚠️  POTENTIAL ISSUES:")
        print("-" * 70)
        unprocessed = db.query(IncomingDataEvent).filter(IncomingDataEvent.processed == False).count()
        print(f"   Unprocessed emails: {unprocessed}")

        no_extraction = total_incoming - total_extracted
        print(f"   Emails without extraction: {no_extraction}")

        if no_extraction > 0:
            print(f"\n   💡 These emails were synced but AI extraction failed.")
            print(f"      Possible reasons:")
            print(f"      - Email content didn't match any loan data patterns")
            print(f"      - AI confidence too low")
            print(f"      - Processing error occurred")

        print("\n" + "=" * 70)

        db.close()
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = check_sync_status()
    sys.exit(0 if success else 1)
