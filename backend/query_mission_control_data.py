#!/usr/bin/env python3
"""
Query Mission Control Production Data
"""
import os
import sys
from sqlalchemy import create_engine, text
from datetime import datetime

PROD_DB_URL = os.getenv("PROD_DATABASE_URL")

if not PROD_DB_URL:
    print("❌ Error: PROD_DATABASE_URL environment variable not set")
    print("Set it with: export PROD_DATABASE_URL='your_database_url'")
    sys.exit(1)

engine = create_engine(PROD_DB_URL)

print("="*70)
print("MISSION CONTROL DATA QUERY")
print("="*70)
print()

try:
    with engine.connect() as conn:
        # Query 1: Recent Actions
        print("RECENT AI ACTIONS (Last 10):")
        print("-" * 70)
        result = conn.execute(text("""
            SELECT
                agent_name,
                action_type,
                outcome,
                confidence_score,
                created_at
            FROM ai_colleague_actions
            ORDER BY created_at DESC
            LIMIT 10
        """))

        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"{row[0]:20} | {row[1]:25} | {row[2]:10} | {row[3] if row[3] else 0:.2f} | {row[4]}")
        else:
            print("  No data yet")

        print()

        # Query 2: Agent Performance Summary
        print("AGENT PERFORMANCE SUMMARY (Last 7 Days):")
        print("-" * 70)
        result = conn.execute(text("""
            SELECT
                agent_name,
                COUNT(*) as total_actions,
                COUNT(*) FILTER (WHERE outcome = 'success') as successful,
                AVG(confidence_score) as avg_confidence,
                AVG(impact_score) as avg_impact
            FROM ai_colleague_actions
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY agent_name
            ORDER BY total_actions DESC
        """))

        rows = result.fetchall()
        if rows:
            for row in rows:
                success_rate = (row[2] / row[1] * 100) if row[1] > 0 else 0
                print(f"{row[0]:25} | {row[1]:5} actions | {success_rate:5.1f}% success | {row[3] if row[3] else 0:.2f} conf | {row[4] if row[4] else 0:.2f} impact")
        else:
            print("  No data in last 7 days")

        print()

        # Query 3: Total Statistics
        print("OVERALL STATISTICS:")
        print("-" * 70)
        result = conn.execute(text("""
            SELECT
                COUNT(*) as total_actions,
                COUNT(*) FILTER (WHERE autonomy_level = 'full') as autonomous,
                COUNT(*) FILTER (WHERE outcome = 'success') as successful,
                AVG(confidence_score) as avg_confidence
            FROM ai_colleague_actions
        """))

        row = result.fetchone()
        if row and row[0] > 0:
            auto_pct = (row[1] / row[0] * 100) if row[0] > 0 else 0
            success_pct = (row[2] / row[0] * 100) if row[0] > 0 else 0
            print(f"Total Actions: {row[0]}")
            print(f"Autonomous: {row[1]} ({auto_pct:.1f}%)")
            print(f"Successful: {row[2]} ({success_pct:.1f}%)")
            print(f"Avg Confidence: {row[3] if row[3] else 0:.2f}")
        else:
            print("  No data yet - Mission Control waiting for AI actions!")

        print()
        print("="*70)

except Exception as e:
    print(f"❌ Error querying database: {str(e)}")
    print("\nMake sure:")
    print("1. PROD_DATABASE_URL is set correctly")
    print("2. You have network access to Railway")
    print("3. The database credentials are correct")
    sys.exit(1)
