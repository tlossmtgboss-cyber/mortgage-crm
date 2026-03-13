"""
Test Agent Tenant Isolation — Cross-Tenant Data Contamination Prevention

Verifies that all AI agent tool implementations enforce organization_id
validation before accessing any data. Tests cover:

1. Each agent rejects cross-tenant loan access
2. Each agent rejects cross-tenant document access
3. Org verification runs BEFORE any service calls
4. Error messages do not leak org information
5. Base class shared helpers work correctly
6. Campaign tenant verification (DocumentFollowUpAgent)
"""

import pytest
import asyncio
import re
from unittest.mock import patch, MagicMock, call
from dataclasses import dataclass
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Lightweight stand-ins so we don't need the full import chain
# ---------------------------------------------------------------------------

class MockRow:
    """Simulate a SQLAlchemy Row object with attribute access."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_fetchone_side_effect(org_id_for_success="org_42"):
    """Return a side_effect function for db.execute().fetchone() that returns
    a row only when the params include the matching org_id."""
    def side_effect(*args, **kwargs):
        mock_result = MagicMock()
        # Get the last call's params from the enclosing execute mock
        return mock_result
    return side_effect


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ORG_A = "org_42"   # The agent's own org
ORG_B = "org_99"   # A different org (cross-tenant)


@pytest.fixture
def context_org_a() -> Dict[str, Any]:
    """Agent context for Organization A."""
    return {
        "user_id": "user_1",
        "user_email": "lo@orga.com",
        "user_role": "loan_officer",
        "organization_id": ORG_A,
        "autonomous_mode": True,
        "permissions": ["read", "write"],
    }


@pytest.fixture
def context_org_b() -> Dict[str, Any]:
    """Agent context for Organization B (cross-tenant attacker)."""
    return {
        "user_id": "user_99",
        "user_email": "lo@orgb.com",
        "user_role": "loan_officer",
        "organization_id": ORG_B,
        "autonomous_mode": True,
        "permissions": ["read", "write"],
    }


@pytest.fixture
def context_no_org() -> Dict[str, Any]:
    """Agent context with NO organization_id."""
    return {
        "user_id": "user_1",
        "user_email": "lo@orga.com",
        "user_role": "loan_officer",
        "autonomous_mode": True,
    }


@pytest.fixture
def mock_db():
    """Create a mock DB session. By default, fetchone() returns None
    (simulating cross-tenant denial)."""
    session = MagicMock()
    session.close = MagicMock()
    # Default: org check returns None (cross-tenant denial)
    session.execute.return_value.fetchone.return_value = None
    session.execute.return_value.fetchall.return_value = []
    return session


def _allow_org_check(mock_db, loan_id=1, org_id=ORG_A):
    """Configure mock_db so the org verification query succeeds for the
    given loan_id and org_id, but subsequent queries also work."""
    original_execute = mock_db.execute

    call_count = {"n": 0}

    def execute_side_effect(query, params=None):
        call_count["n"] += 1
        result = MagicMock()
        # First call is always the tenant isolation check
        if call_count["n"] == 1:
            result.fetchone.return_value = MockRow(id=loan_id)
        else:
            # Subsequent calls return reasonable defaults
            result.fetchone.return_value = MockRow(
                id=loan_id, loan_number="LN-2026-001",
                borrower_name="John Doe", stage="PROCESSING",
                loan_type="conventional", amount=350000,
                coborrower_name=None, closing_date=None,
            )
            result.fetchall.return_value = []
        return result

    mock_db.execute.side_effect = execute_side_effect


# ---------------------------------------------------------------------------
# Tests: Base Class Helpers
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBaseClassTenantHelpers:
    """Test the shared verify_* methods on SpecializedAgent base class."""

    def test_verify_loan_tenant_rejects_cross_org(self, context_org_b, mock_db):
        """verify_loan_tenant raises ValueError for another org's loan."""
        from agents.specialized.base import SpecializedAgent

        class _TestAgent(SpecializedAgent):
            @property
            def name(self):
                return "TestAgent"

            @property
            def description(self):
                return "Test"

            def _register_tools(self):
                pass

        agent = _TestAgent(context_org_b)
        # DB returns no row (loan belongs to org_42, agent is org_99)
        mock_db.execute.return_value.fetchone.return_value = None

        with pytest.raises(ValueError, match=r"Loan \d+ not found"):
            agent.verify_loan_tenant(mock_db, loan_id=1)

    def test_verify_loan_tenant_error_does_not_leak_org(self, context_org_b, mock_db):
        """Error message must NOT contain the organization ID."""
        from agents.specialized.base import SpecializedAgent

        class _TestAgent(SpecializedAgent):
            @property
            def name(self):
                return "TestAgent"

            @property
            def description(self):
                return "Test"

            def _register_tools(self):
                pass

        agent = _TestAgent(context_org_b)
        mock_db.execute.return_value.fetchone.return_value = None

        with pytest.raises(ValueError) as exc_info:
            agent.verify_loan_tenant(mock_db, loan_id=1)

        error_msg = str(exc_info.value)
        assert ORG_B not in error_msg
        assert ORG_A not in error_msg
        assert "org" not in error_msg.lower() or "not found" in error_msg.lower()

    def test_verify_document_tenant_rejects_cross_org(self, context_org_b, mock_db):
        """verify_document_tenant raises ValueError for another org's document."""
        from agents.specialized.base import SpecializedAgent

        class _TestAgent(SpecializedAgent):
            @property
            def name(self):
                return "TestAgent"

            @property
            def description(self):
                return "Test"

            def _register_tools(self):
                pass

        agent = _TestAgent(context_org_b)
        mock_db.execute.return_value.fetchone.return_value = None

        with pytest.raises(ValueError, match=r"Document \d+ not found"):
            agent.verify_document_tenant(mock_db, document_id=10)

    def test_verify_campaign_tenant_rejects_cross_org(self, context_org_b, mock_db):
        """verify_campaign_tenant raises ValueError for another org's campaign."""
        from agents.specialized.base import SpecializedAgent

        class _TestAgent(SpecializedAgent):
            @property
            def name(self):
                return "TestAgent"

            @property
            def description(self):
                return "Test"

            def _register_tools(self):
                pass

        agent = _TestAgent(context_org_b)
        mock_db.execute.return_value.fetchone.return_value = None

        with pytest.raises(ValueError, match=r"Campaign \d+ not found"):
            agent.verify_campaign_tenant(mock_db, campaign_id=5)

    def test_verify_entity_tenant_rejects_disallowed_table(self, context_org_a, mock_db):
        """verify_entity_tenant rejects tables not in the allowlist."""
        from agents.specialized.base import SpecializedAgent

        class _TestAgent(SpecializedAgent):
            @property
            def name(self):
                return "TestAgent"

            @property
            def description(self):
                return "Test"

            def _register_tools(self):
                pass

        agent = _TestAgent(context_org_a)

        with pytest.raises(ValueError, match="not allowed"):
            agent.verify_entity_tenant(mock_db, table="users", entity_id=1)

    def test_verify_entity_tenant_allows_known_tables(self, context_org_a, mock_db):
        """verify_entity_tenant accepts tables in the allowlist (but still rejects if row missing)."""
        from agents.specialized.base import SpecializedAgent

        class _TestAgent(SpecializedAgent):
            @property
            def name(self):
                return "TestAgent"

            @property
            def description(self):
                return "Test"

            def _register_tools(self):
                pass

        agent = _TestAgent(context_org_a)
        mock_db.execute.return_value.fetchone.return_value = None

        with pytest.raises(ValueError, match="not found"):
            agent.verify_entity_tenant(mock_db, table="loans", entity_id=999)

    def test_require_org_id_raises_without_org(self, context_no_org):
        """require_org_id raises ValueError when context has no organization_id."""
        from agents.specialized.base import SpecializedAgent

        class _TestAgent(SpecializedAgent):
            @property
            def name(self):
                return "TestAgent"

            @property
            def description(self):
                return "Test"

            def _register_tools(self):
                pass

        agent = _TestAgent(context_no_org)
        with pytest.raises(ValueError):
            agent.require_org_id()


# ---------------------------------------------------------------------------
# Tests: DocumentIntelligenceAgent Tenant Isolation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDocumentIntelligenceAgentTenantIsolation:
    """Verify DocumentIntelligenceAgent rejects cross-tenant access."""

    @pytest.fixture
    def agent_org_b(self, context_org_b):
        from agents.specialized.document_intelligence_agent import DocumentIntelligenceAgent
        return DocumentIntelligenceAgent(context_org_b)

    @pytest.fixture
    def agent_org_a(self, context_org_a):
        from agents.specialized.document_intelligence_agent import DocumentIntelligenceAgent
        return DocumentIntelligenceAgent(context_org_a)

    @pytest.mark.parametrize("tool_name,input_data", [
        ("analyze_application_for_documents", {"loan_id": 1}),
        ("batch_review_loan_documents", {"loan_id": 1}),
        ("calculate_income", {"loan_id": 1, "borrower_id": 10}),
        ("analyze_bank_statements", {"loan_id": 1, "borrower_id": 10}),
        ("analyze_call_for_documents", {"call_id": 5, "transcript": "test", "loan_id": 1}),
        ("get_missing_documents", {"loan_id": 1}),
        ("get_document_completeness", {"loan_id": 1}),
        ("cross_validate_documents", {"loan_id": 1}),
        ("create_follow_up", {"loan_id": 1, "borrower_id": 10, "request_ids": "1,2"}),
        ("get_income_tasks", {"loan_id": 1}),
        ("get_bank_analysis_flags", {"loan_id": 1}),
        ("generate_needs_list", {"loan_id": 1, "loan_program": "conventional",
                                 "occupancy_type": "primary", "income_type": "w2",
                                 "borrower_id": 10}),
        ("get_document_status_summary", {"loan_id": 1}),
    ])
    def test_loan_tools_reject_cross_tenant(
        self, agent_org_b, mock_db, tool_name, input_data
    ):
        """All loan-based tools must reject access when loan belongs to a different org."""
        with patch("database.SessionLocal", return_value=mock_db):
            result = asyncio.get_event_loop().run_until_complete(
                agent_org_b.tools[tool_name].handler(input_data, agent_org_b.context)
            )
            # The tool should either return error=True via ToolResult or raise
            assert result.success is False or (hasattr(result, 'error') and result.error)

    @pytest.mark.parametrize("tool_name,input_data", [
        ("classify_document", {"document_id": 10}),
        ("review_document", {"document_id": 10}),
    ])
    def test_document_tools_reject_cross_tenant(
        self, agent_org_b, mock_db, tool_name, input_data
    ):
        """Document-based tools must reject access when document's loan belongs to a different org."""
        with patch("database.SessionLocal", return_value=mock_db):
            result = asyncio.get_event_loop().run_until_complete(
                agent_org_b.tools[tool_name].handler(input_data, agent_org_b.context)
            )
            assert result.success is False or (hasattr(result, 'error') and result.error)

    def test_error_message_does_not_leak_org_id(self, agent_org_b, mock_db):
        """Error messages must not contain organization identifiers."""
        with patch("database.SessionLocal", return_value=mock_db):
            result = asyncio.get_event_loop().run_until_complete(
                agent_org_b.tools["get_missing_documents"].handler(
                    {"loan_id": 1}, agent_org_b.context
                )
            )
            if result.error:
                assert ORG_A not in result.error
                assert ORG_B not in result.error

    def test_org_check_runs_before_service_call(self, agent_org_a, mock_db):
        """The tenant isolation check must execute before any service layer call."""
        _allow_org_check(mock_db, loan_id=1, org_id=ORG_A)

        with patch("database.SessionLocal", return_value=mock_db):
            with patch(
                "services.smart_docs.pos_analyzer_service.get_pos_analyzer_service"
            ) as mock_service:
                mock_svc = MagicMock()
                mock_result = MagicMock()
                mock_result.success = True
                mock_result.total_documents_needed = 5
                mock_result.categories = {}
                mock_result.requirements = []
                mock_result.analysis_notes = []
                mock_svc.analyze_application.return_value = mock_result
                mock_service.return_value = mock_svc

                result = asyncio.get_event_loop().run_until_complete(
                    agent_org_a.tools["analyze_application_for_documents"].handler(
                        {"loan_id": 1}, agent_org_a.context
                    )
                )

                # The first execute call should be the org check
                first_call_args = mock_db.execute.call_args_list[0]
                query_str = str(first_call_args[0][0])
                assert "organization_id" in query_str


# ---------------------------------------------------------------------------
# Tests: DocumentReviewAgent Tenant Isolation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDocumentReviewAgentTenantIsolation:
    """Verify DocumentReviewAgent rejects cross-tenant access."""

    @pytest.fixture
    def agent_org_b(self, context_org_b):
        from agents.specialized.document_review_agent import DocumentReviewAgent
        return DocumentReviewAgent(context_org_b)

    @pytest.mark.parametrize("tool_name,input_data", [
        ("cross_validate_documents", {"loan_id": 1}),
        ("validate_employer_info", {"loan_id": 1}),
        ("validate_account_numbers", {"loan_id": 1}),
        ("generate_condition_from_review", {
            "loan_id": 1, "document_id": 10,
            "finding_type": "quality_issue",
            "description": "test", "severity": "MEDIUM",
        }),
        ("bulk_review_loan_documents", {"loan_id": 1}),
        ("create_review_summary", {"loan_id": 1}),
    ])
    def test_loan_tools_reject_cross_tenant(
        self, agent_org_b, mock_db, tool_name, input_data
    ):
        """Loan-based tools must reject cross-tenant access."""
        with patch("database.SessionLocal", return_value=mock_db):
            result = asyncio.get_event_loop().run_until_complete(
                agent_org_b.tools[tool_name].handler(input_data, agent_org_b.context)
            )
            assert result.success is False or (hasattr(result, 'error') and result.error)

    @pytest.mark.parametrize("tool_name,input_data", [
        ("review_document_quality", {"document_id": 10}),
        ("verify_document_type", {"document_id": 10}),
        ("check_document_freshness", {"document_id": 10}),
        ("check_document_completeness", {"document_id": 10}),
        ("detect_fraud_indicators", {"document_id": 10}),
        ("assess_overall_document_risk", {"document_id": 10}),
        ("recommend_review_action", {"document_id": 10}),
    ])
    def test_document_tools_reject_cross_tenant(
        self, agent_org_b, mock_db, tool_name, input_data
    ):
        """Document-based tools must reject cross-tenant access."""
        with patch("database.SessionLocal", return_value=mock_db):
            result = asyncio.get_event_loop().run_until_complete(
                agent_org_b.tools[tool_name].handler(input_data, agent_org_b.context)
            )
            assert result.success is False or (hasattr(result, 'error') and result.error)

    def test_error_message_does_not_leak_org_id(self, agent_org_b, mock_db):
        """Error messages must not contain organization identifiers."""
        with patch("database.SessionLocal", return_value=mock_db):
            result = asyncio.get_event_loop().run_until_complete(
                agent_org_b.tools["bulk_review_loan_documents"].handler(
                    {"loan_id": 1}, agent_org_b.context
                )
            )
            if result.error:
                assert ORG_A not in result.error
                assert ORG_B not in result.error


# ---------------------------------------------------------------------------
# Tests: IncomeAnalysisAgent Tenant Isolation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIncomeAnalysisAgentTenantIsolation:
    """Verify IncomeAnalysisAgent rejects cross-tenant access via _verify_loan_ownership."""

    @pytest.fixture
    def agent_org_b(self, context_org_b):
        from agents.specialized.income_analysis_agent import IncomeAnalysisAgent
        return IncomeAnalysisAgent(context_org_b)

    @pytest.mark.parametrize("tool_name", [
        "analyze_paystubs",
        "analyze_w2s",
        "analyze_tax_returns",
        "calculate_qualifying_income",
        "analyze_income_trends",
        "check_employment_gaps",
        "verify_income_consistency",
        "calculate_dti_ratios",
        "analyze_self_employment_income",
        "evaluate_non_traditional_income",
        "generate_income_findings",
        "assess_income_stability",
        "compare_stated_vs_documented",
        "get_income_task_queue",
        "create_income_condition",
    ])
    def test_all_tools_reject_cross_tenant(
        self, agent_org_b, mock_db, tool_name
    ):
        """Every tool must fail when the loan belongs to a different org."""
        # Build minimal input (all tools require loan_id at minimum)
        input_data = {"loan_id": 1}
        # Some tools need extra params
        if tool_name in ("calculate_dti_ratios",):
            input_data["housing_expense"] = 2000
        if tool_name in ("create_income_condition",):
            input_data["finding_type"] = "variance"
            input_data["description"] = "test"

        with patch("database.SessionLocal", return_value=mock_db):
            result = asyncio.get_event_loop().run_until_complete(
                agent_org_b.tools[tool_name].handler(input_data, agent_org_b.context)
            )
            assert result.success is False or (hasattr(result, 'error') and result.error)


# ---------------------------------------------------------------------------
# Tests: DocumentFollowUpAgent Tenant Isolation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDocumentFollowUpAgentTenantIsolation:
    """Verify DocumentFollowUpAgent rejects cross-tenant access."""

    @pytest.fixture
    def agent_org_b(self, context_org_b):
        from agents.specialized.document_followup_agent import DocumentFollowUpAgent
        return DocumentFollowUpAgent(context_org_b)

    @pytest.mark.parametrize("tool_name", [
        "select_followup_channel",
        "draft_followup_message",
        "evaluate_borrower_responsiveness",
        "schedule_followup_sequence",
        "optimize_contact_timing",
        "schedule_document_appointment",
        "create_borrower_portal_notification",
        "pause_followup_on_receipt",
    ])
    def test_loan_tools_reject_cross_tenant(
        self, agent_org_b, mock_db, tool_name
    ):
        """All follow-up tools must reject cross-tenant loan access."""
        input_data = {"loan_id": 1}
        # Add extra required params
        if tool_name == "draft_followup_message":
            input_data["message_type"] = "email"
            input_data["doc_types"] = "PAYSTUB"
        if tool_name == "schedule_followup_sequence":
            input_data["request_ids"] = "1,2"
        if tool_name == "schedule_document_appointment":
            input_data["appointment_type"] = "document_review"
        if tool_name == "create_borrower_portal_notification":
            input_data["notification_type"] = "missing_documents"
        if tool_name == "pause_followup_on_receipt":
            input_data["document_type"] = "PAYSTUB"

        with patch("database.SessionLocal", return_value=mock_db):
            result = asyncio.get_event_loop().run_until_complete(
                agent_org_b.tools[tool_name].handler(input_data, agent_org_b.context)
            )
            assert result.success is False or (hasattr(result, 'error') and result.error)

    def test_escalate_tool_rejects_cross_tenant_campaign(
        self, agent_org_b, mock_db
    ):
        """escalate_to_loan_officer must reject access to another org's campaign."""
        input_data = {"loan_id": 1, "campaign_id": 5, "reason": "test"}

        with patch("database.SessionLocal", return_value=mock_db):
            result = asyncio.get_event_loop().run_until_complete(
                agent_org_b.tools["escalate_to_loan_officer"].handler(
                    input_data, agent_org_b.context
                )
            )
            assert result.success is False or (hasattr(result, 'error') and result.error)


# ---------------------------------------------------------------------------
# Tests: Error Message Safety (Cross-Agent)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestErrorMessageSafety:
    """Verify no agent leaks organization identifiers in error responses."""

    AGENTS_AND_TOOLS = [
        ("document_intelligence_agent", "DocumentIntelligenceAgent", "get_missing_documents", {"loan_id": 1}),
        ("document_review_agent", "DocumentReviewAgent", "bulk_review_loan_documents", {"loan_id": 1}),
        ("income_analysis_agent", "IncomeAnalysisAgent", "calculate_qualifying_income", {"loan_id": 1}),
        ("document_followup_agent", "DocumentFollowUpAgent", "select_followup_channel", {"loan_id": 1}),
    ]

    @pytest.mark.parametrize("module,cls_name,tool_name,input_data", AGENTS_AND_TOOLS)
    def test_no_org_id_in_error(
        self, context_org_b, mock_db, module, cls_name, tool_name, input_data
    ):
        """Error messages must never contain organization identifiers."""
        import importlib
        mod = importlib.import_module(f"agents.specialized.{module}")
        AgentClass = getattr(mod, cls_name)
        agent = AgentClass(context_org_b)

        with patch("database.SessionLocal", return_value=mock_db):
            result = asyncio.get_event_loop().run_until_complete(
                agent.tools[tool_name].handler(input_data, agent.context)
            )

        # Check error field
        error_text = str(result.error or "") + str(result.message or "")
        assert ORG_A not in error_text, f"Org A ({ORG_A}) leaked in error: {error_text}"
        assert ORG_B not in error_text, f"Org B ({ORG_B}) leaked in error: {error_text}"
        # Should not contain any org_id-like pattern
        assert not re.search(r"org_\d+", error_text), f"Org ID pattern found in error: {error_text}"
