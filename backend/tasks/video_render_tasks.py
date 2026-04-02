"""
Video Render Tasks

Celery tasks for processing video render jobs.
These tasks integrate with the video render worker to handle
asynchronous video rendering in the background.
"""

import os
import logging
from typing import Optional

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="tasks.video_render_tasks.process_render_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=600,  # 10 minute hard limit
    soft_time_limit=540,  # 9 minute soft limit
)
def process_render_job(self, job_id: int):
    """
    Process a single video render job.

    This task is triggered when a new render job is created and handles
    the full render pipeline: script -> voiceover -> visuals -> composition.

    Uses tenant-scoped session if the job has an organization_id.

    Args:
        job_id: The database ID of the render job to process
    """
    from database import SessionLocal, get_db_with_tenant
    from services.video_render_service import video_render_service, RenderState
    from jobs.video_render_worker import VideoRenderWorker
    from sqlalchemy import text as sa_text

    logger.info(f"Processing render job {job_id}")

    # Look up org_id from the render job
    lookup_db = SessionLocal()
    try:
        row = lookup_db.execute(sa_text(
            "SELECT organization_id FROM video_render_jobs WHERE id = :jid"
        ), {"jid": job_id}).fetchone()
        org_id = row[0] if row else None
    except Exception:
        org_id = None
    finally:
        lookup_db.close()

    # Use tenant-scoped session if org_id is available
    if org_id:
        from contextlib import contextmanager
        ctx = get_db_with_tenant(org_id)
    else:
        from contextlib import contextmanager
        @contextmanager
        def _fallback():
            _db = SessionLocal()
            try:
                yield _db
            finally:
                _db.close()
        ctx = _fallback()

    try:
        with ctx as db:
            # Get the job
            job = video_render_service.get_render_job(db, job_id)
            if not job:
                logger.error(f"Render job {job_id} not found")
                return {"status": "error", "message": "Job not found"}

            # Check if job is already being processed or completed
            if job["state"] in ["rendered", "published"]:
                logger.info(f"Job {job_id} already completed with state {job['state']}")
                return {"status": "skipped", "message": f"Job already {job['state']}"}

            if job["state"] == "failed" and job.get("retry_count", 0) >= job.get("max_retries", 3):
                logger.warning(f"Job {job_id} has exceeded max retries")
                return {"status": "skipped", "message": "Max retries exceeded"}

            # Create a worker instance and process
            worker = VideoRenderWorker(SessionLocal)
            worker._process_job(db, job)

            logger.info(f"Render job {job_id} completed successfully")
            return {"status": "success", "job_id": job_id}

    except Exception as e:
        logger.exception(f"Error processing render job {job_id}")

        # Mark job as failed using a fresh session
        try:
            fail_db = SessionLocal()
            try:
                job = video_render_service.get_render_job(fail_db, job_id)
                if job:
                    video_render_service.fail_job(
                        fail_db, job["job_id"], str(e), {"celery_task_id": self.request.id}
                    )
            finally:
                fail_db.close()
        except Exception as fail_error:
            logger.error(f"Failed to mark job as failed: {fail_error}")

        # Retry if we haven't exceeded max retries
        raise self.retry(exc=e)


@shared_task(
    name="tasks.video_render_tasks.queue_pending_jobs",
    bind=True,
    time_limit=120,  # 2 minute limit
)
def queue_pending_jobs(self, limit: int = 10):
    """
    Check for pending render jobs and queue them for processing.

    This is a periodic task that runs every 2 minutes to find
    jobs that haven't been picked up yet and dispatch them.

    Args:
        limit: Maximum number of jobs to queue per run
    """
    from database import SessionLocal
    from services.video_render_service import video_render_service

    logger.info("Checking for pending video render jobs...")

    db = None
    queued_count = 0

    try:
        db = SessionLocal()

        # Get pending jobs that haven't been assigned to a worker
        pending_jobs = video_render_service.get_pending_jobs(db, limit=limit)

        for job in pending_jobs:
            # Skip jobs already being processed
            if job.get("worker_id"):
                continue

            # Skip failed jobs that have exceeded retries
            if job["state"] == "failed":
                if job.get("retry_count", 0) >= job.get("max_retries", 3):
                    continue

            # Queue the job for processing
            process_render_job.delay(job["id"])
            queued_count += 1
            logger.info(f"Queued render job {job['id']} (job_id: {job['job_id']})")

        logger.info(f"Queued {queued_count} video render jobs")
        return {"status": "success", "queued_count": queued_count}

    except Exception as e:
        logger.exception("Error queuing pending jobs")
        return {"status": "error", "message": "Internal server error"}

    finally:
        if db:
            db.close()


@shared_task(
    name="tasks.video_render_tasks.retry_failed_jobs",
    bind=True,
    time_limit=60,
)
def retry_failed_jobs(self, hours: int = 24, limit: int = 20):
    """
    Retry failed render jobs that haven't exceeded max retries.

    Args:
        hours: Only retry jobs that failed within this many hours
        limit: Maximum number of jobs to retry
    """
    from database import SessionLocal
    from services.video_render_service import video_render_service
    from sqlalchemy import text

    logger.info(f"Checking for failed render jobs to retry (last {hours} hours)...")

    db = None
    retried_count = 0

    try:
        db = SessionLocal()

        # Find failed jobs that can be retried
        failed_jobs = db.execute(text("""
            SELECT id, job_id, retry_count, max_retries
            FROM video_render_jobs
            WHERE state = 'failed'
                AND retry_count < max_retries
                AND updated_at >= CURRENT_TIMESTAMP - INTERVAL ':hours hours'
            ORDER BY updated_at ASC
            LIMIT :limit
        """), {"hours": hours, "limit": limit}).fetchall()

        for job in failed_jobs:
            job_id = job[0]
            string_job_id = job[1]

            # Reset job state to created for retry
            success, message = video_render_service.retry_failed_job(db, job_id)

            if success:
                # Queue for processing
                process_render_job.delay(job_id)
                retried_count += 1
                logger.info(f"Retrying render job {string_job_id}")
            else:
                logger.warning(f"Could not retry job {string_job_id}: {message}")

        logger.info(f"Retried {retried_count} failed render jobs")
        return {"status": "success", "retried_count": retried_count}

    except Exception as e:
        logger.exception("Error retrying failed jobs")
        return {"status": "error", "message": "Internal server error"}

    finally:
        if db:
            db.close()


@shared_task(
    name="tasks.video_render_tasks.cleanup_old_artifacts",
    bind=True,
    time_limit=300,
)
def cleanup_old_artifacts(self, days: int = 30):
    """
    Clean up old render artifacts and temporary files.

    Args:
        days: Delete artifacts older than this many days
    """
    import shutil
    from pathlib import Path
    from datetime import datetime, timedelta, timezone
    from database import SessionLocal
    from sqlalchemy import text

    logger.info(f"Cleaning up render artifacts older than {days} days...")

    db = None
    cleaned_count = 0

    try:
        db = SessionLocal()

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Find old completed jobs
        old_jobs = db.execute(text("""
            SELECT job_id FROM video_render_jobs
            WHERE state IN ('rendered', 'published', 'failed')
                AND completed_at IS NOT NULL
                AND completed_at < :cutoff
        """), {"cutoff": cutoff_date}).fetchall()

        temp_dir = Path(os.getenv("VIDEO_TEMP_DIR", "/tmp/video_render"))

        for job in old_jobs:
            job_id = job[0]
            job_dir = temp_dir / job_id

            if job_dir.exists():
                try:
                    shutil.rmtree(job_dir)
                    cleaned_count += 1
                    logger.debug(f"Cleaned up temp files for job {job_id}")
                except Exception as e:
                    logger.warning(f"Failed to clean up {job_id}: {e}")

        logger.info(f"Cleaned up {cleaned_count} old render job directories")
        return {"status": "success", "cleaned_count": cleaned_count}

    except Exception as e:
        logger.exception("Error cleaning up artifacts")
        return {"status": "error", "message": "Internal server error"}

    finally:
        if db:
            db.close()
