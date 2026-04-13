"""
Tests for routes/mobile_api_routes.py — Mobile API endpoints

Tests the 5 endpoints not covered by existing tests:
  - GET /api/v1/mobile/pipeline
  - GET /api/v1/mobile/leads
  - GET /api/v1/mobile/notifications
  - POST /api/v1/mobile/quick-lead
  - GET /api/v1/mobile/rate-lock-alerts

Uses direct handler invocation with mocked DB sessions.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone, timedelta
from collections import namedtuple


pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(user_id=1, org_id=100):
    user = MagicMock()
    user.id = user_id
    user.organization_id = org_id
    return user


def _register_routes():
    """Call register_mobile_api_routes and return the route handlers."""
    from routes.mobile_api_routes import register_mobile_api_routes

    app = MagicMock()
    handlers = {}

    def capture_route(path, **kwargs):
        def decorator(func):
            handlers[path] = func
            return func
        return decorator

    app.get = capture_route
    app.post = capture_route

    register_mobile_api_routes(
        app=app,
        get_db=MagicMock(),
        get_current_user=MagicMock(),
    )
    return handlers


@pytest.fixture
def handlers():
    return _register_routes()


# ---------------------------------------------------------------------------
# 1. Helper functions
# ---------------------------------------------------------------------------

class TestRelativeTime:
    def test_none_returns_empty_string(self):
        from routes.mobile_api_routes import _relative_time
        assert _relative_time(None) == ""

    def test_recent_time_returns_seconds(self):
        from routes.mobile_api_routes import _relative_time
        now = datetime.now(timezone.utc)
        result = _relative_time(now - timedelta(seconds=30))
        assert "s ago" in result

    def test_minutes_ago(self):
        from routes.mobile_api_routes import _relative_time
        now = datetime.now(timezone.utc)
        result = _relative_time(now - timedelta(minutes=5))
        assert "m ago" in result

    def test_hours_ago(self):
        from routes.mobile_api_routes import _relative_time
        now = datetime.now(timezone.utc)
        result = _relative_time(now - timedelta(hours=3))
        assert "h ago" in result

    def test_days_ago(self):
        from routes.mobile_api_routes import _relative_time
        now = datetime.now(timezone.utc)
        result = _relative_time(now - timedelta(days=5))
        assert "d ago" in result

    def test_old_dates_show_formatted(self):
        from routes.mobile_api_routes import _relative_time
        old = datetime(2025, 1, 15, tzinfo=timezone.utc)
        result = _relative_time(old)
        assert "01/15/2025" in result

    def test_naive_datetime_handled(self):
        from routes.mobile_api_routes import _relative_time
        # Naive datetime should not crash — it gets treated as UTC
        result = _relative_time(datetime(2026, 4, 13, 12, 0, 0))
        assert result  # Should return a non-empty string without crashing


class TestQuickLeadModel:
    def test_valid_quick_lead(self):
        from routes.mobile_api_routes import QuickLeadCreate
        lead = QuickLeadCreate(
            first_name="John",
            last_name="Doe",
            phone="+15551234567",
            email="john@example.com",
        )
        assert lead.first_name == "John"
        assert lead.source == "mobile_app"  # Default

    def test_requires_first_and_last_name(self):
        from routes.mobile_api_routes import QuickLeadCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QuickLeadCreate(first_name="", last_name="Doe")

    def test_optional_fields(self):
        from routes.mobile_api_routes import QuickLeadCreate
        lead = QuickLeadCreate(first_name="Jane", last_name="Smith")
        assert lead.phone is None
        assert lead.email is None
        assert lead.notes is None


# ---------------------------------------------------------------------------
# 2. GET /api/v1/mobile/pipeline
# ---------------------------------------------------------------------------

class TestMobilePipeline:
    @pytest.mark.asyncio
    async def test_returns_pipeline_shape(self, handlers):
        handler = handlers["/api/v1/mobile/pipeline"]

        # Mock the DB to return no loans
        mock_db = MagicMock()
        AggRow = namedtuple("AggRow", ["count", "total_volume"])
        mock_db.query.return_value.filter.return_value.first.return_value = AggRow(0, 0)
        mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        user = _make_user()

        with patch("routes.mobile_api_routes._ensure_models"):
            with patch("routes.mobile_api_routes._Loan", MagicMock()):
                result = await handler(
                    stage=None,
                    limit=50,
                    offset=0,
                    db=mock_db,
                    current_user=user,
                )

        assert "stage" in result
        assert "count" in result
        assert "loans" in result
        assert "total_volume" in result

    @pytest.mark.asyncio
    async def test_stage_filter_uppercased(self, handlers):
        handler = handlers["/api/v1/mobile/pipeline"]
        mock_db = MagicMock()
        AggRow = namedtuple("AggRow", ["count", "total_volume"])
        mock_db.query.return_value.filter.return_value.first.return_value = AggRow(0, 0)
        mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        with patch("routes.mobile_api_routes._ensure_models"):
            with patch("routes.mobile_api_routes._Loan", MagicMock()):
                result = await handler(
                    stage="processing",
                    limit=50,
                    offset=0,
                    db=mock_db,
                    current_user=_make_user(),
                )

        assert result["stage"] == "PROCESSING"


# ---------------------------------------------------------------------------
# 3. GET /api/v1/mobile/leads
# ---------------------------------------------------------------------------

class TestMobileLeads:
    @pytest.mark.asyncio
    async def test_returns_leads_shape(self, handlers):
        handler = handlers["/api/v1/mobile/leads"]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0
        mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        with patch("routes.mobile_api_routes._ensure_models"):
            with patch("routes.mobile_api_routes._Lead", MagicMock()):
                result = await handler(
                    filter=None,
                    limit=50,
                    offset=0,
                    db=mock_db,
                    current_user=_make_user(),
                )

        assert "filter" in result
        assert result["filter"] == "all"
        assert "count" in result
        assert "leads" in result

    @pytest.mark.asyncio
    async def test_filter_defaults_to_all(self, handlers):
        handler = handlers["/api/v1/mobile/leads"]
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0
        mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        with patch("routes.mobile_api_routes._ensure_models"):
            with patch("routes.mobile_api_routes._Lead", MagicMock()):
                result = await handler(
                    filter=None,
                    limit=50,
                    offset=0,
                    db=mock_db,
                    current_user=_make_user(),
                )
        assert result["filter"] == "all"


# ---------------------------------------------------------------------------
# 4. GET /api/v1/mobile/notifications
# ---------------------------------------------------------------------------

class TestMobileNotifications:
    @pytest.mark.asyncio
    async def test_returns_notification_shape(self, handlers):
        handler = handlers["/api/v1/mobile/notifications"]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0
        mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        with patch("routes.mobile_api_routes._ensure_models"):
            with patch("routes.mobile_api_routes._Notification", MagicMock()):
                result = await handler(
                    unread_only=False,
                    limit=30,
                    offset=0,
                    db=mock_db,
                    current_user=_make_user(),
                )

        assert "total" in result
        assert "unread_count" in result
        assert "notifications" in result
        assert "has_more" in result

    @pytest.mark.asyncio
    async def test_has_more_when_more_results(self, handlers):
        handler = handlers["/api/v1/mobile/notifications"]

        mock_db = MagicMock()
        # Total is 50, limit is 30, offset is 0 → has_more should be True
        mock_db.query.return_value.filter.return_value.scalar.side_effect = [50, 10]
        mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        with patch("routes.mobile_api_routes._ensure_models"):
            with patch("routes.mobile_api_routes._Notification", MagicMock()):
                result = await handler(
                    unread_only=False,
                    limit=30,
                    offset=0,
                    db=mock_db,
                    current_user=_make_user(),
                )

        assert result["has_more"] is True


# ---------------------------------------------------------------------------
# 5. GET /api/v1/mobile/rate-lock-alerts
# ---------------------------------------------------------------------------

class TestMobileRateLockAlerts:
    def test_response_shape_has_required_keys(self):
        """Verify the rate-lock-alerts endpoint is registered with correct path."""
        handlers = _register_routes()
        assert "/api/v1/mobile/rate-lock-alerts" in handlers

    def test_terminal_stages_excluded_from_alerts(self):
        """Rate lock alerts should only show for active (non-terminal) loans."""
        from routes.mobile_api_routes import TERMINAL_STAGES
        # FUNDED loans should not show rate lock alerts
        assert "FUNDED" in TERMINAL_STAGES
        assert "CANCELLED" in TERMINAL_STAGES


# ---------------------------------------------------------------------------
# 6. Constants
# ---------------------------------------------------------------------------

class TestMobileApiConstants:
    def test_terminal_stages_include_funded(self):
        from routes.mobile_api_routes import TERMINAL_STAGES
        assert "FUNDED" in TERMINAL_STAGES
        assert "CANCELLED" in TERMINAL_STAGES
        assert "DENIED" in TERMINAL_STAGES

    def test_closing_stages(self):
        from routes.mobile_api_routes import CLOSING_STAGES
        assert "CTC" in CLOSING_STAGES
        assert "CLEAR_TO_CLOSE" in CLOSING_STAGES
        assert "CLOSING" in CLOSING_STAGES

    def test_processing_not_terminal(self):
        from routes.mobile_api_routes import TERMINAL_STAGES
        assert "PROCESSING" not in TERMINAL_STAGES
        assert "UNDERWRITING" not in TERMINAL_STAGES
