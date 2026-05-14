"""
Tests for the unified SchedulerService with distributed locking.

Covers:
  - Job registration from the centralized registry
  - Distributed lock prevents duplicate execution across replicas
  - Scheduler start/shutdown lifecycle
  - Job status reporting with execution history
  - register_job() individual job registration
"""

import os
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Set TESTING env before imports
os.environ["TESTING"] = "1"


class TestSchedulerServiceInit:
    """Test SchedulerService initialization and configuration."""

    def test_scheduler_service_creates_background_scheduler(self):
        """SchedulerService should create a BackgroundScheduler with correct defaults."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        assert svc.scheduler is not None
        assert svc._jobs_registered is False
        assert svc._execution_log == {}

    def test_scheduler_service_singleton_exists(self):
        """Module-level scheduler_service should be a SchedulerService instance."""
        from services.scheduler_service import scheduler_service, SchedulerService

        assert isinstance(scheduler_service, SchedulerService)


class TestJobRegistration:
    """Test job registration methods."""

    def test_register_job_cron(self):
        """register_job should add a cron job to APScheduler."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        called = []

        def my_job():
            called.append(1)

        svc.register_job(
            name="test_cron_job",
            func=my_job,
            trigger="cron",
            description="Test cron job",
            lock_ttl=60,
            minute=0,
            hour=3,
        )

        jobs = svc.scheduler.get_jobs()
        job_ids = [j.id for j in jobs]
        assert "test_cron_job" in job_ids

    def test_register_job_interval(self):
        """register_job should add an interval job to APScheduler."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()

        def my_interval_job():
            pass

        svc.register_job(
            name="test_interval_job",
            func=my_interval_job,
            trigger="interval",
            description="Test interval job",
            lock_ttl=30,
            minutes=10,
        )

        jobs = svc.scheduler.get_jobs()
        job_ids = [j.id for j in jobs]
        assert "test_interval_job" in job_ids

    def test_register_job_invalid_trigger_raises(self):
        """register_job should raise ValueError for unknown trigger types."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()

        with pytest.raises(ValueError, match="Unknown trigger type"):
            svc.register_job(
                name="bad_job",
                func=lambda: None,
                trigger="daily",
                description="Bad trigger",
            )

    def test_register_job_replace_existing(self):
        """Registering a job with the same name should replace it."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        svc.register_job("dup_job", lambda: None, "interval", "First", minutes=5)
        svc.register_job("dup_job", lambda: None, "interval", "Second", minutes=10)

        jobs = [j for j in svc.scheduler.get_jobs() if j.id == "dup_job"]
        assert len(jobs) == 1
        assert jobs[0].name == "Second"

    def test_register_from_registry(self):
        """register_from_registry should register all jobs from scheduled_jobs module."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        svc.register_from_registry()

        jobs = svc.scheduler.get_jobs()
        job_ids = {j.id for j in jobs}

        # Should have registered the core jobs from the registry
        assert "application_reminders" in job_ids
        assert "appointment_reminders" in job_ids
        assert "workflow_task_generation" in job_ids
        assert "stale_cleanup" in job_ids
        assert "slot_hold_cleanup" in job_ids
        assert "webhook_dead_letter_retry" in job_ids
        assert "audit_log_retention" in job_ids
        assert "agent_message_processor" in job_ids


class TestDistributedLockWrapping:
    """Test that jobs are wrapped with distributed lock guard."""

    def test_job_skipped_when_lock_held(self):
        """When Redis lock is held by another replica, job should be skipped."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        called = []

        def my_job():
            called.append(1)

        # Mock the distributed lock service to simulate lock already held
        mock_redis = MagicMock()
        mock_redis.set.return_value = False  # Lock not acquired (held by other)

        mock_lock_svc = MagicMock()
        mock_lock_svc._get_redis.return_value = mock_redis

        with patch("services.scheduler_service.functools.wraps", side_effect=lambda f: lambda g: g):
            pass

        # Use the _wrap_with_lock directly
        wrapped = svc._wrap_with_lock("test_lock_job", my_job, lock_ttl=30)

        with patch("services.distributed_lock.get_lock_service", return_value=mock_lock_svc):
            wrapped()

        # Job should NOT have been called
        assert len(called) == 0
        # Execution log should show skipped
        assert svc._execution_log["test_lock_job"]["last_status"] == "skipped_lock"
        assert svc._execution_log["test_lock_job"]["lock_acquired"] is False

    def test_job_runs_when_lock_acquired(self):
        """When Redis lock is acquired, job should run."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        called = []

        def my_job():
            called.append(1)
            return "done"

        mock_redis = MagicMock()
        mock_redis.set.return_value = True  # Lock acquired

        mock_lock_svc = MagicMock()
        mock_lock_svc._get_redis.return_value = mock_redis

        wrapped = svc._wrap_with_lock("test_run_job", my_job, lock_ttl=30)

        with patch("services.distributed_lock.get_lock_service", return_value=mock_lock_svc):
            result = wrapped()

        assert len(called) == 1
        assert svc._execution_log["test_run_job"]["last_status"] == "success"
        assert svc._execution_log["test_run_job"]["lock_acquired"] is True
        assert svc._execution_log["test_run_job"]["last_duration_ms"] >= 0

    def test_job_runs_when_redis_unavailable(self):
        """When Redis is unavailable, job should still run (fallback to advisory lock)."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        called = []

        def my_job():
            called.append(1)

        mock_lock_svc = MagicMock()
        mock_lock_svc._get_redis.return_value = None  # Redis unavailable

        wrapped = svc._wrap_with_lock("test_no_redis_job", my_job, lock_ttl=30)

        with patch("services.distributed_lock.get_lock_service", return_value=mock_lock_svc):
            wrapped()

        # Job should run even without Redis
        assert len(called) == 1
        assert svc._execution_log["test_no_redis_job"]["last_status"] == "success"

    def test_job_runs_when_lock_service_unavailable(self):
        """When the lock service module can't be imported, job should still run."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        called = []

        def my_job():
            called.append(1)

        wrapped = svc._wrap_with_lock("test_no_lock_svc", my_job, lock_ttl=30)

        with patch("services.distributed_lock.get_lock_service", side_effect=ImportError("no module")):
            wrapped()

        assert len(called) == 1

    def test_job_error_recorded_in_execution_log(self):
        """When a job raises an exception, it should be recorded in execution log."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()

        def failing_job():
            raise ValueError("test error")

        mock_lock_svc = MagicMock()
        mock_lock_svc._get_redis.return_value = None

        wrapped = svc._wrap_with_lock("test_error_job", failing_job, lock_ttl=30)

        with patch("services.distributed_lock.get_lock_service", return_value=mock_lock_svc):
            with pytest.raises(ValueError, match="test error"):
                wrapped()

        assert svc._execution_log["test_error_job"]["last_status"] == "error"
        assert "test error" in svc._execution_log["test_error_job"]["last_error"]

    def test_lock_released_after_job_completion(self):
        """Lock should be released after job completes (success or failure)."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()

        def my_job():
            pass

        mock_redis = MagicMock()
        mock_redis.set.return_value = True

        mock_lock_svc = MagicMock()
        mock_lock_svc._get_redis.return_value = mock_redis

        wrapped = svc._wrap_with_lock("test_release_job", my_job, lock_ttl=30)

        with patch("services.distributed_lock.get_lock_service", return_value=mock_lock_svc):
            wrapped()

        # Verify release was called
        mock_lock_svc._release.assert_called_once()

    def test_concurrent_execution_prevented(self):
        """Two threads trying to run the same job should result in only one execution."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        executions = []
        lock = threading.Lock()

        def slow_job():
            with lock:
                executions.append(threading.current_thread().name)
            time.sleep(0.1)  # Simulate work

        # Simulate Redis lock: first call acquires, second fails
        call_count = {"n": 0}

        def mock_set(key, value, nx=False, ex=None):
            call_count["n"] += 1
            # First caller gets the lock, second does not
            return call_count["n"] == 1

        mock_redis = MagicMock()
        mock_redis.set = mock_set

        mock_lock_svc = MagicMock()
        mock_lock_svc._get_redis.return_value = mock_redis

        wrapped = svc._wrap_with_lock("test_concurrent_job", slow_job, lock_ttl=30)

        with patch("services.distributed_lock.get_lock_service", return_value=mock_lock_svc):
            t1 = threading.Thread(target=wrapped, name="replica-1")
            t2 = threading.Thread(target=wrapped, name="replica-2")
            t1.start()
            t2.start()
            t1.join()
            t2.join()

        # Only one thread should have executed the job
        assert len(executions) == 1


class TestSchedulerLifecycle:
    """Test scheduler start/shutdown lifecycle."""

    def test_start_registers_jobs_and_starts(self):
        """start() should register jobs and start the scheduler."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()

        with patch.object(svc, 'register_from_registry') as mock_reg:
            svc.start()
            mock_reg.assert_called_once()

        assert svc._jobs_registered is True
        assert svc.scheduler.running is True

        # Cleanup
        svc.stop()

    def test_start_idempotent(self):
        """Calling start() twice should not re-register jobs."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()

        with patch.object(svc, 'register_from_registry') as mock_reg:
            svc.start()
            svc.start()  # Second call
            # register_from_registry called only once
            mock_reg.assert_called_once()

        svc.stop()

    def test_stop_shuts_down_scheduler(self):
        """stop() should shut down the running scheduler."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        with patch.object(svc, 'register_from_registry'):
            svc.start()
        assert svc.scheduler.running is True

        svc.stop()
        assert svc.scheduler.running is False


class TestJobStatusReporting:
    """Test job status reporting methods."""

    def test_get_job_status_returns_all_jobs(self):
        """get_job_status should return info for all registered jobs."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        svc.register_job("status_test_1", lambda: None, "interval", "Test 1", minutes=5)
        svc.register_job("status_test_2", lambda: None, "cron", "Test 2", hour=3)

        status = svc.get_job_status()
        ids = [j["id"] for j in status]
        assert "status_test_1" in ids
        assert "status_test_2" in ids

    def test_get_job_status_includes_execution_history(self):
        """get_job_status should include execution log data when available."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        svc.register_job("hist_test", lambda: None, "interval", "Test", minutes=5)

        # Manually set execution log
        svc._execution_log["hist_test"] = {
            "last_start": "2026-05-14T10:00:00",
            "last_end": "2026-05-14T10:00:05",
            "last_duration_ms": 5000.0,
            "last_status": "success",
            "lock_acquired": True,
        }

        status = svc.get_job_status()
        hist_job = [j for j in status if j["id"] == "hist_test"][0]
        assert hist_job["last_status"] == "success"
        assert hist_job["last_duration_ms"] == 5000.0
        assert hist_job["lock_acquired"] is True

    def test_list_jobs_groups_by_domain(self):
        """list_jobs should include domain information from the registry."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        svc.register_from_registry()

        all_jobs = svc.list_jobs()
        domains = {j["domain"] for j in all_jobs}

        # Should have multiple domains from the registry
        assert "notification" in domains
        assert "workflow" in domains
        assert "cleanup" in domains

    def test_list_jobs_includes_external_jobs(self):
        """list_jobs should include jobs not in the registry (externally registered)."""
        from services.scheduler_service import SchedulerService

        svc = SchedulerService()
        svc.register_from_registry()

        # Register an external job directly on the APScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        svc.scheduler.add_job(
            lambda: None,
            trigger=IntervalTrigger(minutes=5),
            id="external_test_job",
            name="External Test",
            replace_existing=True,
        )

        all_jobs = svc.list_jobs()
        external = [j for j in all_jobs if j["name"] == "external_test_job"]
        assert len(external) == 1
        assert external[0]["domain"] == "external"


class TestAdvisoryLock:
    """Test PostgreSQL advisory lock mechanism."""

    def test_advisory_lock_succeeds_for_sqlite(self):
        """Advisory lock should return True for SQLite (development)."""
        from services.scheduler_service import _try_acquire_scheduler_lock

        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///test.db"}):
            assert _try_acquire_scheduler_lock() is True

    def test_advisory_lock_succeeds_when_no_db_url(self):
        """Advisory lock should return True when DATABASE_URL is empty."""
        from services.scheduler_service import _try_acquire_scheduler_lock

        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            assert _try_acquire_scheduler_lock() is True


class TestScheduledJobsRegistry:
    """Test the scheduled_jobs registry module."""

    def test_get_all_jobs_returns_jobs(self):
        """get_all_jobs should return a non-empty list of JobDefinitions."""
        from services.scheduled_jobs import get_all_jobs, JobDefinition

        jobs = get_all_jobs()
        assert len(jobs) > 0
        assert all(isinstance(j, JobDefinition) for j in jobs)

    def test_get_jobs_by_domain(self):
        """get_jobs_by_domain should filter by domain."""
        from services.scheduled_jobs import get_jobs_by_domain

        notification_jobs = get_jobs_by_domain("notification")
        assert len(notification_jobs) > 0
        assert all(j.domain == "notification" for j in notification_jobs)

    def test_all_jobs_have_required_fields(self):
        """All jobs should have name, func, trigger, domain, description."""
        from services.scheduled_jobs import get_all_jobs

        for job in get_all_jobs():
            assert job.name, f"Job missing name"
            assert callable(job.func), f"Job {job.name} func not callable"
            assert job.trigger in ("cron", "interval"), f"Job {job.name} invalid trigger: {job.trigger}"
            assert job.domain, f"Job {job.name} missing domain"
            assert job.description, f"Job {job.name} missing description"
            assert job.lock_ttl > 0, f"Job {job.name} invalid lock_ttl"

    def test_job_names_unique(self):
        """All job names should be unique."""
        from services.scheduled_jobs import get_all_jobs

        names = [j.name for j in get_all_jobs()]
        assert len(names) == len(set(names)), f"Duplicate job names: {[n for n in names if names.count(n) > 1]}"

    def test_register_external_job(self):
        """register_external_job should add a job to the registry."""
        from services.scheduled_jobs import register_external_job, get_all_jobs, JobDefinition

        initial_count = len(get_all_jobs())

        register_external_job(JobDefinition(
            name="test_external_registration",
            func=lambda: None,
            trigger="interval",
            trigger_kwargs={"minutes": 60},
            domain="test",
            description="Test external registration",
        ))

        assert len(get_all_jobs()) == initial_count + 1

    def test_register_external_job_no_duplicates(self):
        """register_external_job should skip duplicate names."""
        from services.scheduled_jobs import register_external_job, get_all_jobs, JobDefinition

        initial_count = len(get_all_jobs())

        job = JobDefinition(
            name="test_dedup_job",
            func=lambda: None,
            trigger="interval",
            trigger_kwargs={"minutes": 60},
            domain="test",
            description="Test dedup",
        )

        register_external_job(job)
        count_after_first = len(get_all_jobs())

        register_external_job(job)
        count_after_second = len(get_all_jobs())

        assert count_after_second == count_after_first
