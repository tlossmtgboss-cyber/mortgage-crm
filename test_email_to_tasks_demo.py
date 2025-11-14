#!/usr/bin/env python3
"""
Demo: Show how email-to-task flow would work
This demo doesn't require actual Microsoft OAuth connection
"""
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
    User,
    Task,
    Base
)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test_agentic_crm.db")
if DATABASE_URL.startswith("sqlite:///./"):
    db_file = DATABASE_URL.replace("sqlite:///./", "")
    DATABASE_URL = f"sqlite:///./backend/{db_file}"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create all tables
Base.metadata.create_all(bind=engine)

def demo_email_to_tasks():
    """Demo showing how emails would be converted to tasks"""
    db = SessionLocal()

    try:
        print("\n" + "="*60)
        print("EMAIL TO TASKS DEMO")
        print("="*60)

        # Step 1: Get or create user
        print("\n1️⃣  Finding user...")
        user = db.query(User).filter(User.email == "tloss@cmgfi.com").first()
        if not user:
            print("   Creating user...")
            user = User(
                email="tloss@cmgfi.com",
                full_name="Tim Loss",
                hashed_password="test"
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        print(f"✅ User: {user.full_name} ({user.email})")

        # Step 2: Simulate email data (what would come from Microsoft Graph)
        print("\n2️⃣  Simulating incoming emails...")

        mock_emails = [
            {
                "subject": "Pre-approval request from John Smith",
                "from": {"emailAddress": {"address": "john.smith@example.com"}},
                "receivedDateTime": "2025-01-15T10:30:00Z",
                "bodyPreview": "Hi, I'm looking to get pre-approved for a mortgage..."
            },
            {
                "subject": "Documents ready for review - Case #12345",
                "from": {"emailAddress": {"address": "sarah.jones@realty.com"}},
                "receivedDateTime": "2025-01-15T11:45:00Z",
                "bodyPreview": "The appraisal documents are ready for your review..."
            },
            {
                "subject": "Rate lock expiring soon",
                "from": {"emailAddress": {"address": "alerts@mortgagesystem.com"}},
                "receivedDateTime": "2025-01-15T14:20:00Z",
                "bodyPreview": "ALERT: Rate lock for Thompson loan expires in 3 days..."
            },
        ]

        print(f"✅ Simulated {len(mock_emails)} emails from inbox")

        # Step 3: Convert emails to tasks
        print("\n3️⃣  Creating tasks from emails...")
        tasks_created = 0

        for i, email in enumerate(mock_emails, 1):
            subject = email.get("subject", "No Subject")
            sender = email.get("from", {}).get("emailAddress", {}).get("address", "Unknown")
            preview = email.get("bodyPreview", "")

            print(f"\n   Email {i}/{len(mock_emails)}:")
            print(f"   From: {sender}")
            print(f"   Subject: {subject}")

            # Create task from email
            task_title = f"Follow up: {subject[:50]}"
            task_description = f"Email from {sender}\n\nSubject: {subject}\n\n{preview[:200]}..."

            # Determine priority based on keywords
            priority = "medium"
            if any(keyword in subject.lower() for keyword in ["urgent", "expiring", "alert", "asap"]):
                priority = "high"
            elif any(keyword in subject.lower() for keyword in ["fyi", "update", "reminder"]):
                priority = "low"

            task = Task(
                owner_id=user.id,
                title=task_title,
                description=task_description,
                status="pending",
                priority=priority,
                related_type="email_auto",
                created_at=datetime.now(timezone.utc)
            )
            db.add(task)
            db.commit()
            db.refresh(task)

            print(f"   ✅ Created task #{task.id}")
            print(f"      Priority: {priority}")
            tasks_created += 1

        # Step 4: Summary
        print("\n" + "="*60)
        print("📊 DEMO SUMMARY")
        print("="*60)
        print(f"Emails processed: {len(mock_emails)}")
        print(f"Tasks created: {tasks_created}")

        # Show created tasks
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
            print(f"   Description: {task.description[:100]}...")

        print("\n" + "="*60)
        print("✅ Demo completed successfully!")
        print("="*60)
        print("\nℹ️  Next Steps:")
        print("   1. Connect Microsoft 365 in Settings")
        print("   2. Real emails will be synced automatically")
        print("   3. Tasks will be created from actual inbox emails")

    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()

if __name__ == "__main__":
    print("Starting Email to Tasks Demo...")
    demo_email_to_tasks()
