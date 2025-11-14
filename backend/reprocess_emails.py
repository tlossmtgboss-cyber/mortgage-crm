"""
Reprocess Existing Emails with New Extraction Logic
Re-runs AI extraction on emails that were synced but not extracted
"""
import os
import sys
import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

async def reprocess_unextracted_emails():
    """Find and reprocess emails that have no extracted_data record"""
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Import the processing function from main
        from main import process_microsoft_email_to_dre, IncomingDataEvent, ExtractedData

        db = SessionLocal()

        print("=" * 70)
        print("REPROCESSING UNEXTRACTED EMAILS")
        print("=" * 70)

        # Find all emails without extracted data
        unextracted = db.execute(text("""
            SELECT ide.id, ide.subject, ide.sender, ide.user_id
            FROM incoming_data_events ide
            LEFT JOIN extracted_data ed ON ide.id = ed.event_id
            WHERE ed.id IS NULL
            ORDER BY ide.created_at DESC
        """)).fetchall()

        print(f"\n📧 Found {len(unextracted)} emails without extraction\n")

        if len(unextracted) == 0:
            print("✅ No emails need reprocessing!")
            db.close()
            return True

        # Reprocess each email
        success_count = 0
        error_count = 0

        for email_id, subject, sender, user_id in unextracted:
            print(f"Processing: {subject[:50]}...")

            # Get the full email event
            event = db.query(IncomingDataEvent).filter(IncomingDataEvent.id == email_id).first()

            if not event:
                print(f"   ❌ Event not found")
                error_count += 1
                continue

            # Create email_data dict from the event (mimicking Microsoft Graph format)
            email_data = {
                "subject": event.subject,
                "from": {"emailAddress": {"address": event.sender}},
                "toRecipients": [{"emailAddress": {"address": r}} for r in (event.recipients or [])],
                "receivedDateTime": event.received_at.isoformat() if event.received_at else None,
                "body": {
                    "content": event.raw_text or event.raw_html or "",
                    "contentType": "text" if event.raw_text else "html"
                }
            }

            # Reprocess with new extraction logic
            try:
                # Delete the old event to avoid duplicates
                db.delete(event)
                db.commit()

                # Process fresh with new logic
                result = await process_microsoft_email_to_dre(email_data, user_id, db)

                if result.get("status") == "success":
                    print(f"   ✅ Successfully extracted")
                    success_count += 1
                else:
                    print(f"   ⚠️  Processed but no extraction: {result.get('error', 'No error')}")
                    success_count += 1  # Still count as success - it was processed

            except Exception as e:
                print(f"   ❌ Error: {e}")
                error_count += 1
                db.rollback()

        print(f"\n{'='*70}")
        print(f"📊 RESULTS:")
        print(f"   Successfully processed: {success_count}")
        print(f"   Errors: {error_count}")
        print(f"   Total: {len(unextracted)}")
        print(f"{'='*70}\n")

        db.close()
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(reprocess_unextracted_emails())
    sys.exit(0 if success else 1)
