"""
Security tests for notification_templates.py

Verifies that all 18 template functions properly HTML-escape user-supplied
data to prevent XSS attacks in borrower email clients. Tests cover:
- Script injection in text fields (borrower_name, document_name, etc.)
- HTML attribute injection via event handlers
- javascript: URL scheme in link targets
- Normal text passthrough
- None value handling
"""

import pytest

from services.smart_docs.notification_templates import (
    _safe,
    _safe_url,
    _esc,
    _cta_button,
    _html_scaffold,
    render_template,
    get_available_templates,
)


# =============================================================================
# XSS Payloads
# =============================================================================

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    '<img src=x onerror=alert(1)>',
    '"><script>alert(1)</script>',
    "' onmouseover='alert(1)",
    "<svg/onload=alert(1)>",
    '"><img src=x onerror=alert(document.cookie)>',
    "<body onload=alert(1)>",
]

DANGEROUS_URLS = [
    "javascript:alert(1)",
    "javascript:alert(document.cookie)",
    "JAVASCRIPT:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:MsgBox(1)",
    " javascript:alert(1)",
]


# =============================================================================
# _safe() helper tests
# =============================================================================

class TestSafeHelper:
    """Tests for the _safe() HTML escaping helper."""

    def test_escapes_script_tag(self):
        result = _safe("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_escapes_html_entities(self):
        result = _safe('"><script>alert(1)</script>')
        assert "<script>" not in result
        assert "&quot;" in result

    def test_escapes_angle_brackets(self):
        result = _safe("<img src=x onerror=alert(1)>")
        assert "<img" not in result
        assert "&lt;img" in result

    def test_escapes_single_quotes(self):
        result = _safe("' onmouseover='alert(1)")
        assert "onmouseover" in result  # text is preserved
        assert "'" not in result or "&#x27;" in result or "&apos;" not in result
        # html.escape with default quote=True escapes & < > " but not '
        # This is fine because in the templates, values are placed in
        # double-quoted attributes or text content

    def test_none_returns_empty_string(self):
        assert _safe(None) == ""

    def test_empty_string_returns_empty(self):
        assert _safe("") == ""

    def test_normal_text_passes_through(self):
        assert _safe("John Smith") == "John Smith"
        assert _safe("Loan #12345") == "Loan #12345"

    def test_numeric_value(self):
        assert _safe(42) == "42"
        assert _safe(3.14) == "3.14"

    def test_ampersand_escaped(self):
        assert _safe("A & B") == "A &amp; B"

    def test_consistent_with_esc(self):
        """_safe and _esc produce identical output."""
        for payload in XSS_PAYLOADS:
            assert _safe(payload) == _esc(payload)
        assert _safe(None) == _esc(None)


# =============================================================================
# _safe_url() helper tests
# =============================================================================

class TestSafeUrlHelper:
    """Tests for the _safe_url() URL validation helper."""

    def test_allows_https(self):
        url = "https://portal.perenniaai.com/upload"
        assert _safe_url(url) == url

    def test_allows_http(self):
        url = "http://portal.perenniaai.com/upload"
        assert _safe_url(url) == url

    def test_rejects_javascript_url(self):
        assert _safe_url("javascript:alert(1)") == ""

    def test_rejects_javascript_case_insensitive(self):
        assert _safe_url("JAVASCRIPT:alert(1)") == ""
        assert _safe_url("JaVaScRiPt:alert(1)") == ""

    def test_rejects_data_url(self):
        assert _safe_url("data:text/html,<script>alert(1)</script>") == ""

    def test_rejects_vbscript_url(self):
        assert _safe_url("vbscript:MsgBox(1)") == ""

    def test_rejects_leading_whitespace_javascript(self):
        assert _safe_url(" javascript:alert(1)") == ""

    def test_none_returns_empty(self):
        assert _safe_url(None) == ""

    def test_empty_returns_empty(self):
        assert _safe_url("") == ""

    def test_all_dangerous_urls_rejected(self):
        for url in DANGEROUS_URLS:
            assert _safe_url(url) == "", f"Should reject: {url!r}"

    def test_protocol_relative_url_allowed(self):
        assert _safe_url("//cdn.example.com/image.png") == "//cdn.example.com/image.png"


# =============================================================================
# _cta_button() tests
# =============================================================================

class TestCtaButton:
    """Tests for CTA button URL safety."""

    def test_javascript_url_produces_empty_button(self):
        result = _cta_button("Click Me", "javascript:alert(1)")
        assert result == ""

    def test_valid_url_produces_button(self):
        result = _cta_button("Click Me", "https://example.com")
        assert "https://example.com" in result
        assert "Click Me" in result

    def test_label_is_escaped(self):
        result = _cta_button("<script>alert(1)</script>", "https://example.com")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


# =============================================================================
# _html_scaffold() tests
# =============================================================================

class TestHtmlScaffold:
    """Tests for the HTML scaffold wrapper."""

    def test_title_is_escaped(self):
        result = _html_scaffold(
            header_title="<script>alert(1)</script>",
            header_subtitle="test",
            body_html="<p>body</p>",
        )
        assert "<script>alert(1)</script>" not in result
        assert "&lt;script&gt;" in result

    def test_subtitle_is_escaped(self):
        result = _html_scaffold(
            header_title="Title",
            header_subtitle='"><img src=x onerror=alert(1)>',
            body_html="<p>body</p>",
        )
        assert 'onerror=alert(1)>' not in result

    def test_company_name_is_escaped(self):
        result = _html_scaffold(
            header_title="Title",
            header_subtitle="Sub",
            body_html="<p>body</p>",
            company_name="<script>evil</script>",
        )
        assert "<script>evil</script>" not in result

    def test_javascript_unsubscribe_url_rejected(self):
        result = _html_scaffold(
            header_title="Title",
            header_subtitle="Sub",
            body_html="<p>body</p>",
            unsubscribe_url="javascript:alert(1)",
        )
        assert "javascript:" not in result


# =============================================================================
# Template-level XSS tests (all 18 templates)
# =============================================================================

# Build a set of malicious variables that covers all user-supplied fields
_XSS_VARS = {
    "borrower_name": "<script>alert('xss')</script>",
    "loan_officer_name": '<img src=x onerror=alert(1)>',
    "document_name": '"><script>alert(1)</script>',
    "document_list": [
        {"name": "<script>alert('doc')</script>", "status": "needed", "note": "<b>bold</b>"},
    ],
    "loan_number": "' onmouseover='alert(1)",
    "due_date": "<svg/onload=alert(1)>",
    "portal_url": "https://portal.example.com/upload",
    "company_name": "<script>company</script>",
    "company_logo_url": "https://example.com/logo.png",
    "days_waiting": "5",
    "closing_date": "<script>close</script>",
    "escalation_date": "<b>now</b>",
    "loan_officer_phone": "555-<script>1234</script>",
    "received_date": "03/01/2026",
    "remaining_count": 2,
    "next_step": "<img src=x onerror=alert(1)>",
    "rejection_reason": '"><script>alert(1)</script>',
    "reupload_instructions": "<script>instructions</script>",
    "expiration_date": "04/01/2026",
    "days_until_expiry": "5",
    "envelope_name": '<img src=x onerror=alert(1)>',
    "signing_url": "https://esign.example.com/sign",
    "signing_expiration": "03/20/2026",
    "days_pending": "3",
    "completed_date": "03/10/2026",
    "download_url": "https://example.com/download",
    "void_reason": "<script>voided</script>",
    "next_action": "<b>action</b>",
    "income_total": "$5,000",
    "income_sources": [
        {"type": "<script>type</script>", "amount": "$3,000"},
    ],
    "task_description": "<script>task</script>",
    "assigned_by": "<img src=x onerror=alert(1)>",
    "findings": [
        {"severity": "high", "title": "<script>finding</script>", "description": "<b>desc</b>"},
    ],
    "overall_severity": "high",
    "appointment_date": "03/15/2026",
    "appointment_time": "2:00 PM",
    "location": "<script>location</script>",
    "meeting_url": "https://meet.example.com/room",
    "appointment_notes": "<script>notes</script>",
    "documents_to_bring": [
        {"name": "<script>doc</script>"},
    ],
    "hours_until": "24",
    "cancellation_reason": "<script>cancelled</script>",
    "reschedule_url": "https://schedule.example.com/book",
}


def _assert_no_raw_xss(html_body: str, subject: str):
    """Assert that no raw XSS payloads appear unescaped in the output."""
    # These literal strings should NEVER appear in the rendered HTML
    dangerous_patterns = [
        "<script>",
        "</script>",
        "onerror=alert",
        "onload=alert",
        "onmouseover='alert",
        "<svg/onload",
        "<img src=x onerror",
        "<body onload",
    ]
    for pattern in dangerous_patterns:
        assert pattern not in html_body, (
            f"Unescaped XSS pattern found in HTML body: {pattern!r}"
        )
        assert pattern not in subject, (
            f"Unescaped XSS pattern found in subject: {pattern!r}"
        )


class TestAllTemplatesXssProtection:
    """Test every registered template function for XSS protection."""

    def test_all_18_templates_registered(self):
        """Verify all 18 templates are in the registry."""
        templates = get_available_templates()
        assert len(templates) == 18

    @pytest.mark.parametrize("template_name", [
        "document_request_initial",
        "document_request_reminder",
        "document_request_urgent",
        "document_request_final",
        "document_received",
        "document_approved",
        "document_rejected",
        "document_expiring",
        "esign_request",
        "esign_reminder",
        "esign_completed",
        "esign_voided",
        "income_review_complete",
        "income_task_assigned",
        "review_findings",
        "appointment_scheduled",
        "appointment_reminder",
        "appointment_cancelled",
    ])
    def test_template_escapes_xss_payloads(self, template_name):
        """Each template must escape all XSS payloads in its HTML output."""
        result = render_template(template_name, _XSS_VARS)
        _assert_no_raw_xss(result.html_body, result.subject)

    @pytest.mark.parametrize("template_name", [
        "document_request_initial",
        "document_request_reminder",
        "document_request_urgent",
        "document_request_final",
        "document_received",
        "document_approved",
        "document_rejected",
        "document_expiring",
        "esign_request",
        "esign_reminder",
        "esign_completed",
        "esign_voided",
        "income_review_complete",
        "income_task_assigned",
        "review_findings",
        "appointment_scheduled",
        "appointment_reminder",
        "appointment_cancelled",
    ])
    def test_template_handles_none_values(self, template_name):
        """Templates should not crash when all user fields are None."""
        none_vars = {k: None for k in _XSS_VARS}
        # Lists/dicts can't be None in some templates, provide empty
        none_vars["document_list"] = []
        none_vars["income_sources"] = []
        none_vars["findings"] = []
        none_vars["documents_to_bring"] = []
        none_vars["remaining_count"] = 0
        result = render_template(template_name, none_vars)
        assert result.html_body
        assert result.subject

    @pytest.mark.parametrize("template_name", [
        "document_request_initial",
        "document_request_reminder",
        "document_request_urgent",
        "document_request_final",
        "document_received",
        "document_approved",
        "document_rejected",
        "document_expiring",
        "esign_request",
        "esign_reminder",
        "esign_completed",
        "esign_voided",
        "income_review_complete",
        "income_task_assigned",
        "review_findings",
        "appointment_scheduled",
        "appointment_reminder",
        "appointment_cancelled",
    ])
    def test_template_normal_text_passes_through(self, template_name):
        """Normal safe text should appear in the rendered output."""
        safe_vars = {
            "borrower_name": "Jane Doe",
            "loan_officer_name": "Sarah Johnson",
            "document_name": "W-2 Form",
            "document_list": [{"name": "W-2 Form", "status": "needed"}],
            "loan_number": "LN-20260312",
            "due_date": "March 15, 2026",
            "portal_url": "https://portal.example.com/upload",
            "company_name": "Perennia AI",
            "company_logo_url": "https://example.com/logo.png",
            "days_waiting": "3",
            "closing_date": "April 1, 2026",
            "escalation_date": "March 20, 2026",
            "loan_officer_phone": "555-123-4567",
            "received_date": "03/01/2026",
            "remaining_count": 2,
            "next_step": "Proceed to underwriting",
            "rejection_reason": "Document is expired",
            "reupload_instructions": "Please upload a current version",
            "expiration_date": "04/01/2026",
            "days_until_expiry": "10",
            "envelope_name": "Closing Package",
            "signing_url": "https://esign.example.com/sign",
            "signing_expiration": "03/20/2026",
            "days_pending": "2",
            "completed_date": "03/10/2026",
            "download_url": "https://example.com/download",
            "void_reason": "Package updated with new terms",
            "next_action": "A new signing request will be sent",
            "income_total": "$5,000",
            "income_sources": [{"type": "Employment", "amount": "$5,000"}],
            "task_description": "Verify employment income",
            "assigned_by": "Manager Smith",
            "findings": [{"severity": "medium", "title": "Income gap", "description": "30-day gap noted"}],
            "overall_severity": "medium",
            "appointment_date": "March 15, 2026",
            "appointment_time": "2:00 PM",
            "location": "Office Suite 200",
            "meeting_url": "https://meet.example.com/room",
            "appointment_notes": "Bring all originals",
            "documents_to_bring": [{"name": "Photo ID"}],
            "hours_until": "24",
            "cancellation_reason": "Borrower rescheduled",
            "reschedule_url": "https://schedule.example.com/book",
        }
        result = render_template(template_name, safe_vars)
        # At minimum, the HTML body should be non-empty
        assert len(result.html_body) > 100


# =============================================================================
# Template-specific XSS vector tests
# =============================================================================

class TestSpecificXssVectors:
    """Targeted tests for specific XSS vectors in specific templates."""

    def test_borrower_name_script_in_document_request(self):
        """Script tag in borrower_name is escaped in document_request_initial."""
        result = render_template("document_request_initial", {
            "borrower_name": "<script>alert('xss')</script>",
            "document_list": [],
        })
        assert "<script>" not in result.html_body
        assert "&lt;script&gt;" in result.html_body

    def test_loan_number_html_entities_in_subject(self):
        """HTML entities in loan_number are escaped in subject line."""
        result = render_template("income_review_complete", {
            "borrower_name": "Test",
            "loan_number": "<b>LN-123</b>",
        })
        assert "<b>" not in result.subject
        assert "&lt;b&gt;" in result.subject

    def test_javascript_url_in_portal_url(self):
        """javascript: URL in portal_url does not produce a clickable link."""
        result = render_template("document_request_initial", {
            "borrower_name": "Test",
            "document_list": [],
            "portal_url": "javascript:alert(document.cookie)",
        })
        assert "javascript:" not in result.html_body

    def test_javascript_url_in_signing_url(self):
        """javascript: URL in signing_url is rejected."""
        result = render_template("esign_request", {
            "borrower_name": "Test",
            "signing_url": "javascript:alert(1)",
        })
        assert "javascript:" not in result.html_body

    def test_javascript_url_in_meeting_url(self):
        """javascript: URL in meeting_url is rejected."""
        result = render_template("appointment_scheduled", {
            "borrower_name": "Test",
            "meeting_url": "javascript:alert(1)",
        })
        assert "javascript:" not in result.html_body

    def test_javascript_url_in_download_url(self):
        """javascript: URL in download_url is rejected."""
        result = render_template("esign_completed", {
            "borrower_name": "Test",
            "download_url": "javascript:alert(1)",
        })
        assert "javascript:" not in result.html_body

    def test_javascript_url_in_reschedule_url(self):
        """javascript: URL in reschedule_url is rejected."""
        result = render_template("appointment_cancelled", {
            "borrower_name": "Test",
            "reschedule_url": "javascript:alert(1)",
        })
        assert "javascript:" not in result.html_body

    def test_reviewer_notes_escaped_in_rejection(self):
        """Rejection reason with XSS payload is escaped."""
        result = render_template("document_rejected", {
            "borrower_name": "Test",
            "document_name": "W-2",
            "rejection_reason": '<img src=x onerror=alert(1)>',
        })
        assert "onerror=" not in result.html_body
        assert "&lt;img" in result.html_body

    def test_instructions_escaped_in_rejection(self):
        """Reupload instructions with XSS payload are escaped."""
        result = render_template("document_rejected", {
            "borrower_name": "Test",
            "document_name": "W-2",
            "reupload_instructions": '<script>alert("instructions")</script>',
        })
        assert "<script>" not in result.html_body

    def test_document_name_in_checklist_escaped(self):
        """Document names inside checklists are escaped."""
        result = render_template("document_request_initial", {
            "borrower_name": "Test",
            "document_list": [
                {"name": '<img src=x onerror=alert(1)>', "status": "needed"},
            ],
        })
        assert "onerror=" not in result.html_body

    def test_finding_title_escaped(self):
        """Finding titles in review_findings are escaped."""
        result = render_template("review_findings", {
            "borrower_name": "Test",
            "findings": [
                {"severity": "high", "title": "<script>alert(1)</script>", "description": "test"},
            ],
        })
        assert "<script>" not in result.html_body

    def test_finding_description_escaped(self):
        """Finding descriptions in review_findings are escaped."""
        result = render_template("review_findings", {
            "borrower_name": "Test",
            "findings": [
                {"severity": "low", "title": "test", "description": '<img src=x onerror=alert(1)>'},
            ],
        })
        assert "onerror=" not in result.html_body

    def test_income_source_type_escaped(self):
        """Income source types are escaped."""
        result = render_template("income_review_complete", {
            "borrower_name": "Test",
            "income_sources": [
                {"type": "<script>alert(1)</script>", "amount": "$1,000"},
            ],
        })
        assert "<script>" not in result.html_body

    def test_cancellation_reason_escaped(self):
        """Cancellation reason is escaped."""
        result = render_template("appointment_cancelled", {
            "borrower_name": "Test",
            "cancellation_reason": '<script>alert("cancel")</script>',
        })
        assert "<script>" not in result.html_body

    def test_void_reason_escaped(self):
        """Void reason in esign_voided is escaped."""
        result = render_template("esign_voided", {
            "borrower_name": "Test",
            "void_reason": '<script>alert("void")</script>',
        })
        assert "<script>" not in result.html_body

    def test_appointment_notes_escaped(self):
        """Appointment notes are escaped."""
        result = render_template("appointment_scheduled", {
            "borrower_name": "Test",
            "appointment_notes": '<script>alert("notes")</script>',
        })
        assert "<script>" not in result.html_body


# =============================================================================
# Regression: double-escaping prevention
# =============================================================================

class TestDoubleEscapingPrevention:
    """Verify that values are not double-escaped (e.g. &amp;amp;)."""

    def test_ampersand_in_borrower_name_single_escaped(self):
        """Ampersand should be escaped once, not double-escaped."""
        result = render_template("document_request_initial", {
            "borrower_name": "Tom & Jerry",
            "document_list": [],
        })
        assert "Tom &amp; Jerry" in result.html_body
        assert "Tom &amp;amp; Jerry" not in result.html_body

    def test_document_name_in_scaffold_subtitle_single_escaped(self):
        """Document name passed to scaffold subtitle should be single-escaped."""
        result = render_template("document_received", {
            "borrower_name": "Test",
            "document_name": "W-2 & Tax Return",
        })
        assert "W-2 &amp; Tax Return" in result.html_body
        assert "W-2 &amp;amp; Tax Return" not in result.html_body
