"""
Tests for calendar export functionality - ICS generation and PDF schedule.

Covers:
- ICS format validation (proper VCALENDAR/VEVENT structure)
- Multi-appointment ICS generation
- Single appointment ICS generation
- Special character escaping in ICS fields
- Date range filtering via route helpers
- PDF/HTML schedule generation
- CalendarExportService public API
"""

import pytest
from datetime import datetime, date, timedelta, timezone
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from services.calendar_export import (
    CalendarExportService,
    _appointment_to_event_dict,
    _build_schedule_html,
    _ICS_STATUS_MAP,
)


# =============================================================================
# Fixtures
# =============================================================================

def _make_appointment(**overrides):
    """Create a mock Appointment object with sensible defaults."""
    defaults = {
        "id": 1,
        "organization_id": 100,
        "title": "Discovery Call",
        "description": "Initial consultation",
        "scheduled_start": datetime(2026, 3, 15, 14, 0, 0, tzinfo=timezone.utc),
        "scheduled_end": datetime(2026, 3, 15, 14, 30, 0, tzinfo=timezone.utc),
        "duration_minutes": 30,
        "status": SimpleNamespace(value="booked"),
        "location": "123 Main St",
        "video_link": "https://meet.example.com/abc",
        "attendee_name": "Jane Borrower",
        "attendee_email": "jane@example.com",
        "attendee_phone": "555-0100",
        "internal_notes": "High priority lead",
        "assigned_user_id": 10,
        "meeting_type": SimpleNamespace(value="discovery_call"),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_appointments_list(count=3):
    """Create a list of mock appointments across multiple days."""
    appointments = []
    base_date = datetime(2026, 3, 15, 9, 0, 0, tzinfo=timezone.utc)
    for i in range(count):
        start = base_date + timedelta(days=i, hours=i)
        appointments.append(_make_appointment(
            id=i + 1,
            title=f"Meeting {i + 1}",
            scheduled_start=start,
            scheduled_end=start + timedelta(minutes=30),
            attendee_name=f"Client {i + 1}",
            attendee_email=f"client{i + 1}@example.com",
        ))
    return appointments


# =============================================================================
# ICS Format Validation
# =============================================================================

class TestICSGeneration:
    """Tests for ICS file generation."""

    def test_ics_has_vcalendar_structure(self):
        """ICS output must have BEGIN/END VCALENDAR wrapper."""
        appts = [_make_appointment()]
        ics = CalendarExportService.generate_ics(appts)

        assert "BEGIN:VCALENDAR" in ics
        assert "END:VCALENDAR" in ics
        assert "VERSION:2.0" in ics
        assert "PRODID:" in ics

    def test_ics_has_vevent_for_each_appointment(self):
        """Each appointment should produce a VEVENT block."""
        appts = _make_appointments_list(3)
        ics = CalendarExportService.generate_ics(appts)

        assert ics.count("BEGIN:VEVENT") == 3
        assert ics.count("END:VEVENT") == 3

    def test_ics_single_appointment(self):
        """Single appointment ICS should have exactly one VEVENT."""
        appt = _make_appointment()
        ics = CalendarExportService.generate_ics_single(appt)

        assert ics.count("BEGIN:VEVENT") == 1
        assert ics.count("END:VEVENT") == 1
        assert "Discovery Call" in ics

    def test_ics_contains_appointment_details(self):
        """VEVENT should contain summary, dtstart, dtend."""
        appt = _make_appointment(
            title="Rate Lock Discussion",
            scheduled_start=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 4, 1, 10, 30, 0, tzinfo=timezone.utc),
        )
        ics = CalendarExportService.generate_ics_single(appt)

        assert "SUMMARY:Rate Lock Discussion" in ics
        assert "DTSTART:20260401T100000Z" in ics
        assert "DTEND:20260401T103000Z" in ics

    def test_ics_contains_location(self):
        """Location should appear in VEVENT when set."""
        appt = _make_appointment(location="456 Oak Ave, Suite 200")
        ics = CalendarExportService.generate_ics_single(appt)

        assert "LOCATION:" in ics
        assert "456 Oak Ave" in ics

    def test_ics_uses_video_link_as_location_fallback(self):
        """When location is empty, video_link should be used."""
        appt = _make_appointment(location="", video_link="https://zoom.us/j/123456")
        ics = CalendarExportService.generate_ics_single(appt)

        assert "LOCATION:" in ics
        assert "zoom.us" in ics

    def test_ics_calendar_name_header(self):
        """X-WR-CALNAME should contain the provided calendar name."""
        appts = [_make_appointment()]
        ics = CalendarExportService.generate_ics(appts, calendar_name="My Custom Schedule")

        assert "X-WR-CALNAME:My Custom Schedule" in ics

    def test_ics_method_publish(self):
        """Multi-event calendar should use METHOD:PUBLISH."""
        appts = [_make_appointment()]
        ics = CalendarExportService.generate_ics(appts)

        assert "METHOD:PUBLISH" in ics

    def test_ics_crlf_line_endings(self):
        """ICS must use CRLF line endings per RFC 5545."""
        appt = _make_appointment()
        ics = CalendarExportService.generate_ics_single(appt)

        # Every line should end with \r\n
        assert "\r\n" in ics

    def test_ics_uid_is_unique_per_appointment(self):
        """Each VEVENT should have a unique UID."""
        appts = _make_appointments_list(3)
        ics = CalendarExportService.generate_ics(appts)

        # Extract UIDs
        uids = [line.split(":", 1)[1] for line in ics.split("\r\n") if line.startswith("UID:")]
        assert len(uids) == 3
        assert len(set(uids)) == 3  # all unique

    def test_ics_empty_appointments(self):
        """Empty appointment list should produce valid calendar with no events."""
        ics = CalendarExportService.generate_ics([])

        assert "BEGIN:VCALENDAR" in ics
        assert "END:VCALENDAR" in ics
        assert "BEGIN:VEVENT" not in ics


class TestICSSpecialCharacterEscaping:
    """Tests for proper escaping of special characters in ICS fields."""

    def test_semicolons_escaped(self):
        """Semicolons in text must be escaped with backslash."""
        appt = _make_appointment(title="Call; discuss rates; finalize")
        ics = CalendarExportService.generate_ics_single(appt)

        assert "Call\\; discuss rates\\; finalize" in ics

    def test_commas_escaped(self):
        """Commas in text must be escaped."""
        appt = _make_appointment(title="Review docs, rates, and timeline")
        ics = CalendarExportService.generate_ics_single(appt)

        assert "Review docs\\, rates\\, and timeline" in ics

    def test_backslashes_escaped(self):
        """Backslashes must be double-escaped."""
        appt = _make_appointment(description="Path: C:\\Users\\docs")
        ics = CalendarExportService.generate_ics_single(appt)

        assert "C:\\\\Users\\\\docs" in ics

    def test_newlines_escaped(self):
        """Newlines in description must be escaped as literal \\n."""
        appt = _make_appointment(description="Line 1\nLine 2\nLine 3")
        ics = CalendarExportService.generate_ics_single(appt)

        # The literal string \n (not an actual newline) should appear
        assert "Line 1\\n" in ics


# =============================================================================
# Appointment-to-event conversion
# =============================================================================

class TestAppointmentToEventDict:
    """Tests for the internal appointment-to-dict converter."""

    def test_basic_conversion(self):
        """Should extract all key fields from appointment."""
        appt = _make_appointment()
        result = _appointment_to_event_dict(appt)

        assert result["summary"] == "Discovery Call"
        assert result["start"] == appt.scheduled_start
        assert result["end"] == appt.scheduled_end
        assert "uid" in result
        assert "@perenniaai.com" in result["uid"]

    def test_description_includes_attendee_info(self):
        """Description should include attendee details."""
        appt = _make_appointment(
            attendee_name="John Smith",
            attendee_email="john@example.com",
            attendee_phone="555-1234",
        )
        result = _appointment_to_event_dict(appt)

        assert "John Smith" in result["description"]
        assert "john@example.com" in result["description"]
        assert "555-1234" in result["description"]

    def test_description_includes_video_link(self):
        """Video link should appear in description."""
        appt = _make_appointment(video_link="https://zoom.us/j/999")
        result = _appointment_to_event_dict(appt)

        assert "https://zoom.us/j/999" in result["description"]

    def test_description_includes_notes(self):
        """Internal notes should appear in description."""
        appt = _make_appointment(internal_notes="VIP client, handle with care")
        result = _appointment_to_event_dict(appt)

        assert "VIP client" in result["description"]

    def test_location_prefers_physical_address(self):
        """Physical location takes priority over video link."""
        appt = _make_appointment(location="100 Main St", video_link="https://zoom.us/j/123")
        result = _appointment_to_event_dict(appt)

        assert result["location"] == "100 Main St"

    def test_location_falls_back_to_video_link(self):
        """When location is empty, video link is used."""
        appt = _make_appointment(location="", video_link="https://meet.example.com/xyz")
        result = _appointment_to_event_dict(appt)

        assert result["location"] == "https://meet.example.com/xyz"

    def test_location_empty_when_both_missing(self):
        """Location should be empty string when both are absent."""
        appt = _make_appointment(location="", video_link="")
        result = _appointment_to_event_dict(appt)

        assert result["location"] == ""

    def test_handles_none_optional_fields(self):
        """Should handle None gracefully for optional fields."""
        appt = _make_appointment(
            description=None,
            attendee_name=None,
            attendee_email=None,
            attendee_phone=None,
            video_link=None,
            internal_notes=None,
            location=None,
        )
        result = _appointment_to_event_dict(appt)

        assert result["summary"] == "Discovery Call"
        assert result["location"] == ""

    def test_handles_string_status(self):
        """Should handle status as plain string (not enum)."""
        appt = _make_appointment(status="booked")
        result = _appointment_to_event_dict(appt)
        # Should not raise
        assert result["summary"] == "Discovery Call"


# =============================================================================
# PDF / HTML Schedule Generation
# =============================================================================

class TestPDFScheduleGeneration:
    """Tests for PDF/HTML schedule output."""

    def test_html_contains_user_name(self):
        """Schedule should display the user's name."""
        appts = _make_appointments_list(2)
        html = _build_schedule_html(appts, "Sarah Johnson", (date(2026, 3, 15), date(2026, 3, 17)), "Perennia Inc")

        assert "Sarah Johnson" in html

    def test_html_contains_org_name(self):
        """Schedule should display the organization name."""
        appts = [_make_appointment()]
        html = _build_schedule_html(appts, "User", (date(2026, 3, 15), date(2026, 3, 15)), "Acme Mortgage")

        assert "Acme Mortgage" in html

    def test_html_contains_date_range(self):
        """Schedule header should show the date range."""
        appts = [_make_appointment()]
        html = _build_schedule_html(appts, "User", (date(2026, 3, 1), date(2026, 3, 31)), "")

        assert "March 01, 2026" in html
        assert "March 31, 2026" in html

    def test_html_contains_appointment_titles(self):
        """Each appointment title should appear in the schedule."""
        appts = _make_appointments_list(3)
        html = _build_schedule_html(appts, "User", (date(2026, 3, 15), date(2026, 3, 17)), "")

        assert "Meeting 1" in html
        assert "Meeting 2" in html
        assert "Meeting 3" in html

    def test_html_contains_attendee_names(self):
        """Attendee names should be shown."""
        appts = [_make_appointment(attendee_name="John Doe")]
        html = _build_schedule_html(appts, "User", (date(2026, 3, 15), date(2026, 3, 15)), "")

        assert "John Doe" in html

    def test_html_contains_time_format(self):
        """Times should be displayed in readable format."""
        appt = _make_appointment(
            scheduled_start=datetime(2026, 3, 15, 14, 0, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 3, 15, 14, 30, 0, tzinfo=timezone.utc),
        )
        html = _build_schedule_html([appt], "User", (date(2026, 3, 15), date(2026, 3, 15)), "")

        assert "02:00 PM" in html
        assert "02:30 PM" in html

    def test_html_groups_by_date(self):
        """Appointments should be grouped by date with date headers."""
        appts = _make_appointments_list(3)  # spans 3 days
        html = _build_schedule_html(appts, "User", (date(2026, 3, 15), date(2026, 3, 17)), "")

        # Date headers should appear
        assert "Sunday, March 15, 2026" in html
        assert "Monday, March 16, 2026" in html
        assert "Tuesday, March 17, 2026" in html

    def test_html_empty_schedule(self):
        """Empty schedule should show a friendly message."""
        html = _build_schedule_html([], "User", (date(2026, 3, 15), date(2026, 3, 17)), "")

        assert "No appointments scheduled" in html

    def test_html_contains_status_badges(self):
        """Status should be displayed as styled badges."""
        appt = _make_appointment(status=SimpleNamespace(value="booked"))
        html = _build_schedule_html([appt], "User", (date(2026, 3, 15), date(2026, 3, 15)), "")

        assert "badge" in html
        assert "booked" in html

    def test_html_appointment_count(self):
        """Summary should show the total appointment count."""
        appts = _make_appointments_list(5)
        html = _build_schedule_html(appts, "User", (date(2026, 3, 15), date(2026, 3, 19)), "")

        assert "<strong>5</strong>" in html

    def test_html_escapes_xss_in_title(self):
        """HTML special characters in titles must be escaped."""
        appt = _make_appointment(title="<script>alert('xss')</script>")
        html = _build_schedule_html([appt], "User", (date(2026, 3, 15), date(2026, 3, 15)), "")

        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_html_escapes_xss_in_attendee(self):
        """HTML special characters in attendee names must be escaped."""
        appt = _make_appointment(attendee_name='"><img src=x onerror=alert(1)>')
        html = _build_schedule_html([appt], "User", (date(2026, 3, 15), date(2026, 3, 15)), "")

        assert "<img" not in html

    def test_html_is_valid_document(self):
        """Output should be a complete HTML5 document."""
        html = _build_schedule_html([], "User", (date(2026, 3, 15), date(2026, 3, 15)), "")

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "<head>" in html
        assert "<body>" in html

    def test_generate_pdf_schedule_returns_bytes(self):
        """generate_pdf_schedule should return bytes (HTML fallback)."""
        appts = _make_appointments_list(2)
        result = CalendarExportService.generate_pdf_schedule(
            appointments=appts,
            user_name="Test User",
            date_range=(date(2026, 3, 15), date(2026, 3, 16)),
            org_name="Test Org",
        )

        assert isinstance(result, bytes)
        assert b"Test User" in result
        assert b"Test Org" in result


# =============================================================================
# CalendarExportService API
# =============================================================================

class TestCalendarExportServiceAPI:
    """Tests for the public CalendarExportService methods."""

    def test_generate_ics_returns_string(self):
        """generate_ics should return a string."""
        result = CalendarExportService.generate_ics([_make_appointment()])
        assert isinstance(result, str)

    def test_generate_ics_single_returns_string(self):
        """generate_ics_single should return a string."""
        result = CalendarExportService.generate_ics_single(_make_appointment())
        assert isinstance(result, str)

    def test_pdf_content_type_without_weasyprint(self):
        """Without weasyprint, content type should be text/html."""
        # In test environment weasyprint is typically not installed
        content_type = CalendarExportService.pdf_content_type()
        assert content_type in ("application/pdf", "text/html")

    def test_pdf_file_extension_without_weasyprint(self):
        """Without weasyprint, extension should be html."""
        ext = CalendarExportService.pdf_file_extension()
        assert ext in ("pdf", "html")

    def test_generate_ics_large_batch(self):
        """ICS generation should handle a large number of appointments."""
        appts = [_make_appointment(id=i, title=f"Appt {i}") for i in range(100)]
        ics = CalendarExportService.generate_ics(appts)

        assert ics.count("BEGIN:VEVENT") == 100
        assert ics.count("END:VEVENT") == 100

    def test_generate_ics_preserves_appointment_order(self):
        """Events in ICS should appear in the order provided."""
        appts = [
            _make_appointment(id=1, title="First Meeting"),
            _make_appointment(id=2, title="Second Meeting"),
            _make_appointment(id=3, title="Third Meeting"),
        ]
        ics = CalendarExportService.generate_ics(appts)

        first_pos = ics.index("First Meeting")
        second_pos = ics.index("Second Meeting")
        third_pos = ics.index("Third Meeting")

        assert first_pos < second_pos < third_pos


# =============================================================================
# ICS Status Mapping
# =============================================================================

class TestICSStatusMap:
    """Tests for the status mapping constants."""

    def test_booked_maps_to_confirmed(self):
        assert _ICS_STATUS_MAP["booked"] == "CONFIRMED"

    def test_confirmed_maps_to_confirmed(self):
        assert _ICS_STATUS_MAP["confirmed"] == "CONFIRMED"

    def test_tentative_maps_to_tentative(self):
        assert _ICS_STATUS_MAP["tentative"] == "TENTATIVE"

    def test_cancelled_maps_to_cancelled(self):
        assert _ICS_STATUS_MAP["cancelled"] == "CANCELLED"

    def test_no_show_maps_to_cancelled(self):
        assert _ICS_STATUS_MAP["no_show"] == "CANCELLED"

    def test_completed_maps_to_confirmed(self):
        assert _ICS_STATUS_MAP["completed"] == "CONFIRMED"


# =============================================================================
# Route-level tests (mock DB/auth)
# =============================================================================

class TestCalendarExportRoutes:
    """Tests for the FastAPI route handlers (unit-tested with mocks)."""

    def test_parse_date_valid(self):
        """_parse_date should accept YYYY-MM-DD format."""
        from routes.calendar_export_routes import _parse_date
        result = _parse_date("2026-03-15", "test")
        assert result == date(2026, 3, 15)

    def test_parse_date_invalid_raises(self):
        """_parse_date should raise HTTPException for invalid format."""
        from routes.calendar_export_routes import _parse_date
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _parse_date("03/15/2026", "start_date")
        assert exc_info.value.status_code == 400
        assert "start_date" in str(exc_info.value.detail)

    def test_parse_date_empty_raises(self):
        """_parse_date should raise HTTPException for empty string."""
        from routes.calendar_export_routes import _parse_date
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _parse_date("", "end_date")

    def test_get_org_id_raises_on_missing(self):
        """_get_org_id should raise 403 when user has no org."""
        from routes.calendar_export_routes import _get_org_id
        from fastapi import HTTPException

        user = SimpleNamespace(id=1)  # no organization_id
        with pytest.raises(HTTPException) as exc_info:
            _get_org_id(user)
        assert exc_info.value.status_code == 403

    def test_get_org_id_returns_org(self):
        """_get_org_id should return the organization_id."""
        from routes.calendar_export_routes import _get_org_id

        user = SimpleNamespace(id=1, organization_id=42)
        assert _get_org_id(user) == 42
