"""
Test Claude Parser
Quick test script to verify Claude parser is working correctly

Run with: python backend/test_claude_parser.py
"""

import os
import sys
import json
import asyncio
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_providers.claude_parser import get_claude_parser
from tests.sample_emails import ALL_SAMPLE_EMAILS


async def test_parser():
    """Test Claude parser with all sample emails"""

    print("=" * 80)
    print("CLAUDE PARSER TEST")
    print("=" * 80)

    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n❌ ERROR: ANTHROPIC_API_KEY not set in environment")
        print("   Please set your Anthropic API key:")
        print("   export ANTHROPIC_API_KEY='your-key-here'")
        return False

    try:
        # Initialize parser
        print("\n1️⃣  Initializing Claude parser...")
        parser = get_claude_parser()
        print(f"   ✅ Parser initialized with model: {parser.model}")

        # Test each profile type
        for profile_type, email_data in ALL_SAMPLE_EMAILS.items():
            print(f"\n{'='*80}")
            print(f"2️⃣  Testing {profile_type.upper()} email")
            print(f"{'='*80}")

            print(f"\n   Subject: {email_data['subject']}")
            print(f"   From: {email_data['from_email']}")

            start_time = datetime.utcnow()

            # Parse email
            print(f"\n   ⏳ Calling Claude API...")
            result = await parser.parse_email(
                email_data,
                profile_type,
                current_profile=None
            )

            processing_time = (datetime.utcnow() - start_time).total_seconds()

            # Display results
            print(f"\n   ✅ Parsing complete in {processing_time:.2f}s")
            print(f"\n   📊 RESULTS:")
            print(f"      Fields extracted: {result.get('field_count', 0)}")
            print(f"      Overall confidence: {result.get('overall_confidence', 0):.1f}%")
            print(f"      Processing time: {result.get('extraction_metadata', {}).get('processing_time_ms', 0)}ms")

            # Show extracted fields
            extracted = result.get('extracted_fields', {})
            if extracted:
                print(f"\n   📝 EXTRACTED FIELDS:")
                for field, value in list(extracted.items())[:10]:  # Show first 10
                    confidence = result.get('confidence_scores', {}).get(field, 0)
                    print(f"      • {field}: {value} (confidence: {confidence}%)")

                if len(extracted) > 10:
                    print(f"      ... and {len(extracted) - 10} more fields")

            # Show AI analysis
            print(f"\n   🤖 AI ANALYSIS:")
            print(f"      Summary: {result.get('email_summary', 'N/A')}")
            print(f"      Sentiment: {result.get('sentiment', 'N/A')}")
            print(f"      Urgency: {result.get('urgency_score', 0)}/100")

            if next_action := result.get('next_best_action'):
                print(f"      Next action: {next_action}")

            # Show milestones (if any)
            milestones = result.get('milestone_triggers', [])
            if milestones:
                print(f"\n   🎯 MILESTONES DETECTED:")
                for milestone in milestones:
                    print(f"      • {milestone.get('milestone')}: {milestone.get('date')}")

            # Show conflicts (if any)
            conflicts = result.get('conflicts', [])
            if conflicts:
                print(f"\n   ⚠️  CONFLICTS:")
                for conflict in conflicts:
                    print(f"      • {conflict.get('field')}: {conflict.get('reason')}")

            # Save full result to file
            output_file = f"test_results_{profile_type}.json"
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"\n   💾 Full results saved to: {output_file}")

        print(f"\n{'='*80}")
        print("✅ ALL TESTS PASSED")
        print(f"{'='*80}")
        print("\n💡 Next steps:")
        print("   1. Review the test_results_*.json files")
        print("   2. Run the database migration: python backend/migrations/001_create_comprehensive_profiles.py")
        print("   3. Test end-to-end with: python backend/test_email_processing.py")

        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_parser())
    sys.exit(0 if success else 1)
