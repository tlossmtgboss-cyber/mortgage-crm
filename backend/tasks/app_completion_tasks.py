"""
Application Completion Orchestrator Tasks

Celery tasks for the Application Completion Orchestrator workflow:
- Trigger application review when a loan is submitted
- Process borrower SMS responses to missing-item requests
- Recalculate stale review scores (periodic)
- Send follow-up reminders for unanswered requests (periodic)

Usage:
    # Trigger review after application submission
    from tasks.app_completion_tasks import trigger_application_review_task
    trigger_application_review_task.delay(loan_id=loan_id)

    # Process inbound SMS
    from tasks.app_completion_tasks import process_borrower_sms_response_task
    process_borrower_sms_response_task.delay(
        from_number="+15551234567",
        to_number="+15559876543",
        message_body="I uploaded the paystubs",
        raw_payload={...},
    )
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# =============================================================================
# Event-Driven Tasks
# =============================================================================

@celery_app.task(
    name="tasks.app_completion_tasks.trigger_application_review_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def trigger_application_review_task(
    self,
    loan_id: int,
    triggered_by: str = "APPLICATION_SUBMITTED",
) -> Dict:
    """
    Trigger an Application Completion Orchestrator review for a loan.

    Called asynchronously when a loan application is submitted or when
    a manual review is requested. Analyzes the loan file for missing
    documents, incomplete fields, and compliance gaps.

    Uses tenant-scoped session via loan's organization_id for RLS.

    Args:
        loan_id: ID of the loan to review.
        triggered_by: Event that triggered the review (default APPLICATION_SUBMITTED).

    Returns:
        dict with review_id, score, and missing item count.
    """
    from db import SessionLocal
    from database import get_db_with_tenant
    from sqlalchemy import text as sa_text
    from services.smart_docs.app_completion_orchestrator import trigger_application_review

    logger.info(
        "Starting application review for loan_id=%s triggered_by=%s",
        loan_id, triggered_by,
    )
    start_time = datetime.now(timezone.utc)

    # Look up org_id from the loan
    lookup_db = SessionLocal()
    try:
        row = lookup_db.execute(sa_text(
            "SELECT organization_id FROM loans WHERE id = :lid"
        ), {"lid": loan_id}).fetchone()
        org_id = row[0] if row else None
    finally:
        lookup_db.close()

    if not org_id:
        logger.warning("Loan %d not found or has no org_id", loan_id)
        return {"error": "loan_not_found"}

    try:
        with get_db_with_tenant(org_id) as session:
            result = trigger_application_review(
                db=session,
                loan_id=loan_id,
                triggered_by=triggered_by,
            )
            session.commit()

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(
                "Application review complete for loan_id=%s in %.1fs: "
                "review_id=%s score=%s missing_items=%s",
                loan_id, elapsed,
                result.get("review_id"),
                result.get("score"),
                result.get("missing_item_count", 0),
            )
            return result

    except Exception as e:
        logger.exception(
            "Application review failed for loan_id=%s: %s", loan_id, e,
        )
        raise self.retry(exc=e)


@celery_app.task(
    name="tasks.app_completion_tasks.process_borrower_sms_response_task",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    acks_late=True,
)
def process_borrower_sms_response_task(
    self,
    from_number: str,
    to_number: str,
    message_body: str,
    raw_payload: Optional[Dict] = None,
) -> Dict:
    """
    Process an inbound SMS response from a borrower regarding missing items.

    Matches the phone number to a borrower, finds their active review,
    and updates the relevant missing item status based on the message content.

    Args:
        from_number: Borrower's phone number.
        to_number: System phone number the message was sent to.
        message_body: Text content of the SMS.
        raw_payload: Full webhook payload for audit logging.

    Returns:
        dict with processing result (matched_loan_id, items_updated, etc).
    """
    from db import SessionLocal
    from services.smart_docs.app_completion_orchestrator import AppCompletionOrchestrator

    logger.info(
        "Processing borrower SMS response from=%s body_len=%d",
        from_number, len(message_body or ""),
    )

    session = SessionLocal()
    try:
        orchestrator = AppCompletionOrchestrator(db=session)
        result = orchestrator.handle_borrower_response(
            from_number=from_number,
            to_number=to_number,
            message_body=message_body,
            raw_payload=raw_payload or {},
        )
        session.commit()

        logger.info(
            "Borrower SMS processed from=%s: matched_loan=%s items_updated=%s",
            from_number,
            result.get("matched_loan_id"),
            result.get("items_updated", 0),
        )
        return result

    except Exception as e:
        session.rollback()
        logger.exception(
            "Failed to process borrower SMS from=%s: %s", from_number, e,
        )
        raise self.retry(exc=e)
    finally:
        session.close()


# =============================================================================
# Periodic / Cron Tasks
# =============================================================================

@celery_app.task(
    name="tasks.app_completion_tasks.recalculate_stale_reviews_task",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def recalculate_stale_reviews_task(self, stale_hours: int = 24) -> Dict:
    """
    Recalculate completion scores for reviews older than the given threshold,
    per organization.

    Documents may have been uploaded or fields updated since the last review.
    This task finds stale reviews and refreshes their scores so the dashboard
    always reflects current state.

    Uses tenant-scoped sessions per-org to enforce RLS.

    Args:
        stale_hours: Reviews older than this many hours are recalculated.

    Returns:
        dict with total_found, refreshed, failed counts.
    """
    from db import SessionLocal
    from database import get_db_with_tenant
    from sqlalchemy import text as sa_text
    from services.smart_docs.app_completion_orchestrator import AppCompletionOrchestrator

    logger.info("Recalculating stale reviews (threshold=%dh)", stale_hours)
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

    total_found = 0
    refreshed = 0
    failed = 0

    cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_hours)

    for org_id in org_ids:
        try:
            with get_db_with_tenant(org_id) as session:
                # Find active reviews for this org that haven't been recalculated
                stale_reviews = session.execute(sa_text("""
                    SELECT acr.id, acr.loan_id
                    FROM app_completion_reviews acr
                    JOIN loans l ON l.id = acr.loan_id
                    WHERE l.organization_id = :org_id
                      AND acr.status = 'ACTIVE'
                      AND acr.updated_at < :cutoff
                    ORDER BY acr.updated_at ASC
                    LIMIT 200
                """), {"org_id": org_id, "cutoff": cutoff}).fetchall()

                total_found += len(stale_reviews)

                if not stale_reviews:
                    continue

                orchestrator = AppCompletionOrchestrator(db=session)

                for review in stale_reviews:
                    try:
                        orchestrator.recalculate_score(review_id=review.id)
                        refreshed += 1
                    except Exception as e:
                        failed += 1
                        logger.warning(
                            "Failed to recalculate review %s (loan_id=%s): %s",
                            review.id, review.loan_id, e,
                        )

                session.commit()
        except Exception as e:
            logger.exception("Stale review recalculation failed for org_id=%d: %s", org_id, e)

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        "Stale review recalculation complete in %.1fs: "
        "found=%d refreshed=%d failed=%d",
        elapsed, total_found, refreshed, failed,
    )
    return {
        "total_found": total_found,
        "refreshed": refreshed,
        "failed": failed,
    }


@celery_app.task(
    name="tasks.app_completion_tasks.send_pending_reminders_task",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def send_pending_reminders_task(self, reminder_delay_hours: int = 24) -> Dict:
    """
    Send follow-up reminders for missing items that were sent to the borrower
    but received no response within the configured delay, per organization.

    Only sends one reminder per missing item to avoid spamming.
    Uses tenant-scoped sessions per-org to enforce RLS.

    Args:
        reminder_delay_hours: Hours to wait before sending a reminder.

    Returns:
        dict with candidates_found, reminders_sent, failed counts.
    """
    from db import SessionLocal
    from database import get_db_with_tenant
    from sqlalchemy import text as sa_text
    from services.smart_docs.app_completion_orchestrator import AppCompletionOrchestrator

    logger.info(
        "Sending pending reminders (delay=%dh)", reminder_delay_hours,
    )
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

    cutoff = datetime.now(timezone.utc) - timedelta(hours=reminder_delay_hours)
    candidates_found = 0
    reminders_sent = 0
    failed = 0

    for org_id in org_ids:
        try:
            with get_db_with_tenant(org_id) as session:
                # Find missing items for this org
                candidates = session.execute(sa_text("""
                    SELECT mi.id, mi.review_id, mi.item_type, mi.description,
                           acr.loan_id
                    FROM app_completion_missing_items mi
                    JOIN app_completion_reviews acr ON acr.id = mi.review_id
                    JOIN loans l ON l.id = acr.loan_id
                    WHERE l.organization_id = :org_id
                      AND mi.status = 'SENT_TO_BORROWER'
                      AND mi.reminder_sent_at IS NULL
                      AND mi.sent_at IS NOT NULL
                      AND mi.sent_at < :cutoff
                      AND acr.status = 'ACTIVE'
                    ORDER BY mi.sent_at ASC
                    LIMIT 100
                """), {"org_id": org_id, "cutoff": cutoff}).fetchall()

                candidates_found += len(candidates)

                if not candidates:
                    continue

                orchestrator = AppCompletionOrchestrator(db=session)

                for item in candidates:
                    try:
                        orchestrator.send_item_reminder(
                            missing_item_id=item.id,
                            loan_id=item.loan_id,
                        )
                        reminders_sent += 1
                    except Exception as e:
                        failed += 1
                        logger.warning(
                            "Failed to send reminder for item %s (loan_id=%s): %s",
                            item.id, item.loan_id, e,
                        )

                session.commit()
        except Exception as e:
            logger.exception("Pending reminders failed for org_id=%d: %s", org_id, e)

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        "Pending reminders complete in %.1fs: "
        "found=%d sent=%d failed=%d",
        elapsed, candidates_found, reminders_sent, failed,
    )
    return {
        "candidates_found": candidates_found,
        "reminders_sent": reminders_sent,
        "failed": failed,
    }
