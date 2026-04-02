"""
Celery Tasks for Call Intelligence

Async task processing for:
- Single transcript processing
- Batch transcript processing
- Cleanup of old results

Usage:
    # Process single transcript
    result = process_transcript_task.delay(request_data)

    # Process batch
    result = process_batch_task.delay(batch_id, request_ids)

    # Schedule cleanup
    cleanup_old_results_task.apply_async(kwargs={"days": 90})
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from celery import shared_task
from sqlalchemy import text

from tasks.celery_app import celery_app
from db.session import get_db_session

logger = logging.getLogger(__name__)


# =============================================================================
# Task Configuration
# =============================================================================

# Rate limiting for LLM API calls
RATE_LIMIT_SINGLE = "30/m"  # 30 requests per minute
RATE_LIMIT_BATCH = "5/m"   # 5 batch jobs per minute


# =============================================================================
# Single Transcript Processing Task
# =============================================================================

@celery_app.task(
    name="tasks.call_intelligence_tasks.process_transcript_task",
    queue="ai_tasks",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    rate_limit=RATE_LIMIT_SINGLE,
    soft_time_limit=120,
    time_limit=150,
)
def process_transcript_task(
    self,
    request_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Async task for single transcript processing.

    Args:
        request_data: Dict with CallIntelligenceRequest fields:
            - call_id (required)
            - loan_id (optional)
            - organization_id (optional)
            - transcript (required)
            - call_type (optional)

    Returns:
        Dict with processing results

    Raises:
        Retry on transient failures
    """
    import asyncio
    from services.call_intelligence.processor import CallIntelligenceProcessor
    from services.call_intelligence.data_contracts import CallIntelligenceRequest
    from services.call_intelligence.llm_client import create_llm_client

    call_id = request_data.get("call_id", "unknown")
    org_id = request_data.get("organization_id")
    logger.info(f"Processing transcript task: {call_id}")

    try:
        # Create request object
        request = CallIntelligenceRequest(
            call_id=call_id,
            loan_id=request_data.get("loan_id"),
            organization_id=org_id,
            transcript=request_data.get("transcript", ""),
        )

        # Get tenant-scoped database session if org_id is available,
        # otherwise fall back to un-scoped session
        if org_id:
            from tasks.base import tenant_task_session
            ctx = tenant_task_session(org_id)
        else:
            from contextlib import contextmanager
            @contextmanager
            def _fallback_session():
                db = get_db_session()
                try:
                    yield db
                finally:
                    db.close()
            ctx = _fallback_session()

        with ctx as db:
            # Create LLM client and processor
            llm_client = create_llm_client()
            processor = CallIntelligenceProcessor(db, llm_client)

            # Process synchronously (we're in a Celery worker)
            response = asyncio.run(processor.process_transcript(request))

            result = {
                "success": response.success,
                "call_id": call_id,
                "total_extractions": response.total_extractions,
                "high_confidence_count": response.high_confidence_count,
                "processing_time_ms": response.processing_time_ms,
                "extraction_method": response.extraction_method,
                "errors": response.errors,
            }

            logger.info(
                f"Transcript task complete: {call_id}, "
                f"{response.total_extractions} extractions, "
                f"{response.processing_time_ms}ms"
            )

            return result

    except Exception as e:
        logger.exception(f"Transcript task failed for {call_id}: {e}")

        # Retry on transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

        return {
            "success": False,
            "call_id": call_id,
            "error": "Internal server error",
        }


# =============================================================================
# Batch Processing Task
# =============================================================================

@celery_app.task(
    name="tasks.call_intelligence_tasks.process_batch_task",
    queue="ai_tasks",
    bind=True,
    max_retries=1,
    rate_limit=RATE_LIMIT_BATCH,
    soft_time_limit=600,
    time_limit=660,
)
def process_batch_task(
    self,
    batch_id: str,
    request_ids: List[str],
    organization_id: Optional[int] = None,
    max_concurrent: int = 10,
) -> Dict[str, Any]:
    """
    Async task for batch processing multiple transcripts.

    Args:
        batch_id: Unique batch job identifier
        request_ids: List of call_ids to process
        organization_id: Organization filter
        max_concurrent: Max concurrent processing (default 10)

    Returns:
        Dict with batch processing results
    """
    import asyncio
    from services.call_intelligence.batch_processor import BatchProcessor
    from services.call_intelligence.llm_client import create_llm_client

    logger.info(f"Processing batch task: {batch_id} with {len(request_ids)} requests")

    try:
        # Get tenant-scoped database session if org_id is available
        if organization_id:
            from tasks.base import tenant_task_session
            ctx = tenant_task_session(organization_id)
        else:
            from contextlib import contextmanager
            @contextmanager
            def _fallback_session():
                _db = get_db_session()
                try:
                    yield _db
                finally:
                    _db.close()
            ctx = _fallback_session()

        with ctx as db:
            # Create LLM client and batch processor
            llm_client = create_llm_client()
            processor = BatchProcessor(db, llm_client)

            # Create batch job if not exists
            job = processor.get_batch_job(batch_id)
            if not job:
                job = processor.create_batch_job(request_ids, organization_id)

            # Process the batch
            job = asyncio.run(processor.process_batch_job(batch_id, max_concurrent))

            result = {
                "success": job.status in ("completed", "partial"),
                "batch_id": batch_id,
                "status": job.status,
                "total_requests": job.total_requests,
                "completed": job.completed,
                "failed": job.failed,
                "error_message": job.error_message,
            }

            logger.info(
                f"Batch task complete: {batch_id}, "
                f"{job.completed}/{job.total_requests} successful"
            )

            return result

    except Exception as e:
        logger.exception(f"Batch task failed for {batch_id}: {e}")

        # Update batch status to failed
        try:
            db = get_db_session()
            db.execute(
                text("""
                    UPDATE batch_jobs
                    SET status = 'failed', error_message = :error
                    WHERE batch_id = :batch_id
                """),
                {"batch_id": batch_id, "error": "Internal server error"[:500]}
            )
            db.commit()
            db.close()
        except Exception as e2:
            logger.warning(f"Error updating batch status to failed for {batch_id}: {e2}")

        return {
            "success": False,
            "batch_id": batch_id,
            "error": "Internal server error",
        }


# =============================================================================
# Cleanup Task
# =============================================================================

@celery_app.task(
    name="tasks.call_intelligence_tasks.cleanup_old_results_task",
    queue="low_priority",
    soft_time_limit=300,
    time_limit=360,
)
def cleanup_old_results_task(
    days: int = 90,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Cleanup old extraction results and batch jobs.

    Args:
        days: Delete results older than this many days (default 90)
        dry_run: If True, count but don't delete

    Returns:
        Dict with cleanup summary
    """
    logger.info(f"Starting cleanup task: older than {days} days, dry_run={dry_run}")

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        db = get_db_session()

        try:
            # Count records to delete
            counts = {}

            # Call intelligence results
            result = db.execute(
                text("""
                    SELECT COUNT(*) FROM call_intelligence_results
                    WHERE created_at < :cutoff
                """),
                {"cutoff": cutoff_date}
            ).scalar()
            counts["call_intelligence_results"] = result or 0

            # Batch jobs
            result = db.execute(
                text("""
                    SELECT COUNT(*) FROM batch_jobs
                    WHERE created_at < :cutoff
                """),
                {"cutoff": cutoff_date}
            ).scalar()
            counts["batch_jobs"] = result or 0

            # Review queue (completed only)
            result = db.execute(
                text("""
                    SELECT COUNT(*) FROM extraction_review_queue
                    WHERE created_at < :cutoff AND review_status != 'pending'
                """),
                {"cutoff": cutoff_date}
            ).scalar()
            counts["review_queue_completed"] = result or 0

            if not dry_run:
                # Delete old records
                deleted = {}

                result = db.execute(
                    text("""
                        DELETE FROM call_intelligence_results
                        WHERE created_at < :cutoff
                    """),
                    {"cutoff": cutoff_date}
                )
                deleted["call_intelligence_results"] = result.rowcount

                result = db.execute(
                    text("""
                        DELETE FROM batch_jobs
                        WHERE created_at < :cutoff
                    """),
                    {"cutoff": cutoff_date}
                )
                deleted["batch_jobs"] = result.rowcount

                result = db.execute(
                    text("""
                        DELETE FROM extraction_review_queue
                        WHERE created_at < :cutoff AND review_status != 'pending'
                    """),
                    {"cutoff": cutoff_date}
                )
                deleted["review_queue_completed"] = result.rowcount

                db.commit()

                logger.info(f"Cleanup complete: deleted {deleted}")

                return {
                    "success": True,
                    "dry_run": False,
                    "cutoff_days": days,
                    "counts_found": counts,
                    "deleted": deleted,
                }
            else:
                logger.info(f"Cleanup dry run: would delete {counts}")

                return {
                    "success": True,
                    "dry_run": True,
                    "cutoff_days": days,
                    "counts_found": counts,
                }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Cleanup task failed: {e}")
        return {
            "success": False,
            "error": "Internal server error",
        }


# =============================================================================
# Reprocess Failed Task
# =============================================================================

@celery_app.task(
    name="tasks.call_intelligence_tasks.reprocess_failed_task",
    queue="low_priority",
)
def reprocess_failed_task(
    hours: int = 24,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Reprocess failed extractions from the last N hours.

    Args:
        hours: Look back this many hours for failures
        limit: Maximum number to reprocess

    Returns:
        Dict with reprocessing results
    """
    logger.info(f"Reprocessing failed extractions from last {hours} hours")

    cutoff_date = datetime.now(timezone.utc) - timedelta(hours=hours)

    try:
        db = get_db_session()

        try:
            # Find failed extractions
            results = db.execute(
                text("""
                    SELECT call_id, loan_id, organization_id
                    FROM call_intelligence_results
                    WHERE created_at > :cutoff
                    AND total_extractions = 0
                    LIMIT :limit
                """),
                {"cutoff": cutoff_date, "limit": limit}
            ).fetchall()

            if not results:
                return {
                    "success": True,
                    "requeued": 0,
                    "message": "No failed extractions found",
                }

            # Requeue each for processing
            requeued = 0
            for row in results:
                try:
                    # Load transcript
                    transcript_result = db.execute(
                        text("""
                            SELECT transcript FROM calls WHERE call_id = :call_id
                        """),
                        {"call_id": row[0]}
                    ).fetchone()

                    if transcript_result and transcript_result[0]:
                        process_transcript_task.delay({
                            "call_id": row[0],
                            "loan_id": row[1],
                            "organization_id": row[2],
                            "transcript": transcript_result[0],
                        })
                        requeued += 1
                except Exception as e:
                    logger.warning(f"Failed to requeue {row[0]}: {e}")

            logger.info(f"Requeued {requeued} failed extractions")

            return {
                "success": True,
                "found": len(results),
                "requeued": requeued,
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Reprocess task failed: {e}")
        return {
            "success": False,
            "error": "Internal server error",
        }
