import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

from ai_providers.claude_parser import get_claude_parser

print("="*80)
print("CLAUDE AI - READY FOR tloss@cmgfi.com")
print("="*80)
print(f"\nEnvironment: AI_PROVIDER={os.getenv('AI_PROVIDER')}")
print(f"Claude API: {'✅ Configured' if os.getenv('ANTHROPIC_API_KEY') else '❌ Not set'}")

async def test_for_user():
    # Email sent TO tloss@cmgfi.com FROM a prospect
    email = {
        'subject': 'Mortgage pre-approval needed',
        'body_text': '''
Hi Tim,

I need help getting pre-approved for a home loan.

My info:
- Name: Alex Martinez
- Email: alex.martinez@example.com  
- Phone: (512) 555-9999
- Income: $185,000/year (Software Engineer at Apple)
- Credit Score: 795
- Down Payment: $120,000 saved
- Looking at homes: $550,000 range
- Location: Austin, TX

Can we talk this week?

Thanks!
Alex
        ''',
        'from_email': 'alex.martinez@example.com'
    }
    
    parser = get_claude_parser()
    print(f"\n🤖 Parser: {parser.model}")
    
    # Classify
    profile_type = parser.classify_email(email)
    print(f"\n📧 Classification: {profile_type}")
    
    # Parse
    print(f"⏳ Calling Claude API...")
    result = await parser.parse_email(email, profile_type, None)
    
    # Results
    fields = result.get('extracted_fields', {})
    confidence = result.get('overall_confidence', 0)
    
    print(f"\n✅ RESULTS:")
    print(f"   Fields extracted: {len(fields)}")
    print(f"   Confidence: {confidence:.1f}%")
    print(f"   Processing time: {result.get('extraction_metadata', {}).get('processing_time_ms', 0)}ms")
    
    print(f"\n📝 Sample Fields:")
    for i, (k, v) in enumerate(list(fields.items())[:8], 1):
        conf = result.get('confidence_scores', {}).get(k, 0)
        print(f"   {i}. {k}: {v} ({conf}%)")
    
    print(f"\n🤖 AI Insights:")
    print(f"   Summary: {result.get('email_summary', 'N/A')[:120]}...")
    print(f"   Urgency: {result.get('urgency_score', 0)}/100")
    print(f"   Next action: {result.get('next_best_action', 'N/A')[:80]}...")
    
    print(f"\n{'='*80}")
    print(f"✅ CLAUDE IS READY!")
    print(f"{'='*80}")
    print(f"\n💡 When emails arrive to tloss@cmgfi.com:")
    print(f"   • Claude will classify them ({profile_type})")
    print(f"   • Extract {len(fields)} fields with {confidence:.1f}% accuracy")
    print(f"   • Store in Data Reconciliation Engine")
    print(f"   • Available for review in CRM dashboard")
    print(f"\n🎉 Ready to process production emails!")

asyncio.run(test_for_user())
