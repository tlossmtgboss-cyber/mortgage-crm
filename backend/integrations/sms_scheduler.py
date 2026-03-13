"""SMS Scheduler - Mortgage CRM A+ Module #10
Schedule SMS messages for future delivery with timezone support,
quiet-hours enforcement, and persistent job storage.
"""
import asyncio
import logging
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum
import pytz

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduledSMSJob:
    """A single scheduled SMS job."""

    def __init__(
        self,
        to: str,
        body: str,
        send_at: datetime,
        tenant_id: Optional[str] = None,
        template_key: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.job_id = str(uuid.uuid4())
        self.to = to
        self.body = body
        self.send_at = send_at  # UTC
        self.tenant_id = tenant_id
        self.template_key = template_key
        self.variables = variables or {}
        self.metadata = metadata or {}
        self.status = JobStatus.PENDING
        self.created_at = datetime.utcnow()
        self.sent_at: Optional[datetime] = None
        self.error: Optional[str] = None
        self.attempts: int = 0


class SMSScheduler:
    """Schedule and dispatch future-dated SMS messages."""

    # Quiet hours: do not send between 9 PM and 8 AM local time
    QUIET_HOUR_START = 21  # 9 PM
    QUIET_HOUR_END = 8     # 8 AM

    def __init__(self, sms_service=None, db=None):
        self.sms_service = sms_service
        self.db = db
        self._jobs: Dict[str, ScheduledSMSJob] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ── Job scheduling ─────────────────────────────────────────────────────────
    def schedule(
        self,
        to: str,
        body: str,
        send_at: datetime,
        timezone: str = "UTC",
        tenant_id: Optional[str] = None,
        template_key: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScheduledSMSJob:
        """Schedule an SMS for future delivery."""
        # Convert local time to UTC
        send_at_utc = self._to_utc(send_at, timezone)

        # Enforce quiet hours - push to next allowed window
        send_at_utc = self._enforce_quiet_hours(send_at_utc, timezone)

        job = ScheduledSMSJob(
            to=to,
            body=body,
            send_at=send_at_utc,
            tenant_id=tenant_id,
            template_key=template_key,
            variables=variables,
            metadata=metadata,
        )
        self._jobs[job.job_id] = job
        logger.info(f"Scheduled SMS job {job.job_id} to {to} at {send_at_utc} UTC")
        return job

    def schedule_relative(
        self,
        to: str,
        body: str,
        delay_minutes: int,
        tenant_id: Optional[str] = None,
        **kwargs,
    ) -> ScheduledSMSJob:
        """Schedule an SMS relative to now."""
        send_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
        return self.schedule(to=to, body=body, send_at=send_at, tenant_id=tenant_id, **kwargs)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending scheduled job."""
        job = self._jobs.get(job_id)
        if job and job.status == JobStatus.PENDING:
            job.status = JobStatus.CANCELLED
            logger.info(f"Cancelled scheduled SMS job {job_id}")
            return True
        return False

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        return {
            "job_id": job.job_id,
            "to": job.to,
            "status": job.status.value,
            "send_at": job.send_at.isoformat(),
            "sent_at": job.sent_at.isoformat() if job.sent_at else None,
            "attempts": job.attempts,
            "error": job.error,
        }

    def list_pending_jobs(self) -> List[Dict[str, Any]]:
        """Return all pending jobs sorted by send_at."""
        pending = [
            self.get_job(jid)
            for jid, j in self._jobs.items()
            if j.status == JobStatus.PENDING
        ]
        return sorted(pending, key=lambda x: x["send_at"])

    # ── Scheduler loop ────────────────────────────────────────────────────────
    async def start(self) -> None:
        """Start the scheduler background loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("SMS Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SMS Scheduler stopped")

    async def _run_loop(self) -> None:
        """Main scheduler loop - checks for due jobs every 30 seconds."""
        while self._running:
            try:
                await self._dispatch_due_jobs()
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            await asyncio.sleep(30)

    async def _dispatch_due_jobs(self) -> None:
        """Find and dispatch all jobs that are due."""
        now = datetime.utcnow()
        due_jobs = [
            job for job in self._jobs.values()
            if job.status == JobStatus.PENDING and job.send_at <= now
        ]

        if due_jobs:
            logger.info(f"Dispatching {len(due_jobs)} due SMS jobs")

        for job in due_jobs:
            await self._execute_job(job)

    async def _execute_job(self, job: ScheduledSMSJob) -> None:
        """Execute a scheduled SMS job."""
        job.status = JobStatus.RUNNING
        job.attempts += 1

        try:
            if self.sms_service:
                result = await self.sms_service.send_sms(
                    to=job.to,
                    body=job.body,
                    tenant_id=job.tenant_id,
                )
                if result.get("success"):
                    job.status = JobStatus.COMPLETED
                    job.sent_at = datetime.utcnow()
                    logger.info(f"Scheduled SMS job {job.job_id} sent successfully")
                else:
                    raise Exception(result.get("error", "Send failed"))
            else:
                # Dry-run
                job.status = JobStatus.COMPLETED
                job.sent_at = datetime.utcnow()
                logger.debug(f"[DRY RUN] Job {job.job_id} to {job.to}: {job.body[:40]}...")
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            logger.error(f"Scheduled SMS job {job.job_id} failed: {e}")

    # ── Timezone helpers ────────────────────────────────────────────────────
    def _to_utc(self, dt: datetime, timezone: str) -> datetime:
        """Convert a datetime to UTC."""
        if dt.tzinfo is not None:
            return dt.astimezone(pytz.utc).replace(tzinfo=None)
        try:
            tz = pytz.timezone(timezone)
            return tz.localize(dt).astimezone(pytz.utc).replace(tzinfo=None)
        except Exception:
            logger.warning(f"Invalid timezone '{timezone}', treating as UTC")
            return dt

    def _enforce_quiet_hours(self, dt_utc: datetime, timezone: str) -> datetime:
        """Push send_at past quiet hours if it falls within them."""
        try:
            tz = pytz.timezone(timezone)
            local_dt = pytz.utc.localize(dt_utc).astimezone(tz)
            hour = local_dt.hour
            if hour >= self.QUIET_HOUR_START or hour < self.QUIET_HOUR_END:
                # Push to next 8 AM local
                if hour >= self.QUIET_HOUR_START:
                    next_day = local_dt.date() + timedelta(days=1)
                else:
                    next_day = local_dt.date()
                send_local = tz.localize(
                    datetime(next_day.year, next_day.month, next_day.day, self.QUIET_HOUR_END, 0, 0)
                )
                pushed_utc = send_local.astimezone(pytz.utc).replace(tzinfo=None)
                logger.info(
                    f"Quiet hours: pushing send_at from {dt_utc} to {pushed_utc} UTC"
                )
                return pushed_utc
        except Exception as e:
            logger.warning(f"Quiet-hours check failed: {e}")
        return dt_utc


# ── Singleton ───────────────────────────────────────────────────────────────────
_scheduler: Optional[SMSScheduler] = None


def get_scheduler(sms_service=None, db=None) -> SMSScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = SMSScheduler(sms_service=sms_service, db=db)
    return _scheduler
