"""
PII Masking Tests

Tests that PII (Personally Identifiable Information) is properly masked
in API responses and sanitized in data dictionaries. Exercises real code
from schemas/pii_masking.py.

Critical for GLBA/CCPA compliance:
- SSN must never appear in plaintext (Enterprise Readiness 3.19)
- DOB, bank account numbers, tax IDs must be masked
- Free text containing SSN patterns must be redacted
- Nested data structures must be recursively sanitized
"""

import pytest
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# SSN Masking
# =============================================================================

@pytest.mark.critical
@pytest.mark.security
@pytest.mark.unit
class TestSSNMasking:
    """SSN must be masked to show only last 4 digits."""

    def test_mask_ssn_standard_format(self):
        """SSN 123-45-6789 should become ***-**-6789."""
        from schemas.pii_masking import mask_ssn
        assert mask_ssn("123-45-6789") == "***-**-6789"

    def test_mask_ssn_digits_only(self):
        """SSN 123456789 should become ***-**-6789."""
        from schemas.pii_masking import mask_ssn
        assert mask_ssn("123456789") == "***-**-6789"

    def test_mask_ssn_with_spaces(self):
        """SSN 123 45 6789 should become ***-**-6789."""
        from schemas.pii_masking import mask_ssn
        assert mask_ssn("123 45 6789") == "***-**-6789"

    def test_mask_ssn_short_value(self):
        """SSN with fewer than 4 digits should return fully masked."""
        from schemas.pii_masking import mask_ssn
        assert mask_ssn("12") == "***-**-****"

    def test_mask_ssn_none(self):
        """None SSN should return None."""
        from schemas.pii_masking import mask_ssn
        assert mask_ssn(None) is None

    def test_mask_ssn_empty_string(self):
        """Empty SSN should return None."""
        from schemas.pii_masking import mask_ssn
        assert mask_ssn("") is None

    def test_contains_ssn_detects_pattern(self):
        """contains_ssn() should detect SSN-like patterns in text."""
        from schemas.pii_masking import contains_ssn
        assert contains_ssn("My SSN is 123-45-6789 and it should be hidden")
        assert contains_ssn("SSN: 123456789")
        assert not contains_ssn("Phone: 555-1234")
        assert not contains_ssn("No PII here")

    def test_redact_ssn_from_text(self):
        """redact_ssn_from_text() should replace SSN patterns with masked version."""
        from schemas.pii_masking import redact_ssn_from_text
        text = "Borrower SSN is 123-45-6789 and co-borrower is 987-65-4321"
        result = redact_ssn_from_text(text)
        assert "123-45-6789" not in result
        assert "987-65-4321" not in result
        assert "***-**-6789" in result
        assert "***-**-4321" in result


# =============================================================================
# DOB Masking
# =============================================================================

@pytest.mark.critical
@pytest.mark.security
@pytest.mark.unit
class TestDOBMasking:
    """Date of birth must be masked to show only year."""

    def test_mask_dob_iso_format(self):
        """ISO date 1990-05-14 should become 1990-**-**."""
        from schemas.pii_masking import mask_dob
        assert mask_dob("1990-05-14") == "1990-**-**"

    def test_mask_dob_us_format(self):
        """US date 05/14/1990 should become **/**/1990."""
        from schemas.pii_masking import mask_dob
        assert mask_dob("05/14/1990") == "**/**/1990"

    def test_mask_dob_iso_with_time(self):
        """ISO datetime 1990-05-14T00:00:00 should become 1990-**-**T00:00:00."""
        from schemas.pii_masking import mask_dob
        result = mask_dob("1990-05-14T00:00:00")
        assert result == "1990-**-**T00:00:00"

    def test_mask_dob_none(self):
        """None DOB should return None."""
        from schemas.pii_masking import mask_dob
        assert mask_dob(None) is None

    def test_mask_dob_already_masked(self):
        """Already-masked DOB should be returned as-is."""
        from schemas.pii_masking import mask_dob
        assert mask_dob("**/**/1990") == "**/**/1990"


# =============================================================================
# Bank Account Number Masking
# =============================================================================

@pytest.mark.critical
@pytest.mark.security
@pytest.mark.unit
class TestAccountNumberMasking:
    """Bank account numbers must be masked to show only last 4 digits."""

    def test_mask_account_number(self):
        """Account 9876543210 should become ****3210."""
        from schemas.pii_masking import mask_account_number
        assert mask_account_number("9876543210") == "****3210"

    def test_mask_account_number_short(self):
        """Short account with fewer than 4 digits should be fully masked."""
        from schemas.pii_masking import mask_account_number
        assert mask_account_number("12") == "********"

    def test_mask_account_number_none(self):
        """None should return None."""
        from schemas.pii_masking import mask_account_number
        assert mask_account_number(None) is None

    def test_mask_account_already_masked(self):
        """Already-masked account should be returned as-is."""
        from schemas.pii_masking import mask_account_number
        assert mask_account_number("****3210") == "****3210"


# =============================================================================
# Tax ID Masking
# =============================================================================

@pytest.mark.critical
@pytest.mark.security
@pytest.mark.unit
class TestTaxIDMasking:
    """Tax IDs (EIN/TIN) must be masked."""

    def test_mask_tax_id(self):
        """Tax ID 12-3456789 should become ***-**-6789."""
        from schemas.pii_masking import mask_tax_id
        assert mask_tax_id("12-3456789") == "***-**-6789"

    def test_mask_tax_id_digits_only(self):
        """Tax ID 123456789 should become ***-**-6789."""
        from schemas.pii_masking import mask_tax_id
        assert mask_tax_id("123456789") == "***-**-6789"

    def test_mask_tax_id_none(self):
        """None should return None."""
        from schemas.pii_masking import mask_tax_id
        assert mask_tax_id(None) is None


# =============================================================================
# Email and Phone Masking
# =============================================================================

@pytest.mark.unit
class TestEmailPhoneMasking:
    """Email and phone masking utilities."""

    def test_mask_email(self):
        """Email john@example.com should be partially masked."""
        from schemas.pii_masking import mask_email
        result = mask_email("john@example.com")
        assert "@example.com" in result
        assert "john" not in result
        assert result.startswith("j")

    def test_mask_email_short_local(self):
        """Short email local part (<=2 chars) should still mask."""
        from schemas.pii_masking import mask_email
        result = mask_email("ab@x.com")
        assert "@x.com" in result

    def test_mask_phone(self):
        """Phone +15551234567 should become (***) ***-4567."""
        from schemas.pii_masking import mask_phone
        result = mask_phone("+15551234567")
        assert "4567" in result
        assert "555" not in result


# =============================================================================
# Deep Data Sanitization
# =============================================================================

@pytest.mark.critical
@pytest.mark.security
@pytest.mark.unit
class TestSanitizeStepData:
    """sanitize_step_data() must recursively scrub PII from nested dicts."""

    def test_sanitize_ssn_in_flat_dict(self):
        """SSN key in a flat dict must be masked."""
        from schemas.pii_masking import sanitize_step_data
        data = {"ssn": "123-45-6789", "name": "John Smith"}
        result = sanitize_step_data(data)
        assert result["ssn"] == "***-**-6789"
        assert result["name"] == "John Smith"  # Non-PII preserved

    def test_sanitize_nested_dict(self):
        """PII in nested dicts must be recursively masked."""
        from schemas.pii_masking import sanitize_step_data
        data = {
            "borrower": {
                "ssn": "987-65-4321",
                "date_of_birth": "1985-03-22",
                "bank_account_number": "1234567890",
            }
        }
        result = sanitize_step_data(data)
        assert result["borrower"]["ssn"] == "***-**-4321"
        assert result["borrower"]["date_of_birth"] == "1985-**-**"
        assert result["borrower"]["bank_account_number"] == "****7890"

    def test_sanitize_list_of_dicts(self):
        """PII in lists of dicts must be masked."""
        from schemas.pii_masking import sanitize_step_data
        data = {
            "applicants": [
                {"ssn": "111-22-3333"},
                {"ssn": "444-55-6666"},
            ]
        }
        result = sanitize_step_data(data)
        assert result["applicants"][0]["ssn"] == "***-**-3333"
        assert result["applicants"][1]["ssn"] == "***-**-6666"

    def test_sanitize_ssn_in_free_text(self):
        """SSN patterns in string values must be redacted."""
        from schemas.pii_masking import sanitize_step_data
        data = {"notes": "Borrower SSN: 123-45-6789, verified"}
        result = sanitize_step_data(data)
        assert "123-45-6789" not in result["notes"]
        assert "***-**-6789" in result["notes"]

    def test_sanitize_empty_data(self):
        """Empty or None data should return empty dict."""
        from schemas.pii_masking import sanitize_step_data
        assert sanitize_step_data(None) == {}
        assert sanitize_step_data({}) == {}

    def test_sanitize_co_ssn_key(self):
        """co_ssn key should also be masked."""
        from schemas.pii_masking import sanitize_step_data
        data = {"co_ssn": "999-88-7777"}
        result = sanitize_step_data(data)
        assert result["co_ssn"] == "***-**-7777"

    def test_sanitize_routing_number(self):
        """routing_number key should be masked."""
        from schemas.pii_masking import sanitize_step_data
        data = {"routing_number": "021000021"}
        result = sanitize_step_data(data)
        assert result["routing_number"] == "****0021"

    def test_sanitize_preserves_non_pii(self):
        """Non-PII fields should be preserved unchanged."""
        from schemas.pii_masking import sanitize_step_data
        data = {
            "loan_amount": 400000,
            "interest_rate": 6.875,
            "loan_type": "conventional",
            "step": 3,
            "completed": True,
        }
        result = sanitize_step_data(data)
        assert result["loan_amount"] == 400000
        assert result["interest_rate"] == 6.875
        assert result["loan_type"] == "conventional"
        assert result["step"] == 3
        assert result["completed"] is True
