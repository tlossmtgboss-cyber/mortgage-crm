#!/usr/bin/env python3
"""
Test script to generate hallucination tracking data.
Runs the hallucination verifier on sample AI responses and records metrics.
"""

import asyncio
import os
import sys

# Use production database — requires PROD_DATABASE_URL or DATABASE_URL to be set
_db_url = os.getenv("PROD_DATABASE_URL") or os.getenv("DATABASE_URL")
if not _db_url:
    print("ERROR: Set PROD_DATABASE_URL or DATABASE_URL environment variable")
    sys.exit(1)
os.environ["DATABASE_URL"] = _db_url

from datetime import datetime
from database import SessionLocal
from agents.hallucination_verifier import get_hallucination_verifier
from agents.metrics.service import AIMetricsService


async def test_hallucination_verification():
    """Test hallucination verification with sample data."""

    print("=" * 60)
    print("HALLUCINATION TRACKING TEST")
    print("=" * 60)

    verifier = get_hallucination_verifier()
    db = SessionLocal()

    # Test cases: (response, source_data, expected_result)
    test_cases = [
        # Case 1: Accurate response - should be verified
        {
            "name": "Accurate loan count",
            "response": "You have 5 loans in your pipeline with a total value of $2,500,000.",
            "source_data": {
                "get_pipeline_metrics": {
                    "total_count": 5,
                    "total_volume": 2500000,
                    "total_volume_formatted": "$2,500,000.00"
                }
            },
            "tools_used": ["get_pipeline_metrics"]
        },
        # Case 2: Hallucinated numbers - should be contradicted
        {
            "name": "Wrong loan count (hallucination)",
            "response": "Your pipeline shows 12 active loans worth $5,000,000 in total volume.",
            "source_data": {
                "get_pipeline_metrics": {
                    "total_count": 5,
                    "total_volume": 2500000,
                    "total_volume_formatted": "$2,500,000.00"
                }
            },
            "tools_used": ["get_pipeline_metrics"]
        },
        # Case 3: Accurate dates
        {
            "name": "Accurate closing date",
            "response": "The loan for John Smith is scheduled to close on December 28, 2025.",
            "source_data": {
                "get_loan_details": {
                    "borrower_name": "John Smith",
                    "expected_close_date": "2025-12-28",
                    "loan_amount": 450000
                }
            },
            "tools_used": ["get_loan_details"]
        },
        # Case 4: Wrong status (hallucination)
        {
            "name": "Wrong loan status (hallucination)",
            "response": "The loan is currently in underwriting and approved for closing.",
            "source_data": {
                "get_loan_details": {
                    "status": "processing",
                    "approval_date": None
                }
            },
            "tools_used": ["get_loan_details"]
        },
        # Case 5: Unsupported claim - no source data
        {
            "name": "Unsupported market claim",
            "response": "Interest rates are expected to drop by 0.5% next month based on market trends.",
            "source_data": {},
            "tools_used": []
        },
        # Case 6: Accurate multi-tool response
        {
            "name": "Accurate multi-source response",
            "response": "You have 3 leads pending follow-up and 2 loans closing this week.",
            "source_data": {
                "get_pending_leads": {
                    "count": 3,
                    "leads": [{"name": "Alice"}, {"name": "Bob"}, {"name": "Carol"}]
                },
                "get_loans_closing_soon": {
                    "count": 2,
                    "loans": [{"borrower": "Dave"}, {"borrower": "Eve"}]
                }
            },
            "tools_used": ["get_pending_leads", "get_loans_closing_soon"]
        },
    ]

    results_summary = []

    for i, test in enumerate(test_cases, 1):
        print(f"\n--- Test {i}: {test['name']} ---")
        print(f"Response: {test['response'][:100]}...")

        try:
            # Generate hallucination report
            report = await verifier.generate_report(
                session_id=f"test-session-{i}",
                message_id=f"test-msg-{datetime.now().timestamp()}-{i}",
                response_text=test['response'],
                source_data=test['source_data'],
                tools_used=test['tools_used'],
                use_llm=False  # Use rule-based for testing
            )

            print(f"  Claims extracted: {report.total_claims}")
            print(f"  Verified: {report.verified_claims}")
            print(f"  Unsupported: {report.unsupported_claims}")
            print(f"  Contradicted: {report.contradicted_claims}")
            print(f"  Faithfulness: {report.faithfulness_score:.1%}")
            print(f"  Hallucination rate: {report.hallucination_rate:.1%}")

            # Record to database
            await AIMetricsService.record_hallucination_report(
                db=db,
                user_id=1,
                report=report
            )
            print(f"  [RECORDED TO DATABASE]")

            results_summary.append({
                "name": test['name'],
                "claims": report.total_claims,
                "verified": report.verified_claims,
                "contradicted": report.contradicted_claims,
                "faithfulness": report.faithfulness_score
            })

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

    db.close()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_claims = sum(r['claims'] for r in results_summary)
    total_verified = sum(r['verified'] for r in results_summary)
    total_contradicted = sum(r['contradicted'] for r in results_summary)

    print(f"Total test cases: {len(results_summary)}")
    print(f"Total claims: {total_claims}")
    print(f"Verified claims: {total_verified}")
    print(f"Contradicted claims: {total_contradicted}")
    print(f"Average faithfulness: {sum(r['faithfulness'] for r in results_summary) / len(results_summary):.1%}")

    print("\n✅ Hallucination tracking test complete!")
    print("Check the admin panel AI Metrics tab to see the data.")


if __name__ == "__main__":
    asyncio.run(test_hallucination_verification())
