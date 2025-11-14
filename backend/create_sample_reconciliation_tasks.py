#!/usr/bin/env python3
"""
Create 5 sample reconciliation tasks from emails
These will appear in the Reconciliation page for review
"""
import os
import sys
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not found")
    sys.exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
db = Session()

print("=" * 70)
print("📧 CREATING 5 SAMPLE RECONCILIATION TASKS FROM EMAILS")
print("=" * 70)
print()

# Sample email tasks
sample_emails = [
    {
        "subject": "RE: Johnson Loan - Appraisal Scheduled for Next Week",
        "sender": "appraisal@titleco.com",
        "content": """
Hi Team,

The appraisal for the Johnson property at 123 Oak Street has been scheduled for next Tuesday at 2 PM.
Loan amount: $450,000
Property value estimate: $475,000

Please confirm receipt.

Best regards,
Title Company
        """,
        "category": "loan_update",
        "subcategory": "appraisal_scheduled",
        "fields": {
            "borrower_name": {"value": "Johnson", "confidence": 0.85},
            "property_address": {"value": "123 Oak Street", "confidence": 0.90},
            "loan_amount": {"value": "$450,000", "confidence": 0.95},
            "appraisal_date": {"value": "Next Tuesday 2 PM", "confidence": 0.88},
            "estimated_value": {"value": "$475,000", "confidence": 0.92}
        }
    },
    {
        "subject": "URGENT: Smith Closing - Title Issue Detected",
        "sender": "title@escrow.com",
        "content": """
URGENT ATTENTION NEEDED

We've discovered a lien on the Smith property (456 Maple Avenue) that needs resolution before closing.
Loan: $325,000
Scheduled Closing: Friday
Issue: Outstanding HOA lien of $2,500

Please advise on next steps.
        """,
        "category": "loan_update",
        "subcategory": "title_issue",
        "fields": {
            "borrower_name": {"value": "Smith", "confidence": 0.92},
            "property_address": {"value": "456 Maple Avenue", "confidence": 0.95},
            "loan_amount": {"value": "$325,000", "confidence": 0.98},
            "closing_date": {"value": "Friday", "confidence": 0.85},
            "issue_type": {"value": "Outstanding HOA lien", "confidence": 0.90},
            "issue_amount": {"value": "$2,500", "confidence": 0.95}
        }
    },
    {
        "subject": "Williams Pre-Approval Request - $600K Budget",
        "sender": "sarah.williams@email.com",
        "content": """
Hello,

I'm interested in getting pre-approved for a mortgage. Here are my details:

Name: Sarah Williams
Phone: (555) 123-4567
Email: sarah.williams@email.com
Budget: $600,000
Property Type: Single Family Home
Location: Looking in the downtown area

Please let me know what documents you need.

Thank you!
Sarah
        """,
        "category": "lead_update",
        "subcategory": "new_lead",
        "fields": {
            "borrower_name": {"value": "Sarah Williams", "confidence": 0.98},
            "phone": {"value": "(555) 123-4567", "confidence": 0.95},
            "email": {"value": "sarah.williams@email.com", "confidence": 0.99},
            "loan_amount": {"value": "$600,000", "confidence": 0.92},
            "property_type": {"value": "Single Family Home", "confidence": 0.88},
            "desired_location": {"value": "downtown area", "confidence": 0.85}
        }
    },
    {
        "subject": "RE: Martinez Loan - Rate Lock Expiring Soon",
        "sender": "processor@lendingco.com",
        "content": """
REMINDER: Rate Lock Expiration Alert

Borrower: Carlos Martinez
Property: 789 Pine Boulevard
Loan Amount: $280,000
Current Rate: 6.75%
Rate Lock Expires: December 1st (15 days)

Please coordinate with borrower to ensure closing before expiration or discuss extension options.

Loan Processing Team
        """,
        "category": "loan_update",
        "subcategory": "rate_lock_expiring",
        "fields": {
            "borrower_name": {"value": "Carlos Martinez", "confidence": 0.96},
            "property_address": {"value": "789 Pine Boulevard", "confidence": 0.94},
            "loan_amount": {"value": "$280,000", "confidence": 0.97},
            "interest_rate": {"value": "6.75%", "confidence": 0.95},
            "rate_lock_expiry": {"value": "December 1st", "confidence": 0.90},
            "days_remaining": {"value": "15 days", "confidence": 0.88}
        }
    },
    {
        "subject": "Thompson Family - Clear to Close!",
        "sender": "underwriting@mortgage.com",
        "content": """
GREAT NEWS!

The Thompson loan has been cleared to close!

Borrower: Michael & Jennifer Thompson
Property: 321 Birch Lane
Loan Amount: $525,000
Closing Date: November 20th
Final Approval: APPROVED

All conditions have been satisfied. Congratulations!

Underwriting Department
        """,
        "category": "loan_update",
        "subcategory": "clear_to_close",
        "fields": {
            "borrower_name": {"value": "Michael & Jennifer Thompson", "confidence": 0.97},
            "property_address": {"value": "321 Birch Lane", "confidence": 0.95},
            "loan_amount": {"value": "$525,000", "confidence": 0.98},
            "closing_date": {"value": "November 20th", "confidence": 0.92},
            "status": {"value": "Clear to Close", "confidence": 0.99}
        }
    }
]

try:
    # Get user ID (assuming user 4 from logs)
    result = db.execute(text("SELECT id FROM users WHERE email = 'tloss@cmgfi.com' OR email = 'crmemail@homemortgagecomparison.com' LIMIT 1"))
    user_row = result.fetchone()
    if not user_row:
        print("❌ No user found - please check database")
        sys.exit(1)

    user_id = user_row[0]
    print(f"✅ Using user ID: {user_id}")
    print()

    created_tasks = []

    for idx, email in enumerate(sample_emails, 1):
        print(f"📬 Creating task {idx}/5: {email['subject'][:50]}...")

        # Create incoming data event (email)
        result = db.execute(text("""
            INSERT INTO incoming_data_events
            (source, external_message_id, raw_text, subject, sender, received_at, user_id, processed, created_at)
            VALUES
            (:source, :msg_id, :content, :subject, :sender, :received_at, :user_id, :processed, :created_at)
            RETURNING id
        """), {
            "source": "microsoft365",
            "msg_id": f"sample_task_{idx}_{datetime.now().timestamp()}",
            "content": email["content"],
            "subject": email["subject"],
            "sender": email["sender"],
            "received_at": datetime.now(timezone.utc),
            "user_id": user_id,
            "processed": True,
            "created_at": datetime.now(timezone.utc)
        })

        event_id = result.fetchone()[0]
        print(f"   ✅ Created email event ID: {event_id}")

        # Calculate average confidence
        confidences = [field["confidence"] for field in email["fields"].values()]
        avg_confidence = sum(confidences) / len(confidences)

        # Create extracted data (reconciliation item)
        result = db.execute(text("""
            INSERT INTO extracted_data
            (event_id, category, subcategory, fields, ai_confidence, status, created_at)
            VALUES
            (:event_id, :category, :subcategory, :fields::jsonb, :confidence, :status, :created_at)
            RETURNING id
        """), {
            "event_id": event_id,
            "category": email["category"],
            "subcategory": email["subcategory"],
            "fields": str(email["fields"]).replace("'", '"'),  # Convert to JSON
            "confidence": avg_confidence,
            "status": "pending_review",
            "created_at": datetime.now(timezone.utc)
        })

        extracted_id = result.fetchone()[0]
        print(f"   ✅ Created reconciliation task ID: {extracted_id}")
        print(f"   📊 Confidence: {avg_confidence:.0%} | Status: pending_review")
        print()

        created_tasks.append({
            "event_id": event_id,
            "extracted_id": extracted_id,
            "subject": email["subject"],
            "category": email["category"]
        })

    db.commit()

    print("=" * 70)
    print("✅ SUCCESS! Created 5 reconciliation tasks")
    print("=" * 70)
    print()
    print("📋 Summary:")
    for idx, task in enumerate(created_tasks, 1):
        print(f"{idx}. {task['subject'][:60]}")
        print(f"   Event ID: {task['event_id']} | Extract ID: {task['extracted_id']} | Category: {task['category']}")

    print()
    print("=" * 70)
    print("🎯 NEXT STEP: Open your CRM → Reconciliation tab")
    print("   You should see 5 new tasks ready for review!")
    print("=" * 70)

except Exception as e:
    db.rollback()
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    db.close()
