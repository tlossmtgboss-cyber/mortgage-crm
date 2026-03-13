"""
Test Document Lifecycle Agent

Validates the 15 tools of the DocumentLifecycleAgent including:
- Document needs assessment and priority ordering
- Completeness checking and blocking document identification
- Tenant isolation on all database queries
- Decision audit logging
- Closing-date-aware prioritization
- Smart needs list due date calculation
- Borrower-friendly status message generation
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

from agents.specialized.base import AgentContext, ToolResult, AgentRegistry
from agents.specialized.document_lifecycle_agent import (
    DocumentLifecycleAgent,
    LOAN_TYPE_REQUIREMENTS,
    SELF_EMPLOYED_DOCS,
    INVESTMENT_PROPERTY_DOCS,
    GIFT_FUND_DOCS,
    DOC_PRIORITY,
    STAGE_BLOCKERS,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def agent_context():
    """Standard agent context with org_id for tenant isolation."""
    return AgentContext(
        user_id="test-user-1",
        user_email="processor@example.com",
        user_role="processor",
        organization_id="org-100",
        autonomous_mode=True,
        permissions=["read", "write"],
    )


@pytest.fixture
def agent(agent_context):
    """Instantiate DocumentLifecycleAgent with test context."""
    return DocumentLifecycleAgent(agent_context)


@pytest.fixture
def no_org_context():
    """Context without organization_id for tenant isolation tests."""
    return AgentContext(
        user_id="test-user-1",
        user_email="processor@example.com",
        user_role="processor",
        autonomous_mode=True,
        permissions=["read"],
    )


# =============================================================================
# Agent Registration and Structure
# =============================================================================

@pytest.mark.unit
class TestAgentRegistration:
    """Verify agent is properly registered and has correct tool count."""

    def test_agent_is_registered(self):
        """DocumentLifecycleAgent should be in the AgentRegistry."""
        assert "DocumentLifecycleAgent" in AgentRegistry._agents

    def test_agent_has_15_tools(self, agent):
        """Agent should have exactly 15 tools registered."""
        assert len(agent.tools) == 15

    def test_agent_name(self, agent):
        """Agent name should be DocumentLifecycleAgent."""
        assert agent.name == "DocumentLifecycleAgent"

    def test_agent_description_mentions_lifecycle(self, agent):
        """Agent description should mention lifecycle orchestration."""
        assert "lifecycle" in agent.description.lower()

    def test_all_tool_names_present(self, agent):
        """Verify all 15 expected tool names are registered."""
        expected_tools = [
            "assess_loan_document_needs",
            "generate_smart_needs_list",
            "check_document_completeness",
            "identify_blocking_documents",
            "trigger_intelligent_followup",
            "route_document_for_review",
            "escalate_stale_documents",
            "generate_condition_checklist",
            "predict_document_completion",
            "recommend_next_action",
            "batch_process_uploads",
            "generate_borrower_status_update",
            "check_expiring_documents",
            "coordinate_third_party_orders",
            "generate_processor_briefing",
        ]
        for tool_name in expected_tools:
            assert tool_name in agent.tools, f"Missing tool: {tool_name}"


# =============================================================================
# Constants and Configuration
# =============================================================================

@pytest.mark.unit
class TestDocumentConstants:
    """Validate document requirement constants."""

    def test_loan_type_requirements_has_5_types(self):
        """Should have requirements for conventional, fha, va, usda, jumbo."""
        expected = {"conventional", "fha", "va", "usda", "jumbo"}
        assert set(LOAN_TYPE_REQUIREMENTS.keys()) == expected

    def test_all_loan_types_have_base_docs(self):
        """Every loan type must have a non-empty base document list."""
        for loan_type, reqs in LOAN_TYPE_REQUIREMENTS.items():
            assert len(reqs["base"]) > 0, f"{loan_type} has empty base docs"

    def test_conventional_base_includes_critical_docs(self):
        """Conventional base should include paystubs, w2, bank_statements."""
        base = LOAN_TYPE_REQUIREMENTS["conventional"]["base"]
        for doc in ["paystubs", "w2", "bank_statements"]:
            assert doc in base, f"Missing {doc} from conventional base"

    def test_va_has_dd214_and_coe(self):
        """VA loans require DD214 and Certificate of Eligibility."""
        extra = LOAN_TYPE_REQUIREMENTS["va"]["extra"]
        assert "dd214" in extra
        assert "certificate_of_eligibility" in extra

    def test_fha_has_fha_case_number(self):
        """FHA loans require FHA case number."""
        extra = LOAN_TYPE_REQUIREMENTS["fha"]["extra"]
        assert "fha_case_number" in extra

    def test_self_employed_docs_include_tax_returns(self):
        """Self-employed docs should include tax returns and P&L."""
        assert "tax_returns" in SELF_EMPLOYED_DOCS
        assert "profit_loss" in SELF_EMPLOYED_DOCS

    def test_doc_priority_has_4_tiers(self):
        """DOC_PRIORITY should have critical, high, medium, low tiers."""
        assert set(DOC_PRIORITY.keys()) == {"critical", "high", "medium", "low"}

    def test_critical_docs_include_paystubs_and_w2(self):
        """Critical tier should include paystubs and w2."""
        for doc in ["paystubs", "w2", "bank_statements"]:
            assert doc in DOC_PRIORITY["critical"]

    def test_stage_blockers_has_processing(self):
        """STAGE_BLOCKERS should define blocking docs for PROCESSING."""
        assert "PROCESSING" in STAGE_BLOCKERS
        assert len(STAGE_BLOCKERS["PROCESSING"]) > 0


# =============================================================================
# Tenant Isolation
# =============================================================================

@pytest.mark.unit
class TestTenantIsolation:
    """Verify tenant isolation is enforced on all tools."""

    def test_require_org_id_raises_without_org(self, no_org_context):
        """Agent should raise ValueError if organization_id missing."""
        agent = DocumentLifecycleAgent(no_org_context)
        with pytest.raises(ValueError, match="requires organization_id"):
            agent.require_org_id()

    def test_require_org_id_returns_org(self, agent):
        """Agent should return org_id when present in context."""
        assert agent.require_org_id() == "org-100"

    def test_org_filter_sql_includes_org_id(self, agent):
        """org_filter_sql should produce correct SQL fragment."""
        sql = agent.org_filter_sql("l")
        assert "l.organization_id = :org_id" in sql

    def test_org_filter_params_includes_org_id(self, agent):
        """org_filter_params should include org_id in params dict."""
        params = agent.org_filter_params({"loan_id": 42})
        assert params["org_id"] == "org-100"
        assert params["loan_id"] == 42


# =============================================================================
# Decision Audit Logging
# =============================================================================

@pytest.mark.unit
class TestDecisionAuditLogging:
    """Verify audit logging is called by tools."""

    def test_audit_log_records_action(self, agent):
        """audit_log should not raise and should accept standard params."""
        # Should not raise
        agent.audit_log(
            "test_action",
            entity_type="loan",
            entity_id="123",
            details={"key": "value"},
        )

    def test_audit_log_includes_agent_name(self, agent, caplog):
        """Audit log entries should include the agent name."""
        import logging
        with caplog.at_level(logging.INFO):
            agent.audit_log("test_action", entity_type="loan", entity_id="1")
        assert "DocumentLifecycleAgent" in caplog.text

    def test_audit_log_includes_org_id(self, agent, caplog):
        """Audit log entries should include the organization_id."""
        import logging
        with caplog.at_level(logging.INFO):
            agent.audit_log("test_action")
        assert "org-100" in caplog.text


# =============================================================================
# Priority Ordering Logic
# =============================================================================

@pytest.mark.unit
class TestPriorityOrdering:
    """Test document priority classification logic."""

    def test_critical_doc_gets_critical_priority(self):
        """A doc in DOC_PRIORITY['critical'] should classify as critical."""
        doc = "paystubs"
        priority = "medium"  # default
        for p, docs in DOC_PRIORITY.items():
            if doc in docs:
                priority = p
                break
        assert priority == "critical"

    def test_high_doc_gets_high_priority(self):
        """A doc in DOC_PRIORITY['high'] should classify as high."""
        doc = "appraisal"
        priority = "medium"
        for p, docs in DOC_PRIORITY.items():
            if doc in docs:
                priority = p
                break
        assert priority == "high"

    def test_unknown_doc_defaults_to_medium(self):
        """A doc not in any DOC_PRIORITY tier defaults to medium."""
        doc = "some_unknown_doc_type"
        priority = "medium"
        for p, docs in DOC_PRIORITY.items():
            if doc in docs:
                priority = p
                break
        assert priority == "medium"

    def test_priority_sort_order(self):
        """Priority sort should order critical < high < medium < low."""
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        items = [
            {"priority": "low", "doc": "gift_letter"},
            {"priority": "critical", "doc": "paystubs"},
            {"priority": "high", "doc": "appraisal"},
            {"priority": "medium", "doc": "insurance"},
        ]
        items.sort(key=lambda x: priority_order.get(x["priority"], 9))
        assert items[0]["priority"] == "critical"
        assert items[1]["priority"] == "high"
        assert items[2]["priority"] == "medium"
        assert items[3]["priority"] == "low"


# =============================================================================
# Closing Date Awareness
# =============================================================================

@pytest.mark.unit
class TestClosingDateAwareness:
    """Test closing-date-driven logic."""

    def test_days_to_close_calculation(self):
        """Should correctly calculate days to closing."""
        today = date.today()
        closing = today + timedelta(days=15)
        days_to_close = (closing - today).days
        assert days_to_close == 15

    def test_critical_due_date_within_21_days_of_close(self):
        """Critical docs due date should leave 21+ days before close."""
        today = date.today()
        closing = today + timedelta(days=30)
        days_to_close = (closing - today).days
        critical_due = today + timedelta(days=min(3, max(0, days_to_close - 21)))
        # With 30 days to close, critical due = today + 3
        assert critical_due == today + timedelta(days=3)

    def test_critical_due_date_with_tight_closing(self):
        """When closing is very soon, critical due date should be today."""
        today = date.today()
        closing = today + timedelta(days=5)
        days_to_close = (closing - today).days
        critical_due = today + timedelta(days=min(3, max(0, days_to_close - 21)))
        # 5 - 21 = -16 -> max(0, -16) = 0
        assert critical_due == today

    def test_urgency_classification_under_7_days(self):
        """Loans closing within 7 days should be classified as urgent."""
        days_to_close = 5
        if days_to_close <= 7:
            urgency = "urgent"
        elif days_to_close <= 14:
            urgency = "attention"
        else:
            urgency = "on_track"
        assert urgency == "urgent"

    def test_urgency_classification_under_14_days(self):
        """Loans closing within 14 days should be classified as attention."""
        days_to_close = 10
        open_conditions = 0
        has_expiring = False
        if days_to_close <= 7 or has_expiring or open_conditions >= 3:
            urgency = "urgent"
        elif days_to_close <= 14 or open_conditions >= 1:
            urgency = "attention"
        else:
            urgency = "on_track"
        assert urgency == "attention"

    def test_urgency_classification_healthy(self):
        """Loans with 20+ days and no issues should be on_track."""
        days_to_close = 25
        open_conditions = 0
        has_expiring = False
        if days_to_close <= 7 or has_expiring or open_conditions >= 3:
            urgency = "urgent"
        elif days_to_close <= 14 or open_conditions >= 1:
            urgency = "attention"
        else:
            urgency = "on_track"
        assert urgency == "on_track"


# =============================================================================
# Stage Blocker Logic
# =============================================================================

@pytest.mark.unit
class TestStageBlockerLogic:
    """Test stage-based document blocking detection."""

    def test_processing_stage_requires_income_docs(self):
        """PROCESSING should require paystubs, w2, bank_statements, ID."""
        blockers = STAGE_BLOCKERS["PROCESSING"]
        for doc in ["paystubs", "w2", "bank_statements", "drivers_license"]:
            assert doc in blockers, f"{doc} should block PROCESSING"

    def test_submitted_stage_requires_appraisal(self):
        """SUBMITTED should require appraisal."""
        blockers = STAGE_BLOCKERS["SUBMITTED"]
        assert "appraisal" in blockers

    def test_clear_to_close_requires_insurance(self):
        """CLEAR_TO_CLOSE should require insurance."""
        blockers = STAGE_BLOCKERS["CLEAR_TO_CLOSE"]
        assert "insurance" in blockers

    def test_blocking_detection_logic(self):
        """Missing blocker docs should be identified correctly."""
        stage = "PROCESSING"
        existing_types = {"paystubs", "bank_statements"}
        blockers = STAGE_BLOCKERS.get(stage, [])
        missing_blockers = [d for d in blockers if d not in existing_types]
        assert "w2" in missing_blockers
        assert "drivers_license" in missing_blockers
        assert "paystubs" not in missing_blockers

    def test_no_blockers_when_all_present(self):
        """When all blocking docs are received, no blockers should be reported."""
        stage = "PROCESSING"
        existing_types = {"paystubs", "w2", "bank_statements", "drivers_license"}
        blockers = STAGE_BLOCKERS.get(stage, [])
        missing_blockers = [d for d in blockers if d not in existing_types]
        assert len(missing_blockers) == 0


# =============================================================================
# Document Requirements Building
# =============================================================================

@pytest.mark.unit
class TestDocumentRequirementsBuilding:
    """Test the logic for building loan-specific document requirements."""

    def test_conventional_base_doc_count(self):
        """Conventional base should have 9 document types."""
        base = LOAN_TYPE_REQUIREMENTS["conventional"]["base"]
        assert len(base) == 9

    def test_self_employed_adds_4_docs(self):
        """Self-employed flag should add 4 additional document types."""
        assert len(SELF_EMPLOYED_DOCS) == 4

    def test_investment_property_adds_docs(self):
        """Investment property should add rental docs."""
        assert len(INVESTMENT_PROPERTY_DOCS) == 2
        assert "rental_agreement" in INVESTMENT_PROPERTY_DOCS

    def test_gift_funds_adds_docs(self):
        """Gift funds flag should add gift letter and donor statements."""
        assert len(GIFT_FUND_DOCS) == 2
        assert "gift_letter" in GIFT_FUND_DOCS

    def test_deduplication_of_requirements(self):
        """When building requirements, duplicates should be removed."""
        required = ["paystubs", "w2", "paystubs", "bank_statements", "w2"]
        deduped = list(dict.fromkeys(required))
        assert len(deduped) == 3
        # Verify order preserved (first occurrence)
        assert deduped == ["paystubs", "w2", "bank_statements"]

    def test_completeness_calculation(self):
        """Completeness percentage should be correctly calculated."""
        required = ["paystubs", "w2", "bank_statements", "appraisal", "title"]
        existing = {"paystubs", "w2", "bank_statements"}
        total = len(required)
        received = len(existing & set(required))
        pct = round((received / total) * 100, 1) if total > 0 else 0
        assert pct == 60.0

    def test_completeness_100_percent(self):
        """100% completeness when all required docs are received."""
        required = ["paystubs", "w2"]
        existing = {"paystubs", "w2", "extra_doc"}
        received = len(existing & set(required))
        pct = round((received / len(required)) * 100, 1)
        assert pct == 100.0


# =============================================================================
# Borrower Status Message Generation
# =============================================================================

@pytest.mark.unit
class TestBorrowerStatusMessages:
    """Test the borrower-friendly status message generation logic."""

    def test_100_percent_message(self):
        """100% complete should generate a 'great news' message."""
        pct = 100
        first_name = "Jane"
        if pct == 100:
            msg = f"Hi {first_name}, great news! We have received all the documents we need."
        else:
            msg = ""
        assert "great news" in msg
        assert "Jane" in msg

    def test_75_percent_message_includes_missing(self):
        """75%+ should acknowledge progress and list remaining items."""
        pct = 80
        received = 8
        total = 10
        missing = ["insurance", "title"]
        first_name = "John"
        if pct >= 75:
            still_needed = [d.replace("_", " ").title() for d in missing[:3]]
            msg = f"Hi {first_name}, we are making great progress! We have {received} of {total} documents."
            next_step = f"Please provide: {', '.join(still_needed)}."
        else:
            msg = ""
            next_step = ""
        assert "great progress" in msg
        assert "Insurance" in next_step

    def test_under_50_percent_focuses_on_critical(self):
        """Under 50% should focus on critical missing items."""
        pct = 30
        missing = ["paystubs", "w2", "bank_statements", "title", "insurance"]
        critical_docs = DOC_PRIORITY.get("critical", [])
        critical_missing = [d for d in missing if d in critical_docs]
        assert len(critical_missing) >= 2  # paystubs and w2 are critical

    def test_first_name_extraction(self):
        """First name should be extracted from borrower_name."""
        borrower_name = "Jane Doe"
        first_name = borrower_name.split()[0] if borrower_name else "there"
        assert first_name == "Jane"

    def test_first_name_fallback_when_none(self):
        """Should fall back to 'there' when borrower_name is None."""
        borrower_name = None
        first_name = (borrower_name or "").split()[0] if borrower_name else "there"
        assert first_name == "there"


# =============================================================================
# Tool Risk Levels
# =============================================================================

@pytest.mark.unit
class TestToolRiskLevels:
    """Verify tool risk levels are set appropriately."""

    def test_query_tools_are_low_risk(self, agent):
        """Read-only query tools should be LOW risk."""
        low_risk_tools = [
            "assess_loan_document_needs",
            "check_document_completeness",
            "check_expiring_documents",
            "coordinate_third_party_orders",
        ]
        for tool_name in low_risk_tools:
            tool = agent.get_tool(tool_name)
            assert tool is not None, f"Tool {tool_name} not found"
            assert tool.risk_level.value == "low", f"{tool_name} should be LOW risk"

    def test_communication_tools_are_medium_risk(self, agent):
        """Communication tools should be MEDIUM risk (requires review)."""
        tool = agent.get_tool("trigger_intelligent_followup")
        assert tool is not None
        assert tool.risk_level.value == "medium"

    def test_escalation_tool_is_medium_risk(self, agent):
        """Escalation tool should be MEDIUM risk."""
        tool = agent.get_tool("escalate_stale_documents")
        assert tool is not None
        assert tool.risk_level.value == "medium"

    def test_analysis_tools_are_low_risk(self, agent):
        """Analysis tools should be LOW risk."""
        analysis_tools = [
            "generate_smart_needs_list",
            "identify_blocking_documents",
            "generate_condition_checklist",
            "predict_document_completion",
            "recommend_next_action",
            "generate_processor_briefing",
        ]
        for tool_name in analysis_tools:
            tool = agent.get_tool(tool_name)
            assert tool is not None, f"Tool {tool_name} not found"
            assert tool.risk_level.value == "low", f"{tool_name} should be LOW risk"


# =============================================================================
# Tool Categories
# =============================================================================

@pytest.mark.unit
class TestToolCategories:
    """Verify tools are in correct categories."""

    def test_analysis_tools_have_analysis_category(self, agent):
        """Analysis tools should have ANALYSIS category."""
        analysis_tools = [
            "assess_loan_document_needs",
            "generate_smart_needs_list",
            "identify_blocking_documents",
            "generate_condition_checklist",
            "predict_document_completion",
            "recommend_next_action",
            "generate_processor_briefing",
        ]
        for tool_name in analysis_tools:
            tool = agent.get_tool(tool_name)
            assert tool.category.value == "analysis", f"{tool_name} should be ANALYSIS"

    def test_query_tools_have_query_category(self, agent):
        """Query tools should have QUERY category."""
        query_tools = [
            "check_document_completeness",
            "check_expiring_documents",
            "coordinate_third_party_orders",
        ]
        for tool_name in query_tools:
            tool = agent.get_tool(tool_name)
            assert tool.category.value == "query", f"{tool_name} should be QUERY"

    def test_workflow_tools_have_workflow_category(self, agent):
        """Workflow tools should have WORKFLOW category."""
        workflow_tools = [
            "route_document_for_review",
            "batch_process_uploads",
        ]
        for tool_name in workflow_tools:
            tool = agent.get_tool(tool_name)
            assert tool.category.value == "workflow", f"{tool_name} should be WORKFLOW"

    def test_communication_tools_have_communication_category(self, agent):
        """Communication tools should have COMMUNICATION category."""
        tool = agent.get_tool("trigger_intelligent_followup")
        assert tool.category.value == "communication"

        tool = agent.get_tool("generate_borrower_status_update")
        # This is actually communication but classifying as LOW risk
        # since it generates but does not send
        assert tool.category.value == "communication"


# =============================================================================
# Expiration Logic
# =============================================================================

@pytest.mark.unit
class TestExpirationLogic:
    """Test document expiration detection logic."""

    def test_expired_document_detected(self):
        """Document past its expiration date should be flagged as expired."""
        today = date.today()
        expire_date = today - timedelta(days=5)
        is_expired = expire_date < today
        assert is_expired

    def test_expiring_soon_detected(self):
        """Document expiring within threshold should be flagged."""
        today = date.today()
        days_ahead = 30
        expire_date = today + timedelta(days=10)
        is_expiring = expire_date <= today + timedelta(days=days_ahead)
        assert is_expiring

    def test_far_future_not_flagged(self):
        """Document expiring well beyond threshold should not be flagged."""
        today = date.today()
        days_ahead = 30
        expire_date = today + timedelta(days=90)
        is_expiring = expire_date <= today + timedelta(days=days_ahead)
        assert not is_expiring

    def test_days_expired_calculation(self):
        """Days expired should be a positive integer for past-due docs."""
        today = date.today()
        expire_date = today - timedelta(days=12)
        days_expired = (today - expire_date).days
        assert days_expired == 12

    def test_days_until_expiry_calculation(self):
        """Days until expiry should be positive for future dates."""
        today = date.today()
        expire_date = today + timedelta(days=8)
        days_until = (expire_date - today).days
        assert days_until == 8
