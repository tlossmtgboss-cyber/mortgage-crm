"""
Integration tests for appointment creation consistency across booking paths.

Verifies that all 3 booking paths produce consistent appointment records:
  1. Authenticated (POST /appointments) — appointments.py
  2. Public booking (POST /public/book/{slug}/confirm) — public_booking.py
  3. Pipeline AI trigger (PipelineAppointmentTrigger.create_appointment_suggestion) — pipeline_appointment_trigger.py

Architecture note (March 2026):
  All three paths now delegate to the unified appointment_creation_service.py,
  which handles the Appointment() constructor, conflict checking, duplicate
  detection, meeting link generation, audit logging, lead linking, and CRM
  activity logging.  These tests verify:
    1. The unified service sets all required fields on the Appointment.
    2. Each booking path calls the unified service (not a direct Appointment() call).
    3. Each path passes the correct control flags.
    4. Pipeline-specific behavior (business hours snapping, default rules).
"""

import ast
import inspect
import pytest
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# =============================================================================
# PATH CONSTANTS
# =============================================================================

_BACKEND_DIR = Path(__file__).parent.parent
_AUTHENTICATED_PATH = _BACKEND_DIR / "routes" / "scheduler" / "appointments.py"
_PUBLIC_BOOKING_PATH = _BACKEND_DIR / "routes" / "scheduler" / "public_booking.py"
_PIPELINE_TRIGGER_PATH = _BACKEND_DIR / "services" / "pipeline_appointment_trigger.py"
_UNIFIED_SERVICE_PATH = _BACKEND_DIR / "services" / "appointment_creation_service.py"


# =============================================================================
# HELPERS
# =============================================================================

def _extract_appointment_constructor_kwargs(source_path: Path) -> list[set[str]]:
    """Parse a Python source file and return sets of keyword argument names
    used in every ``Appointment(...)`` constructor call found in it.
    """
    source = source_path.read_text()
    tree = ast.parse(source, filename=str(source_path))

    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            is_appointment_call = False
            if isinstance(func, ast.Name) and func.id == "Appointment":
                is_appointment_call = True
            elif isinstance(func, ast.Attribute) and func.attr == "Appointment":
                is_appointment_call = True

            if is_appointment_call:
                kwarg_names = {kw.arg for kw in node.keywords if kw.arg is not None}
                if kwarg_names:
                    results.append(kwarg_names)

    return results


def _source_contains(path: Path, pattern: str) -> bool:
    """Check if the source file contains a pattern (case-sensitive)."""
    return pattern in path.read_text()


# Required fields that the unified service MUST set on Appointment()
REQUIRED_CORE_FIELDS = {
    "organization_id",
    "title",
    "scheduled_start",
    "scheduled_end",
    "duration_minutes",
    "status",
    "status_changed_at",
    "meeting_mode",
    "timezone",
}


# =============================================================================
# SOURCE FILE EXISTENCE GUARD
# =============================================================================

@pytest.fixture(autouse=True, scope="module")
def _verify_source_files_exist():
    """Fail fast if any of the source files are missing."""
    for path in (_AUTHENTICATED_PATH, _PUBLIC_BOOKING_PATH,
                 _PIPELINE_TRIGGER_PATH, _UNIFIED_SERVICE_PATH):
        assert path.exists(), f"Source file not found: {path}"


# =============================================================================
# TEST CLASS: Unified Service — Single Appointment Constructor
# =============================================================================

class TestUnifiedServiceFields:
    """Verify the unified appointment_creation_service.py sets all required
    fields on the Appointment() constructor.

    All three booking paths now delegate to this service, so verifying the
    service's Appointment() constructor is sufficient to cover all paths.
    """

    def test_unified_service_has_appointment_constructor(self):
        """The unified service must contain an Appointment() constructor call."""
        calls = _extract_appointment_constructor_kwargs(_UNIFIED_SERVICE_PATH)
        assert len(calls) > 0, (
            "appointment_creation_service.py must contain at least one "
            "Appointment() constructor call"
        )

    def test_unified_service_sets_required_core_fields(self):
        """The unified service Appointment() call must include all required fields."""
        calls = _extract_appointment_constructor_kwargs(_UNIFIED_SERVICE_PATH)
        assert len(calls) > 0, "No Appointment() call found in unified service"

        kwargs = calls[0]
        missing = REQUIRED_CORE_FIELDS - kwargs
        assert not missing, (
            f"Unified service Appointment() is missing required fields: {missing}"
        )

    def test_unified_service_sets_status_changed_at(self):
        """The unified service must set status_changed_at for timeline queries."""
        calls = _extract_appointment_constructor_kwargs(_UNIFIED_SERVICE_PATH)
        assert len(calls) > 0
        assert "status_changed_at" in calls[0], (
            "Unified service must set status_changed_at to prevent NULL values "
            "in status timeline queries"
        )

    def test_unified_service_sets_timezone(self):
        """The unified service must explicitly set timezone on the Appointment."""
        calls = _extract_appointment_constructor_kwargs(_UNIFIED_SERVICE_PATH)
        assert len(calls) > 0
        assert "timezone" in calls[0], (
            "Unified service must set timezone on the Appointment "
            "(resolved from SchedulerConfig or caller-provided)"
        )

    def test_unified_service_sets_attendee_fields(self):
        """The unified service must set attendee_name and attendee_email."""
        calls = _extract_appointment_constructor_kwargs(_UNIFIED_SERVICE_PATH)
        assert len(calls) > 0
        assert "attendee_name" in calls[0]
        assert "attendee_email" in calls[0]

    def test_unified_service_sets_ai_context_fields(self):
        """The unified service must set booked_by_ai and ai_booking_context."""
        calls = _extract_appointment_constructor_kwargs(_UNIFIED_SERVICE_PATH)
        assert len(calls) > 0
        assert "booked_by_ai" in calls[0]
        assert "ai_booking_context" in calls[0]

    def test_unified_service_does_conflict_checking(self):
        """The unified service must check for scheduling conflicts."""
        assert _source_contains(_UNIFIED_SERVICE_PATH, "_check_internal_conflict"), (
            "Unified service must call _check_internal_conflict (SELECT FOR UPDATE)"
        )

    def test_unified_service_does_duplicate_checking(self):
        """The unified service must check for duplicate bookings."""
        assert _source_contains(_UNIFIED_SERVICE_PATH, "_check_duplicate"), (
            "Unified service must call _check_duplicate"
        )

    def test_unified_service_generates_meeting_links(self):
        """The unified service must support meeting link generation."""
        assert _source_contains(_UNIFIED_SERVICE_PATH, "_generate_meeting_link"), (
            "Unified service must call _generate_meeting_link for video appointments"
        )

    def test_unified_service_writes_audit_log(self):
        """The unified service must write audit log entries."""
        assert _source_contains(_UNIFIED_SERVICE_PATH, "_write_audit_log"), (
            "Unified service must call _write_audit_log for compliance trail"
        )

    def test_unified_service_creates_leads(self):
        """The unified service must support lead creation/linking."""
        assert _source_contains(_UNIFIED_SERVICE_PATH, "_ensure_lead"), (
            "Unified service must call _ensure_lead for CRM integration"
        )

    def test_unified_service_creates_followup_tasks(self):
        """The unified service must create follow-up tasks."""
        assert _source_contains(_UNIFIED_SERVICE_PATH, "_create_followup_task"), (
            "Unified service must call _create_followup_task"
        )

    def test_unified_service_checks_cross_source_conflicts(self):
        """The unified service must support cross-source conflict checking."""
        assert _source_contains(_UNIFIED_SERVICE_PATH, "_check_cross_source_conflicts"), (
            "Unified service must call _check_cross_source_conflicts"
        )


# =============================================================================
# TEST CLASS: All Paths Delegate to Unified Service
# =============================================================================

class TestDelegationToUnifiedService:
    """Verify each booking path delegates to appointment_creation_service
    rather than constructing Appointment() directly.
    """

    def test_authenticated_path_does_not_construct_appointment_directly(self):
        """Authenticated path should delegate to unified service, not Appointment()."""
        calls = _extract_appointment_constructor_kwargs(_AUTHENTICATED_PATH)
        if calls:
            pytest.fail(
                "appointments.py should delegate to appointment_creation_service, "
                "not construct Appointment() directly. Found direct constructor calls."
            )

    def test_public_booking_does_not_construct_appointment_directly(self):
        """Public booking should delegate to unified service, not Appointment()."""
        calls = _extract_appointment_constructor_kwargs(_PUBLIC_BOOKING_PATH)
        assert len(calls) == 0, (
            "public_booking.py should delegate to appointment_creation_service, "
            "not construct Appointment() directly"
        )

    def test_pipeline_trigger_does_not_construct_appointment_directly(self):
        """Pipeline trigger should delegate to unified service, not Appointment()."""
        calls = _extract_appointment_constructor_kwargs(_PIPELINE_TRIGGER_PATH)
        assert len(calls) == 0, (
            "pipeline_appointment_trigger.py should delegate to "
            "appointment_creation_service, not construct Appointment() directly"
        )

    def test_public_booking_imports_unified_service(self):
        """Public booking must import create_appointment from the unified service."""
        assert _source_contains(
            _PUBLIC_BOOKING_PATH,
            "from services.appointment_creation_service import"
        ), "Public booking must import from appointment_creation_service"

    def test_pipeline_trigger_imports_unified_service(self):
        """Pipeline trigger must import create_appointment from the unified service."""
        assert _source_contains(
            _PIPELINE_TRIGGER_PATH,
            "from services.appointment_creation_service import create_appointment"
        ), "Pipeline trigger must import create_appointment from unified service"

    def test_public_booking_passes_timezone(self):
        """Public booking must pass timezone= to the unified service."""
        source = _PUBLIC_BOOKING_PATH.read_text()
        # Find _create_appointment_via_service calls and verify timezone= is passed
        assert "timezone=" in source, (
            "Public booking must pass timezone= to the unified service "
            "to avoid relying on model defaults"
        )

    def test_pipeline_trigger_passes_timezone(self):
        """Pipeline trigger must pass timezone= to the unified service."""
        source = _PIPELINE_TRIGGER_PATH.read_text()
        assert "timezone=" in source, (
            "Pipeline trigger must pass timezone= to the unified service"
        )

    def test_public_booking_passes_conflict_flags(self):
        """Public booking must enable conflict and cross-source checks."""
        source = _PUBLIC_BOOKING_PATH.read_text()
        assert "check_conflicts=True" in source
        assert "check_cross_source=True" in source

    def test_pipeline_trigger_passes_conflict_flags(self):
        """Pipeline trigger must enable conflict and cross-source checks."""
        source = _PIPELINE_TRIGGER_PATH.read_text()
        assert "check_conflicts=True" in source
        assert "check_cross_source=True" in source

    def test_pipeline_trigger_passes_meeting_link_flag(self):
        """Pipeline trigger must enable meeting link generation."""
        source = _PIPELINE_TRIGGER_PATH.read_text()
        assert "generate_meeting_link=True" in source

    def test_public_booking_passes_meeting_link_flag(self):
        """Public booking must enable meeting link generation."""
        source = _PUBLIC_BOOKING_PATH.read_text()
        assert "generate_meeting_link=True" in source


# =============================================================================
# TEST CLASS: Public Booking Post-Creation
# =============================================================================

class TestPublicBookingPostCreation:
    """Verify public booking path's post-creation side effects."""

    def test_public_booking_calls_scheduler_audit(self):
        """Public booking must call scheduler_audit for enterprise compliance."""
        assert _source_contains(
            _PUBLIC_BOOKING_PATH,
            "scheduler_audit.log_appointment_created"
        ), "Public booking must call scheduler_audit.log_appointment_created"

    def test_public_booking_sends_confirmation_email(self):
        """Public booking must send confirmation email."""
        assert _source_contains(
            _PUBLIC_BOOKING_PATH,
            "send_appointment_confirmation_email"
        ), "Public booking must send confirmation email"

    def test_public_booking_sends_confirmation_sms(self):
        """Public booking must send confirmation SMS when phone is provided."""
        assert _source_contains(
            _PUBLIC_BOOKING_PATH,
            "send_appointment_confirmation_sms"
        ), "Public booking must send confirmation SMS"

    def test_public_booking_creates_outlook_event(self):
        """Public booking must create Outlook calendar event."""
        assert _source_contains(
            _PUBLIC_BOOKING_PATH,
            "create_event_via_graph"
        ), "Public booking must create Outlook calendar event"

    def test_public_booking_increments_booking_count(self):
        """Public booking must atomically increment the booking link counter."""
        assert _source_contains(
            _PUBLIC_BOOKING_PATH,
            "booking_count"
        ), "Public booking must increment booking_count on the BookingLink"


# =============================================================================
# TEST CLASS: Pipeline Trigger Post-Creation
# =============================================================================

class TestPipelineTriggerPostCreation:
    """Verify pipeline trigger's post-creation side effects."""

    def test_pipeline_trigger_logs_trigger(self):
        """Pipeline trigger must log to pipeline_appointment_trigger_log."""
        assert _source_contains(
            _PIPELINE_TRIGGER_PATH,
            "_log_trigger"
        ), "Pipeline trigger must log to trigger_log table"

    def test_pipeline_trigger_calls_scheduler_audit(self):
        """Pipeline trigger must call scheduler_audit for AI bookings."""
        assert _source_contains(
            _PIPELINE_TRIGGER_PATH,
            "scheduler_audit"
        ), "Pipeline trigger must call scheduler_audit for AI bookings"

    def test_pipeline_trigger_notifies_lo_on_failure(self):
        """Pipeline trigger must notify the LO when auto-booking fails."""
        assert _source_contains(
            _PIPELINE_TRIGGER_PATH,
            "_notify_lo_of_failure"
        ), "Pipeline trigger must notify LO on auto-book failure"

    def test_pipeline_trigger_falls_back_to_booking_link(self):
        """Pipeline trigger must fall back to booking link when auto-book fails."""
        assert _source_contains(
            _PIPELINE_TRIGGER_PATH,
            "send_booking_link"
        ), "Pipeline trigger must fall back to send_booking_link"

    def test_pipeline_trigger_records_speed_to_lead(self):
        """Pipeline trigger must record speed-to-lead metrics."""
        assert _source_contains(
            _PIPELINE_TRIGGER_PATH,
            "_record_speed_to_lead"
        ), "Pipeline trigger must record speed-to-lead timing"

    def test_pipeline_trigger_passes_ai_context(self):
        """Pipeline trigger must pass booked_by_ai and ai_booking_context."""
        source = _PIPELINE_TRIGGER_PATH.read_text()
        assert "booked_by_ai=True" in source
        assert "ai_booking_context=" in source


# =============================================================================
# TEST CLASS: Pipeline Trigger Specific Behavior
# =============================================================================

class TestPipelineTriggerBehavior:
    """Tests specific to the PipelineAppointmentTrigger booking path."""

    def test_snap_to_business_hours_weekday_morning(self):
        """_snap_to_business_hours should keep times within 9 AM - 5 PM."""
        from services.pipeline_appointment_trigger import PipelineAppointmentTrigger

        # 7:30 AM on a Wednesday should snap to 9:00 AM
        dt = datetime(2026, 3, 18, 7, 30, tzinfo=timezone.utc)  # Wednesday
        snapped = PipelineAppointmentTrigger._snap_to_business_hours(dt)
        assert snapped.hour == 9
        assert snapped.minute == 0

    def test_snap_to_business_hours_after_close(self):
        """Times after 5 PM should snap to next business day 9 AM."""
        from services.pipeline_appointment_trigger import PipelineAppointmentTrigger

        # 6:00 PM on a Wednesday should snap to Thursday 9:00 AM
        dt = datetime(2026, 3, 18, 18, 0, tzinfo=timezone.utc)  # Wednesday
        snapped = PipelineAppointmentTrigger._snap_to_business_hours(dt)
        assert snapped.weekday() == 3  # Thursday
        assert snapped.hour == 9
        assert snapped.minute == 0

    def test_snap_to_business_hours_weekend(self):
        """Weekend times should snap to Monday 9 AM."""
        from services.pipeline_appointment_trigger import PipelineAppointmentTrigger

        # Saturday 10 AM should snap to Monday 9:00 AM
        dt = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)  # Saturday
        snapped = PipelineAppointmentTrigger._snap_to_business_hours(dt)
        assert snapped.weekday() == 0  # Monday
        assert snapped.hour == 9
        assert snapped.minute == 0

    def test_snap_to_business_hours_rounds_to_15_min(self):
        """Times should be rounded up to 15-minute boundaries."""
        from services.pipeline_appointment_trigger import PipelineAppointmentTrigger

        # 10:07 AM on a Wednesday -> 10:15 AM
        dt = datetime(2026, 3, 18, 10, 7, tzinfo=timezone.utc)
        snapped = PipelineAppointmentTrigger._snap_to_business_hours(dt)
        assert snapped.hour == 10
        assert snapped.minute == 15

    def test_fallback_timezone_constant(self):
        """Pipeline trigger should define a fallback timezone."""
        from services.pipeline_appointment_trigger import _FALLBACK_TIMEZONE
        assert _FALLBACK_TIMEZONE == "America/Chicago"

    def test_default_rules_cover_key_stages(self):
        """DEFAULT_RULES should cover the key mortgage pipeline stages."""
        from services.pipeline_appointment_trigger import DEFAULT_RULES

        stages_covered = {r.from_stage for r in DEFAULT_RULES}
        expected_stages = {
            "APPLICATION",
            "DISCLOSED",
            "CONDITIONAL_APPROVAL",
            "APPROVED",
            "CLEAR_TO_CLOSE",
            "CTC",
        }
        missing = expected_stages - stages_covered
        assert not missing, f"DEFAULT_RULES missing stages: {missing}"

    def test_auto_book_rules_are_required(self):
        """Rules with auto_book=True should also be required=True.

        Auto-booked appointments bypass borrower consent (no booking link),
        so they should only be used for compliance-required appointments.
        """
        from services.pipeline_appointment_trigger import DEFAULT_RULES

        for rule in DEFAULT_RULES:
            if rule.auto_book:
                assert rule.required, (
                    f"Rule '{rule.appointment_type}' has auto_book=True but "
                    f"required=False. Auto-booked rules should be compliance-required."
                )


# =============================================================================
# TEST CLASS: Cross-Path Field Parity via Unified Service
# =============================================================================

class TestCrossPathFieldParity:
    """Verify the unified service's Appointment() constructor includes all
    fields that matter across the three booking paths.
    """

    def test_unified_service_appointment_constructor_completeness(self):
        """The unified service Appointment() must set a comprehensive set of fields."""
        calls = _extract_appointment_constructor_kwargs(_UNIFIED_SERVICE_PATH)
        assert len(calls) > 0

        kwargs = calls[0]

        # Every field the unified service should set
        expected_fields = {
            "organization_id",
            "appointment_type_id",
            "assigned_user_id",
            "created_by_user_id",
            "lead_id",
            "loan_id",
            "contact_id",
            "title",
            "description",
            "meeting_type",
            "meeting_mode",
            "scheduled_start",
            "scheduled_end",
            "duration_minutes",
            "timezone",
            "attendee_name",
            "attendee_email",
            "attendee_phone",
            "attendee_notes",
            "intake_responses",
            "status",
            "status_changed_at",
            "booked_by_ai",
            "ai_booking_context",
            "internal_notes",
            "external_source",
        }

        missing = expected_fields - kwargs
        assert not missing, (
            f"Unified service Appointment() is missing fields: {missing}"
        )
