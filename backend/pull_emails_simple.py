"""
Simple Email Pull Script
Fetches emails directly using Microsoft Graph API
"""
import os
import sys
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, timezone

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def decrypt_token(encrypted_token):
    """Simple decrypt - in production this should use proper encryption"""
    # For now, assume tokens are stored as-is
    return encrypted_token

def pull_emails():
    """Pull emails from Microsoft 365"""
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        from main import MicrosoftOAuthToken

        db = SessionLocal()

        print("=" * 60)
        print("PULLING EMAILS FROM MICROSOFT 365")
        print("=" * 60)

        # Get OAuth token
        print("\n1️⃣  Checking Microsoft 365 connection...")
        oauth = db.query(MicrosoftOAuthToken).first()

        if not oauth:
            print("❌ No Microsoft OAuth token found")
            db.close()
            return False

        print(f"✅ Connected to: {oauth.email_address}")
        print(f"   Sync enabled: {oauth.sync_enabled}")
        print(f"   Auto-delete: {oauth.auto_delete_imported_emails}")

        # Get access token
        access_token = decrypt_token(oauth.access_token)

        # Fetch emails
        print("\n2️⃣  Fetching emails from inbox...")

        folder = oauth.sync_folder or "Inbox"
        graph_url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages"

        # Get last 10 emails
        graph_url += "?$top=10&$orderby=receivedDateTime desc"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = requests.get(graph_url, headers=headers)

        if response.status_code == 401:
            print("⚠️  Token expired - needs refresh")
            print("   Please reconnect Microsoft 365 in the CRM Settings")
            db.close()
            return False
        elif response.status_code != 200:
            print(f"❌ API Error: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            db.close()
            return False

        emails_data = response.json()
        emails = emails_data.get("value", [])

        print(f"✅ Found {len(emails)} emails")

        if len(emails) == 0:
            print("   No emails in inbox")
            db.close()
            return True

        # Display emails
        print("\n3️⃣  Email Summary:")
        print("-" * 60)

        for i, email in enumerate(emails, 1):
            subject = email.get("subject", "No Subject")
            sender = email.get("from", {}).get("emailAddress", {}).get("address", "Unknown")
            received = email.get("receivedDateTime", "")
            has_attachments = email.get("hasAttachments", False)
            is_read = email.get("isRead", False)

            print(f"\n   [{i}] {subject}")
            print(f"       From: {sender}")
            print(f"       Received: {received}")
            print(f"       Attachments: {'Yes' if has_attachments else 'No'}")
            print(f"       Read: {'Yes' if is_read else 'No'}")

        print("\n" + "=" * 60)
        print(f"✅ Successfully retrieved {len(emails)} emails!")
        print("=" * 60)

        db.close()
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = pull_emails()
    sys.exit(0 if success else 1)
