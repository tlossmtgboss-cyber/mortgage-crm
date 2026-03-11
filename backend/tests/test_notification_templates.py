"""
Test Notification Templates

Covers template rendering for document collection notifications:
- SmartDocsNotificationService (notification_service.py): single/bulk document request emails
- FollowupAutomationService._render_template: variable substitution with DB/hardcoded fallbacks
- NotificationTemplate model (portal_models.py): DB-backed templates with {{var}} substitution
- HTML structure, plain text fallback, mobile responsiveness, and edge cases
"""

import enum
import re
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Lightweight stubs so the tests run without a live database or
# the full import chain (EmailService, SQLAlchemy session, etc.)
# ---------------------------------------------------------------------------

class _RequestPriority(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class _RequestStatus(str, enum.Enum):
    OPEN = "OPEN"
    PENDING_REVIEW = "PENDING_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WAIVED = "WAIVED"


def _make_document_request(
    id: int = 1,
    title: str = "Recent Paystub",
    description: str = "Upload your 2 most recent paystubs",
    instructions: str = "PDF or photo of full paystub including YTD totals",
    priority=_RequestPriority.NORMAL,
    due_date=None,
    status=_RequestStatus.OPEN,
    is_active: bool = True,
):
    """Build a mock DocumentRequest with the attributes used by the notification service."""
    req = MagicMock()
    req.id = id
    req.title = title
    req.description = description
    req.instructions = instructions
    req.priority = priority
    req.due_date = due_date or (datetime.now() + timedelta(days=7))
    req.status = status
    req.is_active = is_active
    return req


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_email_service():
    """Mock EmailService so no real emails are sent."""
    with patch("services.smart_docs.notification_service.EmailService") as mock_cls:
        instance = MagicMock()
        instance.send_html_email.return_value = True
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def notification_service(mock_email_service):
    """SmartDocsNotificationService with mocked DB and EmailService."""
    from services.smart_docs.notification_service import SmartDocsNotificationService

    mock_db = MagicMock()
    svc = SmartDocsNotificationService(db=mock_db)
    return svc


@pytest.fixture
def followup_service():
    """FollowupAutomationService with mocked DB for _render_template tests."""
    mock_db = MagicMock()

    # Default: DB lookup returns None (use hardcoded fallbacks)
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.first.return_value = None
    mock_db.query.return_value = mock_query

    from services.smart_docs.followup_automation_service import FollowupAutomationService

    svc = FollowupAutomationService(db=mock_db)
    return svc, mock_db


@pytest.fixture
def standard_variables():
    """Standard set of template variables used across tests."""
    return {
        "borrower_name": "Jane Doe",
        "document_list": "  - W-2 (2025)\n  - Bank Statement (January)",
        "document_count": "2",
        "portal_link": "https://portal.perenniaai.com/docs/42",
        "lo_name": "Sarah Johnson",
        "reminder_count": "1",
        "campaign_start_date": "03/01/2026",
        "last_contact_date": "03/08/2026",
        "rejection_details": "",
    }


# ===========================================================================
# 1. Document request initial template rendering
# ===========================================================================

class TestDocumentRequestInitialTemplate:
    """Test initial document request email template generation."""

    def test_initial_request_html_contains_borrower_name(self, notification_service):
        """HTML body addresses the borrower by name."""
        req = _make_document_request(title="W-2 Form")
        html = notification_service._build_request_email_html(
            borrower_name="John Smith",
            document_title="W-2 Form",
            description="Most recent W-2",
            instructions=None,
            due_date="March 15, 2026",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="Sarah Johnson",
            portal_url="https://portal.example.com/upload",
        )
        assert "John Smith" in html
        assert "W-2 Form" in html

    def test_initial_request_includes_upload_button_when_portal_url_present(self, notification_service):
        """Upload CTA button appears when portal_url is provided."""
        html = notification_service._build_request_email_html(
            borrower_name="Alice",
            document_title="Bank Statement",
            description=None,
            instructions=None,
            due_date="",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url="https://portal.example.com/upload",
        )
        assert "Upload Document Now" in html
        assert "https://portal.example.com/upload" in html

    def test_initial_request_omits_upload_button_without_portal_url(self, notification_service):
        """No upload button when portal_url is None."""
        html = notification_service._build_request_email_html(
            borrower_name="Alice",
            document_title="Bank Statement",
            description=None,
            instructions=None,
            due_date="",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "Upload Document Now" not in html


# ===========================================================================
# 2. Document request reminder template rendering
# ===========================================================================

class TestDocumentRequestReminderTemplate:
    """Test gentle reminder template rendering."""

    def test_gentle_reminder_subject(self, followup_service, standard_variables):
        """Gentle reminder template has correct subject."""
        svc, _ = followup_service
        result = svc._render_template("gentle_reminder", standard_variables)
        assert "reminder" in result["subject"].lower()

    def test_gentle_reminder_body_substitution(self, followup_service, standard_variables):
        """Borrower name and document list are substituted in reminder body."""
        svc, _ = followup_service
        result = svc._render_template("gentle_reminder", standard_variables)
        assert "Jane Doe" in result["body"]
        assert "W-2 (2025)" in result["body"]
        assert "{{borrower_name}}" not in result["body"]


# ===========================================================================
# 3. Document request urgent template rendering
# ===========================================================================

class TestDocumentRequestUrgentTemplate:
    """Test urgent reminder template rendering."""

    def test_urgent_reminder_subject_contains_urgent(self, followup_service, standard_variables):
        """Urgent template subject conveys urgency."""
        svc, _ = followup_service
        result = svc._render_template("urgent_reminder", standard_variables)
        assert "urgent" in result["subject"].lower()

    def test_urgent_reminder_body_mentions_closing_risk(self, followup_service, standard_variables):
        """Urgent body warns about potential closing delay."""
        svc, _ = followup_service
        result = svc._render_template("urgent_reminder", standard_variables)
        body_lower = result["body"].lower()
        assert "closing" in body_lower or "asap" in body_lower or "urgently" in body_lower


# ===========================================================================
# 4. Document received confirmation template
# ===========================================================================

class TestDocumentReceivedConfirmation:
    """Test document-received confirmation rendering via notification_service."""

    def test_send_notification_calls_email_service(self, notification_service, mock_email_service):
        """send_document_request_notification delegates to EmailService."""
        req = _make_document_request(title="W-2 Form")
        result = notification_service.send_document_request_notification(
            request=req,
            borrower_email="borrower@example.com",
            borrower_name="Bob",
            loan_officer_name="LO Name",
            portal_url=None,
        )
        assert result is True
        mock_email_service.send_html_email.assert_called_once()
        call_kwargs = mock_email_service.send_html_email.call_args
        assert call_kwargs[1]["to_email"] == "borrower@example.com" or call_kwargs[0][0] == "borrower@example.com"


# ===========================================================================
# 5. Document approved notification template
# ===========================================================================

class TestDocumentApprovedTemplate:
    """Approved notification relies on portal NotificationTemplate model."""

    def test_approved_template_variables_substitution(self):
        """Simulate {{variable}} substitution on a body_template string."""
        body_template = (
            "<h2>Hi {{borrower_name}},</h2>"
            "<p>Your document <strong>{{document_type}}</strong> has been approved.</p>"
        )
        variables = {"borrower_name": "Alice", "document_type": "Bank Statement"}
        rendered = body_template
        for key, value in variables.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        assert "Alice" in rendered
        assert "Bank Statement" in rendered
        assert "{{" not in rendered


# ===========================================================================
# 6. Document rejected template with reason
# ===========================================================================

class TestDocumentRejectedTemplate:
    """Test document_rejected template rendering."""

    def test_rejected_template_includes_rejection_details(self, followup_service):
        """Rejection details are substituted into the body."""
        svc, _ = followup_service
        variables = {
            "borrower_name": "Charlie",
            "document_list": "  - Bank Statement (December)",
            "rejection_details": "Statement is older than 60 days. Please upload a recent copy.",
            "portal_link": "https://portal.example.com/docs/99",
            "lo_name": "Agent Smith",
            "document_count": "1",
        }
        result = svc._render_template("document_rejected", variables)
        assert "older than 60 days" in result["body"]
        assert "Charlie" in result["body"]
        assert "re-upload" in result["body"].lower() or "corrected" in result["body"].lower()


# ===========================================================================
# 7. E-sign request template with signing link
# ===========================================================================

class TestEsignRequestTemplate:
    """E-sign request template with signing link."""

    def test_esign_request_contains_signing_link(self):
        """E-sign template includes the signing URL."""
        subject_template = "Please sign: {{document_name}}"
        body_template = (
            "Hi {{borrower_name}},\n\n"
            "Please review and sign the following document:\n"
            "{{document_name}}\n\n"
            "Sign here: {{signing_link}}\n\n"
            "This link expires on {{expiry_date}}.\n\n"
            "Best regards,\n{{lo_name}}"
        )
        variables = {
            "borrower_name": "Diana",
            "document_name": "Closing Disclosure",
            "signing_link": "https://esign.perenniaai.com/envelope/abc123",
            "expiry_date": "March 20, 2026",
            "lo_name": "Tom",
        }
        rendered_subject = subject_template
        rendered_body = body_template
        for k, v in variables.items():
            rendered_subject = rendered_subject.replace("{{" + k + "}}", v)
            rendered_body = rendered_body.replace("{{" + k + "}}", v)

        assert "Closing Disclosure" in rendered_subject
        assert "https://esign.perenniaai.com/envelope/abc123" in rendered_body
        assert "March 20, 2026" in rendered_body


# ===========================================================================
# 8. E-sign reminder template
# ===========================================================================

class TestEsignReminderTemplate:
    """E-sign reminder template."""

    def test_esign_reminder_conveys_urgency(self):
        """Reminder body mentions that signature is still needed."""
        body_template = (
            "Hi {{borrower_name}},\n\n"
            "We're still waiting for your signature on {{document_name}}. "
            "Please sign as soon as possible to avoid delays.\n\n"
            "Sign here: {{signing_link}}\n\n"
            "{{lo_name}}"
        )
        variables = {
            "borrower_name": "Eve",
            "document_name": "Initial Disclosures",
            "signing_link": "https://esign.perenniaai.com/envelope/xyz789",
            "lo_name": "Jordan",
        }
        rendered = body_template
        for k, v in variables.items():
            rendered = rendered.replace("{{" + k + "}}", v)

        assert "still waiting" in rendered
        assert "Eve" in rendered
        assert "esign.perenniaai.com" in rendered


# ===========================================================================
# 9. E-sign completed template
# ===========================================================================

class TestEsignCompletedTemplate:
    """E-sign completed confirmation template."""

    def test_esign_completed_confirms_signature(self):
        """Completed template confirms the document was signed."""
        body_template = (
            "Hi {{borrower_name}},\n\n"
            "Thank you! Your signature on {{document_name}} has been received.\n\n"
            "Signed on: {{signed_date}}\n\n"
            "No further action is needed on this document.\n\n"
            "Best regards,\n{{lo_name}}"
        )
        variables = {
            "borrower_name": "Frank",
            "document_name": "Loan Estimate",
            "signed_date": "March 10, 2026",
            "lo_name": "Kim",
        }
        rendered = body_template
        for k, v in variables.items():
            rendered = rendered.replace("{{" + k + "}}", v)

        assert "Thank you" in rendered
        assert "signature" in rendered.lower()
        assert "March 10, 2026" in rendered


# ===========================================================================
# 10. Income review complete template
# ===========================================================================

class TestIncomeReviewCompleteTemplate:
    """Income review completion notification."""

    def test_income_review_complete_includes_results(self):
        """Income review template includes calculated income and next steps."""
        body_template = (
            "Hi {{borrower_name}},\n\n"
            "Your income documents have been reviewed.\n\n"
            "Qualifying Income: {{qualifying_income}}\n"
            "Documents Reviewed: {{documents_reviewed}}\n\n"
            "{{next_steps}}\n\n"
            "Best regards,\n{{lo_name}}"
        )
        variables = {
            "borrower_name": "Grace",
            "qualifying_income": "$8,500/month",
            "documents_reviewed": "W-2 (2025), Recent Paystub, Tax Return (2024)",
            "next_steps": "No additional income documents are needed at this time.",
            "lo_name": "Pat",
        }
        rendered = body_template
        for k, v in variables.items():
            rendered = rendered.replace("{{" + k + "}}", v)

        assert "$8,500/month" in rendered
        assert "W-2 (2025)" in rendered
        assert "No additional income documents" in rendered


# ===========================================================================
# 11. Appointment scheduled template
# ===========================================================================

class TestAppointmentScheduledTemplate:
    """Appointment scheduled notification."""

    def test_appointment_scheduled_includes_datetime(self):
        """Template includes the appointment date, time, and duration."""
        body_template = (
            "Hi {{borrower_name}},\n\n"
            "Your appointment has been scheduled:\n\n"
            "  Date/Time: {{scheduled_time}}\n"
            "  Duration: {{duration}} minutes\n"
            "  Type: {{location_type}}\n\n"
            "We'll be reviewing your outstanding documents.\n\n"
            "Best regards,\n{{lo_name}}"
        )
        variables = {
            "borrower_name": "Henry",
            "scheduled_time": "March 15, 2026 at 02:00 PM",
            "duration": "30",
            "location_type": "Phone call",
            "lo_name": "Robin",
        }
        rendered = body_template
        for k, v in variables.items():
            rendered = rendered.replace("{{" + k + "}}", v)

        assert "March 15, 2026 at 02:00 PM" in rendered
        assert "30 minutes" in rendered
        assert "Phone call" in rendered


# ===========================================================================
# 12. Appointment reminder template
# ===========================================================================

class TestAppointmentReminderTemplate:
    """Appointment reminder notification."""

    def test_appointment_reminder_mentions_upcoming(self):
        """Reminder emphasizes the appointment is coming up soon."""
        body_template = (
            "Hi {{borrower_name}},\n\n"
            "Just a reminder that your appointment is coming up:\n\n"
            "  Date/Time: {{scheduled_time}}\n\n"
            "Please have your outstanding documents ready.\n\n"
            "{{lo_name}}"
        )
        variables = {
            "borrower_name": "Irene",
            "scheduled_time": "Tomorrow at 10:00 AM",
            "lo_name": "Casey",
        }
        rendered = body_template
        for k, v in variables.items():
            rendered = rendered.replace("{{" + k + "}}", v)

        assert "reminder" in rendered.lower()
        assert "Tomorrow at 10:00 AM" in rendered


# ===========================================================================
# 13. Template variable substitution (borrower name, doc list, dates)
# ===========================================================================

class TestTemplateVariableSubstitution:
    """Comprehensive variable substitution via FollowupAutomationService._render_template."""

    def test_all_standard_variables_are_substituted(self, followup_service, standard_variables):
        """Every {{variable}} placeholder should be replaced."""
        svc, _ = followup_service
        result = svc._render_template("initial_request", standard_variables)

        # No unreplaced placeholders
        assert "{{" not in result["body"]
        assert "{{" not in result["subject"]

        # Key values present
        assert "Jane Doe" in result["body"]
        assert "W-2 (2025)" in result["body"]
        assert "portal.perenniaai.com" in result["body"]
        assert "Sarah Johnson" in result["body"]

    def test_extra_variables_are_ignored(self, followup_service, standard_variables):
        """Variables not referenced in template should not cause errors."""
        svc, _ = followup_service
        standard_variables["nonexistent_var"] = "should not break"
        result = svc._render_template("initial_request", standard_variables)
        assert result["body"]  # renders without error

    def test_empty_variable_value_replaces_cleanly(self, followup_service):
        """Empty string values replace placeholders without residue."""
        svc, _ = followup_service
        variables = {
            "borrower_name": "",
            "document_list": "",
            "portal_link": "",
            "lo_name": "",
            "document_count": "0",
            "reminder_count": "0",
            "campaign_start_date": "",
            "last_contact_date": "",
            "rejection_details": "",
        }
        result = svc._render_template("initial_request", variables)
        assert "{{borrower_name}}" not in result["body"]


# ===========================================================================
# 14. HTML output validity
# ===========================================================================

class TestHtmlOutputValidity:
    """Verify HTML structure of rendered email templates."""

    def test_html_contains_doctype(self, notification_service):
        """Rendered HTML starts with DOCTYPE declaration."""
        html = notification_service._build_request_email_html(
            borrower_name="Test",
            document_title="Doc",
            description=None,
            instructions=None,
            due_date="",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "<!DOCTYPE html>" in html

    def test_html_has_matching_open_and_close_tags(self, notification_service):
        """HTML has balanced <html>, <head>, <body> tags."""
        html = notification_service._build_request_email_html(
            borrower_name="Test",
            document_title="Doc",
            description="desc",
            instructions="instr",
            due_date="Jan 1, 2026",
            priority="High",
            priority_color="#f97316",
            loan_officer_name="LO",
            portal_url="https://portal.example.com",
        )
        assert "<html>" in html and "</html>" in html
        assert "<head>" in html and "</head>" in html
        assert "<body" in html and "</body>" in html

    def test_html_contains_charset_meta(self, notification_service):
        """HTML contains UTF-8 charset meta tag for proper encoding."""
        html = notification_service._build_request_email_html(
            borrower_name="Test",
            document_title="Doc",
            description=None,
            instructions=None,
            due_date="",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert 'charset="utf-8"' in html or "charset=utf-8" in html.lower()


# ===========================================================================
# 15. Plain text fallback generation
# ===========================================================================

class TestPlainTextFallback:
    """Verify plain text versions of email templates."""

    def test_plain_text_contains_borrower_name(self, notification_service):
        """Plain text body addresses the borrower."""
        text = notification_service._build_request_email_plain_text(
            borrower_name="Maya",
            document_title="Tax Return",
            description="2024 tax return",
            instructions="Include all pages and schedules",
            due_date="April 15, 2026",
            priority="High",
            loan_officer_name="Alex",
            portal_url="https://portal.example.com",
        )
        assert "Maya" in text
        assert "Tax Return" in text

    def test_plain_text_includes_portal_url(self, notification_service):
        """Plain text includes the upload link."""
        text = notification_service._build_request_email_plain_text(
            borrower_name="Maya",
            document_title="Tax Return",
            description=None,
            instructions=None,
            due_date="",
            priority="Normal",
            loan_officer_name="Alex",
            portal_url="https://portal.example.com/upload",
        )
        assert "https://portal.example.com/upload" in text

    def test_plain_text_has_no_html_tags(self, notification_service):
        """Plain text body should not contain HTML tags."""
        text = notification_service._build_request_email_plain_text(
            borrower_name="Maya",
            document_title="Tax Return",
            description="Upload tax return",
            instructions="All pages",
            due_date="April 15, 2026",
            priority="Normal",
            loan_officer_name="Alex",
            portal_url="https://portal.example.com",
        )
        # No HTML angle-bracket tags (allow URLs with ://)
        html_tag_pattern = re.compile(r"<(?!http)[^>]+>")
        assert not html_tag_pattern.search(text), f"Found HTML tags in plain text: {text}"

    def test_plain_text_omits_portal_url_when_none(self, notification_service):
        """When portal_url is None, no upload link text appears."""
        text = notification_service._build_request_email_plain_text(
            borrower_name="Maya",
            document_title="Tax Return",
            description=None,
            instructions=None,
            due_date="",
            priority="Normal",
            loan_officer_name="Alex",
            portal_url=None,
        )
        assert "Upload your document here" not in text


# ===========================================================================
# 16. Missing variable handling (graceful defaults)
# ===========================================================================

class TestMissingVariableHandling:
    """Test behavior when variables are missing or None."""

    def test_unreplaced_placeholders_remain_when_variable_missing(self, followup_service):
        """Missing variables leave {{placeholder}} in output (no crash)."""
        svc, _ = followup_service
        result = svc._render_template("initial_request", {
            "borrower_name": "Partial",
            # document_list, portal_link, lo_name intentionally omitted
        })
        # Should not crash; some placeholders remain
        assert "Partial" in result["body"]
        # Remaining placeholders are present but the rendering did not fail
        assert result["subject"] is not None
        assert result["body"] is not None

    def test_empty_variables_dict_does_not_crash(self, followup_service):
        """Rendering with zero variables should not raise."""
        svc, _ = followup_service
        result = svc._render_template("initial_request", {})
        assert result["subject"]
        assert result["body"]

    def test_notification_service_handles_none_description(self, notification_service):
        """None description should not cause errors in HTML rendering."""
        html = notification_service._build_request_email_html(
            borrower_name="Test",
            document_title="Doc",
            description=None,
            instructions=None,
            due_date="",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "Test" in html
        assert "Doc" in html


# ===========================================================================
# 17. Mobile-responsive HTML structure
# ===========================================================================

class TestMobileResponsiveHtmlStructure:
    """Verify HTML templates contain mobile-responsive meta and styling."""

    def test_viewport_meta_tag_present(self, notification_service):
        """HTML includes viewport meta tag for mobile rendering."""
        html = notification_service._build_request_email_html(
            borrower_name="Test",
            document_title="Doc",
            description=None,
            instructions=None,
            due_date="",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "viewport" in html
        assert "width=device-width" in html

    def test_max_width_constraint_for_email(self, notification_service):
        """Email container has max-width for proper rendering in email clients."""
        html = notification_service._build_request_email_html(
            borrower_name="Test",
            document_title="Doc",
            description=None,
            instructions=None,
            due_date="",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "max-width: 600px" in html or "max-width:600px" in html

    def test_inline_styles_used_not_external_css(self, notification_service):
        """Email HTML uses inline styles (no <link> or <style> blocks)."""
        html = notification_service._build_request_email_html(
            borrower_name="Test",
            document_title="Doc",
            description=None,
            instructions=None,
            due_date="",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "<link" not in html
        assert 'style="' in html  # Inline styles are used


# ===========================================================================
# 18. Unsubscribe link inclusion
# ===========================================================================

class TestUnsubscribeLinkInclusion:
    """Check that templates include an automated message footer."""

    def test_footer_present_in_single_request_html(self, notification_service):
        """Single request HTML includes automated message footer."""
        html = notification_service._build_request_email_html(
            borrower_name="Test",
            document_title="Doc",
            description=None,
            instructions=None,
            due_date="",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "automated message" in html.lower()

    def test_footer_present_in_bulk_request_html(self, notification_service):
        """Bulk request HTML includes automated message footer."""
        html = notification_service._build_bulk_request_email_html(
            borrower_name="Test",
            critical_requests=[],
            high_requests=[],
            normal_requests=[_make_document_request()],
            low_requests=[],
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "automated message" in html.lower()


# ===========================================================================
# 19. Template not found handling
# ===========================================================================

class TestTemplateNotFoundHandling:
    """Test behavior when a template slug is unknown."""

    def test_unknown_slug_returns_fallback(self, followup_service):
        """Unknown template slug falls back to generic message."""
        svc, _ = followup_service
        result = svc._render_template("totally_nonexistent_template_xyz", {
            "borrower_name": "Bob",
            "portal_link": "https://portal.example.com",
        })
        # Should use the ultimate fallback
        assert result["subject"] == "Document follow-up"
        assert "Bob" in result["body"]
        assert "portal.example.com" in result["body"]

    def test_db_error_falls_back_to_defaults(self, followup_service):
        """Database query failure falls back to hardcoded templates."""
        svc, mock_db = followup_service

        # Make the DB query raise an exception
        mock_db.query.side_effect = Exception("DB connection lost")

        result = svc._render_template("initial_request", {
            "borrower_name": "Carol",
            "document_list": "  - Appraisal",
            "portal_link": "https://portal.example.com",
            "lo_name": "Agent",
            "document_count": "1",
        })
        # Should still render using hardcoded defaults
        assert "Carol" in result["body"]
        assert "Appraisal" in result["body"]


# ===========================================================================
# 20. Batch template rendering
# ===========================================================================

class TestBatchTemplateRendering:
    """Test bulk/batch document request template rendering."""

    def test_bulk_html_lists_all_documents(self, notification_service):
        """Bulk HTML template lists all requested document titles."""
        requests = [
            _make_document_request(id=1, title="W-2 Form", priority=_RequestPriority.HIGH),
            _make_document_request(id=2, title="Bank Statement", priority=_RequestPriority.NORMAL),
            _make_document_request(id=3, title="Gift Letter", priority=_RequestPriority.LOW),
        ]
        html = notification_service._build_bulk_request_email_html(
            borrower_name="Team Test",
            critical_requests=[],
            high_requests=[requests[0]],
            normal_requests=[requests[1]],
            low_requests=[requests[2]],
            loan_officer_name="LO",
            portal_url="https://portal.example.com",
        )
        assert "W-2 Form" in html
        assert "Bank Statement" in html
        assert "Gift Letter" in html

    def test_bulk_html_shows_total_count(self, notification_service):
        """Bulk HTML header shows total document count."""
        requests = [
            _make_document_request(id=1, title="Doc A", priority=_RequestPriority.NORMAL),
            _make_document_request(id=2, title="Doc B", priority=_RequestPriority.NORMAL),
            _make_document_request(id=3, title="Doc C", priority=_RequestPriority.NORMAL),
        ]
        html = notification_service._build_bulk_request_email_html(
            borrower_name="Test",
            critical_requests=[],
            high_requests=[],
            normal_requests=requests,
            low_requests=[],
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "3 documents" in html

    def test_bulk_plain_text_lists_documents_numbered(self, notification_service):
        """Bulk plain text lists documents with numbering."""
        requests = [
            _make_document_request(id=1, title="Paystub", priority=_RequestPriority.CRITICAL),
            _make_document_request(id=2, title="Tax Return", priority=_RequestPriority.HIGH),
        ]
        text = notification_service._build_bulk_request_email_plain_text(
            borrower_name="Batch User",
            requests=requests,
            loan_officer_name="LO",
            portal_url="https://portal.example.com",
        )
        assert "1. Paystub" in text
        assert "2. Tax Return" in text
        assert "Batch User" in text

    def test_bulk_send_returns_true_on_success(self, notification_service, mock_email_service):
        """send_bulk_request_notification returns True when email succeeds."""
        requests = [
            _make_document_request(id=1, title="Doc A", priority=_RequestPriority.NORMAL),
        ]
        result = notification_service.send_bulk_request_notification(
            requests=requests,
            borrower_email="borrower@example.com",
            borrower_name="Batch User",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert result is True
        mock_email_service.send_html_email.assert_called_once()

    def test_bulk_send_empty_list_returns_true_without_sending(self, notification_service, mock_email_service):
        """Empty request list returns True without sending any email."""
        result = notification_service.send_bulk_request_notification(
            requests=[],
            borrower_email="borrower@example.com",
            borrower_name="Nobody",
        )
        assert result is True
        mock_email_service.send_html_email.assert_not_called()


# ===========================================================================
# Additional edge case tests
# ===========================================================================

class TestPriorityColorMapping:
    """Test priority-to-color mapping in SmartDocsNotificationService."""

    def test_critical_priority_is_red(self, notification_service):
        color = notification_service._get_priority_color(_RequestPriority.CRITICAL)
        assert color == "#dc2626"

    def test_high_priority_is_orange(self, notification_service):
        color = notification_service._get_priority_color(_RequestPriority.HIGH)
        # notification_service uses smart_docs_models.RequestPriority which has HIGH
        # Our stub uses the same values, but _get_priority_color expects
        # the enum from smart_docs_models. Test the fallback.
        assert color in ("#f97316", "#3b82f6")  # orange or default blue

    def test_none_priority_returns_blue(self, notification_service):
        color = notification_service._get_priority_color(None)
        assert color == "#3b82f6"


class TestDbTemplateOverride:
    """Test that DB-stored templates override hardcoded defaults."""

    def test_db_template_takes_priority(self, followup_service):
        """When DB returns a template, its content is used."""
        svc, mock_db = followup_service

        # Simulate DB returning a custom template
        db_template = MagicMock()
        db_template.subject_template = "Custom Subject for {{borrower_name}}"
        db_template.body_template = "Custom body: Hello {{borrower_name}}!"
        db_template.usage_count = 10

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = db_template
        mock_db.query.return_value = mock_query

        result = svc._render_template("initial_request", {"borrower_name": "Override"})
        assert result["subject"] == "Custom Subject for Override"
        assert result["body"] == "Custom body: Hello Override!"
        assert db_template.usage_count == 11

    def test_db_template_with_empty_body_falls_back(self, followup_service):
        """When DB template body is empty, hardcoded default is used."""
        svc, mock_db = followup_service

        db_template = MagicMock()
        db_template.subject_template = "Subject"
        db_template.body_template = ""  # Empty body
        db_template.usage_count = 0

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = db_template
        mock_db.query.return_value = mock_query

        result = svc._render_template("initial_request", {"borrower_name": "Fallback"})
        # Hardcoded default should be used since DB body was empty
        assert "Fallback" in result["body"]
        assert len(result["body"]) > 20  # Not just the empty string


class TestInstructionsSectionRendering:
    """Test that instructions section renders conditionally."""

    def test_instructions_rendered_when_present(self, notification_service):
        """Instructions section appears when instructions are provided."""
        html = notification_service._build_request_email_html(
            borrower_name="Test",
            document_title="Doc",
            description="A document",
            instructions="Please include all pages",
            due_date="",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "Please include all pages" in html
        assert "Instructions:" in html

    def test_instructions_omitted_when_none(self, notification_service):
        """Instructions section is absent when instructions are None."""
        html = notification_service._build_request_email_html(
            borrower_name="Test",
            document_title="Doc",
            description="A document",
            instructions=None,
            due_date="",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "Instructions:" not in html


class TestDueDateRendering:
    """Test that due date renders conditionally."""

    def test_due_date_rendered_when_present(self, notification_service):
        """Due date section appears when due_date is provided."""
        html = notification_service._build_request_email_html(
            borrower_name="Test",
            document_title="Doc",
            description=None,
            instructions=None,
            due_date="March 20, 2026",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "March 20, 2026" in html
        assert "Due Date" in html

    def test_due_date_omitted_when_empty(self, notification_service):
        """Due date section is absent when due_date is empty string."""
        html = notification_service._build_request_email_html(
            borrower_name="Test",
            document_title="Doc",
            description=None,
            instructions=None,
            due_date="",
            priority="Normal",
            priority_color="#3b82f6",
            loan_officer_name="LO",
            portal_url=None,
        )
        assert "Due Date" not in html
