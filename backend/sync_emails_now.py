"""
Sync Emails from Microsoft 365 Inbox
Fetches and processes emails through the DRE
"""
import os
import sys
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

async def sync_emails():
    """Fetch and process emails from Microsoft 365"""
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Import after engine is created
        from main import MicrosoftOAuthToken, User, fetch_microsoft_emails, process_microsoft_email_to_dre

        db = SessionLocal()

        print("=" * 60)
        print("MICROSOFT 365 EMAIL SYNC")
        print("=" * 60)

        # Get OAuth token
        print("\n1️⃣  Checking Microsoft 365 connection...")
        oauth = db.query(MicrosoftOAuthToken).first()

        if not oauth:
            print("❌ No Microsoft OAuth token found")
            print("   Please connect Microsoft 365 in Settings first")
            db.close()
            return False

        print(f"✅ Connected to: {oauth.email_address}")
        print(f"   Sync enabled: {oauth.sync_enabled}")
        print(f"   Auto-delete: {oauth.auto_delete_imported_emails}")

        # Get user
        user = db.query(User).filter(User.id == oauth.user_id).first()
        if not user:
            print("❌ User not found")
            db.close()
            return False

        # Fetch emails
        print("\n2️⃣  Fetching emails from inbox...")
        result = await fetch_microsoft_emails(oauth, db, limit=50)

        if "error" in result:
            print(f"❌ Error: {result['error']}")
            db.close()
            return False

        emails = result.get("emails", [])
        print(f"✅ Found {len(emails)} emails")

        if len(emails) == 0:
            print("   No new emails to process")
            db.close()
            return True

        # Process each email
        print("\n3️⃣  Processing emails through AI extraction...")
        processed_count = 0

        for i, email_data in enumerate(emails, 1):
            subject = email_data.get("subject", "No Subject")
            sender_data = email_data.get("from", {})
            sender = sender_data.get("emailAddress", {}).get("address", "Unknown") if sender_data else "Unknown"

            print(f"\n   Email {i}/{len(emails)}:")
            print(f"   Subject: {subject}")
            print(f"   From: {sender}")

            # Process through DRE
            process_result = await process_microsoft_email_to_dre(email_data, user.id, db)

            if process_result.get("status") == "success":
                print(f"   ✅ Processed successfully")
                processed_count += 1
            else:
                print(f"   ⚠️  Processing failed: {process_result.get('error', 'Unknown error')}")

        # Summary
        print("\n" + "=" * 60)
        print("📊 SYNC SUMMARY")
        print("=" * 60)
        print(f"Emails fetched: {len(emails)}")
        print(f"Emails processed: {processed_count}")
        print(f"Success rate: {(processed_count/len(emails)*100):.1f}%" if emails else "N/A")
        print("\n✅ Sync completed!")
        print("\n💡 Check Reconciliation Center to review extracted data")

        db.close()
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(sync_emails())
    sys.exit(0 if success else 1)
