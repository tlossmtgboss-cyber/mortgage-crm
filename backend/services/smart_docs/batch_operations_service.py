"""
Smart Docs V2 - Batch Operations Service

Production-grade service for bulk document operations:
- BULK_UPLOAD:     Process a ZIP file containing multiple documents
- BULK_CLASSIFY:   AI-classify all pending/unclassified documents for a loan
- BULK_EXPORT:     Create a submission-ready ZIP of all loan documents
- BULK_REMINDER:   Send reminders for all outstanding document requests on a loan
- STACKING_ORDER:  Organize loan documents in investor-required stacking order

Design principles:
- Org-id isolation on every query (multi-tenant safe)
- Cooperative cancellation: each item iteration checks job.status
- Continue-on-failure: individual item errors are logged, not propagated
- Concurrency control: max 3 active batch jobs per org
- Rate limiting: configurable delay between items to prevent API abuse
- Asyncio for concurrent I/O within batches (S3 uploads, AI calls)
- Structured logging with job_id correlation

Usage:
    from services.smart_docs.batch_operations_service import (
        BatchOperationsService,
        get_batch_operations_service,
    )

    service = get_batch_operations_service()

    # Start a bulk classify job (returns immediately with job_id)
    job = await service.start_bulk_classify(
        db=db,
        org_id=1,
        user_id=42,
        loan_id=100,
    )

    # Poll progress
    status = service.get_job_status(db=db, org_id=1, job_id=job.id)

    # Cancel a running job
    service.cancel_job(db=db, org_id=1, job_id=job.id)
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, text
from sqlalchemy.orm import Session

from database.models.batch_job import BatchJob, BatchJobStatus, BatchJobType

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Maximum concurrent batch jobs (PENDING + RUNNING) per organization
MAX_CONCURRENT_JOBS_PER_ORG = int(os.getenv("BATCH_MAX_CONCURRENT_PER_ORG", "3"))

# Delay between individual items to prevent API/DB saturation (seconds)
ITEM_RATE_LIMIT_SECONDS = float(os.getenv("BATCH_ITEM_RATE_LIMIT_SECONDS", "0.1"))

# Maximum items per single batch job (safety valve)
MAX_ITEMS_PER_JOB = int(os.getenv("BATCH_MAX_ITEMS_PER_JOB", "500"))

# Maximum ZIP file size for bulk upload (bytes) -- default 200 MB
MAX_ZIP_SIZE_BYTES = int(os.getenv("BATCH_MAX_ZIP_SIZE_BYTES", str(200 * 1024 * 1024)))

# Concurrency limit for async I/O tasks within a single batch job
ASYNC_CONCURRENCY_LIMIT = int(os.getenv("BATCH_ASYNC_CONCURRENCY", "5"))

# Investor stacking order (index = position, value = doc type string)
INVESTOR_STACKING_ORDER: List[str] = [
    "APPLICATION",
    "DRIVERS_LICENSE",
    "PURCHASE_CONTRACT",
    "APPRAISAL",
    "TITLE_REPORT",
    "HOMEOWNERS_INSURANCE",
    "PAYSTUB",
    "W2",
    "TAX_RETURN",
    "BUSINESS_TAX_RETURN",
    "PROFIT_LOSS",
    "BALANCE_SHEET",
    "BANK_STATEMENT",
    "INVESTMENT_STATEMENT",
    "GIFT_LETTER",
    "LOE",
    "LEASE_AGREEMENT",
    "FHA_CERT",
    "VA_COE",
    "DD214",
    "BANKRUPTCY_DISCHARGE",
    "OTHER",
]

# Allowed MIME types for documents inside uploaded ZIPs
ALLOWED_MIME_TYPES = frozenset({
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/gif",
    "image/webp",
})

# Map file extensions to MIME types for ZIP entries (which lack content-type)
EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


# =============================================================================
# EXCEPTIONS
# =============================================================================

class BatchOperationError(Exception):
    """Raised for batch operation failures that should surface to the caller."""

    def __init__(self, message: str, code: str = "BATCH_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ConcurrencyLimitExceeded(BatchOperationError):
    """Raised when an org already has the max number of active batch jobs."""

    def __init__(self, org_id: int, current_count: int):
        super().__init__(
            message=(
                f"Organization {org_id} already has {current_count} active batch jobs "
                f"(max {MAX_CONCURRENT_JOBS_PER_ORG}). Wait for existing jobs to finish or cancel them."
            ),
            code="CONCURRENCY_LIMIT_EXCEEDED",
        )


# =============================================================================
# SERVICE
# =============================================================================

class BatchOperationsService:
    """
    Orchestrates Smart Docs batch operations with progress tracking,
    cancellation support, and per-item error handling.

    All public methods require explicit org_id for tenant isolation.
    """

    # ------------------------------------------------------------------
    # Job lifecycle helpers
    # ------------------------------------------------------------------

    def _check_concurrency(self, db: Session, org_id: int) -> int:
        """
        Check how many active (PENDING/RUNNING) batch jobs exist for an org.
        Raises ConcurrencyLimitExceeded if at capacity.
        Returns the current count.
        """
        active_count = (
            db.query(func.count(BatchJob.id))
            .filter(
                BatchJob.organization_id == org_id,
                BatchJob.status.in_([
                    BatchJobStatus.PENDING.value,
                    BatchJobStatus.RUNNING.value,
                ]),
            )
            .scalar()
        ) or 0

        if active_count >= MAX_CONCURRENT_JOBS_PER_ORG:
            raise ConcurrencyLimitExceeded(org_id, active_count)

        return active_count

    def _create_job(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        job_type: BatchJobType,
        total_items: int,
        input_params: Optional[Dict[str, Any]] = None,
    ) -> BatchJob:
        """Create a BatchJob row in PENDING status (with concurrency guard)."""
        self._check_concurrency(db, org_id)

        if total_items > MAX_ITEMS_PER_JOB:
            raise BatchOperationError(
                f"Batch size {total_items} exceeds maximum of {MAX_ITEMS_PER_JOB}.",
                code="MAX_ITEMS_EXCEEDED",
            )

        job = BatchJob(
            organization_id=org_id,
            job_type=job_type.value,
            status=BatchJobStatus.PENDING.value,
            total_items=total_items,
            input_params=input_params,
            created_by_user_id=user_id,
        )
        db.add(job)
        db.flush()  # Assign job.id
        logger.info(
            "batch_job_created job_id=%s type=%s org_id=%s items=%s user_id=%s",
            job.id, job_type.value, org_id, total_items, user_id,
        )
        return job

    def _mark_running(self, db: Session, job: BatchJob) -> None:
        """Transition job to RUNNING."""
        job.status = BatchJobStatus.RUNNING.value
        job.started_at = datetime.now(timezone.utc)
        db.flush()

    def _mark_completed(self, db: Session, job: BatchJob, results: Optional[Dict] = None) -> None:
        """Transition job to COMPLETED."""
        job.status = BatchJobStatus.COMPLETED.value
        job.completed_at = datetime.now(timezone.utc)
        if results:
            job.results = results
        db.flush()
        logger.info(
            "batch_job_completed job_id=%s processed=%s failed=%s skipped=%s",
            job.id, job.processed_items, job.failed_items, job.skipped_items,
        )

    def _mark_failed(self, db: Session, job: BatchJob, error_message: str) -> None:
        """Transition job to FAILED."""
        job.status = BatchJobStatus.FAILED.value
        job.completed_at = datetime.now(timezone.utc)
        job.results = {"error": error_message}
        db.flush()
        logger.error(
            "batch_job_failed job_id=%s error=%s",
            job.id, error_message,
        )

    def _is_cancelled(self, db: Session, job_id: int, org_id: int) -> bool:
        """
        Re-read job status from DB to detect cancellation.
        Uses a fresh query (not cached ORM state) to pick up concurrent updates.
        """
        row = db.execute(
            text(
                "SELECT status FROM smart_docs_batch_jobs "
                "WHERE id = :job_id AND organization_id = :org_id"
            ),
            {"job_id": job_id, "org_id": org_id},
        ).fetchone()
        if row is None:
            return True  # Treat missing row as cancelled
        return row[0] == BatchJobStatus.CANCELLED.value

    def _append_item_error(
        self,
        job: BatchJob,
        item_index: int,
        item_name: str,
        error: str,
    ) -> None:
        """Append a per-item error entry to job.error_log (in-memory)."""
        if job.error_log is None:
            job.error_log = []
        job.error_log = [
            *job.error_log,
            {
                "item_index": item_index,
                "item_name": item_name,
                "error": str(error),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        ]

    def _flush_progress(self, db: Session, job: BatchJob) -> None:
        """Persist current progress counters to the database."""
        db.flush()

    # ------------------------------------------------------------------
    # Public: Job status & management
    # ------------------------------------------------------------------

    def get_job_status(self, db: Session, org_id: int, job_id: int) -> Optional[Dict]:
        """
        Get the current status of a batch job.
        Returns None if the job does not exist or belongs to a different org.
        """
        job = (
            db.query(BatchJob)
            .filter(BatchJob.id == job_id, BatchJob.organization_id == org_id)
            .first()
        )
        if job is None:
            return None
        return job.to_dict()

    def cancel_job(self, db: Session, org_id: int, job_id: int) -> Dict:
        """
        Request cancellation of a batch job.

        Only PENDING and RUNNING jobs can be cancelled. The running job will
        stop at the next item boundary (cooperative cancellation).

        Returns the updated job dict.
        Raises BatchOperationError if the job cannot be cancelled.
        """
        job = (
            db.query(BatchJob)
            .filter(BatchJob.id == job_id, BatchJob.organization_id == org_id)
            .first()
        )
        if job is None:
            raise BatchOperationError(
                f"Batch job {job_id} not found.",
                code="JOB_NOT_FOUND",
            )

        if job.is_terminal:
            raise BatchOperationError(
                f"Cannot cancel job {job_id} -- already in terminal state '{job.status}'.",
                code="ALREADY_TERMINAL",
            )

        job.status = BatchJobStatus.CANCELLED.value
        job.completed_at = datetime.now(timezone.utc)
        db.flush()
        logger.info("batch_job_cancelled job_id=%s org_id=%s", job_id, org_id)
        return job.to_dict()

    def list_jobs(
        self,
        db: Session,
        org_id: int,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict:
        """
        List batch jobs for an org with optional filters.
        Returns {jobs: [...], total: int}.
        """
        query = db.query(BatchJob).filter(BatchJob.organization_id == org_id)

        if status:
            query = query.filter(BatchJob.status == status)
        if job_type:
            query = query.filter(BatchJob.job_type == job_type)

        total = query.count()
        jobs = (
            query.order_by(BatchJob.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "jobs": [j.to_dict() for j in jobs],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    # ------------------------------------------------------------------
    # BULK UPLOAD
    # ------------------------------------------------------------------

    async def start_bulk_upload(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        loan_id: int,
        zip_bytes: bytes,
        borrower_id: Optional[int] = None,
    ) -> BatchJob:
        """
        Process a ZIP file containing multiple documents.

        Each file in the ZIP is individually validated, scanned, stored, and
        queued for AI classification via the existing DocumentUploadPipeline.

        Args:
            db: Database session.
            org_id: Organization ID.
            user_id: Uploading user ID.
            loan_id: Target loan ID.
            zip_bytes: Raw bytes of the ZIP file.
            borrower_id: Optional borrower ID.

        Returns:
            The created BatchJob (initially PENDING, transitions to RUNNING/COMPLETED).
        """
        if len(zip_bytes) > MAX_ZIP_SIZE_BYTES:
            raise BatchOperationError(
                f"ZIP file is {len(zip_bytes) / (1024 * 1024):.1f} MB -- "
                f"maximum is {MAX_ZIP_SIZE_BYTES / (1024 * 1024):.0f} MB.",
                code="ZIP_TOO_LARGE",
            )

        # Parse the ZIP to enumerate valid entries
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile:
            raise BatchOperationError("Invalid ZIP file.", code="INVALID_ZIP")

        entries = self._enumerate_zip_entries(zf)
        if not entries:
            raise BatchOperationError(
                "ZIP file contains no supported document files.",
                code="EMPTY_ZIP",
            )

        job = self._create_job(
            db=db,
            org_id=org_id,
            user_id=user_id,
            job_type=BatchJobType.BULK_UPLOAD,
            total_items=len(entries),
            input_params={
                "loan_id": loan_id,
                "borrower_id": borrower_id,
                "file_count": len(entries),
                "zip_size_bytes": len(zip_bytes),
            },
        )
        db.commit()

        # Execute in background (fire-and-forget within current event loop)
        asyncio.ensure_future(
            self._run_bulk_upload(db, job.id, org_id, user_id, loan_id, borrower_id, zf, entries)
        )
        return job

    async def _run_bulk_upload(
        self,
        db: Session,
        job_id: int,
        org_id: int,
        user_id: int,
        loan_id: int,
        borrower_id: Optional[int],
        zf: zipfile.ZipFile,
        entries: List[Tuple[str, str]],
    ) -> None:
        """Background coroutine that processes each file in the ZIP."""
        from db import SessionLocal

        session = SessionLocal()
        try:
            job = session.query(BatchJob).filter(BatchJob.id == job_id).first()
            if job is None:
                return

            self._mark_running(session, job)
            session.commit()

            semaphore = asyncio.Semaphore(ASYNC_CONCURRENCY_LIMIT)
            upload_results: List[Dict] = []

            for idx, (entry_name, mime_type) in enumerate(entries):
                # Cooperative cancellation check
                if self._is_cancelled(session, job_id, org_id):
                    logger.info("batch_job_cancelled_mid_run job_id=%s at_item=%s", job_id, idx)
                    break

                try:
                    async with semaphore:
                        file_bytes = zf.read(entry_name)
                        result = await self._upload_single_file(
                            session, org_id, user_id, loan_id,
                            borrower_id, entry_name, mime_type, file_bytes,
                        )
                        upload_results.append(result)

                    if result.get("success"):
                        job.processed_items = (job.processed_items or 0) + 1
                    elif result.get("skipped"):
                        job.skipped_items = (job.skipped_items or 0) + 1
                    else:
                        job.failed_items = (job.failed_items or 0) + 1
                        self._append_item_error(job, idx, entry_name, result.get("error", "Unknown error"))

                except Exception as e:
                    logger.exception("batch_upload_item_error job_id=%s file=%s", job_id, entry_name)
                    job.failed_items = (job.failed_items or 0) + 1
                    self._append_item_error(job, idx, entry_name, str(e))

                # Rate limiting
                if ITEM_RATE_LIMIT_SECONDS > 0:
                    await asyncio.sleep(ITEM_RATE_LIMIT_SECONDS)

                # Periodic progress flush (every 10 items)
                if (idx + 1) % 10 == 0:
                    self._flush_progress(session, job)
                    session.commit()

            # Final status
            if self._is_cancelled(session, job_id, org_id):
                job.status = BatchJobStatus.CANCELLED.value
                job.completed_at = datetime.now(timezone.utc)
            else:
                self._mark_completed(session, job, results={
                    "uploaded": job.processed_items,
                    "failed": job.failed_items,
                    "skipped": job.skipped_items,
                })
            session.commit()

        except Exception as e:
            logger.exception("batch_bulk_upload_fatal job_id=%s", job_id)
            try:
                job = session.query(BatchJob).filter(BatchJob.id == job_id).first()
                if job and not job.is_terminal:
                    self._mark_failed(session, job, str(e))
                    session.commit()
            except Exception as e2:
                logger.exception("batch_bulk_upload_fatal_cleanup_failed job_id=%s: %s", job_id, e2)
        finally:
            session.close()

    async def _upload_single_file(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        loan_id: int,
        borrower_id: Optional[int],
        filename: str,
        mime_type: str,
        file_bytes: bytes,
    ) -> Dict:
        """Upload a single file through the existing upload pipeline."""
        try:
            from services.smart_docs.upload_pipeline import get_upload_pipeline
            pipeline = get_upload_pipeline()
            result = await pipeline.process_upload(
                file_bytes=file_bytes,
                filename=filename,
                mime_type=mime_type,
                org_id=org_id,
                user_id=str(user_id),
                loan_id=loan_id,
                db=db,
                borrower_id=borrower_id,
                upload_source="BULK_UPLOAD",
            )
            return result.to_dict()
        except Exception as e:
            logger.exception("upload_single_file_error file=%s", filename)
            return {"success": False, "error": str(e)}

    def _enumerate_zip_entries(self, zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
        """
        Extract valid (non-directory, supported MIME type) entries from a ZIP.
        Returns list of (entry_name, mime_type) tuples.
        """
        entries = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            # Skip macOS resource forks and hidden files
            basename = info.filename.rsplit("/", 1)[-1] if "/" in info.filename else info.filename
            if basename.startswith(".") or basename.startswith("__MACOSX"):
                continue

            ext = os.path.splitext(basename)[1].lower()
            mime_type = EXTENSION_TO_MIME.get(ext)
            if mime_type and mime_type in ALLOWED_MIME_TYPES:
                entries.append((info.filename, mime_type))

        return entries

    # ------------------------------------------------------------------
    # BULK CLASSIFY
    # ------------------------------------------------------------------

    async def start_bulk_classify(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        loan_id: int,
    ) -> BatchJob:
        """
        AI-classify all pending/unclassified documents for a loan.

        Queries smart_documents where doc_type is NULL or classification status
        is pending, then runs each through the AI classifier.

        Returns the created BatchJob.
        """
        # Count unclassified docs
        unclassified = db.execute(
            text(
                "SELECT id, file_name, mime_type, storage_key "
                "FROM smart_documents "
                "WHERE loan_id = :loan_id "
                "  AND (doc_type IS NULL OR doc_type = 'OTHER') "
                "  AND status NOT IN ('DELETED', 'REJECTED') "
                "ORDER BY uploaded_at ASC"
            ),
            {"loan_id": loan_id},
        ).fetchall()

        if not unclassified:
            raise BatchOperationError(
                "No unclassified documents found for this loan.",
                code="NO_ITEMS",
            )

        doc_ids = [row[0] for row in unclassified]

        job = self._create_job(
            db=db,
            org_id=org_id,
            user_id=user_id,
            job_type=BatchJobType.BULK_CLASSIFY,
            total_items=len(doc_ids),
            input_params={"loan_id": loan_id, "document_ids": doc_ids},
        )
        db.commit()

        asyncio.ensure_future(
            self._run_bulk_classify(job.id, org_id, loan_id, doc_ids)
        )
        return job

    async def _run_bulk_classify(
        self,
        job_id: int,
        org_id: int,
        loan_id: int,
        doc_ids: List[int],
    ) -> None:
        """Background coroutine that classifies each document."""
        from db import SessionLocal

        session = SessionLocal()
        try:
            job = session.query(BatchJob).filter(BatchJob.id == job_id).first()
            if job is None:
                return

            self._mark_running(session, job)
            session.commit()

            for idx, doc_id in enumerate(doc_ids):
                if self._is_cancelled(session, job_id, org_id):
                    break

                try:
                    classified = await self._classify_single_document(session, org_id, doc_id)
                    if classified:
                        job.processed_items = (job.processed_items or 0) + 1
                    else:
                        job.skipped_items = (job.skipped_items or 0) + 1
                except Exception as e:
                    logger.exception("batch_classify_item_error job_id=%s doc_id=%s", job_id, doc_id)
                    job.failed_items = (job.failed_items or 0) + 1
                    self._append_item_error(job, idx, f"doc_{doc_id}", str(e))

                if ITEM_RATE_LIMIT_SECONDS > 0:
                    await asyncio.sleep(ITEM_RATE_LIMIT_SECONDS)

                if (idx + 1) % 10 == 0:
                    self._flush_progress(session, job)
                    session.commit()

            if self._is_cancelled(session, job_id, org_id):
                job.status = BatchJobStatus.CANCELLED.value
                job.completed_at = datetime.now(timezone.utc)
            else:
                self._mark_completed(session, job, results={
                    "classified": job.processed_items,
                    "failed": job.failed_items,
                    "skipped": job.skipped_items,
                })
            session.commit()

        except Exception as e:
            logger.exception("batch_bulk_classify_fatal job_id=%s", job_id)
            try:
                job = session.query(BatchJob).filter(BatchJob.id == job_id).first()
                if job and not job.is_terminal:
                    self._mark_failed(session, job, str(e))
                    session.commit()
            except Exception as e2:
                logger.exception("batch_bulk_classify_fatal_cleanup job_id=%s: %s", job_id, e2)
        finally:
            session.close()

    async def _classify_single_document(
        self,
        db: Session,
        org_id: int,
        doc_id: int,
    ) -> bool:
        """
        Classify a single document using the AI classifier.
        Returns True if classification was applied, False if skipped.
        """
        doc_row = db.execute(
            text(
                "SELECT id, file_name, mime_type, storage_key "
                "FROM smart_documents WHERE id = :doc_id"
            ),
            {"doc_id": doc_id},
        ).fetchone()

        if doc_row is None:
            return False

        file_name = doc_row[1]
        mime_type = doc_row[2]
        storage_key = doc_row[3]

        # Retrieve file bytes from S3
        file_bytes = await self._fetch_file_from_storage(storage_key)
        if file_bytes is None:
            logger.warning("batch_classify_no_file doc_id=%s storage_key=%s", doc_id, storage_key)
            return False

        try:
            from services.smart_docs.ai_classifier_service import get_ai_classifier_service
            classifier = get_ai_classifier_service()
            result = classifier.classify_document(
                file_content=file_bytes,
                mime_type=mime_type,
                filename=file_name,
            )

            if result and hasattr(result, "predicted_type") and result.predicted_type:
                db.execute(
                    text(
                        "UPDATE smart_documents "
                        "SET doc_type = :doc_type, updated_at = :now "
                        "WHERE id = :doc_id"
                    ),
                    {
                        "doc_type": result.predicted_type,
                        "now": datetime.now(timezone.utc),
                        "doc_id": doc_id,
                    },
                )
                db.flush()
                return True

        except Exception as e:
            logger.exception("ai_classify_error doc_id=%s: %s", doc_id, e)
            raise

        return False

    async def _fetch_file_from_storage(self, storage_key: str) -> Optional[bytes]:
        """Retrieve file bytes from S3 storage."""
        try:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
            s3 = get_smart_docs_s3_service()
            return s3.download_file(storage_key)
        except Exception as e:
            logger.warning("s3_download_failed key=%s: %s", storage_key, e)
            return None

    # ------------------------------------------------------------------
    # BULK EXPORT
    # ------------------------------------------------------------------

    async def start_bulk_export(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        loan_id: int,
        include_stacking_order: bool = True,
    ) -> BatchJob:
        """
        Create a submission-ready ZIP of all active documents for a loan.

        Optionally organizes files according to investor stacking order.
        The resulting ZIP is uploaded to S3 and a download URL is provided.

        Returns the created BatchJob.
        """
        docs = db.execute(
            text(
                "SELECT id, file_name, doc_type, storage_key, mime_type "
                "FROM smart_documents "
                "WHERE loan_id = :loan_id "
                "  AND status NOT IN ('DELETED', 'REJECTED', 'SUPERSEDED') "
                "ORDER BY uploaded_at ASC"
            ),
            {"loan_id": loan_id},
        ).fetchall()

        if not docs:
            raise BatchOperationError(
                "No documents found for this loan.",
                code="NO_ITEMS",
            )

        doc_list = [
            {
                "id": row[0],
                "file_name": row[1],
                "doc_type": row[2],
                "storage_key": row[3],
                "mime_type": row[4],
            }
            for row in docs
        ]

        job = self._create_job(
            db=db,
            org_id=org_id,
            user_id=user_id,
            job_type=BatchJobType.BULK_EXPORT,
            total_items=len(doc_list),
            input_params={
                "loan_id": loan_id,
                "include_stacking_order": include_stacking_order,
                "document_count": len(doc_list),
            },
        )
        db.commit()

        asyncio.ensure_future(
            self._run_bulk_export(job.id, org_id, loan_id, doc_list, include_stacking_order)
        )
        return job

    async def _run_bulk_export(
        self,
        job_id: int,
        org_id: int,
        loan_id: int,
        doc_list: List[Dict],
        include_stacking_order: bool,
    ) -> None:
        """Background coroutine that builds the export ZIP."""
        from db import SessionLocal

        session = SessionLocal()
        try:
            job = session.query(BatchJob).filter(BatchJob.id == job_id).first()
            if job is None:
                return

            self._mark_running(session, job)
            session.commit()

            zip_buffer = io.BytesIO()
            downloaded_files: List[Tuple[str, bytes, str]] = []  # (filename, bytes, doc_type)

            # Sort by stacking order if requested
            if include_stacking_order:
                doc_list = self._sort_by_stacking_order(doc_list)

            semaphore = asyncio.Semaphore(ASYNC_CONCURRENCY_LIMIT)

            for idx, doc in enumerate(doc_list):
                if self._is_cancelled(session, job_id, org_id):
                    break

                try:
                    async with semaphore:
                        file_bytes = await self._fetch_file_from_storage(doc["storage_key"])

                    if file_bytes:
                        # Prefix with stacking order number if enabled
                        if include_stacking_order:
                            prefix = f"{idx + 1:03d}_"
                        else:
                            prefix = ""

                        # Organize by doc type folders
                        doc_type_folder = doc.get("doc_type") or "UNCATEGORIZED"
                        export_name = f"{doc_type_folder}/{prefix}{doc['file_name']}"
                        downloaded_files.append((export_name, file_bytes, doc.get("doc_type", "")))
                        job.processed_items = (job.processed_items or 0) + 1
                    else:
                        job.failed_items = (job.failed_items or 0) + 1
                        self._append_item_error(
                            job, idx, doc["file_name"],
                            f"Could not retrieve file from storage: {doc['storage_key']}",
                        )

                except Exception as e:
                    logger.exception("batch_export_item_error job_id=%s doc_id=%s", job_id, doc["id"])
                    job.failed_items = (job.failed_items or 0) + 1
                    self._append_item_error(job, idx, doc["file_name"], str(e))

                if ITEM_RATE_LIMIT_SECONDS > 0:
                    await asyncio.sleep(ITEM_RATE_LIMIT_SECONDS)

                if (idx + 1) % 10 == 0:
                    self._flush_progress(session, job)
                    session.commit()

            if self._is_cancelled(session, job_id, org_id):
                job.status = BatchJobStatus.CANCELLED.value
                job.completed_at = datetime.now(timezone.utc)
                session.commit()
                return

            # Build the ZIP
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for export_name, file_bytes, _ in downloaded_files:
                    zf.writestr(export_name, file_bytes)

                # Add manifest
                manifest = self._build_export_manifest(loan_id, downloaded_files)
                zf.writestr("_manifest.txt", manifest)

            zip_buffer.seek(0)

            # Upload the export ZIP to S3
            download_url = await self._upload_export_zip(
                org_id, loan_id, job_id, zip_buffer.getvalue()
            )

            self._mark_completed(session, job, results={
                "download_url": download_url,
                "zip_size_bytes": len(zip_buffer.getvalue()),
                "files_included": len(downloaded_files),
                "failed": job.failed_items,
            })
            session.commit()

        except Exception as e:
            logger.exception("batch_bulk_export_fatal job_id=%s", job_id)
            try:
                job = session.query(BatchJob).filter(BatchJob.id == job_id).first()
                if job and not job.is_terminal:
                    self._mark_failed(session, job, str(e))
                    session.commit()
            except Exception as e2:
                logger.exception("batch_bulk_export_fatal_cleanup job_id=%s: %s", job_id, e2)
        finally:
            session.close()

    def _sort_by_stacking_order(self, doc_list: List[Dict]) -> List[Dict]:
        """Sort documents by the investor stacking order."""

        def stacking_key(doc: Dict) -> int:
            doc_type = (doc.get("doc_type") or "OTHER").upper()
            try:
                return INVESTOR_STACKING_ORDER.index(doc_type)
            except ValueError:
                return len(INVESTOR_STACKING_ORDER)  # Unknown types go last

        return sorted(doc_list, key=stacking_key)

    def _build_export_manifest(
        self,
        loan_id: int,
        files: List[Tuple[str, bytes, str]],
    ) -> str:
        """Build a plain-text manifest for the export ZIP."""
        lines = [
            f"Loan File Export - Loan ID: {loan_id}",
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Total Documents: {len(files)}",
            "",
            "Stacking Order:",
            "-" * 60,
        ]
        for idx, (export_name, file_bytes, doc_type) in enumerate(files, 1):
            size_kb = len(file_bytes) / 1024
            lines.append(f"  {idx:3d}. [{doc_type or 'UNKNOWN':25s}] {export_name} ({size_kb:.1f} KB)")

        lines.append("-" * 60)
        return "\n".join(lines)

    async def _upload_export_zip(
        self,
        org_id: int,
        loan_id: int,
        job_id: int,
        zip_bytes: bytes,
    ) -> Optional[str]:
        """Upload the export ZIP to S3 and return a presigned download URL."""
        try:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
            s3 = get_smart_docs_s3_service()

            storage_key = f"org-{org_id}/smart-docs/exports/loan_{loan_id}/batch_{job_id}.zip"
            s3.upload_file(
                file_content=zip_bytes,
                storage_key=storage_key,
                content_type="application/zip",
                metadata={
                    "org_id": str(org_id),
                    "loan_id": str(loan_id),
                    "batch_job_id": str(job_id),
                    "export_type": "loan_file_package",
                },
            )

            # Generate a presigned URL valid for 24 hours
            url = s3.generate_presigned_url(storage_key, expires_in=86400)
            return url

        except Exception as e:
            logger.exception("export_zip_upload_failed job_id=%s: %s", job_id, e)
            return None

    # ------------------------------------------------------------------
    # BULK REMINDER
    # ------------------------------------------------------------------

    async def start_bulk_reminder(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        loan_id: int,
        reminder_message: Optional[str] = None,
    ) -> BatchJob:
        """
        Send reminders for all outstanding document requests on a loan.

        Queries smart_document_requests with status=OPEN for the given loan,
        then sends notification for each via the Smart Docs notification service.

        Returns the created BatchJob.
        """
        open_requests = db.execute(
            text(
                "SELECT id, doc_type, title, borrower_id, due_date "
                "FROM smart_document_requests "
                "WHERE loan_id = :loan_id AND status = 'OPEN' AND is_active = true "
                "ORDER BY priority DESC, due_date ASC NULLS LAST"
            ),
            {"loan_id": loan_id},
        ).fetchall()

        if not open_requests:
            raise BatchOperationError(
                "No outstanding document requests found for this loan.",
                code="NO_ITEMS",
            )

        request_data = [
            {
                "request_id": row[0],
                "doc_type": row[1],
                "title": row[2],
                "borrower_id": row[3],
                "due_date": row[4].isoformat() if row[4] else None,
            }
            for row in open_requests
        ]

        job = self._create_job(
            db=db,
            org_id=org_id,
            user_id=user_id,
            job_type=BatchJobType.BULK_REMINDER,
            total_items=len(request_data),
            input_params={
                "loan_id": loan_id,
                "reminder_message": reminder_message,
                "request_count": len(request_data),
            },
        )
        db.commit()

        asyncio.ensure_future(
            self._run_bulk_reminder(job.id, org_id, loan_id, request_data, reminder_message)
        )
        return job

    async def _run_bulk_reminder(
        self,
        job_id: int,
        org_id: int,
        loan_id: int,
        request_data: List[Dict],
        reminder_message: Optional[str],
    ) -> None:
        """Background coroutine that sends reminders for each open request."""
        from db import SessionLocal

        session = SessionLocal()
        try:
            job = session.query(BatchJob).filter(BatchJob.id == job_id).first()
            if job is None:
                return

            self._mark_running(session, job)
            session.commit()

            for idx, req_info in enumerate(request_data):
                if self._is_cancelled(session, job_id, org_id):
                    break

                try:
                    sent = await self._send_single_reminder(
                        session, org_id, loan_id, req_info, reminder_message,
                    )
                    if sent:
                        job.processed_items = (job.processed_items or 0) + 1
                    else:
                        job.skipped_items = (job.skipped_items or 0) + 1
                except Exception as e:
                    logger.exception(
                        "batch_reminder_item_error job_id=%s request_id=%s",
                        job_id, req_info["request_id"],
                    )
                    job.failed_items = (job.failed_items or 0) + 1
                    self._append_item_error(job, idx, req_info["title"], str(e))

                if ITEM_RATE_LIMIT_SECONDS > 0:
                    await asyncio.sleep(ITEM_RATE_LIMIT_SECONDS)

                if (idx + 1) % 10 == 0:
                    self._flush_progress(session, job)
                    session.commit()

            if self._is_cancelled(session, job_id, org_id):
                job.status = BatchJobStatus.CANCELLED.value
                job.completed_at = datetime.now(timezone.utc)
            else:
                self._mark_completed(session, job, results={
                    "reminders_sent": job.processed_items,
                    "skipped": job.skipped_items,
                    "failed": job.failed_items,
                })
            session.commit()

        except Exception as e:
            logger.exception("batch_bulk_reminder_fatal job_id=%s", job_id)
            try:
                job = session.query(BatchJob).filter(BatchJob.id == job_id).first()
                if job and not job.is_terminal:
                    self._mark_failed(session, job, str(e))
                    session.commit()
            except Exception as e2:
                logger.exception("batch_bulk_reminder_fatal_cleanup job_id=%s: %s", job_id, e2)
        finally:
            session.close()

    async def _send_single_reminder(
        self,
        db: Session,
        org_id: int,
        loan_id: int,
        req_info: Dict,
        custom_message: Optional[str],
    ) -> bool:
        """Send a reminder notification for a single document request."""
        borrower_id = req_info.get("borrower_id")
        if not borrower_id:
            logger.warning(
                "batch_reminder_skip_no_borrower request_id=%s",
                req_info["request_id"],
            )
            return False

        # Look up borrower email
        borrower_row = db.execute(
            text(
                "SELECT email, first_name, last_name "
                "FROM borrower_profiles "
                "WHERE id = :borrower_id"
            ),
            {"borrower_id": borrower_id},
        ).fetchone()

        if not borrower_row or not borrower_row[0]:
            logger.warning(
                "batch_reminder_skip_no_email borrower_id=%s request_id=%s",
                borrower_id, req_info["request_id"],
            )
            return False

        borrower_email = borrower_row[0]
        borrower_name = f"{borrower_row[1] or ''} {borrower_row[2] or ''}".strip() or "Borrower"

        try:
            from services.smart_docs.notification_service import SmartDocsNotificationService
            from models.smart_docs_models import DocumentRequest

            doc_request = db.query(DocumentRequest).filter(
                DocumentRequest.id == req_info["request_id"]
            ).first()

            if doc_request is None:
                return False

            notifier = SmartDocsNotificationService(db)
            return notifier.send_document_request_notification(
                request=doc_request,
                borrower_email=borrower_email,
                borrower_name=borrower_name,
            )

        except Exception as e:
            logger.exception("reminder_send_error request_id=%s: %s", req_info["request_id"], e)
            raise

    # ------------------------------------------------------------------
    # STACKING ORDER
    # ------------------------------------------------------------------

    async def start_stacking_order(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        loan_id: int,
        custom_order: Optional[List[str]] = None,
    ) -> BatchJob:
        """
        Organize all loan documents in investor-required stacking order.

        Generates a merged PDF (or ordered manifest) with documents arranged
        per the standard investor stacking order or a custom order if provided.

        Returns the created BatchJob.
        """
        docs = db.execute(
            text(
                "SELECT id, file_name, doc_type, storage_key, mime_type, file_size "
                "FROM smart_documents "
                "WHERE loan_id = :loan_id "
                "  AND status NOT IN ('DELETED', 'REJECTED', 'SUPERSEDED') "
                "ORDER BY uploaded_at ASC"
            ),
            {"loan_id": loan_id},
        ).fetchall()

        if not docs:
            raise BatchOperationError(
                "No documents found for this loan.",
                code="NO_ITEMS",
            )

        doc_list = [
            {
                "id": row[0],
                "file_name": row[1],
                "doc_type": row[2],
                "storage_key": row[3],
                "mime_type": row[4],
                "file_size": row[5],
            }
            for row in docs
        ]

        stacking_order = custom_order or INVESTOR_STACKING_ORDER

        job = self._create_job(
            db=db,
            org_id=org_id,
            user_id=user_id,
            job_type=BatchJobType.STACKING_ORDER,
            total_items=len(doc_list),
            input_params={
                "loan_id": loan_id,
                "document_count": len(doc_list),
                "stacking_order": stacking_order,
            },
        )
        db.commit()

        asyncio.ensure_future(
            self._run_stacking_order(job.id, org_id, loan_id, doc_list, stacking_order)
        )
        return job

    async def _run_stacking_order(
        self,
        job_id: int,
        org_id: int,
        loan_id: int,
        doc_list: List[Dict],
        stacking_order: List[str],
    ) -> None:
        """Background coroutine that builds the stacking-ordered package."""
        from db import SessionLocal

        session = SessionLocal()
        try:
            job = session.query(BatchJob).filter(BatchJob.id == job_id).first()
            if job is None:
                return

            self._mark_running(session, job)
            session.commit()

            # Sort documents by stacking order
            sorted_docs = self._apply_stacking_order(doc_list, stacking_order)

            # Download all PDFs and attempt to merge
            pdf_pages: List[Tuple[str, bytes]] = []
            semaphore = asyncio.Semaphore(ASYNC_CONCURRENCY_LIMIT)

            for idx, doc in enumerate(sorted_docs):
                if self._is_cancelled(session, job_id, org_id):
                    break

                try:
                    async with semaphore:
                        file_bytes = await self._fetch_file_from_storage(doc["storage_key"])

                    if file_bytes:
                        pdf_pages.append((doc["file_name"], file_bytes))
                        job.processed_items = (job.processed_items or 0) + 1
                    else:
                        job.failed_items = (job.failed_items or 0) + 1
                        self._append_item_error(
                            job, idx, doc["file_name"],
                            f"Could not retrieve file: {doc['storage_key']}",
                        )
                except Exception as e:
                    logger.exception("stacking_order_item_error job_id=%s doc_id=%s", job_id, doc["id"])
                    job.failed_items = (job.failed_items or 0) + 1
                    self._append_item_error(job, idx, doc["file_name"], str(e))

                if ITEM_RATE_LIMIT_SECONDS > 0:
                    await asyncio.sleep(ITEM_RATE_LIMIT_SECONDS)

                if (idx + 1) % 10 == 0:
                    self._flush_progress(session, job)
                    session.commit()

            if self._is_cancelled(session, job_id, org_id):
                job.status = BatchJobStatus.CANCELLED.value
                job.completed_at = datetime.now(timezone.utc)
                session.commit()
                return

            # Attempt PDF merge for all PDF files
            merged_url = None
            try:
                merged_url = await self._merge_and_upload_pdfs(
                    org_id, loan_id, job_id, pdf_pages,
                )
            except Exception as e:
                logger.warning(
                    "stacking_order_merge_failed job_id=%s (will provide manifest only): %s",
                    job_id, e,
                )

            # Build stacking order manifest
            manifest = []
            for position, doc in enumerate(sorted_docs, 1):
                manifest.append({
                    "position": position,
                    "doc_type": doc.get("doc_type"),
                    "file_name": doc["file_name"],
                    "doc_id": doc["id"],
                    "file_size": doc.get("file_size"),
                })

            self._mark_completed(session, job, results={
                "merged_pdf_url": merged_url,
                "stacking_manifest": manifest,
                "total_documents": len(sorted_docs),
                "failed": job.failed_items,
            })
            session.commit()

        except Exception as e:
            logger.exception("batch_stacking_order_fatal job_id=%s", job_id)
            try:
                job = session.query(BatchJob).filter(BatchJob.id == job_id).first()
                if job and not job.is_terminal:
                    self._mark_failed(session, job, str(e))
                    session.commit()
            except Exception as e2:
                logger.exception("batch_stacking_order_fatal_cleanup job_id=%s: %s", job_id, e2)
        finally:
            session.close()

    def _apply_stacking_order(
        self,
        doc_list: List[Dict],
        stacking_order: List[str],
    ) -> List[Dict]:
        """
        Sort docs by the given stacking order.
        Documents with unknown types are placed at the end.
        Within the same type, maintain original upload order.
        """
        order_map = {dtype.upper(): idx for idx, dtype in enumerate(stacking_order)}
        max_pos = len(stacking_order)

        def sort_key(doc: Dict) -> Tuple[int, int]:
            doc_type = (doc.get("doc_type") or "OTHER").upper()
            position = order_map.get(doc_type, max_pos)
            return (position, doc["id"])  # Stable sort by id within same type

        return sorted(doc_list, key=sort_key)

    async def _merge_and_upload_pdfs(
        self,
        org_id: int,
        loan_id: int,
        job_id: int,
        pdf_pages: List[Tuple[str, bytes]],
    ) -> Optional[str]:
        """
        Merge PDF files into a single document and upload to S3.
        Non-PDF files are skipped. Returns presigned download URL.
        """
        try:
            from services.smart_docs.pdf_generation_service import get_pdf_generation_service
            pdf_service = get_pdf_generation_service()

            # Filter to PDF files only
            pdf_files = [
                (name, data) for name, data in pdf_pages
                if name.lower().endswith(".pdf")
            ]

            if not pdf_files:
                return None

            merged_result = pdf_service.merge_documents(
                documents=[(name, data) for name, data in pdf_files],
                add_cover_page=True,
                cover_title=f"Loan File - Loan ID {loan_id}",
            )

            if not merged_result or not hasattr(merged_result, "pdf_bytes") or not merged_result.pdf_bytes:
                return None

            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
            s3 = get_smart_docs_s3_service()

            storage_key = (
                f"org-{org_id}/smart-docs/stacking-orders/"
                f"loan_{loan_id}/batch_{job_id}_stacked.pdf"
            )
            s3.upload_file(
                file_content=merged_result.pdf_bytes,
                storage_key=storage_key,
                content_type="application/pdf",
                metadata={
                    "org_id": str(org_id),
                    "loan_id": str(loan_id),
                    "batch_job_id": str(job_id),
                    "type": "stacking_order_merged",
                },
            )

            return s3.generate_presigned_url(storage_key, expires_in=86400)

        except Exception as e:
            logger.exception("merge_pdfs_failed job_id=%s: %s", job_id, e)
            raise

    # ------------------------------------------------------------------
    # Job history / audit
    # ------------------------------------------------------------------

    def get_job_history(
        self,
        db: Session,
        org_id: int,
        loan_id: Optional[int] = None,
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Get batch job history for an org, optionally filtered by loan_id.
        Returns completed/failed/cancelled jobs within the given time window.
        """
        query = (
            db.query(BatchJob)
            .filter(
                BatchJob.organization_id == org_id,
                BatchJob.status.in_([
                    BatchJobStatus.COMPLETED.value,
                    BatchJobStatus.FAILED.value,
                    BatchJobStatus.CANCELLED.value,
                ]),
                BatchJob.created_at >= text("CURRENT_TIMESTAMP - INTERVAL '" + str(int(days)) + " days'"),
            )
        )

        if loan_id is not None:
            # Filter on input_params->loan_id using PostgreSQL JSON operator
            query = query.filter(
                text("input_params->>'loan_id' = :loan_id_str"),
            ).params(loan_id_str=str(loan_id))

        jobs = (
            query.order_by(BatchJob.created_at.desc())
            .limit(limit)
            .all()
        )

        return [j.to_dict() for j in jobs]


# =============================================================================
# SINGLETON
# =============================================================================

_service_instance: Optional[BatchOperationsService] = None


def get_batch_operations_service() -> BatchOperationsService:
    """Get or create the singleton BatchOperationsService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = BatchOperationsService()
    return _service_instance
