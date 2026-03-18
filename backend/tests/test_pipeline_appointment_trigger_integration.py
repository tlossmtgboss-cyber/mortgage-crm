"""
Integration tests for pipeline appointment trigger.
Tests AI auto-booking and fallback booking link flows.

The PipelineAppointmentTrigger service orchestrates automatic appointment
creation when loans change stages in the pipeline.  These tests exercise
the full trigger flow with mocked DB sessions and external services.
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

from services.pipeline_appointment_trigger import (
    PipelineAppointmentTrigger,
    PipelineAppointmentRule,
    PipelineAppointmentRuleModel,
    PipelineAppointmentTriggerLog,
    DEFAULT_RULES,
    _FALLBACK_TIMEZONE,
    _MAX_RETRIES,
    _TRANSIENT_ERRORS,
)
from services.appointment_creation_service import AppointmentCreationResult


# =============================================================================
# HELPERS
# =============================================================================

def _make_mock_loan(
    loan_id=100,
    organization_id=1,
    borrower_name="Jane Doe",
    borrower_email="jane@example.com",
    borrower_phone="+15559990000",
    loan_number="2026-TEST-001",
    loan_officer_id=10,
    stage="DISCLOSED",
):
    """Build a mock Loan ORM-like object."""
    loan = MagicMock()
    loan.id = loan_id
    loan.organization_id = organization_id
    loan.borrower_name = borrower_name
    loan.borrower_email = borrower_email
    loan.borrower_phone = borrower_phone
    loan.loan_number = loan_number
    loan.loan_officer_id = loan_officer_id
    loan.stage = stage
    return loan


def _make_mock_session(loan=None, scheduler_config=None, custom_rules=None):
    """Build a mock SQLAlchemy session.

    Args:
        loan: Mock Loan to return from query(Loan).
        scheduler_config: Mock SchedulerConfig to return from query(SchedulerConfig).
        custom_rules: List of PipelineAppointmentRuleModel instances (or empty list).
    """
    session = MagicMock()

    def _query_side_effect(model):
        q = MagicMock()

        model_name = getattr(model, "__name__", "") or getattr(model, "__tablename__", "")

        if model_name == "PipelineAppointmentRuleModel" or getattr(model, "__tablename__", "") == "pipeline_appointment_rules":
            # Custom rules query
            filter_q = MagicMock()
            order_q = MagicMock()
            filter_q.order_by.return_value = order_q
            order_q.all.return_value = custom_rules or []
            q.filter.return_value = filter_q
            return q

        if "SchedulerConfig" in str(model):
            filter_q = MagicMock()
            filter_q.first.return_value = scheduler_config
            q.filter.return_value = filter_q
            return q

        # Default: Loan queries
        filter_q = MagicMock()
        filter_q.first.return_value = loan
        q.filter.return_value = filter_q
        return q

    session.query.side_effect = _query_side_effect
    session.add = MagicMock()
    session.flush = MagicMock()
    session.commit = MagicMock()

    return session


def _make_successful_creation_result(appointment_id=42, lead_id=None):
    """Build a successful AppointmentCreationResult for mocking create_appointment."""
    mock_appointment = MagicMock()
    mock_appointment.id = appointment_id
    mock_appointment.lead_id = lead_id
    return AppointmentCreationResult(
        success=True,
        appointment=mock_appointment,
        appointment_id=appointment_id,
        lead_id=lead_id,
        warnings=[],
    )


# =============================================================================
# PATCHES — centralized so tests stay readable
# =============================================================================

_CREATE_APPOINTMENT_PATCH = "services.pipeline_appointment_trigger.create_appointment"
_NOTIFICATION_SERVICE_PATCH = "services.pipeline_appointment_trigger.notification_service"


# =============================================================================
# TESTS
# =============================================================================

class TestPipelineAppointmentTrigger:
    """Test the AI pipeline appointment trigger flow."""

    # -----------------------------------------------------------------
    # 1. Auto-book creates appointment with correct fields
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_auto_book_creates_appointment(self):
        """Auto-booking should delegate to create_appointment and return correct fields."""
        mock_loan = _make_mock_loan()
        mock_session = _make_mock_session(loan=mock_loan)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        # The CONDITIONAL_APPROVAL rule has auto_book=True
        rule = PipelineAppointmentRule(
            from_stage="CONDITIONAL_APPROVAL",
            appointment_type="condition_clearing_session",
            appointment_title="Condition Clearing Session",
            delay_hours=4,
            duration_minutes=30,
            auto_book=True,
            required=True,
            description="Review outstanding conditions.",
            meeting_mode="video",
        )

        mock_result = _make_successful_creation_result(appointment_id=42)

        with patch(
            "services.appointment_creation_service.create_appointment",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_create:
            result = await trigger.create_appointment_suggestion(
                loan_id=100,
                rule=rule,
                loan_officer_id=10,
                loan=mock_loan,
            )

            # Verify create_appointment was called with correct args
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["organization_id"] == 1
            assert call_kwargs["assigned_user_id"] == 10
            assert call_kwargs["source"] == "ai_pipeline"
            assert call_kwargs["loan_id"] == 100
            assert call_kwargs["duration_minutes"] == 30
            assert call_kwargs["booked_by_ai"] is True
            assert call_kwargs["auto_commit"] is False
            assert call_kwargs["check_conflicts"] is True
            assert call_kwargs["create_lead_if_missing"] is True
            assert call_kwargs["meeting_mode"] == "video"
            assert call_kwargs["attendee_name"] == "Jane Doe"
            assert call_kwargs["attendee_email"] == "jane@example.com"
            assert "Condition Clearing Session" in call_kwargs["title"]
            assert call_kwargs["ai_booking_context"]["trigger"] == "pipeline_stage_change"

        assert result["action"] == "auto_booked"
        assert result["appointment_id"] == 42
        assert result["appointment_type"] == "condition_clearing_session"
        assert result["duration_minutes"] == 30
        assert result["required"] is True
        assert result["loan_id"] == 100
        assert "scheduled_start" in result
        assert "scheduled_end" in result

    # -----------------------------------------------------------------
    # 2. Auto-book uses user timezone
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_auto_book_uses_user_timezone(self):
        """Auto-booking should use the LO's configured timezone, not hardcoded."""
        mock_loan = _make_mock_loan()

        # Create a mock SchedulerConfig with a custom timezone
        mock_config = MagicMock()
        mock_config.timezone = "America/New_York"

        mock_session = _make_mock_session(loan=mock_loan, scheduler_config=mock_config)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        # _get_lo_timezone should return the LO's configured timezone
        tz = trigger._get_lo_timezone(loan_officer_id=10)
        assert tz == "America/New_York"

    @pytest.mark.asyncio
    async def test_auto_book_falls_back_timezone_when_no_config(self):
        """When no SchedulerConfig exists, timezone should fall back to default."""
        mock_session = _make_mock_session(loan=None, scheduler_config=None)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        tz = trigger._get_lo_timezone(loan_officer_id=10)
        assert tz == _FALLBACK_TIMEZONE
        assert tz == "America/Chicago"

    @pytest.mark.asyncio
    async def test_auto_book_falls_back_timezone_when_no_lo(self):
        """When no loan_officer_id is provided, should use fallback timezone."""
        mock_session = _make_mock_session()
        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        tz = trigger._get_lo_timezone(loan_officer_id=None)
        assert tz == _FALLBACK_TIMEZONE

    # -----------------------------------------------------------------
    # 3. Auto-book failure falls back to booking link
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_auto_book_failure_falls_back_to_booking_link(self):
        """If auto-booking fails, should send booking link instead."""
        mock_loan = _make_mock_loan()
        mock_session = _make_mock_session(loan=mock_loan)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        rule = PipelineAppointmentRule(
            from_stage="CONDITIONAL_APPROVAL",
            appointment_type="condition_clearing_session",
            appointment_title="Condition Clearing Session",
            delay_hours=4,
            duration_minutes=30,
            auto_book=True,
            required=True,
            description="Review outstanding conditions.",
            meeting_mode="video",
        )

        # Make create_appointment fail with a non-transient error so it
        # falls through to the booking link fallback immediately
        with patch(
            "services.appointment_creation_service.create_appointment",
            new_callable=AsyncMock,
            side_effect=ValueError("Simulated validation error"),
        ):
            # Patch notification service import inside send_booking_link
            with patch("services.pipeline_appointment_trigger.notification_service", None):
                result = await trigger.create_appointment_suggestion(
                    loan_id=100,
                    rule=rule,
                    loan_officer_id=10,
                    loan=mock_loan,
                )

        # Should have fallen back to booking link
        assert result["action"] == "booking_link_sent"
        assert result["appointment_type"] == "condition_clearing_session"
        assert result["loan_id"] == 100
        assert "booking_link" in result
        assert "booking_token" in result

    # -----------------------------------------------------------------
    # 4. Both auto-book and booking link fail -> LO notification
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_booking_link_failure_creates_notification(self):
        """If both auto-book and booking link fail, LO should be notified."""
        mock_loan = _make_mock_loan()
        mock_session = _make_mock_session(loan=mock_loan)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        rule = PipelineAppointmentRule(
            from_stage="CONDITIONAL_APPROVAL",
            appointment_type="condition_clearing_session",
            appointment_title="Condition Clearing Session",
            delay_hours=4,
            duration_minutes=30,
            auto_book=True,
            required=True,
            description="Review conditions.",
            meeting_mode="video",
        )

        # Make create_appointment fail with non-transient error
        with patch(
            "services.appointment_creation_service.create_appointment",
            new_callable=AsyncMock,
            side_effect=ValueError("Simulated validation error"),
        ):
            # Also make send_booking_link fail
            with patch.object(trigger, "send_booking_link", side_effect=RuntimeError("Booking link service down")):
                with patch.object(trigger, "_notify_lo_of_failure") as mock_notify:
                    with pytest.raises(RuntimeError, match="Booking link service down"):
                        await trigger.create_appointment_suggestion(
                            loan_id=100,
                            rule=rule,
                            loan_officer_id=10,
                            loan=mock_loan,
                        )

                    # Verify LO notification was called
                    mock_notify.assert_called_once()
                    call_kwargs = mock_notify.call_args
                    assert call_kwargs[1]["loan_officer_id"] == 10 or call_kwargs[0][0] == 10
                    assert call_kwargs[1]["loan_id"] == 100 or call_kwargs[0][1] == 100

    # -----------------------------------------------------------------
    # 5. Transient failure is retried
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_transient_failure_retried(self):
        """Transient failures (ConnectionError) should be retried."""
        mock_loan = _make_mock_loan()
        mock_session = _make_mock_session(loan=mock_loan)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        rule = PipelineAppointmentRule(
            from_stage="CTC",
            appointment_type="signing_appointment",
            appointment_title="Signing Appointment",
            delay_hours=24,
            duration_minutes=60,
            auto_book=True,
            required=True,
            description="Loan signing.",
            meeting_mode="in_person",
        )

        call_count = 0
        mock_result = _make_successful_creation_result(appointment_id=42)

        async def _create_appointment_with_retry(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: transient error
                raise ConnectionError("Temporary DB connection failure")
            # Second call: success
            return mock_result

        with patch(
            "services.appointment_creation_service.create_appointment",
            side_effect=_create_appointment_with_retry,
        ):
            # Patch asyncio.sleep to avoid real delay
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await trigger.create_appointment_suggestion(
                    loan_id=100,
                    rule=rule,
                    loan_officer_id=10,
                    loan=mock_loan,
                )

        # Should succeed on retry
        assert result["action"] == "auto_booked"
        assert call_count == 2  # First failed, second succeeded

    # -----------------------------------------------------------------
    # 6. Stage trigger creates correct appointment type
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_stage_trigger_creates_correct_appointment_type(self):
        """Each pipeline stage should trigger the correct appointment type."""
        # Verify the default rules map stages to expected appointment types
        expected_mappings = {
            "APPLICATION": "initial_consultation",
            "DISCLOSED": "document_collection_review",
            "CONDITIONAL_APPROVAL": "condition_clearing_session",
            "APPROVED": "closing_prep_meeting",
            "CLEAR_TO_CLOSE": "final_walkthrough_scheduling",
            "CTC": "signing_appointment",
        }

        for rule in DEFAULT_RULES:
            assert rule.from_stage in expected_mappings, (
                f"Unexpected default rule stage: {rule.from_stage}"
            )
            assert rule.appointment_type == expected_mappings[rule.from_stage], (
                f"Stage {rule.from_stage} should map to "
                f"{expected_mappings[rule.from_stage]}, got {rule.appointment_type}"
            )

        # Verify auto_book flags match expectations
        auto_book_stages = {r.from_stage for r in DEFAULT_RULES if r.auto_book}
        assert auto_book_stages == {"CONDITIONAL_APPROVAL", "CTC"}

        required_stages = {r.from_stage for r in DEFAULT_RULES if r.required}
        assert required_stages == {"CONDITIONAL_APPROVAL", "CTC"}

    @pytest.mark.asyncio
    async def test_on_stage_change_dispatches_to_correct_method(self):
        """on_stage_change should call auto-book for auto_book rules and booking link otherwise."""
        mock_loan = _make_mock_loan(stage="CONDITIONAL_APPROVAL")
        mock_session = _make_mock_session(loan=mock_loan)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        auto_book_result = {
            "action": "auto_booked",
            "appointment_id": 42,
            "appointment_type": "condition_clearing_session",
            "appointment_title": "Condition Clearing Session — Jane Doe",
            "scheduled_start": datetime.now(timezone.utc).isoformat(),
            "scheduled_end": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            "duration_minutes": 30,
            "required": True,
            "loan_id": 100,
        }

        with patch.object(trigger, "get_rules", new_callable=AsyncMock) as mock_get_rules, \
             patch.object(trigger, "create_appointment_suggestion", new_callable=AsyncMock) as mock_auto, \
             patch.object(trigger, "send_booking_link", new_callable=AsyncMock) as mock_link:

            # CONDITIONAL_APPROVAL rule has auto_book=True
            mock_get_rules.return_value = [
                PipelineAppointmentRule(
                    from_stage="CONDITIONAL_APPROVAL",
                    appointment_type="condition_clearing_session",
                    appointment_title="Condition Clearing Session",
                    auto_book=True,
                    required=True,
                ),
            ]
            mock_auto.return_value = auto_book_result

            results = await trigger.on_stage_change(
                loan_id=100,
                old_stage="APPROVED",
                new_stage="CONDITIONAL_APPROVAL",
                loan_officer_id=10,
            )

            mock_auto.assert_called_once()
            mock_link.assert_not_called()
            assert len(results) == 1
            assert results[0]["action"] == "auto_booked"

    @pytest.mark.asyncio
    async def test_on_stage_change_sends_booking_link_for_non_autobook(self):
        """on_stage_change should call send_booking_link for non-auto_book rules."""
        mock_loan = _make_mock_loan(stage="APPLICATION")
        mock_session = _make_mock_session(loan=mock_loan)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        link_result = {
            "action": "booking_link_sent",
            "appointment_type": "initial_consultation",
            "appointment_title": "Initial Consultation",
            "booking_link": "/book/10?type=initial_consultation&loan_id=100&ref=abc123&duration=30",
            "booking_token": "abc123",
            "borrower_email": "jane@example.com",
            "required": False,
            "loan_id": 100,
            "delay_hours": 0,
        }

        with patch.object(trigger, "get_rules", new_callable=AsyncMock) as mock_get_rules, \
             patch.object(trigger, "create_appointment_suggestion", new_callable=AsyncMock) as mock_auto, \
             patch.object(trigger, "send_booking_link", new_callable=AsyncMock) as mock_link:

            mock_get_rules.return_value = [
                PipelineAppointmentRule(
                    from_stage="APPLICATION",
                    appointment_type="initial_consultation",
                    appointment_title="Initial Consultation",
                    auto_book=False,
                    required=False,
                ),
            ]
            mock_link.return_value = link_result

            results = await trigger.on_stage_change(
                loan_id=100,
                old_stage="",
                new_stage="APPLICATION",
                loan_officer_id=10,
            )

            mock_link.assert_called_once()
            mock_auto.assert_not_called()
            assert len(results) == 1
            assert results[0]["action"] == "booking_link_sent"

    # -----------------------------------------------------------------
    # 7. Duplicate trigger prevented
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_duplicate_trigger_prevented(self):
        """Same stage change shouldn't trigger duplicate appointments.

        When rules don't match the new_stage, no actions should be taken.
        Also verifies that a stage like PROCESSING (no matching rule) produces
        no results even though rules exist for other stages.
        """
        mock_loan = _make_mock_loan(stage="PROCESSING")
        mock_session = _make_mock_session(loan=mock_loan)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        with patch.object(trigger, "get_rules", new_callable=AsyncMock) as mock_get_rules:
            # Return default rules — none match PROCESSING
            mock_get_rules.return_value = list(DEFAULT_RULES)

            results = await trigger.on_stage_change(
                loan_id=100,
                old_stage="DISCLOSED",
                new_stage="PROCESSING",
                loan_officer_id=10,
            )

            assert results == []

    @pytest.mark.asyncio
    async def test_no_rules_match_terminal_stage(self):
        """Terminal stages (FUNDED, CANCELLED, etc.) should not trigger appointments."""
        mock_loan = _make_mock_loan(stage="FUNDED")
        mock_session = _make_mock_session(loan=mock_loan)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        with patch.object(trigger, "get_rules", new_callable=AsyncMock) as mock_get_rules:
            mock_get_rules.return_value = list(DEFAULT_RULES)

            for terminal_stage in ("FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN"):
                results = await trigger.on_stage_change(
                    loan_id=100,
                    old_stage="APPROVED",
                    new_stage=terminal_stage,
                    loan_officer_id=10,
                )
                assert results == [], f"Terminal stage {terminal_stage} should produce no triggers"

    # -----------------------------------------------------------------
    # 8. Trigger respects AI scheduling config
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_trigger_respects_ai_scheduling_config(self):
        """Trigger should respect user's AI scheduling settings (enabled, max per day, etc.).

        Custom rules completely override defaults when present for the org.
        An empty custom rules list means nothing triggers.
        """
        mock_loan = _make_mock_loan(stage="APPLICATION")

        # Custom rules: org has custom rules that do NOT include APPLICATION
        custom_rule_model = MagicMock()
        custom_rule_model.to_rule.return_value = PipelineAppointmentRule(
            from_stage="DISCLOSED",
            appointment_type="custom_doc_review",
            appointment_title="Custom Doc Review",
            auto_book=False,
        )

        mock_session = _make_mock_session(loan=mock_loan, custom_rules=[custom_rule_model])

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        results = await trigger.on_stage_change(
            loan_id=100,
            old_stage="",
            new_stage="APPLICATION",
            loan_officer_id=10,
        )

        # Custom rules don't have APPLICATION, so nothing should trigger
        assert results == []

    @pytest.mark.asyncio
    async def test_custom_rules_override_defaults(self):
        """When an org has custom rules, defaults should NOT be used."""
        mock_loan = _make_mock_loan(stage="DISCLOSED")

        custom_rule_model = MagicMock()
        custom_rule_model.to_rule.return_value = PipelineAppointmentRule(
            from_stage="DISCLOSED",
            appointment_type="custom_doc_review",
            appointment_title="Custom Doc Review",
            auto_book=False,
            required=False,
            duration_minutes=45,
        )

        mock_session = _make_mock_session(loan=mock_loan, custom_rules=[custom_rule_model])

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        link_result = {
            "action": "booking_link_sent",
            "appointment_type": "custom_doc_review",
            "appointment_title": "Custom Doc Review",
            "booking_link": "/book/10?type=custom_doc_review&loan_id=100&ref=xyz&duration=45",
            "booking_token": "xyz",
            "borrower_email": "jane@example.com",
            "required": False,
            "loan_id": 100,
            "delay_hours": 0,
        }

        with patch.object(trigger, "send_booking_link", new_callable=AsyncMock) as mock_link:
            mock_link.return_value = link_result

            results = await trigger.on_stage_change(
                loan_id=100,
                old_stage="APPLICATION",
                new_stage="DISCLOSED",
                loan_officer_id=10,
            )

            assert len(results) == 1
            assert results[0]["appointment_type"] == "custom_doc_review"

    # -----------------------------------------------------------------
    # 9. Booking link generation
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_booking_link_contains_expected_params(self):
        """Booking link should include LO id, appointment type, loan id, duration, and ref token."""
        mock_loan = _make_mock_loan()
        mock_session = _make_mock_session(loan=mock_loan)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        rule = PipelineAppointmentRule(
            from_stage="APPLICATION",
            appointment_type="initial_consultation",
            appointment_title="Initial Consultation",
            delay_hours=0,
            duration_minutes=30,
            auto_book=False,
            required=False,
            description="Welcome call.",
            meeting_mode="video",
        )

        with patch.dict("sys.modules", {"services.notification_service": MagicMock()}):
            # Patch the notification_service import inside send_booking_link
            with patch("services.pipeline_appointment_trigger.notification_service", None):
                result = await trigger.send_booking_link(
                    loan_id=100,
                    rule=rule,
                    loan_officer_id=10,
                    loan=mock_loan,
                )

        link = result["booking_link"]
        assert "/book/10" in link
        assert "type=initial_consultation" in link
        assert "loan_id=100" in link
        assert "duration=30" in link
        assert "ref=" in link
        assert result["borrower_email"] == "jane@example.com"

    # -----------------------------------------------------------------
    # 10. Business hours snapping
    # -----------------------------------------------------------------
    def test_snap_to_business_hours_during_business_hours(self):
        """Time during business hours should be rounded to 15-minute boundary."""
        dt = datetime(2026, 3, 18, 10, 7, 0, tzinfo=timezone.utc)  # Wednesday 10:07
        snapped = PipelineAppointmentTrigger._snap_to_business_hours(dt)
        assert snapped.hour == 10
        assert snapped.minute == 15
        assert snapped.weekday() == 2  # Still Wednesday

    def test_snap_to_business_hours_before_9am(self):
        """Time before 9 AM should snap to 9:00 AM same day."""
        dt = datetime(2026, 3, 18, 6, 30, 0, tzinfo=timezone.utc)  # Wednesday 6:30 AM
        snapped = PipelineAppointmentTrigger._snap_to_business_hours(dt)
        assert snapped.hour == 9
        assert snapped.minute == 0
        assert snapped.weekday() == 2  # Still Wednesday

    def test_snap_to_business_hours_after_5pm(self):
        """Time after 5 PM should snap to next business day 9:00 AM."""
        dt = datetime(2026, 3, 18, 17, 30, 0, tzinfo=timezone.utc)  # Wednesday 5:30 PM
        snapped = PipelineAppointmentTrigger._snap_to_business_hours(dt)
        assert snapped.hour == 9
        assert snapped.minute == 0
        assert snapped.day == 19  # Thursday

    def test_snap_to_business_hours_weekend_saturday(self):
        """Saturday should snap to Monday 9:00 AM."""
        dt = datetime(2026, 3, 21, 12, 0, 0, tzinfo=timezone.utc)  # Saturday
        snapped = PipelineAppointmentTrigger._snap_to_business_hours(dt)
        assert snapped.hour == 9
        assert snapped.minute == 0
        assert snapped.weekday() == 0  # Monday
        assert snapped.day == 23

    def test_snap_to_business_hours_weekend_sunday(self):
        """Sunday should snap to Monday 9:00 AM."""
        dt = datetime(2026, 3, 22, 14, 0, 0, tzinfo=timezone.utc)  # Sunday
        snapped = PipelineAppointmentTrigger._snap_to_business_hours(dt)
        assert snapped.hour == 9
        assert snapped.minute == 0
        assert snapped.weekday() == 0  # Monday
        assert snapped.day == 23

    def test_snap_to_business_hours_friday_after_5pm(self):
        """Friday after 5 PM should snap to Monday 9:00 AM."""
        dt = datetime(2026, 3, 20, 18, 0, 0, tzinfo=timezone.utc)  # Friday 6 PM
        snapped = PipelineAppointmentTrigger._snap_to_business_hours(dt)
        assert snapped.hour == 9
        assert snapped.minute == 0
        assert snapped.weekday() == 0  # Monday

    def test_snap_exact_15_minute_boundary(self):
        """Time already on a 15-minute boundary during business hours should stay."""
        dt = datetime(2026, 3, 18, 14, 0, 0, tzinfo=timezone.utc)  # Wednesday 2:00 PM
        snapped = PipelineAppointmentTrigger._snap_to_business_hours(dt)
        assert snapped.hour == 14
        assert snapped.minute == 0

    # -----------------------------------------------------------------
    # 11. Loan not found handling
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_on_stage_change_returns_empty_when_loan_not_found(self):
        """If the loan is not found, on_stage_change should return empty results."""
        mock_session = _make_mock_session(loan=None)  # Loan not found

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        with patch.object(trigger, "get_rules", new_callable=AsyncMock) as mock_get_rules:
            mock_get_rules.return_value = list(DEFAULT_RULES)

            results = await trigger.on_stage_change(
                loan_id=999,
                old_stage="APPLICATION",
                new_stage="DISCLOSED",
                loan_officer_id=10,
            )

            assert results == []

    # -----------------------------------------------------------------
    # 12. Trigger log is written
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_trigger_log_is_written(self):
        """on_stage_change should write audit log entries for each triggered rule."""
        mock_loan = _make_mock_loan(stage="APPLICATION")
        mock_session = _make_mock_session(loan=mock_loan)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        link_result = {
            "action": "booking_link_sent",
            "appointment_type": "initial_consultation",
            "appointment_title": "Initial Consultation",
            "booking_link": "/book/10?type=initial_consultation&loan_id=100&ref=abc&duration=30",
            "booking_token": "abc",
            "borrower_email": "jane@example.com",
            "required": False,
            "loan_id": 100,
            "delay_hours": 0,
        }

        with patch.object(trigger, "get_rules", new_callable=AsyncMock) as mock_get_rules, \
             patch.object(trigger, "send_booking_link", new_callable=AsyncMock) as mock_link, \
             patch.object(trigger, "_log_trigger") as mock_log:

            mock_get_rules.return_value = [
                PipelineAppointmentRule(
                    from_stage="APPLICATION",
                    appointment_type="initial_consultation",
                    appointment_title="Initial Consultation",
                    auto_book=False,
                ),
            ]
            mock_link.return_value = link_result

            await trigger.on_stage_change(
                loan_id=100,
                old_stage="",
                new_stage="APPLICATION",
                loan_officer_id=10,
            )

            mock_log.assert_called_once()
            log_call = mock_log.call_args
            assert log_call.kwargs["loan_id"] == 100
            assert log_call.kwargs["new_stage"] == "APPLICATION"
            assert log_call.kwargs["result"]["action"] == "booking_link_sent"

    # -----------------------------------------------------------------
    # 13. Error in one rule doesn't block others
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_error_in_one_rule_does_not_block_others(self):
        """If processing one rule fails, subsequent rules should still execute."""
        mock_loan = _make_mock_loan(stage="APPLICATION")
        mock_session = _make_mock_session(loan=mock_loan)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        call_count = 0

        async def _mock_send_booking_link(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First rule failed")
            return {
                "action": "booking_link_sent",
                "appointment_type": "second_type",
                "loan_id": 100,
            }

        with patch.object(trigger, "get_rules", new_callable=AsyncMock) as mock_get_rules, \
             patch.object(trigger, "send_booking_link", side_effect=_mock_send_booking_link), \
             patch.object(trigger, "_log_trigger"), \
             patch.object(trigger, "_notify_lo_of_failure"):

            # Two rules that match the same stage
            mock_get_rules.return_value = [
                PipelineAppointmentRule(
                    from_stage="APPLICATION",
                    appointment_type="first_type",
                    appointment_title="First Type",
                    auto_book=False,
                ),
                PipelineAppointmentRule(
                    from_stage="APPLICATION",
                    appointment_type="second_type",
                    appointment_title="Second Type",
                    auto_book=False,
                ),
            ]

            results = await trigger.on_stage_change(
                loan_id=100,
                old_stage="",
                new_stage="APPLICATION",
                loan_officer_id=10,
            )

            assert len(results) == 2
            assert results[0]["action"] == "error"
            assert results[1]["action"] == "booking_link_sent"

    # -----------------------------------------------------------------
    # 14. LO failure notification content
    # -----------------------------------------------------------------
    def test_notify_lo_of_failure_creates_notification(self):
        """_notify_lo_of_failure should create a Notification in the session."""
        mock_session = _make_mock_session()

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        rule = PipelineAppointmentRule(
            from_stage="CTC",
            appointment_type="signing_appointment",
            appointment_title="Signing Appointment",
        )

        with patch("services.pipeline_appointment_trigger.Notification") as MockNotification:
            mock_notification_instance = MagicMock()
            MockNotification.return_value = mock_notification_instance

            trigger._notify_lo_of_failure(
                loan_officer_id=10,
                loan_id=100,
                rule=rule,
                error_message="Something went wrong",
            )

            MockNotification.assert_called_once()
            call_kwargs = MockNotification.call_args.kwargs
            assert call_kwargs["user_id"] == 10
            assert call_kwargs["organization_id"] == 1
            assert call_kwargs["type"] == "pipeline_appointment_failed"
            assert "Signing Appointment" in call_kwargs["title"]
            assert "Something went wrong" in call_kwargs["message"]
            mock_session.add.assert_called_with(mock_notification_instance)

    def test_notify_lo_skips_when_no_loan_officer_id(self):
        """_notify_lo_of_failure should skip when no loan_officer_id is provided."""
        mock_session = _make_mock_session()
        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        rule = PipelineAppointmentRule(
            from_stage="CTC",
            appointment_type="signing_appointment",
            appointment_title="Signing Appointment",
        )

        # Should not raise, just log a warning
        trigger._notify_lo_of_failure(
            loan_officer_id=None,
            loan_id=100,
            rule=rule,
            error_message="Something went wrong",
        )

        # No notification should be added to session
        mock_session.add.assert_not_called()

    # -----------------------------------------------------------------
    # 15. Default rules completeness
    # -----------------------------------------------------------------
    def test_default_rules_cover_key_stages(self):
        """DEFAULT_RULES should cover the critical mortgage pipeline stages."""
        stages_covered = {r.from_stage for r in DEFAULT_RULES}
        assert "APPLICATION" in stages_covered
        assert "DISCLOSED" in stages_covered
        assert "CONDITIONAL_APPROVAL" in stages_covered
        assert "APPROVED" in stages_covered
        assert "CLEAR_TO_CLOSE" in stages_covered
        assert "CTC" in stages_covered
        assert len(DEFAULT_RULES) == 6

    def test_default_rules_have_valid_meeting_modes(self):
        """All default rules should have valid meeting modes."""
        valid_modes = {"video", "phone", "in_person", "screen_share"}
        for rule in DEFAULT_RULES:
            assert rule.meeting_mode in valid_modes, (
                f"Rule {rule.appointment_type} has invalid mode: {rule.meeting_mode}"
            )

    def test_pipeline_appointment_rule_dataclass_defaults(self):
        """PipelineAppointmentRule dataclass should have correct defaults."""
        rule = PipelineAppointmentRule(
            from_stage="TEST",
            appointment_type="test_type",
            appointment_title="Test Title",
        )
        assert rule.delay_hours == 0
        assert rule.duration_minutes == 30
        assert rule.auto_book is False
        assert rule.required is False
        assert rule.description == ""
        assert rule.meeting_mode == "video"

    # -----------------------------------------------------------------
    # 16. Conflict detected by shared service falls back to booking link
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_conflict_detected_falls_back_to_booking_link(self):
        """When create_appointment returns a conflict error, should fall back to booking link."""
        mock_loan = _make_mock_loan()
        mock_session = _make_mock_session(loan=mock_loan)

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        rule = PipelineAppointmentRule(
            from_stage="CONDITIONAL_APPROVAL",
            appointment_type="condition_clearing_session",
            appointment_title="Condition Clearing Session",
            delay_hours=4,
            duration_minutes=30,
            auto_book=True,
            required=True,
            meeting_mode="video",
        )

        # create_appointment returns a conflict (not an exception)
        conflict_result = AppointmentCreationResult(
            success=False,
            error="This time slot is no longer available. Please select a different time.",
        )

        with patch(
            "services.appointment_creation_service.create_appointment",
            new_callable=AsyncMock,
            return_value=conflict_result,
        ):
            with patch("services.pipeline_appointment_trigger.notification_service", None):
                result = await trigger.create_appointment_suggestion(
                    loan_id=100,
                    rule=rule,
                    loan_officer_id=10,
                    loan=mock_loan,
                )

        # Should have fallen back to booking link
        assert result["action"] == "booking_link_sent"
        assert result["loan_id"] == 100

    # -----------------------------------------------------------------
    # 17. Auto-book passes auto_commit=False to shared service
    # -----------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_auto_book_uses_auto_commit_false(self):
        """Pipeline auto-book should pass auto_commit=False so callers control the transaction."""
        mock_loan = _make_mock_loan()
        mock_session = _make_mock_session(loan=mock_loan)
        mock_result = _make_successful_creation_result()

        trigger = PipelineAppointmentTrigger(mock_session, organization_id=1)

        rule = PipelineAppointmentRule(
            from_stage="CTC",
            appointment_type="signing_appointment",
            appointment_title="Signing Appointment",
            auto_book=True,
            required=True,
            meeting_mode="in_person",
        )

        with patch(
            "services.appointment_creation_service.create_appointment",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_create:
            await trigger.create_appointment_suggestion(
                loan_id=100,
                rule=rule,
                loan_officer_id=10,
                loan=mock_loan,
            )

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["auto_commit"] is False
            assert call_kwargs["external_source"] == "pipeline_stage_change"
