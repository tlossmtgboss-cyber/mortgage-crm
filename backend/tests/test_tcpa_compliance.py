"""
Tests for TCPA Compliance Service (Smart Docs Follow-Up)

TCPA penalties: $500-$1,500 per unconsented message. These tests verify that
the TCPAComplianceService correctly blocks outreach when consent is missing,
revoked, during quiet hours, when frequency limits are exceeded, and when
a number is on the DNC list.

Covers:
1.  SMS consent check - with active consent
2.  SMS consent check - without consent (BLOCKED)
3.  Call consent check - with active consent
4.  Call consent check - without consent (BLOCKED)
5.  DNC list blocking (InternalDNCEntry)
6.  DNC list blocking (ContactDNCStatus)
7.  Quiet hours - before 8 AM recipient time (BLOCKED)
8.  Quiet hours - after 9 PM recipient time (BLOCKED)
9.  Quiet hours - within allowed window (ALLOWED)
10. Frequency limiting - 4th contact in a day (BLOCKED)
11. Frequency limiting - within limit (ALLOWED)
12. Consent recording
13. Consent revocation - immediate effect
14. Comprehensive validate_outreach - all clear
15. Comprehensive validate_outreach - multiple blockers
16. Followup service respects TCPA blocks on SMS
17. Followup service respects TCPA blocks on calls
18. Revoked consent blocks subsequent outreach
19. "both" channel consent satisfies SMS and call checks
20. Phone normalization edge cases
"""

import os
import sys
import pytest
from datetime import datetime, timedelta, timezone, time
from unittest.mock import MagicMock, Mock, patch, PropertyMock

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database.models.tcpa_smart_docs import (
    SmartDocsConsentRecord,
    InternalDNCEntry,
    OutreachLog,
)
from services.smart_docs.tcpa_compliance_service import (
    TCPAComplianceService,
    TCPACheckResult,
    OutreachValidation,
    QUIET_HOURS_START,
    QUIET_HOURS_END,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db():
    """Create a mock database session with query builder chains."""
    db = MagicMock()

    # Default: query().filter().order_by().first() returns None
    query_chain = MagicMock()
    query_chain.filter.return_value = query_chain
    query_chain.order_by.return_value = query_chain
    query_chain.first.return_value = None
    query_chain.scalar.return_value = 0
    query_chain.all.return_value = []
    db.query.return_value = query_chain

    return db


@pytest.fixture
def tcpa_service(mock_db):
    """Create a TCPAComplianceService with a mocked DB."""
    return TCPAComplianceService(mock_db)


def _make_consent_record(
    phone="15551234567",
    org_id=1,
    channel="sms",
    source="web_form",
    consented_at=None,
    revoked_at=None,
):
    """Helper to create a mock SmartDocsConsentRecord."""
    record = MagicMock(spec=SmartDocsConsentRecord)
    record.id = 1
    record.phone = phone
    record.organization_id = org_id
    record.channel = channel
    record.consent_given = True
    record.consent_source = source
    record.consented_at = consented_at or datetime.now(timezone.utc)
    record.revoked_at = revoked_at
    return record


def _make_dnc_entry(phone="15551234567", reason="Requested removal"):
    """Helper to create a mock InternalDNCEntry."""
    entry = MagicMock(spec=InternalDNCEntry)
    entry.id = 1
    entry.phone = phone
    entry.reason = reason
    entry.expires_at = None
    return entry


# =============================================================================
# SMS CONSENT TESTS
# =============================================================================


class TestSMSConsent:
    """Test SMS consent checking."""

    def test_sms_consent_with_active_consent(self, tcpa_service, mock_db):
        """SMS allowed when active consent record exists."""
        consent = _make_consent_record(channel="sms")
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.order_by.return_value = query_chain
        query_chain.first.return_value = consent
        mock_db.query.return_value = query_chain

        result = tcpa_service.check_sms_consent("555-123-4567", org_id=1)

        assert result.allowed is True
        assert result.consent_date is not None
        assert result.consent_type == "web_form"

    def test_sms_consent_without_consent(self, tcpa_service, mock_db):
        """SMS blocked when no consent record exists."""
        # Default mock returns None for .first()
        result = tcpa_service.check_sms_consent("555-123-4567", org_id=1)

        assert result.allowed is False
        assert "No active sms consent" in result.reason

    def test_sms_consent_with_both_channel(self, tcpa_service, mock_db):
        """SMS allowed when consent channel is 'both'."""
        consent = _make_consent_record(channel="both")
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.order_by.return_value = query_chain
        query_chain.first.return_value = consent
        mock_db.query.return_value = query_chain

        result = tcpa_service.check_sms_consent("555-123-4567", org_id=1)

        assert result.allowed is True


# =============================================================================
# CALL CONSENT TESTS
# =============================================================================


class TestCallConsent:
    """Test call consent checking."""

    def test_call_consent_with_active_consent(self, tcpa_service, mock_db):
        """Call allowed when active consent record exists."""
        consent = _make_consent_record(channel="call")
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.order_by.return_value = query_chain
        query_chain.first.return_value = consent
        mock_db.query.return_value = query_chain

        result = tcpa_service.check_call_consent("555-123-4567", org_id=1)

        assert result.allowed is True
        assert result.consent_type == "web_form"

    def test_call_consent_without_consent(self, tcpa_service, mock_db):
        """Call blocked when no consent record exists."""
        result = tcpa_service.check_call_consent("555-123-4567", org_id=1)

        assert result.allowed is False
        assert "No active call consent" in result.reason


# =============================================================================
# DNC LIST TESTS
# =============================================================================


class TestDNCList:
    """Test Do Not Call list checking."""

    def test_dnc_blocks_when_on_internal_list(self, tcpa_service, mock_db):
        """Phone on InternalDNCEntry list is blocked."""
        dnc = _make_dnc_entry()
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.first.return_value = dnc
        mock_db.query.return_value = query_chain

        is_blocked = tcpa_service.check_dnc_list("555-123-4567")

        assert is_blocked is True

    def test_dnc_allows_when_not_on_list(self, tcpa_service, mock_db):
        """Phone not on any DNC list is allowed."""
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.first.return_value = None
        mock_db.query.return_value = query_chain

        is_blocked = tcpa_service.check_dnc_list("555-123-4567")

        assert is_blocked is False

    def test_dnc_invalid_phone_is_blocked(self, tcpa_service):
        """Invalid phone number is treated as blocked."""
        is_blocked = tcpa_service.check_dnc_list("123")

        assert is_blocked is True

    def test_dnc_empty_phone_is_blocked(self, tcpa_service):
        """Empty phone is blocked."""
        is_blocked = tcpa_service.check_dnc_list("")

        assert is_blocked is True


# =============================================================================
# QUIET HOURS TESTS
# =============================================================================


class TestQuietHours:
    """Test TCPA quiet hours enforcement (8 AM - 9 PM recipient time)."""

    @patch("services.smart_docs.tcpa_compliance_service.TCPAComplianceService._now_in_tz")
    def test_blocked_before_8am(self, mock_now, tcpa_service):
        """Outreach before 8 AM local time is blocked."""
        # 7:30 AM local time
        mock_now.return_value = datetime(2026, 3, 12, 7, 30, 0)

        is_quiet = tcpa_service.check_quiet_hours("555-123-4567")

        assert is_quiet is True

    @patch("services.smart_docs.tcpa_compliance_service.TCPAComplianceService._now_in_tz")
    def test_blocked_after_9pm(self, mock_now, tcpa_service):
        """Outreach at or after 9 PM local time is blocked."""
        # 9:00 PM local time (21:00)
        mock_now.return_value = datetime(2026, 3, 12, 21, 0, 0)

        is_quiet = tcpa_service.check_quiet_hours("555-123-4567")

        assert is_quiet is True

    @patch("services.smart_docs.tcpa_compliance_service.TCPAComplianceService._now_in_tz")
    def test_blocked_at_midnight(self, mock_now, tcpa_service):
        """Outreach at midnight is blocked."""
        mock_now.return_value = datetime(2026, 3, 12, 0, 0, 0)

        is_quiet = tcpa_service.check_quiet_hours("555-123-4567")

        assert is_quiet is True

    @patch("services.smart_docs.tcpa_compliance_service.TCPAComplianceService._now_in_tz")
    def test_allowed_during_business_hours(self, mock_now, tcpa_service):
        """Outreach at 10 AM local time is allowed."""
        mock_now.return_value = datetime(2026, 3, 12, 10, 0, 0)

        is_quiet = tcpa_service.check_quiet_hours("555-123-4567")

        assert is_quiet is False

    @patch("services.smart_docs.tcpa_compliance_service.TCPAComplianceService._now_in_tz")
    def test_allowed_at_exactly_8am(self, mock_now, tcpa_service):
        """Outreach at exactly 8:00 AM is allowed (boundary)."""
        mock_now.return_value = datetime(2026, 3, 12, 8, 0, 0)

        is_quiet = tcpa_service.check_quiet_hours("555-123-4567")

        assert is_quiet is False

    @patch("services.smart_docs.tcpa_compliance_service.TCPAComplianceService._now_in_tz")
    def test_allowed_at_8_59pm(self, mock_now, tcpa_service):
        """Outreach at 8:59 PM is allowed (boundary)."""
        mock_now.return_value = datetime(2026, 3, 12, 20, 59, 0)

        is_quiet = tcpa_service.check_quiet_hours("555-123-4567")

        assert is_quiet is False


# =============================================================================
# FREQUENCY LIMITING TESTS
# =============================================================================


class TestFrequencyLimit:
    """Test daily per-channel frequency limits."""

    def test_4th_contact_blocked(self, tcpa_service, mock_db):
        """4th SMS in a day is blocked when max is 3."""
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.scalar.return_value = 3  # Already 3 contacts today
        mock_db.query.return_value = query_chain

        is_over = tcpa_service.check_frequency_limit(
            "555-123-4567", org_id=1, channel="sms", max_per_day=3
        )

        assert is_over is True

    def test_within_limit_allowed(self, tcpa_service, mock_db):
        """2nd SMS in a day is allowed when max is 3."""
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.scalar.return_value = 1  # Only 1 contact today
        mock_db.query.return_value = query_chain

        is_over = tcpa_service.check_frequency_limit(
            "555-123-4567", org_id=1, channel="sms", max_per_day=3
        )

        assert is_over is False

    def test_zero_contacts_allowed(self, tcpa_service, mock_db):
        """First contact of the day is allowed."""
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.scalar.return_value = 0
        mock_db.query.return_value = query_chain

        is_over = tcpa_service.check_frequency_limit(
            "555-123-4567", org_id=1, channel="call", max_per_day=3
        )

        assert is_over is False


# =============================================================================
# CONSENT RECORDING TESTS
# =============================================================================


class TestConsentRecording:
    """Test consent recording with audit trail."""

    def test_record_consent_creates_record(self, tcpa_service, mock_db):
        """Recording consent adds a SmartDocsConsentRecord to the session."""
        result = tcpa_service.record_consent(
            phone="555-123-4567",
            org_id=1,
            borrower_id=42,
            channel="sms",
            consent_source="web_form",
            ip_address="192.168.1.100",
        )

        assert "error" not in result
        assert result["phone"] == "15551234567"
        assert result["channel"] == "sms"
        assert result["consent_source"] == "web_form"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_record_consent_invalid_phone(self, tcpa_service, mock_db):
        """Recording consent with invalid phone returns error."""
        result = tcpa_service.record_consent(
            phone="123",
            org_id=1,
            borrower_id=42,
            channel="sms",
            consent_source="web_form",
        )

        assert "error" in result
        mock_db.add.assert_not_called()


# =============================================================================
# CONSENT REVOCATION TESTS
# =============================================================================


class TestConsentRevocation:
    """Test consent revocation with immediate effect."""

    def test_revocation_marks_records(self, tcpa_service, mock_db):
        """Revoking consent marks all matching records with revoked_at."""
        active_record = _make_consent_record(channel="sms")
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.all.return_value = [active_record]
        mock_db.query.return_value = query_chain

        result = tcpa_service.revoke_consent(
            phone="555-123-4567",
            org_id=1,
            channel="sms",
            revocation_source="text_reply",
        )

        assert result["revoked_count"] == 1
        assert active_record.revoked_at is not None
        assert active_record.revocation_source == "text_reply"

    def test_revoked_consent_blocks_subsequent_check(self, tcpa_service, mock_db):
        """After revocation, consent check returns not allowed."""
        # Simulate revoked record (revoked_at is not None)
        # The query for active consent should filter out revoked records
        # so .first() returns None
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.order_by.return_value = query_chain
        query_chain.first.return_value = None
        mock_db.query.return_value = query_chain

        result = tcpa_service.check_sms_consent("555-123-4567", org_id=1)

        assert result.allowed is False

    def test_revocation_of_both_channel(self, tcpa_service, mock_db):
        """Revoking 'both' also revokes individual sms and call records."""
        sms_record = _make_consent_record(channel="sms")
        call_record = _make_consent_record(channel="call")
        both_record = _make_consent_record(channel="both")

        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.all.return_value = [sms_record, call_record, both_record]
        mock_db.query.return_value = query_chain

        result = tcpa_service.revoke_consent(
            phone="555-123-4567",
            org_id=1,
            channel="both",
            revocation_source="phone_request",
        )

        assert result["revoked_count"] == 3


# =============================================================================
# COMPREHENSIVE VALIDATE_OUTREACH TESTS
# =============================================================================


class TestValidateOutreach:
    """Test the comprehensive validate_outreach() method."""

    @patch.object(TCPAComplianceService, "check_frequency_limit", return_value=False)
    @patch.object(TCPAComplianceService, "check_quiet_hours", return_value=False)
    @patch.object(TCPAComplianceService, "check_dnc_list", return_value=False)
    @patch.object(
        TCPAComplianceService,
        "_check_consent",
        return_value=TCPACheckResult(
            allowed=True,
            reason="Active consent",
            consent_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            consent_type="web_form",
        ),
    )
    def test_all_clear(self, mock_consent, mock_dnc, mock_quiet, mock_freq, tcpa_service):
        """When all checks pass, outreach is allowed."""
        result = tcpa_service.validate_outreach("555-123-4567", org_id=1, channel="sms")

        assert result.allowed is True
        assert len(result.blockers) == 0
        assert result.consent_info is not None
        assert result.consent_info["consent_source"] == "web_form"

    @patch.object(TCPAComplianceService, "check_frequency_limit", return_value=True)
    @patch.object(TCPAComplianceService, "check_quiet_hours", return_value=True)
    @patch.object(TCPAComplianceService, "check_dnc_list", return_value=True)
    @patch.object(
        TCPAComplianceService,
        "_check_consent",
        return_value=TCPACheckResult(allowed=False, reason="No consent"),
    )
    def test_multiple_blockers(self, mock_consent, mock_dnc, mock_quiet, mock_freq, tcpa_service):
        """When multiple checks fail, all blockers are reported."""
        result = tcpa_service.validate_outreach("555-123-4567", org_id=1, channel="sms")

        assert result.allowed is False
        assert len(result.blockers) >= 3  # consent + DNC + quiet hours + frequency
        assert any("consent" in b.lower() for b in result.blockers)
        assert any("do not contact" in b.lower() for b in result.blockers)

    def test_invalid_phone(self, tcpa_service):
        """Invalid phone number is immediately blocked."""
        result = tcpa_service.validate_outreach("123", org_id=1, channel="sms")

        assert result.allowed is False
        assert "Invalid phone number" in result.blockers

    @patch.object(TCPAComplianceService, "check_frequency_limit", return_value=False)
    @patch.object(TCPAComplianceService, "check_quiet_hours", return_value=False)
    @patch.object(TCPAComplianceService, "check_dnc_list", return_value=True)
    @patch.object(
        TCPAComplianceService,
        "_check_consent",
        return_value=TCPACheckResult(allowed=True, reason="OK"),
    )
    def test_consent_but_on_dnc(self, mock_consent, mock_dnc, mock_quiet, mock_freq, tcpa_service):
        """Even with consent, DNC list blocks outreach."""
        result = tcpa_service.validate_outreach("555-123-4567", org_id=1, channel="sms")

        assert result.allowed is False
        assert any("Do Not Contact" in b for b in result.blockers)


# =============================================================================
# PHONE NORMALIZATION TESTS
# =============================================================================


class TestPhoneNormalization:
    """Test phone number normalization edge cases."""

    def test_normalize_with_dashes(self, tcpa_service):
        """Phone with dashes is normalized to digits."""
        assert tcpa_service._normalize("555-123-4567") == "15551234567"

    def test_normalize_with_parens(self, tcpa_service):
        """Phone with parentheses is normalized."""
        assert tcpa_service._normalize("(555) 123-4567") == "15551234567"

    def test_normalize_with_country_code(self, tcpa_service):
        """Phone with +1 prefix is handled."""
        assert tcpa_service._normalize("+1 555-123-4567") == "15551234567"

    def test_normalize_already_digits(self, tcpa_service):
        """Already-normalized 11-digit number passes through."""
        assert tcpa_service._normalize("15551234567") == "15551234567"

    def test_normalize_short_number_rejected(self, tcpa_service):
        """Number with fewer than 10 digits returns empty string."""
        assert tcpa_service._normalize("555123") == ""

    def test_normalize_none(self, tcpa_service):
        """None input returns empty string."""
        assert tcpa_service._normalize(None) == ""

    def test_normalize_empty(self, tcpa_service):
        """Empty string returns empty string."""
        assert tcpa_service._normalize("") == ""


# =============================================================================
# CONSENT STATUS TESTS
# =============================================================================


class TestConsentStatus:
    """Test get_consent_status() full status report."""

    @patch.object(TCPAComplianceService, "check_dnc_list", return_value=False)
    @patch.object(
        TCPAComplianceService,
        "check_call_consent",
        return_value=TCPACheckResult(allowed=False, reason="No consent"),
    )
    @patch.object(
        TCPAComplianceService,
        "check_sms_consent",
        return_value=TCPACheckResult(
            allowed=True,
            reason="OK",
            consent_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            consent_type="portal",
        ),
    )
    def test_mixed_consent_status(self, mock_sms, mock_call, mock_dnc, tcpa_service):
        """Status report shows SMS consent but no call consent."""
        status = tcpa_service.get_consent_status("555-123-4567", org_id=1)

        assert status["sms_consent"] is True
        assert status["sms_consent_source"] == "portal"
        assert status["call_consent"] is False
        assert status["is_on_dnc"] is False


# =============================================================================
# FOLLOWUP SERVICE INTEGRATION TESTS
# =============================================================================


class TestFollowupServiceTCPAIntegration:
    """Test that FollowupAutomationService respects TCPA blocks."""

    @patch("services.smart_docs.followup_automation_service.TCPAComplianceService")
    def test_sms_blocked_by_tcpa(self, MockTCPA):
        """SMS step is skipped when TCPA validation fails."""
        from services.smart_docs.followup_automation_service import FollowupAutomationService
        from database.models.document_followup import (
            FollowupCampaign,
            CampaignStatus,
            DeliveryStatus,
        )

        # Set up mock TCPA service
        mock_tcpa_instance = MagicMock()
        mock_tcpa_instance.validate_outreach.return_value = OutreachValidation(
            allowed=False,
            blockers=["No sms consent found for this phone number"],
        )
        MockTCPA.return_value = mock_tcpa_instance

        # Set up mock DB and campaign
        mock_db = MagicMock()
        service = FollowupAutomationService(mock_db)

        # Create a mock campaign at SMS step
        campaign = MagicMock(spec=FollowupCampaign)
        campaign.id = 1
        campaign.status = CampaignStatus.ACTIVE
        campaign.current_step = 0
        campaign.loan_id = 100
        campaign.borrower_id = 200
        campaign.organization_id = 1
        campaign.reminders_sent = 0
        campaign.step_config = [
            {"step": 1, "channel": "sms", "delay_hours": 0, "template": "gentle_reminder_sms", "action": "send_sms"},
        ]
        campaign.linked_request_ids = [1, 2]
        campaign.next_action_at = None

        # Mock _get_campaign to return our campaign
        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value={
            "borrower_name": "John Doe",
            "borrower_email": "john@example.com",
            "borrower_phone": "555-123-4567",
            "lo_name": "Jane LO",
            "lo_email": "jane@company.com",
            "lo_user_id": 10,
        })
        service._get_outstanding_documents = MagicMock(return_value=[
            {"request_id": 1, "title": "W-2"},
        ])

        result = service.execute_campaign_step(1)

        assert result["delivery_status"] == DeliveryStatus.FAILED.value
        assert "blocked_tcpa" in str(result.get("result", {}).get("status", ""))

    @patch("services.smart_docs.followup_automation_service.TCPAComplianceService")
    def test_call_blocked_by_tcpa(self, MockTCPA):
        """Call step is skipped when TCPA validation fails."""
        from services.smart_docs.followup_automation_service import FollowupAutomationService
        from database.models.document_followup import (
            FollowupCampaign,
            CampaignStatus,
            DeliveryStatus,
        )

        mock_tcpa_instance = MagicMock()
        mock_tcpa_instance.validate_outreach.return_value = OutreachValidation(
            allowed=False,
            blockers=["TCPA quiet hours: recipient local time is 10:30 PM"],
        )
        MockTCPA.return_value = mock_tcpa_instance

        mock_db = MagicMock()
        service = FollowupAutomationService(mock_db)

        campaign = MagicMock(spec=FollowupCampaign)
        campaign.id = 2
        campaign.status = CampaignStatus.ACTIVE
        campaign.current_step = 0
        campaign.loan_id = 100
        campaign.borrower_id = 200
        campaign.organization_id = 1
        campaign.reminders_sent = 0
        campaign.step_config = [
            {"step": 1, "channel": "call", "delay_hours": 0, "template": "call", "action": "schedule_call"},
        ]
        campaign.linked_request_ids = [1]
        campaign.next_action_at = None

        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value={
            "borrower_name": "John Doe",
            "borrower_email": "john@example.com",
            "borrower_phone": "555-123-4567",
            "lo_name": "Jane LO",
            "lo_email": "jane@company.com",
            "lo_user_id": 10,
        })
        service._get_outstanding_documents = MagicMock(return_value=[
            {"request_id": 1, "title": "Paystubs"},
        ])

        result = service.execute_campaign_step(2)

        assert result["delivery_status"] == DeliveryStatus.FAILED.value
        assert "blocked_tcpa" in str(result.get("result", {}).get("status", ""))

    @patch("services.smart_docs.followup_automation_service.TCPAComplianceService")
    def test_sms_allowed_when_tcpa_passes(self, MockTCPA):
        """SMS step proceeds when TCPA validation passes."""
        from services.smart_docs.followup_automation_service import FollowupAutomationService
        from database.models.document_followup import (
            FollowupCampaign,
            CampaignStatus,
        )

        mock_tcpa_instance = MagicMock()
        mock_tcpa_instance.validate_outreach.return_value = OutreachValidation(
            allowed=True,
            blockers=[],
            consent_info={"consent_date": "2026-01-01", "consent_source": "web_form"},
        )
        MockTCPA.return_value = mock_tcpa_instance

        mock_db = MagicMock()
        service = FollowupAutomationService(mock_db)

        campaign = MagicMock(spec=FollowupCampaign)
        campaign.id = 3
        campaign.status = CampaignStatus.ACTIVE
        campaign.current_step = 0
        campaign.loan_id = 100
        campaign.borrower_id = 200
        campaign.organization_id = 1
        campaign.reminders_sent = 0
        campaign.step_config = [
            {"step": 1, "channel": "sms", "delay_hours": 0, "template": "gentle_reminder_sms", "action": "send_sms"},
        ]
        campaign.linked_request_ids = [1]
        campaign.next_action_at = None

        service._get_campaign = MagicMock(return_value=campaign)
        service._get_borrower_info = MagicMock(return_value={
            "borrower_name": "John Doe",
            "borrower_email": "john@example.com",
            "borrower_phone": "555-123-4567",
            "lo_name": "Jane LO",
            "lo_email": "jane@company.com",
            "lo_user_id": 10,
        })
        service._get_outstanding_documents = MagicMock(return_value=[
            {"request_id": 1, "title": "W-2"},
        ])
        # Mock the actual SMS sender to succeed
        service._send_sms_reminder = MagicMock(return_value={
            "status": "sent",
            "channel": "sms",
            "recipient": "555-123-4567",
            "body": "Hi John, reminder...",
        })

        result = service.execute_campaign_step(3)

        # SMS should have been sent
        service._send_sms_reminder.assert_called_once()
        # Outreach should have been logged for frequency tracking
        mock_tcpa_instance.log_outreach.assert_called_once()


# =============================================================================
# OUTREACH LOGGING TESTS
# =============================================================================


class TestOutreachLogging:
    """Test outreach logging for frequency limiting."""

    def test_log_outreach_adds_record(self, tcpa_service, mock_db):
        """log_outreach adds an OutreachLog record."""
        tcpa_service.log_outreach(
            phone="555-123-4567",
            org_id=1,
            channel="sms",
            campaign_id=42,
        )

        mock_db.add.assert_called_once()
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.phone == "15551234567"
        assert added_obj.channel == "sms"
        assert added_obj.campaign_id == 42

    def test_log_outreach_invalid_phone_noop(self, tcpa_service, mock_db):
        """log_outreach with invalid phone does nothing."""
        tcpa_service.log_outreach(
            phone="",
            org_id=1,
            channel="sms",
        )

        mock_db.add.assert_not_called()
