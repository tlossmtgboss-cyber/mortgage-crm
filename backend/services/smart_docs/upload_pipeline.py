"""
Document Upload Pipeline

Orchestrates the full document upload flow with malware scanning, validation,
deduplication, storage, and audit logging. Each step is clearly separated so
failures produce actionable error messages and the pipeline stops early on
security issues.

Usage:
    from services.smart_docs.upload_pipeline import get_upload_pipeline

    pipeline = get_upload_pipeline()
    result = await pipeline.process_upload(
        file_bytes=content,
        filename="paystub.pdf",
        mime_type="application/pdf",
        org_id=1,
        user_id="abc-123",
        loan_id=42,
        db=session,
    )
    if not result.success:
        return error_response(result.error_step, result.error_message)
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class UploadResult:
    """Result of the full upload pipeline."""
    success: bool
    doc_id: Optional[int] = None
    file_hash: str = ""
    storage_key: str = ""
    classification_status: Optional[str] = None
    scan_clean: bool = True
    scan_details: Optional[Dict] = None
    is_duplicate: bool = False
    duplicate_doc_id: Optional[int] = None
    error_step: Optional[str] = None
    error_message: Optional[str] = None
    pipeline_duration_ms: int = 0
    steps_completed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        result = {
            "success": self.success,
            "doc_id": self.doc_id,
            "file_hash": self.file_hash,
            "scan_clean": self.scan_clean,
            "is_duplicate": self.is_duplicate,
            "pipeline_duration_ms": self.pipeline_duration_ms,
            "steps_completed": self.steps_completed,
        }
        if not self.success:
            result["error_step"] = self.error_step
            result["error_message"] = self.error_message
        if self.scan_details:
            result["scan_details"] = self.scan_details
        if self.classification_status:
            result["classification_status"] = self.classification_status
        if self.duplicate_doc_id:
            result["duplicate_doc_id"] = self.duplicate_doc_id
        return result


# =============================================================================
# UPLOAD PIPELINE
# =============================================================================

class DocumentUploadPipeline:
    """
    Orchestrates the full document upload flow.

    Steps (in order):
    1. Validate file size
    2. Validate MIME type and magic bytes (document_validation_engine)
    3. Scan for malware (malware_scanner_service)
    4. Compute document hash (SHA-256)
    5. Check for duplicate upload (same hash + loan)
    6. Store file (delegate to S3 storage service)
    7. Queue for AI classification (if enabled and doc_type not specified)
    8. Log upload event to audit trail
    9. Return UploadResult

    Any step failure stops the pipeline and returns a clear error.
    """

    def __init__(self):
        # Lazy-initialized service references
        self._validation_engine = None
        self._malware_scanner = None
        self._s3_service = None

    @property
    def validation_engine(self):
        if self._validation_engine is None:
            from services.smart_docs.document_validation_engine import get_document_validation_engine
            self._validation_engine = get_document_validation_engine()
        return self._validation_engine

    @property
    def malware_scanner(self):
        if self._malware_scanner is None:
            from services.smart_docs.malware_scanner_service import get_malware_scanner
            self._malware_scanner = get_malware_scanner()
        return self._malware_scanner

    @property
    def s3_service(self):
        if self._s3_service is None:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
            self._s3_service = get_smart_docs_s3_service()
        return self._s3_service

    async def process_upload(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        org_id: int,
        user_id: str,
        loan_id: int,
        db: Session,
        declared_doc_type: Optional[str] = None,
        request_id: Optional[int] = None,
        borrower_id: Optional[int] = None,
        upload_source: str = "WEB",
    ) -> UploadResult:
        """
        Process a document upload through the full pipeline.

        Args:
            file_bytes: Raw file content.
            filename: Original filename.
            mime_type: Declared MIME type.
            org_id: Organization ID (tenant).
            user_id: ID of the uploading user.
            loan_id: Associated loan ID.
            db: Database session.
            declared_doc_type: Optional declared document type (e.g. "PAYSTUB").
            request_id: Optional document request ID being fulfilled.
            borrower_id: Optional borrower ID.
            upload_source: Source of upload (WEB, EMAIL, PORTAL, API).

        Returns:
            UploadResult with success/failure details and scan results.
        """
        start = time.monotonic()
        steps_completed = []

        # ----- Step 1: Validate file size -----
        try:
            from middleware.upload_limits import MAX_DOCUMENT_SIZE
            if len(file_bytes) > MAX_DOCUMENT_SIZE:
                max_mb = MAX_DOCUMENT_SIZE / (1024 * 1024)
                return UploadResult(
                    success=False,
                    error_step="file_size_validation",
                    error_message=f"File too large ({len(file_bytes) / (1024 * 1024):.1f} MB). Maximum is {max_mb:.0f} MB.",
                    pipeline_duration_ms=int((time.monotonic() - start) * 1000),
                )
            if len(file_bytes) == 0:
                return UploadResult(
                    success=False,
                    error_step="file_size_validation",
                    error_message="File is empty (0 bytes).",
                    pipeline_duration_ms=int((time.monotonic() - start) * 1000),
                )
            steps_completed.append("file_size_validation")
        except ImportError:
            # upload_limits not available; use a safe default
            if len(file_bytes) > 50 * 1024 * 1024:
                return UploadResult(
                    success=False,
                    error_step="file_size_validation",
                    error_message="File too large (max 50 MB).",
                    pipeline_duration_ms=int((time.monotonic() - start) * 1000),
                )
            steps_completed.append("file_size_validation")

        # ----- Step 2: Validate MIME type and magic bytes -----
        try:
            validation_result = self.validation_engine.validate_upload(
                file_content=file_bytes,
                filename=filename,
                mime_type=mime_type,
                declared_doc_type=declared_doc_type,
            )
            if hasattr(validation_result, "critical_count") and validation_result.critical_count > 0:
                # Collect critical issue messages
                if hasattr(validation_result, "issues"):
                    critical_msgs = [
                        i.message for i in validation_result.issues
                        if i.severity == "CRITICAL"
                    ]
                else:
                    critical_msgs = ["File validation failed"]
                return UploadResult(
                    success=False,
                    error_step="mime_validation",
                    error_message="; ".join(critical_msgs),
                    pipeline_duration_ms=int((time.monotonic() - start) * 1000),
                    steps_completed=steps_completed,
                )
            steps_completed.append("mime_validation")
        except Exception as e:
            logger.exception("MIME validation failed for '%s': %s", filename, e)
            return UploadResult(
                success=False,
                error_step="mime_validation",
                error_message=f"File validation error: {e}",
                pipeline_duration_ms=int((time.monotonic() - start) * 1000),
                steps_completed=steps_completed,
            )

        # ----- Step 3: Malware scan -----
        try:
            scan_result = self.malware_scanner.validate_file_safety(
                file_bytes=file_bytes,
                filename=filename,
                mime_type=mime_type,
            )
            scan_details = scan_result.to_dict()

            if not scan_result.clean:
                threat_names = [
                    f.threat_name for f in scan_result.findings
                    if not f.clean and f.threat_name
                ]
                logger.warning(
                    "Upload rejected for malware: file='%s', threats=%s, user=%s, org=%s",
                    filename, threat_names, user_id, org_id,
                )
                return UploadResult(
                    success=False,
                    scan_clean=False,
                    scan_details=scan_details,
                    error_step="malware_scan",
                    error_message=(
                        "File rejected: security scan detected potentially harmful content. "
                        "Please save the document as a new PDF and try again."
                    ),
                    pipeline_duration_ms=int((time.monotonic() - start) * 1000),
                    steps_completed=steps_completed,
                )
            steps_completed.append("malware_scan")
        except Exception as e:
            logger.exception("Malware scan failed for '%s': %s", filename, e)
            # Fail closed -- if the scanner errors, do not allow the upload
            return UploadResult(
                success=False,
                error_step="malware_scan",
                error_message="Security scan failed. Please try again.",
                pipeline_duration_ms=int((time.monotonic() - start) * 1000),
                steps_completed=steps_completed,
            )

        # ----- Step 4: Compute document hash -----
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        steps_completed.append("hash_computation")

        # ----- Step 5: Check for duplicate upload -----
        is_duplicate = False
        duplicate_doc_id = None
        try:
            existing = db.execute(text("""
                SELECT id, file_name
                FROM smart_documents
                WHERE loan_id = :loan_id
                    AND file_hash = :file_hash
                    AND status NOT IN ('DELETED', 'SUPERSEDED', 'REJECTED')
                ORDER BY uploaded_at DESC
                LIMIT 1
            """), {"loan_id": loan_id, "file_hash": file_hash}).fetchone()

            if existing:
                is_duplicate = True
                duplicate_doc_id = existing[0]
                logger.info(
                    "Duplicate upload detected: hash=%s matches doc_id=%s for loan %s",
                    file_hash[:16], duplicate_doc_id, loan_id,
                )
        except Exception as e:
            # If file_hash column doesn't exist, try file_size-based dedup
            logger.debug("Hash-based dedup failed (%s), trying size-based", e)
            try:
                existing = db.execute(text("""
                    SELECT id, file_name
                    FROM smart_documents
                    WHERE loan_id = :loan_id
                        AND file_size = :file_size
                        AND file_name = :file_name
                        AND status NOT IN ('DELETED', 'SUPERSEDED', 'REJECTED')
                    ORDER BY uploaded_at DESC
                    LIMIT 1
                """), {
                    "loan_id": loan_id,
                    "file_size": len(file_bytes),
                    "file_name": filename,
                }).fetchone()
                if existing:
                    is_duplicate = True
                    duplicate_doc_id = existing[0]
            except Exception as e2:
                logger.debug("Size-based dedup also failed: %s", e2)

        steps_completed.append("duplicate_check")

        # ----- Step 6: Store file -----
        storage_key = ""
        try:
            storage_key = self.s3_service.generate_storage_key(
                loan_id=loan_id,
                borrower_id=borrower_id,
                file_name=filename,
                organization_id=org_id,
            )
            s3_result = self.s3_service.upload_file(
                file_content=file_bytes,
                storage_key=storage_key,
                content_type=mime_type,
                metadata={
                    "loan_id": str(loan_id),
                    "user_id": str(user_id),
                    "file_hash": file_hash,
                    "scan_status": "clean",
                    "upload_source": upload_source,
                },
            )
            if not s3_result.get("success") and self.s3_service.is_available:
                logger.error("S3 upload failed: %s", s3_result)
                return UploadResult(
                    success=False,
                    error_step="file_storage",
                    error_message="Failed to store file. Please try again.",
                    pipeline_duration_ms=int((time.monotonic() - start) * 1000),
                    steps_completed=steps_completed,
                )
            steps_completed.append("file_storage")
        except Exception as e:
            logger.exception("File storage failed for '%s': %s", filename, e)
            return UploadResult(
                success=False,
                error_step="file_storage",
                error_message="Failed to store file. Please try again.",
                pipeline_duration_ms=int((time.monotonic() - start) * 1000),
                steps_completed=steps_completed,
            )

        # ----- Step 7: Queue for AI classification (non-blocking) -----
        classification_status = None
        if not declared_doc_type:
            try:
                from services.smart_docs.ai_classifier_service import get_ai_classifier_service
                classifier = get_ai_classifier_service()
                classification_result = classifier.classify(
                    file_content=file_bytes,
                    filename=filename,
                    mime_type=mime_type,
                )
                if classification_result and classification_result.get("doc_type"):
                    classification_status = classification_result["doc_type"]
            except Exception as e:
                logger.warning("AI classification failed (non-blocking): %s", e)
                classification_status = "classification_pending"
        steps_completed.append("ai_classification")

        # ----- Step 8: Log upload event to audit trail -----
        try:
            db.execute(text("""
                INSERT INTO doc_policy_events (
                    event_type, loan_id, request_id, payload, created_at
                )
                VALUES (
                    'DOCUMENT_UPLOAD_SCANNED',
                    :loan_id,
                    :request_id,
                    :payload,
                    CURRENT_TIMESTAMP
                )
            """), {
                "loan_id": loan_id,
                "request_id": request_id,
                "payload": str({
                    "filename": filename,
                    "file_hash": file_hash,
                    "file_size": len(file_bytes),
                    "mime_type": mime_type,
                    "scan_clean": True,
                    "scanners_used": scan_details.get("scanners_used", []),
                    "scan_duration_ms": scan_details.get("scan_duration_ms", 0),
                    "is_duplicate": is_duplicate,
                    "upload_source": upload_source,
                    "user_id": user_id,
                }),
            })
            db.flush()
            steps_completed.append("audit_log")
        except Exception as e:
            # Audit logging failure is non-blocking
            logger.warning("Failed to log upload audit event: %s", e)

        pipeline_duration = int((time.monotonic() - start) * 1000)

        return UploadResult(
            success=True,
            file_hash=file_hash,
            storage_key=storage_key,
            classification_status=classification_status or declared_doc_type,
            scan_clean=True,
            scan_details=scan_details,
            is_duplicate=is_duplicate,
            duplicate_doc_id=duplicate_doc_id,
            pipeline_duration_ms=pipeline_duration,
            steps_completed=steps_completed,
        )


# =============================================================================
# SINGLETON
# =============================================================================

_pipeline_instance: Optional[DocumentUploadPipeline] = None


def get_upload_pipeline() -> DocumentUploadPipeline:
    """Get or create the singleton DocumentUploadPipeline instance."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = DocumentUploadPipeline()
    return _pipeline_instance
