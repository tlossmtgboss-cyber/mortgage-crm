"""
Tests for scheduler compliance scheduling routes.

Covers:
  - GET  /compliance/evaluate/{loan_id}    Evaluate one loan
  - GET  /compliance/pipeline              Evaluate all active loans for the org
  - POST /compliance/schedule/{loan_id}    Create a compliance appointment
  - GET  /compliance/overdue               List overdue compliance appointments

All endpoints require authentication and organization context. Non-admin users
are restricted to viewing their own data for pipeline and overdue endpoints.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockUser:
    """Mock authenticated user."""
    def __init__(self, id=1, organization_id=1, role="loan_officer", email="lo@test.com"):
        self.id = id
        self.organization_id = organization_id
        self.role = role
        self.permission_role = role
        self.email = email


class MockAdminUser(MockUser):
    """Mock admin user."""
    def __init__(self, **kwargs):
        defaults = {"id": 2, "role": "admin", "email": "admin@test.com"}
        defaults.update(kwargs)
        super().__init__(**defaults)


SAMPLE_SUGGESTION = {
    "rule_id": "disclosure_review",
    "appointment_type": "Disclosure Review Call",
    "meeting_type": "review_call",
    "duration_minutes": 30,
    "urgency": "critical",
    "reason": "LE sent 4 days ago, not yet signed by borrower",
    "regulation": "TRID",
    "loan_id": 100,
    "loan_number": "2026-001234",
    "borrower_name": "Jane Doe",
    "loan_stage": "DISCLOSED",
    "lo_id": 5,
    "context": {"days_since_le_sent": 4},
    "days_remaining": -1,
}

SAMPLE_SUGGESTION_HIGH = {
    "rule_id": "lock_expiration_review",
    "appointment_type": "Lock Expiration Review",
    "meeting_type": "review_call",
    "duration_minutes": 15,
    "urgency": "high",
    "reason": "Rate lock expires in 5 days",
    "regulation": "Internal SLA",
    "loan_id": 101,
    "loan_number": "2026-001235",
    "borrower_name": "John Smith",
    "loan_stage": "PROCESSING",
    "lo_id": 5,
    "context": {"days_until_lock_expiry": 5},
    "days_remaining": 5,
}

SAMPLE_OVERDUE = [
    {
        "appointment_id": 500,
        "title": "Disclosure Review - Jane Doe",
        "loan_id": 100,
        "rule_id": "disclosure_review",
        "urgency": "critical",
        "regulation": "TRID",
        "scheduled_start": "2026-03-15T14:00:00+00:00",
        "hours_overdue": 48.5,
        "assigned_user_id": 5,
        "attendee_name": "Jane Doe",
        "status": "booked",
    },
]

SAMPLE_APPOINTMENT_RESULT = {
    "appointment_id": 600,
    "loan_id": 100,
    "loan_number": "2026-001234",
    "borrower_name": "Jane Doe",
    "rule_id": "disclosure_review",
    "appointment_type": "Disclosure Review Call",
    "urgency": "critical",
    "regulation": "TRID",
    "scheduled_start": "2026-03-18T10:00:00+00:00",
    "scheduled_end": "2026-03-18T10:30:00+00:00",
    "duration_minutes": 30,
    "status": "booked",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEvaluateLoan:
    """Tests for GET /compliance/evaluate/{loan_id}."""

    @pytest.mark.asyncio
    async def test_evaluate_requires_auth(self):
        """Unauthenticated requests should fail."""
        from routes.scheduler.compliance_scheduling import evaluate_loan

        with patch(
            "routes.scheduler.compliance_scheduling.get_current_user",
            new_callable=AsyncMock,
            side_effect=Exception("Not authenticated"),
        ):
            with pytest.raises(Exception, match="Not authenticated"):
                await evaluate_loan(
                    loan_id=100,
                    request=MagicMock(),
                    db=MagicMock(),
                    current_user=None,
                )

    @pytest.mark.asyncio
    async def test_evaluate_returns_suggestions(self):
        """Should return compliance suggestions for an active loan."""
        from routes.scheduler.compliance_scheduling import evaluate_loan

        user = MockUser()
        mock_service = MagicMock()
        mock_service.evaluate_loan = AsyncMock(return_value=[SAMPLE_SUGGESTION])

        with patch("routes.scheduler.compliance_scheduling._get_org_id", return_value=1), \
             patch("routes.scheduler.compliance_scheduling.ComplianceSchedulingService", return_value=mock_service):

            result = await evaluate_loan(
                loan_id=100,
                request=MagicMock(),
                db=MagicMock(),
                current_user=user,
            )

        assert result.loan_id == 100
        assert result.suggestion_count == 1
        assert result.critical_count == 1
        assert result.high_count == 0
        assert result.suggestions[0].rule_id == "disclosure_review"

    @pytest.mark.asyncio
    async def test_evaluate_returns_empty_for_clean_loan(self):
        """A loan with no compliance issues should return zero suggestions."""
        from routes.scheduler.compliance_scheduling import evaluate_loan

        user = MockUser()
        mock_service = MagicMock()
        mock_service.evaluate_loan = AsyncMock(return_value=[])

        with patch("routes.scheduler.compliance_scheduling._get_org_id", return_value=1), \
             patch("routes.scheduler.compliance_scheduling.ComplianceSchedulingService", return_value=mock_service):

            result = await evaluate_loan(
                loan_id=200,
                request=MagicMock(),
                db=MagicMock(),
                current_user=user,
            )

        assert result.loan_id == 200
        assert result.suggestion_count == 0
        assert result.critical_count == 0
        assert result.high_count == 0
        assert result.suggestions == []

    @pytest.mark.asyncio
    async def test_evaluate_counts_urgency_levels(self):
        """Should correctly count critical, high urgency suggestions."""
        from routes.scheduler.compliance_scheduling import evaluate_loan

        user = MockUser()
        mock_service = MagicMock()
        mock_service.evaluate_loan = AsyncMock(
            return_value=[SAMPLE_SUGGESTION, SAMPLE_SUGGESTION_HIGH]
        )

        with patch("routes.scheduler.compliance_scheduling._get_org_id", return_value=1), \
             patch("routes.scheduler.compliance_scheduling.ComplianceSchedulingService", return_value=mock_service):

            result = await evaluate_loan(
                loan_id=100,
                request=MagicMock(),
                db=MagicMock(),
                current_user=user,
            )

        assert result.suggestion_count == 2
        assert result.critical_count == 1
        assert result.high_count == 1


class TestEvaluatePipeline:
    """Tests for GET /compliance/pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_403_for_other_lo(self):
        """Non-admin should get 403 when viewing another LO's pipeline."""
        from routes.scheduler.compliance_scheduling import evaluate_pipeline

        user = MockUser(id=5)

        with patch("routes.scheduler.compliance_scheduling.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.compliance_scheduling._get_org_id", return_value=1), \
             patch("routes.scheduler.compliance_scheduling._is_scheduler_admin", return_value=False):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await evaluate_pipeline(
                    request=MagicMock(),
                    lo_id=99,
                    db=MagicMock(),
                    current_user=user,
                )
            assert exc_info.value.status_code == 403


class TestScheduleComplianceAppointment:
    """Tests for POST /compliance/schedule/{loan_id}."""

    @pytest.mark.asyncio
    async def test_schedule_creates_appointment(self):
        """Should create a compliance appointment and return details."""
        from routes.scheduler.compliance_scheduling import (
            schedule_compliance_appointment,
            ScheduleComplianceRequest,
        )

        user = MockUser()
        body = ScheduleComplianceRequest(
            rule_id="disclosure_review",
            scheduled_start=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
        )

        mock_service = MagicMock()
        mock_service.create_compliance_appointment = AsyncMock(return_value=SAMPLE_APPOINTMENT_RESULT)

        with patch("routes.scheduler.compliance_scheduling._get_org_id", return_value=1), \
             patch("routes.scheduler.compliance_scheduling.ComplianceSchedulingService", return_value=mock_service):

            result = await schedule_compliance_appointment(
                loan_id=100,
                body=body,
                request=MagicMock(),
                db=MagicMock(),
                current_user=user,
            )

        assert result.appointment_id == 600
        assert result.rule_id == "disclosure_review"
        assert result.regulation == "TRID"
        assert result.status == "booked"

    @pytest.mark.asyncio
    async def test_schedule_400_for_invalid_rule(self):
        """Should return 400 when the service raises ValueError for bad rule_id."""
        from routes.scheduler.compliance_scheduling import (
            schedule_compliance_appointment,
            ScheduleComplianceRequest,
        )

        user = MockUser()
        body = ScheduleComplianceRequest(rule_id="nonexistent_rule")

        mock_service = MagicMock()
        mock_service.create_compliance_appointment = AsyncMock(
            side_effect=ValueError("Unknown compliance rule: nonexistent_rule")
        )

        with patch("routes.scheduler.compliance_scheduling._get_org_id", return_value=1), \
             patch("routes.scheduler.compliance_scheduling.ComplianceSchedulingService", return_value=mock_service):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await schedule_compliance_appointment(
                    loan_id=100,
                    body=body,
                    request=MagicMock(),
                    db=MagicMock(),
                    current_user=user,
                )
            assert exc_info.value.status_code == 400
            assert "nonexistent_rule" in str(exc_info.value.detail)


class TestOverdueCompliance:
    """Tests for GET /compliance/overdue."""

    @pytest.mark.asyncio
    async def test_overdue_returns_empty_state(self):
        """No overdue appointments should return empty list."""
        from routes.scheduler.compliance_scheduling import list_overdue_compliance

        user = MockUser()
        mock_service = MagicMock()
        mock_service.get_overdue_compliance_appointments = AsyncMock(return_value=[])

        with patch("routes.scheduler.compliance_scheduling.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.compliance_scheduling._get_org_id", return_value=1), \
             patch("routes.scheduler.compliance_scheduling._is_scheduler_admin", return_value=False), \
             patch("routes.scheduler.compliance_scheduling.ComplianceSchedulingService", return_value=mock_service):

            result = await list_overdue_compliance(
                request=MagicMock(),
                lo_id=None,
                db=MagicMock(),
                current_user=user,
            )

        assert result.overdue_count == 0
        assert result.appointments == []

    @pytest.mark.asyncio
    async def test_overdue_403_for_other_lo(self):
        """Non-admin should get 403 when viewing another LO's overdue items."""
        from routes.scheduler.compliance_scheduling import list_overdue_compliance

        user = MockUser(id=5)

        with patch("routes.scheduler.compliance_scheduling.get_current_user", new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.compliance_scheduling._get_org_id", return_value=1), \
             patch("routes.scheduler.compliance_scheduling._is_scheduler_admin", return_value=False):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await list_overdue_compliance(
                    request=MagicMock(),
                    lo_id=99,
                    db=MagicMock(),
                    current_user=user,
                )
            assert exc_info.value.status_code == 403
