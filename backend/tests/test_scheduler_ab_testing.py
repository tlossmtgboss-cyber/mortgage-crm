"""
Tests for scheduler A/B testing routes.

Covers:
  Authenticated (admin):
    - POST   /ab-tests                              Create A/B test
    - GET    /ab-tests                              List tests for org
    - GET    /ab-tests/{test_id}/results            Get results
    - PUT    /ab-tests/{test_id}/status             Activate/complete test

  Public (no auth):
    - GET    /public/ab-tests/assign/{booking_link}  Assign visitor to variant
    - POST   /public/ab-tests/record                 Record impression/conversion

Focus: admin-only enforcement, status transitions, conflict on same
element type, input sanitization, and public endpoint access.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock
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


# Mock enum classes
class FakeABTestStatus:
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"

    @classmethod
    def __iter__(cls):
        return iter([
            type('', (), {'value': 'draft'})(),
            type('', (), {'value': 'active'})(),
            type('', (), {'value': 'completed'})(),
        ])


class FakeABTestElementType:
    @classmethod
    def __iter__(cls):
        return iter([
            type('', (), {'value': 'headline'})(),
            type('', (), {'value': 'cta_button'})(),
            type('', (), {'value': 'layout'})(),
            type('', (), {'value': 'color_scheme'})(),
        ])


class MockABTest:
    """Mock ABTest ORM object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.name = kwargs.get("name", "Headline Test")
        self.description = kwargs.get("description", "Testing headline variants")
        self.status = kwargs.get("status", "draft")
        self.element_type = kwargs.get("element_type", "headline")
        self.variant_a = kwargs.get("variant_a", {"text": "Get Your Rate"})
        self.variant_b = kwargs.get("variant_b", {"text": "Check Rates Now"})
        self.traffic_split = kwargs.get("traffic_split", 50)
        self.start_date = kwargs.get("start_date", None)
        self.end_date = kwargs.get("end_date", None)
        self.created_at = kwargs.get("created_at", datetime(2026, 3, 1, tzinfo=timezone.utc))
        self.updated_at = kwargs.get("updated_at", datetime(2026, 3, 1, tzinfo=timezone.utc))


class MockBookingLink:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)


class MockABTestService:
    """Mock ABTestService."""
    def __init__(self, db):
        pass

    def assign_variant(self, test_id, visitor_id):
        return "A"

    def record_impression(self, test_id, variant, visitor_id):
        pass

    def record_conversion(self, test_id, variant, visitor_id):
        pass

    def calculate_results(self, test_id):
        return {
            "variant_a": {"impressions": 100, "conversions": 10, "rate": 0.10},
            "variant_b": {"impressions": 100, "conversions": 15, "rate": 0.15},
            "significance": 0.85,
            "winner": "B",
        }


# ---------------------------------------------------------------------------
# Tests: Create A/B Test
# ---------------------------------------------------------------------------

class TestCreateABTest:
    """Tests for POST /ab-tests."""

    @pytest.mark.asyncio
    async def test_create_requires_admin(self):
        """Non-admin users should get 403."""
        from routes.scheduler.ab_testing import create_ab_test, CreateABTestRequest

        non_admin = MockUser(role="loan_officer")
        body = CreateABTestRequest(
            name="Test",
            element_type="headline",
            variant_a={"text": "A"},
            variant_b={"text": "B"},
        )

        with patch("routes.scheduler.ab_testing.get_current_user",
                    new_callable=AsyncMock, return_value=non_admin), \
             patch("routes.scheduler.ab_testing.require_feature_tier", lambda x: lambda f: f):
            with pytest.raises(HTTPException) as exc_info:
                await create_ab_test(body, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_create_invalid_element_type(self):
        """Invalid element_type should return 400."""
        from routes.scheduler.ab_testing import create_ab_test, CreateABTestRequest

        admin = MockUser(role="admin")
        body = CreateABTestRequest(
            name="Test",
            element_type="invalid_type",
            variant_a={"text": "A"},
            variant_b={"text": "B"},
        )

        with patch("routes.scheduler.ab_testing.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.ab_testing.ABTestElementType", FakeABTestElementType), \
             patch("routes.scheduler.ab_testing.require_feature_tier", lambda x: lambda f: f):
            with pytest.raises(HTTPException) as exc_info:
                await create_ab_test(body, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_conflict_same_element_type(self):
        """Active test on same element type should return 409."""
        from routes.scheduler.ab_testing import create_ab_test, CreateABTestRequest

        admin = MockUser(role="admin")
        body = CreateABTestRequest(
            name="Another Headline Test",
            element_type="headline",
            variant_a={"text": "A"},
            variant_b={"text": "B"},
        )

        existing = MockABTest(status="active")

        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=existing)  # Existing active test
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.ab_testing.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.ab_testing.ABTestElementType", FakeABTestElementType), \
             patch("routes.scheduler.ab_testing.ABTestStatus", FakeABTestStatus), \
             patch("routes.scheduler.ab_testing.require_feature_tier", lambda x: lambda f: f):
            with pytest.raises(HTTPException) as exc_info:
                await create_ab_test(body, MagicMock(), db)
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_happy_path(self):
        """Admin can create an A/B test."""
        from routes.scheduler.ab_testing import create_ab_test, CreateABTestRequest

        admin = MockUser(role="admin")
        body = CreateABTestRequest(
            name="CTA Button Test",
            element_type="cta_button",
            variant_a={"text": "Book Now"},
            variant_b={"text": "Schedule Call"},
        )

        db = MagicMock()
        db.commit = MagicMock()
        db.flush = MagicMock()

        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=None)  # No existing active
        db.query = MagicMock(return_value=query_mock)

        # db.add should capture the created test
        created_test = None
        def capture_add(obj):
            nonlocal created_test
            created_test = obj
            obj.id = 42
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)

        db.add = capture_add

        with patch("routes.scheduler.ab_testing.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.ab_testing.ABTestElementType", FakeABTestElementType), \
             patch("routes.scheduler.ab_testing.ABTestStatus", FakeABTestStatus), \
             patch("routes.scheduler.ab_testing.ABTest") as MockABTestCls, \
             patch("routes.scheduler.ab_testing._audit_log"), \
             patch("routes.scheduler.ab_testing.require_feature_tier", lambda x: lambda f: f):

            # Make ABTest constructor return a mock with all expected attributes
            mock_test_instance = MockABTest(id=42, name="CTA Button Test",
                                             element_type="cta_button",
                                             status="draft")
            MockABTestCls.return_value = mock_test_instance

            result = await create_ab_test(body, MagicMock(), db)

        assert result["success"] is True
        assert result["test"]["name"] == "CTA Button Test"


# ---------------------------------------------------------------------------
# Tests: List A/B Tests
# ---------------------------------------------------------------------------

class TestListABTests:
    """Tests for GET /ab-tests."""

    @pytest.mark.asyncio
    async def test_list_requires_auth(self):
        """Unauthenticated requests should fail."""
        from routes.scheduler.ab_testing import list_ab_tests

        with patch("routes.scheduler.ab_testing.get_current_user",
                    new_callable=AsyncMock,
                    side_effect=HTTPException(status_code=401, detail="Not authenticated")), \
             patch("routes.scheduler.ab_testing.require_feature_tier", lambda x: lambda f: f):
            with pytest.raises(HTTPException) as exc_info:
                await list_ab_tests(MagicMock(), None, 50, 0, MagicMock())
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_list_invalid_status_filter(self):
        """Invalid status filter should return 400."""
        from routes.scheduler.ab_testing import list_ab_tests

        user = MockUser()
        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.ab_testing.get_current_user",
                    new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.ab_testing.ABTestStatus", FakeABTestStatus), \
             patch("routes.scheduler.ab_testing.ABTest", MagicMock()), \
             patch("routes.scheduler.ab_testing.require_feature_tier", lambda x: lambda f: f):
            with pytest.raises(HTTPException) as exc_info:
                await list_ab_tests(MagicMock(), "invalid_status", 50, 0, db)
            assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Tests: Update Status
# ---------------------------------------------------------------------------

class TestUpdateABTestStatus:
    """Tests for PUT /ab-tests/{test_id}/status."""

    @pytest.mark.asyncio
    async def test_update_status_not_found(self):
        """Non-existent test returns 404."""
        from routes.scheduler.ab_testing import update_ab_test_status, UpdateStatusRequest

        admin = MockUser(role="admin")
        body = UpdateStatusRequest(status="active")

        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=None)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.ab_testing.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.ab_testing.ABTest", MagicMock()), \
             patch("routes.scheduler.ab_testing.require_feature_tier", lambda x: lambda f: f):
            with pytest.raises(HTTPException) as exc_info:
                await update_ab_test_status(999, body, MagicMock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_status_transition(self):
        """Invalid status transition should return 400."""
        from routes.scheduler.ab_testing import update_ab_test_status, UpdateStatusRequest

        admin = MockUser(role="admin")
        body = UpdateStatusRequest(status="active")

        # Test is already completed -- cannot go back to active
        completed_test = MockABTest(status="completed")

        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=completed_test)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.ab_testing.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.ab_testing.ABTest", MagicMock()), \
             patch("routes.scheduler.ab_testing.ABTestStatus", FakeABTestStatus), \
             patch("routes.scheduler.ab_testing.require_feature_tier", lambda x: lambda f: f):
            with pytest.raises(HTTPException) as exc_info:
                await update_ab_test_status(1, body, MagicMock(), db)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_requires_admin(self):
        """Non-admin users should get 403."""
        from routes.scheduler.ab_testing import update_ab_test_status, UpdateStatusRequest

        non_admin = MockUser(role="loan_officer")
        body = UpdateStatusRequest(status="active")

        with patch("routes.scheduler.ab_testing.get_current_user",
                    new_callable=AsyncMock, return_value=non_admin), \
             patch("routes.scheduler.ab_testing.require_feature_tier", lambda x: lambda f: f):
            with pytest.raises(HTTPException) as exc_info:
                await update_ab_test_status(1, body, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Tests: Public Endpoints
# ---------------------------------------------------------------------------

class TestPublicAssignVariant:
    """Tests for GET /public/ab-tests/assign/{booking_link_id}."""

    @pytest.mark.asyncio
    async def test_assign_booking_link_not_found(self):
        """Non-existent booking link returns 404."""
        from routes.scheduler.ab_testing import public_assign_variant

        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=None)
        db.query = MagicMock(return_value=query_mock)

        mock_models = {"BookingLink": MagicMock()}

        with patch("routes.scheduler.ab_testing.get_models", return_value=mock_models):
            with pytest.raises(HTTPException) as exc_info:
                await public_assign_variant(999, "visitor123", MagicMock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_assign_no_active_tests(self):
        """When no active tests exist, return empty assignments."""
        from routes.scheduler.ab_testing import public_assign_variant

        link = MockBookingLink()

        db = MagicMock()
        call_count = [0]
        def side_effect_query(model):
            call_count[0] += 1
            q = MagicMock()
            q.filter = MagicMock(return_value=q)
            if call_count[0] == 1:
                q.first = MagicMock(return_value=link)
            else:
                q.all = MagicMock(return_value=[])
                q.first = MagicMock(return_value=None)
            return q

        db.query = MagicMock(side_effect=side_effect_query)

        mock_models = {"BookingLink": MagicMock()}

        with patch("routes.scheduler.ab_testing.get_models", return_value=mock_models), \
             patch("routes.scheduler.ab_testing.ABTest", MagicMock()), \
             patch("routes.scheduler.ab_testing.ABTestStatus", FakeABTestStatus):
            result = await public_assign_variant(1, "visitor123", MagicMock(), db)

        assert result["assignments"] == []


class TestPublicRecordEvent:
    """Tests for POST /public/ab-tests/record."""

    @pytest.mark.asyncio
    async def test_record_test_not_found(self):
        """Non-existent or inactive test returns 404."""
        from routes.scheduler.ab_testing import public_record_event, RecordEventRequest

        body = RecordEventRequest(
            test_id=999,
            variant="A",
            visitor_id="visitor123",
            event_type="impression",
        )

        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter = MagicMock(return_value=query_mock)
        query_mock.first = MagicMock(return_value=None)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.ab_testing.ABTest", MagicMock()), \
             patch("routes.scheduler.ab_testing.ABTestStatus", FakeABTestStatus), \
             patch("routes.scheduler.ab_testing.ABTestService", MockABTestService):
            with pytest.raises(HTTPException) as exc_info:
                await public_record_event(body, MagicMock(), db)
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Input Sanitization
# ---------------------------------------------------------------------------

class TestSanitization:
    """Tests for _sanitize helper."""

    def test_sanitize_strips_html(self):
        """HTML tags should be stripped."""
        from routes.scheduler.ab_testing import _sanitize

        result = _sanitize("<script>alert('xss')</script>Hello")
        assert "<script>" not in result
        assert "Hello" in result

    def test_sanitize_none_returns_none(self):
        """None input should return None."""
        from routes.scheduler.ab_testing import _sanitize

        assert _sanitize(None) is None

    def test_parse_optional_datetime_valid(self):
        """Valid ISO datetime should parse."""
        from routes.scheduler.ab_testing import _parse_optional_datetime

        result = _parse_optional_datetime("2026-04-01T10:00:00Z")
        assert result is not None
        assert result.year == 2026

    def test_parse_optional_datetime_invalid(self):
        """Invalid datetime should raise 400."""
        from routes.scheduler.ab_testing import _parse_optional_datetime

        with pytest.raises(HTTPException) as exc_info:
            _parse_optional_datetime("not-a-date")
        assert exc_info.value.status_code == 400

    def test_parse_optional_datetime_none(self):
        """None/empty should return None."""
        from routes.scheduler.ab_testing import _parse_optional_datetime

        assert _parse_optional_datetime(None) is None
        assert _parse_optional_datetime("") is None
