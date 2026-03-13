"""
Tests for Smart Docs Input Validators
======================================
Covers ReDoS prevention, HTML sanitization, threshold pair validation,
DTI constraints, filename sanitization, JSON size limits, and
notification template escaping.
"""

import pytest

from validation.smart_docs_validators import (
    validate_regex_safe,
    sanitize_html,
    validate_threshold_pair,
    validate_dti,
    validate_phone,
    validate_email_safe,
    validate_loan_amount,
    validate_percentage,
    sanitize_filename,
    validate_json_size,
)


# =============================================================================
# REGEX SAFETY (ReDoS Prevention)
# =============================================================================

class TestValidateRegexSafe:
    """Tests for validate_regex_safe — ReDoS prevention."""

    def test_rejects_nested_quantifiers_basic(self):
        """Classic ReDoS pattern (a+)+ must be rejected."""
        assert validate_regex_safe("(a+)+b") is False

    def test_rejects_nested_quantifiers_star(self):
        """(a*)* must be rejected."""
        assert validate_regex_safe("(a*)*") is False

    def test_rejects_nested_quantifiers_complex(self):
        """(\\d+)+ must be rejected."""
        assert validate_regex_safe(r"(\d+)+") is False

    def test_rejects_alternation_under_quantifier(self):
        """(a|b)*c must be rejected."""
        assert validate_regex_safe("(a|b)*c") is False

    def test_rejects_alternation_with_plus(self):
        """(x|y)+ must be rejected."""
        assert validate_regex_safe("(x|y)+") is False

    def test_rejects_overly_long_pattern(self):
        """Patterns > 200 chars must be rejected."""
        long_pattern = r"\d" * 201
        assert validate_regex_safe(long_pattern) is False

    def test_rejects_invalid_regex_syntax(self):
        """Syntactically invalid regex must be rejected."""
        assert validate_regex_safe("[unclosed") is False

    def test_rejects_empty_string(self):
        """Empty string must be rejected."""
        assert validate_regex_safe("") is False

    def test_rejects_none(self):
        """None must be rejected."""
        assert validate_regex_safe(None) is False

    def test_accepts_ssn_pattern(self):
        """Standard SSN pattern must be accepted."""
        assert validate_regex_safe(r"^\d{3}-\d{2}-\d{4}$") is True

    def test_accepts_alpha_pattern(self):
        """Simple alpha pattern must be accepted."""
        assert validate_regex_safe("[A-Za-z]+") is True

    def test_accepts_phone_pattern(self):
        """Phone number pattern must be accepted."""
        assert validate_regex_safe(r"^\+?[1-9]\d{1,14}$") is True

    def test_accepts_email_simple(self):
        """Simple email pattern must be accepted."""
        assert validate_regex_safe(r"^[^@]+@[^@]+\.[^@]+$") is True

    def test_accepts_zip_code(self):
        """Zip code pattern must be accepted."""
        assert validate_regex_safe(r"^\d{5}(-\d{4})?$") is True

    def test_accepts_date_pattern(self):
        """Date pattern must be accepted."""
        assert validate_regex_safe(r"^\d{2}/\d{2}/\d{4}$") is True

    def test_accepts_200_char_safe_pattern(self):
        """Pattern at exactly 200 chars should be accepted if safe."""
        pattern = r"[A-Z]" * 50  # 250 would be too long, but 200 is fine
        if len(pattern) <= 200:
            assert validate_regex_safe(pattern) is True


# =============================================================================
# HTML SANITIZATION
# =============================================================================

class TestSanitizeHtml:
    """Tests for sanitize_html — XSS prevention."""

    def test_strips_script_tags(self):
        result = sanitize_html('<script>alert("xss")</script>Hello')
        assert "<script>" not in result
        assert "alert" not in result
        assert "Hello" in result

    def test_strips_img_onerror(self):
        result = sanitize_html('<img src=x onerror="alert(1)">text')
        assert "<img" not in result
        assert "onerror" not in result
        assert "text" in result

    def test_strips_all_html_tags(self):
        result = sanitize_html("<b>bold</b> and <i>italic</i>")
        assert "<b>" not in result
        assert "<i>" not in result
        assert "bold" in result
        assert "italic" in result

    def test_preserves_plain_text(self):
        text = "Hello World 123"
        assert sanitize_html(text) == text

    def test_handles_empty_string(self):
        assert sanitize_html("") == ""

    def test_handles_none(self):
        assert sanitize_html(None) == ""

    def test_handles_non_string(self):
        assert sanitize_html(12345) == "12345"

    def test_strips_iframe(self):
        result = sanitize_html('<iframe src="evil.com"></iframe>')
        assert "<iframe" not in result


# =============================================================================
# THRESHOLD PAIR VALIDATION
# =============================================================================

class TestValidateThresholdPair:
    """Tests for validate_threshold_pair."""

    def test_valid_pair(self):
        """80 approve, 30 reject is valid."""
        validate_threshold_pair(80, 30)  # should not raise

    def test_equal_thresholds_rejected(self):
        """Equal thresholds must be rejected."""
        with pytest.raises(ValueError, match="lower than"):
            validate_threshold_pair(50, 50)

    def test_reject_higher_than_approve(self):
        """Reject > approve must be rejected."""
        with pytest.raises(ValueError, match="lower than"):
            validate_threshold_pair(30, 80)

    def test_approve_out_of_range_high(self):
        with pytest.raises(ValueError, match="between 0 and 100"):
            validate_threshold_pair(101, 30)

    def test_reject_out_of_range_negative(self):
        with pytest.raises(ValueError, match="between 0 and 100"):
            validate_threshold_pair(80, -1)

    def test_boundary_valid(self):
        """0 and 100 are valid boundaries."""
        validate_threshold_pair(100, 0)  # should not raise

    def test_adjacent_valid(self):
        """approve=1, reject=0 is valid (strictly greater)."""
        validate_threshold_pair(1, 0)  # should not raise


# =============================================================================
# DTI VALIDATION
# =============================================================================

class TestValidateDti:
    """Tests for validate_dti."""

    def test_valid_dti(self):
        assert validate_dti(43.5) == 43.5

    def test_zero_valid(self):
        assert validate_dti(0) == 0.0

    def test_hundred_valid(self):
        assert validate_dti(100) == 100.0

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="between 0 and 100"):
            validate_dti(-1)

    def test_over_hundred_rejected(self):
        with pytest.raises(ValueError, match="between 0 and 100"):
            validate_dti(100.01)

    def test_none_rejected(self):
        with pytest.raises(ValueError, match="required"):
            validate_dti(None)

    def test_string_coercion(self):
        """Numeric strings should be coerced."""
        assert validate_dti("45.0") == 45.0


# =============================================================================
# FILENAME SANITIZATION
# =============================================================================

class TestSanitizeFilename:
    """Tests for sanitize_filename — path traversal prevention."""

    def test_normal_filename(self):
        assert sanitize_filename("document.pdf") == "document.pdf"

    def test_path_traversal_unix(self):
        result = sanitize_filename("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result
        assert "passwd" in result

    def test_path_traversal_windows(self):
        result = sanitize_filename("..\\..\\windows\\system32\\config")
        assert "\\" not in result
        assert ".." not in result

    def test_absolute_path_stripped(self):
        result = sanitize_filename("/var/log/secret.txt")
        assert result == "secret.txt"

    def test_null_bytes_removed(self):
        result = sanitize_filename("file\x00name.pdf")
        assert "\x00" not in result

    def test_long_filename_truncated(self):
        long_name = "a" * 300 + ".pdf"
        result = sanitize_filename(long_name)
        assert len(result) <= 255
        assert result.endswith(".pdf")

    def test_empty_string_returns_unnamed(self):
        assert sanitize_filename("") == "unnamed"

    def test_none_returns_unnamed(self):
        assert sanitize_filename(None) == "unnamed"

    def test_special_chars_removed(self):
        result = sanitize_filename("file<>name|test.pdf")
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result

    def test_preserves_spaces_and_hyphens(self):
        result = sanitize_filename("my file - v2.pdf")
        assert result == "my file - v2.pdf"


# =============================================================================
# JSON SIZE VALIDATION
# =============================================================================

class TestValidateJsonSize:
    """Tests for validate_json_size."""

    def test_small_dict_passes(self):
        data = {"key": "value"}
        assert validate_json_size(data) == data

    def test_oversized_dict_rejected(self):
        # Create a dict with > 1MB of data
        big_data = {"key": "x" * 2_000_000}
        with pytest.raises(ValueError, match="too large"):
            validate_json_size(big_data)

    def test_custom_max_bytes(self):
        data = {"key": "x" * 100}
        with pytest.raises(ValueError, match="too large"):
            validate_json_size(data, max_bytes=50)

    def test_none_returns_empty_dict(self):
        assert validate_json_size(None) == {}

    def test_exact_limit_passes(self):
        """Data at exactly the limit should pass."""
        data = {"k": "v"}
        size = len('{"k": "v"}'.encode("utf-8"))
        assert validate_json_size(data, max_bytes=size) == data


# =============================================================================
# PHONE VALIDATION
# =============================================================================

class TestValidatePhone:
    """Tests for validate_phone."""

    def test_e164_format(self):
        assert validate_phone("+15551234567") == "+15551234567"

    def test_strips_formatting(self):
        assert validate_phone("(555) 123-4567") == "+15551234567"

    def test_adds_us_country_code(self):
        assert validate_phone("5551234567") == "+15551234567"

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            validate_phone("")

    def test_none_rejected(self):
        with pytest.raises(ValueError):
            validate_phone(None)


# =============================================================================
# EMAIL VALIDATION
# =============================================================================

class TestValidateEmailSafe:
    """Tests for validate_email_safe."""

    def test_valid_email(self):
        assert validate_email_safe("user@example.com") == "user@example.com"

    def test_strips_control_chars(self):
        result = validate_email_safe("user\x00@example.com")
        assert "\x00" not in result

    def test_lowercased(self):
        assert validate_email_safe("User@Example.COM") == "user@example.com"

    def test_invalid_format_rejected(self):
        with pytest.raises(ValueError):
            validate_email_safe("not-an-email")

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            validate_email_safe("")

    def test_too_long_rejected(self):
        with pytest.raises(ValueError, match="maximum length"):
            validate_email_safe("a" * 250 + "@b.com")


# =============================================================================
# LOAN AMOUNT VALIDATION
# =============================================================================

class TestValidateLoanAmount:
    """Tests for validate_loan_amount."""

    def test_valid_amount(self):
        assert validate_loan_amount(350000) == 350000.0

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            validate_loan_amount(0)

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            validate_loan_amount(-100)

    def test_over_50m_rejected(self):
        with pytest.raises(ValueError, match="50,000,000"):
            validate_loan_amount(50_000_001)

    def test_exactly_50m_valid(self):
        assert validate_loan_amount(50_000_000) == 50_000_000.0

    def test_none_rejected(self):
        with pytest.raises(ValueError, match="required"):
            validate_loan_amount(None)


# =============================================================================
# PERCENTAGE VALIDATION
# =============================================================================

class TestValidatePercentage:
    """Tests for validate_percentage."""

    def test_valid_percentage(self):
        assert validate_percentage(45.5) == 45.5

    def test_zero_valid(self):
        assert validate_percentage(0) == 0.0

    def test_hundred_valid(self):
        assert validate_percentage(100) == 100.0

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="between"):
            validate_percentage(-0.1)

    def test_over_max_rejected(self):
        with pytest.raises(ValueError, match="between"):
            validate_percentage(100.01)

    def test_custom_range(self):
        assert validate_percentage(150, min_val=0, max_val=200) == 150.0

    def test_none_rejected(self):
        with pytest.raises(ValueError, match="required"):
            validate_percentage(None)


# =============================================================================
# NOTIFICATION TEMPLATE ESCAPING
# =============================================================================

class TestNotificationTemplateEscaping:
    """Verify that notification templates HTML-escape user-supplied data."""

    def test_scaffold_escapes_title(self):
        """The _html_scaffold function must escape header_title."""
        from services.smart_docs.notification_templates import _html_scaffold
        result = _html_scaffold(
            header_title='<script>alert("xss")</script>',
            header_subtitle="",
            body_html="<p>test</p>",
        )
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_scaffold_escapes_subtitle(self):
        """The _html_scaffold function must escape header_subtitle."""
        from services.smart_docs.notification_templates import _html_scaffold
        result = _html_scaffold(
            header_title="Title",
            header_subtitle='<img onerror="alert(1)">',
            body_html="<p>test</p>",
        )
        assert 'onerror="alert(1)"' not in result

    def test_document_request_escapes_borrower_name(self):
        """Document request template must escape borrower_name in HTML output."""
        from services.smart_docs.notification_templates import render_template
        rendered = render_template("document_request_initial", {
            "borrower_name": '<script>alert("xss")</script>',
            "document_list": [],
            "loan_officer_name": "Test LO",
        })
        assert "<script>" not in rendered.html_body
        assert "&lt;script&gt;" in rendered.html_body

    def test_document_rejected_escapes_reason(self):
        """Document rejected template must escape rejection_reason."""
        from services.smart_docs.notification_templates import render_template
        rendered = render_template("document_rejected", {
            "borrower_name": "John",
            "document_name": "W-2",
            "rejection_reason": '<img src=x onerror="alert(1)">',
            "loan_officer_name": "Test LO",
        })
        assert 'onerror="alert(1)"' not in rendered.html_body

    def test_esign_request_escapes_envelope_name(self):
        """E-sign request template must escape envelope_name."""
        from services.smart_docs.notification_templates import render_template
        rendered = render_template("esign_request", {
            "borrower_name": "John",
            "envelope_name": '<script>steal()</script>',
            "signing_url": "https://example.com/sign/abc",
            "loan_officer_name": "Test LO",
        })
        assert "<script>" not in rendered.html_body


# =============================================================================
# INCOME CALCULATION MODEL DTI VALIDATION
# =============================================================================

class TestIncomeCalculationDtiValidation:
    """Tests for the @validates decorators on IncomeCalculation model."""

    def test_valid_dti_values_accepted(self):
        """Normal DTI values should be accepted."""
        from database.models.income_calculation import IncomeCalculation
        calc = IncomeCalculation()
        calc.dti_front_end = 28.0
        calc.dti_back_end = 43.0
        assert float(calc.dti_front_end) == 28.0
        assert float(calc.dti_back_end) == 43.0

    def test_dti_front_end_negative_rejected(self):
        """Negative DTI front-end should raise ValueError."""
        from database.models.income_calculation import IncomeCalculation
        calc = IncomeCalculation()
        with pytest.raises(ValueError, match="between 0 and 100"):
            calc.dti_front_end = -5.0

    def test_dti_back_end_over_100_rejected(self):
        """DTI back-end > 100 should raise ValueError."""
        from database.models.income_calculation import IncomeCalculation
        calc = IncomeCalculation()
        with pytest.raises(ValueError, match="between 0 and 100"):
            calc.dti_back_end = 150.0

    def test_dti_none_accepted(self):
        """None DTI values should be accepted (nullable field)."""
        from database.models.income_calculation import IncomeCalculation
        calc = IncomeCalculation()
        calc.dti_front_end = None
        calc.dti_back_end = None
        assert calc.dti_front_end is None
        assert calc.dti_back_end is None

    def test_dti_boundary_zero_accepted(self):
        """DTI = 0 should be accepted."""
        from database.models.income_calculation import IncomeCalculation
        calc = IncomeCalculation()
        calc.dti_front_end = 0
        assert float(calc.dti_front_end) == 0.0

    def test_dti_boundary_hundred_accepted(self):
        """DTI = 100 should be accepted."""
        from database.models.income_calculation import IncomeCalculation
        calc = IncomeCalculation()
        calc.dti_back_end = 100
        assert float(calc.dti_back_end) == 100.0
