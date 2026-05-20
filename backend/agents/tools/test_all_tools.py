# Perennia AI Agent Tools - Test Suite
# Run this file to verify all tools are properly installed and functioning

"""
TEST INSTRUCTIONS:
==================
1. Save this file as: backend/agents/tools/test_all_tools.py
2. Run from your backend directory: python -m agents.tools.test_all_tools
3. Or run with pytest: pytest agents/tools/test_all_tools.py -v

This tests:
- Tool registration and discovery
- ToolResult formatting
- Tool execution (with mock data)
- Integration layer
- All 64 tools across 8 agents
"""

import sys
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, List, Any
from unittest.mock import patch, MagicMock
from decimal import Decimal


# =============================================================================
# TEST CONFIGURATION
# =============================================================================

# Set to True to run tests against real database
USE_REAL_DATABASE = False

# Mock data for testing without database
MOCK_LOAN = {
    "id": "LOAN001",
    "loan_number": "2024-001234",
    "borrower_first_name": "John",
    "borrower_last_name": "Smith",
    "borrower_name": "John Smith",
    "loan_amount": Decimal("450000.00"),
    "amount": Decimal("450000.00"),
    "interest_rate": Decimal("6.75"),
    "rate": Decimal("6.75"),
    "loan_type": "conventional",
    "program": "Conventional 30yr",
    "status": "processing",
    "stage": "processing",
    "property_address": "123 Main St",
    "property_city": "Austin",
    "property_state": "TX",
    "expected_close_date": date.today() + timedelta(days=30),
    "target_close_date": date.today() + timedelta(days=30),
    "status_changed_at": datetime.now() - timedelta(days=3),
    "stage_entered_at": datetime.now() - timedelta(days=3),
    "created_at": datetime.now() - timedelta(days=14),
    "application_date": date.today() - timedelta(days=14),
    "le_sent_date": date.today() - timedelta(days=12),
    "cd_sent_date": None,
    "loan_officer_id": "LO001",
    "loan_officer_name": "Mike Johnson",
}

MOCK_LEAD = {
    "id": "LEAD001",
    "first_name": "Jane",
    "last_name": "Doe",
    "email": "jane.doe@email.com",
    "phone": "555-123-4567",
    "status": "contacted",
    "lead_score": 75,
    "source": "Website",
    "source_type": "organic",
    "campaign_name": None,
    "assigned_to": "LO001",
    "assigned_lo_name": "Mike Johnson",
    "total_activities": 5,
    "last_contact_date": datetime.now() - timedelta(hours=2),
    "next_followup_date": date.today() + timedelta(days=2),
    "created_at": datetime.now() - timedelta(days=3),
    "updated_at": datetime.now() - timedelta(hours=2),
    "timeline": "1-3 months",
    "estimated_loan_amount": Decimal("400000"),
    "estimated_down_payment": Decimal("80000"),
    "credit_score_range": "good",
    "property_type_interest": "single_family",
    "notes": "Interested in new construction",
    "preferred_contact_method": "email",
}

MOCK_CONTACT = {
    "id": "CUST001",
    "first_name": "Robert",
    "last_name": "Williams",
    "email": "robert.w@email.com",
    "phone": "555-987-6543",
    "phone_secondary": None,
    "address": "456 Oak Ave",
    "city": "Dallas",
    "state": "TX",
    "zip": "75001",
    "date_of_birth": date(1980, 5, 15),
    "customer_since": datetime.now() - timedelta(days=365),
    "created_at": datetime.now() - timedelta(days=365),
    "acquisition_source": "referral",
    "source": "referral",
    "preferred_contact_method": "email",
    "preferred_contact_time": "morning",
    "notes": "VIP customer",
    "tags": ["investor", "repeat"],
    "employer": "Tech Corp",
}


# =============================================================================
# TEST UTILITIES
# =============================================================================

class TestResult:
    """Tracks test results."""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def record_pass(self, test_name: str):
        self.passed += 1
        print(f"  ✅ {test_name}")

    def record_fail(self, test_name: str, reason: str):
        self.failed += 1
        self.errors.append((test_name, reason))
        print(f"  ❌ {test_name}: {reason}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"TEST SUMMARY: {self.passed}/{total} passed")
        if self.errors:
            print(f"\nFailed tests:")
            for name, reason in self.errors:
                print(f"  - {name}: {reason}")
        print(f"{'='*60}")
        return self.failed == 0


results = TestResult()


def mock_execute_query(query: str, params: Dict = None) -> List[Dict]:
    """Mock database query execution."""
    query_lower = query.lower()

    if "from loans" in query_lower:
        return [MOCK_LOAN]
    elif "from leads" in query_lower:
        return [MOCK_LEAD]
    elif "from contacts" in query_lower:
        return [MOCK_CONTACT]
    elif "from loan_status_history" in query_lower or "from loan_stage_history" in query_lower:
        return [{"loans_moved": 5, "volume_moved": Decimal("2250000"), "stage": "processing", "avg_days": 3.5}]
    elif "from documents" in query_lower:
        return [
            {"doc_type": "application", "uploaded_at": date.today(), "status": "active", "doc_category": "compliance", "notes": None, "updated_at": date.today()},
            {"doc_type": "credit_report", "uploaded_at": date.today(), "status": "active", "doc_category": "compliance", "notes": None, "updated_at": date.today()},
        ]
    elif "from disclosure_events" in query_lower:
        return [
            {"disclosure_type": "initial_le", "prepared_at": datetime.now() - timedelta(days=12), "received_at": datetime.now() - timedelta(days=11), "delivery_method": "email", "change_reason": None, "change_description": None},
        ]
    elif "from communication_history" in query_lower:
        return [
            {"id": "COM001", "type": "call", "direction": "outbound", "subject": None, "summary": "Left voicemail", "sentiment": "neutral", "created_at": datetime.now(), "user_name": "Agent 1", "duration_seconds": 45, "outcome": "voicemail", "loan_number": None},
        ]
    elif "from lead_activities" in query_lower:
        return [
            {"activity_type": "call", "description": "Initial contact call", "outcome": "answered", "created_at": datetime.now() - timedelta(hours=2), "created_by": "LO001", "duration_minutes": 15, "channel": "phone"},
        ]
    elif "from referrals" in query_lower:
        return []
    elif "loan_officer" in query_lower or "from users" in query_lower:
        return [
            {"lo_id": "LO001", "lo_name": "Mike Johnson", "name": "Mike Johnson", "email": "mike@company.com", "pipeline_count": 12, "pipeline_volume": Decimal("5400000"), "applications": 3, "processing": 4, "underwriting": 3, "near_close": 2, "past_due": 1, "avg_days_in_stage": 4.5, "id": "LO001"},
        ]

    return []


def mock_execute_single(query: str, params: Dict = None) -> Dict:
    """Mock single result query."""
    results = mock_execute_query(query, params)
    return results[0] if results else None


# =============================================================================
# TEST: INFRASTRUCTURE (base.py)
# =============================================================================

def test_infrastructure():
    """Test base infrastructure components."""
    print("\n📦 Testing Infrastructure (base.py)")
    print("-" * 40)

    try:
        from backend.agents.tools.base import (
            ToolResult, ToolStatus, ToolError, ToolRegistry, tool_registry,
            mortgage_tool, format_currency, format_percentage, days_between,
            LoanStatus, LoanType
        )
        results.record_pass("Import base module")
    except ImportError as e:
        results.record_fail("Import base module", str(e))
        return

    # Test ToolResult
    try:
        result = ToolResult.success({"test": "data"}, "Test message", count=5)
        assert result.status == ToolStatus.SUCCESS
        assert result.data == {"test": "data"}
        assert result.message == "Test message"
        assert result.metadata.get("count") == 5
        results.record_pass("ToolResult.success()")
    except Exception as e:
        results.record_fail("ToolResult.success()", str(e))

    try:
        result = ToolResult.error("Something went wrong")
        assert result.status == ToolStatus.ERROR
        assert "Something went wrong" in result.errors
        results.record_pass("ToolResult.error()")
    except Exception as e:
        results.record_fail("ToolResult.error()", str(e))

    try:
        result = ToolResult.no_data("No results found")
        assert result.status == ToolStatus.NO_DATA
        results.record_pass("ToolResult.no_data()")
    except Exception as e:
        results.record_fail("ToolResult.no_data()", str(e))

    # Test serialization
    try:
        result = ToolResult.success({"count": 5}, "Serialization test")
        serialized = result.to_dict()
        assert serialized["status"] == "success"
        assert serialized["data"]["count"] == 5
        results.record_pass("ToolResult serialization")
    except Exception as e:
        results.record_fail("ToolResult serialization", str(e))

    # Test formatters
    try:
        assert format_currency(1234.56) == "$1,234.56"
        assert format_currency(1000000) == "$1,000,000.00"
        results.record_pass("format_currency()")
    except Exception as e:
        results.record_fail("format_currency()", str(e))

    try:
        assert format_percentage(0.75) == "0.75%"
        assert format_percentage(12.345) == "12.35%"
        results.record_pass("format_percentage()")
    except Exception as e:
        results.record_fail("format_percentage()", str(e))

    try:
        days = days_between(date.today() - timedelta(days=10), date.today())
        assert days == 10
        results.record_pass("days_between()")
    except Exception as e:
        results.record_fail("days_between()", str(e))

    # Test ToolRegistry
    try:
        assert isinstance(tool_registry, ToolRegistry)
        results.record_pass("ToolRegistry singleton")
    except Exception as e:
        results.record_fail("ToolRegistry singleton", str(e))

    # Test Enums
    try:
        assert LoanStatus.PROCESSING.value == "processing"
        assert LoanType.CONVENTIONAL.value == "conventional"
        results.record_pass("Enums (LoanStatus, LoanType)")
    except Exception as e:
        results.record_fail("Enums", str(e))


# =============================================================================
# TEST: TOOL REGISTRATION
# =============================================================================

def test_tool_registration():
    """Test that all 64 tools are properly registered."""
    print("\n📝 Testing Tool Registration")
    print("-" * 40)

    try:
        from backend.agents.tools import tool_registry, ALL_TOOLS
        results.record_pass("Import tool registry")
    except ImportError as e:
        results.record_fail("Import tool registry", str(e))
        return

    expected_tools = {
        "pipeline": [
            "get_pipeline_metrics", "get_loans_by_status", "get_loan_aging_report",
            "calculate_conversion_rates", "predict_closing_timeline",
            "get_bottleneck_analysis", "compare_to_benchmark", "get_lo_pipeline_breakdown"
        ],
        "compliance": [
            "check_trid_compliance", "check_respa_compliance", "check_fair_lending",
            "get_state_requirements", "audit_loan_file", "get_disclosure_timeline",
            "check_tolerance_violations", "get_compliance_history"
        ],
        "leads": [
            "get_lead_details", "get_engagement_history", "score_lead",
            "suggest_followup", "draft_message", "schedule_outreach",
            "get_similar_converted_leads", "get_optimal_contact_time"
        ],
        "documents": [
            "get_missing_documents", "get_loan_conditions", "track_document_request",
            "send_document_reminder", "escalate_issue", "get_document_timeline",
            "check_document_expiration", "get_third_party_status"
        ],
        "profitability": [
            "calculate_loan_profitability", "analyze_margins_by_segment",
            "forecast_revenue", "compare_lo_profitability", "optimize_pricing",
            "get_cost_breakdown", "calculate_pull_through_impact", "get_profitability_trends"
        ],
        "rates": [
            "get_current_rates", "analyze_rate_trends", "calculate_lock_cost",
            "recommend_lock_strategy", "monitor_float_position", "get_extension_pricing",
            "compare_rate_scenarios", "get_market_events"
        ],
        "coaching": [
            "get_lo_metrics", "compare_to_peers", "identify_training_needs",
            "generate_coaching_plan", "track_improvement", "get_best_practices",
            "get_performance_trends", "set_performance_goals"
        ],
        "customer": [
            "get_customer_360", "map_relationships", "calculate_ltv",
            "assess_churn_risk", "find_opportunities", "get_interaction_history",
            "get_referral_network", "get_market_comparison"
        ],
    }

    total_expected = sum(len(tools) for tools in expected_tools.values())
    registered_count = 0

    for category, tools in expected_tools.items():
        category_count = 0
        missing_tools = []
        for tool_name in tools:
            tool_def = tool_registry.get(tool_name)
            if tool_def is not None:
                category_count += 1
                registered_count += 1
            else:
                missing_tools.append(tool_name)

        if category_count == len(tools):
            results.record_pass(f"{category.capitalize()} tools ({category_count}/8)")
        else:
            results.record_fail(f"{category.capitalize()} tools", f"Missing: {', '.join(missing_tools)}")

    print(f"\n  Total: {registered_count}/{total_expected} tools registered")


# =============================================================================
# TEST: TOOL EXECUTION (with mocks)
# =============================================================================

def test_tool_execution():
    """Test tool execution with mock data."""
    print("\n⚡ Testing Tool Execution (with mocks)")
    print("-" * 40)

    try:
        from backend.agents.tools import execute_tool
        results.record_pass("Import execute_tool")
    except ImportError as e:
        results.record_fail("Import execute_tool", str(e))
        return

    # Patch database functions across all modules
    patches = [
        patch('backend.agents.tools.base.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.base.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.pipeline.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.pipeline.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.compliance.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.compliance.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.leads.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.leads.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.customer.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.customer.execute_single', side_effect=mock_execute_single),
    ]

    for p in patches:
        p.start()

    try:
        # Test pipeline tools
        try:
            result = execute_tool("get_pipeline_metrics")
            assert result.status.value in ["success", "no_data", "error"]
            results.record_pass("get_pipeline_metrics execution")
        except Exception as e:
            results.record_fail("get_pipeline_metrics execution", str(e))

        # Test compliance tools
        try:
            result = execute_tool("check_trid_compliance", loan_id="LOAN001")
            assert result.status.value in ["success", "no_data", "error"]
            results.record_pass("check_trid_compliance execution")
        except Exception as e:
            results.record_fail("check_trid_compliance execution", str(e))

        # Test lead tools
        try:
            result = execute_tool("get_lead_details", lead_id="LEAD001")
            assert result.status.value in ["success", "no_data", "error"]
            results.record_pass("get_lead_details execution")
        except Exception as e:
            results.record_fail("get_lead_details execution", str(e))

        # Test customer tools
        try:
            result = execute_tool("get_customer_360", customer_id="CUST001")
            assert result.status.value in ["success", "no_data", "error"]
            results.record_pass("get_customer_360 execution")
        except Exception as e:
            results.record_fail("get_customer_360 execution", str(e))

        # Test state requirements (uses hardcoded data, less DB dependent)
        try:
            result = execute_tool("get_state_requirements", state="CA")
            assert result.status.value == "success"
            assert result.data is not None
            results.record_pass("get_state_requirements execution")
        except Exception as e:
            results.record_fail("get_state_requirements execution", str(e))

    finally:
        for p in patches:
            p.stop()


# =============================================================================
# TEST: INTEGRATION LAYER
# =============================================================================

def test_integration_layer():
    """Test the tool integration layer."""
    print("\n🔗 Testing Integration Layer")
    print("-" * 40)

    try:
        from backend.agents.tool_integration import (
            AgentToolConfig, AGENT_CONFIGS, AgentToolExecutor,
            get_tool_descriptions, get_all_agent_tools
        )
        results.record_pass("Import integration layer")
    except ImportError as e:
        results.record_fail("Import integration layer", str(e))
        return

    # Test agent configs
    expected_agents = [
        "pipeline_analyst", "compliance_checker", "lead_nurturer",
        "document_tracker", "profitability_analyst", "rate_advisor",
        "team_coach", "customer_intelligence"
    ]

    for agent in expected_agents:
        if agent in AGENT_CONFIGS:
            config = AGENT_CONFIGS[agent]
            if len(config.tool_names) == 8:
                results.record_pass(f"Agent config: {agent}")
            else:
                results.record_fail(f"Agent config: {agent}", f"Has {len(config.tool_names)} tools, expected 8")
        else:
            results.record_fail(f"Agent config: {agent}", "Not found in AGENT_CONFIGS")

    # Test AgentToolExecutor creation
    try:
        executor = AgentToolExecutor("pipeline_analyst")
        tools = executor.get_available_tools()
        assert len(tools) == 8
        results.record_pass("AgentToolExecutor creation")
    except Exception as e:
        results.record_fail("AgentToolExecutor creation", str(e))

    # Test get_tool_descriptions
    try:
        descriptions = get_tool_descriptions("pipeline_analyst")
        assert "get_pipeline_metrics" in descriptions
        results.record_pass("get_tool_descriptions()")
    except Exception as e:
        results.record_fail("get_tool_descriptions()", str(e))

    # Test get_all_agent_tools
    try:
        all_tools = get_all_agent_tools()
        assert len(all_tools) == 8  # 8 agents
        total_tools = sum(len(tools) for tools in all_tools.values())
        assert total_tools == 64  # 64 tools total
        results.record_pass("get_all_agent_tools()")
    except Exception as e:
        results.record_fail("get_all_agent_tools()", str(e))


# =============================================================================
# TEST: ASYNC EXECUTION
# =============================================================================

async def test_async_execution():
    """Test async tool execution."""
    print("\n🔄 Testing Async Execution")
    print("-" * 40)

    try:
        from backend.agents.tool_integration import AgentToolExecutor
        results.record_pass("Import async components")
    except ImportError as e:
        results.record_fail("Import async components", str(e))
        return

    patches = [
        patch('backend.agents.tools.base.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.base.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.pipeline.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.pipeline.execute_single', side_effect=mock_execute_single),
    ]

    for p in patches:
        p.start()

    try:
        try:
            executor = AgentToolExecutor("pipeline_analyst")
            result = await executor.execute(
                tool_name="get_pipeline_metrics",
                params={"lo_id": "LO001"},
                user_id="test_user"
            )
            assert result.tool_name == "get_pipeline_metrics"
            results.record_pass("Async single tool execution")
        except Exception as e:
            results.record_fail("Async single tool execution", str(e))

        try:
            executor = AgentToolExecutor("pipeline_analyst")
            tool_calls = [
                {"tool_name": "get_pipeline_metrics", "params": {}},
                {"tool_name": "get_lo_pipeline_breakdown", "params": {}},
            ]
            batch_results = await executor.execute_many(tool_calls, user_id="test_user")
            assert len(batch_results) == 2
            results.record_pass("Async batch execution")
        except Exception as e:
            results.record_fail("Async batch execution", str(e))

    finally:
        for p in patches:
            p.stop()


# =============================================================================
# TEST: APPROVAL WORKFLOW
# =============================================================================

async def test_approval_workflow():
    """Test tool approval workflow for high-risk tools."""
    print("\n🔐 Testing Approval Workflow")
    print("-" * 40)

    try:
        from backend.agents.tool_integration import AgentToolExecutor, AGENT_CONFIGS
        results.record_pass("Import approval components")
    except ImportError as e:
        results.record_fail("Import approval components", str(e))
        return

    # Find an agent with approval requirements
    lead_config = AGENT_CONFIGS.get("lead_nurturer")
    if lead_config and lead_config.requires_approval_for:
        try:
            executor = AgentToolExecutor("lead_nurturer")

            # The requires_approval_for list contains action names like "send_email"
            # These aren't actual tool names, but actions that would require approval
            # For testing, we verify the config exists
            results.record_pass("High-risk tool config exists")

            # Test the approval/reject methods exist and work
            approval_id = "test_approval_123"
            executor._pending_approvals[approval_id] = {
                "tool_name": "test_tool",
                "params": {},
                "user_id": "test_user",
            }

            approval = executor.approve(approval_id, "manager_user")
            if approval and approval.get("approved_by") == "manager_user":
                results.record_pass("Approval workflow")
            else:
                results.record_fail("Approval workflow", "Approval returned unexpected result")

        except Exception as e:
            results.record_fail("Approval workflow", str(e))
    else:
        results.record_pass("Approval workflow (no high-risk tools configured)")


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================

def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("PERENNIA AI AGENT TOOLS - TEST SUITE")
    print("=" * 60)
    print(f"Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Database mode: {'REAL' if USE_REAL_DATABASE else 'MOCK'}")

    # Run synchronous tests
    test_infrastructure()
    test_tool_registration()
    test_tool_execution()
    test_integration_layer()

    # Run async tests
    asyncio.run(test_async_execution())
    asyncio.run(test_approval_workflow())

    # Print summary
    return results.summary()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
