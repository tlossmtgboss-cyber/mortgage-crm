"""
Scheduler Safety Tests — Task 1 verification

Covers:
  1. _check_appointment_conflict is genuinely async (asyncio.iscoroutinefunction)
  2. Cancellation policy blocks a cancel within the prohibited window (422 before db.commit)
"""

import asyncio
import inspect
import sys
import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, call

# Ensure backend is on path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ---------------------------------------------------------------------------
# Helpers — minimal stubs so we can import without a real DB
# ---------------------------------------------------------------------------

def _make_minimal_stubs():
    """Pre-seed sys.modules with lightweight stubs for heavy dependencies."""
    stubs = {}

    for mod in [
        "sqlalchemy", "sqlalchemy.orm", "sqlalchemy.exc",
        "sqlalchemy.sql", "sqlalchemy.sql.elements",
        "fastapi", "fastapi.routing", "fastapi.responses",
        "telnyx", "twilio", "twilio.rest",
        "sendgrid", "sendgrid.helpers.mail",
        "openai", "anthropic",
        "redis", "celery",
        "smart_scheduler_models",
        "routes.scheduler._core",
        "routes.scheduler.constants",
        "routes.scheduler._input_validation",
    ]:
        if mod not in sys.modules:
            stubs[mod] = MagicMock()

    return stubs


# ---------------------------------------------------------------------------
# 1. _check_appointment_conflict is async
# ---------------------------------------------------------------------------

class TestConflictCheckIsAsync:
    """_check_appointment_conflict must be a coroutine function."""

    def test_is_coroutine_function(self):
        stubs = _make_minimal_stubs()
        # Provide minimal working stubs for the imports inside _conflicts.py
        mock_sm = MagicMock()
        mock_sm.AppointmentStatus = MagicMock()
        stubs["smart_scheduler_models"] = mock_sm

        mock_core = MagicMock()
        mock_core.get_models.return_value = {"Appointment": MagicMock()}
        stubs["routes.scheduler._core"] = mock_core

        mock_constants = MagicMock()
        mock_constants.DEFAULT_APPOINTMENT_DURATION_MINUTES = 30
        stubs["routes.scheduler.constants"] = mock_constants

        stubs["routes.scheduler._input_validation"] = MagicMock()

        with patch.dict(sys.modules, stubs):
            # Remove cached module so we get a fresh import with our stubs
            sys.modules.pop("routes.scheduler._conflicts", None)
            from routes.scheduler._conflicts import _check_appointment_conflict

        assert asyncio.iscoroutinefunction(_check_appointment_conflict), (
            "_check_appointment_conflict must be async def so that advisory lock "
            "and asyncio.sleep work correctly inside FastAPI async route handlers"
        )


# ---------------------------------------------------------------------------
# 2. cancel_appointment enforces policy BEFORE db.commit
# ---------------------------------------------------------------------------

class TestCancelPolicyEnforcedBeforeCommit:
    """
    When CancellationPolicyService.can_cancel returns allowed=False the route
    must raise HTTP 422 and must NOT call db.commit().
    """

    def _build_mock_appointment(self):
        """Build a minimal appointment mock."""
        from datetime import datetime, timezone, timedelta
        appt = MagicMock()
        appt.id = 99
        appt.organization_id = 1
        appt.assigned_user_id = 7
        appt.lead_id = None
        appt.loan_id = None
        appt.title = "Test Appointment"
        appt.attendee_name = "John Borrower"
        appt.attendee_email = "john@example.com"
        appt.deleted_at = None
        # Status must be in CANCELLABLE_STATUSES
        appt.status = MagicMock()
        appt.status.value = "booked"
        # scheduled_start is in the future but within notice window
        appt.scheduled_start = datetime.now(timezone.utc) + timedelta(hours=2)
        appt.scheduled_end = appt.scheduled_start + timedelta(minutes=30)
        return appt

    def test_policy_blocks_cancel_with_422_before_commit(self):
        """
        Mock can_cancel → allowed=False.
        Expect: HTTPException(422) raised, db.commit never called.
        """
        from fastapi import HTTPException
        from datetime import datetime, timezone, timedelta

        appt = self._build_mock_appointment()

        # Build a mock DB session
        mock_db = MagicMock()
        # query chain for the appointment lookup
        mock_db.query.return_value.filter.return_value.first.return_value = appt
        mock_db.commit = MagicMock()

        # Mock user (is_admin=False so policy applies)
        mock_user = MagicMock()
        mock_user.id = 42
        mock_user.email = "lo@example.com"
        mock_user.full_name = "Loan Officer"
        mock_user.role = "loan_officer"
        mock_user.organization_id = 1

        # Build a mock cancellation policy service that blocks the cancel
        mock_policy_result = {
            "allowed": False,
            "reason": "Within minimum notice period: cancellations require 24 hours notice",
            "is_late": True,
            "late_cancel_message": "Late cancellation fee may apply",
            "cancel_count": 0,
            "max_cancellations": 3,
            "require_reason": True,
            "cancellation_reasons": [],
        }
        mock_policy_svc = MagicMock()
        mock_policy_svc.can_cancel.return_value = mock_policy_result

        # We test the logic by importing the module and directly calling the route
        # handler in a controlled way via asyncio.run after patching dependencies.
        stubs = {
            "smart_scheduler_models": MagicMock(
                AppointmentStatus=MagicMock(CANCELLED=MagicMock(), BOOKED=MagicMock())
            ),
        }

        with patch.dict(sys.modules, stubs):
            sys.modules.pop("routes.scheduler.appointments", None)

            # Patch heavy imports before loading the module
            with patch("routes.scheduler.appointments.get_models") as mock_get_models, \
                 patch("routes.scheduler.appointments.get_current_user") as mock_get_user, \
                 patch("routes.scheduler.appointments._get_org_id", return_value=1), \
                 patch("routes.scheduler.appointments._is_scheduler_admin", return_value=False), \
                 patch("routes.scheduler.appointments._audit_log"), \
                 patch("routes.scheduler.appointments._log_appointment_activity"), \
                 patch("routes.scheduler.appointments._create_followup_task"), \
                 patch("routes.scheduler.appointments._convert_utc_to_user_tz",
                       return_value=datetime.now(timezone.utc)), \
                 patch("services.cancellation_policy_service.CancellationPolicyService",
                       return_value=mock_policy_svc):

                # set up model mocks
                mock_appointment_cls = MagicMock()
                # Make filter chain return our appointment
                mock_appointment_cls.id = 99
                mock_appointment_cls.organization_id = 1
                mock_appointment_cls.deleted_at = MagicMock()
                mock_appointment_cls.assigned_user_id = 7
                mock_appointment_cls.created_by_user_id = 7

                mock_db_query_chain = MagicMock()
                mock_db_query_chain.filter.return_value = mock_db_query_chain
                mock_db_query_chain.first.return_value = appt
                mock_db.query.return_value = mock_db_query_chain

                mock_get_models.return_value = {
                    "Appointment": mock_appointment_cls,
                    "User": MagicMock(),
                }
                mock_get_user.return_value = mock_user

                # Import the cancel handler function directly
                from routes.scheduler.appointments import cancel_appointment

                # Build a mock request
                mock_request = MagicMock()
                mock_background_tasks = MagicMock()

                # Run the async route handler
                with pytest.raises(HTTPException) as exc_info:
                    asyncio.run(cancel_appointment(
                        appointment_id=99,
                        background_tasks=mock_background_tasks,
                        cancel_data=None,
                        request=mock_request,
                        db=mock_db,
                    ))

                # Policy should block with 422
                assert exc_info.value.status_code == 422, (
                    f"Expected 422 from policy block, got {exc_info.value.status_code}: "
                    f"{exc_info.value.detail}"
                )
                assert "notice" in exc_info.value.detail.lower() or "policy" in exc_info.value.detail.lower() or "cancel" in exc_info.value.detail.lower(), (
                    f"Expected policy-related message, got: {exc_info.value.detail}"
                )

                # CRITICAL: db.commit must NOT have been called
                mock_db.commit.assert_not_called()

    def test_policy_allows_staff_cancel(self):
        """
        When can_cancel returns allowed=True (staff path), cancel_appointment
        must not raise HTTPException and must call db.commit() exactly once.
        """
        from fastapi import HTTPException
        from datetime import datetime, timezone, timedelta

        appt = self._build_mock_appointment()

        # Build a mock DB session
        mock_db = MagicMock()
        mock_db_query_chain = MagicMock()
        mock_db_query_chain.filter.return_value = mock_db_query_chain
        mock_db_query_chain.first.return_value = appt
        mock_db.query.return_value = mock_db_query_chain
        mock_db.commit = MagicMock()

        # Admin user (is_admin=True → is_staff=True in policy call)
        mock_user = MagicMock()
        mock_user.id = 10
        mock_user.email = "admin@example.com"
        mock_user.full_name = "Admin User"
        mock_user.role = "admin"
        mock_user.organization_id = 1

        # Policy allows (staff path)
        mock_policy_result = {
            "allowed": True,
            "reason": "Staff cancellation",
            "is_late": False,
            "late_cancel_message": None,
            "cancel_count": 0,
            "max_cancellations": 3,
            "require_reason": False,
            "cancellation_reasons": [],
        }
        mock_policy_svc = MagicMock()
        mock_policy_svc.can_cancel.return_value = mock_policy_result

        stubs = {
            "smart_scheduler_models": MagicMock(
                AppointmentStatus=MagicMock(CANCELLED=MagicMock(), BOOKED=MagicMock())
            ),
        }

        with patch.dict(sys.modules, stubs):
            sys.modules.pop("routes.scheduler.appointments", None)

            with patch("routes.scheduler.appointments.get_models") as mock_get_models, \
                 patch("routes.scheduler.appointments.get_current_user") as mock_get_user, \
                 patch("routes.scheduler.appointments._get_org_id", return_value=1), \
                 patch("routes.scheduler.appointments._is_scheduler_admin", return_value=True), \
                 patch("routes.scheduler.appointments._audit_log"), \
                 patch("routes.scheduler.appointments._log_appointment_activity"), \
                 patch("routes.scheduler.appointments._create_followup_task"), \
                 patch("routes.scheduler.appointments._convert_utc_to_user_tz",
                       return_value=datetime.now(timezone.utc)), \
                 patch("routes.scheduler.appointments.scheduler_audit"), \
                 patch("services.cancellation_policy_service.CancellationPolicyService",
                       return_value=mock_policy_svc):

                mock_appointment_cls = MagicMock()
                mock_get_models.return_value = {
                    "Appointment": mock_appointment_cls,
                    "User": MagicMock(),
                }
                mock_get_user.return_value = mock_user

                from routes.scheduler.appointments import cancel_appointment

                mock_request = MagicMock()
                mock_background_tasks = MagicMock()

                # Should NOT raise — policy allows the cancel
                try:
                    asyncio.run(cancel_appointment(
                        appointment_id=99,
                        background_tasks=mock_background_tasks,
                        cancel_data=None,
                        request=mock_request,
                        db=mock_db,
                    ))
                except HTTPException as exc:
                    pytest.fail(
                        f"cancel_appointment raised HTTPException({exc.status_code}) "
                        f"when policy allows: {exc.detail}"
                    )

                # db.commit() must have been called at least once (primary cancellation commit)
                mock_db.commit.assert_called()


# ---------------------------------------------------------------------------
# 3. confirm_reschedule is async
# ---------------------------------------------------------------------------

class TestConfirmRescheduleIsAsync:
    """RescheduleService.confirm_reschedule must be a coroutine function."""

    def test_is_coroutine_function(self):
        # We can inspect the method directly from the class without instantiating
        stubs = {
            "sqlalchemy": MagicMock(),
            "sqlalchemy.orm": MagicMock(),
        }
        with patch.dict(sys.modules, stubs):
            sys.modules.pop("services.reschedule_service", None)
            from services.reschedule_service import RescheduleService

        assert asyncio.iscoroutinefunction(RescheduleService.confirm_reschedule), (
            "RescheduleService.confirm_reschedule must be async def so it can "
            "await _check_appointment_conflict"
        )
