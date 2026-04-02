"""
Test Post-Closing Workflow System Locally
Perennia AI - TL Development, LLC

Run: python test_workflow.py
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflows.post_closing_workflow import (
    PostClosingWorkflowEngine,
    WorkflowTrigger,
    LeadWorkflowData,
    calculate_referral_score
)
from database import SessionLocal
from datetime import datetime


def test_workflow():
    """Test the workflow with a sample lead"""
    db = SessionLocal()

    print(f"\n{'='*60}")
    print("POST-CLOSING WORKFLOW TEST")
    print(f"{'='*60}\n")

    # Import models
    from sqlalchemy import text

    # Get first lead
    result = db.execute(text("SELECT id, name, email FROM leads LIMIT 1"))
    lead_row = result.fetchone()

    if not lead_row:
        print("❌ No leads found in database. Please add sample data first.")
        db.close()
        return

    lead_id = lead_row[0]
    lead_name = lead_row[1]

    print(f"Testing with Lead: {lead_name} (ID: {lead_id})\n")

    # Create test lead data with HIGH referral potential
    test_lead = LeadWorkflowData(
        id=lead_id,
        name=lead_name,
        referral_source_score=85,  # HIGH - triggers Ambassador workflow
        leadership_level="Manager",  # Triggers workplace opportunity
        employees_managed=15,  # Has a team
        referral_industry_flag="High",
        company_size=300,  # Strategic employer (>200)
        employer_name="Test Tech Corp",
        industry="Technology"  # High-referral industry
    )

    print("Test Lead Configuration:")
    print(f"  Referral Score: {test_lead.referral_source_score}")
    print(f"  Leadership: {test_lead.leadership_level}")
    print(f"  Manages: {test_lead.employees_managed} employees")
    print(f"  Company: {test_lead.employer_name} ({test_lead.company_size} employees)")
    print(f"  Industry: {test_lead.industry}\n")

    # Create workflow trigger
    trigger = WorkflowTrigger(
        loan_id=1,  # Dummy loan ID
        lead_id=lead_id,
        loan_status="Closed",
        closed_date=datetime.now(timezone.utc),
        loan_officer_id=1
    )

    # Run workflow
    print("Running workflow engine...\n")
    engine = PostClosingWorkflowEngine(db)
    result = asyncio.run(engine.process_loan_closing(trigger, test_lead))

    print(f"\n{'='*60}")
    print(f"RESULTS: {result['action_count']} actions triggered")
    print(f"{'='*60}\n")

    for action in result['actions']:
        workflow = action.get('workflow', '')
        action_type = action.get('action', '')

        if action_type == 'add_tags':
            print(f"✓ [{workflow}] Add tags: {action['tags']}")
        elif action_type == 'create_task':
            print(f"✓ [{workflow}] Create task: {action['title']} (due in {action.get('due_days', '?')} days, {action.get('priority', 'normal')})")
        elif action_type == 'create_employer_record':
            print(f"✓ [{workflow}] Create employer: {action['company_name']}")
        elif action_type == 'create_opportunity':
            print(f"✓ [{workflow}] Create opportunity: {action['type']} at {action['company_name']}")
        elif action_type == 'create_recurring_task':
            print(f"✓ [{workflow}] Create recurring: {action['title']} (every {action['interval_days']} days)")

    # Check workflow_executions table
    print(f"\n{'='*60}")
    print("DATABASE VERIFICATION")
    print(f"{'='*60}\n")

    try:
        exec_result = db.execute(text("""
            SELECT workflow_id, execution_status, executed_at
            FROM workflow_executions
            ORDER BY executed_at DESC
            LIMIT 1
        """))
        execution = exec_result.fetchone()

        if execution:
            print(f"✓ Workflow logged to database:")
            print(f"  ID: {execution[0]}")
            print(f"  Status: {execution[1]}")
            print(f"  Time: {execution[2]}")
        else:
            print("⚠️  No execution logged (this is OK for SQLite)")
    except Exception as e:
        print(f"⚠️  Could not verify execution log: {e}")

    db.close()

    print(f"\n{'='*60}")
    print("✅ WORKFLOW TEST COMPLETE!")
    print(f"{'='*60}\n")

    print("Expected workflows triggered for this test:")
    print("  1. HIGH REFERRAL (score >= 80) → Ambassador Program")
    print("  2. WORKPLACE OPPORTUNITY (manages 15 people)")
    print("  3. HIGH-REFERRAL INDUSTRY (Technology)")
    print("  4. STRATEGIC EMPLOYER (300 employees)")
    print()
    print("Next steps:")
    print("  1. Add workflow trigger to loan update endpoint")
    print("  2. Deploy to Railway")
    print("  3. Test with real loan closure")
    print()


def test_score_calculation():
    """Test the referral score calculation"""
    print(f"\n{'='*60}")
    print("REFERRAL SCORE CALCULATION TEST")
    print(f"{'='*60}\n")

    # Test cases
    test_cases = [
        {
            "name": "Executive at Large Tech Company",
            "data": {"industry": "Technology", "leadership_level": "Executive", "employees_managed": 50, "company_size": 500},
            "expected": "80+"
        },
        {
            "name": "Manager in Real Estate",
            "data": {"industry": "Real Estate", "leadership_level": "Manager", "employees_managed": 10, "company_size": 50},
            "expected": "50-79"
        },
        {
            "name": "Individual Contributor in Retail",
            "data": {"industry": "Retail", "leadership_level": None, "employees_managed": 0, "company_size": 20},
            "expected": "<50"
        }
    ]

    class MockLead:
        pass

    for tc in test_cases:
        lead = MockLead()
        for k, v in tc["data"].items():
            setattr(lead, k, v)

        score = calculate_referral_score(lead)
        status = "✓" if (
            (tc["expected"] == "80+" and score >= 80) or
            (tc["expected"] == "50-79" and 50 <= score < 80) or
            (tc["expected"] == "<50" and score < 50)
        ) else "✗"

        print(f"{status} {tc['name']}")
        print(f"  Score: {score} (expected {tc['expected']})")
        print(f"  Data: {tc['data']}\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "score":
        test_score_calculation()
    else:
        test_workflow()
        print("\nRun 'python test_workflow.py score' to test score calculation")
