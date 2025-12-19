#!/usr/bin/env python
"""Test Claude integration in production email processing"""
import os
import sys
import asyncio
from dotenv import load_dotenv


async def test_claude_email_processing():
    """Test processing an email with Claude"""
    # Import after env is loaded
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database import Base
    from main import process_microsoft_email_to_dre

    # Create test database
    DATABASE_URL = "sqlite:///./test_claude_integration.db"
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    print("\n" + "="*80)
    print("TESTING CLAUDE INTEGRATION IN PRODUCTION CODE")
    print("="*80)

    # Sample email from Microsoft Graph API format
    test_email = {
        "id": "test-message-123",
        "subject": "Pre-approval inquiry",
        "from": {
            "emailAddress": {
                "address": "john.smith@gmail.com"
            }
        },
        "toRecipients": [
            {
                "emailAddress": {
                    "address": "loan.officer@example.com"
                }
            }
        ],
        "receivedDateTime": "2025-11-16T10:30:00Z",
        "body": {
            "contentType": "text",
            "content": """
Hi,

I'm interested in getting pre-approved for a home loan. My wife Sarah and I
are first-time homebuyers looking at homes in Austin around $500,000.

Some details:
- Annual income: $145,000 (Software Engineer at Google)
- Down payment: $100,000 saved
- Credit score: 780
- Employment: 4 years at current job

Can we schedule a call this week?

Thanks,
John Smith
(512) 555-1234
            """
        }
    }

    # Create test user
    db = SessionLocal()

    try:
        print("\n📧 Processing test email with Claude...")
        print(f"   Subject: {test_email['subject']}")
        print(f"   From: {test_email['from']['emailAddress']['address']}")

        result = await process_microsoft_email_to_dre(
            email_data=test_email,
            user_id=1,
            db=db
        )

        print(f"\n✅ Processing complete!")
        print(f"   Status: {result.get('status')}")
        print(f"   Event ID: {result.get('event_id')}")

        if result.get('status') == 'success':
            print("\n🎉 SUCCESS! Claude is now processing emails in production code!")
            return True
        else:
            print(f"\n⚠️  Result: {result}")
            return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def main():
    # Load environment
    load_dotenv()

    # Verify Claude is configured
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY not set")
        sys.exit(1)

    if os.getenv("AI_PROVIDER", "").lower() != "claude":
        print("❌ AI_PROVIDER not set to 'claude'")
        print(f"   Current value: {os.getenv('AI_PROVIDER')}")
        sys.exit(1)

    print(f"✅ AI_PROVIDER: {os.getenv('AI_PROVIDER')}")
    print(f"✅ ANTHROPIC_API_KEY: {os.getenv('ANTHROPIC_API_KEY')[:20]}...")

    success = asyncio.run(test_claude_email_processing())

    # Cleanup
    if os.path.exists("test_claude_integration.db"):
        os.remove("test_claude_integration.db")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
