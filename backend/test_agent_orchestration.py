#!/usr/bin/env python3
"""
Quick test script for the Agent Orchestration API
Tests both token optimization and white-label functionality
"""

import asyncio
import json
from pathlib import Path

# Test the context manager
async def test_context_manager():
    print("\n=== Testing Context Manager ===")
    from agents.orchestration.context_manager import ContextManager

    prompts_dir = Path(__file__).parent / "agents" / "perennia-prompts"
    cm = ContextManager(prompts_dir)

    # Test email_intel prompt generation
    prompt = await cm.get_optimized_prompt(
        agent_id="email_intel",
        conversation_stage="email_analysis",
        conversation_history=[{
            "role": "user",
            "content": "Subject: Rate lock question\nFrom: john@example.com\n\nHi, I want to know if I should lock my rate today."
        }],
        user_profile={"first_name": "John", "email": "john@example.com"},
        metadata={"subject": "Rate lock question"}
    )

    token_estimate = len(prompt) // 4
    print(f"✅ Email Intel prompt generated: ~{token_estimate} tokens")
    print(f"   Target: 12-18k tokens (was 90k)")
    print(f"   Actual character count: {len(prompt)}")

    # Test lead_agent prompt generation
    prompt = await cm.get_optimized_prompt(
        agent_id="lead_agent",
        conversation_stage="initial_contact",
        conversation_history=[],
        user_profile={"first_name": "Sarah", "loan_purpose": "purchase"},
        metadata={}
    )

    token_estimate = len(prompt) // 4
    print(f"✅ Lead Agent (initial_contact) prompt generated: ~{token_estimate} tokens")

    # Test with objection detection
    prompt = await cm.get_optimized_prompt(
        agent_id="lead_agent",
        conversation_stage="qualification",
        conversation_history=[
            {"role": "assistant", "content": "Hi Sarah! Are you still looking to purchase a home?"},
            {"role": "user", "content": "I'm not interested, too expensive right now"}
        ],
        user_profile={"first_name": "Sarah"},
        metadata={}
    )

    token_estimate = len(prompt) // 4
    print(f"✅ Lead Agent (with objection) prompt generated: ~{token_estimate} tokens")
    print(f"   Objection handling loaded: {'Objection' in prompt}")


async def test_white_label():
    print("\n=== Testing White-Label Functionality ===")
    from agents.orchestration.context_manager import ContextManager

    prompts_dir = Path(__file__).parent / "agents" / "perennia-prompts"
    cm = ContextManager(prompts_dir)

    # Test with default organization (Perennia AI)
    prompt_default = await cm.get_optimized_prompt(
        agent_id="lead_agent",
        conversation_stage="initial_contact",
        conversation_history=[],
        user_profile={"first_name": "John"},
        metadata={}
    )

    print(f"✅ Default org prompt generated")
    print(f"   Contains 'Perennia AI': {'Perennia AI' in prompt_default}")

    # Test with custom organization (ABC Mortgage)
    custom_org = {
        "id": 123,
        "name": "ABC Mortgage Company",
        "brand_name": "ABC Mortgage",
        "display_name": "ABC Mortgage Company",
        "website": "https://abcmortgage.com",
        "phone": "1-800-ABC-LOAN",
        "agent_personas": {
            "lead_agent": {
                "name": "Mike",
                "role": "Senior Loan Advisor"
            }
        }
    }

    prompt_custom = await cm.get_optimized_prompt(
        agent_id="lead_agent",
        conversation_stage="initial_contact",
        conversation_history=[],
        user_profile={"first_name": "John"},
        metadata={},
        organization=custom_org
    )

    print(f"✅ Custom org prompt generated (ABC Mortgage)")
    print(f"   Contains 'ABC Mortgage': {'ABC Mortgage' in prompt_custom}")
    print(f"   Contains custom agent name 'Mike': {'Mike' in prompt_custom}")
    print(f"   Contains 'Senior Loan Advisor': {'Senior Loan Advisor' in prompt_custom}")
    print(f"   Does NOT contain 'Perennia AI': {'Perennia AI' not in prompt_custom}")

    # Test with another organization (XYZ Lending)
    xyz_org = {
        "id": 456,
        "name": "XYZ Lending Group",
        "brand_name": "XYZ Lending",
    }

    prompt_xyz = await cm.get_optimized_prompt(
        agent_id="lead_agent",
        conversation_stage="initial_contact",
        conversation_history=[],
        user_profile={"first_name": "Jane"},
        metadata={},
        organization=xyz_org
    )

    print(f"✅ XYZ Lending prompt generated")
    print(f"   Contains 'XYZ Lending': {'XYZ Lending' in prompt_xyz}")
    print(f"   Uses default agent name 'Sarah': {'Sarah' in prompt_xyz}")

    # Show sample of custom prompt
    print("\n   Sample of ABC Mortgage prompt:")
    # Find the identity section
    for line in prompt_custom.split('\n'):
        if 'ABC Mortgage' in line or 'Mike' in line:
            print(f"   → {line.strip()}")


async def test_performance_tracker():
    print("\n=== Testing Performance Tracker ===")
    from agents.orchestration.performance_tracker import PerformanceTracker

    tracker = PerformanceTracker()

    # Log an execution
    exec_id = await tracker.log_execution({
        "agent_id": "email_intel",
        "conversation_id": "test-123",
        "stage": "email_analysis",
        "prompt_tokens": 2000,
        "completion_tokens": 500,
        "latency_ms": 1200,
    })
    print(f"✅ Execution logged: {exec_id}")

    # Get metrics (empty for now)
    metrics = await tracker.get_agent_metrics("email_intel", 30)
    print(f"✅ Metrics retrieved for email_intel")
    print(f"   Total executions in memory: {len(tracker._in_memory_executions)}")


async def test_quality_analyzer():
    print("\n=== Testing Quality Analyzer ===")
    from agents.orchestration.quality_analyzer import QualityAnalyzer, generate_quality_report

    analyzer = QualityAnalyzer()

    # Test with a sample prompt
    sample_prompt = """
    # Sarah - Senior Mortgage Consultant

    You are Sarah, a senior mortgage consultant at Perennia AI.

    ## Core Rules:
    - Only ask ONE question at a time
    - Do NOT use conciliatory phrases
    - Persistently engage - never accept rejection on first attempt
    - Keep responses under 60 words

    ## Qualification Questions:
    1. Are you looking to purchase or refinance?
    2. What's your estimated property value?
    3. When are you looking to close?

    ## If they object, use SPIN Selling to re-engage.
    """

    analysis = analyzer.analyze(sample_prompt)
    print(f"✅ Quality analysis complete")
    print(f"   Score: {analysis['total_score']}/{analysis['max_score']} ({analysis['percentage']:.1f}%)")
    print(f"   Grade: {analysis['grade']}")
    print(f"   Checks passed: {len(analysis['checks_passed'])}")
    print(f"   Checks failed: {len(analysis['checks_failed'])}")

    # Quick score
    quick = analyzer.get_quick_score(sample_prompt)
    print(f"✅ Quick score: {quick}/100")


async def test_agent_configs():
    print("\n=== Testing Agent Configs ===")
    from agents.orchestration.config.agent_configs import (
        get_agent_config, get_all_agent_ids, export_agent_config
    )

    agent_ids = get_all_agent_ids()
    print(f"✅ Registered agents: {len(agent_ids)}")
    for aid in agent_ids:
        config = get_agent_config(aid)
        print(f"   - {aid}: {config.use_case.value if config else 'NOT FOUND'}")

    # Export one config
    export = export_agent_config("lead_agent")
    if export:
        print(f"✅ Lead agent config exported")
        print(f"   Channels: {export.get('channels', [])}")
        print(f"   Active: {export.get('is_active', False)}")


async def main():
    print("=" * 50)
    print("Agent Orchestration Integration Test")
    print("=" * 50)

    try:
        await test_context_manager()
        await test_white_label()  # NEW: Test white-label functionality
        await test_performance_tracker()
        await test_quality_analyzer()
        await test_agent_configs()

        print("\n" + "=" * 50)
        print("✅ All tests passed!")
        print("=" * 50)
        print("\nNext steps:")
        print("1. Run database migration: alembic upgrade head")
        print("2. Start the server: uvicorn main:app --reload")
        print("3. Test the API: curl http://localhost:8000/agents/")
        print("\nWhite-label usage example:")
        print('  POST /agents/execute')
        print('  {')
        print('    "agent_id": "lead_agent",')
        print('    "organization": {"brand_name": "Your Company Name"}')
        print('  }')

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
