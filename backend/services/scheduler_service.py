"""
Scheduler Service - Unified background job scheduler with distributed locking.

Uses APScheduler for job scheduling. Wraps every job execution with a Redis
distributed lock (via DistributedLockService) to prevent duplicate execution
across Railway replicas. Falls back to PostgreSQL advisory lock if Redis is
unavailable.

Key design:
  - Single BackgroundScheduler instance (singleton via scheduler_service)
  - Jobs registered from the centralized registry (services/scheduled_jobs.py)
  - Each job wrapped with distributed lock guard before execution
  - Job execution start/end logged with timing
  - get_job_status() exposes last run time, duration, lock holder info
"""

import os
import logging
import time
import functools
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

SCHEDULER_ADVISORY_LOCK_ID = 728372

_advisory_lock_conn = None


def _try_acquire_scheduler_lock() -> bool:
    """Attempt to acquire a PostgreSQL session-level advisory lock.

    Returns True if this process should run the scheduler, False if another
    replica already holds the lock.  The lock is held for the lifetime of the
    connection (session-level), so it is released automatically when the
    process exits.
    """
    global _advisory_lock_conn

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url or "sqlite" in database_url:
        return True

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    try:
        import psycopg2
        conn = psycopg2.connect(database_url, connect_timeout=10)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s)", (SCHEDULER_ADVISORY_LOCK_ID,))
        got_lock = cur.fetchone()[0]
        cur.close()

        if got_lock:
            _advisory_lock_conn = conn
            return True
        else:
            conn.close()
            return False
    except Exception as e:
        logger.warning("Failed to acquire scheduler advisory lock, starting scheduler anyway: %s", e)
        return True

# Reminder configuration (global defaults; orgs can override via scheduler_configs.notification_settings)
REMINDER_INTERVALS = {
    "first": 24,      # Hours after last activity
    "second": 72,     # 3 days
    "third": 168,     # 7 days
    "final": 336,     # 14 days
}

# Import notification service lazily to avoid circular imports
notification_service = None


def get_notification_service():
    """Get notification service instance."""
    global notification_service
    if notification_service is None:
        from services.notification_service import NotificationService
        notification_service = NotificationService()
    return notification_service


def get_db_session():
    """Get database session using shared engine from database.py.

    WARNING: Background scheduler tasks run outside the FastAPI request lifecycle,
    so RLS tenant context is NOT set from middleware. Queries in scheduler jobs
    MUST filter by organization_id explicitly. For tenant-scoped operations,
    use get_db_with_tenant(org_id) from db.py instead.
    """
    from database import SessionLocal
    return SessionLocal()


def _get_org_reminder_intervals(session, org_id) -> Dict[str, int]:
    """Get reminder intervals for an organization, falling back to global defaults.

    TENANT-011: Allows per-org configuration of reminder timing via the
    scheduler_configs.notification_settings JSON column. Orgs can set:
        {"reminder_intervals": {"first": 24, "second": 72, "third": 168, "final": 336}}
    Any missing keys fall back to the global REMINDER_INTERVALS defaults.
    """
    if not org_id:
        return REMINDER_INTERVALS.copy()

    try:
        row = session.execute(text("""
            SELECT notification_settings
            FROM scheduler_configs
            WHERE organization_id = :org_id
              AND user_id IS NULL
              AND is_active = true
            LIMIT 1
        """), {"org_id": org_id}).fetchone()

        if row and row[0]:
            settings = row[0] if isinstance(row[0], dict) else {}
            org_intervals = settings.get("reminder_intervals", {})
            if org_intervals and isinstance(org_intervals, dict):
                merged = REMINDER_INTERVALS.copy()
                for key in ("first", "second", "third", "final"):
                    val = org_intervals.get(key)
                    if isinstance(val, (int, float)) and val > 0:
                        merged[key] = int(val)
                return merged
    except Exception as e:
        logger.warning("Failed to load org %s reminder intervals, using defaults: %s", org_id, e)

    return REMINDER_INTERVALS.copy()


_reminders_table_checked = False


class SchedulerService:
    """Unified scheduler service with distributed locking for multi-replica safety.

    Wraps APScheduler's BackgroundScheduler and adds:
      - Distributed lock guard (Redis) around each job execution
      - Centralized job registration from services/scheduled_jobs.py
      - Job execution logging with timing
      - Status reporting with last run time, duration, lock info
    """

    def __init__(self):
        # Use in-memory job store only. All jobs are re-registered at startup
        # via register_from_registry(), so persistence adds no value. The
        # SQLAlchemy store was causing "missing 1 required positional argument:
        # self" failures: APScheduler pickles bound methods into the DB, but
        # after a deploy the unpickled callable loses its instance binding and
        # resolves to the unbound class method instead.
        _jobstores = {}

        self.scheduler = BackgroundScheduler(
            timezone="America/New_York",
            jobstores=_jobstores,
            executors={
                "default": {"type": "threadpool", "max_workers": 3},
            },
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 3600,
            }
        )
        self._jobs_registered = False
        # Track job execution history: {job_name: {last_start, last_end, last_duration_ms, last_status, lock_acquired}}
        self._execution_log: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _job_error_listener(event):
        """Structured alerting for background job failures (OBS-007).

        Logs at ERROR level with a structured prefix so log aggregators
        (DataDog, CloudWatch, etc.) can trigger alerts on the pattern.
        """
        logger.error(
            "BACKGROUND_JOB_FAILED: job=%s scheduled_run=%s exception=%s",
            event.job_id,
            getattr(event, 'scheduled_run_time', None),
            event.exception,
            exc_info=event.exception,
        )

    @staticmethod
    def _job_missed_listener(event):
        """Log when a job's execution was missed (misfire)."""
        logger.warning(
            "BACKGROUND_JOB_MISSED: job=%s scheduled_run=%s",
            event.job_id,
            getattr(event, 'scheduled_run_time', None),
        )

    def _wrap_with_lock(self, job_name: str, func, lock_ttl: int = 300):
        """Wrap a job function with distributed lock guard and execution logging.

        Before running the job, acquires a Redis lock keyed by
        ``scheduler:{job_name}``. If the lock cannot be acquired (another
        replica is running the same job), the execution is skipped silently.

        Falls back gracefully if Redis is unavailable — the PostgreSQL
        advisory lock (acquired at init_scheduler time) is the primary
        replica guard; this Redis lock is defense-in-depth for the case
        where advisory lock fails or is not available.

        Each execution is timed and logged at INFO level.
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            lock_key = f"scheduler:{job_name}"
            lock_acquired = False
            lock_svc = None

            try:
                from services.distributed_lock import get_lock_service
                lock_svc = get_lock_service()
            except Exception as e:
                logger.debug("Distributed lock service unavailable for job %s: %s", job_name, e)

            # Try to acquire lock via Redis
            if lock_svc is not None:
                redis = lock_svc._get_redis()
                if redis is not None:
                    import uuid
                    lock_value = str(uuid.uuid4())
                    try:
                        acquired = redis.set(lock_key, lock_value, nx=True, ex=lock_ttl)
                        if not acquired:
                            logger.debug(
                                "SCHEDULER_JOB_SKIPPED: job=%s reason=lock_held_by_other_replica",
                                job_name,
                            )
                            self._execution_log[job_name] = {
                                "last_start": datetime.now().isoformat(),
                                "last_end": datetime.now().isoformat(),
                                "last_duration_ms": 0,
                                "last_status": "skipped_lock",
                                "lock_acquired": False,
                            }
                            return
                        lock_acquired = True
                    except Exception as e:
                        logger.warning("Redis lock acquire failed for job %s, proceeding anyway: %s", job_name, e)

            # Execute the job with timing
            start_time = time.monotonic()
            start_dt = datetime.now()
            logger.info("SCHEDULER_JOB_START: job=%s", job_name)

            try:
                result = func(*args, **kwargs)
                duration_ms = round((time.monotonic() - start_time) * 1000, 1)
                logger.info(
                    "SCHEDULER_JOB_END: job=%s duration_ms=%.1f status=success",
                    job_name, duration_ms,
                )
                self._execution_log[job_name] = {
                    "last_start": start_dt.isoformat(),
                    "last_end": datetime.now().isoformat(),
                    "last_duration_ms": duration_ms,
                    "last_status": "success",
                    "lock_acquired": lock_acquired,
                }
                return result
            except Exception as e:
                duration_ms = round((time.monotonic() - start_time) * 1000, 1)
                logger.error(
                    "SCHEDULER_JOB_END: job=%s duration_ms=%.1f status=error error=%s",
                    job_name, duration_ms, e,
                )
                self._execution_log[job_name] = {
                    "last_start": start_dt.isoformat(),
                    "last_end": datetime.now().isoformat(),
                    "last_duration_ms": duration_ms,
                    "last_status": "error",
                    "last_error": str(e),
                    "lock_acquired": lock_acquired,
                }
                raise
            finally:
                # Release lock
                if lock_acquired and lock_svc is not None:
                    try:
                        redis = lock_svc._get_redis()
                        if redis is not None:
                            # Use the Lua script for safe release if available
                            lock_svc._release(lock_key, lock_value)
                    except Exception as e:
                        logger.warning("Failed to release lock for job %s: %s", job_name, e)

        return wrapper

    def register_job(self, name: str, func, trigger: str, description: str = "",
                     lock_ttl: int = 300, **trigger_kwargs):
        """Register a single job with the scheduler.

        Args:
            name: Unique job ID
            func: Callable to execute
            trigger: "cron" or "interval"
            description: Human-readable description
            lock_ttl: Max seconds to hold the distributed lock
            **trigger_kwargs: Passed to CronTrigger or IntervalTrigger
        """
        wrapped_func = self._wrap_with_lock(name, func, lock_ttl)

        if trigger == "cron":
            trigger_obj = CronTrigger(**trigger_kwargs)
        elif trigger == "interval":
            trigger_obj = IntervalTrigger(**trigger_kwargs)
        else:
            raise ValueError(f"Unknown trigger type: {trigger}")

        self.scheduler.add_job(
            func=wrapped_func,
            trigger=trigger_obj,
            id=name,
            name=description or name,
            replace_existing=True,
        )

    def register_from_registry(self):
        """Register all jobs from the centralized scheduled_jobs registry.

        Each job is wrapped with distributed lock guard before registration.
        """
        from services.scheduled_jobs import get_all_jobs

        jobs = get_all_jobs()
        for job_def in jobs:
            self.register_job(
                name=job_def.name,
                func=job_def.func,
                trigger=job_def.trigger,
                description=job_def.description,
                lock_ttl=job_def.lock_ttl,
                **job_def.trigger_kwargs,
            )

        logger.info("Registered %d jobs from centralized registry", len(jobs))

    def start(self):
        """Start the scheduler and register jobs from the centralized registry."""
        if not self._jobs_registered:
            self.register_from_registry()
            self._jobs_registered = True

        # OBS-007: Register error/missed listeners for structured alerting
        self.scheduler.add_listener(self._job_error_listener, EVENT_JOB_ERROR)
        self.scheduler.add_listener(self._job_missed_listener, EVENT_JOB_MISSED)

        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started with %d jobs", len(self.scheduler.get_jobs()))

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def send_application_reminders(self):
        """Send reminders for incomplete applications.

        TENANT-SAFE: Queries all orgs in one batch for efficiency, but processes
        per-application with try/except isolation so one org's failure doesn't
        affect others. Each successful reminder is committed independently.
        """
        logger.info("Running application reminder job")

        session = get_db_session()
        notifier = get_notification_service()

        try:
            # Find incomplete applications that need reminders
            # Ordered by organization_id first for cache-friendly processing
            query = text("""
                SELECT
                    ba.id,
                    ba.organization_id,
                    ba.borrower_email,
                    ba.borrower_first_name,
                    ba.borrower_phone,
                    ba.status,
                    ba.owner_id,
                    ba.updated_at,
                    COALESCE(rn.reminder_count, 0) AS reminder_count,
                    rn.last_reminder_at,
                    u.first_name as lo_first_name,
                    u.last_name as lo_last_name,
                    EXTRACT(EPOCH FROM (NOW() - COALESCE(rn.last_reminder_at, ba.updated_at))) / 3600 as hours_since_activity
                FROM borrower_applications ba
                LEFT JOIN users u ON u.id = ba.owner_id
                LEFT JOIN (
                    SELECT
                        application_id,
                        COUNT(*) AS reminder_count,
                        MAX(created_at) AS last_reminder_at
                    FROM application_notifications
                    WHERE notification_type = 'application_reminder'
                    GROUP BY application_id
                ) rn ON rn.application_id = ba.id
                WHERE ba.status IN ('draft', 'in_progress')
                AND ba.borrower_email IS NOT NULL
                AND (
                    (COALESCE(rn.reminder_count, 0) = 0 AND EXTRACT(EPOCH FROM (NOW() - ba.updated_at)) / 3600 >= :first_interval)
                    OR (COALESCE(rn.reminder_count, 0) = 1 AND EXTRACT(EPOCH FROM (NOW() - rn.last_reminder_at)) / 3600 >= :second_interval)
                    OR (COALESCE(rn.reminder_count, 0) = 2 AND EXTRACT(EPOCH FROM (NOW() - rn.last_reminder_at)) / 3600 >= :third_interval)
                    OR (COALESCE(rn.reminder_count, 0) = 3 AND EXTRACT(EPOCH FROM (NOW() - rn.last_reminder_at)) / 3600 >= :final_interval)
                )
                AND COALESCE(rn.reminder_count, 0) < 4
                AND ba.organization_id IS NOT NULL
                ORDER BY ba.organization_id, ba.updated_at ASC
                LIMIT 100
            """)

            result = session.execute(query, {
                "first_interval": REMINDER_INTERVALS["first"],
                "second_interval": REMINDER_INTERVALS["second"] - REMINDER_INTERVALS["first"],
                "third_interval": REMINDER_INTERVALS["third"] - REMINDER_INTERVALS["second"],
                "final_interval": REMINDER_INTERVALS["final"] - REMINDER_INTERVALS["third"],
            })

            applications = result.fetchall()
            sent_count = 0

            # TENANT-011: Cache per-org intervals to avoid repeated DB lookups
            _org_intervals_cache: Dict[Any, Dict[str, int]] = {}

            for app in applications:
                try:
                    app_dict = dict(app._mapping)
                    app_id = app_dict["id"]
                    app_org_id = app_dict.get("organization_id")
                    borrower_email = app_dict["borrower_email"]
                    borrower_name = app_dict["borrower_first_name"] or "there"
                    borrower_phone = app_dict.get("borrower_phone")
                    reminder_count = app_dict["reminder_count"] or 0
                    lo_name = f"{app_dict.get('lo_first_name', '')} {app_dict.get('lo_last_name', '')}".strip() or "Your Loan Officer"

                    # TENANT-011: Re-check against org-specific intervals before sending.
                    # The SQL query uses global defaults to cast a wide net; this check
                    # ensures we respect per-org overrides before actually sending.
                    if app_org_id not in _org_intervals_cache:
                        _org_intervals_cache[app_org_id] = _get_org_reminder_intervals(session, app_org_id)
                    org_intervals = _org_intervals_cache[app_org_id]

                    hours_since = float(app_dict.get("hours_since_activity") or 0)
                    interval_keys = ["first", "second", "third", "final"]
                    if reminder_count < len(interval_keys):
                        required_key = interval_keys[reminder_count]
                        # For the first reminder, compare against the first interval;
                        # for subsequent ones, compare against the delta from previous.
                        if reminder_count == 0:
                            required_hours = org_intervals[required_key]
                        else:
                            prev_key = interval_keys[reminder_count - 1]
                            required_hours = org_intervals[required_key] - org_intervals[prev_key]
                        if hours_since < required_hours:
                            # Not yet time per org-specific intervals; skip
                            continue

                    # Calculate progress (simplified)
                    progress = 25 if app_dict["status"] == "draft" else 50

                    # Generate resume link
                    resume_link = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/apply/resume/{app_id}"

                    # Send email reminder
                    email_result = notifier.send_application_reminder(
                        borrower_email=borrower_email,
                        borrower_name=borrower_name,
                        resume_link=resume_link,
                        progress_percent=progress,
                        lo_name=lo_name,
                    )

                    # Send SMS on second and subsequent reminders
                    if reminder_count >= 1 and borrower_phone:
                        # COMP-009: TCPA consent check before SMS
                        sms_allowed = True
                        try:
                            from services.scheduler_sms_sender import check_sms_consent
                            can_send, reason = check_sms_consent(borrower_phone)
                            if not can_send:
                                logger.info(
                                    "TCPA consent blocked SMS to ...%s for app %s: %s",
                                    borrower_phone[-4:] if borrower_phone else "unknown",
                                    app_id,
                                    reason,
                                )
                                sms_allowed = False
                        except ImportError:
                            logger.warning("TCPA consent check unavailable - blocking SMS as precaution for app %s", app_id)
                            sms_allowed = False
                        except Exception as e:
                            logger.error("TCPA consent check failed for app %s, blocking SMS: %s", app_id, e)
                            sms_allowed = False

                        if sms_allowed:
                            notifier.send_reminder_sms(
                                borrower_phone=borrower_phone,
                                borrower_name=borrower_name,
                                resume_link=resume_link,
                            )

                    # Record that we sent a reminder (reminder_count is derived
                    # from application_notifications; borrower_applications has no
                    # reminder_count / last_reminder_at columns).
                    update_query = text("""
                        INSERT INTO application_notifications
                            (application_id, notification_type, channel,
                             recipient_email, status, sent_at, created_at)
                        VALUES
                            (:app_id, 'application_reminder', 'email',
                             :borrower_email, 'sent', NOW(), NOW())
                    """)
                    session.execute(update_query, {"app_id": app_id, "borrower_email": borrower_email})
                    session.commit()

                    sent_count += 1
                    logger.info(f"Sent reminder #{reminder_count + 1} for application {app_id}")

                except Exception as e:
                    # TENANT-N10: Catch all exceptions per-application so one org's
                    # failure doesn't prevent reminders for other orgs
                    logger.error(f"Failed to send reminder for application {app_dict.get('id')}: {e}")
                    session.rollback()

            logger.info(f"Application reminder job complete: {sent_count} reminders sent")

        except SQLAlchemyError as e:
            logger.error(f"Application reminder job failed: {e}")
        finally:
            session.close()

    def check_document_expirations(self):
        """Check for expiring documents and notify.

        TENANT-012: Filters by organization_id IS NOT NULL to ensure only
        org-scoped documents are processed, and orders by org for
        cache-friendly processing.
        """
        logger.info("Running document expiration check")

        session = get_db_session()
        notifier = get_notification_service()

        try:
            # Find documents expiring in the next 7 days
            # TENANT-012: Added organization_id filter and ordering
            query = text("""
                SELECT
                    ad.id as doc_id,
                    ad.document_type,
                    ad.expires_at,
                    ba.id as application_id,
                    ba.organization_id,
                    ba.borrower_email,
                    ba.borrower_first_name,
                    ba.owner_id,
                    u.email as lo_email,
                    u.first_name as lo_first_name,
                    u.last_name as lo_last_name
                FROM application_documents ad
                JOIN borrower_applications ba ON ba.id = ad.application_id
                LEFT JOIN users u ON u.id = ba.owner_id
                WHERE ad.expires_at IS NOT NULL
                AND ad.expires_at BETWEEN NOW() AND NOW() + INTERVAL '7 days'
                AND ad.expiration_notified = false
                AND ba.status NOT IN ('submitted', 'funded', 'denied', 'withdrawn')
                AND ba.organization_id IS NOT NULL
                ORDER BY ba.organization_id, ad.expires_at ASC
                LIMIT 200
            """)

            result = session.execute(query)
            docs = result.fetchall()

            for doc in docs:
                try:
                    doc_dict = dict(doc._mapping)
                    expires_at = doc_dict["expires_at"]
                    now_for_expiry = datetime.now(timezone.utc) if getattr(expires_at, 'tzinfo', None) is not None else datetime.now()
                    days_until_expiry = (expires_at - now_for_expiry).days

                    # Notify borrower
                    upload_link = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/apply/documents/{doc_dict['application_id']}"

                    notifier.send_document_request(
                        borrower_email=doc_dict["borrower_email"],
                        borrower_name=doc_dict["borrower_first_name"] or "there",
                        documents_needed=[f"{doc_dict['document_type']} (expires in {days_until_expiry} days)"],
                        upload_link=upload_link,
                        lo_name=f"{doc_dict.get('lo_first_name', '')} {doc_dict.get('lo_last_name', '')}".strip(),
                    )

                    # Mark as notified
                    update_query = text("""
                        UPDATE application_documents
                        SET expiration_notified = true
                        WHERE id = :doc_id
                    """)
                    session.execute(update_query, {"doc_id": doc_dict["doc_id"]})
                    session.commit()

                    logger.info(f"Sent expiration notice for document {doc_dict['doc_id']}")

                except SQLAlchemyError as e:
                    logger.error(f"Failed to send expiration notice for document {doc_dict.get('doc_id')}: {e}")
                    session.rollback()

        except SQLAlchemyError as e:
            logger.error(f"Document expiration check failed: {e}")
        finally:
            session.close()

    def send_appointment_reminders(self):
        """Send reminders for upcoming appointments with cascading intervals (24h, 1h)."""
        logger.info("Running appointment reminder job")

        session = get_db_session()
        notifier = get_notification_service()

        try:
            # =====================================================================
            # PART 1: Legacy appointments table (single reminder)
            # =====================================================================
            # TENANT-013: The legacy `appointments` table predates multi-tenancy and
            # has no organization_id column. We filter via the joined leads table
            # (which has organization_id) to provide org-scoped isolation where
            # possible. Appointments with no linked lead are still included to
            # avoid silently dropping reminders, but logged for visibility.
            # This table will be deprecated once all data is migrated to
            # scheduler_appointments.
            # Check if legacy appointments table exists
            legacy_table_check = session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'appointments'
                )
            """))
            if not legacy_table_check.scalar():
                logger.debug("Legacy appointments table doesn't exist, skipping")
                appointments = []
            else:
                # Check if the legacy table has a lead_id column (schema varies)
                has_lead_id = session.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_name = 'appointments' AND column_name = 'lead_id'
                    )
                """)).scalar()

                if has_lead_id:
                    legacy_query = text("""
                        SELECT
                            a.id as appointment_id,
                            a.appointment_type,
                            a.scheduled_at,
                            a.meeting_link,
                            a.lead_id,
                            a.loan_id,
                            l.first_name as borrower_first_name,
                            l.email as borrower_email,
                            l.phone as borrower_phone,
                            l.organization_id as lead_org_id,
                            u.full_name as lo_name
                        FROM appointments a
                        LEFT JOIN leads l ON l.id = a.lead_id
                        LEFT JOIN users u ON u.id = a.assigned_to
                        WHERE a.scheduled_at BETWEEN NOW() AND NOW() + INTERVAL '24 hours'
                        AND a.reminder_sent = false
                        AND a.status = 'scheduled'
                        AND (l.organization_id IS NOT NULL OR a.lead_id IS NULL)
                    """)
                    result = session.execute(legacy_query)
                    appointments = result.fetchall()
                else:
                    logger.debug("Legacy appointments table missing lead_id column, skipping")
                    appointments = []

            for appt in appointments:
                try:
                    appt_dict = dict(appt._mapping)
                    lo_name = appt_dict.get('lo_name', '') or 'Your Loan Officer'

                    # TENANT-013: Log legacy appointments with no org context for visibility
                    if not appt_dict.get("lead_org_id") and appt_dict.get("lead_id"):
                        logger.warning(
                            "Legacy appointment %s has lead %s with no organization_id",
                            appt_dict.get("appointment_id"),
                            appt_dict.get("lead_id"),
                        )

                    # Send email reminder
                    if appt_dict.get("borrower_email"):
                        notifier.send_appointment_confirmation(
                            borrower_email=appt_dict["borrower_email"],
                            borrower_name=appt_dict.get("borrower_first_name", "there"),
                            appointment_type=f"Reminder: {appt_dict['appointment_type']}",
                            appointment_time=appt_dict["scheduled_at"],
                            lo_name=lo_name,
                            meeting_link=appt_dict.get("meeting_link"),
                        )

                    # Send SMS reminder
                    if appt_dict.get("borrower_phone"):
                        # COMP-009: TCPA consent check before SMS
                        sms_allowed = True
                        try:
                            from services.scheduler_sms_sender import check_sms_consent
                            phone_number = appt_dict["borrower_phone"]
                            can_send, reason = check_sms_consent(phone_number)
                            if not can_send:
                                logger.info(
                                    "TCPA consent blocked legacy SMS to ...%s for appointment %s: %s",
                                    phone_number[-4:] if phone_number else "unknown",
                                    appt_dict.get("appointment_id"),
                                    reason,
                                )
                                sms_allowed = False
                        except ImportError:
                            logger.warning("TCPA consent check unavailable - blocking SMS as precaution for appointment %s", appt_dict.get("appointment_id"))
                            sms_allowed = False
                        except Exception as e:
                            logger.error("TCPA consent check failed for appointment %s, blocking SMS: %s", appt_dict.get("appointment_id"), e)
                            sms_allowed = False

                        if sms_allowed:
                            notifier.send_appointment_reminder_sms(
                                borrower_phone=appt_dict["borrower_phone"],
                                borrower_name=appt_dict.get("borrower_first_name", "there"),
                                appointment_time=appt_dict["scheduled_at"],
                                lo_name=lo_name,
                                meeting_link=appt_dict.get("meeting_link"),
                            )

                    # Mark as reminded
                    update_query = text("""
                        UPDATE appointments
                        SET reminder_sent = true
                        WHERE id = :appt_id
                    """)
                    session.execute(update_query, {"appt_id": appt_dict["appointment_id"]})
                    session.commit()

                    logger.info(f"Sent legacy reminder for appointment {appt_dict['appointment_id']}")

                except SQLAlchemyError as e:
                    logger.error(f"Failed to send legacy reminder for appointment {appt_dict.get('appointment_id')}: {e}")
                    session.rollback()

            # =====================================================================
            # PART 2: Smart scheduler appointments (cascading reminders: 24h, 1h)
            # =====================================================================
            self._send_smart_scheduler_reminders(session, notifier)

            # =====================================================================
            # PART 3: Chat widget appointments (scheduled_appointments table)
            # =====================================================================
            self._send_chat_widget_reminders(session, notifier)

        except SQLAlchemyError as e:
            logger.error(f"Appointment reminder job failed: {e}")
        finally:
            session.close()

    def _send_smart_scheduler_reminders(self, session, notifier):
        """Send cascading reminders for smart scheduler appointments (24h and 1h before)."""
        try:
            # Check if scheduler_appointments table exists
            table_check = session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'scheduler_appointments'
                )
            """))
            if not table_check.scalar():
                logger.debug("scheduler_appointments table doesn't exist, skipping smart reminders")
                return

            # 24-hour reminders
            query_24h = text("""
                SELECT
                    sa.id as appointment_id,
                    sa.title,
                    sa.scheduled_start,
                    sa.video_link,
                    sa.attendee_name,
                    sa.attendee_email,
                    sa.attendee_phone,
                    u.full_name as lo_name
                FROM scheduler_appointments sa
                LEFT JOIN users u ON u.id = sa.assigned_user_id
                WHERE sa.scheduled_start BETWEEN NOW() + INTERVAL '23 hours' AND NOW() + INTERVAL '25 hours'
                AND UPPER(sa.status::text) = 'BOOKED'
                AND sa.organization_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM scheduler_reminders sr
                    WHERE sr.appointment_id = sa.id
                    AND sr.hours_before = 24
                    AND UPPER(sr.status::text) IN ('SENT', 'DELIVERED')
                )
                LIMIT 500
            """)

            result_24h = session.execute(query_24h)
            appointments_24h = result_24h.fetchall()

            for appt in appointments_24h:
                self._send_reminder_for_smart_appt(session, notifier, appt, 24)

            # 1-hour reminders
            query_1h = text("""
                SELECT
                    sa.id as appointment_id,
                    sa.title,
                    sa.scheduled_start,
                    sa.video_link,
                    sa.attendee_name,
                    sa.attendee_email,
                    sa.attendee_phone,
                    u.full_name as lo_name
                FROM scheduler_appointments sa
                LEFT JOIN users u ON u.id = sa.assigned_user_id
                WHERE sa.scheduled_start BETWEEN NOW() + INTERVAL '50 minutes' AND NOW() + INTERVAL '70 minutes'
                AND UPPER(sa.status::text) = 'BOOKED'
                AND sa.organization_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM scheduler_reminders sr
                    WHERE sr.appointment_id = sa.id
                    AND sr.hours_before = 1
                    AND UPPER(sr.status::text) IN ('SENT', 'DELIVERED')
                )
                LIMIT 500
            """)

            result_1h = session.execute(query_1h)
            appointments_1h = result_1h.fetchall()

            for appt in appointments_1h:
                self._send_reminder_for_smart_appt(session, notifier, appt, 1)

            logger.info(f"Processed {len(appointments_24h)} 24h reminders and {len(appointments_1h)} 1h reminders")

        except SQLAlchemyError as e:
            logger.error(f"Smart scheduler reminders failed: {e}")
            session.rollback()

    def _send_reminder_for_smart_appt(self, session, notifier, appt, hours_before: int):
        """Send reminder for a smart scheduler appointment and record it."""
        try:
            appt_dict = dict(appt._mapping)
            lo_name = appt_dict.get('lo_name', '') or 'Your Loan Officer'
            appointment_id = appt_dict["appointment_id"]

            # Determine reminder message based on hours
            if hours_before == 24:
                reminder_prefix = "Reminder: Tomorrow - "
            elif hours_before == 1:
                reminder_prefix = "Starting Soon: "
            else:
                reminder_prefix = "Reminder: "

            email_sent = False
            sms_sent = False

            # Send email reminder
            if appt_dict.get("attendee_email"):
                try:
                    email_result = notifier.send_appointment_confirmation(
                        borrower_email=appt_dict["attendee_email"],
                        borrower_name=appt_dict.get("attendee_name", "there"),
                        appointment_type=f"{reminder_prefix}{appt_dict.get('title', 'Appointment')}",
                        appointment_time=appt_dict["scheduled_start"],
                        lo_name=lo_name,
                        meeting_link=appt_dict.get("video_link"),
                    )
                    email_sent = email_result.get("success", False)
                    if email_sent:
                        logger.info(f"Email reminder sent for appointment {appointment_id}: {email_result}")
                    else:
                        logger.error(f"Email reminder failed for appointment {appointment_id}: {email_result}")
                except Exception as e:
                    logger.error(f"Failed to send email reminder for appointment {appointment_id}: {e}")

            # Send SMS reminder
            if appt_dict.get("attendee_phone"):
                # COMP-009: TCPA consent check before SMS
                sms_allowed = True
                phone_number = appt_dict["attendee_phone"]
                try:
                    from services.scheduler_sms_sender import check_sms_consent
                    can_send, reason = check_sms_consent(phone_number)
                    if not can_send:
                        logger.info(
                            "TCPA consent blocked SMS to ...%s for appointment %s: %s",
                            phone_number[-4:] if phone_number else "unknown",
                            appointment_id,
                            reason,
                        )
                        sms_allowed = False
                except ImportError:
                    logger.warning("TCPA consent check unavailable - blocking SMS as precaution for appointment %s", appointment_id)
                    sms_allowed = False
                except Exception as e:
                    logger.error("TCPA consent check failed for appointment %s, blocking SMS: %s", appointment_id, e)
                    sms_allowed = False

                if sms_allowed:
                    try:
                        sms_result = notifier.send_appointment_reminder_sms(
                            borrower_phone=appt_dict["attendee_phone"],
                            borrower_name=appt_dict.get("attendee_name", "there"),
                            appointment_time=appt_dict["scheduled_start"],
                            lo_name=lo_name,
                            meeting_link=appt_dict.get("video_link"),
                        )
                        sms_sent = sms_result.get("success", False)
                        if sms_sent:
                            logger.info(f"SMS reminder sent for appointment {appointment_id}: {sms_result}")
                        else:
                            logger.error(f"SMS reminder failed for appointment {appointment_id}: {sms_result}")
                    except Exception as e:
                        logger.error(f"Failed to send SMS reminder for appointment {appointment_id}: {e}")

            # Record the reminder in scheduler_reminders table
            if email_sent or sms_sent:
                # Check if scheduler_reminders table exists
                table_check = session.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'scheduler_reminders'
                    )
                """))
                if table_check.scalar():
                    if email_sent:
                        session.execute(text("""
                            INSERT INTO scheduler_reminders
                            (appointment_id, channel, scheduled_for, hours_before, status, sent_at, created_at, updated_at)
                            VALUES (:appt_id, 'EMAIL', NOW(), :hours_before, 'SENT', NOW(), NOW(), NOW())
                        """), {"appt_id": appointment_id, "hours_before": hours_before})

                    if sms_sent:
                        session.execute(text("""
                            INSERT INTO scheduler_reminders
                            (appointment_id, channel, scheduled_for, hours_before, status, sent_at, created_at, updated_at)
                            VALUES (:appt_id, 'SMS', NOW(), :hours_before, 'SENT', NOW(), NOW(), NOW())
                        """), {"appt_id": appointment_id, "hours_before": hours_before})

                session.commit()
                logger.info(f"Sent {hours_before}h reminder for smart appointment {appointment_id} (email={email_sent}, sms={sms_sent})")

        except SQLAlchemyError as e:
            logger.error(f"Failed to send reminder for smart appointment: {e}")
            session.rollback()

    def _send_chat_widget_reminders(self, session, notifier):
        """Send cascading reminders for chat widget appointments (scheduled_appointments table)."""
        try:
            # Check if scheduled_appointments table exists
            table_check = session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'scheduled_appointments'
                )
            """))
            if not table_check.scalar():
                logger.debug("scheduled_appointments table doesn't exist, skipping chat widget reminders")
                return

            # Ensure chat_appointment_reminders table exists (cached after first check)
            global _reminders_table_checked
            if not _reminders_table_checked:
                reminders_table_check = session.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'chat_appointment_reminders'
                    )
                """))
                if not reminders_table_check.scalar():
                    session.execute(text("""
                        CREATE TABLE IF NOT EXISTS chat_appointment_reminders (
                            id SERIAL PRIMARY KEY,
                            appointment_id VARCHAR(50) NOT NULL,
                            channel VARCHAR(20) NOT NULL,
                            hours_before INTEGER NOT NULL,
                            status VARCHAR(20) DEFAULT 'SENT',
                            sent_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    session.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_chat_appt_reminders_appt_id
                        ON chat_appointment_reminders(appointment_id)
                    """))
                    session.commit()
                    logger.info("Created chat_appointment_reminders table")
                _reminders_table_checked = True

            # 24-hour reminders for chat widget appointments
            query_24h = text("""
                SELECT
                    sa.id,
                    sa.appointment_id,
                    sa.appointment_type as title,
                    sa.start_time as scheduled_start,
                    sa.contact_name as attendee_name,
                    sa.contact_email as attendee_email,
                    sa.contact_phone as attendee_phone,
                    sa.lo_name
                FROM scheduled_appointments sa
                WHERE sa.start_time BETWEEN NOW() + INTERVAL '23 hours' AND NOW() + INTERVAL '25 hours'
                AND UPPER(sa.status) = 'SCHEDULED'
                AND NOT EXISTS (
                    SELECT 1 FROM chat_appointment_reminders cr
                    WHERE cr.appointment_id = sa.appointment_id
                    AND cr.hours_before = 24
                    AND UPPER(cr.status) IN ('SENT', 'DELIVERED')
                )
            """)

            result_24h = session.execute(query_24h)
            appointments_24h = result_24h.fetchall()

            for appt in appointments_24h:
                self._send_reminder_for_chat_appt(session, notifier, appt, 24)

            # 1-hour reminders for chat widget appointments
            query_1h = text("""
                SELECT
                    sa.id,
                    sa.appointment_id,
                    sa.appointment_type as title,
                    sa.start_time as scheduled_start,
                    sa.contact_name as attendee_name,
                    sa.contact_email as attendee_email,
                    sa.contact_phone as attendee_phone,
                    sa.lo_name
                FROM scheduled_appointments sa
                WHERE sa.start_time BETWEEN NOW() + INTERVAL '50 minutes' AND NOW() + INTERVAL '70 minutes'
                AND UPPER(sa.status) = 'SCHEDULED'
                AND NOT EXISTS (
                    SELECT 1 FROM chat_appointment_reminders cr
                    WHERE cr.appointment_id = sa.appointment_id
                    AND cr.hours_before = 1
                    AND UPPER(cr.status) IN ('SENT', 'DELIVERED')
                )
            """)

            result_1h = session.execute(query_1h)
            appointments_1h = result_1h.fetchall()

            for appt in appointments_1h:
                self._send_reminder_for_chat_appt(session, notifier, appt, 1)

            logger.info(f"Chat widget reminders: {len(appointments_24h)} 24h, {len(appointments_1h)} 1h")

        except SQLAlchemyError as e:
            logger.error(f"Chat widget reminders failed: {e}")
            session.rollback()

    def _send_reminder_for_chat_appt(self, session, notifier, appt, hours_before: int):
        """Send reminder for a chat widget appointment using ICS-capable email service."""
        try:
            appt_dict = dict(appt._mapping)
            lo_name = appt_dict.get('lo_name', '') or 'Your Loan Officer'
            appointment_id = appt_dict["appointment_id"]
            scheduled_start = appt_dict.get("scheduled_start")

            # Format date/time for the email template
            if scheduled_start:
                appointment_date = scheduled_start.strftime("%A, %B %d, %Y")
                appointment_time = scheduled_start.strftime("%I:%M %p")
            else:
                appointment_date = "Scheduled"
                appointment_time = "Scheduled"

            email_sent = False
            sms_sent = False

            # Send email reminder using the ICS-capable scheduler_email_service
            if appt_dict.get("attendee_email"):
                try:
                    from scheduler_email_service import send_appointment_reminder_email
                    email_result = send_appointment_reminder_email(
                        attendee_email=appt_dict["attendee_email"],
                        attendee_name=appt_dict.get("attendee_name", "there"),
                        appointment_title=appt_dict.get("title", "Consultation"),
                        appointment_date=appointment_date,
                        appointment_time=appointment_time,
                        duration_minutes=30,
                        hours_before=hours_before,
                        team_member_name=lo_name,
                        scheduled_start=scheduled_start,
                    )
                    email_sent = email_result.get("success", False)
                    if email_sent:
                        logger.info(f"Email reminder (with ICS) sent for chat appointment {appointment_id}")
                except ImportError:
                    # Fallback to simpler notification service if scheduler_email_service unavailable
                    email_result = notifier.send_appointment_confirmation(
                        borrower_email=appt_dict["attendee_email"],
                        borrower_name=appt_dict.get("attendee_name", "there"),
                        appointment_type=f"Reminder: Consultation with {lo_name}",
                        appointment_time=scheduled_start,
                        lo_name=lo_name,
                        meeting_link=None,
                    )
                    email_sent = email_result.get("success", False)
                except Exception as e:
                    logger.error(f"Failed to send email reminder for chat appointment {appointment_id}: {e}")

            # Send SMS reminder using the ICS-capable scheduler_email_service
            if appt_dict.get("attendee_phone"):
                # COMP-009: TCPA consent check before SMS
                sms_allowed = True
                phone_number = appt_dict["attendee_phone"]
                try:
                    from services.scheduler_sms_sender import check_sms_consent
                    can_send, reason = check_sms_consent(phone_number)
                    if not can_send:
                        logger.info(
                            "TCPA consent blocked SMS to ...%s for chat appointment %s: %s",
                            phone_number[-4:] if phone_number else "unknown",
                            appointment_id,
                            reason,
                        )
                        sms_allowed = False
                except ImportError:
                    logger.warning("TCPA consent check unavailable - blocking SMS as precaution for chat appointment %s", appointment_id)
                    sms_allowed = False
                except Exception as e:
                    logger.error("TCPA consent check failed for chat appointment %s, blocking SMS: %s", appointment_id, e)
                    sms_allowed = False

                if sms_allowed:
                    try:
                        from scheduler_email_service import send_appointment_reminder_sms as sched_reminder_sms
                        sms_result = sched_reminder_sms(
                            attendee_phone=appt_dict["attendee_phone"],
                            attendee_name=appt_dict.get("attendee_name", "there"),
                            appointment_date=appointment_date,
                            appointment_time=appointment_time,
                            hours_before=hours_before,
                            team_member_name=lo_name,
                        )
                        sms_sent = sms_result.get("success", False)
                        if sms_sent:
                            logger.info(f"SMS reminder sent for chat appointment {appointment_id}")
                    except ImportError:
                        sms_result = notifier.send_appointment_reminder_sms(
                            borrower_phone=appt_dict["attendee_phone"],
                            borrower_name=appt_dict.get("attendee_name", "there"),
                            appointment_time=scheduled_start,
                            lo_name=lo_name,
                            meeting_link=None,
                        )
                        sms_sent = sms_result.get("success", False)
                    except Exception as e:
                        logger.error(f"Failed to send SMS reminder for chat appointment {appointment_id}: {e}")

            # Record the reminder
            if email_sent or sms_sent:
                if email_sent:
                    session.execute(text("""
                        INSERT INTO chat_appointment_reminders
                        (appointment_id, channel, hours_before, status, sent_at, created_at)
                        VALUES (:appt_id, 'EMAIL', :hours_before, 'SENT', NOW(), NOW())
                    """), {"appt_id": appointment_id, "hours_before": hours_before})

                if sms_sent:
                    session.execute(text("""
                        INSERT INTO chat_appointment_reminders
                        (appointment_id, channel, hours_before, status, sent_at, created_at)
                        VALUES (:appt_id, 'SMS', :hours_before, 'SENT', NOW(), NOW())
                    """), {"appt_id": appointment_id, "hours_before": hours_before})

                session.commit()
                logger.info(f"Sent {hours_before}h reminder for chat appointment {appointment_id} (email={email_sent}, sms={sms_sent})")

        except SQLAlchemyError as e:
            logger.error(f"Failed to send reminder for chat appointment: {e}")
            session.rollback()

    def cleanup_stale_applications(self):
        """Archive applications that have been inactive for 90+ days."""
        logger.info("Running stale application cleanup")

        session = get_db_session()

        try:
            # Mark applications as abandoned after 90 days of inactivity
            query = text("""
                UPDATE borrower_applications
                SET status = 'abandoned',
                    updated_at = NOW()
                WHERE status IN ('draft', 'in_progress')
                AND updated_at < NOW() - INTERVAL '90 days'
                AND reminder_count >= 4
                RETURNING id
            """)

            result = session.execute(query)
            abandoned = result.fetchall()
            session.commit()

            logger.info(f"Marked {len(abandoned)} applications as abandoned")

        except SQLAlchemyError as e:
            logger.error(f"Stale application cleanup failed: {e}")
            session.rollback()
        finally:
            session.close()

    # =========================================================================
    # WORKFLOW SLA SYSTEM METHODS
    # =========================================================================

    def run_workflow_task_generation(self):
        """Generate tasks for active workflows."""
        logger.info("Running workflow task generation job")

        session = get_db_session()

        try:
            from services.workflow_scheduler import WorkflowScheduler

            scheduler = WorkflowScheduler(session)
            result = scheduler.generate_due_tasks()

            if result.get("success"):
                logger.info(f"Workflow task generation complete: {result}")
            else:
                logger.error(f"Workflow task generation failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Workflow task generation job failed: {e}")
        finally:
            session.close()

    def run_workflow_status_processing(self):
        """Process status changes and auto-enroll in workflows."""
        logger.info("Running workflow status processing job")

        session = get_db_session()

        try:
            from services.workflow_scheduler import WorkflowScheduler

            scheduler = WorkflowScheduler(session)
            result = scheduler.process_status_changes()

            if result.get("success"):
                enrolled = result.get("workflows_enrolled", 0)
                logger.info(f"Workflow status processing complete: {enrolled} workflows enrolled")
            else:
                logger.error(f"Workflow status processing failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Workflow status processing job failed: {e}")
        finally:
            session.close()

    def run_workflow_escalation(self):
        """Escalate overdue workflow tasks."""
        logger.info("Running workflow escalation job")

        session = get_db_session()

        try:
            from services.workflow_scheduler import WorkflowScheduler

            scheduler = WorkflowScheduler(session)
            result = scheduler.escalate_overdue_tasks()

            if result.get("success"):
                escalated = result.get("escalated_count", 0)
                logger.info(f"Workflow escalation complete: {escalated} tasks escalated")
            else:
                logger.error(f"Workflow escalation failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Workflow escalation job failed: {e}")
        finally:
            session.close()

    def run_workflow_completion_check(self):
        """Check for workflows that should be completed."""
        logger.info("Running workflow completion check job")

        session = get_db_session()

        try:
            from services.workflow_scheduler import WorkflowScheduler

            scheduler = WorkflowScheduler(session)
            result = scheduler.check_workflow_completions()

            if result.get("success"):
                completed = result.get("workflows_completed", 0)
                logger.info(f"Workflow completion check complete: {completed} workflows completed")
            else:
                logger.error(f"Workflow completion check failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Workflow completion check job failed: {e}")
        finally:
            session.close()

    def run_ai_autonomous_execution(self):
        """Run autonomous AI task execution for high-confidence tasks."""
        logger.info("Running AI autonomous execution job")

        session = get_db_session()

        try:
            from services.workflow_ai_executor import run_autonomous_ai_tasks

            result = run_autonomous_ai_tasks(session, max_tasks=20)

            if result.get("success"):
                executed = result.get("executed_count", 0)
                logger.info(f"AI autonomous execution complete: {executed} tasks executed")
            else:
                logger.error(f"AI autonomous execution failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"AI autonomous execution job failed: {e}")
        finally:
            session.close()

    # =========================================================================
    # LISTING AGENT PORTAL METHODS
    # =========================================================================

    def run_listing_weekly_updates(self):
        """Send weekly updates to listing agents for their active transactions."""
        logger.info("Running listing agent weekly updates job")

        session = get_db_session()

        try:
            from jobs.listing_weekly_update_job import run_weekly_updates

            result = run_weekly_updates(dry_run=False)

            logger.info(
                f"Listing weekly updates complete: "
                f"{result.get('emails_sent', 0)} emails sent, "
                f"{result.get('emails_failed', 0)} failed, "
                f"{result.get('parties_processed', 0)} parties processed"
            )

            if result.get("errors"):
                for error in result["errors"][:5]:
                    logger.warning(f"Listing update error: {error}")

        except Exception as e:
            logger.error(f"Listing weekly updates job failed: {e}")
        finally:
            session.close()

    # =========================================================================
    # AI PROSPECT RE-ENGAGEMENT METHODS
    # =========================================================================

    def run_prospect_reengagement_scan(self):
        """Scan for stale prospects and initiate AI re-engagement outreach."""
        logger.info("Running AI prospect re-engagement scan")
        try:
            from services.prospect_reengagement_service import run_prospect_reengagement_scan
            run_prospect_reengagement_scan()
        except Exception as e:
            logger.error(f"Prospect re-engagement scan job failed: {e}")

    def run_prospect_reengagement_expiry(self):
        """Expire stale AI re-engagement conversations with no response."""
        logger.info("Running AI prospect re-engagement expiry")
        try:
            from services.prospect_reengagement_service import run_prospect_reengagement_expiry
            run_prospect_reengagement_expiry()
        except Exception as e:
            logger.error(f"Prospect re-engagement expiry job failed: {e}")

    # =========================================================================
    # NO-SHOW RECOVERY METHODS
    # =========================================================================

    def run_no_show_recovery(self):
        """Detect no-show appointments and execute pending recovery steps.

        This job runs two phases:
        1. Detection: Mark overdue BOOKED/CONFIRMED/REMINDED appointments as NO_SHOW
           and start recovery step 1 (gentle SMS).
        2. Follow-up: For existing NO_SHOW appointments, execute the next due
           recovery step (understanding email, reschedule SMS, final email).

        The NoShowRecoveryService methods are async, so we bridge via
        a new event loop since BackgroundScheduler runs in a background thread
        (which has no running event loop).
        """
        import asyncio

        logger.info("Running no-show recovery job")
        session = get_db_session()

        # Create a dedicated event loop for this thread to avoid
        # "cannot be called from a running event loop" errors
        loop = asyncio.new_event_loop()

        try:
            # Phase 1: Detect new no-shows and start recovery
            detect_result = loop.run_until_complete(
                self._run_no_show_detection(session)
            )
            if detect_result.get("detected", 0) > 0:
                logger.info(
                    "No-show detection: %d new no-shows detected",
                    detect_result["detected"],
                )

            # Phase 2: Execute pending recovery steps for existing no-shows
            recovery_result = loop.run_until_complete(
                self._run_no_show_follow_up(session)
            )
            if recovery_result.get("steps_executed", 0) > 0:
                logger.info(
                    "No-show recovery: %d steps executed, %d skipped, %d errors",
                    recovery_result.get("steps_executed", 0),
                    recovery_result.get("skipped", 0),
                    recovery_result.get("errors", 0),
                )

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"No-show recovery job failed: {e}", exc_info=True)
        finally:
            loop.close()
            session.close()

    async def _run_no_show_detection(self, session) -> Dict:
        """Async helper: detect new no-shows per-org for tenant isolation."""
        from services.no_show_recovery import no_show_recovery_service
        from sqlalchemy import text as sa_text
        org_ids = [
            row[0] for row in
            session.execute(sa_text("SELECT DISTINCT organization_id FROM scheduler_appointments WHERE status IN ('booked','confirmed','reminded')")).fetchall()
        ]
        combined = {"detected": 0, "appointment_ids": []}
        for org_id in org_ids:
            result = await no_show_recovery_service.check_and_mark_no_shows(session, org_id)
            combined["detected"] += result.get("detected", 0)
            combined["appointment_ids"].extend(result.get("appointment_ids", []))
        return combined

    async def _run_no_show_follow_up(self, session) -> Dict:
        """Async helper: execute pending recovery steps per-org for tenant isolation."""
        from services.no_show_recovery import no_show_recovery_service
        from sqlalchemy import text as sa_text
        org_ids = [
            row[0] for row in
            session.execute(sa_text("SELECT DISTINCT organization_id FROM scheduler_appointments WHERE status = 'no_show'")).fetchall()
        ]
        combined = {"processed": 0, "steps_executed": 0, "skipped": 0, "errors": 0}
        for org_id in org_ids:
            result = await no_show_recovery_service.execute_no_show_recovery(session, org_id)
            for key in combined:
                combined[key] += result.get(key, 0)
        return combined

    # =========================================================================
    # SLOT HOLD CLEANUP METHODS
    # =========================================================================

    def cleanup_slot_holds(self):
        """Expire stale active holds and delete old expired/released records.

        Delegates to slot_hold_service.cleanup_expired_holds() which operates
        on the live `slot_holds` table (status column), then performs its own
        DELETE pass for records older than 1 hour.
        """
        import asyncio
        from database.models.scheduler import SlotHold, SlotHoldStatus
        import services.slot_hold_service as shs

        session = get_db_session()
        try:
            models = {'SlotHold': SlotHold}

            # Step 1: mark all expired-TTL holds as 'expired'.
            # asyncio.run() is safe here because APScheduler uses BackgroundScheduler
            # (thread pool), NOT AsyncIOScheduler — this job runs in a worker thread
            # outside the event loop, so there is no "loop already running" conflict.
            result = asyncio.run(shs.cleanup_expired_holds(session, models))
            expired_count = result.get('expired_count', 0)

            # Step 2: delete expired/released records older than 1 hour
            from datetime import datetime, timedelta, timezone
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            deleted_count = session.query(SlotHold).filter(
                SlotHold.status.in_([
                    SlotHoldStatus.EXPIRED.value,
                    SlotHoldStatus.RELEASED.value,
                ]),
                SlotHold.expires_at < cutoff,
            ).delete(synchronize_session=False)

            session.commit()

            if expired_count > 0 or deleted_count > 0:
                logger.info(
                    "Slot hold maintenance: expired %d, deleted %d",
                    expired_count, deleted_count,
                )

        except Exception as e:
            session.rollback()
            logger.error(f"Slot hold maintenance job failed: {e}")
        finally:
            session.close()

    # =========================================================================
    # AUDIT LOG RETENTION METHODS
    # =========================================================================

    def cleanup_audit_logs(self):
        """Purge audit log entries older than the configured retention period.

        Delegates to ``archive_old_audit_logs()`` in ``routes/scheduler/_audit.py``
        which deletes in batches of 1,000 to avoid long-running transactions.

        Default retention: configurable via AUDIT_RETENTION_DAYS env var (default 365).
        Compliance note: most mortgage regulations require 3-7 year retention.
        Set AUDIT_RETENTION_DAYS accordingly for your jurisdiction.
        """
        session = get_db_session()

        try:
            from routes.scheduler._audit import archive_old_audit_logs, AUDIT_RETENTION_DAYS

            logger.info("Running audit log retention cleanup (>%d days)", AUDIT_RETENTION_DAYS)
            result = archive_old_audit_logs(session, retention_days=AUDIT_RETENTION_DAYS)
            session.commit()

            if result["deleted_count"] > 0:
                logger.info(
                    "Audit log retention cleanup: %d entries purged, oldest remaining: %s",
                    result["deleted_count"],
                    result["oldest_remaining"],
                )

        except Exception as e:
            session.rollback()
            # Table may not exist yet — this is not a critical failure
            logger.warning("Audit log retention cleanup skipped: %s", e)
        finally:
            session.close()

    # =========================================================================
    # WEBHOOK AUTO-RETRY METHODS
    # =========================================================================

    def retry_dead_letter_webhooks(self):
        """Auto-retry dead-lettered webhook deliveries and apply circuit breaker.

        Phase 1: Retry failed deliveries that have been in the dead-letter queue
                 for >1 hour (to avoid retrying during transient outages).
        Phase 2: Circuit breaker — disable subscriptions with >10 consecutive
                 failures to preserve resources.
        """
        import asyncio

        logger.info("Running webhook dead-letter retry job")

        # Ensure webhook tables exist before querying them.
        # The migration (database/migrations/add_webhook_tables.py) may not have
        # run in all environments. Use checkfirst=True so this is a no-op when
        # the tables already exist.
        try:
            from database.models.webhook import WebhookDeliveryLog, WebhookSubscription, WebhookEventCatalog
            from database import engine as _engine
            WebhookSubscription.__table__.create(_engine, checkfirst=True)
            WebhookDeliveryLog.__table__.create(_engine, checkfirst=True)
            WebhookEventCatalog.__table__.create(_engine, checkfirst=True)
        except Exception as _table_err:
            logger.error(
                "Webhook dead-letter retry job aborted: could not ensure webhook tables exist: %s",
                _table_err,
            )
            return

        session = get_db_session()

        try:
            from database.models.webhook import WebhookDeliveryLog, WebhookSubscription
            from sqlalchemy import func

            cutoff = datetime.now() - timedelta(hours=1)
            max_auto_retries = 1  # Only auto-retry once; manual retry for further attempts

            # DATA-N02: Phase 1 — Find dead-lettered deliveries eligible for auto-retry.
            # Join to WebhookSubscription to ensure we only process deliveries belonging
            # to active subscriptions (with valid organization_id). This is a cross-org
            # batch job; deliveries are processed per-subscription which inherently
            # scopes to the subscription's organization.
            eligible = (
                session.query(WebhookDeliveryLog)
                .join(
                    WebhookSubscription,
                    WebhookDeliveryLog.subscription_id == WebhookSubscription.id,
                )
                .filter(
                    WebhookDeliveryLog.status == "failed",
                    WebhookDeliveryLog.dead_letter_at.isnot(None),
                    WebhookDeliveryLog.dead_letter_at < cutoff,
                    WebhookDeliveryLog.attempt_number <= 3,  # Original 3 attempts exhausted
                    WebhookSubscription.organization_id.isnot(None),
                )
                .order_by(WebhookSubscription.organization_id)
                .limit(50)
                .all()
            )

            retried = 0
            retry_succeeded = 0
            for delivery in eligible:
                subscription = (
                    session.query(WebhookSubscription)
                    .filter(WebhookSubscription.id == delivery.subscription_id)
                    .first()
                )
                if not subscription or not subscription.is_active:
                    continue

                try:
                    # Re-attempt delivery synchronously using httpx
                    import httpx

                    headers = {"Content-Type": "application/json"}
                    if subscription.secret:
                        import hashlib
                        import hmac
                        import json
                        payload_bytes = json.dumps(delivery.payload).encode()
                        signature = hmac.new(
                            subscription.secret.encode(),
                            payload_bytes,
                            hashlib.sha256,
                        ).hexdigest()
                        headers["X-Webhook-Signature"] = f"sha256={signature}"

                    with httpx.Client(timeout=10.0) as client:
                        resp = client.post(
                            subscription.url,
                            json=delivery.payload,
                            headers=headers,
                        )

                    delivery.attempt_number += 1
                    if 200 <= resp.status_code < 300:
                        delivery.status = "success"
                        delivery.response_code = resp.status_code
                        delivery.delivered_at = datetime.now()
                        delivery.dead_letter_at = None
                        retry_succeeded += 1
                    else:
                        delivery.response_code = resp.status_code
                        delivery.error_message = f"Auto-retry failed: HTTP {resp.status_code}"

                    retried += 1
                except Exception as e:
                    delivery.attempt_number += 1
                    delivery.error_message = f"Auto-retry error: {str(e)[:200]}"
                    retried += 1

            # Phase 2: Circuit breaker — disable subscriptions with >10 consecutive failures.
            # DATA-N03: This intentionally scans ALL organizations for circuit breaker
            # purposes. It is a system-level health check — an unhealthy subscription in
            # any org should be disabled to preserve delivery resources and prevent
            # cascading timeouts across the webhook delivery pipeline.
            unhealthy_subs = (
                session.query(WebhookSubscription.id)
                .filter(
                    WebhookSubscription.is_active == True,
                )
                .all()
            )

            disabled_count = 0
            for (sub_id,) in unhealthy_subs:
                recent = (
                    session.query(WebhookDeliveryLog.status)
                    .filter(WebhookDeliveryLog.subscription_id == sub_id)
                    .order_by(WebhookDeliveryLog.created_at.desc())
                    .limit(10)
                    .all()
                )
                if len(recent) >= 10 and all(r.status == "failed" for r in recent):
                    sub = session.query(WebhookSubscription).get(sub_id)
                    if sub:
                        sub.is_active = False
                        logger.warning(
                            "Circuit breaker: disabled webhook subscription %s (%s) "
                            "after 10 consecutive failures",
                            sub_id, sub.name,
                        )
                        disabled_count += 1

            session.commit()
            logger.info(
                "Webhook auto-retry complete: %d retried (%d succeeded), "
                "%d subscriptions disabled by circuit breaker",
                retried, retry_succeeded, disabled_count,
            )

        except Exception as e:
            session.rollback()
            logger.error(f"Webhook dead-letter retry job failed: {e}", exc_info=True)
        finally:
            session.close()

    def run_outbound_calendar_sync(self):
        """Retry failed/pending outbound calendar syncs.

        Finds CalendarEventMap rows with sync_status='failed' or 'pending'
        and re-runs the push to external calendar providers (Google, Outlook).
        """
        import asyncio
        logger.info("Running outbound calendar sync catchup")

        session = get_db_session()
        try:
            from services.calendar_outbound_sync import process_pending_syncs

            loop = asyncio.new_event_loop()
            try:
                stats = loop.run_until_complete(process_pending_syncs(session))
            finally:
                loop.close()

            if stats.get("retried", 0) > 0:
                logger.info(
                    "Outbound calendar sync catchup complete: %s", stats,
                )
        except Exception as e:
            session.rollback()
            logger.error(f"Outbound calendar sync catchup failed: {e}", exc_info=True)
        finally:
            session.close()


    # =========================================================================
    # CALENDAR FEED CLEANUP
    # =========================================================================

    def cleanup_expired_calendar_feeds(self):
        """Delete calendar feed tokens whose expires_at has passed.

        Idempotent: safe to run multiple times; only rows with a non-NULL
        expires_at in the past are removed.  NULL expires_at rows are legacy
        tokens treated as already-expired by the feed reader but left in place
        to avoid silently breaking existing subscribers until they regenerate.

        Registered in scheduled_jobs.py as 'calendar_feed_cleanup'.
        """
        logger.info("Running expired calendar feed token cleanup")

        session = get_db_session()
        try:
            result = session.execute(text("""
                DELETE FROM calendar_feed_tokens
                WHERE expires_at IS NOT NULL
                  AND expires_at < NOW()
                RETURNING id
            """))
            deleted_ids = result.fetchall()
            session.commit()

            count = len(deleted_ids)
            if count > 0:
                logger.info("Expired calendar feed cleanup: deleted %d tokens", count)
            else:
                logger.debug("Expired calendar feed cleanup: no expired tokens found")

        except Exception as e:
            session.rollback()
            logger.error("Expired calendar feed cleanup failed: %s", e, exc_info=True)
        finally:
            session.close()

    def get_job_status(self) -> List[Dict[str, Any]]:
        """Get status of all scheduled jobs with execution history."""
        jobs = []
        for job in self.scheduler.get_jobs():
            job_info = {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            # Merge execution history if available
            exec_info = self._execution_log.get(job.id)
            if exec_info:
                job_info["last_start"] = exec_info.get("last_start")
                job_info["last_end"] = exec_info.get("last_end")
                job_info["last_duration_ms"] = exec_info.get("last_duration_ms")
                job_info["last_status"] = exec_info.get("last_status")
                job_info["last_error"] = exec_info.get("last_error")
                job_info["lock_acquired"] = exec_info.get("lock_acquired")
            jobs.append(job_info)
        return jobs

    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all registered jobs grouped by domain.

        Returns registry entries enriched with runtime status from APScheduler.
        """
        try:
            from services.scheduled_jobs import get_all_jobs
            registry_jobs = get_all_jobs()
        except Exception:
            registry_jobs = []

        # Build lookup of APScheduler runtime info
        apscheduler_jobs = {job.id: job for job in self.scheduler.get_jobs()}

        result = []
        for job_def in registry_jobs:
            entry = {
                "name": job_def.name,
                "domain": job_def.domain,
                "description": job_def.description,
                "trigger": job_def.trigger,
                "trigger_kwargs": job_def.trigger_kwargs,
                "lock_ttl": job_def.lock_ttl,
            }
            # Runtime info from APScheduler
            ap_job = apscheduler_jobs.get(job_def.name)
            if ap_job:
                entry["next_run"] = ap_job.next_run_time.isoformat() if ap_job.next_run_time else None
                entry["registered"] = True
            else:
                entry["next_run"] = None
                entry["registered"] = False

            # Execution history
            exec_info = self._execution_log.get(job_def.name)
            if exec_info:
                entry["last_run"] = exec_info
            result.append(entry)

        # Include any APScheduler jobs NOT in the registry (externally registered)
        registry_names = {j.name for j in registry_jobs}
        for job_id, ap_job in apscheduler_jobs.items():
            if job_id not in registry_names:
                entry = {
                    "name": job_id,
                    "domain": "external",
                    "description": ap_job.name,
                    "trigger": str(ap_job.trigger),
                    "next_run": ap_job.next_run_time.isoformat() if ap_job.next_run_time else None,
                    "registered": True,
                }
                exec_info = self._execution_log.get(job_id)
                if exec_info:
                    entry["last_run"] = exec_info
                result.append(entry)

        return result


# Create singleton instance
scheduler_service = SchedulerService()


def init_scheduler():
    """Initialize and start the scheduler. Call this from main.py on startup.

    Uses a PostgreSQL advisory lock to ensure only one replica runs the
    scheduler when multiple replicas are deployed (e.g. numReplicas=2 on
    Railway).  If the lock cannot be acquired, the scheduler is skipped
    entirely on this replica.
    """
    if not _try_acquire_scheduler_lock():
        logger.warning(
            "Another replica holds the scheduler advisory lock (%s). "
            "Skipping scheduler startup on this replica.",
            SCHEDULER_ADVISORY_LOCK_ID,
        )
        return scheduler_service
    scheduler_service.start()
    return scheduler_service
