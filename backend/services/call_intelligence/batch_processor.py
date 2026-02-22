"""
Batch Processor for Call Intelligence

Enables efficient processing of multiple transcripts with controlled concurrency.
Supports both synchronous batch processing and async job creation for background
processing via Celery.

Features:
- Controlled concurrency to avoid overwhelming LLM APIs
- Progress tracking for batch jobs
- Error handling with partial success support
- Integration with Celery for background processing
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from .llm_client import BaseLLMClient

from .data_contracts import (
    CallIntelligenceRequest,
    CallIntelligenceResponse,
    BatchJob,
    BatchJobStatus,
)
from .processor import CallIntelligenceProcessor
from .pii_utils import mask_pii_for_logging

logger = logging.getLogger(__name__)


# =============================================================================
# Batch Processing Configuration
# =============================================================================

DEFAULT_MAX_CONCURRENT = 10
"""Default max concurrent requests (respects LLM rate limits)."""

DEFAULT_BATCH_TIMEOUT = 600
"""Default timeout for batch processing in seconds (10 minutes)."""


class BatchProcessor:
    """
    Process multiple transcripts efficiently with controlled concurrency.

    Usage:
        processor = BatchProcessor(db_session, llm_client)

        # Process batch synchronously
        results = await processor.process_batch(requests, max_concurrent=10)

        # Create background job
        job = processor.create_batch_job(request_ids)
    """

    def __init__(
        self,
        db_session: Optional["Session"] = None,
        llm_client: Optional["BaseLLMClient"] = None,
    ):
        """
        Initialize batch processor.

        Args:
            db_session: SQLAlchemy session for database operations
            llm_client: LLM client for AI extractions
        """
        self.db = db_session
        self.llm_client = llm_client
        self._processor = CallIntelligenceProcessor(db_session, llm_client)

        # Track active batch jobs
        self._active_jobs: Dict[str, BatchJob] = {}

    async def process_batch(
        self,
        requests: List[CallIntelligenceRequest],
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        timeout: float = DEFAULT_BATCH_TIMEOUT,
    ) -> List[CallIntelligenceResponse]:
        """
        Process multiple transcripts with controlled concurrency.

        Args:
            requests: List of CallIntelligenceRequest to process
            max_concurrent: Maximum concurrent requests (default 10)
            timeout: Total timeout for batch in seconds

        Returns:
            List of CallIntelligenceResponse in same order as requests
        """
        if not requests:
            return []

        logger.info(f"Starting batch processing of {len(requests)} requests (max_concurrent={max_concurrent})")

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(request: CallIntelligenceRequest) -> CallIntelligenceResponse:
            async with semaphore:
                try:
                    return await self._processor.process_transcript(request)
                except Exception as e:
                    safe_error = mask_pii_for_logging(str(e))
                    logger.error(f"Batch item {request.call_id} failed: {safe_error}")
                    return CallIntelligenceResponse(
                        call_id=request.call_id,
                        success=False,
                        errors=[safe_error],
                    )

        # Process all requests with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[process_with_semaphore(req) for req in requests]),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Batch processing timed out after {timeout}s")
            # Return partial results for completed items, errors for rest
            results = []
            for req in requests:
                results.append(CallIntelligenceResponse(
                    call_id=req.call_id,
                    success=False,
                    errors=["Batch processing timed out"],
                ))

        # Log summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        logger.info(f"Batch complete: {successful} successful, {failed} failed")

        return results

    def create_batch_job(
        self,
        request_ids: List[str],
        organization_id: Optional[int] = None,
    ) -> BatchJob:
        """
        Create a trackable batch job for background processing.

        This creates a job record that can be processed asynchronously
        via Celery tasks.

        Args:
            request_ids: List of call_ids or request IDs to process
            organization_id: Optional organization filter

        Returns:
            BatchJob with tracking ID
        """
        batch_id = f"batch_{uuid.uuid4().hex[:12]}"

        job = BatchJob(
            batch_id=batch_id,
            total_requests=len(request_ids),
            request_ids=request_ids,
            status="pending",
        )

        # Store job for tracking
        self._active_jobs[batch_id] = job

        # Persist to database if available
        if self.db:
            self._save_batch_job(job, organization_id)

        logger.info(f"Created batch job {batch_id} with {len(request_ids)} requests")

        return job

    def get_batch_job(self, batch_id: str) -> Optional[BatchJob]:
        """
        Get batch job status.

        Args:
            batch_id: Batch job ID

        Returns:
            BatchJob if found, None otherwise
        """
        # Check in-memory first
        if batch_id in self._active_jobs:
            return self._active_jobs[batch_id]

        # Check database
        if self.db:
            return self._load_batch_job(batch_id)

        return None

    def update_batch_job(
        self,
        batch_id: str,
        completed: Optional[int] = None,
        failed: Optional[int] = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[BatchJob]:
        """
        Update batch job progress.

        Args:
            batch_id: Batch job ID
            completed: Number of completed requests
            failed: Number of failed requests
            status: New status
            error_message: Error message if failed

        Returns:
            Updated BatchJob if found
        """
        job = self.get_batch_job(batch_id)
        if not job:
            return None

        if completed is not None:
            job.completed = completed
        if failed is not None:
            job.failed = failed
        if status is not None:
            job.status = status
        if error_message is not None:
            job.error_message = error_message

        # Mark completed time if finished
        if status in ("completed", "failed", "partial"):
            job.completed_at = datetime.utcnow()

        # Persist update
        if self.db:
            self._save_batch_job(job)

        self._active_jobs[batch_id] = job

        return job

    async def process_batch_job(
        self,
        batch_id: str,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ) -> BatchJob:
        """
        Process a batch job and update its status.

        Args:
            batch_id: Batch job ID to process
            max_concurrent: Maximum concurrent requests

        Returns:
            Updated BatchJob with results
        """
        job = self.get_batch_job(batch_id)
        if not job:
            logger.error(f"Batch job {batch_id} not found")
            raise ValueError(f"Batch job {batch_id} not found")

        # Update status to processing
        self.update_batch_job(batch_id, status="processing")

        try:
            # Load requests from database or create from IDs
            requests = await self._load_requests_for_batch(job.request_ids)

            # Process batch
            results = await self.process_batch(requests, max_concurrent)

            # Count successes and failures
            completed = sum(1 for r in results if r.success)
            failed = len(results) - completed

            # Store results
            job.results = {
                r.call_id: r.to_dict() for r in results
            }

            # Determine final status
            if failed == 0:
                status = "completed"
            elif completed == 0:
                status = "failed"
            else:
                status = "partial"

            self.update_batch_job(
                batch_id,
                completed=completed,
                failed=failed,
                status=status,
            )

        except Exception as e:
            safe_error = mask_pii_for_logging(str(e))
            logger.exception(f"Batch job {batch_id} failed: {safe_error}")
            self.update_batch_job(
                batch_id,
                status="failed",
                error_message=safe_error,
            )

        return self.get_batch_job(batch_id)

    async def _load_requests_for_batch(
        self,
        request_ids: List[str],
    ) -> List[CallIntelligenceRequest]:
        """
        Load requests for batch processing.

        Loads call data from database or creates minimal request objects.
        """
        requests = []

        if self.db:
            from sqlalchemy import text

            # Load call data from database
            result = self.db.execute(
                text("""
                    SELECT call_id, loan_id, organization_id, transcript
                    FROM calls
                    WHERE call_id = ANY(:call_ids)
                """),
                {"call_ids": request_ids}
            ).fetchall()

            for row in result:
                requests.append(CallIntelligenceRequest(
                    call_id=row[0],
                    loan_id=row[1],
                    organization_id=row[2],
                    transcript=row[3] or "",
                ))

        # For any IDs not found, create placeholder requests
        found_ids = {r.call_id for r in requests}
        for call_id in request_ids:
            if call_id not in found_ids:
                requests.append(CallIntelligenceRequest(
                    call_id=call_id,
                    transcript="",  # Will fail with "no transcript" error
                ))

        return requests

    def _save_batch_job(
        self,
        job: BatchJob,
        organization_id: Optional[int] = None,
    ) -> None:
        """Persist batch job to database."""
        try:
            from sqlalchemy import text
            import json

            self.db.execute(
                text("""
                    INSERT INTO batch_jobs
                    (batch_id, organization_id, total_requests, completed, failed,
                     status, error_message, request_ids, created_at, completed_at)
                    VALUES
                    (:batch_id, :org_id, :total, :completed, :failed,
                     :status, :error, :request_ids, :created_at, :completed_at)
                    ON CONFLICT (batch_id) DO UPDATE SET
                        completed = :completed,
                        failed = :failed,
                        status = :status,
                        error_message = :error,
                        completed_at = :completed_at
                """),
                {
                    "batch_id": job.batch_id,
                    "org_id": organization_id,
                    "total": job.total_requests,
                    "completed": job.completed,
                    "failed": job.failed,
                    "status": job.status,
                    "error": job.error_message,
                    "request_ids": json.dumps(job.request_ids),
                    "created_at": job.created_at,
                    "completed_at": job.completed_at,
                }
            )
            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to save batch job: {e}")
            try:
                self.db.rollback()
            except Exception as e:
                logger.error(f"Error during rollback in _save_batch_job: {e}")

    def _load_batch_job(self, batch_id: str) -> Optional[BatchJob]:
        """Load batch job from database."""
        try:
            from sqlalchemy import text
            import json

            result = self.db.execute(
                text("""
                    SELECT batch_id, total_requests, completed, failed,
                           status, error_message, request_ids, created_at, completed_at
                    FROM batch_jobs
                    WHERE batch_id = :batch_id
                """),
                {"batch_id": batch_id}
            ).fetchone()

            if result:
                return BatchJob(
                    batch_id=result[0],
                    total_requests=result[1],
                    completed=result[2],
                    failed=result[3],
                    status=result[4],
                    error_message=result[5],
                    request_ids=json.loads(result[6]) if result[6] else [],
                    created_at=result[7],
                    completed_at=result[8],
                )
        except Exception as e:
            logger.warning(f"Failed to load batch job: {e}")

        return None


# =============================================================================
# Utility Functions
# =============================================================================

def estimate_batch_processing_time(
    request_count: int,
    avg_transcript_length: int = 5000,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
) -> Dict[str, Any]:
    """
    Estimate batch processing time.

    Args:
        request_count: Number of requests in batch
        avg_transcript_length: Average transcript length in characters
        max_concurrent: Max concurrent requests

    Returns:
        Dict with estimated time ranges
    """
    # Estimate based on unified extraction (~2-5s per transcript)
    avg_time_per_request = 3.0  # seconds

    # Calculate parallel batches needed
    batches = (request_count + max_concurrent - 1) // max_concurrent

    # Total estimated time
    total_seconds = batches * avg_time_per_request

    return {
        "request_count": request_count,
        "max_concurrent": max_concurrent,
        "estimated_seconds_min": int(total_seconds * 0.5),
        "estimated_seconds_max": int(total_seconds * 2.0),
        "estimated_minutes": round(total_seconds / 60, 1),
    }
