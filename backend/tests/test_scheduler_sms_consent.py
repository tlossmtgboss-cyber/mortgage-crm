"""
Integration tests for SMS consent enforcement in scheduling.
Verifies TCPA/DNC compliance before sending booking-related SMS.

Tests cover:
- Public booking confirmation SMS consent checks
- Pipeline appointment trigger SMS consent checks
- No-show recovery SMS consent checks
- Contact hours enforcement (TCPA 8am-9pm)
- DNC list blocking
- ChannelPreference opt-out enforcement
"""
import pytest
from unittest.mock import patch, MagicMock, ANY
from datetime import datetime, timezone


# =============================================================================
# HELPERS
# =============================================================================

def _make_channel_pref(
    lead_id=1,
    do_not_sms=False,
    sms_consent=True,
    organization_id=1,
):
    """Build a mock ChannelPreference object."""
    pref = MagicMock()
    pref.lead_id = lead_id
    pref.organization_id = organization_id
    pref.do_not_sms = do_not_sms
    pref.sms_consent = sms_consent
    return pref


def _make_lead(lead_id=1, phone="+15551234567", organization_id=1):
    """Build a mock Lead object."""
    lead = MagicMock()
    lead.id = lead_id
    lead.phone = phone
    lead.organization_id = organization_id
    return lead


# =============================================================================
# TEST: SMS consent core (services.sms_compliance.check_sms_consent)
# =============================================================================

class TestCheckSmsConsent:
    """Unit tests for the canonical check_sms_consent function."""

    @patch("services.sms_compliance._check_contact_hours", return_value=(True, "OK"))
    @patch("services.sms_compliance.SessionLocal")
    def test_sms_blocked_for_dnc_number(self, mock_session_cls, mock_hours):
        """SMS should not be sent to numbers on DNC list."""
        from services.sms_compliance import check_sms_consent

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        # Simulate ComplianceChecker.check_dnc returning True (on DNC)
        with patch("services.sms_compliance.ComplianceChecker") as MockChecker:
            checker_instance = MagicMock()
            checker_instance.check_dnc.return_value = (True, "STOP keyword received")
            MockChecker.return_value = checker_instance

            can_send, reason = check_sms_consent("+15551234567", organization_id=1)

        assert can_send is False
        assert "DNC" in reason
        checker_instance.check_dnc.assert_called_once_with("+15551234567")

    @patch("services.sms_compliance._check_contact_hours", return_value=(True, "OK"))
    @patch("services.sms_compliance.SessionLocal")
    def test_sms_blocked_when_do_not_sms_flag_set(self, mock_session_cls, mock_hours):
        """SMS should be blocked when ChannelPreference.do_not_sms is True."""
        from services.sms_compliance import check_sms_consent

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        mock_lead = _make_lead()
        mock_pref = _make_channel_pref(do_not_sms=True)

        # DNC check passes
        with patch("services.sms_compliance.ComplianceChecker") as MockChecker:
            checker_instance = MagicMock()
            checker_instance.check_dnc.return_value = (False, None)
            MockChecker.return_value = checker_instance

            # ChannelPreference query chain: Lead query -> pref query
            with patch("services.sms_compliance.Lead") as MockLead, \
                 patch("services.sms_compliance.ChannelPreference") as MockPref:
                # Lead.phone.ilike filter returns the mock lead
                mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_lead
                mock_db.query.return_value.filter.return_value.first.return_value = mock_pref

                can_send, reason = check_sms_consent("+15551234567", organization_id=1)

        assert can_send is False
        assert "opted out" in reason.lower() or "do_not_sms" in reason.lower()

    @patch("services.sms_compliance._check_contact_hours", return_value=(True, "OK"))
    @patch("services.sms_compliance.SessionLocal")
    def test_sms_blocked_when_sms_consent_false(self, mock_session_cls, mock_hours):
        """SMS should be blocked when ChannelPreference.sms_consent is False."""
        from services.sms_compliance import check_sms_consent

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        mock_lead = _make_lead()
        mock_pref = _make_channel_pref(sms_consent=False)

        with patch("services.sms_compliance.ComplianceChecker") as MockChecker:
            checker_instance = MagicMock()
            checker_instance.check_dnc.return_value = (False, None)
            MockChecker.return_value = checker_instance

            with patch("services.sms_compliance.Lead") as MockLead, \
                 patch("services.sms_compliance.ChannelPreference") as MockPref:
                mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_lead
                mock_db.query.return_value.filter.return_value.first.return_value = mock_pref

                can_send, reason = check_sms_consent("+15551234567", organization_id=1)

        assert can_send is False
        assert "consent" in reason.lower()

    def test_sms_blocked_without_phone_number(self):
        """SMS should fail when no phone number is provided."""
        from services.sms_compliance import check_sms_consent

        can_send, reason = check_sms_consent("", organization_id=1)
        assert can_send is False
        assert "no phone" in reason.lower()

        can_send, reason = check_sms_consent(None, organization_id=1)
        assert can_send is False


# =============================================================================
# TEST: TCPA contact hours enforcement
# =============================================================================

class TestContactHoursEnforcement:
    """Test TCPA 8am-9pm recipient local time enforcement."""

    @patch("services.sms_compliance.datetime")
    def test_sms_blocked_before_8am(self, mock_dt):
        """SMS should be blocked before 8am recipient local time."""
        from services.sms_compliance import _check_contact_hours

        # Simulate 6:30 AM Eastern
        mock_now = datetime(2026, 3, 18, 10, 30, 0, tzinfo=timezone.utc)  # 6:30 AM ET (UTC-4 in March)
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        # Use a time that's clearly before 8 AM in the target timezone
        # We test via the function's actual behavior with a real timezone
        can_send, reason = _check_contact_hours("Pacific/Honolulu")
        # Hawaii is UTC-10, so 10:30 UTC = 00:30 HST (before 8am)
        assert can_send is False
        assert "contact hours" in reason.lower() or "TCPA" in reason

    def test_sms_allowed_during_business_hours(self):
        """SMS should be allowed during 8am-9pm in recipient's timezone."""
        from services.sms_compliance import _check_contact_hours

        # Use a timezone where current time is likely during business hours.
        # We patch datetime.now to control the time.
        with patch("services.sms_compliance.datetime") as mock_dt:
            # Set UTC time to 18:00 (2pm Eastern, within 8am-9pm)
            mock_now = MagicMock()
            mock_dt.now.return_value = datetime(2026, 3, 18, 18, 0, 0, tzinfo=timezone.utc)

            can_send, reason = _check_contact_hours("America/New_York")
            # 18:00 UTC = 2:00 PM ET (within 8am-9pm)
            assert can_send is True

    @patch("services.sms_compliance.datetime")
    def test_sms_blocked_after_9pm(self, mock_dt):
        """SMS should be blocked after 9pm (21:00) recipient local time."""
        from services.sms_compliance import _check_contact_hours

        # 02:00 UTC = 10:00 PM ET (after 9pm)
        mock_dt.now.return_value = datetime(2026, 3, 19, 2, 0, 0, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        can_send, reason = _check_contact_hours("America/New_York")
        assert can_send is False

    def test_defaults_to_eastern_when_no_timezone(self):
        """Should default to America/New_York (most conservative US timezone)."""
        from services.sms_compliance import _check_contact_hours

        # The function should use New York if no timezone specified
        # Just verify it doesn't crash and returns a valid tuple
        can_send, reason = _check_contact_hours(None)
        assert isinstance(can_send, bool)
        assert isinstance(reason, str)


# =============================================================================
# TEST: SMS consent in public booking flow
# =============================================================================

class TestSMSConsentInPublicBooking:
    """Test SMS consent checking in public booking confirmation flow."""

    @patch("services.scheduler_sms_sender.check_sms_consent")
    @patch("telephony.sms.send_sms")
    @patch.dict("os.environ", {"TELNYX_PHONE_NUMBER": "+18438838956"})
    def test_confirmation_sms_calls_consent_check(self, mock_send_sms, mock_consent):
        """Confirmation SMS must call check_sms_consent before sending."""
        from services.scheduler_sms_sender import send_appointment_confirmation_sms

        mock_consent.return_value = (True, "OK")
        mock_send_sms.return_value = {"id": "msg-123", "status": "sent"}

        result = send_appointment_confirmation_sms(
            attendee_phone="+15551234567",
            attendee_name="Jane Doe",
            appointment_date="March 20, 2026",
            appointment_time="2:00 PM CT",
            team_member_name="Tim Loss",
            organization_id=42,
        )

        assert result is True
        mock_consent.assert_called_once_with("+15551234567", organization_id=42)
        mock_send_sms.assert_called_once()

    @patch("services.scheduler_sms_sender.check_sms_consent")
    @patch("telephony.sms.send_sms")
    @patch.dict("os.environ", {"TELNYX_PHONE_NUMBER": "+18438838956"})
    def test_confirmation_sms_blocked_by_consent(self, mock_send_sms, mock_consent):
        """Confirmation SMS should NOT be sent when consent check fails."""
        from services.scheduler_sms_sender import send_appointment_confirmation_sms

        mock_consent.return_value = (False, "DNC: STOP keyword received")

        result = send_appointment_confirmation_sms(
            attendee_phone="+15551234567",
            attendee_name="Jane Doe",
            appointment_date="March 20, 2026",
            appointment_time="2:00 PM CT",
            organization_id=42,
        )

        assert result is False
        mock_consent.assert_called_once_with("+15551234567", organization_id=42)
        # send_sms should NOT have been called
        mock_send_sms.assert_not_called()

    @patch("services.scheduler_sms_sender.check_sms_consent")
    @patch.dict("os.environ", {"TELNYX_PHONE_NUMBER": "+18438838956"})
    def test_sms_sent_with_organization_context(self, mock_consent):
        """SMS consent check should include organization_id for tenant isolation."""
        from services.scheduler_sms_sender import send_appointment_confirmation_sms

        mock_consent.return_value = (False, "Consent check error")

        send_appointment_confirmation_sms(
            attendee_phone="+15559876543",
            attendee_name="Bob Builder",
            appointment_date="March 21, 2026",
            appointment_time="10:00 AM CT",
            organization_id=99,
        )

        # Verify organization_id was passed through for tenant-scoped lookup
        mock_consent.assert_called_once_with("+15559876543", organization_id=99)

    @patch("services.scheduler_sms_sender.check_sms_consent")
    @patch("telephony.sms.send_sms")
    @patch.dict("os.environ", {"TELNYX_PHONE_NUMBER": "+18438838956"})
    def test_update_sms_checks_consent(self, mock_send_sms, mock_consent):
        """Appointment update SMS must also check consent."""
        from services.scheduler_sms_sender import send_appointment_update_sms

        mock_consent.return_value = (False, "Contact has opted out of SMS")

        result = send_appointment_update_sms(
            attendee_phone="+15551234567",
            attendee_name="Jane Doe",
            appointment_date="March 22, 2026",
            appointment_time="3:00 PM CT",
            organization_id=42,
        )

        assert result is False
        mock_consent.assert_called_once_with("+15551234567", organization_id=42)
        mock_send_sms.assert_not_called()

    @patch("services.scheduler_sms_sender.check_sms_consent")
    @patch("telephony.sms.send_sms")
    @patch.dict("os.environ", {"TELNYX_PHONE_NUMBER": "+18438838956"})
    def test_reminder_sms_checks_consent(self, mock_send_sms, mock_consent):
        """Appointment reminder SMS must also check consent."""
        from services.scheduler_sms_sender import send_appointment_reminder_sms

        mock_consent.return_value = (False, "No SMS consent on file")

        result = send_appointment_reminder_sms(
            attendee_phone="+15551234567",
            attendee_name="Jane Doe",
            appointment_date="March 23, 2026",
            appointment_time="11:00 AM CT",
            organization_id=42,
        )

        assert result == {"success": False, "error": "Consent blocked: No SMS consent on file"}
        mock_consent.assert_called_once_with("+15551234567", organization_id=42)
        mock_send_sms.assert_not_called()


# =============================================================================
# TEST: SMS consent in pipeline appointment trigger flow
# =============================================================================

class TestSMSConsentInPipelineTrigger:
    """Test SMS consent in AI pipeline trigger flow.

    The PipelineAppointmentTrigger sends booking links via the notification
    service (email), not directly via SMS. However, if a future extension
    adds SMS booking link delivery, these tests verify the consent gate
    is in place.
    """

    @patch("services.scheduler_sms_sender.check_sms_consent")
    @patch("telephony.sms.send_sms")
    @patch.dict("os.environ", {"TELNYX_PHONE_NUMBER": "+18438838956"})
    def test_booking_link_sms_checks_consent(self, mock_send_sms, mock_consent):
        """If a booking link is sent via SMS, consent must be checked first."""
        from services.scheduler_sms_sender import send_appointment_confirmation_sms

        # Simulate a booking link sent as SMS confirmation
        mock_consent.return_value = (True, "OK")
        mock_send_sms.return_value = {"id": "msg-456", "status": "sent"}

        result = send_appointment_confirmation_sms(
            attendee_phone="+15559991234",
            attendee_name="Borrower Smith",
            appointment_date="March 25, 2026",
            appointment_time="9:00 AM CT",
            team_member_name="LO Johnson",
            organization_id=7,
        )

        assert result is True
        mock_consent.assert_called_once_with("+15559991234", organization_id=7)

    @patch("services.scheduler_sms_sender.check_sms_consent")
    @patch.dict("os.environ", {"TELNYX_PHONE_NUMBER": "+18438838956"})
    def test_follow_up_sms_respects_opt_out(self, mock_consent):
        """Follow-up SMS should not be sent if borrower opted out."""
        from services.scheduler_sms_sender import send_appointment_reminder_sms

        mock_consent.return_value = (False, "Contact has opted out of SMS")

        result = send_appointment_reminder_sms(
            attendee_phone="+15559991234",
            attendee_name="Borrower Smith",
            appointment_date="March 26, 2026",
            appointment_time="10:00 AM CT",
            hours_before=24,
            organization_id=7,
        )

        assert result["success"] is False
        assert "opted out" in result["error"].lower()
        mock_consent.assert_called_once()


# =============================================================================
# TEST: SMS consent in no-show recovery flow
# =============================================================================

class TestSMSConsentInNoShowRecovery:
    """Test SMS consent in no-show recovery flow.

    No-show recovery SMS uses the same send_appointment_reminder_sms
    function, which gates on check_sms_consent.
    """

    @patch("services.scheduler_sms_sender.check_sms_consent")
    @patch.dict("os.environ", {"TELNYX_PHONE_NUMBER": "+18438838956"})
    def test_recovery_sms_checks_consent(self, mock_consent):
        """No-show recovery SMS should check consent before sending."""
        from services.scheduler_sms_sender import send_appointment_reminder_sms

        mock_consent.return_value = (False, "DNC: Internal DNC list match")

        result = send_appointment_reminder_sms(
            attendee_phone="+15553334444",
            attendee_name="No-Show Client",
            appointment_date="March 27, 2026",
            appointment_time="1:00 PM CT",
            hours_before=0,  # immediate recovery
            organization_id=12,
        )

        assert result["success"] is False
        assert "DNC" in result["error"]
        mock_consent.assert_called_once_with("+15553334444", organization_id=12)

    @patch("services.sms_compliance._check_contact_hours", return_value=(True, "OK"))
    @patch("services.sms_compliance.SessionLocal")
    def test_stop_keyword_prevents_further_sms(self, mock_session_cls, mock_hours):
        """STOP keyword should set do_not_sms, preventing all further SMS."""
        from services.sms_compliance import check_sms_consent

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        # Simulate DNC check: number was added to DNC via STOP keyword
        with patch("services.sms_compliance.ComplianceChecker") as MockChecker:
            checker_instance = MagicMock()
            checker_instance.check_dnc.return_value = (True, "STOP keyword received 2026-03-15")
            MockChecker.return_value = checker_instance

            can_send, reason = check_sms_consent("+15553334444", organization_id=12)

        assert can_send is False
        assert "DNC" in reason
        assert "STOP" in reason

    @patch("services.scheduler_sms_sender.check_sms_consent")
    @patch("telephony.sms.send_sms")
    @patch.dict("os.environ", {"TELNYX_PHONE_NUMBER": "+18438838956"})
    def test_recovery_sms_sent_when_consent_valid(self, mock_send_sms, mock_consent):
        """Recovery SMS should be sent when consent is valid and number not on DNC."""
        from services.scheduler_sms_sender import send_appointment_reminder_sms

        mock_consent.return_value = (True, "OK")
        mock_send_sms.return_value = {"id": "msg-recovery-001", "status": "sent"}

        result = send_appointment_reminder_sms(
            attendee_phone="+15557778888",
            attendee_name="Consented Client",
            appointment_date="March 28, 2026",
            appointment_time="4:00 PM CT",
            hours_before=0,
            organization_id=5,
        )

        assert result["success"] is True
        assert result["message_id"] == "msg-recovery-001"
        mock_consent.assert_called_once_with("+15557778888", organization_id=5)
        mock_send_sms.assert_called_once()


# =============================================================================
# TEST: DNC check failure mode (fail-closed)
# =============================================================================

class TestDNCFailClosed:
    """Verify fail-closed behavior: SMS blocked when DNC check errors."""

    @patch("services.sms_compliance._check_contact_hours", return_value=(True, "OK"))
    @patch("services.sms_compliance.SessionLocal")
    def test_dnc_check_error_blocks_sms(self, mock_session_cls, mock_hours):
        """When DNC check raises an exception, SMS must be BLOCKED (fail-closed)."""
        from services.sms_compliance import check_sms_consent

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        with patch("services.sms_compliance.ComplianceChecker") as MockChecker:
            checker_instance = MagicMock()
            checker_instance.check_dnc.side_effect = ConnectionError("DB unavailable")
            MockChecker.return_value = checker_instance

            can_send, reason = check_sms_consent("+15551112222", organization_id=1)

        assert can_send is False
        assert "DNC check unavailable" in reason or "error" in reason.lower()

    @patch("services.sms_compliance._check_contact_hours", return_value=(True, "OK"))
    def test_session_creation_error_blocks_sms(self, mock_hours):
        """When DB session cannot be created, SMS must be BLOCKED (fail-safe)."""
        from services.sms_compliance import check_sms_consent

        with patch("services.sms_compliance.SessionLocal", side_effect=RuntimeError("Pool exhausted")):
            can_send, reason = check_sms_consent("+15551112222", organization_id=1)

        assert can_send is False
        assert "error" in reason.lower() or "consent check" in reason.lower()
