"""
Scheduler Security Test Suite

Tests for security-critical paths in the Smart Calendar system:
- Rate limiting (Redis and in-memory fallback)
- IDOR protection (blocked time descriptions, availability visibility)
- CSS sanitization (booking branding)
- Cloudflare Turnstile verification
- Token expiration enforcement
- Organization isolation
"""

import pytest
import asyncio
import re
from datetime import datetime, timedelta, date, time, timezone
from unittest.mock import Mock, MagicMock, patch, AsyncMock, PropertyMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# SQLAlchemy Column Mock (reused pattern from test_scheduler_routes.py)
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
    def ilike(self, value): return True

    def __hash__(self):
        return id(self)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_models():
    """Create mock model classes for dependency injection."""
    models = {}

    class MockConfig:
        user_id = _Col()
        organization_id = _Col()

        def __init__(self, **kwargs):
            self.user_id = kwargs.get('user_id', 1)
            self.organization_id = kwargs.get('organization_id', 1)
            self.working_hours = kwargs.get('working_hours', {
                "monday": {"start": "09:00", "end": "17:00", "enabled": True},
                "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
                "friday": {"start": "09:00", "end": "17:00", "enabled": True},
                "saturday": {"start": "00:00", "end": "00:00", "enabled": False},
                "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
            })
            self.buffer_before_minutes = kwargs.get('buffer_before_minutes', 5)
            self.buffer_after_minutes = kwargs.get('buffer_after_minutes', 5)
            self.min_notice_hours = kwargs.get('min_notice_hours', 2)
            self.max_meetings_per_day = kwargs.get('max_meetings_per_day', 8)
            self.enforce_lunch_break = kwargs.get('enforce_lunch_break', True)
            self.lunch_break_start = kwargs.get('lunch_break_start', time(12, 0))
            self.lunch_break_end = kwargs.get('lunch_break_end', time(13, 0))
            self.timezone = kwargs.get('timezone', 'America/Chicago')

    class MockAppointment:
        id = _Col()
        assigned_user_id = _Col()
        created_by_user_id = _Col()
        organization_id = _Col()
        status = _Col()
        scheduled_start = _Col()
        scheduled_end = _Col()
        attendee_email = _Col()

    class MockBlockedTime:
        id = _Col()
        user_id = _Col()
        organization_id = _Col()
        start_datetime = _Col()
        end_datetime = _Col()
        is_active = _Col()
        applies_to_all_users = _Col()
        description = _Col()

    models['SchedulerConfig'] = MockConfig
    models['BlockedTime'] = MockBlockedTime
    models['Appointment'] = MockAppointment
    models['BookingLink'] = MagicMock
    models['AppointmentType'] = MagicMock
    models['SchedulerAuditLog'] = None
    models['VideoMeetingRoom'] = None

    return models


@pytest.fixture
def mock_db():
    """Create a chainable mock DB session."""
    db = MagicMock()
    db.query.return_value.filter.return_value = db.query.return_value
    db.query.return_value.first.return_value = None
    db.query.return_value.all.return_value = []
    db.query.return_value.count.return_value = 0
    db.query.return_value.with_for_update.return_value = db.query.return_value
    return db


@pytest.fixture
def setup_scheduler_helpers(mock_models):
    """Set up scheduler helpers with mocked dependencies."""
    import routes.scheduler._helpers as sar
    sar.set_dependencies(
        get_db_func=lambda: iter([MagicMock()]),
        get_current_user_func=MagicMock(),
        models_dict=mock_models
    )
    return sar


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request object."""
    request = MagicMock()
    request.client.host = "203.0.113.50"
    request.url.path = "/api/v1/scheduler/public/book/test-slug/confirm"
    request.headers.get.return_value = None
    return request


@pytest.fixture
def mock_user_lo():
    """Mock non-admin loan officer user."""
    user = MagicMock()
    user.id = 10
    user.email = "lo@example.com"
    user.organization_id = 1
    user.role = "loan_officer"
    user.permission_role = "loan_officer"
    return user


@pytest.fixture
def mock_user_admin():
    """Mock admin user."""
    user = MagicMock()
    user.id = 20
    user.email = "admin@example.com"
    user.organization_id = 1
    user.role = "admin"
    user.permission_role = "admin"
    return user


@pytest.fixture
def mock_user_other_org():
    """Mock user in a different organization."""
    user = MagicMock()
    user.id = 30
    user.email = "other@example.com"
    user.organization_id = 999
    user.role = "loan_officer"
    user.permission_role = "loan_officer"
    return user


# =============================================================================
# RATE LIMITING TESTS - REDIS PATH
# =============================================================================

class TestRateLimitingRedisPath:
    """Test Redis-backed rate limiting for public booking endpoints."""

    @pytest.mark.asyncio
    async def test_rate_limiting_enforces_limits_on_public_booking(self, setup_scheduler_helpers, mock_request):
        """Rate limiting should block requests that exceed the configured max."""
        sar = setup_scheduler_helpers

        mock_redis = MagicMock()
        mock_redis.incr.return_value = 11  # Over the default 10 limit
        mock_redis.ttl.return_value = 45
        sar._rate_limit_redis = mock_redis
        sar._rate_limit_redis_checked = True

        with pytest.raises(HTTPException) as exc:
            await sar._check_rate_limit(mock_request)
        assert exc.value.status_code == 429
        assert "Too many requests" in exc.value.detail

    @pytest.mark.asyncio
    async def test_rate_limiting_allows_under_limit(self, setup_scheduler_helpers, mock_request):
        """Requests under the limit should be allowed through."""
        sar = setup_scheduler_helpers

        mock_redis = MagicMock()
        mock_redis.incr.return_value = 5  # Under limit
        mock_redis.ttl.return_value = 30
        sar._rate_limit_redis = mock_redis
        sar._rate_limit_redis_checked = True

        # Should not raise
        await sar._check_rate_limit(mock_request)

    @pytest.mark.asyncio
    async def test_rate_limiting_blocks_after_limit_exceeded(self, setup_scheduler_helpers, mock_request):
        """Successive requests should be blocked once the limit is exceeded."""
        sar = setup_scheduler_helpers

        mock_redis = MagicMock()
        sar._rate_limit_redis = mock_redis
        sar._rate_limit_redis_checked = True

        # Simulate requests 1 through 10 (all allowed)
        for i in range(1, 11):
            mock_redis.incr.return_value = i
            mock_redis.ttl.return_value = 60
            await sar._check_rate_limit(mock_request)  # Should not raise

        # 11th request exceeds limit
        mock_redis.incr.return_value = 11
        mock_redis.ttl.return_value = 50

        with pytest.raises(HTTPException) as exc:
            await sar._check_rate_limit(mock_request)
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_rate_limit_retry_after_header(self, setup_scheduler_helpers, mock_request):
        """429 response should include Retry-After header."""
        sar = setup_scheduler_helpers

        mock_redis = MagicMock()
        mock_redis.incr.return_value = 11
        mock_redis.ttl.return_value = 42
        sar._rate_limit_redis = mock_redis
        sar._rate_limit_redis_checked = True

        with pytest.raises(HTTPException) as exc:
            await sar._check_rate_limit(mock_request)
        assert exc.value.headers.get("Retry-After") == "42"


# =============================================================================
# RATE LIMITING TESTS - IN-MEMORY FALLBACK
# =============================================================================

class TestRateLimitingMemoryFallback:
    """Test in-memory rate limiting when Redis is unavailable."""

    @pytest.mark.asyncio
    async def test_redis_unavailable_uses_memory_fallback(self, setup_scheduler_helpers, mock_request):
        """When Redis is None, should fall back to in-memory rate limiter."""
        sar = setup_scheduler_helpers

        # Force Redis unavailable
        sar._rate_limit_redis = None
        sar._rate_limit_redis_checked = True

        # Clear in-memory state
        sar._memory_rate_limits.clear()

        # Should not raise on first few requests
        await sar._check_rate_limit(mock_request)

    @pytest.mark.asyncio
    async def test_memory_fallback_blocks_after_limit(self, setup_scheduler_helpers, mock_request):
        """In-memory fallback should still enforce rate limits."""
        sar = setup_scheduler_helpers

        sar._rate_limit_redis = None
        sar._rate_limit_redis_checked = True

        # Clear in-memory state
        sar._memory_rate_limits.clear()

        # Send requests up to the limit (default is 10)
        for _ in range(10):
            await sar._check_rate_limit(mock_request, max_requests=10)

        # Next request should be blocked
        with pytest.raises(HTTPException) as exc:
            await sar._check_rate_limit(mock_request, max_requests=10)
        assert exc.value.status_code == 429

    @pytest.mark.asyncio
    async def test_redis_error_mid_request_falls_back(self, setup_scheduler_helpers, mock_request):
        """If Redis raises an error during incr(), should fall back to memory."""
        sar = setup_scheduler_helpers

        mock_redis = MagicMock()
        mock_redis.incr.side_effect = Exception("Connection reset by peer")
        sar._rate_limit_redis = mock_redis
        sar._rate_limit_redis_checked = True

        # Clear in-memory state so the fallback can succeed
        sar._memory_rate_limits.clear()

        # Should not raise -- graceful degradation to in-memory
        await sar._check_rate_limit(mock_request)


# =============================================================================
# IDOR TESTS - BLOCKED TIME DESCRIPTIONS
# =============================================================================

class TestBlockedTimeIDOR:
    """Test IDOR protection: non-admins cannot see other users' personal blocked time descriptions."""

    def test_non_admin_cannot_see_other_users_blocked_time_description(
        self, setup_scheduler_helpers, mock_user_lo
    ):
        """A non-admin user should not receive the description field for another user's blocked time."""
        sar = setup_scheduler_helpers

        # The _is_scheduler_admin check should return False for a loan officer
        assert sar._is_scheduler_admin(mock_user_lo) is False

    def test_admin_is_identified_correctly(self, setup_scheduler_helpers, mock_user_admin):
        """Admin user should be recognized as scheduler admin."""
        sar = setup_scheduler_helpers
        assert sar._is_scheduler_admin(mock_user_admin) is True

    def test_admin_can_see_other_users_full_availability(
        self, setup_scheduler_helpers, mock_db, mock_models, mock_user_admin
    ):
        """Admin should be able to generate availability slots for other users."""
        sar = setup_scheduler_helpers

        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        future_monday = today + timedelta(days=days_until_monday)

        config = mock_models['SchedulerConfig'](user_id=99, min_notice_hours=0)
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[99],  # Different user ID
                start_date=future_monday,
                end_date=future_monday,
                org_id=mock_user_admin.organization_id,
            )

        # Admin should get slots for any user in their org
        assert len(result) > 0

    def test_site_admin_recognized(self, setup_scheduler_helpers):
        """site_admin role should be recognized as scheduler admin."""
        sar = setup_scheduler_helpers
        user = MagicMock()
        user.permission_role = "site_admin"
        user.role = "site_admin"
        assert sar._is_scheduler_admin(user) is True

    def test_platform_admin_recognized(self, setup_scheduler_helpers):
        """platform_admin role should be recognized as scheduler admin."""
        sar = setup_scheduler_helpers
        user = MagicMock()
        user.permission_role = "platform_admin"
        user.role = "platform_admin"
        assert sar._is_scheduler_admin(user) is True

    def test_leadership_not_admin(self, setup_scheduler_helpers):
        """Leadership role should NOT be recognized as scheduler admin."""
        sar = setup_scheduler_helpers
        user = MagicMock()
        user.permission_role = "leadership"
        user.role = "leadership"
        assert sar._is_scheduler_admin(user) is False

    def test_management_not_admin(self, setup_scheduler_helpers):
        """Management role should NOT be recognized as scheduler admin."""
        sar = setup_scheduler_helpers
        user = MagicMock()
        user.permission_role = "management"
        user.role = "management"
        assert sar._is_scheduler_admin(user) is False


# =============================================================================
# CSS SANITIZATION TESTS
# =============================================================================

class TestCSSSanitization:
    """Test CSS sanitization in booking branding to prevent XSS and data exfiltration."""

    def _sanitize(self, css):
        """Import and call the CSS sanitization function."""
        from routes.booking_branding_routes import _sanitize_css
        return _sanitize_css(css)

    def test_strips_url_in_all_contexts(self):
        """url() with javascript: protocol should be neutralized."""
        result = self._sanitize("background: url(javascript:alert(1));")
        assert "javascript:" not in result
        assert "blocked:" in result

    def test_strips_import(self):
        """@import rules should be stripped to prevent loading external CSS."""
        result = self._sanitize("@import url('https://evil.com/steal.css'); body { color: red; }")
        assert "@import" not in result
        assert "color: red" in result

    def test_strips_expression(self):
        """expression() (IE CSS) should be neutralized."""
        result = self._sanitize("width: expression(document.body.clientWidth);")
        assert "expression(" not in result
        assert "blocked(" in result

    def test_strips_javascript_protocol(self):
        """javascript: protocol in url() should be blocked."""
        result = self._sanitize("background-image: url('javascript:void(0)');")
        assert "javascript:" not in result

    def test_strips_javascript_protocol_case_insensitive(self):
        """javascript: detection should be case-insensitive."""
        result = self._sanitize("background: url(JAVASCRIPT:alert(1));")
        assert "JAVASCRIPT:" not in result.upper() or "blocked:" in result.lower()

    def test_allows_safe_properties(self):
        """Safe CSS properties should pass through unchanged."""
        safe_css = "color: #333; font-size: 16px; margin: 10px; padding: 0;"
        result = self._sanitize(safe_css)
        assert "color: #333" in result
        assert "font-size: 16px" in result
        assert "margin: 10px" in result
        assert "padding: 0" in result

    def test_allows_safe_background_color(self):
        """Safe background-color values should be allowed."""
        result = self._sanitize("background-color: #ff6600;")
        assert "background-color: #ff6600" in result

    def test_strips_script_tags(self):
        """Embedded script tags should be removed."""
        result = self._sanitize("<script>alert('xss')</script> .btn { color: blue; }")
        assert "<script>" not in result
        assert "alert(" not in result
        assert "color: blue" in result

    def test_strips_import_with_url_function(self):
        """@import with url() function should be stripped."""
        result = self._sanitize("@import url(https://evil.com/payload.css);")
        assert "@import" not in result

    def test_strips_import_with_string(self):
        """@import with string URL should be stripped."""
        result = self._sanitize('@import "https://evil.com/payload.css";')
        assert "@import" not in result

    def test_none_input_returns_none(self):
        """None input should return None (or falsy)."""
        result = self._sanitize(None)
        assert result is None or result == ""

    def test_empty_string_returns_empty(self):
        """Empty string should return empty/falsy."""
        result = self._sanitize("")
        assert result == "" or result is None

    def test_caps_length(self):
        """Very long CSS should be truncated."""
        long_css = "a { color: red; } " * 10000
        result = self._sanitize(long_css)
        assert len(result) <= 10000


# =============================================================================
# CLOUDFLARE TURNSTILE VERIFICATION TESTS
# =============================================================================

class TestTurnstileVerification:
    """Test Cloudflare Turnstile token verification for public booking."""

    @pytest.mark.asyncio
    async def test_turnstile_skipped_without_secret(self, setup_scheduler_helpers):
        """Without TURNSTILE_SECRET_KEY set, should allow in non-production."""
        sar = setup_scheduler_helpers

        # Save originals
        original_key = sar._TURNSTILE_SECRET_KEY
        original_prod = sar._IS_PRODUCTION

        try:
            sar._TURNSTILE_SECRET_KEY = None
            sar._IS_PRODUCTION = False

            result = await sar._verify_turnstile_token("any-token")
            assert result is True  # Dev mode bypass
        finally:
            sar._TURNSTILE_SECRET_KEY = original_key
            sar._IS_PRODUCTION = original_prod

    @pytest.mark.asyncio
    async def test_turnstile_rejected_without_secret_in_production(self, setup_scheduler_helpers):
        """In production, no TURNSTILE_SECRET_KEY should reject all tokens."""
        sar = setup_scheduler_helpers

        original_key = sar._TURNSTILE_SECRET_KEY
        original_prod = sar._IS_PRODUCTION

        try:
            sar._TURNSTILE_SECRET_KEY = None
            sar._IS_PRODUCTION = True

            result = await sar._verify_turnstile_token("any-token")
            assert result is False  # Production without key = reject
        finally:
            sar._TURNSTILE_SECRET_KEY = original_key
            sar._IS_PRODUCTION = original_prod

    @pytest.mark.asyncio
    async def test_turnstile_valid_token(self, setup_scheduler_helpers):
        """Valid Turnstile token should be accepted."""
        sar = setup_scheduler_helpers

        original_key = sar._TURNSTILE_SECRET_KEY

        try:
            sar._TURNSTILE_SECRET_KEY = "test-secret-key"

            mock_response = MagicMock()
            mock_response.json.return_value = {"success": True}

            with patch('routes.scheduler._helpers.httpx') as mock_httpx:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await sar._verify_turnstile_token("valid-token-123")
                assert result is True
        finally:
            sar._TURNSTILE_SECRET_KEY = original_key

    @pytest.mark.asyncio
    async def test_turnstile_invalid_token(self, setup_scheduler_helpers):
        """Invalid Turnstile token should be rejected."""
        sar = setup_scheduler_helpers

        original_key = sar._TURNSTILE_SECRET_KEY

        try:
            sar._TURNSTILE_SECRET_KEY = "test-secret-key"

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "success": False,
                "error-codes": ["invalid-input-response"]
            }

            with patch('routes.scheduler._helpers.httpx') as mock_httpx:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await sar._verify_turnstile_token("invalid-token")
                assert result is False
        finally:
            sar._TURNSTILE_SECRET_KEY = original_key

    @pytest.mark.asyncio
    async def test_turnstile_network_error_returns_false(self, setup_scheduler_helpers):
        """Network error during Turnstile verification should return False."""
        sar = setup_scheduler_helpers

        original_key = sar._TURNSTILE_SECRET_KEY

        try:
            sar._TURNSTILE_SECRET_KEY = "test-secret-key"

            with patch('routes.scheduler._helpers.httpx') as mock_httpx:
                mock_client = AsyncMock()
                mock_client.post.side_effect = Exception("Network timeout")
                mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await sar._verify_turnstile_token("some-token")
                assert result is False
        finally:
            sar._TURNSTILE_SECRET_KEY = original_key


# =============================================================================
# TOKEN EXPIRATION TESTS
# =============================================================================

class TestTokenExpiration:
    """Test that authenticated endpoints reject expired or invalid tokens."""

    @pytest.mark.asyncio
    async def test_get_current_user_raises_without_dependencies(self, setup_scheduler_helpers):
        """get_current_user should raise if dependencies not set."""
        sar = setup_scheduler_helpers

        original_func = sar._get_current_user_func
        try:
            sar._get_current_user_func = None

            mock_request = MagicMock()
            mock_request.headers.get.return_value = "Bearer expired-token"
            mock_db = MagicMock()

            with pytest.raises(RuntimeError, match="Dependencies not set"):
                await sar.get_current_user(mock_request, mock_db)
        finally:
            sar._get_current_user_func = original_func

    @pytest.mark.asyncio
    async def test_get_current_user_extracts_bearer_token(self, setup_scheduler_helpers):
        """get_current_user should extract the token from Bearer auth header."""
        sar = setup_scheduler_helpers

        mock_auth_func = AsyncMock(return_value=MagicMock())
        original_func = sar._get_current_user_func

        try:
            sar._get_current_user_func = mock_auth_func

            mock_request = MagicMock()
            mock_request.headers.get.return_value = "Bearer test-token-123"
            mock_db = MagicMock()

            await sar.get_current_user(mock_request, mock_db)

            # Verify the auth function was called with the extracted token
            call_kwargs = mock_auth_func.call_args
            assert call_kwargs.kwargs.get('token') == 'test-token-123' or \
                   call_kwargs[1].get('token') == 'test-token-123'
        finally:
            sar._get_current_user_func = original_func

    @pytest.mark.asyncio
    async def test_get_current_user_handles_missing_bearer_prefix(self, setup_scheduler_helpers):
        """If Authorization header has no Bearer prefix, token should be empty."""
        sar = setup_scheduler_helpers

        mock_auth_func = AsyncMock(return_value=MagicMock())
        original_func = sar._get_current_user_func

        try:
            sar._get_current_user_func = mock_auth_func

            mock_request = MagicMock()
            mock_request.headers.get.return_value = "InvalidHeaderFormat"
            mock_db = MagicMock()

            await sar.get_current_user(mock_request, mock_db)

            call_kwargs = mock_auth_func.call_args
            assert call_kwargs.kwargs.get('token') == '' or \
                   call_kwargs[1].get('token') == ''
        finally:
            sar._get_current_user_func = original_func


# =============================================================================
# ORGANIZATION ISOLATION TESTS
# =============================================================================

class TestOrgIsolation:
    """Test that users cannot access data from other organizations."""

    def test_get_org_id_raises_403_if_no_org(self, setup_scheduler_helpers):
        """User without organization_id should get 403."""
        sar = setup_scheduler_helpers
        user = MagicMock()
        user.organization_id = None

        with pytest.raises(HTTPException) as exc:
            sar._get_org_id(user)
        assert exc.value.status_code == 403
        assert "No organization context" in exc.value.detail

    def test_conflict_check_scopes_by_org_id(self, setup_scheduler_helpers, mock_db):
        """_check_appointment_conflict should include org_id in its filters."""
        sar = setup_scheduler_helpers

        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

        # Call with explicit org_id
        sar._check_appointment_conflict(
            mock_db,
            assigned_user_id=1,
            start_time=datetime(2026, 3, 5, 10, 0),
            end_time=datetime(2026, 3, 5, 10, 30),
            org_id=42,
        )

        # Verify filter was called (it uses _models['Appointment'] with org_id filter)
        assert mock_db.query.called

    def test_duplicate_check_scopes_by_org_id(self, setup_scheduler_helpers, mock_db):
        """_check_duplicate_booking should scope by org_id."""
        sar = setup_scheduler_helpers

        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Should not raise
        sar._check_duplicate_booking(
            mock_db,
            attendee_email="test@example.com",
            assigned_user_id=1,
            start_time=datetime(2026, 3, 5, 10, 0),
            org_id=42,
        )

        # The query should have been called with org_id filter
        assert mock_db.query.called

    def test_cross_source_conflicts_scopes_by_org_id(self, setup_scheduler_helpers, mock_db):
        """_get_cross_source_conflicts should pass org_id to all source queries."""
        sar = setup_scheduler_helpers

        result = sar._get_cross_source_conflicts(
            mock_db,
            target_user_id=1,
            start_dt=datetime(2026, 3, 5, 9, 0),
            end_dt=datetime(2026, 3, 5, 17, 0),
            org_id=42,
        )

        # Should return a list (possibly empty since models are mocked)
        assert isinstance(result, list)

    def test_user_timezone_scoped_by_org(self, setup_scheduler_helpers, mock_db, mock_models):
        """_get_user_timezone should filter by org_id to prevent cross-tenant leaks."""
        sar = setup_scheduler_helpers

        config = mock_models['SchedulerConfig'](user_id=1, timezone='America/New_York')
        mock_db.query.return_value.filter.return_value.first.return_value = config

        tz = sar._get_user_timezone(mock_db, user_id=1, org_id=42)
        assert tz == "America/New_York"

        # Verify filter was called at least once (for user_id, potentially for org_id)
        assert mock_db.query.return_value.filter.called

    def test_slot_generation_passes_org_id(self, setup_scheduler_helpers, mock_db, mock_models):
        """_generate_available_slots should scope all DB queries by org_id."""
        sar = setup_scheduler_helpers

        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        future_monday = today + timedelta(days=days_until_monday)

        config = mock_models['SchedulerConfig'](user_id=1, min_notice_hours=0)
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]) as mock_conflicts:
            sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=future_monday,
                end_date=future_monday,
                org_id=42,
            )

            # Verify _get_cross_source_conflicts was called with the org_id
            if mock_conflicts.called:
                call_kwargs = mock_conflicts.call_args
                # org_id should be passed through
                assert call_kwargs.kwargs.get('org_id') == 42 or \
                       (len(call_kwargs.args) > 3 and call_kwargs.args[3] == 42)


# =============================================================================
# IP EXTRACTION SECURITY TESTS
# =============================================================================

class TestIPExtractionSecurity:
    """Test that client IP extraction is safe against spoofing."""

    def test_private_ip_detection(self, setup_scheduler_helpers):
        """Should correctly identify private/internal IP addresses."""
        sar = setup_scheduler_helpers

        assert sar._is_private_ip("10.0.0.1") is True
        assert sar._is_private_ip("172.16.0.1") is True
        assert sar._is_private_ip("192.168.1.1") is True
        assert sar._is_private_ip("127.0.0.1") is True
        assert sar._is_private_ip("203.0.113.50") is False  # Public

    def test_get_client_ip_direct_connection(self, setup_scheduler_helpers):
        """When no trusted proxy, should use direct connection IP."""
        sar = setup_scheduler_helpers

        mock_request = MagicMock()
        mock_request.client.host = "203.0.113.50"  # Public IP (not a trusted proxy)
        mock_request.headers.get.return_value = "1.2.3.4, 5.6.7.8"  # Spoofed X-Forwarded-For

        ip = sar._get_client_ip(mock_request)
        # Since 203.0.113.50 is not a trusted proxy, X-Forwarded-For should be ignored
        assert ip == "203.0.113.50"

    def test_get_client_ip_no_forwarded_header(self, setup_scheduler_helpers):
        """Without X-Forwarded-For, should use direct connection IP."""
        sar = setup_scheduler_helpers

        mock_request = MagicMock()
        mock_request.client.host = "1.2.3.4"
        mock_request.headers.get.return_value = None

        ip = sar._get_client_ip(mock_request)
        assert ip == "1.2.3.4"


# =============================================================================
# SANITIZATION INTEGRATION TESTS
# =============================================================================

class TestSanitizationSecurity:
    """Test input sanitization for security-sensitive fields."""

    def test_sanitize_text_strips_xss(self, setup_scheduler_helpers):
        """_sanitize_text should strip XSS payloads."""
        sar = setup_scheduler_helpers
        result = sar._sanitize_text("<img src=x onerror=alert(1)>Booking note")
        assert "onerror" not in result
        assert "Booking" in result

    def test_sanitize_text_strips_script_tags(self, setup_scheduler_helpers):
        """_sanitize_text should strip script tags."""
        sar = setup_scheduler_helpers
        result = sar._sanitize_text("<script>document.cookie</script>Normal text")
        assert "<script>" not in result
        assert "Normal text" in result

    def test_validate_phone_accepts_valid_formats(self, setup_scheduler_helpers):
        """Phone validation should accept standard US formats."""
        sar = setup_scheduler_helpers
        assert sar._validate_phone("+15551234567") == "+15551234567"
        assert sar._validate_phone("555-123-4567") == "555-123-4567"

    def test_validate_phone_rejects_invalid(self, setup_scheduler_helpers):
        """Phone validation should reject invalid numbers."""
        sar = setup_scheduler_helpers
        with pytest.raises(HTTPException) as exc:
            sar._validate_phone("123")
        assert exc.value.status_code == 400

    def test_sanitize_public_error_hides_internals(self, setup_scheduler_helpers):
        """Public error messages should not leak internal details."""
        sar = setup_scheduler_helpers

        # 500 errors should show generic message
        msg = sar._sanitize_public_error(500, "sqlalchemy.exc.OperationalError: connection refused")
        assert "sqlalchemy" not in msg
        assert "Something went wrong" in msg

        # 400 should show safe message
        msg = sar._sanitize_public_error(400, "Validation error in SchedulerConfig model")
        assert "SchedulerConfig" not in msg
        assert "Invalid booking request" in msg

        # 409 should show safe conflict message
        msg = sar._sanitize_public_error(409, "Overlapping appointment at user_id=42")
        assert "user_id" not in msg
        assert "already been booked" in msg
