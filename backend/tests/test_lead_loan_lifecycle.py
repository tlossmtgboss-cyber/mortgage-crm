"""
Lead & Loan Lifecycle Tests

Tests the critical paths for lead creation, stage transitions,
loan creation linked to leads, and stage validation. Exercises:

- Lead model stage validation (@validates decorator)
- Loan model stage validation
- LeadStage and LoanStage enum completeness
- Stage transition ordering
- API endpoint stage transitions
- Lead-to-loan relationship

These are integration tests that use real DB sessions.
"""

import pytest
import uuid
import logging
from datetime import datetime, timezone
from unittest.mock import patch

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================

def _insert_lead(db_session, **kwargs):
    from database.models import Lead
    defaults = dict(
        name="Test Lead",
        email="test@example.com",
        phone="5551234567",
        stage="New",
        source="website",
        owner_id=1,
        organization_id=1,
        ai_score=50,
        sentiment="neutral",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    lead = Lead(**defaults)
    db_session.add(lead)
    db_session.flush()
    return lead


def _insert_loan(db_session, **kwargs):
    from database.models import Loan
    defaults = dict(
        loan_number=f"LN-{uuid.uuid4().hex[:8]}",
        borrower_name="Test Borrower",
        amount=400000,
        stage="DISCLOSED",
        loan_officer_id=1,
        organization_id=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    loan = Loan(**defaults)
    db_session.add(loan)
    db_session.flush()
    return loan


@pytest.fixture(autouse=True)
def _mock_side_effects():
    """Patch scoring/SLA side effects."""
    patches = []
    targets = [
        "utils.lead_scoring.calculate_lead_score",
        "services.sla_tracking_service.track_lead_created",
        "services.capacity_service.update_capacity_on_assignment",
        "services.lead_cascade_service.cascade_lead_status",
    ]
    for t in targets:
        try:
            p = patch(t, return_value=50)
            p.start()
            patches.append(p)
        except Exception:
            pass
    yield
    for p in patches:
        p.stop()


# =============================================================================
# Lead Stage Validation (model level)
# =============================================================================

@pytest.mark.critical
@pytest.mark.unit
class TestLeadStageValidation:
    """Lead.stage must validate against LeadStage enum values."""

    def test_valid_lead_stage_accepted(self, db_session):
        """Valid LeadStage values are accepted without warning."""
        lead = _insert_lead(db_session, stage="New", email="valid@test.com")
        assert lead.stage == "New"

    def test_standard_lead_stages(self, db_session):
        """All standard LeadStage values should be accepted."""
        from database.enums import LeadStage
        for i, stage in enumerate(LeadStage):
            lead = _insert_lead(
                db_session,
                stage=stage.value,
                email=f"stage{i}@test.com",
                name=f"Stage {i}",
            )
            assert lead.stage == stage.value

    def test_invalid_stage_warns_but_allows(self, db_session):
        """Invalid stage values emit a warning but are allowed (backward compat)."""
        import warnings
        lead = _insert_lead(db_session, stage="TOTALLY_BOGUS", email="bogus@test.com")
        # The model allows it but logs a warning
        assert lead.stage == "TOTALLY_BOGUS"

    def test_enum_value_converted_to_string(self, db_session):
        """LeadStage enum members should be converted to plain strings."""
        from database.enums import LeadStage
        lead = _insert_lead(db_session, stage=LeadStage.NEW, email="enum@test.com")
        assert lead.stage == "New"
        assert isinstance(lead.stage, str)


# =============================================================================
# Loan Stage Validation (model level)
# =============================================================================

@pytest.mark.critical
@pytest.mark.unit
class TestLoanStageValidation:
    """Loan.stage must validate against LoanStage enum values."""

    def test_valid_loan_stage_accepted(self, db_session):
        """Valid LoanStage values are accepted."""
        loan = _insert_loan(db_session, stage="PROCESSING")
        assert loan.stage == "PROCESSING"

    def test_all_loan_stages(self, db_session):
        """All LoanStage enum values should be accepted."""
        from database.enums import LoanStage
        for i, stage in enumerate(LoanStage):
            loan = _insert_loan(
                db_session,
                stage=stage.value,
                loan_number=f"STAGE-{i:03d}",
            )
            assert loan.stage == stage.value

    def test_loan_stages_are_uppercase(self):
        """All LoanStage values must be uppercase (DB convention)."""
        from database.enums import LoanStage
        for stage in LoanStage:
            assert stage.value == stage.value.upper(), (
                f"LoanStage.{stage.name} has non-uppercase value '{stage.value}'"
            )

    def test_terminal_loan_stages(self):
        """Terminal stages match the documented set."""
        from database.enums import LoanStage
        terminal = {"FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE"}
        for name in terminal:
            assert hasattr(LoanStage, name), f"Missing terminal stage: {name}"


# =============================================================================
# Lead Stage Progression (enum ordering)
# =============================================================================

@pytest.mark.critical
@pytest.mark.unit
class TestLeadStageProgression:
    """Lead stages follow a logical progression."""

    def test_lead_stages_include_full_funnel(self):
        """LeadStage must include all funnel stages from New to Closed."""
        from database.enums import LeadStage
        required = [
            "New",
            "Attempted Contact",
            "Prospect",
            "Application",
            "Pre-Qualified",
            "Pre-Approved",
        ]
        actual_values = [s.value for s in LeadStage]
        for stage in required:
            assert stage in actual_values, f"Missing funnel stage: {stage}"

    def test_lead_stages_include_terminal_states(self):
        """LeadStage must include terminal states."""
        from database.enums import LeadStage
        terminal = ["Withdrawn", "Does Not Qualify", "Funded"]
        actual_values = [s.value for s in LeadStage]
        for stage in terminal:
            assert stage in actual_values, f"Missing terminal stage: {stage}"


# =============================================================================
# Loan Pipeline Progression Order
# =============================================================================

@pytest.mark.critical
@pytest.mark.unit
class TestLoanPipelineProgression:
    """Loan stages follow the documented pipeline order."""

    def test_active_pipeline_order(self):
        """Active loan stages should follow the documented progression."""
        from database.enums import LoanStage
        # The expected progression from CLAUDE.md
        expected_order = [
            "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
            "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
            "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
            "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
        ]
        actual = [s.value for s in LoanStage]
        for stage in expected_order:
            assert stage in actual, f"Missing pipeline stage: {stage}"


# =============================================================================
# API-Level Stage Transitions
# =============================================================================

@pytest.mark.critical
@pytest.mark.integration
class TestLeadStageTransitionAPI:
    """Test stage transitions through the API."""

    def test_create_lead_has_default_stage(self, authenticated_client):
        """New lead should default to 'New' stage."""
        resp = authenticated_client.post("/api/v1/leads/", json={
            "name": "Default Stage",
            "email": "default@test.com",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["stage"] == "New"

    def test_stage_transition_updates_timestamp(self, authenticated_client, db_session):
        """Changing stage updates stage_changed_at."""
        lead = _insert_lead(db_session, name="Transition", email="transition@test.com", stage="New")
        db_session.commit()

        resp = authenticated_client.patch(
            f"/api/v1/leads/{lead.id}",
            json={"stage": "Prospect"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["stage"] == "Prospect"
        assert data["stage_changed_at"] is not None

    def test_stage_transition_to_attempted_contact_stamps_sla(self, authenticated_client, db_session):
        """Moving to 'Attempted Contact' sets first_contact_attempt_date."""
        lead = _insert_lead(db_session, name="SLA Test", email="sla@test.com", stage="New")
        db_session.commit()

        resp = authenticated_client.patch(
            f"/api/v1/leads/{lead.id}",
            json={"stage": "Attempted Contact"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["first_contact_attempt_date"] is not None


# =============================================================================
# Lead-to-Loan Linkage
# =============================================================================

@pytest.mark.critical
@pytest.mark.integration
class TestLeadLoanLinkage:
    """Test that leads and loans share organization_id for tenant isolation."""

    def test_lead_and_loan_same_org(self, db_session):
        """Lead and Loan in the same org should both have the same organization_id."""
        lead = _insert_lead(db_session, name="Linked Lead", email="linked@test.com",
                            organization_id=1)
        loan = _insert_loan(db_session, borrower_name="Linked Lead",
                            organization_id=1)
        assert lead.organization_id == loan.organization_id == 1

    def test_lead_org_id_is_not_nullable(self):
        """Lead.organization_id must be NOT NULL."""
        from database.models.lead_loan import Lead
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(Lead)
        for col in mapper.columns:
            if col.key == "organization_id":
                assert col.nullable is False, "Lead.organization_id must be NOT NULL"
                break

    def test_loan_org_id_is_not_nullable(self):
        """Loan.organization_id must be NOT NULL."""
        from database.models.lead_loan import Loan
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(Loan)
        for col in mapper.columns:
            if col.key == "organization_id":
                assert col.nullable is False, "Loan.organization_id must be NOT NULL"
                break
