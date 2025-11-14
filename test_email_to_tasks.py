#!/usr/bin/env python3
"""
Test: Pull emails from Outlook, parse content, and create tasks
"""
import asyncio
import sys
import os
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment
load_dotenv('backend/.env')

# Import from main
from main import (
    MicrosoftOAuthToken,
    User,
    Task,
    fetch_microsoft_emails,
    process_microsoft_email_to_dre,
    IncomingDataEvent,
    Base
)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test_agentic_crm.db")
# Point to the backend database directory
if DATABASE_URL.startswith("sqlite:///./"):
    db_file = DATABASE_URL.replace("sqlite:///./", "")
    DATABASE_URL = f"sqlite:///./backend/{db_file}"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create all tables
Base.metadata.create_all(bind=engine)

async def test_email_to_tasks():
    """Test email sync and task creation"""
    db = SessionLocal()

    try:
        print("\n" + "="*60)
        print("EMAIL TO TASKS TEST")
        print("="*60)

        # Step 1: Get user with Microsoft connected
        print("\n1️⃣  Finding user with Microsoft 365 connected...")
        user = db.query(User).filter(User.email == "tloss@cmgfi.com").first()
        if not user:
            print("❌ User not found. Creating test user...")
            user = User(
                email="tloss@cmgfi.com",
                full_name="Tim Loss",
                hashed_password="test"
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        print(f"✅ Found user: {user.full_name} ({user.email})")

        # Step 2: Check OAuth token
        print("\n2️⃣  Checking Microsoft OAuth token...")
        oauth_record = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.user_id == user.id
        ).first()

        if not oauth_record:
            print("❌ No Microsoft OAuth token found")
            print("   Please connect Microsoft 365 in Settings first")
            return

        print(f"✅ OAuth token found")
        print(f"   Sync enabled: {oauth_record.sync_enabled}")
        print(f"   Last sync: {oauth_record.last_sync_at}")

        # Step 3: Fetch emails from Microsoft
        print("\n3️⃣  Fetching emails from Microsoft Outlook...")
        result = await fetch_microsoft_emails(oauth_record, db, limit=10)

        if "error" in result:
            print(f"❌ Error fetching emails: {result['error']}")
            return

        emails = result.get("emails", [])
        print(f"✅ Fetched {len(emails)} emails")

        if len(emails) == 0:
            print("   No new emails to process")
            return

        # Step 4: Process each email
        print("\n4️⃣  Processing emails and creating tasks...")
        tasks_created = 0

        for i, email_data in enumerate(emails[:5], 1):  # Process first 5
            subject = email_data.get("subject", "No Subject")
            sender = email_data.get("from", {}).get("emailAddress", {}).get("address", "Unknown")
            received = email_data.get("receivedDateTime", "")

            print(f"\n   Email {i}/{min(5, len(emails))}:")
            print(f"   From: {sender}")
            print(f"   Subject: {subject}")
            print(f"   Received: {received}")

            # Process email into DRE
            process_result = await process_microsoft_email_to_dre(email_data, user.id, db)

            if process_result.get("status") == "success":
                print(f"   ✅ Processed successfully")

                # Check if task was created
                event_id = process_result.get("event_id")
                if event_id:
                    event = db.query(IncomingDataEvent).filter(
                        IncomingDataEvent.id == event_id
                    ).first()

                    if event:
                        print(f"   📧 Created data event #{event.id}")

                        # Create a task from the email
                        task_title = f"Follow up: {subject[:50]}"
                        task_description = f"Email from {sender}\n\nSubject: {subject}"

                        task = Task(
                            owner_id=user.id,
                            title=task_title,
                            description=task_description,
                            status="pending",
                            priority="medium",
                            related_type="email_auto",
                            created_at=datetime.now(timezone.utc)
                        )
                        db.add(task)
                        db.commit()
                        db.refresh(task)

                        print(f"   ✅ Created task #{task.id}: {task.title}")
                        tasks_created += 1
            else:
                print(f"   ⚠️  Processing failed: {process_result.get('error', 'Unknown error')}")

        # Step 5: Summary
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        print(f"Emails fetched: {len(emails)}")
        print(f"Emails processed: {min(5, len(emails))}")
        print(f"Tasks created: {tasks_created}")

        # Show created tasks
        if tasks_created > 0:
            print("\n📋 Created Tasks:")
            recent_tasks = db.query(Task).filter(
                Task.owner_id == user.id,
                Task.related_type == "email_auto"
            ).order_by(Task.created_at.desc()).limit(tasks_created).all()

            for task in recent_tasks:
                print(f"\n   Task #{task.id}")
                print(f"   Title: {task.title}")
                print(f"   Status: {task.status}")
                print(f"   Priority: {task.priority}")

        print("\n✅ Test completed successfully!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()

if __name__ == "__main__":
    print("Starting Email to Tasks Test...")
    asyncio.run(test_email_to_tasks())
