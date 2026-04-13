"""
Tests for routes/audit_routes.py — Calendar Audit Log endpoints

Validates auth, tenant isolation, input validation, admin-only access,
and graceful handling of uninitialized audit service.
"""

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# Mock the calendar_audit_service before importing audit_routes
_mock_cas = MagicMock()
sys.modules.setdefault("services.calendar_audit_service", _mock_cas)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(user_id=1, org_id=100, role="loan_officer"):
    user = MagicMock()
    user.id = user_id
    user.organization_id = org_id
    user.permission_role = role
    user.role = role
    return user


def _admin_user(user_id=1, org_id=100):
    return _make_user(user_id, org_id, "admin")


# ---------------------------------------------------------------------------
# Import helpers — audit_routes needs set_dependencies called first
# ---------------------------------------------------------------------------

@pytest.fixture
def audit_module():
    """Import audit_routes and provide its helpers."""
    from routes.audit_routes import (
        _get_org_id,
        _is_scheduler_admin,
    )
    return {
        "get_org_id": _get_org_id,
        "is_admin": _is_scheduler_admin,
    }


# ---------------------------------------------------------------------------
# 1. _get_org_id
# ---------------------------------------------------------------------------

class TestGetOrgId:
    def test_returns_org_id_when_present(self, audit_module):
        user = _make_user(org_id=42)
        assert audit_module["get_org_id"](user) == 42

    def test_raises_403_when_missing(self, audit_module):
        from fastapi import HTTPException
        user = MagicMock()
        user.organization_id = None
        with pytest.raises(HTTPException) as exc_info:
            audit_module["get_org_id"](user)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 2. _is_scheduler_admin
# ---------------------------------------------------------------------------

class TestIsSchedulerAdmin:
    @pytest.mark.parametrize("role", ["admin", "platform_admin", "site_admin", "super_admin"])
    def test_admin_roles_return_true(self, audit_module, role):
        user = _make_user(role=role)
        assert audit_module["is_admin"](user) is True

    @pytest.mark.parametrize("role", ["loan_officer", "processor", "manager", ""])
    def test_non_admin_roles_return_false(self, audit_module, role):
        user = _make_user(role=role)
        assert audit_module["is_admin"](user) is False


# ---------------------------------------------------------------------------
# 3. CalendarAuditService routing (mocked)
# ---------------------------------------------------------------------------

class TestAppointmentAuditTrail:
    @pytest.mark.asyncio
    async def test_returns_entries_for_appointment(self):
        """GET /audit/appointment/{id} returns entries from CalendarAuditService."""
        from routes.audit_routes import get_appointment_audit_trail

        mock_entries = [{"id": 1, "event": "appointment.created"}]

        with patch("routes.audit_routes.CalendarAuditService") as MockService:
            MockService.get_entity_history = AsyncMock(return_value=mock_entries)

            user = _make_user()
            db = MagicMock()
            request = MagicMock()

            result = await get_appointment_audit_trail(
                appointment_id=10,
                request=request,
                limit=50,
                offset=0,
                db=db,
                current_user=user,
            )

            assert result["appointment_id"] == 10
            assert result["entries"] == mock_entries
            assert result["count"] == 1

            MockService.get_entity_history.assert_awaited_once_with(
                db=db,
                entity_type="appointment",
                entity_id="10",
                organization_id=100,
                limit=50,
                offset=0,
            )

    @pytest.mark.asyncio
    async def test_returns_503_when_service_not_initialized(self):
        from routes.audit_routes import get_appointment_audit_trail
        from fastapi import HTTPException

        with patch("routes.audit_routes.CalendarAuditService") as MockService:
            MockService.get_entity_history = AsyncMock(
                side_effect=RuntimeError("Not initialized")
            )

            user = _make_user()
            with pytest.raises(HTTPException) as exc_info:
                await get_appointment_audit_trail(
                    appointment_id=1,
                    request=MagicMock(),
                    limit=50,
                    offset=0,
                    db=MagicMock(),
                    current_user=user,
                )
            assert exc_info.value.status_code == 503


class TestUserActivityLog:
    @pytest.mark.asyncio
    async def test_user_can_view_own_activity(self):
        from routes.audit_routes import get_user_activity_log

        with patch("routes.audit_routes.CalendarAuditService") as MockService:
            MockService.get_user_activity = AsyncMock(return_value=[])

            user = _make_user(user_id=5)
            result = await get_user_activity_log(
                user_id=5,
                request=MagicMock(),
                days=30,
                limit=100,
                offset=0,
                db=MagicMock(),
                current_user=user,
            )

            assert result["user_id"] == 5
            assert result["period_days"] == 30

    @pytest.mark.asyncio
    async def test_non_admin_cannot_view_others_activity(self):
        from routes.audit_routes import get_user_activity_log
        from fastapi import HTTPException

        user = _make_user(user_id=5, role="loan_officer")
        with pytest.raises(HTTPException) as exc_info:
            await get_user_activity_log(
                user_id=99,  # Different user
                request=MagicMock(),
                days=30,
                limit=100,
                offset=0,
                db=MagicMock(),
                current_user=user,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_view_others_activity(self):
        from routes.audit_routes import get_user_activity_log

        with patch("routes.audit_routes.CalendarAuditService") as MockService:
            MockService.get_user_activity = AsyncMock(return_value=[])

            user = _admin_user(user_id=1)
            result = await get_user_activity_log(
                user_id=99,
                request=MagicMock(),
                days=30,
                limit=100,
                offset=0,
                db=MagicMock(),
                current_user=user,
            )
            assert result["user_id"] == 99


class TestSearchAuditLogs:
    @pytest.mark.asyncio
    async def test_rejects_invalid_severity(self):
        from routes.audit_routes import search_audit_logs
        from fastapi import HTTPException

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await search_audit_logs(
                request=MagicMock(),
                event_type=None,
                event_category=None,
                severity="extreme",
                actor_id=None,
                actor_type=None,
                entity_type=None,
                entity_id=None,
                start_date=None,
                end_date=None,
                limit=50,
                offset=0,
                db=MagicMock(),
                current_user=user,
            )
        assert exc_info.value.status_code == 400
        assert "severity" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_rejects_invalid_actor_type(self):
        from routes.audit_routes import search_audit_logs
        from fastapi import HTTPException

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await search_audit_logs(
                request=MagicMock(),
                event_type=None,
                event_category=None,
                severity=None,
                actor_id=None,
                actor_type="robot",
                entity_type=None,
                entity_id=None,
                start_date=None,
                end_date=None,
                limit=50,
                offset=0,
                db=MagicMock(),
                current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_invalid_date_format(self):
        from routes.audit_routes import search_audit_logs
        from fastapi import HTTPException

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await search_audit_logs(
                request=MagicMock(),
                event_type=None,
                event_category=None,
                severity=None,
                actor_id=None,
                actor_type=None,
                entity_type=None,
                entity_id=None,
                start_date="not-a-date",
                end_date=None,
                limit=50,
                offset=0,
                db=MagicMock(),
                current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_passes_valid_filters_to_service(self):
        from routes.audit_routes import search_audit_logs

        with patch("routes.audit_routes.CalendarAuditService") as MockService:
            MockService.search_audit_logs = AsyncMock(return_value={"entries": [], "total": 0})

            user = _make_user()
            result = await search_audit_logs(
                request=MagicMock(),
                event_type="appointment.created",
                event_category="booking",
                severity="info",
                actor_id=None,
                actor_type="user",
                entity_type=None,
                entity_id=None,
                start_date="2026-01-01T00:00:00Z",
                end_date="2026-04-01T00:00:00Z",
                limit=50,
                offset=0,
                db=MagicMock(),
                current_user=user,
            )

            MockService.search_audit_logs.assert_awaited_once()
            call_kwargs = MockService.search_audit_logs.call_args.kwargs
            assert call_kwargs["event_type"] == "appointment.created"
            assert call_kwargs["severity"] == "info"
            assert call_kwargs["organization_id"] == 100


class TestSuspiciousActivity:
    @pytest.mark.asyncio
    async def test_rejects_non_admin(self):
        from routes.audit_routes import get_suspicious_activity
        from fastapi import HTTPException

        user = _make_user(role="loan_officer")
        with pytest.raises(HTTPException) as exc_info:
            await get_suspicious_activity(
                request=MagicMock(),
                days=7,
                db=MagicMock(),
                current_user=user,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_gets_findings(self):
        from routes.audit_routes import get_suspicious_activity

        with patch("routes.audit_routes.CalendarAuditService") as MockService:
            findings = {"suspicious": [], "risk_score": 0}
            MockService.get_suspicious_activity = AsyncMock(return_value=findings)

            user = _admin_user()
            result = await get_suspicious_activity(
                request=MagicMock(),
                days=7,
                db=MagicMock(),
                current_user=user,
            )
            assert result == findings


class TestAuditStats:
    @pytest.mark.asyncio
    async def test_returns_stats(self):
        from routes.audit_routes import get_audit_stats

        with patch("routes.audit_routes.CalendarAuditService") as MockService:
            stats = {"total": 100, "by_type": {}}
            MockService.get_audit_stats = AsyncMock(return_value=stats)

            user = _make_user()
            result = await get_audit_stats(
                request=MagicMock(),
                days=30,
                db=MagicMock(),
                current_user=user,
            )
            assert result == stats


class TestEntityAuditTrail:
    @pytest.mark.asyncio
    async def test_rejects_invalid_entity_type(self):
        from routes.audit_routes import get_entity_audit_trail
        from fastapi import HTTPException

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await get_entity_audit_trail(
                entity_type="invalid_type",
                entity_id="1",
                request=MagicMock(),
                limit=50,
                offset=0,
                db=MagicMock(),
                current_user=user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_accepts_valid_entity_types(self):
        from routes.audit_routes import get_entity_audit_trail

        valid_types = [
            "appointment", "booking_link", "blocked_time", "config",
            "availability", "appointment_type", "routing_rule",
        ]

        for entity_type in valid_types:
            with patch("routes.audit_routes.CalendarAuditService") as MockService:
                MockService.get_entity_history = AsyncMock(return_value=[])

                user = _make_user()
                result = await get_entity_audit_trail(
                    entity_type=entity_type,
                    entity_id="1",
                    request=MagicMock(),
                    limit=50,
                    offset=0,
                    db=MagicMock(),
                    current_user=user,
                )
                assert result["entity_type"] == entity_type
