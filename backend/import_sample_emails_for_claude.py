#!/usr/bin/env python
"""Import sample mortgage emails into demo account and process with Claude"""
import os
import sys
import asyncio
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Import the processing function
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from main import process_microsoft_email_to_dre
from database import get_db

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("❌ DATABASE_URL not set")
    sys.exit(1)

# Sample mortgage emails
SAMPLE_EMAILS = [
    {
        "id": "sample-email-001",
        "subject": "Pre-approval request for Austin home",
        "from": {"emailAddress": {"address": "sarah.martinez@gmail.com"}},
        "toRecipients": [{"emailAddress": {"address": "admin@perenniaai.com"}}],
        "receivedDateTime": "2025-11-16T14:30:00Z",
        "body": {
            "contentType": "text",
            "content": """
Hi,

I'm looking to get pre-approved for a home loan. Here are my details:

Personal Information:
- Name: Sarah Martinez
- Email: sarah.martinez@gmail.com
- Phone: (512) 555-1234
- Current Address: Austin, TX

Financial Information:
- Annual Income: $125,000 (Marketing Manager at Dell)
- Employment: 5 years at current job
- Credit Score: 760
- Down Payment Available: $75,000
- Monthly Debts: $800 (car payment)

Property Information:
- Looking at homes around: $425,000
- Preferred Location: North Austin
- Property Type: Single Family Home
- Timeline: Want to close in 60 days

Please let me know what documentation you need!

Thanks,
Sarah Martinez
            """
        }
    },
    {
        "id": "sample-email-002",
        "subject": "Rate lock expiring soon - Loan #98765432",
        "from": {"emailAddress": {"address": "processor@lendco.com"}},
        "toRecipients": [{"emailAddress": {"address": "admin@perenniaai.com"}}],
        "receivedDateTime": "2025-11-16T15:00:00Z",
        "body": {
            "contentType": "text",
            "content": """
Hi,

This is a reminder that the rate lock for loan #98765432 is expiring on 11/25/2025.

Loan Details:
- Borrower: Michael Chen
- Loan Amount: $380,000
- Interest Rate: 6.25%
- Property: 123 Oak Street, Dallas, TX 75201
- Appraised Value: $425,000
- Loan Program: Conventional 30-year fixed
- Lock Date: 10/26/2025
- Lock Expiration: 11/25/2025

Current Status:
- Appraisal: ✅ Complete
- Title: ✅ Received
- Underwriting: In Progress
- Estimated Closing: 11/22/2025

Please coordinate with the title company for final closing details.

Best regards,
Lisa Johnson
Senior Loan Processor
LendCo Mortgage
            """
        }
    },
    {
        "id": "sample-email-003",
        "subject": "Refinance inquiry",
        "from": {"emailAddress": {"address": "robert.williams@email.com"}},
        "toRecipients": [{"emailAddress": {"address": "admin@perenniaai.com"}}],
        "receivedDateTime": "2025-11-16T16:30:00Z",
        "body": {
            "contentType": "text",
            "content": """
Hello,

I closed on my home loan with you back in March 2024 (Loan #12345678).
With rates dropping, I'm interested in exploring refinancing options.

Current Loan Info:
- Original Loan Amount: $400,000
- Current Balance: $385,000
- Current Rate: 7.25%
- Monthly Payment: $2,850
- Property Value: $500,000 (estimated)
- Property Address: 456 Maple Drive, Houston, TX 77002

Financial Situation:
- Credit Score: 785 (improved since original loan)
- Annual Income: $145,000
- No other debts

Questions:
1. What rates are you seeing for refinances right now?
2. Would it make sense to cash out some equity?
3. What's the typical timeline?

Also, I referred my coworker Tom to you - he's looking to buy his first home.

Thanks!
Robert Williams
robert.williams@email.com
(214) 555-9876
            """
        }
    },
    {
        "id": "sample-email-004",
        "subject": "First-time homebuyer - need guidance",
        "from": {"emailAddress": {"address": "jessica.taylor@yahoo.com"}},
        "toRecipients": [{"emailAddress": {"address": "admin@perenniaai.com"}}],
        "receivedDateTime": "2025-11-16T17:15:00Z",
        "body": {
            "contentType": "text",
            "content": """
Hi there,

I'm a first-time homebuyer and feeling a bit overwhelmed. A friend recommended
you as a great loan officer who really helps people through the process.

About Me:
- Name: Jessica Taylor
- Age: 28
- Job: Software Engineer at Apple (3 years)
- Income: $165,000/year
- Savings: $95,000
- Credit Score: 795
- No debt (paid off student loans last year!)

What I'm Looking For:
- Budget: $550,000 - $600,000
- Location: San Francisco Bay Area
- Property: Condo or townhouse
- Timeline: No rush, want to do this right

Questions:
1. How much can I realistically afford?
2. What kind of down payment do I need?
3. Are there any first-time buyer programs?
4. What's the difference between pre-qualified and pre-approved?
5. How long does the whole process take?

I'd love to schedule a call to discuss!

Thank you,
Jessica Taylor
jessica.taylor@yahoo.com
(415) 555-3344
            """
        }
    },
    {
        "id": "sample-email-005",
        "subject": "Clear to Close - Loan #55566677",
        "from": {"emailAddress": {"address": "underwriting@nationalmtg.com"}},
        "toRecipients": [{"emailAddress": {"address": "admin@perenniaai.com"}}],
        "receivedDateTime": "2025-11-16T18:00:00Z",
        "body": {
            "contentType": "text",
            "content": """
CLEAR TO CLOSE - URGENT

Loan Number: 55566677
Borrower: Amanda Rodriguez
Property: 789 Pine Avenue, Phoenix, AZ 85001
Loan Amount: $315,000
Program: FHA 30-year fixed
Rate: 5.875%
APR: 6.125%

MILESTONE UPDATES:
✅ Appraisal completed: 11/10/2025 ($340,000)
✅ Title received: 11/12/2025
✅ Conditional approval: 11/14/2025
✅ Conditions cleared: 11/15/2025
✅ CLEAR TO CLOSE: 11/16/2025

CLOSING DETAILS:
- Closing Date: November 22, 2025 at 2:00 PM
- Closing Disclosure sent: 11/13/2025
- CD signed by borrower: 11/14/2025
- Title Company: First American Title
- Title Contact: John Smith (602) 555-7890
- Cash to Close: $24,850

NEXT STEPS:
1. Confirm final walkthrough with buyer (scheduled 11/21)
2. Coordinate wire instructions with title
3. Verify homeowners insurance is in place
4. Confirm all parties for closing

Please call me to coordinate final details.

Best,
Mark Anderson
Senior Underwriter
National Mortgage Company
(800) 555-0000 ext. 4567
            """
        }
    }
]

print("="*80)
print("IMPORTING SAMPLE EMAILS INTO DEMO ACCOUNT")
print("="*80)

engine = create_engine(database_url)
SessionLocal = sessionmaker(bind=engine)

async def import_and_process():
    """Import sample emails and process with Claude"""

    # Get demo user ID
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, email
            FROM users
            WHERE email = 'admin@perenniaai.com'
            LIMIT 1
        """))
        user = result.fetchone()

        if not user:
            print("\n❌ Demo user not found")
            return False

        demo_user_id = user[0]
        print(f"\n✅ Demo user found: {user[1]} (ID: {demo_user_id})")

    print(f"\n📧 Importing {len(SAMPLE_EMAILS)} sample emails...")

    db = SessionLocal()
    results = []

    try:
        for i, email_data in enumerate(SAMPLE_EMAILS, 1):
            print(f"\n{'='*80}")
            print(f"Processing Email {i}/{len(SAMPLE_EMAILS)}")
            print(f"{'='*80}")
            print(f"From: {email_data['from']['emailAddress']['address']}")
            print(f"Subject: {email_data['subject']}")

            # Process with Claude
            result = await process_microsoft_email_to_dre(
                email_data,
                demo_user_id,
                db
            )

            results.append(result)

            if result.get('status') == 'success':
                print(f"✅ Processed successfully (Event ID: {result.get('event_id')})")
            elif result.get('status') == 'skipped':
                print(f"⏭️  Skipped: {result.get('reason')}")
            else:
                print(f"❌ Error: {result.get('error')}")

        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")

        success_count = sum(1 for r in results if r.get('status') == 'success')
        skipped_count = sum(1 for r in results if r.get('status') == 'skipped')
        error_count = sum(1 for r in results if r.get('status') == 'error')

        print(f"\n📊 Results:")
        print(f"   ✅ Successfully processed: {success_count}")
        print(f"   ⏭️  Skipped (duplicates): {skipped_count}")
        print(f"   ❌ Errors: {error_count}")

        if success_count > 0:
            print(f"\n🎉 SUCCESS! Claude processed {success_count} emails!")
            print(f"\n💡 Check Railway logs to see Claude in action:")
            print(f"   railway logs --tail 100 | grep -E '🤖|Claude|demo'")
            print(f"\n💡 View in CRM:")
            print(f"   1. Log into demo account")
            print(f"   2. Go to Data Reconciliation page")
            print(f"   3. See Claude's field extractions with 97-99% confidence!")

        return success_count > 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = asyncio.run(import_and_process())
    sys.exit(0 if success else 1)
