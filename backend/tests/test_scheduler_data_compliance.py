"""
Tests for scheduler data compliance routes (GDPR/CCPA).

Covers:
  - GET  /data-export/{borrower_email}    Export borrower data
  - DELETE /data-delete/{borrower_email}  Anonymize/delete borrower PII
  - GET  /data-retention/report           Data retention report

Security-critical: every endpoint requires admin auth + tenant isolation.
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
    def __init__(self, id=1, organization_id=1, role="admin", email="admin@test.com"):
        self.id = id
        self.organization_id = organization_id
        self.role = role
        self.permission_role = role
        self.email = email


class MockAppointment:
    """Minimal appointment mock for data export/deletion."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 100)
        self.title = kwargs.get("title", "Loan Review")
        self.description = kwargs.get("description", "Review call")
        self.meeting_type = MagicMock(value="review_call")
        self.meeting_mode = MagicMock(value="video")
        self.scheduled_start = kwargs.get("scheduled_start", datetime(2026, 3, 10, 14, 0, tzinfo=timezone.utc))
        self.scheduled_end = kwargs.get("scheduled_end", datetime(2026, 3, 10, 14, 30, tzinfo=timezone.utc))
        self.duration_minutes = 30
        self.timezone = "America/Chicago"
        self.location = None
        self.attendee_name = kwargs.get("attendee_name", "John Smith")
        self.attendee_email = kwargs.get("attendee_email", "john@example.com")
        self.attendee_phone = "+15551234567"
        self.attendee_notes = "First time buyer"
        self.intake_responses = {"question1": "answer1"}
        self.status = MagicMock(value="booked")
        self.cancelled_at = None
        self.cancellation_reason = None
        self.completed_at = None
        self.no_show_at = None
        self.reschedule_count = 0
        self.booked_by_ai = False
        self.created_at = datetime(2026, 3, 8, 10, 0, tzinfo=timezone.utc)
        self.internal_notes = None
        self.meeting_notes = None
        self.organization_id = kwargs.get("organization_id", 1)


def _build_mock_db_query(appointments=None, reminder_logs=None, surveys=None,
                          audit_entries=None, stale_count=0, total_count=0,
                          stale_pii_count=0, deletion_requests=0):
    """Build a mock db session that returns expected query results."""
    db = MagicMock()

    def side_effect_query(model):
        q = MagicMock()
        q.filter = MagicMock(return_value=q)
        q.order_by = MagicMock(return_value=q)
        q.join = MagicMock(return_value=q)
        q.all = MagicMock(return_value=appointments or [])
        q.first = MagicMock(return_value=None)
        q.scalar = MagicMock(return_value=0)
        q.delete = MagicMock(return_value=0)
        q.count = MagicMock(return_value=0)
        return q

    db.query = MagicMock(side_effect=side_effect_query)
    db.commit = MagicMock()
    db.flush = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDataExport:
    """Tests for GET /data-export/{borrower_email}."""

    @pytest.mark.asyncio
    async def test_export_requires_auth(self):
        """Unauthenticated requests should be rejected."""
        from routes.scheduler.data_compliance import export_borrower_data

        # Simulate get_current_user raising
        with patch("routes.scheduler.data_compliance.get_current_user",
                    new_callable=AsyncMock, side_effect=Exception("Not authenticated")):
            with pytest.raises(Exception, match="Not authenticated"):
                await export_borrower_data("test@example.com", MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_export_requires_admin(self):
        """Non-admin users should get 403."""
        from routes.scheduler.data_compliance import export_borrower_data

        non_admin = MockUser(role="loan_officer")

        with patch("routes.scheduler.data_compliance.get_current_user",
                    new_callable=AsyncMock, return_value=non_admin):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await export_borrower_data("test@example.com", MagicMock(), MagicMock())
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_export_invalid_email_format(self):
        """Invalid email format should return 400."""
        from routes.scheduler.data_compliance import export_borrower_data

        admin = MockUser(role="admin")

        with patch("routes.scheduler.data_compliance.get_current_user",
                    new_callable=AsyncMock, return_value=admin):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await export_borrower_data("not-an-email", MagicMock(), MagicMock())
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_export_happy_path(self):
        """Admin can export borrower data successfully."""
        from routes.scheduler.data_compliance import export_borrower_data

        admin = MockUser(role="admin")
        appt = MockAppointment(attendee_email="borrower@example.com")
        db = _build_mock_db_query(appointments=[appt])

        mock_models = {"Appointment": MagicMock(), "SchedulerAuditLog": MagicMock()}

        with patch("routes.scheduler.data_compliance.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.data_compliance.get_models", return_value=mock_models), \
             patch("routes.scheduler.data_compliance._audit_log"):
            result = await export_borrower_data("borrower@example.com", MagicMock(), db)

        assert result["export_type"] == "scheduler_data_export"
        assert result["borrower_email"] == "borrower@example.com"
        assert "data" in result
        assert "counts" in result
        assert result["counts"]["appointments"] == 1

    @pytest.mark.asyncio
    async def test_export_empty_result(self):
        """Export with no matching data returns empty lists."""
        from routes.scheduler.data_compliance import export_borrower_data

        admin = MockUser(role="admin")
        db = _build_mock_db_query(appointments=[])

        mock_models = {"Appointment": MagicMock(), "SchedulerAuditLog": MagicMock()}

        with patch("routes.scheduler.data_compliance.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.data_compliance.get_models", return_value=mock_models), \
             patch("routes.scheduler.data_compliance._audit_log"):
            result = await export_borrower_data("nobody@example.com", MagicMock(), db)

        assert result["counts"]["appointments"] == 0

    @pytest.mark.asyncio
    async def test_export_tenant_isolation(self):
        """Export should filter by organization_id."""
        from routes.scheduler.data_compliance import export_borrower_data

        admin = MockUser(role="admin", organization_id=42)
        db = _build_mock_db_query(appointments=[])

        mock_models = {"Appointment": MagicMock(), "SchedulerAuditLog": MagicMock()}

        with patch("routes.scheduler.data_compliance.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.data_compliance.get_models", return_value=mock_models), \
             patch("routes.scheduler.data_compliance._audit_log"):
            result = await export_borrower_data("test@example.com", MagicMock(), db)

        assert result["organization_id"] == 42


class TestDataDeletion:
    """Tests for DELETE /data-delete/{borrower_email}."""

    @pytest.mark.asyncio
    async def test_delete_requires_admin(self):
        """Non-admin users should get 403."""
        from routes.scheduler.data_compliance import delete_borrower_data

        non_admin = MockUser(role="loan_officer")

        with patch("routes.scheduler.data_compliance.get_current_user",
                    new_callable=AsyncMock, return_value=non_admin):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await delete_borrower_data("test@example.com", MagicMock(), MagicMock())
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_invalid_email(self):
        """Invalid email should return 400."""
        from routes.scheduler.data_compliance import delete_borrower_data

        admin = MockUser(role="admin")

        with patch("routes.scheduler.data_compliance.get_current_user",
                    new_callable=AsyncMock, return_value=admin):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await delete_borrower_data("bad-email", MagicMock(), MagicMock())
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_anonymizes_appointments(self):
        """Deletion should anonymize appointment PII fields."""
        from routes.scheduler.data_compliance import delete_borrower_data, _REDACTED, _ANON_EMAIL

        admin = MockUser(role="admin")
        appt = MockAppointment(attendee_email="borrower@example.com")
        db = _build_mock_db_query(appointments=[appt])

        mock_models = {"Appointment": MagicMock(), "SchedulerAuditLog": None}

        with patch("routes.scheduler.data_compliance.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.data_compliance.get_models", return_value=mock_models), \
             patch("routes.scheduler.data_compliance._audit_log"):
            result = await delete_borrower_data("borrower@example.com", MagicMock(), db)

        assert result["success"] is True
        assert result["records_affected"]["appointments_anonymized"] == 1
        # Verify the appointment's PII fields were overwritten
        assert appt.attendee_name == _REDACTED
        assert appt.attendee_email == _ANON_EMAIL
        assert appt.attendee_phone is None
        assert appt.attendee_notes is None


class TestDataRetentionReport:
    """Tests for GET /data-retention/report."""

    @pytest.mark.asyncio
    async def test_retention_report_requires_admin(self):
        """Non-admin users should get 403."""
        from routes.scheduler.data_compliance import get_data_retention_report

        non_admin = MockUser(role="loan_officer")

        with patch("routes.scheduler.data_compliance.get_current_user",
                    new_callable=AsyncMock, return_value=non_admin):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await get_data_retention_report(MagicMock(), 730, MagicMock())
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_retention_report_happy_path(self):
        """Admin can view retention report."""
        from routes.scheduler.data_compliance import get_data_retention_report

        admin = MockUser(role="admin")
        db = _build_mock_db_query()

        mock_models = {"Appointment": MagicMock(), "SchedulerAuditLog": None}

        with patch("routes.scheduler.data_compliance.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.data_compliance.get_models", return_value=mock_models), \
             patch("routes.scheduler.data_compliance._audit_log"):
            result = await get_data_retention_report(MagicMock(), 730, db)

        assert "retention_period_days" in result
        assert result["retention_period_days"] == 730
        assert "appointments" in result
        assert "recommendations" in result
