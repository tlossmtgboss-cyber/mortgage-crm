# Perennia AI Agent Tools - Complete Tool-by-Tool Test Suite
# Tests all 64 tools across all 8 agents individually

"""
COMPLETE TOOL TEST SUITE
========================
This file tests EVERY tool for EVERY agent with mock data.

Save as: backend/agents/tools/test_complete_tools.py
Run: python -m agents.tools.test_complete_tools
"""

import sys
import asyncio
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Optional
from unittest.mock import patch, MagicMock
from dataclasses import dataclass


# =============================================================================
# MOCK DATA FACTORY
# =============================================================================

class MockDataFactory:
    """Generates mock data for all tool tests."""

    @staticmethod
    def loan(loan_id: str = "LOAN001", status: str = "processing") -> Dict:
        return {
            "id": loan_id,
            "loan_number": f"2024-{loan_id[-4:]}",
            "borrower_first_name": "John",
            "borrower_last_name": "Smith",
            "borrower_name": "John Smith",
            "loan_amount": Decimal("450000.00"),
            "amount": Decimal("450000.00"),
            "interest_rate": Decimal("6.75"),
            "rate": Decimal("6.75"),
            "apr": Decimal("6.875"),
            "loan_type": "conventional",
            "program": "Conventional 30yr",
            "property_type": "single_family",
            "occupancy_type": "primary",
            "status": status,
            "stage": status,
            "property_address": "123 Main St",
            "property_city": "Austin",
            "property_state": "TX",
            "property_zip": "78701",
            "expected_close_date": date.today() + timedelta(days=30),
            "target_close_date": date.today() + timedelta(days=30),
            "status_changed_at": datetime.now() - timedelta(days=3),
            "stage_entered_at": datetime.now() - timedelta(days=3),
            "created_at": datetime.now() - timedelta(days=14),
            "funded_at": None,
            "application_date": date.today() - timedelta(days=14),
            "le_sent_date": date.today() - timedelta(days=12),
            "le_received_date": date.today() - timedelta(days=11),
            "cd_sent_date": None,
            "cd_received_date": None,
            "intent_to_proceed_date": date.today() - timedelta(days=10),
            "loan_officer_id": "LO001",
            "loan_officer_name": "Mike Johnson",
            "processor_id": "PROC001",
            "branch_id": "BRANCH001",
            "referral_source": "realtor",
            "referral_fee_paid": Decimal("0"),
            "lo_nmls": "123456",
            "lo_license_exp": date.today() + timedelta(days=365),
            "credit_score": 750,
            "dti_ratio": 35.5,
            "ltv_ratio": 80.0,
            "pricing_adjustment": Decimal("0.125"),
            "current_balance": Decimal("445000.00"),
            "original_value": Decimal("562500.00"),
            "estimated_value": Decimal("580000.00"),
            "is_arm": False,
            "arm_adjustment_date": None,
        }

    @staticmethod
    def lead(lead_id: str = "LEAD001") -> Dict:
        return {
            "id": lead_id,
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@email.com",
            "phone": "555-123-4567",
            "phone_secondary": None,
            "status": "contacted",
            "lead_score": 75,
            "score": 75,
            "source": "Website",
            "source_name": "Website",
            "source_type": "organic",
            "campaign_name": None,
            "assigned_to": "LO001",
            "assigned_lo_name": "Mike Johnson",
            "total_activities": 5,
            "last_contact_date": datetime.now() - timedelta(hours=2),
            "last_activity": datetime.now() - timedelta(hours=2),
            "next_followup_date": date.today() + timedelta(days=2),
            "created_at": datetime.now() - timedelta(days=3),
            "updated_at": datetime.now() - timedelta(hours=2),
            "timeline": "1-3 months",
            "loan_purpose": "purchase",
            "estimated_loan_amount": Decimal("400000"),
            "estimated_down_payment": Decimal("80000"),
            "estimated_value": Decimal("500000"),
            "loan_amount_needed": Decimal("400000"),
            "down_payment": Decimal("100000"),
            "credit_score_range": "good",
            "employment_status": "employed_w2",
            "annual_income": Decimal("150000"),
            "property_state": "TX",
            "property_city": "Austin",
            "property_type_interest": "single_family",
            "notes": "Interested in 30yr fixed",
            "tags": ["hot", "first-time-buyer"],
            "preferred_contact_method": "email",
            "preferred_contact_time": "morning",
            "timezone": "America/Chicago",
        }

    @staticmethod
    def customer(customer_id: str = "CUST001") -> Dict:
        return {
            "id": customer_id,
            "first_name": "Robert",
            "last_name": "Williams",
            "email": "robert.w@email.com",
            "phone": "555-987-6543",
            "phone_secondary": "555-987-6544",
            "address": "456 Oak Ave",
            "city": "Dallas",
            "state": "TX",
            "zip": "75001",
            "date_of_birth": date(1980, 5, 15),
            "customer_since": datetime.now() - timedelta(days=730),
            "created_at": datetime.now() - timedelta(days=730),
            "acquisition_source": "referral",
            "source": "referral",
            "preferred_contact_method": "email",
            "preferred_contact_time": "morning",
            "notes": "VIP customer",
            "tags": ["investor", "repeat"],
            "employer": "Tech Corp",
            "job_title": "Senior Engineer",
            "annual_income": Decimal("200000"),
            "total_loans": 2,
            "total_funded_amount": Decimal("850000"),
            "lifetime_value": Decimal("12750"),
            "last_interaction": datetime.now() - timedelta(days=30),
            "sentiment_score": 0.8,
            "referral_count": 3,
        }

    @staticmethod
    def loan_officer(lo_id: str = "LO001") -> Dict:
        return {
            "id": lo_id,
            "lo_id": lo_id,
            "name": "Mike Johnson",
            "lo_name": "Mike Johnson",
            "email": "mike.johnson@company.com",
            "lo_email": "mike.johnson@company.com",
            "nmls_id": "123456",
            "license_expiration": date.today() + timedelta(days=365),
            "branch_id": "BRANCH001",
            "is_active": True,
            "role": "loan_officer",
            "hire_date": date.today() - timedelta(days=730),
            "pipeline_count": 12,
            "total_loans": 12,
            "pipeline_volume": Decimal("5400000"),
            "total_volume": Decimal("5400000"),
            "applications": 3,
            "early_stage": 3,
            "processing": 4,
            "mid_stage": 5,
            "underwriting": 3,
            "late_stage": 4,
            "near_close": 2,
            "past_due": 1,
            "avg_days_in_stage": 4.5,
            "total_funded_ytd": 45,
            "total_volume_ytd": Decimal("18500000"),
            "avg_cycle_time": 28,
            "pull_through_rate": 78.5,
            "conversion_rate": 65.0,
            "speed_to_lead_avg": 8.5,
        }

    @staticmethod
    def document(doc_type: str = "application") -> Dict:
        return {
            "id": f"DOC-{doc_type.upper()[:3]}001",
            "loan_id": "LOAN001",
            "document_type": doc_type,
            "document_category": "income" if doc_type in ["paystubs", "w2", "tax_returns"] else "compliance",
            "status": "received",
            "received_date": date.today() - timedelta(days=5),
            "expiration_date": date.today() + timedelta(days=90) if doc_type == "credit_report" else None,
            "requested_date": date.today() - timedelta(days=10),
            "requested_by": "LO001",
            "notes": None,
            "file_path": f"/documents/{doc_type}.pdf",
            "version": 1,
        }

    @staticmethod
    def condition(condition_type: str = "PTD") -> Dict:
        return {
            "id": f"COND001",
            "loan_id": "LOAN001",
            "condition_type": condition_type,
            "description": "Provide 2 most recent paystubs",
            "status": "pending",
            "category": "income",
            "priority": "high",
            "created_at": datetime.now() - timedelta(days=3),
            "due_date": date.today() + timedelta(days=7),
            "cleared_at": None,
            "cleared_by": None,
            "notes": None,
        }

    @staticmethod
    def rate_data() -> Dict:
        return {
            "product_type": "30yr_fixed",
            "rate": Decimal("6.750"),
            "apr": Decimal("6.875"),
            "points": Decimal("0.000"),
            "loan_type": "conventional",
            "as_of": datetime.now(),
            "trend": "stable",
            "change_1d": Decimal("-0.125"),
            "change_7d": Decimal("0.250"),
            "change_30d": Decimal("-0.375"),
        }

    @staticmethod
    def communication(comm_type: str = "call") -> Dict:
        return {
            "id": "COMM001",
            "contact_id": "CUST001",
            "loan_id": "LOAN001",
            "type": comm_type,
            "channel": comm_type,
            "direction": "outbound",
            "subject": "Follow up on application",
            "summary": "Discussed missing documents",
            "sentiment": "positive",
            "created_at": datetime.now() - timedelta(hours=2),
            "user_id": "LO001",
            "user_name": "Mike Johnson",
            "duration_seconds": 180 if comm_type == "call" else None,
            "outcome": "successful",
            "next_action": "Send document checklist",
            "next_action_date": date.today() + timedelta(days=1),
            "loan_number": "2024-001234",
        }

    @staticmethod
    def activity(activity_type: str = "call") -> Dict:
        return {
            "id": "ACT001",
            "lead_id": "LEAD001",
            "activity_type": activity_type,
            "description": "Initial contact call",
            "outcome": "answered",
            "created_at": datetime.now() - timedelta(hours=2),
            "created_by": "LO001",
            "duration_minutes": 15,
            "channel": "phone",
        }

    @staticmethod
    def fee(fee_type: str = "origination") -> Dict:
        return {
            "id": "FEE001",
            "loan_id": "LOAN001",
            "fee_type": fee_type,
            "fee_name": fee_type.replace("_", " ").title(),
            "fee_category": "lender" if fee_type == "origination" else "third_party",
            "tolerance_category": "zero" if fee_type in ["origination", "appraisal"] else "ten_percent",
            "le_amount": Decimal("1500.00"),
            "cd_amount": Decimal("1500.00"),
            "amount": Decimal("1500.00"),
            "final_amount": Decimal("1500.00"),
            "paid_to": "Lender",
            "paid_to_type": "lender",
            "is_affiliated": False,
            "is_affiliated_provider": False,
            "service_provided": True,
            "disclosure_type": "le",
        }

    @staticmethod
    def disclosure(disc_type: str = "initial_le") -> Dict:
        return {
            "id": "DISC001",
            "loan_id": "LOAN001",
            "disclosure_type": disc_type,
            "version": 1,
            "issued_date": datetime.now() - timedelta(days=12),
            "received_date": datetime.now() - timedelta(days=11),
            "delivery_method": "email",
            "apr": Decimal("6.875"),
            "total_closing_costs": Decimal("12500"),
            "notes": None,
        }

    @staticmethod
    def pipeline_metrics() -> Dict:
        return {
            "total_loans": 45,
            "total_volume": Decimal("18500000"),
            "avg_loan_size": Decimal("411111.11"),
            "applications": 8,
            "processing": 12,
            "underwriting": 10,
            "conditional": 8,
            "ctc": 4,
            "closing": 3,
            "past_due": 2,
            "closing_this_week": 3,
            "closing_this_month": 12,
            "count": 45,
            "stage_volume": Decimal("18500000"),
            "avg_days_in_stage": 4.5,
        }

    @staticmethod
    def stage_data(status: str = "processing") -> Dict:
        return {
            "status": status,
            "stage": status,
            "loan_count": 12,
            "count": 12,
            "total_volume": Decimal("5400000"),
            "stage_volume": Decimal("5400000"),
            "avg_loan_size": Decimal("450000"),
            "avg_days_in_stage": 4.5,
        }


# =============================================================================
# MOCK DATABASE RESPONSES
# =============================================================================

class MockDatabase:
    """Provides mock database responses based on query patterns."""

    def __init__(self):
        self.factory = MockDataFactory()

    def execute_query(self, query: str, params: Dict = None) -> List[Dict]:
        """Return mock data based on query pattern."""
        query_lower = query.lower()

        # Pipeline queries
        if "from loans" in query_lower and "count(*)" in query_lower and "group by" in query_lower:
            return [
                self.factory.stage_data("application"),
                self.factory.stage_data("processing"),
                self.factory.stage_data("underwriting"),
                self.factory.stage_data("conditional"),
                self.factory.stage_data("clear_to_close"),
            ]

        if "from loans" in query_lower and "group by" in query_lower and "stage" in query_lower:
            return [
                self.factory.stage_data("application"),
                self.factory.stage_data("processing"),
                self.factory.stage_data("underwriting"),
            ]

        if "from loans" in query_lower:
            return [self.factory.loan()]

        if "from loan_stage_history" in query_lower or "from loan_status_history" in query_lower:
            return [{"stage": "processing", "avg_days": 3.5, "stage_exited_at": datetime.now(), "stage_entered_at": datetime.now() - timedelta(days=3)}]

        # Lead queries
        if "from leads" in query_lower:
            return [self.factory.lead()]

        if "from lead_activities" in query_lower:
            return [self.factory.activity("call"), self.factory.activity("email")]

        # Customer/Contact queries
        if "from contacts" in query_lower or "from customers" in query_lower:
            return [self.factory.customer()]

        # Document queries
        if "from documents" in query_lower:
            return [
                self.factory.document("application"),
                self.factory.document("credit_report"),
                self.factory.document("income_verification"),
            ]

        if "from loan_conditions" in query_lower or "from conditions" in query_lower:
            return [self.factory.condition("PTD"), self.factory.condition("PTF")]

        # LO/User queries
        if "from users" in query_lower:
            return [self.factory.loan_officer()]

        # Communication queries
        if "from communication_history" in query_lower:
            return [self.factory.communication("call"), self.factory.communication("email")]

        # Fee queries
        if "from loan_fees" in query_lower:
            return [
                self.factory.fee("origination"),
                self.factory.fee("appraisal"),
                self.factory.fee("title"),
            ]

        # Disclosure queries
        if "from disclosure_events" in query_lower:
            return [self.factory.disclosure("initial_le")]

        # Compliance queries
        if "from compliance_audits" in query_lower:
            return [{"audit_date": datetime.now(), "audit_type": "full", "auditor": "COMP001", "overall_status": "pass", "critical_count": 0, "warning_count": 1, "findings": None}]

        if "from service_issues" in query_lower:
            return [{"total_issues": 1, "open_issues": 0, "high_severity": 0, "avg_resolution_days": 2.5}]

        # Rate queries
        if "from rate_sheet" in query_lower or "from rates" in query_lower:
            return [self.factory.rate_data()]

        # Referral queries
        if "from referrals" in query_lower:
            return [{"id": "REF001", "referrer_id": "CUST001", "referred_id": "CUST002", "status": "funded", "created_at": datetime.now() - timedelta(days=90), "loan_amount": Decimal("400000"), "loan_status": "funded", "funded_at": datetime.now() - timedelta(days=30), "referred_name": "John Doe", "referrer_name": "Jane Smith"}]

        # Third party orders
        if "from third_party_orders" in query_lower:
            return [
                {"id": "TPO001", "loan_id": "LOAN001", "order_type": "appraisal", "vendor": "ABC Appraisals", "status": "ordered", "ordered_date": date.today() - timedelta(days=5), "due_date": date.today() + timedelta(days=5), "completed_date": None, "amount": Decimal("550")},
            ]

        # Performance queries
        if "from lo_performance" in query_lower or "from performance_metrics" in query_lower:
            return [
                {"lo_id": "LO001", "period": "2024-01", "funded_count": 8, "funded_volume": Decimal("3200000"), "avg_cycle_time": 27, "pull_through": 80.0, "conversion_rate": 68.0},
            ]

        # Market events
        if "from market_events" in query_lower:
            return [
                {"id": "ME001", "event_type": "fed_meeting", "event_date": date.today() + timedelta(days=14), "description": "FOMC Meeting", "expected_impact": "high"},
            ]

        # Tasks
        if "from tasks" in query_lower:
            return [{"id": "TASK001", "task_type": "call", "related_lead_id": "LEAD001", "title": "Follow up call", "due_date": date.today(), "status": "pending"}]

        # Default empty
        return []

    def execute_single(self, query: str, params: Dict = None) -> Optional[Dict]:
        """Return single mock result."""
        results = self.execute_query(query, params)
        return results[0] if results else None


mock_db = MockDatabase()


def mock_execute_query(query: str, params: Dict = None) -> List[Dict]:
    return mock_db.execute_query(query, params)


def mock_execute_single(query: str, params: Dict = None) -> Optional[Dict]:
    return mock_db.execute_single(query, params)


# =============================================================================
# TEST RESULT TRACKER
# =============================================================================

@dataclass
class TestCase:
    tool_name: str
    agent: str
    passed: bool
    message: str
    execution_time: float = 0.0
    error: str = None


class TestTracker:
    """Tracks all test results."""

    def __init__(self):
        self.results: List[TestCase] = []
        self.by_agent: Dict[str, List[TestCase]] = {}

    def record(self, tool_name: str, agent: str, passed: bool, message: str,
               execution_time: float = 0.0, error: str = None):
        test = TestCase(tool_name, agent, passed, message or "OK", execution_time, error)
        self.results.append(test)

        if agent not in self.by_agent:
            self.by_agent[agent] = []
        self.by_agent[agent].append(test)

        status = "✅" if passed else "❌"
        display_msg = message[:50] + "..." if message and len(message) > 50 else (message or "OK")
        print(f"    {status} {tool_name}: {display_msg}")

    def summary(self) -> bool:
        """Print summary and return True if all passed."""
        passed = sum(1 for t in self.results if t.passed)
        failed = sum(1 for t in self.results if not t.passed)
        total = len(self.results)

        print("\n" + "=" * 70)
        print("TEST SUMMARY BY AGENT")
        print("=" * 70)

        for agent, tests in self.by_agent.items():
            agent_passed = sum(1 for t in tests if t.passed)
            agent_total = len(tests)
            status = "✅" if agent_passed == agent_total else "⚠️"
            print(f"\n{status} {agent.upper().replace('_', ' ')}: {agent_passed}/{agent_total} tools passed")

            for test in tests:
                if not test.passed:
                    print(f"   ❌ {test.tool_name}: {test.error or test.message}")

        print("\n" + "=" * 70)
        print(f"TOTAL: {passed}/{total} tests passed ({failed} failed)")
        print("=" * 70)

        return failed == 0


tracker = TestTracker()


# =============================================================================
# TOOL TEST DEFINITIONS
# =============================================================================

def get_all_patches():
    """Return all mock patches needed."""
    return [
        patch('backend.agents.tools.base.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.base.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.pipeline.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.pipeline.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.compliance.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.compliance.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.leads.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.leads.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.documents.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.documents.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.profitability.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.profitability.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.rates.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.rates.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.coaching.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.coaching.execute_single', side_effect=mock_execute_single),
        patch('backend.agents.tools.customer.execute_query', side_effect=mock_execute_query),
        patch('backend.agents.tools.customer.execute_single', side_effect=mock_execute_single),
    ]


def run_tool_test(tool_name: str, agent: str, **kwargs):
    """Run a single tool test."""
    from backend.agents.tools import execute_tool
    from backend.agents.tools.base import ToolStatus

    try:
        result = execute_tool(tool_name, **kwargs)
        if result.status in [ToolStatus.SUCCESS, ToolStatus.NO_DATA, ToolStatus.PARTIAL]:
            tracker.record(tool_name, agent, True, result.message)
        else:
            tracker.record(tool_name, agent, False, result.message, error=str(result.errors) if result.errors else None)
    except Exception as e:
        tracker.record(tool_name, agent, False, "Exception", error=str(e))


# =============================================================================
# PIPELINE ANALYST TESTS (8 tools)
# =============================================================================

def test_pipeline_analyst():
    """Test all 8 Pipeline Analyst tools."""
    print("\n📊 PIPELINE ANALYST (8 tools)")
    print("-" * 50)

    run_tool_test("get_pipeline_metrics", "pipeline_analyst")
    run_tool_test("get_loans_by_status", "pipeline_analyst", status="processing")
    run_tool_test("get_loan_aging_report", "pipeline_analyst")
    run_tool_test("calculate_conversion_rates", "pipeline_analyst")
    run_tool_test("predict_closing_timeline", "pipeline_analyst", loan_id=1)
    run_tool_test("get_bottleneck_analysis", "pipeline_analyst")
    run_tool_test("compare_to_benchmark", "pipeline_analyst")
    run_tool_test("get_lo_pipeline_breakdown", "pipeline_analyst")


# =============================================================================
# COMPLIANCE CHECKER TESTS (8 tools)
# =============================================================================

def test_compliance_checker():
    """Test all 8 Compliance Checker tools."""
    print("\n⚖️ COMPLIANCE CHECKER (8 tools)")
    print("-" * 50)

    run_tool_test("check_trid_compliance", "compliance_checker", loan_id=1)
    run_tool_test("check_respa_compliance", "compliance_checker", loan_id=1)
    run_tool_test("check_fair_lending", "compliance_checker", loan_id=1)
    run_tool_test("get_state_requirements", "compliance_checker", state="TX")
    run_tool_test("audit_loan_file", "compliance_checker", loan_id=1)
    run_tool_test("get_disclosure_timeline", "compliance_checker", loan_id=1)
    run_tool_test("check_tolerance_violations", "compliance_checker", loan_id=1)
    run_tool_test("get_compliance_history", "compliance_checker", loan_id=1)


# =============================================================================
# LEAD NURTURER TESTS (8 tools)
# =============================================================================

def test_lead_nurturer():
    """Test all 8 Lead Nurturer tools."""
    print("\n🎯 LEAD NURTURER (8 tools)")
    print("-" * 50)

    run_tool_test("get_lead_details", "lead_nurturer", lead_id=1)
    run_tool_test("get_engagement_history", "lead_nurturer", lead_id=1)
    run_tool_test("score_lead", "lead_nurturer", lead_id=1)
    run_tool_test("suggest_followup", "lead_nurturer", lead_id=1)
    run_tool_test("draft_message", "lead_nurturer", lead_id=1, message_type="follow_up", channel="email")
    run_tool_test("schedule_outreach", "lead_nurturer", lead_id=1, outreach_type="call", scheduled_date=(date.today() + timedelta(days=1)).isoformat())
    run_tool_test("get_similar_converted_leads", "lead_nurturer", lead_id=1)
    run_tool_test("get_optimal_contact_time", "lead_nurturer", lead_id=1)


# =============================================================================
# DOCUMENT TRACKER TESTS (8 tools)
# =============================================================================

def test_document_tracker():
    """Test all 8 Document Tracker tools."""
    print("\n📄 DOCUMENT TRACKER (8 tools)")
    print("-" * 50)

    run_tool_test("get_missing_documents", "document_tracker", loan_id=1)
    run_tool_test("get_loan_conditions", "document_tracker", loan_id=1)
    run_tool_test("track_document_request", "document_tracker", loan_id=1, document_type="paystubs")
    run_tool_test("send_document_reminder", "document_tracker", loan_id=1, document_type="paystubs")
    run_tool_test("escalate_issue", "document_tracker", loan_id=1, issue_type="missing_documents", description="Borrower unresponsive")
    run_tool_test("get_document_timeline", "document_tracker", loan_id=1)
    run_tool_test("check_document_expiration", "document_tracker", loan_id=1)
    run_tool_test("get_third_party_status", "document_tracker", loan_id=1)


# =============================================================================
# PROFITABILITY ANALYST TESTS (8 tools)
# =============================================================================

def test_profitability_analyst():
    """Test all 8 Profitability Analyst tools."""
    print("\n💰 PROFITABILITY ANALYST (8 tools)")
    print("-" * 50)

    run_tool_test("calculate_loan_profitability", "profitability_analyst", loan_id=1)
    run_tool_test("analyze_margins_by_segment", "profitability_analyst", segment_by="loan_type")
    run_tool_test("forecast_revenue", "profitability_analyst", months_ahead=3)
    run_tool_test("compare_lo_profitability", "profitability_analyst")
    run_tool_test("optimize_pricing", "profitability_analyst", loan_amount=450000, loan_type="conventional", credit_score=750)
    run_tool_test("get_cost_breakdown", "profitability_analyst", loan_id=1)
    run_tool_test("calculate_pull_through_impact", "profitability_analyst", current_rate=75.0, target_rate=80.0)
    run_tool_test("get_profitability_trends", "profitability_analyst", period="monthly", months=6)


# =============================================================================
# RATE ADVISOR TESTS (8 tools)
# =============================================================================

def test_rate_advisor():
    """Test all 8 Rate Advisor tools."""
    print("\n📈 RATE ADVISOR (8 tools)")
    print("-" * 50)

    run_tool_test("get_current_rates", "rate_advisor", loan_type="conventional")
    run_tool_test("analyze_rate_trends", "rate_advisor", days=30)
    run_tool_test("calculate_lock_cost", "rate_advisor", loan_id=1, lock_days=30)
    run_tool_test("recommend_lock_strategy", "rate_advisor", loan_id=1)
    run_tool_test("monitor_float_position", "rate_advisor", lo_id=1)
    run_tool_test("get_extension_pricing", "rate_advisor", loan_id=1, extension_days=7)
    run_tool_test("compare_rate_scenarios", "rate_advisor", loan_amount=450000, rates=[6.5, 6.75, 7.0])
    run_tool_test("get_market_events", "rate_advisor", days_ahead=30)


# =============================================================================
# TEAM COACH TESTS (8 tools)
# =============================================================================

def test_team_coach():
    """Test all 8 Team Coach tools."""
    print("\n🏆 TEAM COACH (8 tools)")
    print("-" * 50)

    run_tool_test("get_lo_metrics", "team_coach", lo_id=1)
    run_tool_test("compare_to_peers", "team_coach", lo_id=1)
    run_tool_test("identify_training_needs", "team_coach", lo_id=1)
    run_tool_test("generate_coaching_plan", "team_coach", lo_id=1)
    run_tool_test("track_improvement", "team_coach", lo_id=1, months=6)
    run_tool_test("get_best_practices", "team_coach", metric="conversion_rate")
    run_tool_test("get_performance_trends", "team_coach", lo_id=1)
    run_tool_test("set_performance_goals", "team_coach", lo_id=1, goals={"monthly_volume": 5000000, "pull_through": 80})


# =============================================================================
# CUSTOMER INTELLIGENCE TESTS (8 tools)
# =============================================================================

def test_customer_intelligence():
    """Test all 8 Customer Intelligence tools."""
    print("\n👥 CUSTOMER INTELLIGENCE (8 tools)")
    print("-" * 50)

    run_tool_test("get_customer_360", "customer_intelligence", customer_id="CUST001")
    run_tool_test("map_relationships", "customer_intelligence", customer_id="CUST001")
    run_tool_test("calculate_ltv", "customer_intelligence", customer_id="CUST001")
    run_tool_test("assess_churn_risk", "customer_intelligence", customer_id="CUST001")
    run_tool_test("find_opportunities", "customer_intelligence", customer_id="CUST001")
    run_tool_test("get_interaction_history", "customer_intelligence", customer_id="CUST001")
    run_tool_test("get_referral_network", "customer_intelligence", customer_id="CUST001")
    run_tool_test("get_market_comparison", "customer_intelligence", customer_id="CUST001")


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================

def run_all_tool_tests():
    """Run all 64 tool tests."""
    print("=" * 70)
    print("PERENNIA AI - COMPLETE TOOL TEST SUITE")
    print("Testing all 64 tools across 8 agents")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Apply all patches
    patches = get_all_patches()
    for p in patches:
        p.start()

    try:
        # Run tests for each agent
        test_pipeline_analyst()
        test_compliance_checker()
        test_lead_nurturer()
        test_document_tracker()
        test_profitability_analyst()
        test_rate_advisor()
        test_team_coach()
        test_customer_intelligence()

    finally:
        # Stop all patches
        for p in patches:
            p.stop()

    # Print summary
    return tracker.summary()


if __name__ == "__main__":
    success = run_all_tool_tests()
    sys.exit(0 if success else 1)
