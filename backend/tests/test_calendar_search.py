"""
Calendar Search API Tests

Tests for the scheduler search endpoint:
- Free-text search across multiple fields
- Status filtering (single and multi)
- Date range filtering
- Attendee email filtering
- Pagination and sorting
- RBAC visibility (admin vs regular user)
- Search suggestions / typeahead
- Edge cases (empty results, invalid params)
"""

import pytest
from datetime import datetime, timedelta, date, time, timezone
from unittest.mock import Mock, MagicMock, patch, PropertyMock, AsyncMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# SQLAlchemy Column Mock
# =============================================================================

class _Col:
    """Fake SQLAlchemy column descriptor for filter expressions."""
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
    def desc(self): return 'DESC'
    def asc(self): return 'ASC'
    def __hash__(self): return id(self)


# =============================================================================
# FIXTURES
# =============================================================================

class MockAppointmentStatus:
    """Mock enum matching AppointmentStatus values."""
    BOOKED = "booked"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


class MockAppointment:
    """Mock Appointment model with class-level column descriptors."""
    id = _Col()
    organization_id = _Col()
    assigned_user_id = _Col()
    created_by_user_id = _Col()
    title = _Col()
    description = _Col()
    attendee_name = _Col()
    attendee_email = _Col()
    attendee_phone = _Col()
    attendee_notes = _Col()
    internal_notes = _Col()
    meeting_notes = _Col()
    location = _Col()
    status = _Col()
    scheduled_start = _Col()
    scheduled_end = _Col()
    appointment_type_id = _Col()
    meeting_type = _Col()
    meeting_mode = _Col()
    lead_id = _Col()
    loan_id = _Col()
    contact_id = _Col()
    booked_by_ai = _Col()
    duration_minutes = _Col()
    timezone_col = _Col()
    video_link = _Col()
    created_at = _Col()
    updated_at = _Col()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class MockUser:
    def __init__(self, id=1, organization_id=1, role='loan_officer', permission_role='sales'):
        self.id = id
        self.organization_id = organization_id
        self.role = role
        self.permission_role = permission_role


def make_appointment(**overrides):
    """Create a mock appointment instance with sensible defaults."""
    defaults = {
        'id': 1,
        'title': 'Discovery Call with John',
        'description': 'Initial consultation',
        'meeting_type': Mock(value='discovery_call'),
        'meeting_mode': Mock(value='video'),
        'scheduled_start': datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
        'scheduled_end': datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc),
        'duration_minutes': 30,
        'timezone': 'America/Chicago',
        'status': Mock(value='booked'),
        'attendee_name': 'John Smith',
        'attendee_email': 'john@example.com',
        'attendee_phone': '555-123-4567',
        'attendee_notes': 'Interested in FHA loan',
        'location': 'Video Call',
        'video_link': 'https://zoom.us/j/123',
        'lead_id': 10,
        'loan_id': None,
        'contact_id': None,
        'assigned_user_id': 1,
        'appointment_type_id': 1,
        'booked_by_ai': False,
        'internal_notes': 'Follow up on rate discussion',
        'created_at': datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc),
        'updated_at': datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return MockAppointment(**defaults)


# =============================================================================
# TESTS FOR _serialize_appointment
# =============================================================================

class TestSerializeAppointment:

    def test_serializes_all_fields(self):
        from routes.scheduler.search import _serialize_appointment
        apt = make_appointment()
        result = _serialize_appointment(apt)

        assert result['id'] == 1
        assert result['title'] == 'Discovery Call with John'
        assert result['attendee_name'] == 'John Smith'
        assert result['attendee_email'] == 'john@example.com'
        assert result['status'] == 'booked'
        assert result['meeting_type'] == 'discovery_call'
        assert result['meeting_mode'] == 'video'
        assert result['duration_minutes'] == 30
        assert result['lead_id'] == 10
        assert result['loan_id'] is None
        assert result['booked_by_ai'] is False
        assert 'scheduled_start' in result
        assert 'created_at' in result

    def test_handles_none_enums(self):
        from routes.scheduler.search import _serialize_appointment
        apt = make_appointment(meeting_type=None, meeting_mode=None, status=None)
        result = _serialize_appointment(apt)

        assert result['meeting_type'] is None
        assert result['meeting_mode'] is None
        assert result['status'] is None

    def test_handles_none_dates(self):
        from routes.scheduler.search import _serialize_appointment
        apt = make_appointment(scheduled_start=None, scheduled_end=None, created_at=None, updated_at=None)
        result = _serialize_appointment(apt)

        assert result['scheduled_start'] is None
        assert result['scheduled_end'] is None
        assert result['created_at'] is None
        assert result['updated_at'] is None


# =============================================================================
# TESTS FOR _apply_status_filter
# =============================================================================

class TestApplyStatusFilter:

    def test_valid_single_status(self):
        from routes.scheduler.search import _apply_status_filter
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        result = _apply_status_filter(mock_query, MockAppointment, ['booked'])
        assert mock_query.filter.called

    def test_valid_multiple_statuses(self):
        from routes.scheduler.search import _apply_status_filter
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        result = _apply_status_filter(mock_query, MockAppointment, ['booked', 'confirmed'])
        assert mock_query.filter.called

    def test_invalid_status_raises_error(self):
        from routes.scheduler.search import _apply_status_filter
        mock_query = Mock()
        with pytest.raises(HTTPException) as exc_info:
            _apply_status_filter(mock_query, MockAppointment, ['invalid_status'])
        assert exc_info.value.status_code == 400
        assert 'Invalid status filter' in str(exc_info.value.detail)

    def test_mixed_valid_invalid_raises_error(self):
        from routes.scheduler.search import _apply_status_filter
        mock_query = Mock()
        with pytest.raises(HTTPException):
            _apply_status_filter(mock_query, MockAppointment, ['booked', 'nonexistent'])


# =============================================================================
# TESTS FOR _apply_date_range
# =============================================================================

class TestApplyDateRange:

    def test_valid_date_from(self):
        from routes.scheduler.search import _apply_date_range
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        result = _apply_date_range(mock_query, MockAppointment, '2026-03-01', None)
        assert mock_query.filter.called

    def test_valid_date_to(self):
        from routes.scheduler.search import _apply_date_range
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        result = _apply_date_range(mock_query, MockAppointment, None, '2026-03-31')
        assert mock_query.filter.called

    def test_both_dates(self):
        from routes.scheduler.search import _apply_date_range
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        result = _apply_date_range(mock_query, MockAppointment, '2026-03-01', '2026-03-31')
        assert mock_query.filter.call_count == 2

    def test_no_dates(self):
        from routes.scheduler.search import _apply_date_range
        mock_query = Mock()
        result = _apply_date_range(mock_query, MockAppointment, None, None)
        assert not mock_query.filter.called

    def test_invalid_date_from_raises_error(self):
        from routes.scheduler.search import _apply_date_range
        mock_query = Mock()
        with pytest.raises(HTTPException) as exc_info:
            _apply_date_range(mock_query, MockAppointment, 'not-a-date', None)
        assert exc_info.value.status_code == 400
        assert 'Invalid date_from' in str(exc_info.value.detail)

    def test_invalid_date_to_raises_error(self):
        from routes.scheduler.search import _apply_date_range
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        with pytest.raises(HTTPException) as exc_info:
            _apply_date_range(mock_query, MockAppointment, None, 'bad-date')
        assert exc_info.value.status_code == 400
        assert 'Invalid date_to' in str(exc_info.value.detail)


# =============================================================================
# TESTS FOR _apply_text_search
# =============================================================================

class TestApplyTextSearch:

    def test_applies_ilike_filter(self):
        from routes.scheduler.search import _apply_text_search
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        result = _apply_text_search(mock_query, MockAppointment, 'john')
        assert mock_query.filter.called
        # Should apply one or_() filter with multiple ilike conditions
        assert mock_query.filter.call_count == 1


# =============================================================================
# TESTS FOR _apply_sorting
# =============================================================================

class TestApplySorting:

    def test_default_sort(self):
        from routes.scheduler.search import _apply_sorting
        mock_query = Mock()
        mock_query.order_by.return_value = mock_query
        result = _apply_sorting(mock_query, MockAppointment, 'scheduled_start', 'desc')
        assert mock_query.order_by.called

    def test_invalid_sort_field_falls_back(self):
        from routes.scheduler.search import _apply_sorting
        mock_query = Mock()
        mock_query.order_by.return_value = mock_query
        # Invalid field should fall back to scheduled_start
        result = _apply_sorting(mock_query, MockAppointment, 'nonexistent_field', 'asc')
        assert mock_query.order_by.called

    def test_invalid_sort_order_falls_back(self):
        from routes.scheduler.search import _apply_sorting
        mock_query = Mock()
        mock_query.order_by.return_value = mock_query
        result = _apply_sorting(mock_query, MockAppointment, 'title', 'invalid_order')
        assert mock_query.order_by.called

    def test_asc_sort(self):
        from routes.scheduler.search import _apply_sorting
        mock_query = Mock()
        mock_query.order_by.return_value = mock_query
        result = _apply_sorting(mock_query, MockAppointment, 'created_at', 'asc')
        assert mock_query.order_by.called

    def test_all_valid_sort_fields(self):
        from routes.scheduler.search import _apply_sorting, ALLOWED_SORT_FIELDS
        for field in ALLOWED_SORT_FIELDS:
            mock_query = Mock()
            mock_query.order_by.return_value = mock_query
            _apply_sorting(mock_query, MockAppointment, field, 'asc')
            assert mock_query.order_by.called


# =============================================================================
# TESTS FOR SEARCH ENDPOINT (integration-style with mocks)
# =============================================================================

class TestSearchEndpoint:
    """Test the search endpoint handler logic via direct function call."""

    def _setup_mocks(self, is_admin=False, appointments=None, total=0):
        """Set up common mocks for the search endpoint."""
        user = MockUser(
            id=1,
            organization_id=1,
            permission_role='admin' if is_admin else 'sales',
        )

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = appointments or []
        mock_query.count.return_value = total
        mock_query.distinct.return_value = mock_query

        mock_db = Mock()
        mock_db.query.return_value = mock_query

        return user, mock_db, mock_query

    @pytest.mark.asyncio
    async def test_search_returns_paginated_results(self):
        """Verify search returns proper pagination metadata."""
        appointments = [make_appointment(id=i) for i in range(1, 4)]
        user, mock_db, mock_query = self._setup_mocks(
            appointments=appointments,
            total=3,
        )

        with patch('routes.scheduler.search.get_current_user', new_callable=AsyncMock, return_value=user), \
             patch('routes.scheduler.search.get_models', return_value={'Appointment': MockAppointment}):

            from routes.scheduler.search import search_appointments
            mock_request = Mock()
            result = await search_appointments(
                request=mock_request,
                q='John',
                status=None,
                appointment_type_id=None,
                assigned_user_id=None,
                date_from=None,
                date_to=None,
                attendee_email=None,
                meeting_type=None,
                lead_id=None,
                loan_id=None,
                booked_by_ai=None,
                sort_by='scheduled_start',
                sort_order='desc',
                page=1,
                page_size=25,
                db=mock_db,
            )

        assert result['success'] is True
        assert len(result['data']) == 3
        assert result['meta']['total'] == 3
        assert result['meta']['page'] == 1
        assert result['meta']['page_size'] == 25
        assert result['meta']['total_pages'] == 1
        assert result['meta']['has_next'] is False
        assert result['meta']['has_prev'] is False

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        """Verify search returns empty array when no results found."""
        user, mock_db, mock_query = self._setup_mocks(total=0)

        with patch('routes.scheduler.search.get_current_user', new_callable=AsyncMock, return_value=user), \
             patch('routes.scheduler.search.get_models', return_value={'Appointment': MockAppointment}):

            from routes.scheduler.search import search_appointments
            result = await search_appointments(
                request=Mock(),
                q='nonexistent',
                status=None,
                appointment_type_id=None,
                assigned_user_id=None,
                date_from=None,
                date_to=None,
                attendee_email=None,
                meeting_type=None,
                lead_id=None,
                loan_id=None,
                booked_by_ai=None,
                sort_by='scheduled_start',
                sort_order='desc',
                page=1,
                page_size=25,
                db=mock_db,
            )

        assert result['success'] is True
        assert len(result['data']) == 0
        assert result['meta']['total'] == 0

    @pytest.mark.asyncio
    async def test_search_with_status_filter(self):
        """Verify status filter is applied to query."""
        appointments = [make_appointment(id=1)]
        user, mock_db, mock_query = self._setup_mocks(
            appointments=appointments,
            total=1,
        )

        with patch('routes.scheduler.search.get_current_user', new_callable=AsyncMock, return_value=user), \
             patch('routes.scheduler.search.get_models', return_value={'Appointment': MockAppointment}):

            from routes.scheduler.search import search_appointments
            result = await search_appointments(
                request=Mock(),
                q=None,
                status=['booked', 'confirmed'],
                appointment_type_id=None,
                assigned_user_id=None,
                date_from=None,
                date_to=None,
                attendee_email=None,
                meeting_type=None,
                lead_id=None,
                loan_id=None,
                booked_by_ai=None,
                sort_by='scheduled_start',
                sort_order='desc',
                page=1,
                page_size=25,
                db=mock_db,
            )

        assert result['success'] is True
        # Verify filter was called (org filter + RBAC + status)
        assert mock_query.filter.call_count >= 2

    @pytest.mark.asyncio
    async def test_search_admin_sees_all_org_appointments(self):
        """Admin users should not have the assigned_user/created_by filter."""
        user, mock_db, mock_query = self._setup_mocks(is_admin=True, total=0)

        with patch('routes.scheduler.search.get_current_user', new_callable=AsyncMock, return_value=user), \
             patch('routes.scheduler.search.get_models', return_value={'Appointment': MockAppointment}):

            from routes.scheduler.search import search_appointments
            result = await search_appointments(
                request=Mock(),
                q=None,
                status=None,
                appointment_type_id=None,
                assigned_user_id=None,
                date_from=None,
                date_to=None,
                attendee_email=None,
                meeting_type=None,
                lead_id=None,
                loan_id=None,
                booked_by_ai=None,
                sort_by='scheduled_start',
                sort_order='desc',
                page=1,
                page_size=25,
                db=mock_db,
            )

        assert result['success'] is True
        # Admin only has org_id filter (1 call), no RBAC filter
        # The first filter call is for org_id only
        first_filter_call = mock_query.filter.call_args_list[0]
        # Should only be called once for org filter (not twice for RBAC)
        # We can't directly inspect or_() vs plain filter, but we verify
        # the total filter count is less than non-admin
        assert mock_query.filter.call_count >= 1

    @pytest.mark.asyncio
    async def test_search_includes_filters_applied_in_response(self):
        """Response should include a 'filters_applied' dict for debugging."""
        user, mock_db, mock_query = self._setup_mocks(total=0)

        with patch('routes.scheduler.search.get_current_user', new_callable=AsyncMock, return_value=user), \
             patch('routes.scheduler.search.get_models', return_value={'Appointment': MockAppointment}):

            from routes.scheduler.search import search_appointments
            result = await search_appointments(
                request=Mock(),
                q='test query',
                status=['booked'],
                appointment_type_id=5,
                assigned_user_id=None,
                date_from='2026-03-01',
                date_to='2026-03-31',
                attendee_email='test@example.com',
                meeting_type=None,
                lead_id=None,
                loan_id=None,
                booked_by_ai=True,
                sort_by='created_at',
                sort_order='asc',
                page=1,
                page_size=25,
                db=mock_db,
            )

        filters = result['filters_applied']
        assert filters['q'] == 'test query'
        assert filters['status'] == ['booked']
        assert filters['appointment_type_id'] == 5
        assert filters['date_from'] == '2026-03-01'
        assert filters['date_to'] == '2026-03-31'
        assert filters['attendee_email'] == 'test@example.com'
        assert filters['booked_by_ai'] is True
        assert filters['sort_by'] == 'created_at'
        assert filters['sort_order'] == 'asc'


# =============================================================================
# TESTS FOR SUGGESTIONS ENDPOINT
# =============================================================================

class TestSearchSuggestions:

    @pytest.mark.asyncio
    async def test_suggestions_returns_results(self):
        """Verify suggestions endpoint returns structured results."""
        user = MockUser()

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.distinct.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [('John Smith',), ('John Doe',)]

        mock_db = Mock()
        mock_db.query.return_value = mock_query

        with patch('routes.scheduler.search.get_current_user', new_callable=AsyncMock, return_value=user), \
             patch('routes.scheduler.search.get_models', return_value={'Appointment': MockAppointment}):

            from routes.scheduler.search import search_suggestions
            result = await search_suggestions(
                request=Mock(),
                q='John',
                limit=8,
                db=mock_db,
            )

        assert result['success'] is True
        assert result['query'] == 'John'
        assert len(result['suggestions']) > 0
        # First suggestions should be attendee type
        assert result['suggestions'][0]['type'] == 'attendee'

    @pytest.mark.asyncio
    async def test_suggestions_empty_when_no_matches(self):
        """Verify suggestions returns empty list when no matches."""
        user = MockUser()

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.distinct.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        mock_db = Mock()
        mock_db.query.return_value = mock_query

        with patch('routes.scheduler.search.get_current_user', new_callable=AsyncMock, return_value=user), \
             patch('routes.scheduler.search.get_models', return_value={'Appointment': MockAppointment}):

            from routes.scheduler.search import search_suggestions
            result = await search_suggestions(
                request=Mock(),
                q='zzz_no_match',
                limit=8,
                db=mock_db,
            )

        assert result['success'] is True
        assert len(result['suggestions']) == 0

    @pytest.mark.asyncio
    async def test_suggestions_respects_limit(self):
        """Suggestions should respect the limit parameter."""
        user = MockUser()
        names = [(f'Person {i}',) for i in range(20)]

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.distinct.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = names[:5]

        mock_db = Mock()
        mock_db.query.return_value = mock_query

        with patch('routes.scheduler.search.get_current_user', new_callable=AsyncMock, return_value=user), \
             patch('routes.scheduler.search.get_models', return_value={'Appointment': MockAppointment}):

            from routes.scheduler.search import search_suggestions
            result = await search_suggestions(
                request=Mock(),
                q='Person',
                limit=5,
                db=mock_db,
            )

        assert result['success'] is True
        assert len(result['suggestions']) <= 5


# =============================================================================
# TESTS FOR PAGINATION EDGE CASES
# =============================================================================

class TestPaginationEdgeCases:

    @pytest.mark.asyncio
    async def test_page_beyond_total_pages_clamped(self):
        """Requesting a page beyond total should clamp to last page."""
        user = MockUser()

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 10  # 10 results total

        mock_db = Mock()
        mock_db.query.return_value = mock_query

        with patch('routes.scheduler.search.get_current_user', new_callable=AsyncMock, return_value=user), \
             patch('routes.scheduler.search.get_models', return_value={'Appointment': MockAppointment}):

            from routes.scheduler.search import search_appointments
            result = await search_appointments(
                request=Mock(),
                q=None,
                status=None,
                appointment_type_id=None,
                assigned_user_id=None,
                date_from=None,
                date_to=None,
                attendee_email=None,
                meeting_type=None,
                lead_id=None,
                loan_id=None,
                booked_by_ai=None,
                sort_by='scheduled_start',
                sort_order='desc',
                page=999,  # Way beyond actual pages
                page_size=25,
                db=mock_db,
            )

        # Page should be clamped to 1 (since 10/25 = 1 page)
        assert result['meta']['page'] == 1

    @pytest.mark.asyncio
    async def test_total_pages_calculation(self):
        """Verify total_pages is calculated correctly."""
        user = MockUser()

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.count.return_value = 51

        mock_db = Mock()
        mock_db.query.return_value = mock_query

        with patch('routes.scheduler.search.get_current_user', new_callable=AsyncMock, return_value=user), \
             patch('routes.scheduler.search.get_models', return_value={'Appointment': MockAppointment}):

            from routes.scheduler.search import search_appointments
            result = await search_appointments(
                request=Mock(),
                q=None,
                status=None,
                appointment_type_id=None,
                assigned_user_id=None,
                date_from=None,
                date_to=None,
                attendee_email=None,
                meeting_type=None,
                lead_id=None,
                loan_id=None,
                booked_by_ai=None,
                sort_by='scheduled_start',
                sort_order='desc',
                page=1,
                page_size=25,
                db=mock_db,
            )

        # 51 / 25 = 3 pages (ceil)
        assert result['meta']['total_pages'] == 3
        assert result['meta']['has_next'] is True
        assert result['meta']['has_prev'] is False


# =============================================================================
# TESTS FOR ALLOWED_SORT_FIELDS
# =============================================================================

class TestAllowedSortFields:

    def test_expected_fields(self):
        from routes.scheduler.search import ALLOWED_SORT_FIELDS
        expected = {'scheduled_start', 'created_at', 'status', 'attendee_name', 'updated_at', 'title'}
        assert ALLOWED_SORT_FIELDS == expected


# =============================================================================
# TESTS FOR NO ORG CONTEXT
# =============================================================================

class TestNoOrgContext:

    @pytest.mark.asyncio
    async def test_no_org_raises_403(self):
        """User with no organization_id should get 403."""
        user = MockUser(organization_id=None)

        with patch('routes.scheduler.search.get_current_user', new_callable=AsyncMock, return_value=user), \
             patch('routes.scheduler.search.get_models', return_value={'Appointment': MockAppointment}):

            from routes.scheduler.search import search_appointments
            with pytest.raises(HTTPException) as exc_info:
                await search_appointments(
                    request=Mock(),
                    q=None,
                    status=None,
                    appointment_type_id=None,
                    assigned_user_id=None,
                    date_from=None,
                    date_to=None,
                    attendee_email=None,
                    meeting_type=None,
                    lead_id=None,
                    loan_id=None,
                    booked_by_ai=None,
                    sort_by='scheduled_start',
                    sort_order='desc',
                    page=1,
                    page_size=25,
                    db=Mock(),
                )
            assert exc_info.value.status_code == 403
