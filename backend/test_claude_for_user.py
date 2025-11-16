#!/usr/bin/env python
"""Test Claude email processing simulating tloss@cmgfi.com account"""
import os
import sys
import asyncio
from dotenv import load_dotenv
from datetime import datetime

# Load Railway environment
load_dotenv()

print("="*80)
print("TESTING CLAUDE FOR tloss@cmgfi.com")
print("="*80)

# Verify environment
ai_provider = os.getenv("AI_PROVIDER", "").lower()
anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

print(f"\n📋 Environment Check:")
print(f"   AI_PROVIDER: {ai_provider}")
print(f"   ANTHROPIC_API_KEY: {'✅ SET' if anthropic_key else '❌ NOT SET'}")

if ai_provider != "claude":
    print(f"\n❌ AI_PROVIDER should be 'claude', got '{ai_provider}'")
    sys.exit(1)

if not anthropic_key:
    print(f"\n❌ ANTHROPIC_API_KEY not set")
    sys.exit(1)

# Import after env is loaded
from ai_providers.claude_parser import get_claude_parser

async def test_claude_email_processing():
    """Simulate processing an email for tloss@cmgfi.com"""

    print(f"\n" + "="*80)
    print("SIMULATING EMAIL PROCESSING")
    print("="*80)

    # Sample email in Microsoft Graph API format
    # This simulates an email received by tloss@cmgfi.com
    test_email = {
        "id": "test-msg-" + datetime.now().strftime("%Y%m%d%H%M%S"),
        "subject": "Pre-approval request - Johnson family",
        "from": {
            "emailAddress": {
                "address": "sarah.johnson@gmail.com"
            }
        },
        "toRecipients": [
            {
                "emailAddress": {
                    "address": "tloss@cmgfi.com"
                }
            }
        ],
        "receivedDateTime": datetime.now().isoformat() + "Z",
        "body": {
            "contentType": "text",
            "content": """
Hi Tim,

I was referred to you by Mark Stevens. My husband and I are looking to get
pre-approved for our first home purchase here in Austin.

Here are our details:

BORROWER INFO:
- Name: Sarah Johnson
- Phone: (512) 555-7890
- Email: sarah.johnson@gmail.com
- Annual Income: $95,000 (Marketing Manager at Dell)
- Employment: 6 years at current job

CO-BORROWER:
- Name: Michael Johnson
- Annual Income: $78,000 (Teacher)
- Employment: 8 years

FINANCIAL INFO:
- Combined annual income: $173,000
- Credit score: 765 (Sarah), 742 (Michael)
- Down payment available: $85,000
- Looking at homes around: $450,000
- Preferred loan type: Conventional 30-year fixed

We're hoping to close within 60 days if possible. When would be a good time
to discuss our options?

Thanks!
Sarah Johnson
            """
        }
    }

    print(f"\n📧 Email Details:")
    print(f"   To: tloss@cmgfi.com")
    print(f"   From: {test_email['from']['emailAddress']['address']}")
    print(f"   Subject: {test_email['subject']}")
    print(f"   Received: {test_email['receivedDateTime']}")

    # Format email data for Claude parser
    claude_email = {
        "id": test_email["id"],
        "subject": test_email["subject"],
        "from_email": test_email["from"]["emailAddress"]["address"],
        "body_text": test_email["body"]["content"],
        "received_at": test_email["receivedDateTime"]
    }

    try:
        # Initialize Claude parser
        print(f"\n🤖 Initializing Claude parser...")
        parser = get_claude_parser()
        print(f"   ✅ Parser: {parser.model}")

        # Classify email
        print(f"\n1️⃣  Classifying email...")
        start_time = datetime.now()
        profile_type = parser.classify_email(claude_email)
        classify_time = (datetime.now() - start_time).total_seconds()
        print(f"   ✅ Classification: {profile_type} ({classify_time:.2f}s)")

        # Parse with Claude
        print(f"\n2️⃣  Parsing email with Claude AI...")
        start_time = datetime.now()
        result = await parser.parse_email(
            claude_email,
            profile_type,
            current_profile=None
        )
        parse_time = (datetime.now() - start_time).total_seconds()

        print(f"   ✅ Parsing complete! ({parse_time:.2f}s)")

        # Display results
        print(f"\n" + "="*80)
        print("CLAUDE EXTRACTION RESULTS")
        print("="*80)

        print(f"\n📊 Statistics:")
        print(f"   Fields extracted: {result.get('field_count', 0)}")
        print(f"   Overall confidence: {result.get('overall_confidence', 0):.1f}%")
        print(f"   Processing time: {result.get('extraction_metadata', {}).get('processing_time_ms', 0)}ms")

        # Show extracted fields
        fields = result.get('extracted_fields', {})
        if fields:
            print(f"\n📝 Extracted Fields:")
            for i, (key, value) in enumerate(fields.items(), 1):
                confidence = result.get('confidence_scores', {}).get(key, 0)
                # Format value nicely
                if isinstance(value, (int, float)):
                    display_value = f"{value:,}" if isinstance(value, int) else f"{value:.2f}"
                else:
                    display_value = str(value)[:60]
                print(f"   {i:2d}. {key:30s}: {display_value:40s} ({confidence}% confident)")

        # Show AI analysis
        print(f"\n🤖 AI Analysis:")
        print(f"   Summary: {result.get('email_summary', 'N/A')}")
        print(f"   Sentiment: {result.get('sentiment', 'N/A')}")
        print(f"   Urgency: {result.get('urgency_score', 0)}/100")

        if next_action := result.get('next_best_action'):
            print(f"   Recommended action: {next_action}")

        # Show milestones
        milestones = result.get('milestone_triggers', [])
        if milestones:
            print(f"\n🎯 Milestones Detected:")
            for milestone in milestones:
                print(f"   • {milestone.get('milestone')}: {milestone.get('date')}")

        # Show confidence mapping for DRE
        avg_confidence = result.get('overall_confidence', 0) / 100.0
        print(f"\n📋 DRE Integration:")
        print(f"   Profile type: {profile_type}")
        print(f"   Avg confidence: {avg_confidence:.3f}")

        if avg_confidence > 0.85:
            status = "auto_approved"
        elif avg_confidence >= 0.60:
            status = "pending_review"
        else:
            status = "needs_review"

        print(f"   Status: {status}")

        print(f"\n" + "="*80)
        print("✅ SUCCESS! CLAUDE IS WORKING FOR tloss@cmgfi.com")
        print("="*80)

        print(f"\n💡 What happens in production:")
        print(f"   1. Email arrives to tloss@cmgfi.com inbox")
        print(f"   2. Microsoft 365 auto-sync fetches email (every 5 min)")
        print(f"   3. process_microsoft_email_to_dre() is called")
        print(f"   4. Claude classifies: '{profile_type}'")
        print(f"   5. Claude extracts {result.get('field_count', 0)} fields with {result.get('overall_confidence', 0):.1f}% confidence")
        print(f"   6. Email stored as '{status}' in Data Reconciliation Engine")
        print(f"   7. User can review in CRM dashboard")

        print(f"\n🎉 Claude is ready to process emails for your account!")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_claude_email_processing())
    sys.exit(0 if success else 1)
