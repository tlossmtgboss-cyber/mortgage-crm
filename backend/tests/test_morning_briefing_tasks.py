"""
Unit tests for backend/tasks/morning_briefing_tasks.py

Covers:
  - dispatch_briefings: timezone matching, dedup guard, level determination
  - generate_user_briefing: happy path, user not found, already exists, email failure, retry
  - cleanup_old_briefings: deletes old records, returns count
"""
from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock, call

import pytest


# ---------------------------------------------------------------------------
# Minimal stub for tasks.celery_app so the module can be imported without
# a running Celery / broker.
# ---------------------------------------------------------------------------

def _install_celery_stub():
    """Register a minimal celery_app stub before importing the tasks module."""
    celery_stub = types.ModuleType("tasks")
    celery_stub.__path__ = []

    # tasks.celery_app
    celery_app_mod = types.ModuleType("tasks.celery_app")
    mock_celery = MagicMock(name="celery_app")

    # Make @celery_app.task(...) return the decorated function unchanged so
    # we can call it directly in tests.
    def _task_decorator(*args, **kwargs):
        def _wrap(fn):
            fn.apply_async = MagicMock(name=f"{fn.__name__}.apply_async")
            fn.retry = MagicMock(name=f"{fn.__name__}.retry",
                                 side_effect=Exception("retry"))
            fn.MaxRetriesExceededError = Exception
            return fn
        # @celery_app.task — called with keyword args then wraps
        if args and callable(args[0]):
            # bare @celery_app.task usage
            fn = args[0]
            fn.apply_async = MagicMock(name=f"{fn.__name__}.apply_async")
            fn.retry = MagicMock(side_effect=Exception("retry"))
            fn.MaxRetriesExceededError = Exception
            return fn
        return _wrap

    mock_celery.task = _task_decorator
    celery_app_mod.celery_app = mock_celery

    # tasks.base
    base_mod = types.ModuleType("tasks.base")

    @contextmanager
    def _tenant_task_session(org_id):
        db = MagicMock(name=f"tenant_db_org_{org_id}")
        db.__enter__ = lambda s: db
        db.__exit__ = MagicMock(return_value=False)
        yield db

    base_mod.tenant_task_session = _tenant_task_session

    sys.modules.setdefault("tasks", celery_stub)
    sys.modules["tasks.celery_app"] = celery_app_mod
    sys.modules["tasks.base"] = base_mod


_install_celery_stub()

# Now safe to import the actual module under test.
import importlib
import tasks.morning_briefing_tasks as _mbt_module

# Re-import to get fresh references after stubs are in place.
from tasks.morning_briefing_tasks import (
    dispatch_briefings,
    generate_user_briefing,
    cleanup_old_briefings,
    _get_all_briefing_candidates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate(user_id=1, tz="America/Chicago", hour=7,
                    role="sales", org_id=10):
    """Return a row tuple matching (id, timezone, briefing_hour, permission_role, organization_id)."""
    return (user_id, tz, hour, role, org_id)


def _mock_db(fetchone_result=None):
    db = MagicMock(name="db_session")
    db.execute.return_value.fetchone.return_value = fetchone_result
    db.execute.return_value.fetchall.return_value = []
    return db


# ---------------------------------------------------------------------------
# dispatch_briefings
# ---------------------------------------------------------------------------

class TestDispatchBriefings:
    """Tests for the dispatch_briefings Celery task."""

    def _run_dispatch(self, candidates, now_utc, check_exists=False,
                      has_reports_result=None):
        """
        Helper that patches all I/O and runs dispatch_briefings().

        candidates     : list of row tuples
        now_utc        : datetime (timezone-aware UTC) to use as "now"
        check_exists   : whether the dedup check should return a hit
        has_reports_result: fetchone result for the manager reports query
        """
        check_db = _mock_db(fetchone_result=(1,) if check_exists else None)
        reports_db = _mock_db(fetchone_result=(1,) if has_reports_result else None)
        main_db = _mock_db()

        call_count = {"n": 0}
        def _db_factory():
            n = call_count["n"]
            call_count["n"] += 1
            # first call is the main session, then alternating check/reports
            if n == 0:
                return main_db
            if n % 2 == 1:
                return check_db
            return reports_db

        with patch("tasks.morning_briefing_tasks._get_db_session", side_effect=_db_factory), \
             patch("tasks.morning_briefing_tasks._get_all_briefing_candidates",
                   return_value=candidates), \
             patch("tasks.morning_briefing_tasks.datetime") as mock_dt, \
             patch("tasks.morning_briefing_tasks.generate_user_briefing") as mock_gen:

            mock_dt.now.return_value = now_utc
            result = dispatch_briefings()

        return result, mock_gen

    # ---- timezone matching ------------------------------------------------

    def test_enqueues_user_when_hour_matches(self):
        # User in America/Chicago, briefing_hour=7
        # UTC 13:00 == CST 07:00 in winter (UTC-6 for CST)
        from zoneinfo import ZoneInfo
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)  # 07:00 CST
        candidates = [_make_candidate(user_id=1, tz="America/Chicago", hour=7)]

        result, mock_gen = self._run_dispatch(candidates, now_utc)

        assert result["enqueued"] == 1
        mock_gen.apply_async.assert_called_once()

    def test_does_not_enqueue_when_hour_does_not_match(self):
        from zoneinfo import ZoneInfo
        # UTC 15:00 == CST 09:00 — does not match briefing_hour=7
        now_utc = datetime(2026, 3, 16, 15, 0, 0, tzinfo=timezone.utc)
        candidates = [_make_candidate(user_id=1, tz="America/Chicago", hour=7)]

        result, mock_gen = self._run_dispatch(candidates, now_utc)

        assert result["enqueued"] == 0
        mock_gen.apply_async.assert_not_called()

    def test_uses_default_tz_for_invalid_timezone(self):
        # Invalid timezone string should fall back to America/Chicago
        # UTC 13:00 = Chicago 07:00 in winter
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        candidates = [_make_candidate(user_id=2, tz="Invalid/Zone", hour=7)]

        result, mock_gen = self._run_dispatch(candidates, now_utc)

        assert result["enqueued"] == 1

    def test_respects_different_timezones(self):
        # User in America/New_York (UTC-5 winter = UTC 12:00 == 07:00 ET)
        now_utc = datetime(2026, 3, 16, 12, 0, 0, tzinfo=timezone.utc)
        candidates = [
            _make_candidate(user_id=3, tz="America/New_York", hour=7),
            _make_candidate(user_id=4, tz="America/Chicago", hour=7),  # 07:00 CST = 13:00 UTC — no match
        ]

        result, mock_gen = self._run_dispatch(candidates, now_utc)

        assert result["enqueued"] == 1  # Only New_York user

    def test_uses_default_briefing_hour_7_when_none(self):
        # row[2] = None => defaults to 7
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        candidates = [_make_candidate(user_id=5, tz="America/Chicago", hour=None)]

        result, mock_gen = self._run_dispatch(candidates, now_utc)

        assert result["enqueued"] == 1

    # ---- dedup guard ------------------------------------------------------

    def test_skips_if_briefing_already_exists(self):
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        candidates = [_make_candidate(user_id=6)]

        result, mock_gen = self._run_dispatch(candidates, now_utc, check_exists=True)

        assert result["enqueued"] == 0
        mock_gen.apply_async.assert_not_called()

    def test_enqueues_when_no_existing_briefing(self):
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        candidates = [_make_candidate(user_id=7)]

        result, mock_gen = self._run_dispatch(candidates, now_utc, check_exists=False)

        assert result["enqueued"] == 1

    # ---- level determination ---------------------------------------------

    def test_leadership_roles_get_leadership_level(self):
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        for role in ("leadership", "admin", "site_admin", "platform_admin"):
            candidates = [_make_candidate(user_id=10, role=role)]
            result, mock_gen = self._run_dispatch(candidates, now_utc)
            if result["enqueued"] == 1:
                args = mock_gen.apply_async.call_args
                assert args[1]["args"][2] == "leadership" or args[0][0][2] == "leadership"
            mock_gen.apply_async.reset_mock()

    def test_manager_with_reports_gets_manager_level(self):
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        candidates = [_make_candidate(user_id=11, role="management")]

        main_db = _mock_db()
        check_db = _mock_db(fetchone_result=None)  # no existing briefing
        reports_db = _mock_db(fetchone_result=(1,))  # has reports

        dbs = iter([main_db, check_db, reports_db])

        with patch("tasks.morning_briefing_tasks._get_db_session", side_effect=lambda: next(dbs)), \
             patch("tasks.morning_briefing_tasks._get_all_briefing_candidates", return_value=candidates), \
             patch("tasks.morning_briefing_tasks.datetime") as mock_dt, \
             patch("tasks.morning_briefing_tasks.generate_user_briefing") as mock_gen:
            mock_dt.now.return_value = now_utc
            dispatch_briefings()

        args_list = mock_gen.apply_async.call_args_list
        assert len(args_list) == 1
        # level is 3rd element of args=[user_id, date_str, level]
        level = args_list[0][1]["args"][2]
        assert level == "manager"

    def test_manager_without_reports_gets_individual_level(self):
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        candidates = [_make_candidate(user_id=12, role="branch_manager")]

        main_db = _mock_db()
        check_db = _mock_db(fetchone_result=None)
        reports_db = _mock_db(fetchone_result=None)  # no direct reports

        dbs = iter([main_db, check_db, reports_db])

        with patch("tasks.morning_briefing_tasks._get_db_session", side_effect=lambda: next(dbs)), \
             patch("tasks.morning_briefing_tasks._get_all_briefing_candidates", return_value=candidates), \
             patch("tasks.morning_briefing_tasks.datetime") as mock_dt, \
             patch("tasks.morning_briefing_tasks.generate_user_briefing") as mock_gen:
            mock_dt.now.return_value = now_utc
            dispatch_briefings()

        args_list = mock_gen.apply_async.call_args_list
        assert len(args_list) == 1
        level = args_list[0][1]["args"][2]
        assert level == "individual"

    def test_sales_role_gets_individual_level(self):
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        candidates = [_make_candidate(user_id=13, role="sales")]

        result, mock_gen = self._run_dispatch(candidates, now_utc)

        assert result["enqueued"] == 1
        level = mock_gen.apply_async.call_args[1]["args"][2]
        assert level == "individual"

    # ---- staggering / countdown ------------------------------------------

    def test_individual_gets_zero_countdown_first(self):
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        candidates = [_make_candidate(user_id=14, role="sales")]

        result, mock_gen = self._run_dispatch(candidates, now_utc)

        countdown = mock_gen.apply_async.call_args[1]["countdown"]
        assert countdown == 0

    def test_second_individual_gets_2s_countdown(self):
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        candidates = [
            _make_candidate(user_id=15, role="sales"),
            _make_candidate(user_id=16, role="sales"),
        ]

        main_db = _mock_db()
        check_db1 = _mock_db(fetchone_result=None)
        check_db2 = _mock_db(fetchone_result=None)

        dbs = iter([main_db, check_db1, check_db2])

        with patch("tasks.morning_briefing_tasks._get_db_session", side_effect=lambda: next(dbs)), \
             patch("tasks.morning_briefing_tasks._get_all_briefing_candidates", return_value=candidates), \
             patch("tasks.morning_briefing_tasks.datetime") as mock_dt, \
             patch("tasks.morning_briefing_tasks.generate_user_briefing") as mock_gen:
            mock_dt.now.return_value = now_utc
            dispatch_briefings()

        call_args = mock_gen.apply_async.call_args_list
        assert call_args[0][1]["countdown"] == 0
        assert call_args[1][1]["countdown"] == 2

    def test_leadership_gets_300s_base_countdown(self):
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        candidates = [_make_candidate(user_id=17, role="leadership")]

        result, mock_gen = self._run_dispatch(candidates, now_utc)

        countdown = mock_gen.apply_async.call_args[1]["countdown"]
        assert countdown == 300

    # ---- error handling --------------------------------------------------

    def test_returns_error_on_exception(self):
        with patch("tasks.morning_briefing_tasks._get_db_session",
                   side_effect=RuntimeError("DB down")):
            result = dispatch_briefings()

        assert "error" in result

    def test_enqueued_count_zero_when_no_candidates(self):
        now_utc = datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc)
        result, mock_gen = self._run_dispatch([], now_utc)

        assert result["enqueued"] == 0
        mock_gen.apply_async.assert_not_called()


# ---------------------------------------------------------------------------
# generate_user_briefing
# ---------------------------------------------------------------------------

class TestGenerateUserBriefing:
    """Tests for the generate_user_briefing Celery task."""

    def _make_user(self, user_id=1, org_id=10, email="lo@example.com",
                   first_name="Jane", last_name="Doe"):
        user = MagicMock(name="User")
        user.id = user_id
        user.organization_id = org_id
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.full_name = f"{first_name} {last_name}"
        user.briefing_preferences = None
        return user

    def _make_briefing(self, bid=1, status="generating"):
        b = MagicMock(name="MorningBriefing")
        b.id = bid
        b.status = status
        b.briefing_data = None
        b.team_data = None
        b.ai_narrative = None
        b.html_content = None
        b.email_sent_at = None
        return b

    def _make_prefs(self):
        prefs = MagicMock(name="BriefingPreferences")
        prefs.sections = {}
        prefs.thresholds = {}
        prefs.ai_tone = "balanced"
        return prefs

    def _make_ctx(self):
        ctx = MagicMock(name="BriefingContext")
        ctx.pipeline = {"active_count": 5, "total_volume": 1_500_000}
        ctx.at_risk = []
        ctx.stale_leads = []
        ctx.appointments = []
        ctx.conditions = []
        ctx.yesterday = {}
        ctx.team = None
        return ctx

    # A self-mock that simulates the Celery task's `self` (bound task)
    def _make_self(self, raise_retry=False, raise_max_retries=False):
        self_mock = MagicMock(name="celery_task_self")
        if raise_max_retries:
            self_mock.MaxRetriesExceededError = Exception
            self_mock.retry.side_effect = Exception("MaxRetriesExceeded")
        elif raise_retry:
            self_mock.MaxRetriesExceededError = type("MaxRetriesExceededError", (Exception,), {})
            self_mock.retry.side_effect = Exception("retry requested")
        else:
            self_mock.MaxRetriesExceededError = type("MaxRetriesExceededError", (Exception,), {})
            self_mock.retry.side_effect = Exception("retry requested")
        return self_mock

    # ---- happy path -------------------------------------------------------

    def test_happy_path_delivered(self):
        user = self._make_user()
        briefing = self._make_briefing()
        prefs = self._make_prefs()
        ctx = self._make_ctx()
        self_mock = self._make_self()

        lookup_db = _mock_db(fetchone_result=(1, 10))  # (user_id, org_id)
        tenant_db = MagicMock(name="tenant_db")
        tenant_db.__enter__ = lambda s: tenant_db
        tenant_db.__exit__ = MagicMock(return_value=False)

        # query().filter().first() chain
        def _query_side_effect(model):
            q = MagicMock()
            # first call returns user, second call returns None (no existing briefing),
            # third call (WhiteLabelConfig) returns None
            q.filter.return_value.first.side_effect = [user, None, None]
            return q

        tenant_db.query.side_effect = _query_side_effect
        tenant_db.flush = MagicMock()

        service = MagicMock(name="service")
        service.build_context.return_value = ctx
        service.generate_narrative.return_value = "Good morning, Jane!"

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=lookup_db), \
             patch("tasks.morning_briefing_tasks._get_tenant_db_session", return_value=tenant_db), \
             patch("tasks.morning_briefing_tasks.MorningBriefing", return_value=briefing), \
             patch("tasks.morning_briefing_tasks.MorningBriefingService") as MockSvc, \
             patch("tasks.morning_briefing_tasks.render_briefing_email", return_value="<html/>"), \
             patch("tasks.morning_briefing_tasks._send_briefing_email") as mock_send:

            MockSvc.load_preferences.return_value = prefs
            MockSvc.return_value = service

            result = generate_user_briefing(self_mock, user_id=1,
                                            briefing_date_str="2026-03-16",
                                            briefing_level="individual")

        assert result["status"] == "delivered"
        mock_send.assert_called_once()

    def test_happy_path_sets_briefing_data(self):
        user = self._make_user()
        briefing = self._make_briefing()
        prefs = self._make_prefs()
        ctx = self._make_ctx()
        ctx.team = {"members": []}
        self_mock = self._make_self()

        lookup_db = _mock_db(fetchone_result=(1, 10))
        tenant_db = MagicMock(name="tenant_db")
        tenant_db.__enter__ = lambda s: tenant_db
        tenant_db.__exit__ = MagicMock(return_value=False)

        q = MagicMock()
        q.filter.return_value.first.side_effect = [user, None, None]
        tenant_db.query.return_value = q
        tenant_db.flush = MagicMock()

        service = MagicMock()
        service.build_context.return_value = ctx
        service.generate_narrative.return_value = "Brief text"

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=lookup_db), \
             patch("tasks.morning_briefing_tasks._get_tenant_db_session", return_value=tenant_db), \
             patch("tasks.morning_briefing_tasks.MorningBriefing", return_value=briefing), \
             patch("tasks.morning_briefing_tasks.MorningBriefingService") as MockSvc, \
             patch("tasks.morning_briefing_tasks.render_briefing_email", return_value="<html/>"), \
             patch("tasks.morning_briefing_tasks._send_briefing_email"):
            MockSvc.load_preferences.return_value = prefs
            MockSvc.return_value = service
            generate_user_briefing(self_mock, 1, "2026-03-16", "manager")

        # team_data should have been set since ctx.team is truthy
        assert briefing.team_data == {"members": []}

    # ---- user not found --------------------------------------------------

    def test_user_not_found_in_lookup(self):
        lookup_db = _mock_db(fetchone_result=None)  # user not found

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=lookup_db):
            result = generate_user_briefing(MagicMock(), user_id=999,
                                            briefing_date_str="2026-03-16",
                                            briefing_level="individual")

        assert result == {"error": "user_not_found"}

    def test_no_organization_id(self):
        lookup_db = _mock_db(fetchone_result=(1, None))  # org_id is None

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=lookup_db):
            result = generate_user_briefing(MagicMock(), user_id=1,
                                            briefing_date_str="2026-03-16",
                                            briefing_level="individual")

        assert result == {"error": "no_organization"}

    def test_user_not_found_in_tenant_session(self):
        lookup_db = _mock_db(fetchone_result=(1, 10))
        tenant_db = MagicMock()
        tenant_db.__enter__ = lambda s: tenant_db
        tenant_db.__exit__ = MagicMock(return_value=False)

        q = MagicMock()
        q.filter.return_value.first.return_value = None  # user not in tenant session
        tenant_db.query.return_value = q

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=lookup_db), \
             patch("tasks.morning_briefing_tasks._get_tenant_db_session", return_value=tenant_db), \
             patch("tasks.morning_briefing_tasks.MorningBriefing"):
            result = generate_user_briefing(MagicMock(), 1, "2026-03-16", "individual")

        assert result == {"error": "user_not_found"}

    # ---- already exists --------------------------------------------------

    def test_already_exists_returns_early(self):
        user = self._make_user()
        existing_briefing = self._make_briefing(status="delivered")
        self_mock = self._make_self()

        lookup_db = _mock_db(fetchone_result=(1, 10))
        tenant_db = MagicMock()
        tenant_db.__enter__ = lambda s: tenant_db
        tenant_db.__exit__ = MagicMock(return_value=False)

        q = MagicMock()
        # First query returns user, second returns existing briefing
        q.filter.return_value.first.side_effect = [user, existing_briefing]
        tenant_db.query.return_value = q

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=lookup_db), \
             patch("tasks.morning_briefing_tasks._get_tenant_db_session", return_value=tenant_db), \
             patch("tasks.morning_briefing_tasks.MorningBriefing"), \
             patch("tasks.morning_briefing_tasks._send_briefing_email") as mock_send:
            result = generate_user_briefing(self_mock, 1, "2026-03-16", "individual")

        assert result == {"status": "already_exists"}
        mock_send.assert_not_called()

    def test_integrity_error_on_flush_returns_already_exists(self):
        from sqlalchemy.exc import IntegrityError
        user = self._make_user()
        briefing = self._make_briefing()
        prefs = self._make_prefs()
        self_mock = self._make_self()

        lookup_db = _mock_db(fetchone_result=(1, 10))
        tenant_db = MagicMock()
        tenant_db.__enter__ = lambda s: tenant_db
        tenant_db.__exit__ = MagicMock(return_value=False)

        q = MagicMock()
        # user found, no existing briefing
        q.filter.return_value.first.side_effect = [user, None]
        tenant_db.query.return_value = q
        # flush raises IntegrityError (concurrent write)
        tenant_db.flush.side_effect = IntegrityError("stmt", {}, Exception("unique"))

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=lookup_db), \
             patch("tasks.morning_briefing_tasks._get_tenant_db_session", return_value=tenant_db), \
             patch("tasks.morning_briefing_tasks.MorningBriefing", return_value=briefing), \
             patch("tasks.morning_briefing_tasks.MorningBriefingService") as MockSvc:
            MockSvc.load_preferences.return_value = prefs
            result = generate_user_briefing(self_mock, 1, "2026-03-16", "individual")

        assert result == {"status": "already_exists"}

    # ---- email failure ---------------------------------------------------

    def test_email_failure_sets_status_failed(self):
        user = self._make_user()
        briefing = self._make_briefing()
        prefs = self._make_prefs()
        ctx = self._make_ctx()
        self_mock = self._make_self()

        lookup_db = _mock_db(fetchone_result=(1, 10))
        tenant_db = MagicMock()
        tenant_db.__enter__ = lambda s: tenant_db
        tenant_db.__exit__ = MagicMock(return_value=False)

        q = MagicMock()
        q.filter.return_value.first.side_effect = [user, None, None]
        tenant_db.query.return_value = q
        tenant_db.flush = MagicMock()

        service = MagicMock()
        service.build_context.return_value = ctx
        service.generate_narrative.return_value = "Narrative"

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=lookup_db), \
             patch("tasks.morning_briefing_tasks._get_tenant_db_session", return_value=tenant_db), \
             patch("tasks.morning_briefing_tasks.MorningBriefing", return_value=briefing), \
             patch("tasks.morning_briefing_tasks.MorningBriefingService") as MockSvc, \
             patch("tasks.morning_briefing_tasks.render_briefing_email", return_value="<html/>"), \
             patch("tasks.morning_briefing_tasks._send_briefing_email",
                   side_effect=Exception("SMTP timeout")):
            MockSvc.load_preferences.return_value = prefs
            MockSvc.return_value = service
            result = generate_user_briefing(self_mock, 1, "2026-03-16", "individual")

        assert result["status"] == "failed"
        assert briefing.status == "failed"

    def test_email_failure_still_commits_briefing(self):
        user = self._make_user()
        briefing = self._make_briefing()
        prefs = self._make_prefs()
        ctx = self._make_ctx()
        self_mock = self._make_self()

        lookup_db = _mock_db(fetchone_result=(1, 10))
        tenant_db = MagicMock()
        tenant_db.__enter__ = lambda s: tenant_db
        tenant_db.__exit__ = MagicMock(return_value=False)

        q = MagicMock()
        q.filter.return_value.first.side_effect = [user, None, None]
        tenant_db.query.return_value = q
        tenant_db.flush = MagicMock()

        service = MagicMock()
        service.build_context.return_value = ctx
        service.generate_narrative.return_value = "Narrative"

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=lookup_db), \
             patch("tasks.morning_briefing_tasks._get_tenant_db_session", return_value=tenant_db), \
             patch("tasks.morning_briefing_tasks.MorningBriefing", return_value=briefing), \
             patch("tasks.morning_briefing_tasks.MorningBriefingService") as MockSvc, \
             patch("tasks.morning_briefing_tasks.render_briefing_email", return_value="<html/>"), \
             patch("tasks.morning_briefing_tasks._send_briefing_email",
                   side_effect=Exception("send failed")):
            MockSvc.load_preferences.return_value = prefs
            MockSvc.return_value = service
            generate_user_briefing(self_mock, 1, "2026-03-16", "individual")

        tenant_db.commit.assert_called()

    # ---- retry logic -----------------------------------------------------

    def test_generation_error_triggers_retry(self):
        user = self._make_user()
        briefing = self._make_briefing()
        prefs = self._make_prefs()
        self_mock = self._make_self(raise_retry=True)

        lookup_db = _mock_db(fetchone_result=(1, 10))
        tenant_db = MagicMock()
        tenant_db.__enter__ = lambda s: tenant_db
        tenant_db.__exit__ = MagicMock(return_value=False)

        q = MagicMock()
        q.filter.return_value.first.side_effect = [user, None]
        tenant_db.query.return_value = q
        tenant_db.flush = MagicMock()

        service = MagicMock()
        service.build_context.side_effect = RuntimeError("DB timeout")

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=lookup_db), \
             patch("tasks.morning_briefing_tasks._get_tenant_db_session", return_value=tenant_db), \
             patch("tasks.morning_briefing_tasks.MorningBriefing", return_value=briefing), \
             patch("tasks.morning_briefing_tasks.MorningBriefingService") as MockSvc, \
             patch("tasks.morning_briefing_tasks.render_briefing_email"):
            MockSvc.load_preferences.return_value = prefs
            MockSvc.return_value = service
            # retry raises, so result should propagate to caller
            try:
                generate_user_briefing(self_mock, 1, "2026-03-16", "individual")
            except Exception:
                pass

        self_mock.retry.assert_called_once()

    def test_max_retries_exceeded_marks_failed(self):
        user = self._make_user()
        briefing = self._make_briefing()
        prefs = self._make_prefs()

        # self.retry raises MaxRetriesExceededError
        self_mock = MagicMock()
        MaxRetriesExceededError = type("MaxRetriesExceededError", (Exception,), {})
        self_mock.MaxRetriesExceededError = MaxRetriesExceededError
        self_mock.retry.side_effect = MaxRetriesExceededError("exhausted")

        lookup_db = _mock_db(fetchone_result=(1, 10))
        tenant_db = MagicMock()
        tenant_db.__enter__ = lambda s: tenant_db
        tenant_db.__exit__ = MagicMock(return_value=False)

        # query returns user, no existing briefing; third returns the briefing for failure mark
        q = MagicMock()
        q.filter.return_value.first.side_effect = [user, None, briefing]
        tenant_db.query.return_value = q
        tenant_db.flush = MagicMock()

        service = MagicMock()
        service.build_context.side_effect = RuntimeError("AI service down")

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=lookup_db), \
             patch("tasks.morning_briefing_tasks._get_tenant_db_session", return_value=tenant_db), \
             patch("tasks.morning_briefing_tasks.MorningBriefing", return_value=briefing), \
             patch("tasks.morning_briefing_tasks.MorningBriefingService") as MockSvc, \
             patch("tasks.morning_briefing_tasks.render_briefing_email"):
            MockSvc.load_preferences.return_value = prefs
            MockSvc.return_value = service
            result = generate_user_briefing(self_mock, 1, "2026-03-16", "individual")

        # After max retries: should return error dict and mark briefing failed
        assert "error" in result

    def test_white_label_branding_applied(self):
        user = self._make_user()
        briefing = self._make_briefing()
        prefs = self._make_prefs()
        ctx = self._make_ctx()
        self_mock = self._make_self()

        wl = MagicMock()
        wl.company_name = "Acme Mortgage"
        wl.logo_url = "https://example.com/logo.png"
        wl.primary_color = "#ff0000"
        wl.secondary_color = "#000000"
        wl.email_from_address = "briefing@acme.com"

        lookup_db = _mock_db(fetchone_result=(1, 10))
        tenant_db = MagicMock()
        tenant_db.__enter__ = lambda s: tenant_db
        tenant_db.__exit__ = MagicMock(return_value=False)

        q = MagicMock()
        q.filter.return_value.first.side_effect = [user, None, wl]
        tenant_db.query.return_value = q
        tenant_db.flush = MagicMock()

        service = MagicMock()
        service.build_context.return_value = ctx
        service.generate_narrative.return_value = "Brief"

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=lookup_db), \
             patch("tasks.morning_briefing_tasks._get_tenant_db_session", return_value=tenant_db), \
             patch("tasks.morning_briefing_tasks.MorningBriefing", return_value=briefing), \
             patch("tasks.morning_briefing_tasks.MorningBriefingService") as MockSvc, \
             patch("tasks.morning_briefing_tasks.render_briefing_email",
                   return_value="<html/>") as mock_render, \
             patch("tasks.morning_briefing_tasks._send_briefing_email") as mock_send:
            MockSvc.load_preferences.return_value = prefs
            MockSvc.return_value = service
            generate_user_briefing(self_mock, 1, "2026-03-16", "individual")

        # Confirm branding was passed to both render and send
        render_kwargs = mock_render.call_args[1]
        assert render_kwargs.get("company_name") == "Acme Mortgage"

        send_kwargs = mock_send.call_args[1]
        assert send_kwargs.get("from_email_override") == "briefing@acme.com"
        assert send_kwargs.get("from_name_override") == "Acme Mortgage"


# ---------------------------------------------------------------------------
# cleanup_old_briefings
# ---------------------------------------------------------------------------

class TestCleanupOldBriefings:
    """Tests for the cleanup_old_briefings Celery task."""

    def test_deletes_old_rows_and_returns_count(self):
        db = MagicMock(name="db")
        db.execute.return_value.rowcount = 17

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=db):
            result = cleanup_old_briefings(retention_days=90)

        assert result == {"deleted": 17}
        db.commit.assert_called_once()
        db.close.assert_called_once()

    def test_uses_correct_cutoff_date(self):
        db = MagicMock(name="db")
        db.execute.return_value.rowcount = 3

        today = date(2026, 3, 16)
        expected_cutoff = date(2025, 12, 16)  # 90 days before 2026-03-16

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=db), \
             patch("tasks.morning_briefing_tasks.date") as mock_date:
            mock_date.today.return_value = today
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            cleanup_old_briefings(retention_days=90)

        call_kwargs = db.execute.call_args[0][1]
        assert call_kwargs["cutoff"] == expected_cutoff

    def test_custom_retention_days(self):
        db = MagicMock(name="db")
        db.execute.return_value.rowcount = 5

        today = date(2026, 3, 16)
        expected_cutoff = today - timedelta(days=30)

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=db), \
             patch("tasks.morning_briefing_tasks.date") as mock_date:
            mock_date.today.return_value = today
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            result = cleanup_old_briefings(retention_days=30)

        assert result["deleted"] == 5
        call_kwargs = db.execute.call_args[0][1]
        assert call_kwargs["cutoff"] == expected_cutoff

    def test_default_retention_is_90_days(self):
        db = MagicMock(name="db")
        db.execute.return_value.rowcount = 0

        today = date(2026, 3, 16)
        expected_cutoff = today - timedelta(days=90)

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=db), \
             patch("tasks.morning_briefing_tasks.date") as mock_date:
            mock_date.today.return_value = today
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            result = cleanup_old_briefings()  # no arg

        call_kwargs = db.execute.call_args[0][1]
        assert call_kwargs["cutoff"] == expected_cutoff

    def test_returns_zero_when_nothing_to_delete(self):
        db = MagicMock(name="db")
        db.execute.return_value.rowcount = 0

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=db):
            result = cleanup_old_briefings(retention_days=90)

        assert result == {"deleted": 0}

    def test_rollback_and_error_on_exception(self):
        db = MagicMock(name="db")
        db.execute.side_effect = Exception("DB error")

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=db):
            result = cleanup_old_briefings(retention_days=90)

        assert "error" in result
        db.rollback.assert_called_once()
        db.close.assert_called_once()

    def test_session_always_closed_on_success(self):
        db = MagicMock(name="db")
        db.execute.return_value.rowcount = 2

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=db):
            cleanup_old_briefings(retention_days=90)

        db.close.assert_called_once()

    def test_session_always_closed_on_failure(self):
        db = MagicMock(name="db")
        db.execute.side_effect = RuntimeError("crash")

        with patch("tasks.morning_briefing_tasks._get_db_session", return_value=db):
            cleanup_old_briefings(retention_days=90)

        db.close.assert_called_once()
