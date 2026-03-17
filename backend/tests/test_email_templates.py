"""
Tests for EmailTemplateService and responsive appointment email templates.

Verifies:
- Template file loading and caching
- Variable substitution (including XSS escaping)
- Base layout wrapping
- Each high-level render method (confirmation, reminder, cancelled, rescheduled, no-show)
- Fragment builders (video button, calendar notice, team member row, etc.)
- Edge cases (missing variables, None values)
"""

import html
import os
import sys
import pytest

# Ensure backend directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.email_template_service import (
    EmailTemplateService,
    TEMPLATES_DIR,
    DEFAULT_BRANDING,
    HEADER_GRADIENTS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_template_cache():
    """Clear template cache before each test to ensure fresh reads."""
    EmailTemplateService.clear_cache()
    yield
    EmailTemplateService.clear_cache()


# ---------------------------------------------------------------------------
# Template file existence
# ---------------------------------------------------------------------------

class TestTemplateFiles:
    """Verify that all expected template files exist."""

    REQUIRED_TEMPLATES = [
        "base",
        "appointment_confirmation",
        "appointment_reminder",
        "appointment_cancelled",
        "appointment_rescheduled",
        "no_show_followup",
    ]

    @pytest.mark.parametrize("template_name", REQUIRED_TEMPLATES)
    def test_template_file_exists(self, template_name):
        path = TEMPLATES_DIR / f"{template_name}.html"
        assert path.exists(), f"Template file missing: {path}"

    @pytest.mark.parametrize("template_name", REQUIRED_TEMPLATES)
    def test_template_file_not_empty(self, template_name):
        path = TEMPLATES_DIR / f"{template_name}.html"
        content = path.read_text(encoding="utf-8")
        assert len(content) > 100, f"Template {template_name} appears too short"


# ---------------------------------------------------------------------------
# Core rendering
# ---------------------------------------------------------------------------

class TestCoreRendering:
    """Test the low-level render() and render_with_base() methods."""

    def test_render_substitutes_variables(self):
        """Variables in {{key}} format should be replaced."""
        result = EmailTemplateService.render("appointment_confirmation", {
            "attendee_name": "Alice",
            "appointment_date": "March 15, 2026",
            "appointment_time": "10:00 AM",
            "duration": "30 minutes",
            "meeting_mode": "Video Call",
            "team_member_section": "",
            "team_member_bottom_pad": "0",
            "video_button": "",
            "calendar_notice": "",
            "reschedule_section": "",
            "lo_contact_section": "",
        })
        assert "Alice" in result
        assert "March 15, 2026" in result
        assert "10:00 AM" in result
        assert "30 minutes" in result

    def test_render_strips_unreplaced_placeholders(self):
        """Any remaining {{...}} placeholders should be stripped."""
        result = EmailTemplateService.render("appointment_confirmation", {
            "attendee_name": "Bob",
        })
        # After rendering, no {{variable}} tokens should remain
        assert "{{" not in result

    def test_render_with_base_wraps_body(self):
        """render_with_base should embed the body inside the base layout."""
        result = EmailTemplateService.render_with_base(
            "appointment_confirmation",
            {
                "attendee_name": "Carol",
                "appointment_date": "April 1, 2026",
                "appointment_time": "2:00 PM",
                "duration": "45 minutes",
                "meeting_mode": "Phone Call",
                "team_member_section": "",
                "team_member_bottom_pad": "0",
                "video_button": "",
                "calendar_notice": "",
                "reschedule_section": "",
                "lo_contact_section": "",
            },
            {
                "header_gradient": HEADER_GRADIENTS["confirmation"],
                "heading": "Test Heading",
                "header_icon": "",
                "header_subtitle": "",
                "preheader_text": "Preview text",
                "email_title": "Test Email",
            },
        )
        # Should contain the base template structure
        assert "<!DOCTYPE html>" in result
        assert "<html" in result
        assert "Test Heading" in result
        # And the body content
        assert "Carol" in result
        assert "April 1, 2026" in result

    def test_render_caches_template(self):
        """Second call should use the cached version."""
        EmailTemplateService._load_template("base")
        assert "base" in EmailTemplateService._template_cache
        # Call again -- should not raise
        EmailTemplateService._load_template("base")

    def test_clear_cache(self):
        EmailTemplateService._load_template("base")
        assert "base" in EmailTemplateService._template_cache
        EmailTemplateService.clear_cache()
        assert "base" not in EmailTemplateService._template_cache

    def test_render_missing_template_raises(self):
        with pytest.raises(FileNotFoundError):
            EmailTemplateService.render("nonexistent_template_xyz", {})


# ---------------------------------------------------------------------------
# XSS escaping
# ---------------------------------------------------------------------------

class TestXSSEscaping:
    """Ensure user-supplied values are HTML-escaped."""

    def test_confirmation_escapes_xss_in_name(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name='<script>alert("xss")</script>',
            appointment_title="Consult",
            appointment_date="March 20, 2026",
            appointment_time="3:00 PM",
            duration="30 minutes",
        )
        assert "<script>" not in result
        assert html.escape('<script>alert("xss")</script>') in result

    def test_cancelled_escapes_reason(self):
        result = EmailTemplateService.render_cancelled(
            attendee_name="Normal User",
            appointment_title="Meeting",
            appointment_date="March 20, 2026",
            appointment_time="3:00 PM",
            cancellation_reason='<img src=x onerror=alert(1)>',
        )
        # The raw tag must not appear -- only the entity-escaped form
        assert "<img src=x" not in result
        assert html.escape('<img src=x onerror=alert(1)>') in result

    def test_video_button_escapes_url(self):
        result = EmailTemplateService.build_video_button(
            'https://evil.com/"><script>alert(1)</script>'
        )
        assert "<script>" not in result


# ---------------------------------------------------------------------------
# Fragment builders
# ---------------------------------------------------------------------------

class TestFragmentBuilders:
    """Test static HTML fragment builder methods."""

    def test_video_button_empty_link(self):
        assert EmailTemplateService.build_video_button("") == ""
        assert EmailTemplateService.build_video_button(None) == ""

    def test_video_button_with_link(self):
        result = EmailTemplateService.build_video_button("https://meet.example.com/abc")
        assert "Join Video Call" in result
        assert "https://meet.example.com/abc" in result

    def test_video_button_with_copy_link(self):
        result = EmailTemplateService.build_video_button(
            "https://meet.example.com/abc", show_copy_link=True
        )
        assert "Or copy this link" in result

    def test_calendar_notice_default(self):
        result = EmailTemplateService.build_calendar_notice()
        assert "calendar invite" in result.lower()

    def test_calendar_notice_custom(self):
        result = EmailTemplateService.build_calendar_notice("Custom notice text")
        assert "Custom notice text" in result

    def test_team_member_row_empty(self):
        assert EmailTemplateService.build_team_member_row("") == ""
        assert EmailTemplateService.build_team_member_row(None) == ""

    def test_team_member_row_with_name(self):
        result = EmailTemplateService.build_team_member_row("Jane Smith")
        assert "Jane Smith" in result
        assert "Meeting With" in result

    def test_reschedule_button_empty_url(self):
        assert EmailTemplateService.build_reschedule_button("") == ""
        assert EmailTemplateService.build_reschedule_button(None) == ""

    def test_reschedule_button_secondary(self):
        result = EmailTemplateService.build_reschedule_button(
            "https://example.com/reschedule"
        )
        assert "Reschedule Appointment" in result
        assert "#f3f4f6" in result  # secondary style bg

    def test_reschedule_button_primary(self):
        result = EmailTemplateService.build_reschedule_button(
            "https://example.com/reschedule",
            label="Reschedule Now",
            style="primary",
        )
        assert "Reschedule Now" in result
        assert "2563eb" in result  # primary gradient

    def test_lo_contact_card_empty(self):
        assert EmailTemplateService.build_lo_contact_card() == ""
        assert EmailTemplateService.build_lo_contact_card(None) == ""

    def test_lo_contact_card_with_details(self):
        result = EmailTemplateService.build_lo_contact_card(
            lo_name="John Doe",
            lo_email="john@example.com",
            lo_phone="555-1234",
        )
        assert "John Doe" in result
        assert "john@example.com" in result
        assert "555-1234" in result
        assert "Your Contact" in result

    def test_prep_checklist_empty(self):
        assert EmailTemplateService.build_prep_checklist([]) == ""

    def test_prep_checklist_with_items(self):
        result = EmailTemplateService.build_prep_checklist([
            "Bring pay stubs",
            "Have ID ready",
        ])
        assert "Preparation Checklist" in result
        assert "Bring pay stubs" in result
        assert "Have ID ready" in result

    def test_reason_row_empty(self):
        assert EmailTemplateService.build_reason_row(None) == ""
        assert EmailTemplateService.build_reason_row("") == ""

    def test_reason_row_with_text(self):
        result = EmailTemplateService.build_reason_row("Schedule conflict")
        assert "Schedule conflict" in result
        assert "Reason" in result


# ---------------------------------------------------------------------------
# High-level render methods
# ---------------------------------------------------------------------------

class TestRenderConfirmation:
    """Test render_confirmation()."""

    def test_basic_confirmation(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name="Alice Johnson",
            appointment_title="Mortgage Consultation",
            appointment_date="March 15, 2026",
            appointment_time="10:00 AM",
            duration="30 minutes",
        )
        assert "Alice Johnson" in result
        assert "Mortgage Consultation" in result
        assert "March 15, 2026" in result
        assert "10:00 AM" in result
        assert "30 minutes" in result
        assert "Appointment Confirmed!" in result
        assert "<!DOCTYPE html>" in result

    def test_confirmation_with_team_member(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name="Bob",
            appointment_title="Review",
            appointment_date="April 1, 2026",
            appointment_time="2:00 PM",
            duration="60 minutes",
            team_member_name="Sarah LO",
        )
        assert "Sarah LO" in result
        assert "Meeting With" in result

    def test_confirmation_with_video_link(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name="Carol",
            appointment_title="Video Consult",
            appointment_date="April 2, 2026",
            appointment_time="3:00 PM",
            duration="45 minutes",
            video_link="https://meet.example.com/12345",
        )
        assert "Join Video Call" in result
        assert "https://meet.example.com/12345" in result

    def test_confirmation_with_reschedule_url(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name="Dan",
            appointment_title="Consult",
            appointment_date="April 3, 2026",
            appointment_time="4:00 PM",
            duration="30 minutes",
            reschedule_url="https://example.com/reschedule?token=abc",
        )
        assert "Reschedule Appointment" in result
        assert "reschedule?token=abc" in result

    def test_confirmation_with_lo_contact(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name="Eve",
            appointment_title="Call",
            appointment_date="April 4, 2026",
            appointment_time="5:00 PM",
            duration="15 minutes",
            lo_name="Frank LO",
            lo_email="frank@company.com",
            lo_phone="555-9999",
        )
        assert "Frank LO" in result
        assert "frank@company.com" in result
        assert "555-9999" in result

    def test_confirmation_with_custom_branding(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name="Grace",
            appointment_title="Branded Call",
            appointment_date="April 5, 2026",
            appointment_time="6:00 PM",
            duration="30 minutes",
            org_branding={
                "org_name": "Custom Mortgage Co",
                "footer_text": "Custom footer",
            },
        )
        assert "Custom Mortgage Co" in result
        assert "Custom footer" in result


class TestRenderReminder:
    """Test render_reminder()."""

    def test_reminder_24h(self):
        result = EmailTemplateService.render_reminder(
            attendee_name="Alice",
            appointment_title="Consultation",
            appointment_date="March 15, 2026",
            appointment_time="10:00 AM",
            duration="30 minutes",
            hours_before=24,
        )
        assert "Tomorrow" in result
        assert "friendly reminder" in result

    def test_reminder_1h(self):
        result = EmailTemplateService.render_reminder(
            attendee_name="Bob",
            appointment_title="Call",
            appointment_date="March 15, 2026",
            appointment_time="10:00 AM",
            duration="30 minutes",
            hours_before=1,
        )
        assert "Soon" in result
        assert "coming up shortly" in result

    def test_reminder_with_prep_items(self):
        result = EmailTemplateService.render_reminder(
            attendee_name="Carol",
            appointment_title="Application Review",
            appointment_date="March 15, 2026",
            appointment_time="10:00 AM",
            duration="30 minutes",
            prep_items=["Bring W-2s", "Have bank statements ready"],
        )
        assert "Preparation Checklist" in result
        assert "Bring W-2s" in result
        assert "Have bank statements ready" in result

    def test_reminder_with_heading_override(self):
        result = EmailTemplateService.render_reminder(
            attendee_name="Dan",
            appointment_title="Prep",
            appointment_date="March 15, 2026",
            appointment_time="10:00 AM",
            duration="30 minutes",
            heading_override="Prepare for Your Appointment",
        )
        assert "Prepare for Your Appointment" in result

    def test_reminder_with_header_style(self):
        result = EmailTemplateService.render_reminder(
            attendee_name="Eve",
            appointment_title="Prep",
            appointment_date="March 15, 2026",
            appointment_time="10:00 AM",
            duration="30 minutes",
            header_style="prep",
        )
        # The prep gradient color should be present
        assert "#059669" in result


class TestRenderCancelled:
    """Test render_cancelled()."""

    def test_basic_cancellation(self):
        result = EmailTemplateService.render_cancelled(
            attendee_name="Alice",
            appointment_title="Mortgage Review",
            appointment_date="March 20, 2026",
            appointment_time="2:00 PM",
        )
        assert "Alice" in result
        assert "Mortgage Review" in result
        assert "Cancelled" in result
        assert "<!DOCTYPE html>" in result

    def test_cancellation_with_reason(self):
        result = EmailTemplateService.render_cancelled(
            attendee_name="Bob",
            appointment_title="Consultation",
            appointment_date="March 20, 2026",
            appointment_time="2:00 PM",
            cancellation_reason="LO unavailable due to scheduling conflict",
        )
        assert "LO unavailable due to scheduling conflict" in result
        assert "Reason" in result

    def test_cancellation_with_team_member(self):
        result = EmailTemplateService.render_cancelled(
            attendee_name="Carol",
            appointment_title="Review",
            appointment_date="March 20, 2026",
            appointment_time="2:00 PM",
            team_member_name="John LO",
        )
        assert "with John LO" in result

    def test_cancellation_with_reschedule(self):
        result = EmailTemplateService.render_cancelled(
            attendee_name="Dan",
            appointment_title="Call",
            appointment_date="March 20, 2026",
            appointment_time="2:00 PM",
            reschedule_url="https://example.com/reschedule",
        )
        assert "Reschedule Now" in result


class TestRenderRescheduled:
    """Test render_rescheduled()."""

    def test_basic_rescheduled(self):
        result = EmailTemplateService.render_rescheduled(
            attendee_name="Alice",
            appointment_title="Mortgage Consultation",
            appointment_date="March 22, 2026",
            appointment_time="3:00 PM",
            duration="30 minutes",
            old_date="March 20, 2026",
            old_time="2:00 PM",
        )
        assert "Alice" in result
        assert "Updated" in result
        # Old time should be shown with strikethrough
        assert "March 20, 2026" in result
        assert "2:00 PM" in result
        # New time should be shown
        assert "March 22, 2026" in result
        assert "3:00 PM" in result
        # Should have the comparison layout
        assert "Previous" in result
        assert "New Time" in result

    def test_rescheduled_with_video_link(self):
        result = EmailTemplateService.render_rescheduled(
            attendee_name="Bob",
            appointment_title="Video Call",
            appointment_date="March 22, 2026",
            appointment_time="3:00 PM",
            duration="45 minutes",
            old_date="March 20, 2026",
            old_time="2:00 PM",
            video_link="https://meet.example.com/xyz",
        )
        assert "Join Video Call" in result

    def test_rescheduled_calendar_notice(self):
        result = EmailTemplateService.render_rescheduled(
            attendee_name="Carol",
            appointment_title="Call",
            appointment_date="March 22, 2026",
            appointment_time="3:00 PM",
            duration="30 minutes",
        )
        assert "updated calendar invite" in result.lower()


class TestRenderNoShow:
    """Test render_no_show()."""

    def test_basic_no_show(self):
        result = EmailTemplateService.render_no_show(
            attendee_name="Alice",
            appointment_title="Consultation",
            appointment_date="March 15, 2026",
            appointment_time="10:00 AM",
        )
        assert "Alice" in result
        assert "We Missed You" in result
        assert "Consultation" in result
        assert "March 15, 2026" in result

    def test_no_show_with_reschedule(self):
        result = EmailTemplateService.render_no_show(
            attendee_name="Bob",
            appointment_title="Call",
            appointment_date="March 15, 2026",
            appointment_time="10:00 AM",
            reschedule_url="https://example.com/reschedule",
        )
        assert "Reschedule Now" in result
        assert "https://example.com/reschedule" in result

    def test_no_show_with_team_member(self):
        result = EmailTemplateService.render_no_show(
            attendee_name="Carol",
            appointment_title="Review",
            appointment_date="March 15, 2026",
            appointment_time="10:00 AM",
            team_member_name="Sarah LO",
        )
        assert "with Sarah LO" in result

    def test_no_show_empathetic_tone(self):
        result = EmailTemplateService.render_no_show(
            attendee_name="Dan",
            appointment_title="Consultation",
            appointment_date="March 15, 2026",
            appointment_time="10:00 AM",
        )
        assert "Life happens" in result
        assert "completely understand" in result

    def test_no_show_opt_out_text(self):
        result = EmailTemplateService.render_no_show(
            attendee_name="Eve",
            appointment_title="Call",
            appointment_date="March 15, 2026",
            appointment_time="10:00 AM",
        )
        assert "no longer interested" in result


# ---------------------------------------------------------------------------
# Responsive design checks
# ---------------------------------------------------------------------------

class TestResponsiveDesign:
    """Verify responsive and email-client compatibility features."""

    def test_base_template_has_viewport_meta(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name="Test",
            appointment_title="Test",
            appointment_date="March 1, 2026",
            appointment_time="1:00 PM",
            duration="30 minutes",
        )
        assert 'name="viewport"' in result

    def test_base_template_has_responsive_styles(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name="Test",
            appointment_title="Test",
            appointment_date="March 1, 2026",
            appointment_time="1:00 PM",
            duration="30 minutes",
        )
        assert "@media" in result
        assert "max-width: 620px" in result

    def test_base_template_has_dark_mode_styles(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name="Test",
            appointment_title="Test",
            appointment_date="March 1, 2026",
            appointment_time="1:00 PM",
            duration="30 minutes",
        )
        assert "prefers-color-scheme: dark" in result

    def test_base_template_uses_table_layout(self):
        """Email clients render tables more reliably than divs."""
        result = EmailTemplateService.render_confirmation(
            attendee_name="Test",
            appointment_title="Test",
            appointment_date="March 1, 2026",
            appointment_time="1:00 PM",
            duration="30 minutes",
        )
        assert 'role="presentation"' in result

    def test_base_template_max_width_600(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name="Test",
            appointment_title="Test",
            appointment_date="March 1, 2026",
            appointment_time="1:00 PM",
            duration="30 minutes",
        )
        assert "max-width: 600px" in result

    def test_base_template_has_preheader(self):
        """Preheader text should be present (hidden preview text for email clients)."""
        result = EmailTemplateService.render_confirmation(
            attendee_name="Test",
            appointment_title="Consult",
            appointment_date="March 1, 2026",
            appointment_time="1:00 PM",
            duration="30 minutes",
        )
        assert "display: none" in result
        assert "March 1, 2026" in result  # preheader includes date


# ---------------------------------------------------------------------------
# None / edge-case handling
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases and None values."""

    def test_none_attendee_name(self):
        """Should not raise with None attendee_name."""
        result = EmailTemplateService.render_confirmation(
            attendee_name=None,
            appointment_title="Call",
            appointment_date="March 1, 2026",
            appointment_time="1:00 PM",
            duration="30 minutes",
        )
        assert "<!DOCTYPE html>" in result

    def test_empty_strings(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name="",
            appointment_title="",
            appointment_date="",
            appointment_time="",
            duration="",
        )
        assert "<!DOCTYPE html>" in result

    def test_no_video_link_no_button(self):
        result = EmailTemplateService.render_confirmation(
            attendee_name="Test",
            appointment_title="Test",
            appointment_date="March 1, 2026",
            appointment_time="1:00 PM",
            duration="30 minutes",
            video_link=None,
        )
        assert "Join Video Call" not in result

    def test_no_reschedule_url_no_button(self):
        result = EmailTemplateService.render_cancelled(
            attendee_name="Test",
            appointment_title="Test",
            appointment_date="March 1, 2026",
            appointment_time="1:00 PM",
            reschedule_url=None,
        )
        assert "Reschedule Now" not in result
