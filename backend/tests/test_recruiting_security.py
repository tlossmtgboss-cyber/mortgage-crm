"""Unit tests for recruiting route security guards.

Covers:
  - skip_score_gate=True by non-admin → 403
  - skip_score_gate=True by admin → passes (service mocked)
  - Non-interviewer submitting feedback → 403
  - Assigned interviewer submitting feedback → passes (service mocked)
  - Primary interviewer submitting feedback → passes (service mocked)
  - Admin submitting feedback (not an interviewer) → passes (service mocked)
  - Interview not found → 404
"""

import asyncio
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers to build lightweight mock objects
# ---------------------------------------------------------------------------

def _make_user(user_id=10, role="loan_officer", org_id=1):
    u = MagicMock()
    u.id = user_id
    u.role = role
    u.organization_id = org_id
    return u


def _make_db_mock(interview_row=None):
    """Return a mock Session whose execute().fetchone() returns interview_row."""
    db = MagicMock()
    execute_result = MagicMock()
    execute_result.fetchone.return_value = interview_row
    db.execute.return_value = execute_result
    return db


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Import the two route handlers under test
# We patch their dependencies at the module level to avoid real DB/service
# ---------------------------------------------------------------------------

# We need the module importable; patch heavy dependencies first.
import sys
import types

# Stub out modules that would require DB connections or heavy imports
for mod_name in [
    "services.recruiting_service",
    "database",
    "database.models",
    "auth.dependencies",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# Provide minimal stubs
sys.modules["database"].get_db = MagicMock()
sys.modules["database.models"].User = MagicMock()
sys.modules["auth.dependencies"].get_current_user = MagicMock()

# RecruitingService stub (will be patched per-test anyway)
recruiting_service_stub = MagicMock()
sys.modules["services.recruiting_service"].RecruitingService = recruiting_service_stub


from routes.recruiting_routes import update_candidate_status, submit_feedback  # noqa: E402


# ---------------------------------------------------------------------------
# Data models used in routes
# ---------------------------------------------------------------------------

from routes.recruiting_routes import CandidateStatusUpdate, InterviewFeedback  # noqa: E402


# ===========================================================================
# 1a. skip_score_gate admin gate
# ===========================================================================

class TestSkipScoreGate:
    def _make_status_data(self, skip_score_gate: bool):
        return CandidateStatusUpdate(status="active", skip_score_gate=skip_score_gate)

    def test_non_admin_skip_score_gate_returns_403(self):
        """A regular loan officer cannot set skip_score_gate=True."""
        user = _make_user(role="loan_officer")
        data = self._make_status_data(skip_score_gate=True)
        db = MagicMock()
        # _verify_candidate_org must succeed (return a truthy row)
        db.execute.return_value.fetchone.return_value = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            _run(update_candidate_status(
                candidate_id=1,
                data=data,
                current_user=user,
                db=db,
            ))

        assert exc_info.value.status_code == 403
        assert "Only admins can override score gates" in exc_info.value.detail

    @pytest.mark.parametrize("role", ["admin", "platform_admin", "site_admin"])
    def test_admin_skip_score_gate_passes(self, role):
        """Admin roles can set skip_score_gate=True — service is called normally."""
        user = _make_user(role=role)
        data = self._make_status_data(skip_score_gate=True)
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = MagicMock()

        mock_service = MagicMock()
        mock_service.update_candidate_status = AsyncMock(return_value={"id": 1, "status": "active"})

        with patch("routes.recruiting_routes.RecruitingService", return_value=mock_service):
            result = _run(update_candidate_status(
                candidate_id=1,
                data=data,
                current_user=user,
                db=db,
            ))

        mock_service.update_candidate_status.assert_awaited_once()
        assert result["id"] == 1

    def test_non_admin_skip_score_gate_false_passes(self):
        """Non-admin can update status as long as skip_score_gate is False."""
        user = _make_user(role="loan_officer")
        data = self._make_status_data(skip_score_gate=False)
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = MagicMock()

        mock_service = MagicMock()
        mock_service.update_candidate_status = AsyncMock(return_value={"id": 1, "status": "active"})

        with patch("routes.recruiting_routes.RecruitingService", return_value=mock_service):
            result = _run(update_candidate_status(
                candidate_id=1,
                data=data,
                current_user=user,
                db=db,
            ))

        mock_service.update_candidate_status.assert_awaited_once()
        assert result["id"] == 1


# ===========================================================================
# 1b. Interview feedback membership check
# ===========================================================================

def _make_interview_row(interviewer_user_ids, primary_interviewer_id=None):
    row = MagicMock()
    row.interviewer_user_ids = interviewer_user_ids
    row.primary_interviewer_id = primary_interviewer_id
    return row


class TestSubmitFeedbackMembershipCheck:

    def _make_feedback(self):
        return InterviewFeedback(overall_score=4.0, recommendation="hire")

    def test_interview_not_found_returns_404(self):
        """If the interview row doesn't exist, return 404."""
        user = _make_user()
        db = _make_db_mock(interview_row=None)
        data = self._make_feedback()

        with pytest.raises(HTTPException) as exc_info:
            _run(submit_feedback(
                interview_id=99,
                data=data,
                current_user=user,
                db=db,
            ))

        assert exc_info.value.status_code == 404
        assert "Interview not found" in exc_info.value.detail

    def test_non_interviewer_returns_403(self):
        """User who is not in interviewer_user_ids and not primary gets 403."""
        user = _make_user(user_id=42, role="loan_officer")
        row = _make_interview_row(interviewer_user_ids=[10, 11], primary_interviewer_id=10)
        db = _make_db_mock(interview_row=row)
        data = self._make_feedback()

        with pytest.raises(HTTPException) as exc_info:
            _run(submit_feedback(
                interview_id=5,
                data=data,
                current_user=user,
                db=db,
            ))

        assert exc_info.value.status_code == 403
        assert "Only assigned interviewers can submit feedback" in exc_info.value.detail

    def test_assigned_interviewer_in_list_passes(self):
        """User whose ID is in interviewer_user_ids can submit feedback."""
        user = _make_user(user_id=10, role="loan_officer")
        row = _make_interview_row(interviewer_user_ids=[10, 11], primary_interviewer_id=99)
        db = _make_db_mock(interview_row=row)
        data = self._make_feedback()

        mock_service = MagicMock()
        mock_service.submit_interview_feedback = AsyncMock(return_value={"id": 5, "submitted": True})

        with patch("routes.recruiting_routes.RecruitingService", return_value=mock_service):
            result = _run(submit_feedback(
                interview_id=5,
                data=data,
                current_user=user,
                db=db,
            ))

        mock_service.submit_interview_feedback.assert_awaited_once()
        assert result["submitted"] is True

    def test_primary_interviewer_passes(self):
        """User who is primary_interviewer_id (but not in list) can submit."""
        user = _make_user(user_id=99, role="loan_officer")
        row = _make_interview_row(interviewer_user_ids=[10, 11], primary_interviewer_id=99)
        db = _make_db_mock(interview_row=row)
        data = self._make_feedback()

        mock_service = MagicMock()
        mock_service.submit_interview_feedback = AsyncMock(return_value={"id": 5, "submitted": True})

        with patch("routes.recruiting_routes.RecruitingService", return_value=mock_service):
            result = _run(submit_feedback(
                interview_id=5,
                data=data,
                current_user=user,
                db=db,
            ))

        mock_service.submit_interview_feedback.assert_awaited_once()
        assert result["submitted"] is True

    @pytest.mark.parametrize("role", ["admin", "platform_admin", "site_admin"])
    def test_admin_not_in_interviewer_list_passes(self, role):
        """Admin can submit feedback even if not in the interviewer list."""
        user = _make_user(user_id=200, role=role)
        row = _make_interview_row(interviewer_user_ids=[10, 11], primary_interviewer_id=10)
        db = _make_db_mock(interview_row=row)
        data = self._make_feedback()

        mock_service = MagicMock()
        mock_service.submit_interview_feedback = AsyncMock(return_value={"id": 5, "submitted": True})

        with patch("routes.recruiting_routes.RecruitingService", return_value=mock_service):
            result = _run(submit_feedback(
                interview_id=5,
                data=data,
                current_user=user,
                db=db,
            ))

        mock_service.submit_interview_feedback.assert_awaited_once()

    def test_json_string_interviewer_ids_parsed_correctly(self):
        """interviewer_user_ids stored as JSON string (not list) is parsed correctly."""
        user = _make_user(user_id=10, role="loan_officer")
        # Simulate JSONB returning a raw JSON string
        row = _make_interview_row(
            interviewer_user_ids='[10, 11]',
            primary_interviewer_id=99,
        )
        db = _make_db_mock(interview_row=row)
        data = self._make_feedback()

        mock_service = MagicMock()
        mock_service.submit_interview_feedback = AsyncMock(return_value={"id": 5, "submitted": True})

        with patch("routes.recruiting_routes.RecruitingService", return_value=mock_service):
            result = _run(submit_feedback(
                interview_id=5,
                data=data,
                current_user=user,
                db=db,
            ))

        mock_service.submit_interview_feedback.assert_awaited_once()

    def test_null_interviewer_ids_non_admin_returns_403(self):
        """NULL interviewer_user_ids with no primary match → 403 for non-admin."""
        user = _make_user(user_id=10, role="loan_officer")
        row = _make_interview_row(interviewer_user_ids=None, primary_interviewer_id=None)
        db = _make_db_mock(interview_row=row)
        data = self._make_feedback()

        with pytest.raises(HTTPException) as exc_info:
            _run(submit_feedback(
                interview_id=5,
                data=data,
                current_user=user,
                db=db,
            ))

        assert exc_info.value.status_code == 403
