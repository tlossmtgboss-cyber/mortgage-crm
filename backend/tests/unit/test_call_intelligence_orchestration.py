"""
Tests for Call Intelligence Orchestration module.

Tests the end-to-end orchestration pipeline including:
- Lead creation
- Pre-qualification calculation
- Document checklist generation
- Outreach
- Scheduling
"""

import pytest
from datetime import datetime
from decimal import Decimal

# Import orchestration components
from services.call_intelligence.orchestration.prequal_calculator import (
    PreQualificationCalculator,
    PreQualificationResult,
    QualificationStatus,
    LoanProgram,
)
from services.call_intelligence.orchestration.lead_service import (
    LeadManagementService,
    LeadResult,
    LeadStatus,
    LeadPriority,
)
from services.call_intelligence.orchestration.document_checklist import (
    DocumentChecklistService,
    DocumentChecklist,
    DocumentCategory,
)
from services.call_intelligence.orchestration.outreach_service import (
    OutreachService,
    OutreachResult,
    OutreachType,
)
from services.call_intelligence.orchestration.scheduling_service import (
    SchedulingService,
    ScheduledFollowup,
    AppointmentType,
    FollowupPriority,
)
from services.call_intelligence.orchestration.orchestrator import (
    CallIntelligenceOrchestrator,
    OrchestrationResult,
    OrchestrationConfig,
    OrchestrationStatus,
)


# =============================================================================
# Sample Data
# =============================================================================

SAMPLE_EXTRACTED_DATA = {
    "identity": {
        "first_name": "John",
        "last_name": "Smith",
        "email": "john.smith@example.com",
        "phone": "555-123-4567",
        "estimated_credit_score": 720,
    },
    "property": {
        "purchase_price": 450000,
        "down_payment": 90000,
        "property_type": "single_family",
    },
    "employment": {
        "employer_name": "Acme Corp",
        "job_title": "Software Engineer",
        "is_self_employed": False,
    },
    "financial": {
        "annual_salary": 120000,
        "car_payment": 400,
        "student_loan_payment": 200,
        "checking_balance": 25000,
        "savings_balance": 50000,
    },
    "compliance": {
        "has_bankruptcy": False,
        "has_foreclosure": False,
    },
    "intent": {
        "loan_purpose": "purchase",
        "target_timeline": "60 days",
        "urgency": "high",
        "has_preapproval": False,
        "has_realtor": True,
    },
}


# =============================================================================
# Pre-Qualification Calculator Tests
# =============================================================================

class TestPreQualificationCalculator:
    """Tests for PreQualificationCalculator."""

    def test_calculator_instantiation(self):
        """Test calculator can be instantiated."""
        calculator = PreQualificationCalculator()
        assert calculator is not None

    def test_calculate_with_complete_data(self):
        """Test calculation with complete borrower data."""
        calculator = PreQualificationCalculator()

        # Format data for prequal calculator
        prequal_data = {
            "identity": SAMPLE_EXTRACTED_DATA["identity"],
            "income": SAMPLE_EXTRACTED_DATA["financial"],
            "assets": SAMPLE_EXTRACTED_DATA["financial"],
            "address": SAMPLE_EXTRACTED_DATA["property"],
            "declarations": SAMPLE_EXTRACTED_DATA["compliance"],
        }

        result = calculator.calculate(prequal_data)

        assert isinstance(result, PreQualificationResult)
        assert result.status in [QualificationStatus.QUALIFIED, QualificationStatus.CONDITIONALLY_QUALIFIED]
        assert result.monthly_income > 0
        assert len(result.qualified_programs) > 0

    def test_calculate_insufficient_data(self):
        """Test calculation with insufficient data."""
        calculator = PreQualificationCalculator()

        result = calculator.calculate({})

        assert result.status == QualificationStatus.INSUFFICIENT_DATA
        assert result.data_completeness < 50

    def test_dti_calculation(self):
        """Test DTI ratio calculation."""
        calculator = PreQualificationCalculator()

        prequal_data = {
            "income": {"annual_salary": 120000},
            "liabilities": {"car_payment": 500, "credit_card_payment": 200},
            "address": {"purchase_price": 300000, "down_payment": 60000},
        }

        result = calculator.calculate(prequal_data)

        # Back-end DTI should be calculated
        assert result.back_end_dti >= 0
        assert result.monthly_income == Decimal("10000")  # 120000 / 12

    def test_loan_program_eligibility(self):
        """Test loan program eligibility determination."""
        calculator = PreQualificationCalculator()

        # High credit, 20% down - should qualify for conventional
        prequal_data = {
            "identity": {"estimated_credit_score": 760},
            "income": {"annual_salary": 150000},
            "address": {"purchase_price": 400000, "down_payment": 80000},
        }

        result = calculator.calculate(prequal_data)

        assert LoanProgram.CONVENTIONAL in result.qualified_programs


# =============================================================================
# Lead Management Service Tests
# =============================================================================

class TestLeadManagementService:
    """Tests for LeadManagementService."""

    @pytest.mark.asyncio
    async def test_create_lead(self):
        """Test lead creation from extracted data."""
        service = LeadManagementService()

        result = await service.create_or_update_lead(
            extracted_data=SAMPLE_EXTRACTED_DATA,
            call_id="test-call-001",
        )

        assert result.success
        assert result.lead_id is not None
        assert result.action == "created"

    @pytest.mark.asyncio
    async def test_lead_score_calculation(self):
        """Test lead score is calculated correctly."""
        service = LeadManagementService()

        # High-intent lead
        high_intent_data = SAMPLE_EXTRACTED_DATA.copy()
        high_intent_data["intent"] = {
            **SAMPLE_EXTRACTED_DATA["intent"],
            "has_preapproval": True,
            "has_realtor": True,
            "has_property_identified": True,
        }

        result = await service.create_or_update_lead(
            extracted_data=high_intent_data,
            call_id="test-call-002",
        )

        assert result.success
        lead = await service.get_lead(result.lead_id)
        assert lead.lead_score >= 70  # High intent should have high score

    @pytest.mark.asyncio
    async def test_lead_priority_determination(self):
        """Test lead priority based on urgency."""
        service = LeadManagementService()

        # Urgent lead
        urgent_data = SAMPLE_EXTRACTED_DATA.copy()
        urgent_data["intent"] = {
            "urgency": "high",
            "has_property_identified": True,
        }

        result = await service.create_or_update_lead(
            extracted_data=urgent_data,
            call_id="test-call-003",
        )

        lead = await service.get_lead(result.lead_id)
        assert lead.priority == LeadPriority.HOT


# =============================================================================
# Document Checklist Service Tests
# =============================================================================

class TestDocumentChecklistService:
    """Tests for DocumentChecklistService."""

    def test_generate_purchase_checklist(self):
        """Test generating checklist for purchase."""
        service = DocumentChecklistService()

        checklist = service.generate_checklist(
            extracted_data=SAMPLE_EXTRACTED_DATA,
            call_id="test-call-001",
            loan_type="conventional",
            loan_purpose="purchase",
        )

        assert isinstance(checklist, DocumentChecklist)
        assert checklist.total_required > 0
        assert checklist.loan_purpose == "purchase"

        # Should have standard income docs
        doc_types = [d.document_type for d in checklist.required_documents]
        assert "paystubs" in doc_types
        assert "w2" in doc_types
        assert "bank_statements" in doc_types

    def test_generate_self_employed_checklist(self):
        """Test checklist includes self-employment docs."""
        service = DocumentChecklistService()

        self_employed_data = SAMPLE_EXTRACTED_DATA.copy()
        self_employed_data["employment"] = {
            "is_self_employed": True,
            "business_name": "Smith Consulting",
        }

        checklist = service.generate_checklist(
            extracted_data=self_employed_data,
            call_id="test-call-001",
            loan_type="conventional",
            loan_purpose="purchase",
        )

        doc_types = [d.document_type for d in checklist.required_documents]
        assert "business_tax_returns" in doc_types
        assert "profit_loss_statement" in doc_types

    def test_generate_fha_checklist(self):
        """Test FHA-specific documents."""
        service = DocumentChecklistService()

        checklist = service.generate_checklist(
            extracted_data=SAMPLE_EXTRACTED_DATA,
            call_id="test-call-001",
            loan_type="fha",
            loan_purpose="purchase",
        )

        doc_types = [d.document_type for d in checklist.required_documents]
        assert "fha_case_number" in doc_types

    def test_generate_va_checklist(self):
        """Test VA-specific documents."""
        service = DocumentChecklistService()

        checklist = service.generate_checklist(
            extracted_data=SAMPLE_EXTRACTED_DATA,
            call_id="test-call-001",
            loan_type="va",
            loan_purpose="purchase",
        )

        doc_types = [d.document_type for d in checklist.required_documents]
        assert "dd214" in doc_types
        assert "coe" in doc_types


# =============================================================================
# Outreach Service Tests
# =============================================================================

class TestOutreachService:
    """Tests for OutreachService."""

    @pytest.mark.asyncio
    async def test_send_welcome_email(self):
        """Test sending welcome email."""
        service = OutreachService()

        result = await service.send_welcome_email(
            extracted_data=SAMPLE_EXTRACTED_DATA,
            lo_name="Jane Doe",
            company_name="Test Mortgage Co",
        )

        assert result.success
        assert result.outreach_type == OutreachType.WELCOME
        assert result.recipient == "john.smith@example.com"

    @pytest.mark.asyncio
    async def test_send_document_request(self):
        """Test sending document request email."""
        service = OutreachService()

        doc_service = DocumentChecklistService()
        checklist = doc_service.generate_checklist(
            extracted_data=SAMPLE_EXTRACTED_DATA,
            call_id="test-call-001",
        )

        result = await service.send_document_request(
            extracted_data=SAMPLE_EXTRACTED_DATA,
            required_documents=checklist.required_documents[:3],
            lo_name="Jane Doe",
            company_name="Test Mortgage Co",
        )

        assert result.success
        assert result.outreach_type == OutreachType.DOCUMENT_REQUEST

    @pytest.mark.asyncio
    async def test_send_fails_without_email(self):
        """Test sending fails gracefully without email."""
        service = OutreachService()

        no_email_data = SAMPLE_EXTRACTED_DATA.copy()
        no_email_data["identity"] = {"first_name": "John"}

        result = await service.send_welcome_email(
            extracted_data=no_email_data,
            lo_name="Jane Doe",
            company_name="Test Mortgage Co",
        )

        assert not result.success
        assert len(result.errors) > 0


# =============================================================================
# Scheduling Service Tests
# =============================================================================

class TestSchedulingService:
    """Tests for SchedulingService."""

    @pytest.mark.asyncio
    async def test_schedule_followup(self):
        """Test scheduling follow-up call."""
        service = SchedulingService()

        followup = await service.schedule_followup(
            extracted_data=SAMPLE_EXTRACTED_DATA,
            call_id="test-call-001",
            appointment_type=AppointmentType.FOLLOWUP_CALL,
        )

        assert isinstance(followup, ScheduledFollowup)
        assert followup.followup_id is not None
        assert followup.scheduled_date is not None
        assert followup.borrower_name == "John Smith"

    @pytest.mark.asyncio
    async def test_priority_affects_scheduling(self):
        """Test that urgency affects scheduling time."""
        service = SchedulingService()

        # Urgent lead
        urgent_data = SAMPLE_EXTRACTED_DATA.copy()
        urgent_data["intent"] = {"urgency": "high"}

        followup = await service.schedule_followup(
            extracted_data=urgent_data,
            call_id="test-call-002",
        )

        assert followup.priority == FollowupPriority.URGENT

    @pytest.mark.asyncio
    async def test_get_available_slots(self):
        """Test getting available time slots."""
        service = SchedulingService()

        slots = await service.get_available_slots(
            start_date=datetime.now(),
            days=3,
        )

        assert len(slots) > 0
        assert all(hasattr(s, 'start_time') for s in slots)


# =============================================================================
# Orchestrator Tests
# =============================================================================

class TestCallIntelligenceOrchestrator:
    """Tests for CallIntelligenceOrchestrator."""

    def test_orchestrator_instantiation(self):
        """Test orchestrator can be instantiated."""
        orchestrator = CallIntelligenceOrchestrator()
        assert orchestrator is not None

    @pytest.mark.asyncio
    async def test_full_orchestration(self):
        """Test complete orchestration pipeline."""
        orchestrator = CallIntelligenceOrchestrator()

        result = await orchestrator.orchestrate(
            call_id="test-orchestration-001",
            extracted_data=SAMPLE_EXTRACTED_DATA,
        )

        assert isinstance(result, OrchestrationResult)
        assert result.status in [OrchestrationStatus.COMPLETED, OrchestrationStatus.PARTIAL]
        assert result.lead_id is not None
        assert result.prequal_result is not None
        assert result.document_checklist is not None

    @pytest.mark.asyncio
    async def test_orchestration_with_config(self):
        """Test orchestration with custom config."""
        config = OrchestrationConfig(
            run_lead_creation=True,
            run_pre_qualification=True,
            run_document_checklist=True,
            run_outreach=False,  # Disable outreach
            run_scheduling=False,  # Disable scheduling
            lo_name="Test LO",
            company_name="Test Company",
        )

        orchestrator = CallIntelligenceOrchestrator(config=config)

        result = await orchestrator.orchestrate(
            call_id="test-orchestration-002",
            extracted_data=SAMPLE_EXTRACTED_DATA,
        )

        assert result.lead_id is not None
        assert result.prequal_result is not None
        # Outreach should not have been sent
        assert len(result.outreach_results) == 0

    @pytest.mark.asyncio
    async def test_orchestration_handles_incomplete_data(self):
        """Test orchestration with incomplete data."""
        orchestrator = CallIntelligenceOrchestrator()

        minimal_data = {
            "identity": {
                "first_name": "Test",
            }
        }

        result = await orchestrator.orchestrate(
            call_id="test-orchestration-003",
            extracted_data=minimal_data,
        )

        # Should still complete (possibly with partial results)
        assert result.status in [OrchestrationStatus.COMPLETED, OrchestrationStatus.PARTIAL]

    @pytest.mark.asyncio
    async def test_orchestration_tracking(self):
        """Test orchestration tracks step results."""
        orchestrator = CallIntelligenceOrchestrator()

        result = await orchestrator.orchestrate(
            call_id="test-orchestration-004",
            extracted_data=SAMPLE_EXTRACTED_DATA,
        )

        # Should have step results
        assert len(result.steps) > 0
        assert result.total_duration_ms > 0
        assert result.started_at is not None
        assert result.completed_at is not None


# =============================================================================
# Integration Tests
# =============================================================================

class TestOrchestrationIntegration:
    """Integration tests for the full orchestration flow."""

    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self):
        """Test complete end-to-end workflow."""
        orchestrator = CallIntelligenceOrchestrator(
            config=OrchestrationConfig(
                lo_name="John Doe",
                company_name="ABC Mortgage",
            )
        )

        result = await orchestrator.orchestrate(
            call_id="e2e-test-001",
            extracted_data=SAMPLE_EXTRACTED_DATA,
            organization_id=1,
            assigned_to="user_123",
        )

        # Verify complete workflow
        assert result.status == OrchestrationStatus.COMPLETED

        # Lead was created
        assert result.lead_id is not None

        # Pre-qualification was calculated
        assert result.prequal_result is not None
        assert result.prequal_result.status != QualificationStatus.INSUFFICIENT_DATA

        # Document checklist was generated
        assert result.document_checklist is not None
        assert result.document_checklist.total_required > 0

        # Followup was scheduled
        assert result.scheduled_followup is not None

    @pytest.mark.asyncio
    async def test_orchestration_result_serialization(self):
        """Test that orchestration result serializes correctly."""
        orchestrator = CallIntelligenceOrchestrator()

        result = await orchestrator.orchestrate(
            call_id="serial-test-001",
            extracted_data=SAMPLE_EXTRACTED_DATA,
        )

        # Should serialize to dict without errors
        result_dict = result.to_dict()

        assert "call_id" in result_dict
        assert "status" in result_dict
        assert "steps" in result_dict
        assert "lead_id" in result_dict
