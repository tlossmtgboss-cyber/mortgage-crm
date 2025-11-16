#!/usr/bin/env python
"""Simple test to verify Claude is being called in production code"""
import os
import sys
import asyncio
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Verify Claude is configured
ai_provider = os.getenv("AI_PROVIDER", "").lower()
anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

print("="*80)
print("CLAUDE PRODUCTION CODE TEST")
print("="*80)

print(f"\n✅ AI_PROVIDER: {ai_provider}")
print(f"✅ ANTHROPIC_API_KEY: {'SET (' + anthropic_key[:20] + '...)' if anthropic_key else 'NOT SET'}")

if ai_provider != "claude":
    print(f"\n❌ AI_PROVIDER is '{ai_provider}', should be 'claude'")
    sys.exit(1)

if not anthropic_key:
    print("\n❌ ANTHROPIC_API_KEY not set")
    sys.exit(1)

# Import the Claude parser
try:
    from ai_providers.claude_parser import get_claude_parser
    print("\n✅ Claude parser module imported successfully")
except Exception as e:
    print(f"\n❌ Failed to import Claude parser: {e}")
    sys.exit(1)


async def test_claude_parsing():
    """Test that Claude parser works"""

    print("\n" + "-"*80)
    print("Testing Claude API call...")
    print("-"*80)

    # Sample email
    test_email = {
        "id": "test-123",
        "subject": "Pre-approval inquiry",
        "from_email": "john.smith@gmail.com",
        "body_text": """
Hi, I'm interested in getting pre-approved for a home loan.

Details:
- Annual income: $145,000
- Credit score: 780
- Down payment: $100,000

Thanks,
John Smith
(512) 555-1234
        """
    }

    try:
        parser = get_claude_parser()
        print(f"✅ Parser initialized: {parser.model}")

        # Classify
        print("\n🔍 Classifying email...")
        profile_type = parser.classify_email(test_email)
        print(f"✅ Classification: {profile_type}")

        # Parse
        print("\n🤖 Parsing with Claude...")
        result = await parser.parse_email(test_email, profile_type, None)

        print(f"\n✅ Parsing complete!")
        print(f"   Fields extracted: {result.get('field_count', 0)}")
        print(f"   Confidence: {result.get('overall_confidence', 0):.1f}%")
        print(f"   Processing time: {result.get('extraction_metadata', {}).get('processing_time_ms', 0)}ms")

        # Show some fields
        fields = result.get('extracted_fields', {})
        if fields:
            print(f"\n📝 Sample extracted fields:")
            for i, (key, value) in enumerate(list(fields.items())[:5]):
                print(f"   • {key}: {value}")

        print("\n" + "="*80)
        print("🎉 SUCCESS! Claude is working in production code!")
        print("="*80)
        print("\n💡 The updated process_microsoft_email_to_dre() function will use this Claude parser when AI_PROVIDER=claude")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_claude_parsing())
    sys.exit(0 if success else 1)
