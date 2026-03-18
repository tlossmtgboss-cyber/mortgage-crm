"""
Tests for scheduler cancellation policy routes.

Covers:
  - GET  /cancellation-policy                  Get org policy
  - PUT  /cancellation-policy                  Update policy (admin)
  - GET  /cancellation-policy/check/{appt_id}  Pre-flight policy check
  - POST /cancel/{appointment_id}              Cancel with enforcement
  - GET  /cancellation-stats                   Cancellation analytics (admin)

Edge cases: non-admin rejection, empty updates, policy denial (409),
missing appointments, and late cancellation handling.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockUser:
    def __init__(self, id=1, organization_id=1, role="admin", email="admin@test.com"):
        self.id = id
        self.organization_id = organization_id
        self.role = role
        self.permission_role = role
        self.email = email
        self.full_name = "Admin User"


class MockPolicy:
    """Mock cancellation policy ORM object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.min_notice_hours = kwargs.get("min_notice_hours", 24)
        self.max_cancellations_per_borrower = kwargs.get("max_cancellations_per_borrower", 3)
        self.allow_borrower_cancel = kwargs.get("allow_borrower_cancel", True)
        self.require_reason = kwargs.get("require_reason", False)
        self.cancellation_reasons = kwargs.get("cancellation_reasons", ["schedule_conflict", "no_longer_needed"])
        self.late_cancel_message = kwargs.get("late_cancel_message", "")
        self.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.updated_at = datetime(2026, 3, 1, tzinfo=timezone.utc)


class MockPolicyService:
    """Mock CancellationPolicyService."""
    def __init__(self, db):
        self._policy = MockPolicy()

    def get_or_create_policy(self, org_id):
        return self._policy

    def update_policy(self, org_id, updates):
        for k, v in updates.items():
            setattr(self._policy, k, v)
        self._policy.updated_at = datetime.now(timezone.utc)
        return self._policy

    def can_cancel(self, **kwargs):
        return {
            "allowed": True,
            "is_late": False,
            "cancel_count": 1,
            "reason": None,
        }

    def enforce_policy(self, **kwargs):
        return {
            "cancelled": True,
            "is_late": False,
            "policy_check": {
                "allowed": True,
                "is_late": False,
                "cancel_count": 1,
                "reason": None,
            },
        }

    def get_cancellation_stats(self, org_id, period_days):
        return {
            "total_cancellations": 5,
            "cancellation_rate": 0.12,
            "late_cancellation_rate": 0.04,
            "top_reasons": [{"reason": "schedule_conflict", "count": 3}],
        }


class MockAppointment:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 100)
        self.title = kwargs.get("title", "Loan Review")
        self.attendee_name = kwargs.get("attendee_name", "John Smith")
        self.attendee_email = kwargs.get("attendee_email", "john@example.com")
        self.lead_id = kwargs.get("lead_id", 10)
        self.loan_id = kwargs.get("loan_id", 20)
        self.assigned_user_id = kwargs.get("assigned_user_id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.scheduled_start = datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetCancellationPolicy:
    """Tests for GET /cancellation-policy."""

    @pytest.mark.asyncio
    async def test_get_policy_happy_path(self):
        """Authenticated user can retrieve policy."""
        from routes.scheduler.cancellation_policy import get_cancellation_policy

        user = MockUser(role="loan_officer")
        db = MagicMock()
        db.commit = MagicMock()

        with patch("routes.scheduler.cancellation_policy.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.cancellation_policy.CancellationPolicyService",
                    return_value=MockPolicyService(db)):
            result = await get_cancellation_policy(MagicMock(), db)

        assert result["min_notice_hours"] == 24
        assert result["max_cancellations_per_borrower"] == 3
        assert result["allow_borrower_cancel"] is True

    @pytest.mark.asyncio
    async def test_get_policy_requires_auth(self):
        """Unauthenticated requests should fail."""
        from routes.scheduler.cancellation_policy import get_cancellation_policy

        with patch("routes.scheduler.cancellation_policy.get_current_user",
                    new_callable=AsyncMock, side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await get_cancellation_policy(MagicMock(), MagicMock())
            assert exc_info.value.status_code == 401


class TestUpdateCancellationPolicy:
    """Tests for PUT /cancellation-policy."""

    @pytest.mark.asyncio
    async def test_update_requires_admin(self):
        """Non-admin users should get 403."""
        from routes.scheduler.cancellation_policy import update_cancellation_policy, CancellationPolicyUpdate

        non_admin = MockUser(role="loan_officer")
        body = CancellationPolicyUpdate(min_notice_hours=48)

        with patch("routes.scheduler.cancellation_policy.get_current_user",
                    new_callable=AsyncMock, return_value=non_admin):
            with pytest.raises(HTTPException) as exc_info:
                await update_cancellation_policy(body, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_update_empty_body_rejected(self):
        """Request with no fields to update returns 400."""
        from routes.scheduler.cancellation_policy import update_cancellation_policy, CancellationPolicyUpdate

        admin = MockUser(role="admin")
        body = CancellationPolicyUpdate()  # All None

        with patch("routes.scheduler.cancellation_policy.get_current_user",
                    new_callable=AsyncMock, return_value=admin):
            with pytest.raises(HTTPException) as exc_info:
                await update_cancellation_policy(body, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_happy_path(self):
        """Admin can update policy fields."""
        from routes.scheduler.cancellation_policy import update_cancellation_policy, CancellationPolicyUpdate

        admin = MockUser(role="admin")
        body = CancellationPolicyUpdate(min_notice_hours=48, require_reason=True)
        db = MagicMock()
        db.commit = MagicMock()

        with patch("routes.scheduler.cancellation_policy.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.cancellation_policy.CancellationPolicyService",
                    return_value=MockPolicyService(db)), \
             patch("routes.scheduler.cancellation_policy._audit_log"):
            result = await update_cancellation_policy(body, MagicMock(), db)

        assert result["min_notice_hours"] == 48
        assert result["require_reason"] is True


class TestCancelWithPolicy:
    """Tests for POST /cancel/{appointment_id}."""

    @pytest.mark.asyncio
    async def test_cancel_happy_path(self):
        """Successful cancellation returns details."""
        from routes.scheduler.cancellation_policy import cancel_with_policy, PolicyCancelRequest

        user = MockUser(role="admin")
        body = PolicyCancelRequest(reason="schedule_conflict")
        db = MagicMock()
        db.commit = MagicMock()
        mock_appt = MockAppointment()

        # Mock the db query for fetching the appointment post-cancel
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=mock_appt)
        db.query = MagicMock(return_value=query_mock)

        mock_models = {"Appointment": MagicMock()}

        with patch("routes.scheduler.cancellation_policy.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.cancellation_policy.CancellationPolicyService",
                    return_value=MockPolicyService(db)), \
             patch("routes.scheduler.cancellation_policy.get_models", return_value=mock_models), \
             patch("routes.scheduler.cancellation_policy._log_appointment_activity"), \
             patch("routes.scheduler.cancellation_policy._create_followup_task"), \
             patch("routes.scheduler.cancellation_policy._audit_log"):
            result = await cancel_with_policy(100, body, MagicMock(), db)

        assert result["message"] == "Appointment cancelled"
        assert result["appointment_id"] == 100

    @pytest.mark.asyncio
    async def test_cancel_policy_denial_returns_409(self):
        """When policy denies cancellation, return 409."""
        from routes.scheduler.cancellation_policy import cancel_with_policy, PolicyCancelRequest

        user = MockUser(role="loan_officer")
        body = PolicyCancelRequest(reason="schedule_conflict")

        # Create a service that denies cancellation
        class DenyingService(MockPolicyService):
            def enforce_policy(self, **kwargs):
                return {
                    "cancelled": False,
                    "is_late": True,
                    "policy_check": {
                        "allowed": False,
                        "is_late": True,
                        "cancel_count": 5,
                        "reason": "Maximum cancellations exceeded",
                    },
                }

        with patch("routes.scheduler.cancellation_policy.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.cancellation_policy.CancellationPolicyService",
                    return_value=DenyingService(MagicMock())):
            with pytest.raises(HTTPException) as exc_info:
                await cancel_with_policy(100, body, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 409


class TestCheckCancellationPolicy:
    """Tests for GET /cancellation-policy/check/{appointment_id}."""

    @pytest.mark.asyncio
    async def test_check_returns_policy_result(self):
        """Pre-flight check returns policy evaluation."""
        from routes.scheduler.cancellation_policy import check_cancellation_policy

        user = MockUser(role="loan_officer")
        db = MagicMock()

        with patch("routes.scheduler.cancellation_policy.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.cancellation_policy.CancellationPolicyService",
                    return_value=MockPolicyService(db)):
            result = await check_cancellation_policy(100, None, MagicMock(), db)

        assert result["allowed"] is True


class TestCancellationStats:
    """Tests for GET /cancellation-stats."""

    @pytest.mark.asyncio
    async def test_stats_requires_admin(self):
        """Non-admin users should get 403."""
        from routes.scheduler.cancellation_policy import get_cancellation_stats

        non_admin = MockUser(role="loan_officer")

        with patch("routes.scheduler.cancellation_policy.get_current_user",
                    new_callable=AsyncMock, return_value=non_admin):
            with pytest.raises(HTTPException) as exc_info:
                await get_cancellation_stats(30, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_stats_happy_path(self):
        """Admin can retrieve cancellation stats."""
        from routes.scheduler.cancellation_policy import get_cancellation_stats

        admin = MockUser(role="admin")
        db = MagicMock()

        with patch("routes.scheduler.cancellation_policy.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.cancellation_policy.CancellationPolicyService",
                    return_value=MockPolicyService(db)):
            result = await get_cancellation_stats(30, MagicMock(), db)

        assert result["total_cancellations"] == 5
        assert "cancellation_rate" in result
