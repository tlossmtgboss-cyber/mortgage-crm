"""
Scheduled task: Expire stale voice scheduling workflows.

Runs every 15 minutes via Celery Beat (configured in celery_app.py beat_schedule).
Can also be run standalone via cron:
    */15 * * * * cd /app && python -m tasks.expire_voice_workflows

Expires workflows that have been in an active state past their expires_at timestamp.
Uses VoiceSchedulingWorkflowService.expire_stale_workflows() which transitions
stale workflows to the EXPIRED state.

Note: main.py also has an APScheduler instance (AsyncIOScheduler) used for
auto-sync jobs. This task uses Celery Beat instead, consistent with the other
periodic background tasks in the tasks/ package.
"""

import logging
from datetime import datetime, timezone

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.expire_voice_workflows.expire_stale_voice_workflows",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def expire_stale_voice_workflows(self):
    """
    Expire voice workflows past their expires_at timestamp.

    Queries for VoiceWorkflow rows that are still in an active state
    (not COMPLETED, EXPIRED, CANCELLED, or FAILED) but whose expires_at
    is in the past. Transitions them to EXPIRED.

    Returns:
        dict with expired_count and run metadata.
    """
    from db import SessionLocal
    from services.voice_scheduling_workflow_service import VoiceSchedulingWorkflowService

    logger.info("Starting voice workflow expiry check")
    start_time = datetime.now(timezone.utc)

    session = SessionLocal()
    try:
        service = VoiceSchedulingWorkflowService(session)
        expired_count = service.expire_stale_workflows()
        session.commit()

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            f"Voice workflow expiry complete in {elapsed:.1f}s: "
            f"{expired_count} workflows expired"
        )
        return {
            "expired_count": expired_count,
            "elapsed_seconds": round(elapsed, 2),
            "run_at": start_time.isoformat(),
        }

    except Exception as e:
        session.rollback()
        logger.exception(f"Voice workflow expiry failed: {e}")
        raise self.retry(exc=e)
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = expire_stale_voice_workflows()
    print(f"Expired {result['expired_count']} stale voice workflows")
