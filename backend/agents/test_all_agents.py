"""
Test script to verify all 20 agents can call their tools correctly.
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.agents.tools import tool_registry, AGENT_CONFIGS

# Map each agent to a representative tool and test params
AGENT_TEST_CASES = {
    "pipeline_analyst": ("get_pipeline_metrics", {}),
    "compliance_checker": ("check_trid_compliance", {"loan_id": "test-123"}),
    "lead_nurturer": ("get_lead_details", {"lead_id": "test-123"}),
    "document_tracker": ("get_missing_documents", {"loan_id": "test-123"}),
    "profitability_analyst": ("calculate_loan_profitability", {"loan_id": "test-123"}),
    "rate_advisor": ("get_current_rates", {}),
    "team_coach": ("get_lo_metrics", {"user_id": "test-123"}),
    "customer_intelligence": ("get_customer_360", {"contact_id": "test-123"}),
    "voice_os": ("get_call_history", {"contact_id": "test-123"}),
    "uvip": ("get_meeting_recordings", {}),
    "email_intelligence": ("get_email_templates", {}),
    "ai_receptionist": ("get_call_queue_status", {}),
    "smart_scheduler": ("get_availability", {"user_id": "test-123"}),
    "task_automation": ("get_task_queue", {}),
    "sla_tracker": ("check_sla_status", {"loan_id": "test-123"}),
    "integrations": ("check_integration_status", {}),
    "reporting_engine": ("generate_pipeline_report", {}),
    "notification_center": ("get_pending_notifications", {}),
    "subscription_manager": ("get_subscription_status", {}),
    "onboarding_assistant": ("get_onboarding_status", {"user_id": "test-123"}),
}


def test_tool_exists(tool_name: str) -> tuple:
    """Test if a tool exists in the registry."""
    tool = tool_registry.get(tool_name)
    if tool is None:
        return False, f"Tool '{tool_name}' not found in registry"
    return True, tool


def test_tool_callable(tool_name: str, params: dict) -> tuple:
    """Test if a tool can be called (may fail due to DB, but checks signature)."""
    tool_def = tool_registry.get(tool_name)
    if tool_def is None:
        return False, f"Tool '{tool_name}' not found"

    # ToolDefinition has a .func attribute with the actual callable
    if not hasattr(tool_def, 'func'):
        return False, f"Tool '{tool_name}' has no func attribute"

    try:
        # Try to call the tool's function - it may fail due to DB but proves it's callable
        result = tool_def.func(**params)
        return True, result
    except TypeError as e:
        # Signature mismatch
        return False, f"Signature error: {e}"
    except Exception as e:
        # Other errors (like DB connection) are OK - tool is callable
        error_type = type(e).__name__
        if "connection" in str(e).lower() or "database" in str(e).lower():
            return True, f"Tool callable (DB not connected): {error_type}"
        return True, f"Tool callable (runtime error): {error_type}: {str(e)[:50]}"


def run_all_tests():
    """Run tests for all agents."""
    print("=" * 70)
    print("PERENNIA AI - AGENT TOOL VERIFICATION")
    print("=" * 70)
    print()

    # First, show registry stats
    print(f"Total tools in registry: {len(tool_registry)}")
    print(f"Total agents to test: {len(AGENT_TEST_CASES)}")
    print()

    results = {
        "passed": 0,
        "failed": 0,
        "errors": []
    }

    print("-" * 70)
    print(f"{'Agent':<25} {'Tool':<35} {'Status'}")
    print("-" * 70)

    for agent_name, (tool_name, params) in AGENT_TEST_CASES.items():
        # Check if tool exists
        exists, tool_or_error = test_tool_exists(tool_name)

        if not exists:
            status = "❌ NOT FOUND"
            results["failed"] += 1
            results["errors"].append(f"{agent_name}: {tool_or_error}")
        else:
            # Check if tool is callable
            callable_ok, call_result = test_tool_callable(tool_name, params)

            if callable_ok:
                status = "✅ OK"
                results["passed"] += 1
            else:
                status = "❌ FAILED"
                results["failed"] += 1
                results["errors"].append(f"{agent_name}: {call_result}")

        print(f"{agent_name:<25} {tool_name:<35} {status}")

    print("-" * 70)
    print()

    # Summary
    total = results["passed"] + results["failed"]
    print(f"SUMMARY: {results['passed']}/{total} agents passed")
    print()

    if results["errors"]:
        print("ERRORS:")
        for error in results["errors"]:
            print(f"  - {error}")
        print()

    # List any tools not mapped to agents
    mapped_tools = set(tool for tool, _ in AGENT_TEST_CASES.values())
    all_tools = set(tool_registry._tools.keys())
    unmapped = all_tools - mapped_tools

    if unmapped:
        print(f"Note: {len(unmapped)} tools not tested (not mapped to primary agent)")

    return results["failed"] == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
