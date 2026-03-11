"""
Test Document Intelligence Agent - Comprehensive tests for the DocumentIntelligenceAgent
and all 15 of its tools.

Covers:
- Agent initialization and tool registration
- classify_document tool - AI document classification
- analyze_application_for_documents tool - POS analysis for doc requirements
- review_document tool - AI-powered review (approve/reject)
- batch_review_loan_documents tool - batch processing all unreviewed docs
- calculate_income tool - income calculation from financial docs
- analyze_bank_statements tool - bank statement red flag analysis
- analyze_call_for_documents tool - call transcript extraction
- get_missing_documents tool - missing docs list
- get_document_completeness tool - completeness report
- cross_validate_documents tool - cross-document consistency checks
- create_follow_up tool - follow-up campaign creation
- get_income_tasks tool - pending income verification tasks
- generate_needs_list tool - needs list generation
- get_document_status_summary tool - comprehensive status summary
- Tenant isolation enforcement (require_org_id)
- Error handling for missing/inaccessible data
- System prompt content validation
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, PropertyMock
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Lightweight stand-ins for base module types so we don't need the full
# application import chain (langchain, sqlalchemy, etc.) just to unit-test
# the agent logic.
# ---------------------------------------------------------------------------


@dataclass
class _MockToolResult:
    """Mirror of agents.specialized.base.ToolResult for assertion helpers."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# ---------------------------------------------------------------------------
# Helpers to build mock DB row objects returned by fetchone / fetchall
# ---------------------------------------------------------------------------

class MockRow:
    """Simulate a SQLAlchemy Row object with attribute access."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def _mapping(self):
        return self.__dict__


def _make_loan_row(loan_id=1, loan_number="LN-2026-001", borrower_name="John Doe",
                   org_id="org_42", stage="PROCESSING"):
    return MockRow(
        id=loan_id,
        loan_number=loan_number,
        borrower_name=borrower_name,
        organization_id=org_id,
        stage=stage,
    )


def _make_doc_row(doc_id=10, filename="paystub.pdf", doc_type="PAYSTUB",
                  mime_type="application/pdf", loan_id=1, loan_number="LN-2026-001",
                  review_decision=None):
    return MockRow(
        id=doc_id,
        filename=filename,
        doc_type=doc_type,
        mime_type=mime_type,
        loan_id=loan_id,
        loan_number=loan_number,
        review_decision=review_decision,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agent_context() -> Dict[str, Any]:
    """Standard agent context with organization_id for tenant isolation."""
    return {
        "user_id": "user_7",
        "user_email": "lo@example.com",
        "user_role": "loan_officer",
        "organization_id": "org_42",
        "autonomous_mode": True,
        "permissions": ["read", "write"],
    }


@pytest.fixture
def agent_context_no_org() -> Dict[str, Any]:
    """Agent context WITHOUT organization_id -- triggers tenant isolation error."""
    return {
        "user_id": "user_7",
        "user_email": "lo@example.com",
        "user_role": "loan_officer",
        "autonomous_mode": True,
        "permissions": ["read"],
    }


@pytest.fixture
def mock_db_session():
    """Create a mock DB session with chainable execute().fetchone()/fetchall()."""
    session = MagicMock()
    session.close = MagicMock()
    return session


@pytest.fixture
def _patch_session_local(mock_db_session):
    """Patch database.SessionLocal to return our mock session."""
    with patch("database.SessionLocal", return_value=mock_db_session):
        yield mock_db_session


@pytest.fixture
def agent(agent_context):
    """Instantiate a DocumentIntelligenceAgent with a mocked context."""
    from agents.specialized.document_intelligence_agent import DocumentIntelligenceAgent
    return DocumentIntelligenceAgent(agent_context)


# ---------------------------------------------------------------------------
# 1. Agent Initialization & Registration
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAgentInitialization:
    """Verify agent identity, tool count, and registry integration."""

    def test_agent_name(self, agent):
        assert agent.name == "DocumentIntelligenceAgent"

    def test_agent_description_mentions_document(self, agent):
        desc = agent.description.lower()
        assert "document" in desc

    def test_agent_registers_15_tools(self, agent):
        assert len(agent.tools) == 15, (
            f"Expected 15 tools but found {len(agent.tools)}: "
            f"{sorted(agent.tools.keys())}"
        )

    def test_expected_tool_names_present(self, agent):
        expected = {
            "analyze_application_for_documents",
            "classify_document",
            "review_document",
            "batch_review_loan_documents",
            "calculate_income",
            "analyze_bank_statements",
            "analyze_call_for_documents",
            "get_missing_documents",
            "get_document_completeness",
            "cross_validate_documents",
            "create_follow_up",
            "get_income_tasks",
            "get_bank_analysis_flags",
            "generate_needs_list",
            "get_document_status_summary",
        }
        assert set(agent.tools.keys()) == expected

    def test_agent_registered_in_registry(self):
        from agents.specialized.base import AgentRegistry
        ctx = {
            "user_id": "u1",
            "organization_id": "org_1",
            "autonomous_mode": True,
        }
        instance = AgentRegistry.get_agent("DocumentIntelligenceAgent", ctx)
        assert instance is not None
        assert instance.name == "DocumentIntelligenceAgent"

    def test_registry_intent_routing_document_intelligence(self):
        from agents.specialized.base import AgentRegistry
        ctx = {
            "user_id": "u1",
            "organization_id": "org_1",
            "autonomous_mode": True,
        }
        routed = AgentRegistry.get_agent_for_intent("document intelligence", ctx)
        assert routed is not None
        assert routed.name == "DocumentIntelligenceAgent"

    def test_registry_intent_routing_classify_document(self):
        from agents.specialized.base import AgentRegistry
        ctx = {
            "user_id": "u1",
            "organization_id": "org_1",
            "autonomous_mode": True,
        }
        routed = AgentRegistry.get_agent_for_intent("classify document", ctx)
        assert routed is not None
        assert routed.name == "DocumentIntelligenceAgent"


# ---------------------------------------------------------------------------
# 2. System Prompt Content Validation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSystemPromptContent:
    """Verify the agent docstring/description contains expected capability info."""

    def test_description_mentions_classification(self, agent):
        assert "classification" in agent.description.lower()

    def test_description_mentions_review(self, agent):
        assert "review" in agent.description.lower()

    def test_description_mentions_income(self, agent):
        assert "income" in agent.description.lower()

    def test_description_mentions_bank_statement(self, agent):
        assert "bank statement" in agent.description.lower()

    def test_description_mentions_cross_validation(self, agent):
        assert "cross-validation" in agent.description.lower()


# ---------------------------------------------------------------------------
# 3. Tenant Isolation Enforcement
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTenantIsolation:
    """Every data-access tool must call require_org_id(), which raises when
    organization_id is missing from the context."""

    def test_require_org_id_returns_org(self, agent):
        assert agent.require_org_id() == "org_42"

    def test_require_org_id_raises_without_org(self, agent_context_no_org):
        from agents.specialized.document_intelligence_agent import DocumentIntelligenceAgent
        agent_no_org = DocumentIntelligenceAgent(agent_context_no_org)
        with pytest.raises(ValueError, match="requires organization_id"):
            agent_no_org.require_org_id()

    @pytest.mark.asyncio
    async def test_analyze_application_fails_without_org(self, agent_context_no_org, _patch_session_local):
        from agents.specialized.document_intelligence_agent import DocumentIntelligenceAgent
        agent_no_org = DocumentIntelligenceAgent(agent_context_no_org)
        result = await agent_no_org.execute_tool(
            "analyze_application_for_documents",
            {"loan_id": 1},
        )
        assert result.success is False
        assert "organization_id" in (result.error or "")

    @pytest.mark.asyncio
    async def test_classify_document_fails_without_org(self, agent_context_no_org, _patch_session_local):
        from agents.specialized.document_intelligence_agent import DocumentIntelligenceAgent
        agent_no_org = DocumentIntelligenceAgent(agent_context_no_org)
        result = await agent_no_org.execute_tool(
            "classify_document",
            {"document_id": 10},
        )
        assert result.success is False
        assert "organization_id" in (result.error or "")

    @pytest.mark.asyncio
    async def test_get_missing_documents_fails_without_org(self, agent_context_no_org, _patch_session_local):
        from agents.specialized.document_intelligence_agent import DocumentIntelligenceAgent
        agent_no_org = DocumentIntelligenceAgent(agent_context_no_org)
        result = await agent_no_org.execute_tool(
            "get_missing_documents",
            {"loan_id": 1},
        )
        assert result.success is False
        assert "organization_id" in (result.error or "")


# ---------------------------------------------------------------------------
# 4. classify_document Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestClassifyDocumentTool:
    """classify_document should verify ownership then call AI classifier."""

    @pytest.mark.asyncio
    async def test_classify_document_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "classify_document",
            {"document_id": 999},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower() or "access denied" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_classify_document_success(self, agent, _patch_session_local, mock_db_session):
        doc_row = _make_doc_row()
        mock_db_session.execute.return_value.fetchone.return_value = doc_row

        mock_classifier = MagicMock()
        mock_classifier.classify_document.return_value = MagicMock(
            success=True,
            predicted_type="W2",
            confidence=95.0,
            alternatives=[{"type": "1099", "confidence": 3.0}],
            features_detected=["employer_name", "wages"],
            model_used="gpt-4o",
            duration_ms=320,
        )

        mock_s3 = MagicMock()
        mock_s3.download_file.return_value = b"fake-pdf-bytes"

        with patch(
            "services.smart_docs.ai_classifier_service.get_ai_classifier_service",
            return_value=mock_classifier,
        ), patch(
            "services.smart_docs.s3_storage_service.get_smart_docs_s3_service",
            return_value=mock_s3,
        ):
            result = await agent.execute_tool(
                "classify_document",
                {"document_id": 10},
            )

        assert result.success is True
        assert result.data["predicted_type"] == "W2"
        assert result.data["confidence"] == 95.0

    @pytest.mark.asyncio
    async def test_classify_document_no_file_bytes(self, agent, _patch_session_local, mock_db_session):
        doc_row = _make_doc_row()
        mock_db_session.execute.return_value.fetchone.return_value = doc_row

        mock_s3 = MagicMock()
        mock_s3.download_file.return_value = None

        with patch(
            "services.smart_docs.s3_storage_service.get_smart_docs_s3_service",
            return_value=mock_s3,
        ):
            result = await agent.execute_tool(
                "classify_document",
                {"document_id": 10},
            )

        assert result.success is False
        assert "could not retrieve" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# 5. analyze_application_for_documents Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyzeApplicationTool:

    @pytest.mark.asyncio
    async def test_analyze_application_loan_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "analyze_application_for_documents",
            {"loan_id": 999},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_analyze_application_success(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        mock_db_session.execute.return_value.fetchone.return_value = loan_row

        mock_req = MagicMock(
            doc_type="W2", title="W-2 Wage Statement", description="Most recent W-2",
            category="income", priority="HIGH", applies_to="BORROWER",
            required_count=2, freshness_days=365, reason="Verify employment income",
        )
        mock_result = MagicMock(
            success=True,
            total_documents_needed=5,
            categories=["income", "assets", "identity"],
            requirements=[mock_req],
            analysis_notes="Standard conventional requirements",
        )

        mock_service = MagicMock()
        mock_service.analyze_application.return_value = mock_result

        with patch(
            "services.smart_docs.pos_analyzer_service.get_pos_analyzer_service",
            return_value=mock_service,
        ):
            result = await agent.execute_tool(
                "analyze_application_for_documents",
                {"loan_id": 1},
            )

        assert result.success is True
        assert result.data["total_documents_needed"] == 5
        assert len(result.data["requirements"]) == 1
        assert result.data["requirements"][0]["doc_type"] == "W2"


# ---------------------------------------------------------------------------
# 6. review_document Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestReviewDocumentTool:

    @pytest.mark.asyncio
    async def test_review_document_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "review_document",
            {"document_id": 999},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower() or "access denied" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_review_document_accept(self, agent, _patch_session_local, mock_db_session):
        doc_row = _make_doc_row()
        mock_db_session.execute.return_value.fetchone.return_value = doc_row

        mock_decision = MagicMock(
            decision="ACCEPT",
            confidence=92,
            reasons=["Document is clear and complete"],
            rejection_category=None,
            fix_instructions=None,
            quality_score=95,
            completeness_score=100,
            readability_score=90,
            freshness_valid=True,
            type_match=True,
            name_match=True,
            auto_approved=True,
            needs_human_review=False,
            review_priority="LOW",
        )

        mock_review_service = MagicMock()
        mock_review_service.review_document.return_value = mock_decision

        with patch(
            "services.smart_docs.ai_review_service.get_ai_review_service",
            return_value=mock_review_service,
        ):
            result = await agent.execute_tool(
                "review_document",
                {"document_id": 10},
            )

        assert result.success is True
        assert result.data["decision"] == "ACCEPT"
        assert result.data["auto_approved"] is True


# ---------------------------------------------------------------------------
# 7. batch_review_loan_documents Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBatchReviewTool:

    @pytest.mark.asyncio
    async def test_batch_review_loan_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "batch_review_loan_documents",
            {"loan_id": 999},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_batch_review_no_unreviewed(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        # First call returns loan, second returns empty list
        mock_db_session.execute.return_value.fetchone.return_value = loan_row
        mock_db_session.execute.return_value.fetchall.return_value = []

        result = await agent.execute_tool(
            "batch_review_loan_documents",
            {"loan_id": 1},
        )

        assert result.success is True
        assert result.data["total_reviewed"] == 0

    @pytest.mark.asyncio
    async def test_batch_review_processes_documents(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()

        # We need to handle multiple execute() calls differently
        call_count = {"n": 0}
        original_execute = mock_db_session.execute

        def side_effect_execute(*args, **kwargs):
            call_count["n"] += 1
            mock_result = MagicMock()
            if call_count["n"] == 1:
                # First call: loan lookup
                mock_result.fetchone.return_value = loan_row
            else:
                # Second call: unreviewed docs
                mock_result.fetchall.return_value = [
                    _make_doc_row(doc_id=10, filename="w2.pdf", doc_type="W2"),
                    _make_doc_row(doc_id=11, filename="bank.pdf", doc_type="BANK_STATEMENT"),
                ]
            return mock_result

        mock_db_session.execute.side_effect = side_effect_execute

        mock_decision = MagicMock(
            decision="ACCEPT", confidence=90, reasons=["OK"],
        )
        mock_review_service = MagicMock()
        mock_review_service.review_document.return_value = mock_decision

        with patch(
            "services.smart_docs.ai_review_service.get_ai_review_service",
            return_value=mock_review_service,
        ):
            result = await agent.execute_tool(
                "batch_review_loan_documents",
                {"loan_id": 1},
            )

        assert result.success is True
        assert result.data["total_reviewed"] == 2
        assert result.data["accepted"] == 2
        assert result.data["rejected"] == 0


# ---------------------------------------------------------------------------
# 8. calculate_income Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCalculateIncomeTool:

    @pytest.mark.asyncio
    async def test_calculate_income_loan_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "calculate_income",
            {"loan_id": 999, "borrower_id": 1},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_calculate_income_success(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        mock_db_session.execute.return_value.fetchone.return_value = loan_row

        mock_source = MagicMock(
            source_type="W2",
            employer="Acme Corp",
            monthly_amount=8500.00,
            annual_amount=102000.00,
            calculation_method="ytd_average",
            confidence=95,
        )
        mock_calc_result = MagicMock(
            success=True,
            total_qualifying_monthly=8500.00,
            total_qualifying_annual=102000.00,
            calculation_method="standard",
            dti_front_end=28.5,
            dti_back_end=42.1,
            confidence=95,
            sources=[mock_source],
            flags=["Declining YTD trend"],
            recommendations=["Request VOE"],
            tasks_to_create=[],
        )

        mock_service = MagicMock()
        mock_service.calculate_income.return_value = mock_calc_result

        with patch(
            "services.smart_docs.income_calculator_service.get_income_calculator_service",
            return_value=mock_service,
        ):
            result = await agent.execute_tool(
                "calculate_income",
                {"loan_id": 1, "borrower_id": 100},
            )

        assert result.success is True
        assert result.data["total_qualifying_monthly"] == 8500.00
        assert result.data["dti_front_end"] == 28.5
        assert len(result.data["sources"]) == 1
        assert result.data["sources"][0]["employer"] == "Acme Corp"


# ---------------------------------------------------------------------------
# 9. analyze_bank_statements Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyzeBankStatementsTool:

    @pytest.mark.asyncio
    async def test_bank_statements_loan_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "analyze_bank_statements",
            {"loan_id": 999, "borrower_id": 1},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_bank_statements_no_data_no_statements(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock = MagicMock()
            if call_count["n"] == 1:
                mock.fetchone.return_value = loan_row
            elif call_count["n"] == 2:
                mock.fetchall.return_value = []  # No analyses
            else:
                mock.fetchone.return_value = MockRow(cnt=0)  # No bank statements
            return mock

        mock_db_session.execute.side_effect = side_effect

        result = await agent.execute_tool(
            "analyze_bank_statements",
            {"loan_id": 1, "borrower_id": 100},
        )

        assert result.success is True
        assert result.data["status"] == "no_statements"

    @pytest.mark.asyncio
    async def test_bank_statements_with_analysis(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        analysis_row = MockRow(
            id=1, document_id=10,
            statement_period_start="2026-01-01", statement_period_end="2026-01-31",
            beginning_balance=5000.00, ending_balance=4200.00,
            total_deposits=3000.00, total_withdrawals=3800.00,
            large_deposit_count=1, nsf_count=0,
            flags=[{"type": "large_deposit", "amount": 2500, "description": "Unexplained deposit"}],
            status="completed", analyzed_at="2026-02-05",
        )

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock = MagicMock()
            if call_count["n"] == 1:
                mock.fetchone.return_value = loan_row
            else:
                mock.fetchall.return_value = [analysis_row]
            return mock

        mock_db_session.execute.side_effect = side_effect

        result = await agent.execute_tool(
            "analyze_bank_statements",
            {"loan_id": 1, "borrower_id": 100},
        )

        assert result.success is True
        assert result.data["risk_level"] == "medium"
        assert result.data["total_large_deposits"] == 1
        assert result.data["total_nsf_events"] == 0
        assert len(result.data["statements"]) == 1


# ---------------------------------------------------------------------------
# 10. analyze_call_for_documents Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyzeCallTool:

    @pytest.mark.asyncio
    async def test_analyze_call_loan_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "analyze_call_for_documents",
            {"call_id": 1, "transcript": "test", "loan_id": 999},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_analyze_call_success(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        mock_db_session.execute.return_value.fetchone.return_value = loan_row

        mock_need = MagicMock(
            doc_type="BANK_STATEMENT", confidence=0.92,
            source="call_transcript", reason="Borrower mentioned bank account",
            auto_created=True,
        )
        mock_call_result = MagicMock(
            success=True,
            total_needs=2,
            auto_create_count=1,
            circumstances_detected=["self_employed"],
            summary="Borrower discussed income docs and bank statements",
            document_needs=[mock_need],
        )

        mock_extractor = MagicMock()
        mock_extractor.analyze_call.return_value = mock_call_result

        with patch(
            "services.smart_docs.call_intel_extractor.get_call_intel_extractor",
            return_value=mock_extractor,
        ):
            result = await agent.execute_tool(
                "analyze_call_for_documents",
                {"call_id": 42, "transcript": "I have my bank statements ready", "loan_id": 1},
            )

        assert result.success is True
        assert result.data["total_needs_detected"] == 2
        assert result.data["auto_created_requests"] == 1
        assert result.data["document_needs"][0]["doc_type"] == "BANK_STATEMENT"


# ---------------------------------------------------------------------------
# 11. get_missing_documents Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetMissingDocumentsTool:

    @pytest.mark.asyncio
    async def test_missing_docs_loan_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "get_missing_documents",
            {"loan_id": 999},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_missing_docs_returns_list(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        open_request = MockRow(
            id=5, doc_type="TAX_RETURN", title="2025 Tax Return",
            priority="CRITICAL", applies_to="BORROWER", status="OPEN",
        )

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock = MagicMock()
            if call_count["n"] == 1:
                mock.fetchone.return_value = loan_row
            elif call_count["n"] == 2:
                mock.fetchall.return_value = [open_request]
            elif call_count["n"] == 3:
                mock.fetchone.return_value = MockRow(cnt=8)  # received count
            else:
                mock.fetchone.return_value = MockRow(cnt=12)  # total count
            return mock

        mock_db_session.execute.side_effect = side_effect

        result = await agent.execute_tool(
            "get_missing_documents",
            {"loan_id": 1},
        )

        assert result.success is True
        assert result.data["missing_count"] == 1
        assert result.data["missing_documents"][0]["doc_type"] == "TAX_RETURN"
        assert result.data["critical_missing"] == 1


# ---------------------------------------------------------------------------
# 12. get_document_completeness Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetDocumentCompletenessTool:

    @pytest.mark.asyncio
    async def test_completeness_loan_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "get_document_completeness",
            {"loan_id": 999},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_completeness_no_requests(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock = MagicMock()
            if call_count["n"] == 1:
                mock.fetchone.return_value = loan_row
            else:
                mock.fetchall.return_value = []
            return mock

        mock_db_session.execute.side_effect = side_effect

        result = await agent.execute_tool(
            "get_document_completeness",
            {"loan_id": 1},
        )

        assert result.success is True
        assert result.data["overall_completeness"] == 0

    @pytest.mark.asyncio
    async def test_completeness_calculation(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        cat_stat = MockRow(
            category="income", total=4, accepted=3, open=1,
            rejected=0, pending_review=0, waived=0,
        )

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock = MagicMock()
            if call_count["n"] == 1:
                mock.fetchone.return_value = loan_row
            else:
                mock.fetchall.return_value = [cat_stat]
            return mock

        mock_db_session.execute.side_effect = side_effect

        result = await agent.execute_tool(
            "get_document_completeness",
            {"loan_id": 1},
        )

        assert result.success is True
        # 3 accepted out of 4 = 75%
        assert result.data["overall_completeness"] == 75.0
        assert result.data["total_required"] == 4
        assert result.data["total_completed"] == 3


# ---------------------------------------------------------------------------
# 13. cross_validate_documents Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCrossValidateDocumentsTool:

    @pytest.mark.asyncio
    async def test_cross_validate_loan_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "cross_validate_documents",
            {"loan_id": 999},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_cross_validate_insufficient_docs(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock = MagicMock()
            if call_count["n"] == 1:
                mock.fetchone.return_value = loan_row
            else:
                mock.fetchall.return_value = [_make_doc_row()]  # Only 1 doc
            return mock

        mock_db_session.execute.side_effect = side_effect

        result = await agent.execute_tool(
            "cross_validate_documents",
            {"loan_id": 1},
        )

        assert result.success is True
        assert result.data["status"] == "insufficient_data"

    @pytest.mark.asyncio
    async def test_cross_validate_name_discrepancy(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        doc1 = MockRow(
            id=10, doc_type="W2", filename="w2.pdf",
            extracted_data=None, extracted_name="John Doe",
            extracted_address="123 Main St", extracted_employer="Acme",
            extracted_income=8500,
        )
        doc2 = MockRow(
            id=11, doc_type="PAYSTUB", filename="paystub.pdf",
            extracted_data=None, extracted_name="Jon Doe",  # Different spelling
            extracted_address="123 Main St", extracted_employer="Acme",
            extracted_income=8500,
        )

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock = MagicMock()
            if call_count["n"] == 1:
                mock.fetchone.return_value = loan_row
            else:
                mock.fetchall.return_value = [doc1, doc2]
            return mock

        mock_db_session.execute.side_effect = side_effect

        result = await agent.execute_tool(
            "cross_validate_documents",
            {"loan_id": 1},
        )

        assert result.success is True
        assert result.data["inconsistency_count"] >= 1
        name_issue = [i for i in result.data["inconsistencies"] if i["field"] == "name"]
        assert len(name_issue) == 1
        assert name_issue[0]["severity"] == "high"

    @pytest.mark.asyncio
    async def test_cross_validate_clean_result(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        doc1 = MockRow(
            id=10, doc_type="W2", filename="w2.pdf",
            extracted_data=None, extracted_name="John Doe",
            extracted_address="123 Main St", extracted_employer="Acme",
            extracted_income=8500,
        )
        doc2 = MockRow(
            id=11, doc_type="PAYSTUB", filename="paystub.pdf",
            extracted_data=None, extracted_name="John Doe",
            extracted_address="123 Main St", extracted_employer="Acme",
            extracted_income=8500,
        )

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock = MagicMock()
            if call_count["n"] == 1:
                mock.fetchone.return_value = loan_row
            else:
                mock.fetchall.return_value = [doc1, doc2]
            return mock

        mock_db_session.execute.side_effect = side_effect

        result = await agent.execute_tool(
            "cross_validate_documents",
            {"loan_id": 1},
        )

        assert result.success is True
        assert result.data["risk_assessment"] == "clean"
        assert result.data["inconsistency_count"] == 0


# ---------------------------------------------------------------------------
# 14. create_follow_up Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCreateFollowUpTool:

    @pytest.mark.asyncio
    async def test_create_follow_up_loan_not_found(self, agent, _patch_session_local, mock_db_session):
        # First call for parsing IDs succeeds, second for loan lookup fails
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock = MagicMock()
            mock.fetchone.return_value = None
            return mock

        mock_db_session.execute.side_effect = side_effect

        result = await agent.execute_tool(
            "create_follow_up",
            {"loan_id": 999, "borrower_id": 1, "request_ids": "1,2"},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_create_follow_up_invalid_ids(self, agent, _patch_session_local, mock_db_session):
        result = await agent.execute_tool(
            "create_follow_up",
            {"loan_id": 1, "borrower_id": 1, "request_ids": "abc,def"},
        )
        assert result.success is False
        assert "invalid" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_create_follow_up_success(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        mock_db_session.execute.return_value.fetchone.return_value = loan_row

        mock_service = MagicMock()
        mock_service.create_campaign.return_value = {
            "campaign_id": 42,
            "steps": [{"step": 1, "channel": "email"}, {"step": 2, "channel": "sms"}],
            "status": "created",
        }

        with patch(
            "services.smart_docs.followup_automation_service.get_followup_automation_service",
            return_value=mock_service,
        ):
            result = await agent.execute_tool(
                "create_follow_up",
                {"loan_id": 1, "borrower_id": 100, "request_ids": "5,6,7"},
            )

        assert result.success is True
        assert result.data["campaign_id"] == 42
        assert result.data["request_ids"] == [5, 6, 7]
        assert len(result.data["steps"]) == 2


# ---------------------------------------------------------------------------
# 15. get_income_tasks Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetIncomeTasksTool:

    @pytest.mark.asyncio
    async def test_income_tasks_loan_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "get_income_tasks",
            {"loan_id": 999},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_income_tasks_success(self, agent, _patch_session_local, mock_db_session):
        from datetime import datetime as dt
        loan_row = _make_loan_row()
        task_row = MockRow(
            id=1, task_type="VOE", description="Verify employment at Acme",
            priority="HIGH", status="pending",
            assigned_to_user_id=7,
            created_at=dt(2026, 3, 1), due_date=dt(2026, 3, 10),
        )

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock = MagicMock()
            if call_count["n"] == 1:
                mock.fetchone.return_value = loan_row
            else:
                mock.fetchall.return_value = [task_row]
            return mock

        mock_db_session.execute.side_effect = side_effect

        result = await agent.execute_tool(
            "get_income_tasks",
            {"loan_id": 1},
        )

        assert result.success is True
        assert result.data["pending_count"] == 1
        assert result.data["tasks"][0]["task_type"] == "VOE"
        assert result.data["tasks"][0]["priority"] == "HIGH"


# ---------------------------------------------------------------------------
# 16. generate_needs_list Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGenerateNeedsListTool:

    @pytest.mark.asyncio
    async def test_needs_list_loan_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "generate_needs_list",
            {
                "loan_id": 999,
                "loan_program": "conventional",
                "occupancy_type": "primary",
                "income_type": "w2",
                "borrower_id": 1,
            },
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_needs_list_success(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        mock_db_session.execute.return_value.fetchone.return_value = loan_row

        mock_req = MagicMock(
            id=1, doc_type="W2", title="W-2 Statement",
            priority="HIGH", applies_to="BORROWER", category="income",
        )
        mock_generator = MagicMock()
        mock_generator.generate.return_value = [mock_req]

        with patch(
            "services.smart_docs.needs_list_generator.NeedsListGenerator",
            return_value=mock_generator,
        ):
            result = await agent.execute_tool(
                "generate_needs_list",
                {
                    "loan_id": 1,
                    "loan_program": "fha",
                    "occupancy_type": "primary",
                    "income_type": "w2",
                    "borrower_id": 100,
                },
            )

        assert result.success is True
        assert result.data["total_documents"] == 1
        assert result.data["loan_program"] == "fha"
        assert result.data["requests"][0]["doc_type"] == "W2"


# ---------------------------------------------------------------------------
# 17. get_document_status_summary Tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetDocumentStatusSummaryTool:

    @pytest.mark.asyncio
    async def test_status_summary_loan_not_found(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.return_value.fetchone.return_value = None
        result = await agent.execute_tool(
            "get_document_status_summary",
            {"loan_id": 999},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_status_summary_success(self, agent, _patch_session_local, mock_db_session):
        loan_row = _make_loan_row()
        request_stats = MockRow(
            total=10, open=3, pending_review=1, accepted=5, rejected=1, waived=0,
        )
        doc_stats = MockRow(
            total_uploaded=8, approved=5, rejected=1, needs_review=1, unreviewed=1,
        )
        expired = MockRow(cnt=2)
        campaigns = MockRow(cnt=1)

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            mock = MagicMock()
            if call_count["n"] == 1:
                mock.fetchone.return_value = loan_row
            elif call_count["n"] == 2:
                mock.fetchone.return_value = request_stats
            elif call_count["n"] == 3:
                mock.fetchone.return_value = doc_stats
            elif call_count["n"] == 4:
                mock.fetchone.return_value = expired
            else:
                mock.fetchone.return_value = campaigns
            return mock

        mock_db_session.execute.side_effect = side_effect

        result = await agent.execute_tool(
            "get_document_status_summary",
            {"loan_id": 1},
        )

        assert result.success is True
        # 5 accepted + 0 waived out of 10 = 50%
        assert result.data["completeness_pct"] == 50.0
        assert result.data["requests"]["total"] == 10
        assert result.data["requests"]["open"] == 3
        assert result.data["documents"]["total_uploaded"] == 8
        assert result.data["expired_count"] == 2
        assert result.data["active_followup_campaigns"] == 1


# ---------------------------------------------------------------------------
# 18. Error Handling
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestErrorHandling:
    """Tools should catch exceptions and return ToolResult(success=False)."""

    @pytest.mark.asyncio
    async def test_db_exception_returns_error_result(self, agent, _patch_session_local, mock_db_session):
        mock_db_session.execute.side_effect = Exception("DB connection lost")
        result = await agent.execute_tool(
            "get_document_completeness",
            {"loan_id": 1},
        )
        assert result.success is False
        assert "DB connection lost" in (result.error or "")

    @pytest.mark.asyncio
    async def test_nonexistent_tool_returns_error(self, agent):
        result = await agent.execute_tool(
            "does_not_exist",
            {"loan_id": 1},
        )
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_service_exception_in_classify(self, agent, _patch_session_local, mock_db_session):
        doc_row = _make_doc_row()
        mock_db_session.execute.return_value.fetchone.return_value = doc_row

        mock_s3 = MagicMock()
        mock_s3.download_file.return_value = b"bytes"

        mock_classifier = MagicMock()
        mock_classifier.classify_document.side_effect = RuntimeError("Model unavailable")

        with patch(
            "services.smart_docs.ai_classifier_service.get_ai_classifier_service",
            return_value=mock_classifier,
        ), patch(
            "services.smart_docs.s3_storage_service.get_smart_docs_s3_service",
            return_value=mock_s3,
        ):
            result = await agent.execute_tool(
                "classify_document",
                {"document_id": 10},
            )

        assert result.success is False
        assert "model unavailable" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# 19. Tool Categories and Risk Levels
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestToolCategoriesAndRiskLevels:
    """Verify tools are assigned correct categories and risk levels."""

    def test_query_tools_are_low_risk(self, agent):
        from agents.specialized.base import ToolCategory, RiskLevel
        query_tools = agent.get_tools_by_category(ToolCategory.QUERY)
        for tool in query_tools:
            assert tool.risk_level == RiskLevel.LOW, (
                f"Query tool '{tool.name}' should be LOW risk, got {tool.risk_level}"
            )

    def test_analysis_tools_are_low_risk(self, agent):
        from agents.specialized.base import ToolCategory, RiskLevel
        analysis_tools = agent.get_tools_by_category(ToolCategory.ANALYSIS)
        for tool in analysis_tools:
            assert tool.risk_level == RiskLevel.LOW, (
                f"Analysis tool '{tool.name}' should be LOW risk, got {tool.risk_level}"
            )

    def test_action_tools_exist(self, agent):
        from agents.specialized.base import ToolCategory
        action_tools = agent.get_tools_by_category(ToolCategory.ACTION)
        action_names = {t.name for t in action_tools}
        expected_actions = {"review_document", "batch_review_loan_documents",
                           "analyze_call_for_documents", "create_follow_up",
                           "generate_needs_list"}
        assert expected_actions.issubset(action_names), (
            f"Missing expected action tools: {expected_actions - action_names}"
        )

    def test_get_safe_tools_excludes_medium_risk(self, agent):
        safe_tools = agent.get_safe_tools()
        safe_names = {t.name for t in safe_tools}
        # review_document is MEDIUM risk -- should not be in safe tools
        assert "review_document" not in safe_names


# ---------------------------------------------------------------------------
# 20. Input Schema Validation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestInputSchemaValidation:
    """Verify Pydantic input schemas enforce required fields."""

    def test_classify_document_input_requires_document_id(self):
        from agents.specialized.document_intelligence_agent import ClassifyDocumentInput
        with pytest.raises(Exception):
            ClassifyDocumentInput()  # Missing required field

    def test_classify_document_input_valid(self):
        from agents.specialized.document_intelligence_agent import ClassifyDocumentInput
        inp = ClassifyDocumentInput(document_id=10)
        assert inp.document_id == 10

    def test_analyze_application_input_requires_loan_id(self):
        from agents.specialized.document_intelligence_agent import AnalyzeApplicationInput
        with pytest.raises(Exception):
            AnalyzeApplicationInput()

    def test_calculate_income_input_requires_both_ids(self):
        from agents.specialized.document_intelligence_agent import CalculateIncomeInput
        with pytest.raises(Exception):
            CalculateIncomeInput(loan_id=1)  # Missing borrower_id

    def test_generate_needs_list_input_requires_all_fields(self):
        from agents.specialized.document_intelligence_agent import GenerateNeedsListInput
        with pytest.raises(Exception):
            GenerateNeedsListInput(loan_id=1)  # Missing loan_program, occupancy_type, income_type, borrower_id

    def test_create_follow_up_input_valid(self):
        from agents.specialized.document_intelligence_agent import CreateFollowUpInput
        inp = CreateFollowUpInput(loan_id=1, borrower_id=100, request_ids="5,6,7")
        assert inp.request_ids == "5,6,7"

    def test_analyze_call_input_valid(self):
        from agents.specialized.document_intelligence_agent import AnalyzeCallInput
        inp = AnalyzeCallInput(call_id=1, transcript="hello", loan_id=5)
        assert inp.transcript == "hello"
        assert inp.loan_id == 5


# ---------------------------------------------------------------------------
# 21. Tool Definitions for LLM
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestToolDefinitions:
    """Verify get_tool_definitions() returns proper LLM function-calling schema."""

    def test_tool_definitions_count(self, agent):
        defs = agent.get_tool_definitions()
        assert len(defs) == 15

    def test_tool_definitions_have_function_key(self, agent):
        defs = agent.get_tool_definitions()
        for d in defs:
            assert d["type"] == "function"
            assert "function" in d
            assert "name" in d["function"]
            assert "description" in d["function"]

    def test_classify_document_definition_has_schema(self, agent):
        defs = agent.get_tool_definitions()
        classify_def = next(
            (d for d in defs if d["function"]["name"] == "classify_document"), None
        )
        assert classify_def is not None
        params = classify_def["function"]["parameters"]
        assert "properties" in params
        assert "document_id" in params["properties"]
