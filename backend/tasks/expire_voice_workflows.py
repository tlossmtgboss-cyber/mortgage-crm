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
    Expire voice workflows past their expires_at timestamp, per organization.

    Queries for VoiceWorkflow rows that are still in an active state
    (not COMPLETED, EXPIRED, CANCELLED, or FAILED) but whose expires_at
    is in the past. Transitions them to EXPIRED.

    Uses tenant-scoped sessions per-org to enforce RLS.

    Returns:
        dict with expired_count and run metadata.
    """
    from db import SessionLocal
    from database import get_db_with_tenant
    from sqlalchemy import text as sa_text
    from services.voice_scheduling_workflow_service import VoiceSchedulingWorkflowService

    logger.info("Starting voice workflow expiry check")
    start_time = datetime.now(timezone.utc)

    # Get org list with un-scoped session
    lookup_db = SessionLocal()
    try:
        org_ids = [
            row[0] for row in
            lookup_db.execute(sa_text(
                "SELECT id FROM organizations WHERE is_active = true ORDER BY id"
            )).fetchall()
        ]
    finally:
        lookup_db.close()

    total_expired = 0
    org_errors = 0

    for org_id in org_ids:
        try:
            with get_db_with_tenant(org_id) as session:
                service = VoiceSchedulingWorkflowService(session)
                expired_count = service.expire_stale_workflows()
                session.commit()
                total_expired += expired_count
                if expired_count > 0:
                    logger.info(
                        "Voice workflow expiry org_id=%d: %d expired",
                        org_id, expired_count,
                    )
        except Exception as e:
            org_errors += 1
            logger.exception(f"Voice workflow expiry failed for org_id={org_id}: {e}")

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        f"Voice workflow expiry complete in {elapsed:.1f}s: "
        f"{total_expired} workflows expired across {len(org_ids)} orgs"
    )
    return {
        "expired_count": total_expired,
        "elapsed_seconds": round(elapsed, 2),
        "run_at": start_time.isoformat(),
        "org_errors": org_errors,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = expire_stale_voice_workflows()
    print(f"Expired {result['expired_count']} stale voice workflows")
