"""
Calendar Audit Service & Routes — Test Suite

Tests for the comprehensive calendar audit logging system:
- CalendarAuditLog model fields and indexes
- CalendarAuditService.log() — core logging
- CalendarAuditService.compute_changes() — diff computation
- CalendarAuditService.entity_to_dict() — ORM-to-dict conversion
- CalendarAuditService.get_entity_history() — entity audit trail
- CalendarAuditService.get_user_activity() — user activity log
- CalendarAuditService.search_audit_logs() — filtered search
- CalendarAuditService.get_suspicious_activity() — anomaly detection
- CalendarAuditService.get_audit_stats() — aggregate statistics
- _audit_log dual-write (legacy + comprehensive)
- Audit route endpoints
- Severity and category inference
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch, AsyncMock, PropertyMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock CalendarAuditLog model for testing without a real database
# =============================================================================

class _Col:
    """Fake SQLAlchemy column descriptor for use in .filter() expressions."""
    def __eq__(self, other): return True
    def __ne__(self, other): return True
    def __lt__(self, other): return True
    def __gt__(self, other): return True
    def __le__(self, other): return True
    def __ge__(self, other): return True
    def notin_(self, values): return True
    def in_(self, values): return True
    def is_(self, value): return True
    def isnot(self, value): return True
    def __hash__(self): return id(self)


class MockCalendarAuditLog:
    """Mock CalendarAuditLog model that stores instances for inspection."""

    _instances = []

    # Class-level column descriptors for SQLAlchemy filter() expressions
    # These must match the attribute names used in the service queries
    organization_id = _Col()
    event_type = _Col()
    event_category = _Col()
    severity = _Col()
    actor_id = _Col()
    actor_type = _Col()
    entity_type = _Col()
    entity_id = _Col()
    created_at = _Col()
    id = _Col()

    def __init__(self, **kwargs):
        MockCalendarAuditLog._instances.append(self)
        self._id = len(MockCalendarAuditLog._instances)
        self.id = self._id
        self.organization_id = kwargs.get("organization_id")
        self.event_type = kwargs.get("event_type")
        self.event_category = kwargs.get("event_category")
        self.severity = kwargs.get("severity", "info")
        self.actor_id = kwargs.get("actor_id")
        self.actor_type = kwargs.get("actor_type", "user")
        self.actor_ip = kwargs.get("actor_ip")
        self.actor_user_agent = kwargs.get("actor_user_agent")
        self.entity_type = kwargs.get("entity_type")
        self.entity_id = kwargs.get("entity_id")
        self.changes = kwargs.get("changes")
        self.extra_metadata = kwargs.get("extra_metadata")
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))

    @classmethod
    def reset(cls):
        cls._instances = []


@pytest.fixture(autouse=True)
def reset_mock_instances():
    """Reset mock instances before each test."""
    MockCalendarAuditLog.reset()
    yield


@pytest.fixture
def mock_db():
    """Create a chainable mock DB session."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.query.return_value.filter.return_value = db.query.return_value
    db.query.return_value.order_by.return_value = db.query.return_value
    db.query.return_value.offset.return_value = db.query.return_value
    db.query.return_value.limit.return_value = db.query.return_value
    db.query.return_value.count.return_value = 0
    db.query.return_value.all.return_value = []
    db.query.return_value.group_by.return_value = db.query.return_value
    db.query.return_value.having.return_value = db.query.return_value
    db.query.return_value.scalar.return_value = 0
    return db


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request."""
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = "192.168.1.100"
    request.headers = {"user-agent": "Mozilla/5.0 TestBrowser"}
    return request


@pytest.fixture
def audit_service():
    """Set up CalendarAuditService with mock model."""
    from services.calendar_audit_service import CalendarAuditService
    CalendarAuditService.init(MockCalendarAuditLog)
    return CalendarAuditService


# =============================================================================
# CalendarAuditService.compute_changes() Tests
# =============================================================================

class TestComputeChanges:
    """Test the change diff computation utility."""

    def test_no_changes(self, audit_service):
        old = {"title": "Test", "duration": 30}
        new = {"title": "Test", "duration": 30}
        changes = audit_service.compute_changes(old, new)
        assert changes == {}

    def test_value_changed(self, audit_service):
        old = {"title": "Old Title", "duration": 30}
        new = {"title": "New Title", "duration": 30}
        changes = audit_service.compute_changes(old, new)
        assert "title" in changes
        assert changes["title"]["old"] == "Old Title"
        assert changes["title"]["new"] == "New Title"
        assert "duration" not in changes

    def test_field_added(self, audit_service):
        old = {"title": "Test"}
        new = {"title": "Test", "notes": "Some notes"}
        changes = audit_service.compute_changes(old, new)
        assert "notes" in changes
        assert changes["notes"]["old"] is None
        assert changes["notes"]["new"] == "Some notes"

    def test_field_removed(self, audit_service):
        old = {"title": "Test", "notes": "Some notes"}
        new = {"title": "Test"}
        changes = audit_service.compute_changes(old, new)
        assert "notes" in changes
        assert changes["notes"]["old"] == "Some notes"
        assert changes["notes"]["new"] is None

    def test_specific_fields_filter(self, audit_service):
        old = {"title": "Old", "duration": 30, "location": "A"}
        new = {"title": "New", "duration": 60, "location": "B"}
        changes = audit_service.compute_changes(old, new, fields={"title", "duration"})
        assert "title" in changes
        assert "duration" in changes
        assert "location" not in changes

    def test_datetime_normalization(self, audit_service):
        dt = datetime(2026, 3, 10, 14, 0, 0)
        old = {"scheduled_at": dt}
        new = {"scheduled_at": dt}
        changes = audit_service.compute_changes(old, new)
        assert changes == {}

    def test_datetime_changed(self, audit_service):
        old = {"scheduled_at": datetime(2026, 3, 10, 14, 0, 0)}
        new = {"scheduled_at": datetime(2026, 3, 11, 14, 0, 0)}
        changes = audit_service.compute_changes(old, new)
        assert "scheduled_at" in changes

    def test_none_values(self, audit_service):
        old = {"field_a": None}
        new = {"field_a": None}
        changes = audit_service.compute_changes(old, new)
        assert changes == {}

    def test_none_to_value(self, audit_service):
        old = {"field_a": None}
        new = {"field_a": "hello"}
        changes = audit_service.compute_changes(old, new)
        assert "field_a" in changes
        assert changes["field_a"]["old"] is None
        assert changes["field_a"]["new"] == "hello"

    def test_multiple_changes(self, audit_service):
        old = {"title": "A", "duration": 30, "status": "booked"}
        new = {"title": "B", "duration": 60, "status": "booked"}
        changes = audit_service.compute_changes(old, new)
        assert len(changes) == 2
        assert "title" in changes
        assert "duration" in changes


# =============================================================================
# CalendarAuditService.log() Tests
# =============================================================================

class TestAuditLog:
    """Test the core audit logging method."""

    @pytest.mark.asyncio
    async def test_log_basic(self, audit_service, mock_db):
        result = await audit_service.log(
            db=mock_db,
            event_type="appointment.created",
            entity_type="appointment",
            entity_id="42",
            actor_id="1",
            organization_id=10,
        )
        assert result is not None
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

        # Verify the entry was created with correct attributes
        entry = mock_db.add.call_args[0][0]
        assert entry.event_type == "appointment.created"
        assert entry.entity_type == "appointment"
        assert entry.entity_id == "42"
        assert entry.actor_id == "1"
        assert entry.organization_id == 10

    @pytest.mark.asyncio
    async def test_log_with_request(self, audit_service, mock_db, mock_request):
        await audit_service.log(
            db=mock_db,
            event_type="appointment.cancelled",
            entity_type="appointment",
            entity_id="99",
            actor_id="5",
            organization_id=10,
            request=mock_request,
        )
        entry = mock_db.add.call_args[0][0]
        assert entry.actor_ip == "192.168.1.100"
        assert "Mozilla" in entry.actor_user_agent

    @pytest.mark.asyncio
    async def test_log_auto_category(self, audit_service, mock_db):
        await audit_service.log(
            db=mock_db,
            event_type="appointment.created",
            entity_type="appointment",
            entity_id="1",
            actor_id="1",
            organization_id=10,
        )
        entry = mock_db.add.call_args[0][0]
        assert entry.event_category == "booking"

    @pytest.mark.asyncio
    async def test_log_auto_severity_info(self, audit_service, mock_db):
        await audit_service.log(
            db=mock_db,
            event_type="appointment.created",
            entity_type="appointment",
            entity_id="1",
            actor_id="1",
            organization_id=10,
        )
        entry = mock_db.add.call_args[0][0]
        assert entry.severity == "info"

    @pytest.mark.asyncio
    async def test_log_auto_severity_warning(self, audit_service, mock_db):
        await audit_service.log(
            db=mock_db,
            event_type="appointment.no_show",
            entity_type="appointment",
            entity_id="1",
            actor_id="system",
            organization_id=10,
        )
        entry = mock_db.add.call_args[0][0]
        assert entry.severity == "warning"

    @pytest.mark.asyncio
    async def test_log_auto_severity_critical(self, audit_service, mock_db):
        await audit_service.log(
            db=mock_db,
            event_type="compliance.alert",
            entity_type="appointment",
            entity_id="1",
            actor_id="system",
            organization_id=10,
        )
        entry = mock_db.add.call_args[0][0]
        assert entry.severity == "critical"

    @pytest.mark.asyncio
    async def test_log_override_severity(self, audit_service, mock_db):
        await audit_service.log(
            db=mock_db,
            event_type="appointment.created",
            entity_type="appointment",
            entity_id="1",
            actor_id="1",
            organization_id=10,
            severity="critical",
        )
        entry = mock_db.add.call_args[0][0]
        assert entry.severity == "critical"

    @pytest.mark.asyncio
    async def test_log_with_changes(self, audit_service, mock_db):
        changes = {"title": {"old": "A", "new": "B"}}
        await audit_service.log(
            db=mock_db,
            event_type="appointment.updated",
            entity_type="appointment",
            entity_id="42",
            actor_id="1",
            organization_id=10,
            changes=changes,
        )
        entry = mock_db.add.call_args[0][0]
        assert entry.changes == changes

    @pytest.mark.asyncio
    async def test_log_with_metadata(self, audit_service, mock_db):
        meta = {"reason": "schedule conflict", "related_id": 99}
        await audit_service.log(
            db=mock_db,
            event_type="appointment.rescheduled",
            entity_type="appointment",
            entity_id="42",
            actor_id="1",
            organization_id=10,
            metadata=meta,
        )
        entry = mock_db.add.call_args[0][0]
        assert entry.extra_metadata == meta

    @pytest.mark.asyncio
    async def test_log_actor_types(self, audit_service, mock_db):
        for actor_type in ["user", "system", "ai_agent", "webhook", "public"]:
            mock_db.reset_mock()
            await audit_service.log(
                db=mock_db,
                event_type="appointment.created",
                entity_type="appointment",
                entity_id="1",
                actor_id="1",
                organization_id=10,
                actor_type=actor_type,
            )
            entry = mock_db.add.call_args[0][0]
            assert entry.actor_type == actor_type

    @pytest.mark.asyncio
    async def test_log_no_request(self, audit_service, mock_db):
        """Logging should work without a request object."""
        await audit_service.log(
            db=mock_db,
            event_type="appointment.created",
            entity_type="appointment",
            entity_id="1",
            actor_id="1",
            organization_id=10,
            request=None,
        )
        entry = mock_db.add.call_args[0][0]
        assert entry.actor_ip is None
        assert entry.actor_user_agent is None

    @pytest.mark.asyncio
    async def test_log_failure_returns_none(self, audit_service, mock_db):
        """If db.add raises, should return None and not propagate."""
        mock_db.add.side_effect = Exception("DB error")
        result = await audit_service.log(
            db=mock_db,
            event_type="appointment.created",
            entity_type="appointment",
            entity_id="1",
            actor_id="1",
            organization_id=10,
        )
        assert result is None


# =============================================================================
# CalendarAuditService.log_legacy() Tests
# =============================================================================

class TestLegacyBridge:
    """Test the backward-compatible legacy bridge method."""

    @pytest.mark.asyncio
    async def test_legacy_maps_action_to_event_type(self, audit_service, mock_db):
        await audit_service.log_legacy(
            db=mock_db,
            org_id=10,
            user_id=5,
            action="cancelled",
            entity_type="appointment",
            entity_id=42,
        )
        entry = mock_db.add.call_args[0][0]
        assert entry.event_type == "appointment.cancelled"
        assert entry.actor_id == "5"
        assert entry.entity_id == "42"

    @pytest.mark.asyncio
    async def test_legacy_with_changes_and_request(self, audit_service, mock_db, mock_request):
        changes = {"status": {"old": "booked", "new": "cancelled"}}
        await audit_service.log_legacy(
            db=mock_db,
            org_id=10,
            user_id=5,
            action="updated",
            entity_type="booking_link",
            entity_id=7,
            changes=changes,
            request=mock_request,
        )
        entry = mock_db.add.call_args[0][0]
        assert entry.changes == changes
        assert entry.actor_ip == "192.168.1.100"


# =============================================================================
# CalendarAuditService.entity_to_dict() Tests
# =============================================================================

class TestEntityToDict:
    """Test ORM model to dict conversion."""

    def test_with_specific_fields(self, audit_service):
        entity = MagicMock()
        entity.title = "Discovery Call"
        entity.status = "booked"
        entity.duration = 30
        result = audit_service.entity_to_dict(entity, fields=["title", "status"])
        assert result == {"title": "Discovery Call", "status": "booked"}

    def test_with_none_entity(self, audit_service):
        result = audit_service.entity_to_dict(None)
        assert result == {}


# =============================================================================
# CalendarAuditService.get_entity_history() Tests
# =============================================================================

class TestGetEntityHistory:
    """Test entity audit trail retrieval."""

    @pytest.mark.asyncio
    @patch('services.calendar_audit_service.desc', lambda x: x)
    async def test_returns_entries(self, audit_service, mock_db):
        mock_entry = MockCalendarAuditLog(
            organization_id=10,
            event_type="appointment.created",
            entity_type="appointment",
            entity_id="42",
            actor_id="1",
            actor_type="user",
            severity="info",
        )
        # Set up the full mock chain
        chain = mock_db.query.return_value
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.offset.return_value = chain
        chain.limit.return_value = chain
        chain.all.return_value = [mock_entry]

        result = await audit_service.get_entity_history(
            db=mock_db,
            entity_type="appointment",
            entity_id="42",
            organization_id=10,
        )
        assert len(result) == 1
        assert result[0]["event_type"] == "appointment.created"
        assert result[0]["entity_id"] == "42"

    @pytest.mark.asyncio
    @patch('services.calendar_audit_service.desc', lambda x: x)
    async def test_empty_result(self, audit_service, mock_db):
        chain = mock_db.query.return_value
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.offset.return_value = chain
        chain.limit.return_value = chain
        chain.all.return_value = []

        result = await audit_service.get_entity_history(
            db=mock_db,
            entity_type="appointment",
            entity_id="999",
        )
        assert result == []


# =============================================================================
# CalendarAuditService.get_user_activity() Tests
# =============================================================================

class TestGetUserActivity:
    """Test user activity retrieval."""

    @pytest.mark.asyncio
    @patch('services.calendar_audit_service.desc', lambda x: x)
    async def test_returns_user_entries(self, audit_service, mock_db):
        mock_entry = MockCalendarAuditLog(
            organization_id=10,
            event_type="appointment.created",
            entity_type="appointment",
            entity_id="42",
            actor_id="5",
            actor_type="user",
            severity="info",
        )
        chain = mock_db.query.return_value
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.offset.return_value = chain
        chain.limit.return_value = chain
        chain.all.return_value = [mock_entry]

        result = await audit_service.get_user_activity(
            db=mock_db,
            user_id="5",
            organization_id=10,
            days=30,
        )
        assert len(result) == 1
        assert result[0]["actor_id"] == "5"


# =============================================================================
# CalendarAuditService.search_audit_logs() Tests
# =============================================================================

class TestSearchAuditLogs:
    """Test audit log search with filters."""

    @pytest.mark.asyncio
    @patch('services.calendar_audit_service.desc', lambda x: x)
    async def test_search_returns_structure(self, audit_service, mock_db):
        chain = mock_db.query.return_value
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.offset.return_value = chain
        chain.limit.return_value = chain
        chain.count.return_value = 0
        chain.all.return_value = []

        result = await audit_service.search_audit_logs(
            db=mock_db,
            organization_id=10,
        )
        assert "entries" in result
        assert "total" in result
        assert "limit" in result
        assert "offset" in result

    @pytest.mark.asyncio
    @patch('services.calendar_audit_service.desc', lambda x: x)
    async def test_search_with_filters(self, audit_service, mock_db):
        """Should not raise when all filters are provided."""
        chain = mock_db.query.return_value
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.offset.return_value = chain
        chain.limit.return_value = chain
        chain.count.return_value = 0
        chain.all.return_value = []

        result = await audit_service.search_audit_logs(
            db=mock_db,
            organization_id=10,
            event_type="appointment.created",
            event_category="booking",
            severity="info",
            actor_id="1",
            actor_type="user",
            entity_type="appointment",
            entity_id="42",
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
        )
        assert "entries" in result


# =============================================================================
# CalendarAuditService.get_suspicious_activity() Tests
# =============================================================================

class TestSuspiciousActivity:
    """Test suspicious activity detection."""

    @pytest.mark.asyncio
    async def test_returns_expected_categories(self, audit_service, mock_db):
        result = await audit_service.get_suspicious_activity(
            db=mock_db,
            organization_id=10,
            days=7,
        )
        assert "mass_cancellations" in result
        assert "off_hours_access" in result
        assert "unusual_actors" in result
        assert "critical_events" in result
        assert "summary" in result
        assert "total_findings" in result["summary"]

    @pytest.mark.asyncio
    async def test_summary_counts(self, audit_service, mock_db):
        """When no findings, total should be 0."""
        result = await audit_service.get_suspicious_activity(
            db=mock_db,
            organization_id=10,
        )
        assert result["summary"]["total_findings"] == 0


# =============================================================================
# CalendarAuditService.get_audit_stats() Tests
# =============================================================================

class TestGetAuditStats:
    """Test aggregate audit statistics."""

    @pytest.mark.asyncio
    async def test_returns_structure(self, audit_service, mock_db):
        mock_db.query.return_value.filter.return_value.scalar.return_value = 42

        result = await audit_service.get_audit_stats(
            db=mock_db,
            organization_id=10,
            days=30,
        )
        assert "period_days" in result
        assert result["period_days"] == 30
        assert "total_entries" in result
        assert "by_event_type" in result
        assert "by_severity" in result
        assert "by_actor_type" in result


# =============================================================================
# _audit_log dual-write Tests
# =============================================================================

class TestAuditLogDualWrite:
    """Test the _audit_log helper does dual-write to both models."""

    def test_dual_write_to_both_tables(self):
        """_audit_log should write to both SchedulerAuditLog and CalendarAuditLog."""
        from routes.scheduler_appointment_routes import _audit_log, _infer_event_category, _infer_severity

        mock_db = MagicMock()
        mock_scheduler_audit = MagicMock()
        mock_calendar_audit = MagicMock()

        # Set up models dict
        import routes.scheduler_appointment_routes as sar
        original_models = sar._models
        sar._models = {
            "SchedulerAuditLog": mock_scheduler_audit,
            "CalendarAuditLog": mock_calendar_audit,
        }

        try:
            _audit_log(
                db=mock_db,
                org_id=10,
                user_id=5,
                action="created",
                entity_type="appointment",
                entity_id=42,
                changes={"title": {"old": None, "new": "Call"}},
            )

            # Should have called db.add twice (once per model)
            assert mock_db.add.call_count == 2

            # Verify legacy SchedulerAuditLog was called
            mock_scheduler_audit.assert_called_once()
            legacy_kwargs = mock_scheduler_audit.call_args
            assert legacy_kwargs[1]["action"] == "created" or legacy_kwargs.kwargs.get("action") == "created"

            # Verify CalendarAuditLog was called
            mock_calendar_audit.assert_called_once()
        finally:
            sar._models = original_models

    def test_dual_write_skips_missing_models(self):
        """_audit_log should work when CalendarAuditLog model is not available."""
        from routes.scheduler_appointment_routes import _audit_log

        mock_db = MagicMock()
        mock_scheduler_audit = MagicMock()

        import routes.scheduler_appointment_routes as sar
        original_models = sar._models
        sar._models = {
            "SchedulerAuditLog": mock_scheduler_audit,
            # CalendarAuditLog intentionally missing
        }

        try:
            _audit_log(
                db=mock_db,
                org_id=10,
                user_id=5,
                action="created",
                entity_type="appointment",
            )
            # Should only write to legacy
            assert mock_db.add.call_count == 1
        finally:
            sar._models = original_models


# =============================================================================
# Severity and Category Inference Tests
# =============================================================================

class TestSeverityAndCategoryInference:
    """Test the _infer_event_category and _infer_severity helpers."""

    def test_infer_category_booking(self):
        from routes.scheduler_appointment_routes import _infer_event_category
        assert _infer_event_category("created") == "booking"
        assert _infer_event_category("confirmed") == "booking"
        assert _infer_event_category("completed") == "booking"

    def test_infer_category_modification(self):
        from routes.scheduler_appointment_routes import _infer_event_category
        assert _infer_event_category("updated") == "modification"
        assert _infer_event_category("cancelled") == "modification"
        assert _infer_event_category("rescheduled") == "modification"
        assert _infer_event_category("deleted") == "modification"

    def test_infer_category_settings(self):
        from routes.scheduler_appointment_routes import _infer_event_category
        assert _infer_event_category("settings_changed") == "settings"

    def test_infer_category_export(self):
        from routes.scheduler_appointment_routes import _infer_event_category
        assert _infer_event_category("exported") == "export"

    def test_infer_category_unknown(self):
        from routes.scheduler_appointment_routes import _infer_event_category
        assert _infer_event_category("unknown_action") == "other"

    def test_infer_severity_info(self):
        from routes.scheduler_appointment_routes import _infer_severity
        assert _infer_severity("created") == "info"
        assert _infer_severity("updated") == "info"
        assert _infer_severity("deleted") == "info"

    def test_infer_severity_warning(self):
        from routes.scheduler_appointment_routes import _infer_severity
        assert _infer_severity("no_show") == "warning"
        assert _infer_severity("rescheduled") == "warning"


# =============================================================================
# CalendarAuditLog Model Tests
# =============================================================================

class TestCalendarAuditLogModel:
    """Test the CalendarAuditLog model definition.

    Uses SQLAlchemy's Base.metadata.tables to inspect the model schema
    after the factory function has been called. Tests may skip if the
    factory has not been called yet (e.g. no database models loaded).
    """

    @pytest.fixture(autouse=True)
    def _load_models(self):
        """Attempt to load models via the factory function."""
        try:
            from db import Base
            from smart_scheduler_models import create_smart_scheduler_models
            self._models = create_smart_scheduler_models(Base)
            self._CalendarAuditLog = self._models.get("CalendarAuditLog")
        except Exception:
            self._models = None
            self._CalendarAuditLog = None

    def test_model_has_required_fields(self):
        """Verify CalendarAuditLog has all required columns."""
        if self._CalendarAuditLog is None:
            pytest.skip("CalendarAuditLog model not available (factory creation failed)")

        assert self._CalendarAuditLog.__tablename__ == "calendar_audit_logs"

        columns = {c.name for c in self._CalendarAuditLog.__table__.columns}
        required_columns = {
            "id", "organization_id", "event_type", "event_category",
            "severity", "actor_id", "actor_type", "actor_ip",
            "actor_user_agent", "entity_type", "entity_id",
            "changes", "extra_metadata", "created_at",
        }
        assert required_columns.issubset(columns), f"Missing columns: {required_columns - columns}"

    def test_model_has_indexes(self):
        """Verify CalendarAuditLog has the expected composite indexes."""
        if self._CalendarAuditLog is None:
            pytest.skip("CalendarAuditLog model not available")

        index_names = {idx.name for idx in self._CalendarAuditLog.__table__.indexes}
        expected_indexes = {
            "ix_cal_audit_org_entity",
            "ix_cal_audit_org_time",
            "ix_cal_audit_actor",
            "ix_cal_audit_event_type",
            "ix_cal_audit_severity",
        }
        assert expected_indexes.issubset(index_names), f"Missing indexes: {expected_indexes - index_names}"

    def test_organization_id_not_nullable(self):
        """organization_id must be NOT NULL for tenant isolation."""
        if self._CalendarAuditLog is None:
            pytest.skip("CalendarAuditLog model not available")

        org_col = self._CalendarAuditLog.__table__.columns["organization_id"]
        assert not org_col.nullable, "organization_id must be NOT NULL"

    def test_organization_id_has_foreign_key(self):
        """organization_id should reference organizations.id."""
        if self._CalendarAuditLog is None:
            pytest.skip("CalendarAuditLog model not available")

        org_col = self._CalendarAuditLog.__table__.columns["organization_id"]
        fk_targets = [fk.target_fullname for fk in org_col.foreign_keys]
        assert "organizations.id" in fk_targets, "organization_id should FK to organizations.id"

    def test_event_type_not_nullable(self):
        """event_type must be NOT NULL."""
        if self._CalendarAuditLog is None:
            pytest.skip("CalendarAuditLog model not available")

        col = self._CalendarAuditLog.__table__.columns["event_type"]
        assert not col.nullable, "event_type must be NOT NULL"

    def test_entity_type_not_nullable(self):
        """entity_type must be NOT NULL."""
        if self._CalendarAuditLog is None:
            pytest.skip("CalendarAuditLog model not available")

        col = self._CalendarAuditLog.__table__.columns["entity_type"]
        assert not col.nullable, "entity_type must be NOT NULL"


# =============================================================================
# Event Constants Tests
# =============================================================================

class TestEventConstants:
    """Test that event type constants are properly defined."""

    def test_all_event_types_have_categories(self):
        from services.calendar_audit_service import (
            EVENT_CATEGORIES,
            EVENT_APPOINTMENT_CREATED,
            EVENT_APPOINTMENT_UPDATED,
            EVENT_APPOINTMENT_CANCELLED,
            EVENT_APPOINTMENT_RESCHEDULED,
            EVENT_APPOINTMENT_CONFIRMED,
            EVENT_APPOINTMENT_COMPLETED,
            EVENT_APPOINTMENT_NO_SHOW,
            EVENT_BOOKING_LINK_CREATED,
            EVENT_BOOKING_LINK_UPDATED,
            EVENT_BOOKING_LINK_DELETED,
            EVENT_BLOCKED_TIME_CREATED,
            EVENT_CONFIG_CREATED,
            EVENT_CONFIG_UPDATED,
            EVENT_DATA_EXPORTED,
            EVENT_COMPLIANCE_ALERT,
        )

        all_events = [
            EVENT_APPOINTMENT_CREATED,
            EVENT_APPOINTMENT_UPDATED,
            EVENT_APPOINTMENT_CANCELLED,
            EVENT_APPOINTMENT_RESCHEDULED,
            EVENT_APPOINTMENT_CONFIRMED,
            EVENT_APPOINTMENT_COMPLETED,
            EVENT_APPOINTMENT_NO_SHOW,
            EVENT_BOOKING_LINK_CREATED,
            EVENT_BOOKING_LINK_UPDATED,
            EVENT_BOOKING_LINK_DELETED,
            EVENT_BLOCKED_TIME_CREATED,
            EVENT_CONFIG_CREATED,
            EVENT_CONFIG_UPDATED,
            EVENT_DATA_EXPORTED,
            EVENT_COMPLIANCE_ALERT,
        ]

        for event in all_events:
            assert event in EVENT_CATEGORIES, f"Event {event} missing from EVENT_CATEGORIES"

    def test_warning_events(self):
        from services.calendar_audit_service import WARNING_EVENTS
        assert "appointment.no_show" in WARNING_EVENTS
        assert "appointment.rescheduled" in WARNING_EVENTS

    def test_critical_events(self):
        from services.calendar_audit_service import CRITICAL_EVENTS
        assert "compliance.alert" in CRITICAL_EVENTS


# =============================================================================
# CalendarAuditService Initialization Tests
# =============================================================================

class TestServiceInitialization:
    """Test service initialization and error handling."""

    def test_init_stores_model(self):
        from services.calendar_audit_service import CalendarAuditService
        CalendarAuditService.init(MockCalendarAuditLog)
        assert CalendarAuditService._CalendarAuditLog is MockCalendarAuditLog

    def test_get_model_raises_if_not_initialized(self):
        from services.calendar_audit_service import CalendarAuditService
        CalendarAuditService._CalendarAuditLog = None
        with pytest.raises(RuntimeError, match="not initialized"):
            CalendarAuditService._get_model()


# =============================================================================
# _entry_to_dict Tests
# =============================================================================

class TestEntryToDict:
    """Test the entry-to-dict conversion helper."""

    def test_converts_all_fields(self):
        from services.calendar_audit_service import _entry_to_dict

        entry = MockCalendarAuditLog(
            organization_id=10,
            event_type="appointment.created",
            event_category="booking",
            severity="info",
            actor_id="5",
            actor_type="user",
            actor_ip="10.0.0.1",
            actor_user_agent="TestAgent",
            entity_type="appointment",
            entity_id="42",
            changes={"title": {"old": None, "new": "Call"}},
            extra_metadata={"source": "api"},
        )

        result = _entry_to_dict(entry)
        assert result["organization_id"] == 10
        assert result["event_type"] == "appointment.created"
        assert result["event_category"] == "booking"
        assert result["severity"] == "info"
        assert result["actor_id"] == "5"
        assert result["actor_type"] == "user"
        assert result["actor_ip"] == "10.0.0.1"
        assert result["entity_type"] == "appointment"
        assert result["entity_id"] == "42"
        assert result["changes"]["title"]["new"] == "Call"
        assert result["metadata"]["source"] == "api"
        assert result["created_at"] is not None


# =============================================================================
# Serialization Helpers Tests
# =============================================================================

class TestSerializationHelpers:
    """Test internal serialization utilities."""

    def test_serialize_value_primitives(self):
        from services.calendar_audit_service import _serialize_value
        assert _serialize_value(None) is None
        assert _serialize_value("hello") == "hello"
        assert _serialize_value(42) == 42
        assert _serialize_value(3.14) == 3.14
        assert _serialize_value(True) is True

    def test_serialize_value_datetime(self):
        from services.calendar_audit_service import _serialize_value
        dt = datetime(2026, 3, 10, 14, 0, 0)
        result = _serialize_value(dt)
        assert isinstance(result, str)
        assert "2026-03-10" in result

    def test_serialize_value_other(self):
        from services.calendar_audit_service import _serialize_value
        result = _serialize_value({"key": "value"})
        assert result == {"key": "value"}

    def test_normalize_for_comparison(self):
        from services.calendar_audit_service import _normalize_for_comparison
        assert _normalize_for_comparison(None) is None
        assert _normalize_for_comparison("hello") == "hello"
        dt = datetime(2026, 3, 10, 14, 0, 0)
        assert _normalize_for_comparison(dt) == dt.isoformat()


# =============================================================================
# Audit Routes Tests
# =============================================================================

class TestAuditRoutes:
    """Test the audit API endpoint structure and validation."""

    def test_router_has_expected_routes(self):
        """Verify the audit router defines all expected endpoints."""
        from routes.audit_routes import router

        paths = [route.path for route in router.routes]
        # Routes include the router prefix /audit/
        assert "/audit/appointment/{appointment_id}" in paths
        assert "/audit/user/{user_id}" in paths
        assert "/audit/search" in paths
        assert "/audit/suspicious" in paths
        assert "/audit/stats" in paths
        assert "/audit/entity/{entity_type}/{entity_id}" in paths

    def test_set_dependencies_initializes_service(self):
        """set_dependencies should call CalendarAuditService.init()."""
        from routes.audit_routes import set_dependencies
        from services.calendar_audit_service import CalendarAuditService

        mock_model = MagicMock()
        set_dependencies(
            get_db_func=MagicMock(),
            get_current_user_func=MagicMock(),
            models_dict={"CalendarAuditLog": mock_model},
        )
        assert CalendarAuditService._CalendarAuditLog is mock_model

    def test_org_id_helper_raises_on_missing(self):
        """_get_org_id should raise 403 when user has no org."""
        from routes.audit_routes import _get_org_id
        from fastapi import HTTPException

        user = MagicMock()
        user.organization_id = None
        with pytest.raises(HTTPException) as exc_info:
            _get_org_id(user)
        assert exc_info.value.status_code == 403

    def test_is_scheduler_admin(self):
        """Admin check should work for expected role names."""
        from routes.audit_routes import _is_scheduler_admin

        admin_user = MagicMock()
        admin_user.permission_role = "admin"
        assert _is_scheduler_admin(admin_user) is True

        regular_user = MagicMock()
        regular_user.permission_role = "loan_officer"
        regular_user.role = "loan_officer"
        assert _is_scheduler_admin(regular_user) is False

        platform_admin = MagicMock()
        platform_admin.permission_role = "platform_admin"
        assert _is_scheduler_admin(platform_admin) is True
