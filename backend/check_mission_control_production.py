#!/usr/bin/env python3
"""
Check Mission Control Production Data
Quick verification script
"""
import os
import sys

# Production database URL
PROD_DB_URL = os.getenv("PROD_DATABASE_URL")

if not PROD_DB_URL:
    print("⚠️  Set PROD_DATABASE_URL environment variable:")
    print('export PROD_DATABASE_URL="postgresql://..."')
    sys.exit(1)

from sqlalchemy import create_engine, text

print("="*70)
print("MISSION CONTROL PRODUCTION DATA CHECK")
print("="*70)
print()

try:
    engine = create_engine(PROD_DB_URL)

    with engine.connect() as conn:
        # Check what's actually in the database
        print("📊 AI Actions Summary:")
        print("-" * 70)

        result = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE autonomy_level = 'full') as autonomous,
                COUNT(*) FILTER (WHERE outcome = 'success') as successful,
                COUNT(*) FILTER (WHERE outcome = 'failure') as failed,
                AVG(confidence_score) as avg_confidence,
                MAX(created_at) as last_action
            FROM ai_colleague_actions
        """))

        row = result.fetchone()

        print(f"Total Actions: {row[0]}")
        print(f"Autonomous: {row[1]}")
        print(f"Successful: {row[2]}")
        print(f"Failed: {row[3]}")
        print(f"Avg Confidence: {row[4]:.2f if row[4] else 'N/A'}")
        print(f"Last Action: {row[5]}")

        print()
        print("📋 Recent Actions (Last 5):")
        print("-" * 70)

        result = conn.execute(text("""
            SELECT
                agent_name,
                action_type,
                outcome,
                confidence_score,
                reasoning,
                created_at
            FROM ai_colleague_actions
            ORDER BY created_at DESC
            LIMIT 5
        """))

        for row in result:
            print(f"\n{row[0]} - {row[1]}")
            print(f"  Outcome: {row[2]}")
            print(f"  Confidence: {row[3] if row[3] else 'N/A'}")
            print(f"  Reasoning: {row[4][:100] if row[4] else 'N/A'}...")
            print(f"  Time: {row[5]}")

        print()
        print("="*70)
        print("✅ Data check complete!")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    sys.exit(1)
