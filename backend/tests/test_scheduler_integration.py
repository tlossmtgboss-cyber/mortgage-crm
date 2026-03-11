"""
Smart Calendar Operational Intelligence — Integration Tests

Tests that actually exercise the code paths with mocked DB sessions.
No conftest.py dependency, no database connection needed.

Run: python -m pytest tests/test_scheduler_integration.py -v --noconftest
"""

import os
import sys
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

# Ensure backend on path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Set test encryption key before any imports that might trigger encryption_utils
os.environ.setdefault("DATA_ENCRYPTION_KEY", "dGVzdF9rZXlfZm9yX2NpX29ubHlfMDAwMDAwMDAwMDA=")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")


# =============================================================================
# Phase 1: Compliance — Functional Tests
# =============================================================================

class TestC1_SMSConsentFunctional:
    """C1: Test check_sms_consent actually blocks/allows correctly."""

    def test_consent_blocks_on_empty_phone(self):
        """Should block if no phone number."""
        from scheduler_email_service import check_sms_consent
        allowed, reason = check_sms_consent("")
        assert allowed is False
        assert "No phone" in reason

    def test_consent_blocks_dnc_number(self):
        """If DNC check returns True, SMS should be blocked."""
        mock_checker = MagicMock()
        mock_checker.check_dnc.return_value = (True, "Number on DNC list")

        mock_db = MagicMock()

        with patch("database.SessionLocal", return_value=mock_db):
            with patch("telephony.compliance.ComplianceChecker", return_value=mock_checker):
                from scheduler_email_service import check_sms_consent
                allowed, reason = check_sms_consent("+15551234567")

                assert allowed is False

    def test_consent_blocks_on_error(self):
        """Fail-safe: block SMS if consent check itself errors."""
        with patch("database.SessionLocal", side_effect=Exception("DB down")):
            from scheduler_email_service import check_sms_consent
            allowed, reason = check_sms_consent("+15551234567")

            assert allowed is False


class TestC2_DuplicateBookingFunctional:
    """C2: Test duplicate booking detection logic.

    _check_duplicate_booking uses SQLAlchemy ORM filter chains that require
    real model classes. We test by verifying the function exists, has the
    right signature, and uses 409 status code. Full ORM path tested in e2e.
    """

    def test_function_signature(self):
        """Should have correct parameters."""
        import inspect
        from scheduler_appointment_routes import _check_duplicate_booking
        sig = inspect.signature(_check_duplicate_booking)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "attendee_email" in params
        assert "assigned_user_id" in params
        assert "start_time" in params
        assert "org_id" in params

    def test_raises_409_on_duplicate(self):
        """Verify function raises HTTPException(409) path via source inspection."""
        import ast
        with open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")) as f:
            source = f.read()
        # Find _check_duplicate_booking and verify it contains 409
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_check_duplicate_booking":
                func_source = ast.get_source_segment(source, node)
                assert "409" in func_source
                assert "duplicate" in func_source.lower() or "Duplicate" in func_source
                break
        else:
            pytest.fail("_check_duplicate_booking not found")


class TestC3_LOLicensingFunctional:
    """C3: Test LO licensing check is advisory."""

    def test_returns_warning_when_no_nmls(self):
        """Should return warning when LO has no NMLS."""
        mock_db = MagicMock()
        class MockUser:
            id = 1
            nmls_number = None
            first_name = "John"
            last_name = "Doe"

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = MockUser()
        mock_db.query.return_value = mock_query

        from scheduler_appointment_routes import _check_lo_licensing
        # Patch User model at import target so filter(User.id == ...) works
        mock_user_class = MagicMock()
        with patch("database.models.core.User", mock_user_class):
            result = _check_lo_licensing(mock_db, assigned_user_id=1, attendee_state="CA")

        assert result is not None
        assert isinstance(result, str)
        assert "NMLS" in result or "nmls" in result.lower()

    def test_returns_none_when_no_state(self):
        """Should return None when no state provided."""
        mock_db = MagicMock()

        from scheduler_appointment_routes import _check_lo_licensing
        result = _check_lo_licensing(mock_db, assigned_user_id=1, attendee_state="")

        assert result is None

    def test_returns_none_when_none_state(self):
        """Should return None when state is None."""
        mock_db = MagicMock()

        from scheduler_appointment_routes import _check_lo_licensing
        result = _check_lo_licensing(mock_db, assigned_user_id=1, attendee_state=None)

        assert result is None


# =============================================================================
# Phase 2: CRM Integration — Functional Tests
# =============================================================================

class TestCRM1_LeadCreationFunctional:
    """CRM1: Lead creation/linking."""

    def test_returns_existing_lead_id_on_dedup(self):
        """If lead with same email exists, return its ID."""
        mock_db = MagicMock()
        mock_lead = MagicMock()
        mock_lead.id = 99
        mock_db.query.return_value.filter.return_value.first.return_value = mock_lead

        from scheduler_appointment_routes import _ensure_lead_for_booking
        result = _ensure_lead_for_booking(
            db=mock_db,
            attendee_email="existing@test.com",
            attendee_name="Existing User",
            attendee_phone="+15551234567",
            assigned_user_id=1,
            org_id=1,
        )

        assert result == 99

    def test_returns_none_on_no_email(self):
        """Should return None if no email provided."""
        mock_db = MagicMock()

        from scheduler_appointment_routes import _ensure_lead_for_booking
        result = _ensure_lead_for_booking(
            db=mock_db,
            attendee_email="",
            attendee_name="No Email",
            attendee_phone="+15551234567",
            assigned_user_id=1,
            org_id=1,
        )

        assert result is None


class TestCRM2_ActivityLoggingFunctional:
    """CRM2: Activity logging."""

    def test_logs_activity_successfully(self):
        """Should create Activity record without raising."""
        mock_db = MagicMock()

        from scheduler_appointment_routes import _log_appointment_activity
        _log_appointment_activity(
            db=mock_db,
            org_id=1,
            user_id=1,
            lead_id=5,
            loan_id=None,
            content="Test appointment scheduled",
            activity_type="Meeting",
        )

        assert mock_db.add.called

    def test_handles_error_gracefully(self):
        """Should not crash if Activity model creation fails."""
        mock_db = MagicMock()
        mock_db.add.side_effect = Exception("DB error")

        from scheduler_appointment_routes import _log_appointment_activity
        # Should not raise
        _log_appointment_activity(
            db=mock_db,
            org_id=1,
            user_id=1,
            lead_id=None,
            loan_id=None,
            content="Test",
        )


class TestCRM3_FollowupTasksFunctional:
    """CRM3: Follow-up task creation."""

    def test_creates_task_successfully(self):
        """Should create a Task record."""
        mock_db = MagicMock()

        from scheduler_appointment_routes import _create_followup_task
        _create_followup_task(
            db=mock_db,
            org_id=1,
            owner_id=1,
            lead_id=5,
            loan_id=None,
            title="Follow up after consultation",
            description="Check in with client after meeting",
            due_date=datetime.now() + timedelta(days=1),
        )

        assert mock_db.add.called


# =============================================================================
# Phase 3: Resilience — Functional Tests
# =============================================================================

class TestR1_RetryWithFallback:
    """R1: Email retry + SMS fallback."""

    def test_retry_succeeds_on_first_attempt(self):
        """Should return success immediately if first attempt works."""
        import asyncio
        from scheduler_email_service import _retry_email_send

        def success_fn():
            return {"success": True, "message_id": "abc123"}

        result = asyncio.get_event_loop().run_until_complete(
            _retry_email_send(success_fn, max_retries=2, backoff_base=0.01)
        )
        assert result["success"] is True

    def test_retry_succeeds_on_second_attempt(self):
        """Should retry and succeed on second attempt."""
        import asyncio
        from scheduler_email_service import _retry_email_send

        call_count = {"n": 0}
        def fail_then_succeed():
            call_count["n"] += 1
            if call_count["n"] < 2:
                return {"success": False, "error": "temporary failure"}
            return {"success": True, "message_id": "def456"}

        result = asyncio.get_event_loop().run_until_complete(
            _retry_email_send(fail_then_succeed, max_retries=2, backoff_base=0.01)
        )
        assert result["success"] is True
        assert call_count["n"] == 2

    def test_retry_exhausts_and_returns_last_error(self):
        """Should return error after all retries exhausted."""
        import asyncio
        from scheduler_email_service import _retry_email_send

        def always_fail():
            return {"success": False, "error": "permanent failure"}

        result = asyncio.get_event_loop().run_until_complete(
            _retry_email_send(always_fail, max_retries=2, backoff_base=0.01)
        )
        assert result["success"] is False
        assert "permanent failure" in result.get("error", "")

    def test_send_with_sms_fallback_email_success(self):
        """Should not attempt SMS if email succeeds."""
        import asyncio
        from scheduler_email_service import send_with_sms_fallback

        sms_called = {"called": False}
        def email_fn():
            return {"success": True}
        def sms_fn():
            sms_called["called"] = True
            return {"success": True}

        result = asyncio.get_event_loop().run_until_complete(
            send_with_sms_fallback(
                email_fn, sms_fn, max_retries=0, context_label="test"
            )
        )
        assert result["email_sent"] is True
        assert sms_called["called"] is False

    def test_send_with_sms_fallback_falls_back_to_sms(self):
        """Should try SMS when email fails."""
        import asyncio
        from scheduler_email_service import send_with_sms_fallback

        def email_fn():
            return {"success": False, "error": "SMTP down"}
        def sms_fn():
            return {"success": True}

        result = asyncio.get_event_loop().run_until_complete(
            send_with_sms_fallback(
                email_fn, sms_fn, max_retries=0, context_label="test"
            )
        )
        assert result["email_sent"] is False
        assert result["sms_sent"] is True

    def test_send_with_sms_fallback_escalates_on_total_failure(self):
        """Should call escalation_fn when both email and SMS fail."""
        import asyncio
        from scheduler_email_service import send_with_sms_fallback

        escalated = {"called": False}
        def email_fn():
            return {"success": False, "error": "email down"}
        def sms_fn():
            return {"success": False, "error": "sms down"}
        def escalation_fn(error_msg):
            escalated["called"] = True
            escalated["error"] = error_msg

        result = asyncio.get_event_loop().run_until_complete(
            send_with_sms_fallback(
                email_fn, sms_fn, max_retries=0, context_label="test",
                escalation_fn=escalation_fn,
            )
        )
        assert result["email_sent"] is False
        assert result["sms_sent"] is False
        assert escalated["called"] is True


class TestR4_MemoryRateLimiter:
    """R4: In-memory rate limiter."""

    def test_allows_under_limit(self):
        """Should allow requests under the limit."""
        from scheduler_appointment_routes import _check_memory_rate_limit, _memory_rate_limits

        _memory_rate_limits.clear()

        key = "test_allow_under_limit"
        assert _check_memory_rate_limit(key, max_requests=5, window_seconds=60) is True
        assert _check_memory_rate_limit(key, max_requests=5, window_seconds=60) is True

    def test_blocks_over_limit(self):
        """Should block requests over the limit."""
        from scheduler_appointment_routes import _check_memory_rate_limit, _memory_rate_limits

        _memory_rate_limits.clear()

        key = "test_block_over_limit"
        for _ in range(3):
            _check_memory_rate_limit(key, max_requests=3, window_seconds=60)

        assert _check_memory_rate_limit(key, max_requests=3, window_seconds=60) is False


class TestR5_EscalationTask:
    """R5: Communication failure escalation."""

    def test_creates_task_on_comm_failure(self):
        """Should create a high-priority task."""
        mock_db = MagicMock()

        from scheduler_appointment_routes import _create_comm_failure_task
        _create_comm_failure_task(
            db=mock_db,
            org_id=1,
            assigned_user_id=1,
            attendee_name="Test Client",
            error_msg="Both email and SMS failed",
        )

        assert mock_db.add.called
        assert mock_db.commit.called


# =============================================================================
# Phase 4: Routing Intelligence — Functional Tests
# =============================================================================

class TestRT1_RoutingStrategies:
    """RT1: Test all 5 routing strategies."""

    def test_direct_returns_first_candidate(self):
        from services.scheduler_routing_service import _assign_direct
        assert _assign_direct([10, 20, 30]) == 10

    def test_direct_returns_none_for_empty(self):
        from services.scheduler_routing_service import _assign_direct
        assert _assign_direct([]) is None

    def test_round_robin_rotates(self):
        """Should rotate past the last assigned user."""
        mock_db = MagicMock()
        mock_db.execute.return_value.scalar.return_value = 20

        from services.scheduler_routing_service import _assign_round_robin
        result = _assign_round_robin(mock_db, org_id=1, candidate_ids=[10, 20, 30])

        assert result == 30

    def test_round_robin_wraps_around(self):
        """Should wrap to first when last assigned is the last candidate."""
        mock_db = MagicMock()
        mock_db.execute.return_value.scalar.return_value = 30

        from services.scheduler_routing_service import _assign_round_robin
        result = _assign_round_robin(mock_db, org_id=1, candidate_ids=[10, 20, 30])

        assert result == 10

    def test_load_balanced_picks_least_busy(self):
        """Should assign to LO with fewest appointments."""
        mock_db = MagicMock()
        mock_db.execute.return_value.scalar.side_effect = [5, 2, 8]

        from services.scheduler_routing_service import _assign_load_balanced
        result = _assign_load_balanced(mock_db, org_id=1, candidate_ids=[10, 20, 30])

        assert result == 20

    def test_assign_loan_officer_excludes_ids(self):
        """Should respect excluded_user_ids."""
        mock_db = MagicMock()
        mock_link = MagicMock()
        mock_link.assigned_users = [10, 20, 30]

        from services.scheduler_routing_service import assign_loan_officer
        result = assign_loan_officer(
            db=mock_db, org_id=1, strategy="direct",
            booking_link=mock_link, excluded_user_ids=[10],
        )

        assert result == 20

    def test_assign_loan_officer_returns_none_when_all_excluded(self):
        """Should return None when all candidates are excluded."""
        mock_db = MagicMock()
        mock_link = MagicMock()
        mock_link.assigned_users = [10, 20]

        from services.scheduler_routing_service import assign_loan_officer
        result = assign_loan_officer(
            db=mock_db, org_id=1, strategy="direct",
            booking_link=mock_link, excluded_user_ids=[10, 20],
        )

        assert result is None

    def test_unknown_strategy_falls_back_to_direct(self):
        """Should fallback to direct for unknown strategy."""
        mock_db = MagicMock()
        mock_link = MagicMock()
        mock_link.assigned_users = [10, 20]

        from services.scheduler_routing_service import assign_loan_officer
        result = assign_loan_officer(
            db=mock_db, org_id=1, strategy="nonexistent_strategy",
            booking_link=mock_link,
        )

        assert result == 10


class TestRT2_CapacityEnforcement:
    """RT2: Hard capacity enforcement."""

    def test_is_lo_available_returns_false_at_capacity(self):
        """Should return False when LO at daily capacity."""
        mock_db = MagicMock()
        mock_db.execute.return_value.scalar.side_effect = [8, 8]

        from services.scheduler_routing_service import _is_lo_available
        result = _is_lo_available(
            mock_db, user_id=1, org_id=1,
            appointment_time=datetime(2026, 3, 10, 10, 0),
        )

        assert result is False

    def test_is_lo_available_returns_true_under_capacity(self):
        """Should return True when LO under capacity and no conflicts."""
        mock_db = MagicMock()
        mock_db.execute.return_value.scalar.side_effect = [2, 10, 0]

        from services.scheduler_routing_service import _is_lo_available
        result = _is_lo_available(
            mock_db, user_id=1, org_id=1,
            appointment_time=datetime(2026, 3, 10, 10, 0),
        )

        assert result is True

    def test_is_lo_available_returns_true_with_no_time(self):
        """Should return True when no appointment_time given."""
        mock_db = MagicMock()

        from services.scheduler_routing_service import _is_lo_available
        result = _is_lo_available(mock_db, user_id=1, org_id=1, appointment_time=None)

        assert result is True


class TestRT3_ConflictDetection:
    """RT3: Unified calendar conflict detection."""

    def test_detects_hard_conflict(self):
        """Should detect overlapping events as hard conflict."""
        from services.unified_calendar_service import UnifiedCalendarService

        mock_db = MagicMock()
        service = UnifiedCalendarService(db=mock_db, user_id=1, organization_id=1)

        events = [
            {"id": "a", "title": "Meeting A", "start_time": "2026-03-10T10:00:00", "end_time": "2026-03-10T11:00:00"},
            {"id": "b", "title": "Meeting B", "start_time": "2026-03-10T10:30:00", "end_time": "2026-03-10T11:30:00"},
        ]

        conflicts = service._detect_conflicts(events)

        assert len(conflicts) == 1
        assert conflicts[0]["type"] == "hard"
        assert conflicts[0]["event_a_id"] == "a"
        assert conflicts[0]["event_b_id"] == "b"

    def test_detects_soft_conflict(self):
        """Should detect back-to-back events with <5min gap as soft conflict."""
        from services.unified_calendar_service import UnifiedCalendarService

        mock_db = MagicMock()
        service = UnifiedCalendarService(db=mock_db, user_id=1, organization_id=1)

        events = [
            {"id": "a", "title": "Meeting A", "start_time": "2026-03-10T10:00:00", "end_time": "2026-03-10T11:00:00"},
            {"id": "b", "title": "Meeting B", "start_time": "2026-03-10T11:03:00", "end_time": "2026-03-10T12:00:00"},
        ]

        conflicts = service._detect_conflicts(events)

        assert len(conflicts) == 1
        assert conflicts[0]["type"] == "soft"
        assert conflicts[0]["gap_minutes"] == 3.0

    def test_no_conflict_with_adequate_gap(self):
        """Should not flag events with >5min gap."""
        from services.unified_calendar_service import UnifiedCalendarService

        mock_db = MagicMock()
        service = UnifiedCalendarService(db=mock_db, user_id=1, organization_id=1)

        events = [
            {"id": "a", "title": "Meeting A", "start_time": "2026-03-10T10:00:00", "end_time": "2026-03-10T11:00:00"},
            {"id": "b", "title": "Meeting B", "start_time": "2026-03-10T11:15:00", "end_time": "2026-03-10T12:00:00"},
        ]

        conflicts = service._detect_conflicts(events)
        assert len(conflicts) == 0

    def test_no_conflict_with_empty_events(self):
        """Should handle empty event list."""
        from services.unified_calendar_service import UnifiedCalendarService

        mock_db = MagicMock()
        service = UnifiedCalendarService(db=mock_db, user_id=1, organization_id=1)

        conflicts = service._detect_conflicts([])
        assert conflicts == []

    def test_requires_organization_id(self):
        """Should raise ValueError if org_id is falsy."""
        from services.unified_calendar_service import UnifiedCalendarService

        mock_db = MagicMock()
        with pytest.raises(ValueError, match="organization_id"):
            UnifiedCalendarService(db=mock_db, user_id=1, organization_id=0)

    def test_multiple_conflicts(self):
        """Should detect multiple conflicts in a sequence."""
        from services.unified_calendar_service import UnifiedCalendarService

        mock_db = MagicMock()
        service = UnifiedCalendarService(db=mock_db, user_id=1, organization_id=1)

        events = [
            {"id": "a", "title": "A", "start_time": "2026-03-10T09:00:00", "end_time": "2026-03-10T10:00:00"},
            {"id": "b", "title": "B", "start_time": "2026-03-10T09:30:00", "end_time": "2026-03-10T10:30:00"},
            {"id": "c", "title": "C", "start_time": "2026-03-10T10:32:00", "end_time": "2026-03-10T11:30:00"},
        ]

        conflicts = service._detect_conflicts(events)

        assert len(conflicts) == 2
        assert conflicts[0]["type"] == "hard"  # a overlaps b
        assert conflicts[1]["type"] == "soft"  # b → c (2 min gap)


# =============================================================================
# CRM5: Analytics tools — Functional Tests
# =============================================================================

class TestCRM5_AnalyticsTools:
    """CRM5: Test analytics tool SQL structure and return types."""

    def test_get_scheduler_metrics_returns_tool_result(self):
        """Should return ToolResult with expected fields."""
        with patch("agents.tools.scheduler.execute_single") as mock_exec:
            mock_exec.return_value = {
                "total_bookings": 100,
                "completed": 75,
                "no_shows": 10,
                "cancelled": 15,
                "upcoming": 5,
                "rescheduled": 3,
            }

            from agents.tools.scheduler import get_scheduler_metrics
            result = get_scheduler_metrics(organization_id="1", days=30)

            assert result.status.value == "success"
            assert result.data["total_bookings"] == 100
            assert result.data["show_rate_pct"] > 0
            assert "no_show_rate_pct" in result.data

    def test_get_appointment_history_requires_filter(self):
        """Should error if no filter provided."""
        from agents.tools.scheduler import get_appointment_history
        result = get_appointment_history()

        assert result.status.value == "error"

    def test_get_best_booking_times_returns_recommendation(self):
        """Should return a recommendation string."""
        with patch("agents.tools.scheduler.execute_query") as mock_exec:
            mock_exec.side_effect = [
                [{"hour": 10, "total": 20, "showed": 18, "no_showed": 2}],
                [{"day_of_week": 2, "total": 30, "showed": 25, "no_showed": 5}],
            ]

            from agents.tools.scheduler import get_best_booking_times
            result = get_best_booking_times(organization_id="1")

            assert result.status.value == "success"
            assert "recommendation" in result.data

    def test_get_no_show_analysis_returns_breakdown(self):
        """Should return breakdown by LO and source."""
        with patch("agents.tools.scheduler.execute_query") as mock_query, \
             patch("agents.tools.scheduler.execute_single") as mock_single:

            mock_query.side_effect = [
                [{"lo_id": 1, "lo_name": "John Doe", "total": 50, "no_shows": 5}],
                [{"source": "website", "total": 30, "no_shows": 3}],
            ]
            mock_single.return_value = {"total": 50, "no_shows": 5}

            from agents.tools.scheduler import get_no_show_analysis
            result = get_no_show_analysis(organization_id="1")

            assert result.status.value == "success"
            assert "by_lo" in result.data
            assert "by_source" in result.data
            assert result.data["overall_no_show_rate_pct"] == 10.0
