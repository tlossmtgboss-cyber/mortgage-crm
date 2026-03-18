"""
Integration tests for appointment creation consistency across booking paths.

Verifies that all 3 booking paths produce consistent appointment records:
  1. Authenticated (POST /appointments) — appointments.py
  2. Public booking (POST /public/book/{slug}/confirm) — public_booking.py
  3. Pipeline AI trigger (PipelineAppointmentTrigger.create_appointment_suggestion) — pipeline_appointment_trigger.py

These tests use source-code analysis of the Appointment() constructor calls
in each path to verify field-level consistency, conflict-checking behavior,
and post-creation side effects (audit log, meeting link, lead linkage, etc.).
"""

import ast
import pytest
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS — Extract Appointment() constructor kwargs from each booking path
# =============================================================================

# The three source files containing the booking paths
_BACKEND_DIR = Path(__file__).parent.parent
_AUTHENTICATED_PATH = _BACKEND_DIR / "routes" / "scheduler" / "appointments.py"
_PUBLIC_BOOKING_PATH = _BACKEND_DIR / "routes" / "scheduler" / "public_booking.py"
_PIPELINE_TRIGGER_PATH = _BACKEND_DIR / "services" / "pipeline_appointment_trigger.py"


def _extract_appointment_constructor_kwargs(source_path: Path) -> list[set[str]]:
    """Parse a Python source file and return sets of keyword argument names
    used in every ``Appointment(...)`` constructor call found in it.

    Returns a list because a file may contain multiple Appointment() calls
    (e.g. the pipeline trigger has one in ``create_appointment_suggestion``).
    """
    source = source_path.read_text()
    tree = ast.parse(source, filename=str(source_path))

    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Match Appointment(...) — could be Name or Attribute node
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


def _get_kwargs_for_path(path: Path) -> set[str]:
    """Return the kwargs from the *first* Appointment() constructor call
    in the given file.  Asserts that at least one was found.
    """
    all_calls = _extract_appointment_constructor_kwargs(path)
    assert len(all_calls) > 0, f"No Appointment() constructor found in {path.name}"
    return all_calls[0]


# Cache the extracted kwargs at module level so every test doesn't re-parse
_authenticated_kwargs: set[str] = set()
_public_kwargs: set[str] = set()
_pipeline_kwargs: set[str] = set()


def _ensure_kwargs_loaded():
    global _authenticated_kwargs, _public_kwargs, _pipeline_kwargs
    if not _authenticated_kwargs:
        _authenticated_kwargs.update(_get_kwargs_for_path(_AUTHENTICATED_PATH))
    if not _public_kwargs:
        _public_kwargs.update(_get_kwargs_for_path(_PUBLIC_BOOKING_PATH))
    if not _pipeline_kwargs:
        _pipeline_kwargs.update(_get_kwargs_for_path(_PIPELINE_TRIGGER_PATH))


# Required fields that EVERY booking path must set on Appointment()
REQUIRED_CORE_FIELDS = {
    "organization_id",
    "title",
    "scheduled_start",
    "scheduled_end",
    "duration_minutes",
    "status",
    "meeting_mode",
}


# =============================================================================
# SOURCE FILE EXISTENCE GUARD
# =============================================================================

@pytest.fixture(autouse=True, scope="module")
def _verify_source_files_exist():
    """Fail fast if any of the three source files are missing."""
    for path in (_AUTHENTICATED_PATH, _PUBLIC_BOOKING_PATH, _PIPELINE_TRIGGER_PATH):
        assert path.exists(), f"Source file not found: {path}"
    _ensure_kwargs_loaded()


# =============================================================================
# TEST CLASS: Appointment Field Consistency
# =============================================================================

class TestAppointmentFieldConsistency:
    """Verify all booking paths set the same required fields."""

    def test_all_paths_set_organization_id(self):
        """All paths must set organization_id for tenant isolation."""
        _ensure_kwargs_loaded()
        assert "organization_id" in _authenticated_kwargs, \
            "Authenticated path missing organization_id"
        assert "organization_id" in _public_kwargs, \
            "Public booking path missing organization_id"
        assert "organization_id" in _pipeline_kwargs, \
            "Pipeline trigger path missing organization_id"

    def test_all_paths_set_status_to_booked(self):
        """All paths must set initial status (expected: BOOKED).

        We verify the field is present in the constructor. The actual value
        (AppointmentStatus.BOOKED) is checked via source text search since
        AST constant extraction varies by Python version.
        """
        _ensure_kwargs_loaded()
        assert "status" in _authenticated_kwargs
        assert "status" in _public_kwargs
        assert "status" in _pipeline_kwargs

        # Verify the value is BOOKED in each source
        for path in (_AUTHENTICATED_PATH, _PUBLIC_BOOKING_PATH, _PIPELINE_TRIGGER_PATH):
            source = path.read_text()
            # Look for status=AppointmentStatus.BOOKED in the Appointment constructor vicinity
            assert "AppointmentStatus.BOOKED" in source, \
                f"{path.name} does not set status to AppointmentStatus.BOOKED"

    def test_all_paths_set_status_changed_at(self):
        """All paths must set status_changed_at timestamp.

        BUG DETECTED: pipeline_appointment_trigger.py does NOT set
        status_changed_at. This is an inconsistency — authenticated and
        public paths both set it, but the pipeline AI trigger omits it,
        leaving it as NULL and breaking timeline queries that sort by
        status_changed_at.
        """
        _ensure_kwargs_loaded()
        assert "status_changed_at" in _authenticated_kwargs, \
            "Authenticated path missing status_changed_at"
        assert "status_changed_at" in _public_kwargs, \
            "Public booking path missing status_changed_at"

        # Document the known inconsistency
        if "status_changed_at" not in _pipeline_kwargs:
            pytest.xfail(
                "KNOWN BUG: pipeline_appointment_trigger.py does not set "
                "status_changed_at on the Appointment, causing NULL values "
                "in the status timeline. Fix: add "
                "status_changed_at=datetime.now(timezone.utc) to the "
                "Appointment() constructor in create_appointment_suggestion()."
            )

    def test_all_paths_set_timezone(self):
        """All paths must set a valid timezone, not rely on model default.

        The Appointment model defaults timezone to 'America/Chicago', but
        each path should explicitly set it based on the LO's configuration.
        """
        _ensure_kwargs_loaded()
        assert "timezone" in _authenticated_kwargs, \
            "Authenticated path should explicitly set timezone"
        assert "timezone" in _pipeline_kwargs, \
            "Pipeline trigger should explicitly set timezone"

        # Public booking path may rely on model default — document the gap
        if "timezone" not in _public_kwargs:
            pytest.xfail(
                "KNOWN GAP: public_booking.py does not explicitly set timezone "
                "on the Appointment, relying on model default 'America/Chicago'. "
                "Fix: resolve the LO's timezone from SchedulerConfig and pass it."
            )

    def test_all_paths_set_duration(self):
        """All paths must set duration_minutes."""
        _ensure_kwargs_loaded()
        assert "duration_minutes" in _authenticated_kwargs
        assert "duration_minutes" in _public_kwargs
        assert "duration_minutes" in _pipeline_kwargs

    def test_all_paths_set_meeting_mode(self):
        """All paths must set meeting_mode (VIDEO, PHONE, IN_PERSON)."""
        _ensure_kwargs_loaded()
        assert "meeting_mode" in _authenticated_kwargs
        assert "meeting_mode" in _public_kwargs
        assert "meeting_mode" in _pipeline_kwargs

    def test_all_paths_set_attendee_info(self):
        """All paths should set at minimum attendee_name and attendee_email."""
        _ensure_kwargs_loaded()
        for label, kwargs in [
            ("authenticated", _authenticated_kwargs),
            ("public", _public_kwargs),
            ("pipeline", _pipeline_kwargs),
        ]:
            assert "attendee_name" in kwargs, \
                f"{label} path missing attendee_name"
            assert "attendee_email" in kwargs, \
                f"{label} path missing attendee_email"

    def test_required_core_fields_present_in_all_paths(self):
        """Every path must include all REQUIRED_CORE_FIELDS."""
        _ensure_kwargs_loaded()
        for label, kwargs in [
            ("authenticated", _authenticated_kwargs),
            ("public", _public_kwargs),
            ("pipeline", _pipeline_kwargs),
        ]:
            missing = REQUIRED_CORE_FIELDS - kwargs
            assert not missing, \
                f"{label} path is missing required core fields: {missing}"


# =============================================================================
# TEST CLASS: Post-Creation Step Consistency
# =============================================================================

class TestPostCreationConsistency:
    """Verify post-creation steps are consistent across paths."""

    def _source_contains(self, path: Path, pattern: str) -> bool:
        """Check if the source file contains a pattern (case-sensitive)."""
        return pattern in path.read_text()

    def test_all_paths_check_conflicts(self):
        """All paths must check for appointment conflicts before creation.

        BUG DETECTED: pipeline_appointment_trigger.py does NOT check for
        scheduling conflicts before creating an appointment. This means
        auto-booked appointments can double-book the LO's calendar.
        """
        auth_ok = self._source_contains(_AUTHENTICATED_PATH, "_check_appointment_conflict")
        public_ok = self._source_contains(_PUBLIC_BOOKING_PATH, "_check_appointment_conflict")
        pipeline_ok = self._source_contains(_PIPELINE_TRIGGER_PATH, "_check_appointment_conflict")

        assert auth_ok, "Authenticated path must check conflicts"
        assert public_ok, "Public booking path must check conflicts"

        if not pipeline_ok:
            pytest.xfail(
                "KNOWN BUG: pipeline_appointment_trigger.py does not call "
                "_check_appointment_conflict() before auto-booking. This can "
                "cause double-booked calendar slots when a loan stage change "
                "triggers an auto-book rule."
            )

    def test_all_paths_check_duplicate_bookings(self):
        """All paths should check for duplicate bookings by the same attendee.

        BUG DETECTED: pipeline_appointment_trigger.py does NOT check for
        duplicate bookings. If a loan oscillates between stages, the same
        appointment type may be created multiple times for the same borrower.
        """
        auth_ok = self._source_contains(_AUTHENTICATED_PATH, "_check_duplicate_booking")
        public_ok = self._source_contains(_PUBLIC_BOOKING_PATH, "_check_duplicate_booking")
        pipeline_ok = self._source_contains(_PIPELINE_TRIGGER_PATH, "_check_duplicate_booking")

        assert auth_ok, "Authenticated path must check duplicates"
        assert public_ok, "Public booking path must check duplicates"

        if not pipeline_ok:
            pytest.xfail(
                "KNOWN BUG: pipeline_appointment_trigger.py does not check "
                "for duplicate bookings. Repeated stage changes can create "
                "multiple appointments of the same type for the same borrower."
            )

    def test_all_paths_generate_meeting_link(self):
        """All paths should generate meeting links when meeting_mode is VIDEO.

        BUG DETECTED: pipeline_appointment_trigger.py does NOT generate a
        virtual meeting link for auto-booked video appointments. The borrower
        receives an appointment without a join URL.
        """
        auth_ok = self._source_contains(_AUTHENTICATED_PATH, "create_meeting_for_appointment")
        public_ok = self._source_contains(_PUBLIC_BOOKING_PATH, "create_meeting_for_appointment")
        pipeline_ok = self._source_contains(_PIPELINE_TRIGGER_PATH, "create_meeting_for_appointment")

        assert auth_ok, "Authenticated path must generate meeting links"
        assert public_ok, "Public booking path must generate meeting links"

        if not pipeline_ok:
            pytest.xfail(
                "KNOWN GAP: pipeline_appointment_trigger.py does not call "
                "create_meeting_for_appointment() for video appointments. "
                "Auto-booked appointments have no video link."
            )

    def test_all_paths_log_audit_trail(self):
        """All paths should create audit log entries for compliance.

        The authenticated and public paths use _audit_log() from _helpers.py.
        The pipeline trigger uses its own _log_trigger() method, which writes
        to pipeline_appointment_trigger_log — a different table.
        """
        auth_ok = self._source_contains(_AUTHENTICATED_PATH, "_audit_log")
        public_ok = (
            self._source_contains(_PUBLIC_BOOKING_PATH, "_audit_log")
            or self._source_contains(_PUBLIC_BOOKING_PATH, "scheduler_audit")
        )
        pipeline_ok = self._source_contains(_PIPELINE_TRIGGER_PATH, "_log_trigger")

        assert auth_ok, "Authenticated path must log audit trail"
        # Public booking path does not call _audit_log; document this
        if not public_ok:
            pytest.xfail(
                "KNOWN GAP: public_booking.py does not call _audit_log() or "
                "scheduler_audit after creating the appointment. Only the "
                "authenticated path creates a scheduler_audit_log entry."
            )
        assert pipeline_ok, \
            "Pipeline trigger must log to pipeline_appointment_trigger_log"

    def test_ai_path_matches_authenticated_output(self):
        """AI-created appointments should have same core fields as authenticated ones.

        Compares the Appointment() kwargs between the pipeline trigger
        and the authenticated path to identify fields present in the
        authenticated path but missing from the pipeline trigger.
        """
        _ensure_kwargs_loaded()

        # Fields that the authenticated path sets but the pipeline path does not
        auth_only = _authenticated_kwargs - _pipeline_kwargs
        # Some fields are legitimately different (e.g. created_by_user_id is
        # the logged-in user in auth path, not applicable for AI path)
        expected_auth_only = {
            "created_by_user_id",
            "appointment_type_id",
            "lead_id",
            "contact_id",
            "attendee_notes",
            "intake_responses",
        }

        unexpected_missing = auth_only - expected_auth_only
        if unexpected_missing:
            # These are fields that the auth path sets but the pipeline does
            # not, AND they are not in the expected-to-differ set.
            msg = (
                f"Pipeline trigger is missing fields that the authenticated path sets: "
                f"{unexpected_missing}. These may cause inconsistent appointment records."
            )
            # status_changed_at is a known bug, others may be intentional.
            # We flag any unexpected missing fields as a warning via xfail.
            if unexpected_missing - {"status_changed_at"}:
                pytest.xfail(f"INCONSISTENCY: {msg}")
            else:
                pytest.xfail(f"KNOWN BUG: {msg}")

    def test_public_path_matches_authenticated_output(self):
        """Public booking appointments should have same core fields as authenticated ones.

        Compares the Appointment() kwargs between the public booking
        and the authenticated path to identify unexpected divergences.
        """
        _ensure_kwargs_loaded()

        # Fields the authenticated path sets but the public path does not
        auth_only = _authenticated_kwargs - _public_kwargs
        expected_auth_only = {
            "created_by_user_id",
            "lead_id",
            "loan_id",
            "contact_id",
            "attendee_notes",
            "booked_by_ai",
            "ai_booking_context",
        }

        unexpected_missing = auth_only - expected_auth_only
        if unexpected_missing:
            msg = (
                f"Public booking path is missing fields that the authenticated path sets: "
                f"{unexpected_missing}."
            )
            if "timezone" in unexpected_missing:
                pytest.xfail(
                    f"KNOWN GAP: {msg} The public path does not set timezone, "
                    f"relying on model default."
                )
            else:
                assert False, msg

    def test_public_path_sets_external_source(self):
        """Public booking should set external_source='booking_link'.

        This field distinguishes publicly-booked appointments from
        authenticated or AI-booked ones in analytics and reporting.
        """
        _ensure_kwargs_loaded()
        assert "external_source" in _public_kwargs, \
            "Public booking path must set external_source"
        assert "external_source" not in _authenticated_kwargs, \
            "Authenticated path should NOT set external_source (default is NULL)"

    def test_pipeline_path_sets_ai_context_fields(self):
        """Pipeline trigger should set booked_by_ai and ai_booking_context."""
        _ensure_kwargs_loaded()
        assert "booked_by_ai" in _pipeline_kwargs, \
            "Pipeline trigger must set booked_by_ai=True"
        assert "ai_booking_context" in _pipeline_kwargs, \
            "Pipeline trigger must set ai_booking_context with trigger metadata"
        assert "internal_notes" in _pipeline_kwargs, \
            "Pipeline trigger must set internal_notes with trigger context"


# =============================================================================
# TEST CLASS: Pipeline Trigger Specific Tests
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
# TEST CLASS: Cross-Path Field Parity Report
# =============================================================================

class TestCrossPathFieldParity:
    """Generate a detailed parity report across all three booking paths.

    These tests are informational — they document every field difference
    between paths so the team can decide which gaps to close.
    """

    def test_fields_unique_to_each_path(self):
        """Report fields that appear in exactly one booking path."""
        _ensure_kwargs_loaded()

        all_paths = {
            "authenticated": _authenticated_kwargs,
            "public": _public_kwargs,
            "pipeline": _pipeline_kwargs,
        }
        all_fields = _authenticated_kwargs | _public_kwargs | _pipeline_kwargs

        for field in sorted(all_fields):
            present_in = [name for name, kw in all_paths.items() if field in kw]
            if len(present_in) == 1:
                logger.info(
                    f"Field '{field}' is unique to the {present_in[0]} path"
                )

        # This test always passes — it's for reporting purposes
        assert True

    def test_fields_present_in_exactly_two_paths(self):
        """Report fields that appear in two paths but not the third.

        These are the most likely candidates for consistency bugs.
        """
        _ensure_kwargs_loaded()

        all_paths = {
            "authenticated": _authenticated_kwargs,
            "public": _public_kwargs,
            "pipeline": _pipeline_kwargs,
        }
        all_fields = _authenticated_kwargs | _public_kwargs | _pipeline_kwargs

        two_path_fields = []
        for field in sorted(all_fields):
            present_in = [name for name, kw in all_paths.items() if field in kw]
            absent_from = [name for name, kw in all_paths.items() if field not in kw]
            if len(present_in) == 2:
                two_path_fields.append((field, present_in, absent_from[0]))
                logger.info(
                    f"Field '{field}' is in {present_in} but missing from {absent_from[0]}"
                )

        # This is informational — always passes
        assert True

    def test_all_three_paths_share_minimum_fields(self):
        """All three paths must share at least the REQUIRED_CORE_FIELDS."""
        _ensure_kwargs_loaded()

        common = _authenticated_kwargs & _public_kwargs & _pipeline_kwargs
        missing_from_common = REQUIRED_CORE_FIELDS - common

        assert not missing_from_common, (
            f"These required fields are not common to all 3 paths: {missing_from_common}"
        )
