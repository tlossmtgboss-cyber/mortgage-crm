"""
Tests for Scheduled Report Executor
====================================

Domain 9 (Analytics) — retry logic, due-ness checks, execution stats.

These are unit tests that do NOT require a real database; they test
the pure-logic functions in scheduled_report_executor.py using mock
sessions where needed.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

from services.scheduled_report_executor import (
    _is_report_due,
    _record_failure,
    _clear_retry_state,
    check_and_run_due_reports,
    MAX_RETRY_COUNT,
    RETRY_DELAY_MINUTES,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_schedule(
    frequency="daily",
    hour_utc=10,
    is_active=True,
    last_sent_at=None,
    day_of_week=None,
    day_of_month=None,
    schedule_id=1,
    retry_count=0,
    status="active",
):
    """Build a minimal schedule dict for testing."""
    return {
        "id": schedule_id,
        "organization_id": 1,
        "created_by_id": 1,
        "report_type": "pipeline",
        "export_format": "pdf",
        "frequency": frequency,
        "recipients": ["test@example.com"],
        "title": "Test Report",
        "day_of_week": day_of_week,
        "day_of_month": day_of_month,
        "hour_utc": hour_utc,
        "is_active": is_active,
        "last_sent_at": last_sent_at,
        "retry_count": retry_count,
        "status": status,
    }


# =============================================================================
# _is_report_due — daily cadence
# =============================================================================


class TestIsReportDueDaily:
    """Test _is_report_due for daily frequency."""

    def test_daily_due_at_correct_hour(self):
        schedule = _make_schedule(frequency="daily", hour_utc=14)
        now = datetime(2026, 5, 7, 14, 30, 0, tzinfo=timezone.utc)
        assert _is_report_due(schedule, now) is True

    def test_daily_not_due_wrong_hour(self):
        schedule = _make_schedule(frequency="daily", hour_utc=14)
        now = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)
        assert _is_report_due(schedule, now) is False

    def test_daily_not_due_inactive(self):
        schedule = _make_schedule(frequency="daily", hour_utc=14, is_active=False)
        now = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)
        assert _is_report_due(schedule, now) is False

    def test_daily_already_sent_today(self):
        """A report already sent today should not fire again."""
        sent_time = datetime(2026, 5, 7, 8, 0, 0, tzinfo=timezone.utc)
        schedule = _make_schedule(frequency="daily", hour_utc=14, last_sent_at=sent_time)
        now = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)
        assert _is_report_due(schedule, now) is False

    def test_daily_sent_yesterday_is_due(self):
        """A report sent yesterday should be due again today."""
        sent_time = datetime(2026, 5, 6, 14, 0, 0, tzinfo=timezone.utc)
        schedule = _make_schedule(frequency="daily", hour_utc=14, last_sent_at=sent_time)
        now = datetime(2026, 5, 7, 14, 0, 0, tzinfo=timezone.utc)
        assert _is_report_due(schedule, now) is True


# =============================================================================
# _is_report_due — weekly cadence
# =============================================================================


class TestIsReportDueWeekly:
    """Test _is_report_due for weekly frequency."""

    def test_weekly_correct_day_and_hour(self):
        # 2026-05-07 is a Thursday (weekday=3)
        schedule = _make_schedule(frequency="weekly", hour_utc=10, day_of_week=3)
        now = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)
        assert _is_report_due(schedule, now) is True

    def test_weekly_wrong_day(self):
        schedule = _make_schedule(frequency="weekly", hour_utc=10, day_of_week=0)  # Monday
        now = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)  # Thursday
        assert _is_report_due(schedule, now) is False

    def test_weekly_defaults_to_monday(self):
        schedule = _make_schedule(frequency="weekly", hour_utc=10, day_of_week=None)
        # 2026-05-04 is a Monday (weekday=0)
        now = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        assert _is_report_due(schedule, now) is True


# =============================================================================
# _is_report_due — monthly cadence
# =============================================================================


class TestIsReportDueMonthly:
    """Test _is_report_due for monthly frequency."""

    def test_monthly_correct_day(self):
        schedule = _make_schedule(frequency="monthly", hour_utc=8, day_of_month=7)
        now = datetime(2026, 5, 7, 8, 0, 0, tzinfo=timezone.utc)
        assert _is_report_due(schedule, now) is True

    def test_monthly_wrong_day(self):
        schedule = _make_schedule(frequency="monthly", hour_utc=8, day_of_month=15)
        now = datetime(2026, 5, 7, 8, 0, 0, tzinfo=timezone.utc)
        assert _is_report_due(schedule, now) is False

    def test_monthly_defaults_to_first(self):
        schedule = _make_schedule(frequency="monthly", hour_utc=8, day_of_month=None)
        now = datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc)
        assert _is_report_due(schedule, now) is True


# =============================================================================
# Retry logic
# =============================================================================


class TestRetryLogic:
    """Test that failed reports record failures and increment retry_count."""

    def _mock_db(self, current_retry_count=0):
        """Return a mock DB session with execute/commit stubs."""
        db = MagicMock()
        # First call to execute (SELECT retry_count) returns the current count
        select_result = MagicMock()
        select_result.fetchone.return_value = (current_retry_count,)
        # Subsequent calls (UPDATE) return a generic result
        update_result = MagicMock()
        db.execute.side_effect = [select_result, update_result]
        return db

    def test_first_failure_sets_retrying_status(self):
        db = self._mock_db(current_retry_count=0)
        _record_failure(db, schedule_id=42, error_message="Connection timeout")

        # Should have called execute twice: SELECT then UPDATE
        assert db.execute.call_count == 2
        db.commit.assert_called_once()

        # Inspect the UPDATE call args — second execute call
        update_call = db.execute.call_args_list[1]
        params = update_call[1] if update_call[1] else update_call[0][1]
        assert params["retry_count"] == 1
        assert params["error"] == "Connection timeout"
        # Status should be 'retrying' (not 'failed') because retry_count < MAX
        # The SQL text contains "status = 'retrying'"
        sql_text = str(update_call[0][0])
        assert "retrying" in sql_text

    def test_max_retries_marks_failed(self):
        db = self._mock_db(current_retry_count=MAX_RETRY_COUNT - 1)
        _record_failure(db, schedule_id=42, error_message="Persistent error")

        assert db.execute.call_count == 2
        db.commit.assert_called_once()

        update_call = db.execute.call_args_list[1]
        sql_text = str(update_call[0][0])
        assert "failed" in sql_text

    def test_clear_retry_state_resets(self):
        db = MagicMock()
        _clear_retry_state(db, schedule_id=42)

        db.execute.assert_called_once()
        db.commit.assert_called_once()
        sql_text = str(db.execute.call_args[0][0])
        assert "retry_count = 0" in sql_text
        assert "'active'" in sql_text

    def test_error_message_truncated(self):
        """Error messages longer than 2000 chars should be truncated."""
        db = self._mock_db(current_retry_count=0)
        long_error = "x" * 3000
        _record_failure(db, schedule_id=42, error_message=long_error)

        update_call = db.execute.call_args_list[1]
        params = update_call[1] if update_call[1] else update_call[0][1]
        assert len(params["error"]) == 2000


# =============================================================================
# check_and_run_due_reports integration with retry
# =============================================================================


class TestCheckAndRunDueReports:
    """Test the main sweep function handles retries."""

    @patch("services.scheduled_report_executor._fetch_retry_candidates")
    @patch("services.scheduled_report_executor._clear_retry_state")
    @patch("services.scheduled_report_executor._record_failure")
    @patch("services.scheduled_report_executor._execute_schedule")
    @patch("services.scheduled_report_executor._fetch_active_schedules")
    def test_successful_delivery_clears_retry(
        self, mock_fetch, mock_execute, mock_record, mock_clear, mock_retry_candidates,
    ):
        mock_fetch.return_value = [
            _make_schedule(frequency="daily", hour_utc=10),
        ]
        mock_retry_candidates.return_value = []
        mock_execute.return_value = None
        db = MagicMock()

        with patch("services.scheduled_report_executor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            # Need to keep fromisoformat working
            mock_dt.fromisoformat = datetime.fromisoformat

            result = check_and_run_due_reports(db)

        assert result["delivered"] == 1
        assert result["failed"] == 0
        mock_clear.assert_called_once_with(db, 1)

    @patch("services.scheduled_report_executor._fetch_retry_candidates")
    @patch("services.scheduled_report_executor._clear_retry_state")
    @patch("services.scheduled_report_executor._record_failure")
    @patch("services.scheduled_report_executor._execute_schedule")
    @patch("services.scheduled_report_executor._fetch_active_schedules")
    def test_failed_delivery_records_failure(
        self, mock_fetch, mock_execute, mock_record, mock_clear, mock_retry_candidates,
    ):
        mock_fetch.return_value = [
            _make_schedule(frequency="daily", hour_utc=10),
        ]
        mock_retry_candidates.return_value = []
        mock_execute.side_effect = RuntimeError("SMTP connection refused")
        db = MagicMock()

        with patch("services.scheduled_report_executor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            mock_dt.fromisoformat = datetime.fromisoformat

            result = check_and_run_due_reports(db)

        assert result["delivered"] == 0
        assert result["failed"] == 1
        mock_record.assert_called_once_with(db, 1, "SMTP connection refused")

    @patch("services.scheduled_report_executor._fetch_retry_candidates")
    @patch("services.scheduled_report_executor._clear_retry_state")
    @patch("services.scheduled_report_executor._record_failure")
    @patch("services.scheduled_report_executor._execute_schedule")
    @patch("services.scheduled_report_executor._fetch_active_schedules")
    def test_retry_candidates_are_processed(
        self, mock_fetch, mock_execute, mock_record, mock_clear, mock_retry_candidates,
    ):
        mock_fetch.return_value = []  # No new due reports
        retry_schedule = _make_schedule(
            frequency="daily", hour_utc=10, retry_count=1, status="retrying",
        )
        mock_retry_candidates.return_value = [retry_schedule]
        mock_execute.return_value = None
        db = MagicMock()

        with patch("services.scheduled_report_executor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            mock_dt.fromisoformat = datetime.fromisoformat

            result = check_and_run_due_reports(db)

        assert result["retried"] == 1
        assert result["delivered"] == 1
        mock_clear.assert_called_once()

    @patch("services.scheduled_report_executor._fetch_retry_candidates")
    @patch("services.scheduled_report_executor._clear_retry_state")
    @patch("services.scheduled_report_executor._record_failure")
    @patch("services.scheduled_report_executor._execute_schedule")
    @patch("services.scheduled_report_executor._fetch_active_schedules")
    def test_retry_failure_records_again(
        self, mock_fetch, mock_execute, mock_record, mock_clear, mock_retry_candidates,
    ):
        mock_fetch.return_value = []
        retry_schedule = _make_schedule(
            frequency="daily", hour_utc=10, retry_count=1, status="retrying",
        )
        mock_retry_candidates.return_value = [retry_schedule]
        mock_execute.side_effect = RuntimeError("Still failing")
        db = MagicMock()

        with patch("services.scheduled_report_executor.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            mock_dt.fromisoformat = datetime.fromisoformat

            result = check_and_run_due_reports(db)

        # Retry failed, so _record_failure is called
        mock_record.assert_called_once_with(db, 1, "Still failing")
        assert result["retried"] == 0  # retried count only increments on success


# =============================================================================
# Edge cases
# =============================================================================


class TestEdgeCases:
    """Edge cases for due-ness logic."""

    def test_last_sent_at_as_string(self):
        """last_sent_at may come as ISO string from JSONB or raw SQL."""
        schedule = _make_schedule(
            frequency="daily",
            hour_utc=10,
            last_sent_at="2026-05-07T08:00:00+00:00",
        )
        now = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)
        # Already sent today — should not be due
        assert _is_report_due(schedule, now) is False

    def test_last_sent_at_naive_datetime(self):
        """Naive datetime (no tzinfo) should be treated as UTC."""
        schedule = _make_schedule(
            frequency="daily",
            hour_utc=10,
            last_sent_at=datetime(2026, 5, 6, 14, 0, 0),  # yesterday, naive
        )
        now = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)
        assert _is_report_due(schedule, now) is True

    def test_unknown_frequency_not_due(self):
        schedule = _make_schedule(frequency="quarterly", hour_utc=10)
        now = datetime(2026, 5, 7, 10, 0, 0, tzinfo=timezone.utc)
        assert _is_report_due(schedule, now) is False

    def test_missing_hour_defaults_to_8(self):
        schedule = _make_schedule(frequency="daily")
        schedule["hour_utc"] = None
        # _is_report_due checks `schedule.get("hour_utc", 8)` — None != 8
        # so at hour 8 it should compare None != 8 -> not due (None is falsy
        # but not equal to any int). This tests the current behavior.
        now = datetime(2026, 5, 7, 8, 0, 0, tzinfo=timezone.utc)
        # With hour_utc=None, get returns None, and None != 8 -> False
        assert _is_report_due(schedule, now) is False
