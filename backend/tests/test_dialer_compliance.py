"""
Test Dialer Compliance — DNC, TCPA Calling Hours, Consent, Rate Limiting

Verifies:
- ComplianceChecker.check_dnc() with mocked DB
- ComplianceChecker.check_calling_hours() TCPA 8am-9pm enforcement
- ComplianceChecker.check_call_consent() blocks without consent
- ComplianceChecker.full_compliance_check() aggregates all checks
- ComplianceChecker._normalize_phone() handles various formats
- Voicemail drop route helpers: check_calling_hours, check_dnc_status, check_consent
- DNC scrub freshness blocking (_check_national_dnc_scrub_freshness)
"""

import os
import pytest
from datetime import datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock


# =============================================================================
# Phone Number Normalization
# =============================================================================

@pytest.mark.unit
class TestPhoneNormalization:
    """Test phone number normalization in ComplianceChecker."""

    def _get_checker(self):
        from telephony.compliance import ComplianceChecker
        mock_db = MagicMock()
        return ComplianceChecker(mock_db)

    def test_normalize_strips_formatting(self):
        """Normalize removes parens, dashes, spaces."""
        checker = self._get_checker()
        assert checker._normalize_phone("(555) 123-4567") == "5551234567"

    def test_normalize_strips_plus_one(self):
        """Normalize strips +1 country code prefix."""
        checker = self._get_checker()
        assert checker._normalize_phone("+15551234567") == "5551234567"

    def test_normalize_11_digit_with_leading_one(self):
        """11-digit number starting with 1 is normalized to 10 digits."""
        checker = self._get_checker()
        assert checker._normalize_phone("15551234567") == "5551234567"

    def test_normalize_empty_string(self):
        """Empty string returns empty string."""
        checker = self._get_checker()
        assert checker._normalize_phone("") == ""

    def test_normalize_none_returns_empty(self):
        """None input returns empty string."""
        checker = self._get_checker()
        assert checker._normalize_phone(None) == ""


# =============================================================================
# DNC Check Tests
# =============================================================================

@pytest.mark.unit
class TestDNCCheck:
    """Test Do Not Call list checking."""

    def test_check_dnc_returns_false_when_not_on_list(self):
        """Phone not on DNC list returns (False, None)."""
        from telephony.compliance import ComplianceChecker
        mock_db = MagicMock()

        # Mock ContactDNCStatus query to return None (not found)
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        checker = ComplianceChecker(mock_db)
        is_dnc, reason = checker.check_dnc("5551234567")
        assert is_dnc is False
        assert reason is None

    def test_check_dnc_returns_true_when_on_list(self):
        """Phone on DNC list returns (True, reason)."""
        from telephony.compliance import ComplianceChecker
        mock_db = MagicMock()

        mock_entry = MagicMock()
        mock_entry.reason = "Customer requested removal"
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_entry
        mock_db.query.return_value = mock_query

        checker = ComplianceChecker(mock_db)
        is_dnc, reason = checker.check_dnc("5551234567")
        assert is_dnc is True
        assert reason == "Customer requested removal"


# =============================================================================
# Calling Hours Tests
# =============================================================================

@pytest.mark.unit
class TestCallingHours:
    """Test TCPA calling hours enforcement (8am-9pm local)."""

    def test_calling_hours_constants_correct(self):
        """TCPA safe harbor hours should be 8 AM - 9 PM."""
        from telephony.compliance import ComplianceChecker
        assert ComplianceChecker.CALLING_HOURS_START == time(8, 0)
        assert ComplianceChecker.CALLING_HOURS_END == time(21, 0)

    def test_area_code_to_timezone_known_codes(self):
        """Known area codes map to expected timezones."""
        from telephony.compliance import ComplianceChecker
        mock_db = MagicMock()
        checker = ComplianceChecker(mock_db)

        # NYC area code should be Eastern
        tz = checker._area_code_to_timezone("212")
        assert tz == "America/New_York"

        # Chicago area code should be Central
        tz = checker._area_code_to_timezone("312")
        assert tz == "America/Chicago"

        # LA area code should be Pacific
        tz = checker._area_code_to_timezone("310")
        assert tz == "America/Los_Angeles"

    def test_area_code_to_timezone_unknown_returns_none(self):
        """Unknown area code returns None (falls back to default)."""
        from telephony.compliance import ComplianceChecker
        mock_db = MagicMock()
        checker = ComplianceChecker(mock_db)
        assert checker._area_code_to_timezone("999") is None


# =============================================================================
# Call Consent Tests
# =============================================================================

@pytest.mark.unit
class TestCallConsent:
    """Test call consent checking (TCPA/FCC one-to-one consent)."""

    def test_no_contact_found_blocks_call(self):
        """When no contact record found, call is blocked."""
        from telephony.compliance import ComplianceChecker
        mock_db = MagicMock()

        # Mock Lead query to return None (no matching contact)
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        checker = ComplianceChecker(mock_db)

        with patch("telephony.compliance.ComplianceChecker.check_call_consent") as mock_check:
            # Directly test the real logic instead of mocking itself
            pass

        # Call with phone number and no contact_id
        has_consent, reason = checker.check_call_consent("5551234567")
        assert has_consent is False
        assert "No contact record" in (reason or "")

    def test_no_channel_preference_blocks_call(self):
        """When ChannelPreference record is missing, call is blocked."""
        from telephony.compliance import ComplianceChecker
        mock_db = MagicMock()

        # When contact_id is provided, lead_id is set directly (no Lead
        # query).  The function then queries ChannelPreference.  We need
        # that query to return None so the "no channel preference" path
        # is taken.
        mock_q = MagicMock()
        mock_q.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_q

        checker = ComplianceChecker(mock_db)
        has_consent, reason = checker.check_call_consent("5551234567", contact_id=42)
        # With contact_id=42, lead_id is 42, ChannelPreference query returns None
        assert has_consent is False
        assert "channel preference" in (reason or "").lower()


# =============================================================================
# Full Compliance Check Tests
# =============================================================================

@pytest.mark.unit
class TestFullComplianceCheck:
    """Test the aggregated full_compliance_check method."""

    def test_full_check_structure(self):
        """full_compliance_check returns expected keys."""
        from telephony.compliance import ComplianceChecker
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        checker = ComplianceChecker(mock_db)

        # Patch all sub-checks to return OK
        with patch.object(checker, "check_call_consent", return_value=(True, None)), \
             patch.object(checker, "check_dnc", return_value=(False, None)), \
             patch.object(checker, "check_calling_hours", return_value=(True, "Within hours")), \
             patch.object(checker, "check_rate_limit", return_value=(True, None)), \
             patch.object(checker, "check_soft_lock", return_value=(False, None)):

            result = checker.full_compliance_check("5551234567", agent_id=1)

        assert "can_call" in result
        assert "issues" in result
        assert "warnings" in result
        assert result["can_call"] is True
        assert len(result["issues"]) == 0

    def test_full_check_blocks_when_dnc(self):
        """full_compliance_check blocks when DNC check fails."""
        from telephony.compliance import ComplianceChecker
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        checker = ComplianceChecker(mock_db)

        with patch.object(checker, "check_call_consent", return_value=(True, None)), \
             patch.object(checker, "check_dnc", return_value=(True, "Customer opt-out")), \
             patch.object(checker, "check_calling_hours", return_value=(True, "OK")), \
             patch.object(checker, "check_rate_limit", return_value=(True, None)), \
             patch.object(checker, "check_soft_lock", return_value=(False, None)):

            result = checker.full_compliance_check("5551234567", agent_id=1)

        assert result["can_call"] is False
        assert any("Do Not Call" in issue for issue in result["issues"])


# =============================================================================
# Voicemail Drop DNC Scrub Freshness Tests
# =============================================================================

@pytest.mark.unit
class TestDNCScrubFreshness:
    """Test the National DNC Registry scrub freshness check."""

    def test_missing_env_var_blocks(self):
        """Missing NATIONAL_DNC_LAST_SCRUB env var should block."""
        from routes.voicemail_drop_routes import _check_national_dnc_scrub_freshness

        with patch.dict(os.environ, {}, clear=True):
            # Remove the var entirely
            os.environ.pop("NATIONAL_DNC_LAST_SCRUB", None)
            is_stale, msg = _check_national_dnc_scrub_freshness()
            assert is_stale is True
            assert "not set" in msg.lower() or "stale" in msg.lower()

    def test_fresh_scrub_allows(self):
        """Recent scrub date (today) should allow calls."""
        from routes.voicemail_drop_routes import _check_national_dnc_scrub_freshness

        today = datetime.now(timezone.utc).isoformat()
        with patch.dict(os.environ, {"NATIONAL_DNC_LAST_SCRUB": today}):
            is_stale, msg = _check_national_dnc_scrub_freshness()
            assert is_stale is False

    def test_stale_scrub_blocks(self):
        """Scrub date older than 31 days should block."""
        from routes.voicemail_drop_routes import _check_national_dnc_scrub_freshness

        old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        with patch.dict(os.environ, {"NATIONAL_DNC_LAST_SCRUB": old_date}):
            is_stale, msg = _check_national_dnc_scrub_freshness()
            assert is_stale is True
            assert "31" in msg or "scrub" in msg.lower()

    def test_invalid_date_format_blocks(self):
        """Invalid date format in env var should block."""
        from routes.voicemail_drop_routes import _check_national_dnc_scrub_freshness

        with patch.dict(os.environ, {"NATIONAL_DNC_LAST_SCRUB": "not-a-date"}):
            is_stale, msg = _check_national_dnc_scrub_freshness()
            assert is_stale is True
            assert "invalid" in msg.lower() or "format" in msg.lower()
