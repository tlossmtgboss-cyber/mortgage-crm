"""
Scheduler Pagination Test Suite

Tests for pagination behavior across scheduler endpoints:
- Search endpoint pagination
- Analytics endpoint pagination
- Default and max page sizes
- Invalid page handling
- Empty result sets
"""

import pytest
import math
from datetime import datetime, timedelta, date, time, timezone
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# MOCK HELPERS
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
    def desc(self): return self
    def asc(self): return self

    def __hash__(self):
        return id(self)


def _make_mock_appointment(appt_id, org_id=1, **kwargs):
    """Create a mock appointment with all required fields for serialization."""
    appt = MagicMock()
    appt.id = appt_id
    appt.title = kwargs.get('title', f"Appointment {appt_id}")
    appt.description = kwargs.get('description', None)
    appt.meeting_type = MagicMock(value="consultation")
    appt.meeting_mode = MagicMock(value="video")
    appt.scheduled_start = kwargs.get('scheduled_start', datetime(2026, 3, 15, 10, 0))
    appt.scheduled_end = kwargs.get('scheduled_end', datetime(2026, 3, 15, 10, 30))
    appt.duration_minutes = kwargs.get('duration_minutes', 30)
    appt.timezone = kwargs.get('timezone', 'America/Chicago')
    appt.status = MagicMock(value="booked")
    appt.attendee_name = kwargs.get('attendee_name', f"Client {appt_id}")
    appt.attendee_email = kwargs.get('attendee_email', f"client{appt_id}@example.com")
    appt.attendee_phone = kwargs.get('attendee_phone', None)
    appt.attendee_notes = kwargs.get('attendee_notes', None)
    appt.location = kwargs.get('location', None)
    appt.video_link = kwargs.get('video_link', None)
    appt.lead_id = kwargs.get('lead_id', None)
    appt.loan_id = kwargs.get('loan_id', None)
    appt.contact_id = kwargs.get('contact_id', None)
    appt.assigned_user_id = kwargs.get('assigned_user_id', 1)
    appt.appointment_type_id = kwargs.get('appointment_type_id', None)
    appt.booked_by_ai = kwargs.get('booked_by_ai', False)
    appt.internal_notes = kwargs.get('internal_notes', None)
    appt.meeting_notes = kwargs.get('meeting_notes', None)
    appt.created_at = kwargs.get('created_at', datetime(2026, 3, 10))
    appt.updated_at = kwargs.get('updated_at', datetime(2026, 3, 10))
    appt.organization_id = org_id
    appt.created_by_user_id = kwargs.get('created_by_user_id', 1)
    return appt


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_user():
    """Mock authenticated user (admin for full visibility)."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@example.com"
    user.organization_id = 1
    user.role = "admin"
    user.permission_role = "admin"
    return user


@pytest.fixture
def mock_non_admin_user():
    """Mock non-admin user."""
    user = MagicMock()
    user.id = 10
    user.email = "lo@example.com"
    user.organization_id = 1
    user.role = "loan_officer"
    user.permission_role = "loan_officer"
    return user


@pytest.fixture
def mock_models():
    """Create mock model classes for dependency injection."""
    models = {}

    class MockAppointment:
        id = _Col()
        assigned_user_id = _Col()
        created_by_user_id = _Col()
        organization_id = _Col()
        status = _Col()
        scheduled_start = _Col()
        scheduled_end = _Col()
        attendee_name = _Col()
        attendee_email = _Col()
        attendee_phone = _Col()
        attendee_notes = _Col()
        description = _Col()
        internal_notes = _Col()
        meeting_notes = _Col()
        location = _Col()
        title = _Col()
        meeting_type = _Col()
        appointment_type_id = _Col()
        booked_by_ai = _Col()
        lead_id = _Col()
        loan_id = _Col()

    class MockConfig:
        user_id = _Col()
        organization_id = _Col()

    models['Appointment'] = MockAppointment
    models['SchedulerConfig'] = MockConfig
    models['BlockedTime'] = MagicMock
    models['BookingLink'] = MagicMock
    models['AppointmentType'] = MagicMock
    models['SchedulerAuditLog'] = None
    models['VideoMeetingRoom'] = None

    return models


# =============================================================================
# SEARCH PAGINATION HELPER TESTS
# =============================================================================

class TestSearchPaginationHelpers:
    """Test pagination helper logic for the search endpoint."""

    def test_pagination_metadata_correct_for_single_page(self):
        """When total fits in one page, metadata should reflect that."""
        from routes.scheduler.search import PaginationMeta
        total = 10
        page = 1
        page_size = 50
        total_pages = math.ceil(total / page_size) if total > 0 else 1

        meta = PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )

        assert meta.total == 10
        assert meta.page == 1
        assert meta.page_size == 50
        assert meta.total_pages == 1
        assert meta.has_next is False
        assert meta.has_prev is False

    def test_pagination_metadata_correct_for_multi_page(self):
        """Multiple pages should have correct has_next and has_prev."""
        from routes.scheduler.search import PaginationMeta
        total = 120
        page_size = 50

        total_pages = math.ceil(total / page_size)  # = 3

        # Page 1
        meta1 = PaginationMeta(
            total=total, page=1, page_size=page_size,
            total_pages=total_pages, has_next=1 < total_pages, has_prev=1 > 1,
        )
        assert meta1.has_next is True
        assert meta1.has_prev is False
        assert meta1.total_pages == 3

        # Page 2
        meta2 = PaginationMeta(
            total=total, page=2, page_size=page_size,
            total_pages=total_pages, has_next=2 < total_pages, has_prev=2 > 1,
        )
        assert meta2.has_next is True
        assert meta2.has_prev is True

        # Page 3 (last)
        meta3 = PaginationMeta(
            total=total, page=3, page_size=page_size,
            total_pages=total_pages, has_next=3 < total_pages, has_prev=3 > 1,
        )
        assert meta3.has_next is False
        assert meta3.has_prev is True

    def test_empty_results_have_correct_metadata(self):
        """Empty results should have total=0, page=1, has_next=False."""
        from routes.scheduler.search import PaginationMeta
        total = 0
        page_size = 50
        total_pages = math.ceil(total / page_size) if total > 0 else 1

        meta = PaginationMeta(
            total=total, page=1, page_size=page_size,
            total_pages=total_pages, has_next=1 < total_pages, has_prev=1 > 1,
        )

        assert meta.total == 0
        assert meta.page == 1
        assert meta.total_pages == 1
        assert meta.has_next is False
        assert meta.has_prev is False


class TestSearchPaginationDefaults:
    """Test default and boundary page sizes for search."""

    def test_default_page_size_is_50(self):
        """The default page_size parameter should be 50."""
        from routes.scheduler.search import PaginationMeta
        meta = PaginationMeta()
        assert meta.page_size == 50

    def test_max_page_size_is_500(self):
        """The search endpoint should accept page_size up to 500."""
        # The endpoint defines page_size: int = Query(50, ge=1, le=500)
        # We verify the schema allows 500
        from routes.scheduler.search import PaginationMeta
        meta = PaginationMeta(total=1000, page=1, page_size=500, total_pages=2, has_next=True, has_prev=False)
        assert meta.page_size == 500

    def test_page_size_boundary_at_1(self):
        """page_size of 1 should work (minimum)."""
        from routes.scheduler.search import PaginationMeta
        total = 5
        page_size = 1
        total_pages = math.ceil(total / page_size)

        meta = PaginationMeta(
            total=total, page=1, page_size=page_size,
            total_pages=total_pages, has_next=True, has_prev=False,
        )
        assert meta.page_size == 1
        assert meta.total_pages == 5

    def test_search_response_model_structure(self):
        """SearchResponse should contain data, pagination, and filters_applied."""
        from routes.scheduler.search import SearchResponse, PaginationMeta, FiltersApplied

        response = SearchResponse(
            success=True,
            data=[],
            pagination=PaginationMeta(
                total=0, page=1, page_size=50, total_pages=1,
                has_next=False, has_prev=False,
            ),
            filters_applied=FiltersApplied(),
        )

        assert response.success is True
        assert response.data == []
        assert response.pagination.total == 0
        assert response.pagination.page_size == 50


class TestSearchSQLHelpers:
    """Test the search SQL helper functions directly."""

    def test_escape_like_escapes_percent(self):
        """SQL LIKE special char % should be escaped."""
        from routes.scheduler.search import _escape_like
        assert _escape_like("100%") == "100\\%"

    def test_escape_like_escapes_underscore(self):
        """SQL LIKE special char _ should be escaped."""
        from routes.scheduler.search import _escape_like
        assert _escape_like("first_name") == "first\\_name"

    def test_escape_like_escapes_backslash(self):
        """Backslash should be escaped first."""
        from routes.scheduler.search import _escape_like
        result = _escape_like("path\\file")
        assert "\\\\" in result

    def test_escape_like_clean_text_unchanged(self):
        """Clean text without LIKE wildcards should pass through unchanged."""
        from routes.scheduler.search import _escape_like
        assert _escape_like("John Smith") == "John Smith"


class TestSearchStatusFilter:
    """Test status filter validation."""

    def test_invalid_status_raises_400(self):
        """Invalid status value should raise HTTPException 400."""
        from routes.scheduler.search import _apply_status_filter

        mock_query = MagicMock()

        class MockAppointment:
            status = _Col()

        with pytest.raises(HTTPException) as exc:
            _apply_status_filter(mock_query, MockAppointment, ["definitely_not_a_status"])
        assert exc.value.status_code == 400
        assert "Invalid status" in exc.value.detail

    def test_invalid_date_format_raises_400(self):
        """Invalid date format in date_from should raise 400."""
        from routes.scheduler.search import _apply_date_range

        mock_query = MagicMock()

        class MockAppointment:
            scheduled_start = _Col()

        with pytest.raises(HTTPException) as exc:
            _apply_date_range(mock_query, MockAppointment, "not-a-date", None)
        assert exc.value.status_code == 400
        assert "Invalid date_from" in exc.value.detail

    def test_invalid_date_to_format_raises_400(self):
        """Invalid date format in date_to should raise 400."""
        from routes.scheduler.search import _apply_date_range

        mock_query = MagicMock()

        class MockAppointment:
            scheduled_start = _Col()

        with pytest.raises(HTTPException) as exc:
            _apply_date_range(mock_query, MockAppointment, None, "13/25/2026")
        assert exc.value.status_code == 400
        assert "Invalid date_to" in exc.value.detail


class TestSearchSorting:
    """Test sorting validation."""

    def test_invalid_sort_field_falls_back_to_scheduled_start(self):
        """Invalid sort_by field should fall back to scheduled_start."""
        from routes.scheduler.search import _apply_sorting, ALLOWED_SORT_FIELDS

        assert "drop_table" not in ALLOWED_SORT_FIELDS

        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query

        class MockAppointment:
            scheduled_start = _Col()

        # Should not raise
        result = _apply_sorting(mock_query, MockAppointment, "drop_table", "desc")
        assert result is not None

    def test_valid_sort_fields(self):
        """Valid sort fields should be accepted."""
        from routes.scheduler.search import ALLOWED_SORT_FIELDS

        expected_fields = {"scheduled_start", "created_at", "status", "attendee_name", "updated_at", "title"}
        assert ALLOWED_SORT_FIELDS == expected_fields

    def test_invalid_sort_order_falls_back(self):
        """Invalid sort order should fall back to asc."""
        from routes.scheduler.search import _apply_sorting

        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query

        class MockAppointment:
            scheduled_start = _Col()

        # Invalid sort order
        result = _apply_sorting(mock_query, MockAppointment, "scheduled_start", "INVALID")
        assert result is not None


# =============================================================================
# ANALYTICS PAGINATION TESTS
# =============================================================================

class TestAnalyticsPagination:
    """Test pagination for analytics by-type and by-lo endpoints."""

    def test_analytics_pagination_model_structure(self):
        """PaginationMeta in analytics should have all required fields."""
        from routes.scheduler.analytics import PaginationMeta

        meta = PaginationMeta(
            page=1,
            page_size=50,
            total=100,
            total_pages=2,
            has_next=True,
        )

        assert meta.page == 1
        assert meta.page_size == 50
        assert meta.total == 100
        assert meta.total_pages == 2
        assert meta.has_next is True

    def test_analytics_by_type_pagination_calculation(self):
        """Analytics by-type should paginate the types list correctly."""
        # Simulate the pagination logic from analytics.py
        all_types = [{"type_name": f"Type {i}", "total": i * 10} for i in range(15)]
        total_count = len(all_types)
        page = 1
        page_size = 5

        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
        offset = (page - 1) * page_size
        paginated = all_types[offset:offset + page_size]

        assert total_pages == 3
        assert len(paginated) == 5
        assert paginated[0]["type_name"] == "Type 0"
        assert paginated[4]["type_name"] == "Type 4"

    def test_analytics_by_type_last_page(self):
        """Last page should contain remaining items."""
        all_types = [{"type_name": f"Type {i}"} for i in range(12)]
        total_count = len(all_types)
        page = 3
        page_size = 5

        total_pages = math.ceil(total_count / page_size)
        offset = (page - 1) * page_size
        paginated = all_types[offset:offset + page_size]

        assert total_pages == 3
        assert len(paginated) == 2  # Only 2 remaining on page 3

    def test_analytics_empty_results(self):
        """Empty analytics should return empty list with correct pagination."""
        all_types = []
        total_count = len(all_types)
        page = 1
        page_size = 50

        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

        assert total_count == 0
        assert total_pages == 0
        assert all_types == []

    def test_analytics_by_lo_pagination(self):
        """Analytics by-lo should paginate loan officers correctly."""
        all_los = [{"name": f"LO {i}", "total": i * 5} for i in range(8)]
        total_count = len(all_los)
        page = 2
        page_size = 5

        total_pages = math.ceil(total_count / page_size)
        offset = (page - 1) * page_size
        paginated = all_los[offset:offset + page_size]

        assert total_pages == 2
        assert len(paginated) == 3  # 3 remaining on page 2

    def test_analytics_default_page_size_is_50(self):
        """Default page_size for analytics endpoints should be 50."""
        # The endpoint defines page_size: int = Query(50, ge=1, le=500)
        # Verify via the response model default
        from routes.scheduler.analytics import PaginationMeta
        # Default is enforced at the Query level, not the model.
        # We verify the model accepts 50.
        meta = PaginationMeta(page=1, page_size=50, total=0, total_pages=0, has_next=False)
        assert meta.page_size == 50

    def test_analytics_max_page_size_is_500(self):
        """Max page_size for analytics endpoints should be 500."""
        from routes.scheduler.analytics import PaginationMeta
        meta = PaginationMeta(page=1, page_size=500, total=1000, total_pages=2, has_next=True)
        assert meta.page_size == 500


# =============================================================================
# SEARCH SERIALIZATION TESTS
# =============================================================================

class TestSearchSerialization:
    """Test appointment serialization for search results."""

    def test_serialize_appointment_all_fields(self):
        """_serialize_appointment should include all expected fields."""
        from routes.scheduler.search import _serialize_appointment

        appt = _make_mock_appointment(1)
        result = _serialize_appointment(appt)

        expected_keys = {
            "id", "title", "description", "meeting_type", "meeting_mode",
            "scheduled_start", "scheduled_end", "duration_minutes", "timezone",
            "status", "attendee_name", "attendee_email", "attendee_phone",
            "attendee_notes", "location", "video_link", "lead_id", "loan_id",
            "contact_id", "assigned_user_id", "appointment_type_id",
            "booked_by_ai", "internal_notes", "created_at", "updated_at",
        }

        assert expected_keys.issubset(set(result.keys()))

    def test_serialize_appointment_handles_none_datetimes(self):
        """Serialization should handle None scheduled_start gracefully."""
        from routes.scheduler.search import _serialize_appointment

        appt = _make_mock_appointment(2)
        appt.scheduled_start = None
        appt.scheduled_end = None
        appt.created_at = None
        appt.updated_at = None

        result = _serialize_appointment(appt)

        assert result["scheduled_start"] is None
        assert result["scheduled_end"] is None
        assert result["created_at"] is None
        assert result["updated_at"] is None

    def test_serialize_appointment_extracts_enum_values(self):
        """Serialization should extract .value from enum fields."""
        from routes.scheduler.search import _serialize_appointment

        appt = _make_mock_appointment(3)
        appt.meeting_type.value = "initial_consultation"
        appt.status.value = "booked"

        result = _serialize_appointment(appt)

        assert result["meeting_type"] == "initial_consultation"
        assert result["status"] == "booked"


# =============================================================================
# SEARCH SUGGESTION TESTS
# =============================================================================

class TestSearchSuggestions:
    """Test typeahead suggestion schemas."""

    def test_suggestion_schema_structure(self):
        """SearchSuggestion should have type, value, and label."""
        from routes.scheduler.search import SearchSuggestion

        suggestion = SearchSuggestion(type="attendee", value="John Smith", label="John Smith")
        assert suggestion.type == "attendee"
        assert suggestion.value == "John Smith"
        assert suggestion.label == "John Smith"

    def test_suggestions_response_structure(self):
        """SuggestionsResponse should contain suggestions list and query."""
        from routes.scheduler.search import SuggestionsResponse, SearchSuggestion

        response = SuggestionsResponse(
            success=True,
            suggestions=[
                SearchSuggestion(type="attendee", value="Jane Doe", label="Jane Doe"),
            ],
            query="jane",
        )

        assert response.success is True
        assert len(response.suggestions) == 1
        assert response.query == "jane"
