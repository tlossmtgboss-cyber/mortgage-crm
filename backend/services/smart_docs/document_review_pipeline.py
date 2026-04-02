"""
Smart Document Collection - Document Review Pipeline

Orchestrates the complete document processing workflow:
1. Upload & initial validation
2. Screenshot detection
3. Date extraction
4. Freshness validation
5. Decision making (accept/reject/needs_review)
6. Request status update

This is the main entry point for document processing.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from sqlalchemy.orm import Session

from models.smart_docs_models import (
    DocumentRequest, SmartDocument, DocPolicyEvent,
    DocType, RequestStatus, DocumentDecision, RejectionCategory,
    DocPolicyEventType, PayrollFrequency
)
from services.smart_docs.screenshot_detector import ScreenshotDetector, ScreenshotDetectionResult
from services.smart_docs.date_extractor import DateExtractor, DateExtractionResult
from services.smart_docs.freshness_validator import FreshnessValidator, FreshnessResult, FreshnessStatus
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

logger = logging.getLogger(__name__)


class ProcessingStatus(str, Enum):
    """Document processing status."""
    UPLOADED = "UPLOADED"
    SCANNING = "SCANNING"
    PROCESSING = "PROCESSING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    EXPIRED = "EXPIRED"
    ERROR = "ERROR"


@dataclass
class ProcessingResult:
    """Result of document processing pipeline."""
    document_id: int
    status: ProcessingStatus
    decision: Optional[DocumentDecision]
    rejection_category: Optional[RejectionCategory]
    rejection_reason: Optional[str]
    fix_instructions: Optional[str]
    screenshot_result: Optional[Dict]
    date_result: Optional[Dict]
    freshness_result: Optional[Dict]


class DocumentReviewPipeline:
    """
    Main pipeline for processing uploaded documents.

    Coordinates multiple analysis services to make accept/reject decisions.
    """

    def __init__(self, db: Session):
        self.db = db
        self.screenshot_detector = ScreenshotDetector()
        self.date_extractor = DateExtractor()
        self.freshness_validator = FreshnessValidator()

    def process_document(
        self,
        document_id: int,
        file_content: bytes,
        mime_type: str,
        filename: str,
        doc_type: Optional[DocType] = None,
        request_id: Optional[int] = None,
    ) -> ProcessingResult:
        """
        Process a single document through the full pipeline.

        Args:
            document_id: ID of the SmartDocument record
            file_content: Raw file bytes
            mime_type: MIME type of the file
            filename: Original filename
            doc_type: Optional document type hint
            request_id: Optional associated request ID

        Returns:
            ProcessingResult with decision and analysis details
        """
        logger.info(f"Starting document processing for document {document_id}")

        # Get the document record
        document = self.db.query(SmartDocument).filter(
            SmartDocument.id == document_id
        ).first()

        if not document:
            logger.error(f"Document {document_id} not found")
            return ProcessingResult(
                document_id=document_id,
                status=ProcessingStatus.ERROR,
                decision=None,
                rejection_category=None,
                rejection_reason="Document record not found",
                fix_instructions=None,
                screenshot_result=None,
                date_result=None,
                freshness_result=None,
            )

        # Update status to processing
        document.status = ProcessingStatus.SCANNING.value
        self.db.commit()

        try:
            # Step 1: Screenshot Detection
            screenshot_result = self._run_screenshot_detection(
                file_content, mime_type, filename
            )

            # Update document with screenshot results
            document.detected_is_screenshot = screenshot_result.is_screenshot
            document.screenshot_confidence = screenshot_result.confidence
            document.screenshot_reasons = self.screenshot_detector.result_to_dict(screenshot_result)

            # If screenshot detected with high confidence, reject early
            if screenshot_result.recommendation == "reject":
                reason, instructions = self._get_screenshot_rejection_message(doc_type)
                return self._reject_document(
                    document=document,
                    category=RejectionCategory.SCREENSHOT,
                    reason=f"{reason} (confidence: {screenshot_result.confidence:.1%})",
                    fix_instructions=instructions,
                    screenshot_result=screenshot_result,
                )

            # Update status
            document.status = ProcessingStatus.PROCESSING.value
            self.db.commit()

            # Step 2: Date Extraction
            date_result = self._run_date_extraction(
                file_content, mime_type, doc_type
            )

            # Update document with extraction results
            if date_result.primary_date:
                document.doc_date = datetime.combine(
                    date_result.primary_date, datetime.min.time()
                )
            document.extracted_dates = date_result.extracted_data
            document.extraction_confidence = date_result.confidence
            document.ocr_text = date_result.ocr_text[:10000] if date_result.ocr_text else None

            # Step 3: Freshness Validation
            freshness_result = None
            if doc_type and date_result.primary_date:
                freshness_result = self._run_freshness_validation(
                    doc_type, date_result.primary_date, request_id
                )

                # Update document with freshness results
                if freshness_result.expires_at:
                    document.doc_expires_at = datetime.combine(
                        freshness_result.expires_at, datetime.min.time()
                    )
                document.is_expired = not freshness_result.is_valid
                document.days_until_expiration = freshness_result.days_until_expiration

                # If document is expired, reject
                if freshness_result.status == FreshnessStatus.EXPIRED:
                    reason, instructions = self._get_freshness_rejection_message(doc_type)
                    return self._reject_document(
                        document=document,
                        category=RejectionCategory.EXPIRED,
                        reason=f"{reason} - dated {freshness_result.doc_date}",
                        fix_instructions=instructions,
                        screenshot_result=screenshot_result,
                        date_result=date_result,
                        freshness_result=freshness_result,
                    )

            # Step 4: Make Final Decision
            decision, result = self._make_decision(
                document=document,
                screenshot_result=screenshot_result,
                date_result=date_result,
                freshness_result=freshness_result,
            )

            # Update document with final decision
            document.decision = decision
            document.reviewed_at = datetime.now(timezone.utc)
            document.reviewed_by = "SYSTEM"

            if decision == DocumentDecision.ACCEPT:
                document.status = ProcessingStatus.APPROVED.value
                self._update_request_status(request_id, RequestStatus.PENDING_REVIEW)
            elif decision == DocumentDecision.REJECT:
                document.status = ProcessingStatus.REJECTED.value
            else:
                document.status = ProcessingStatus.NEEDS_REVIEW.value
                self._update_request_status(request_id, RequestStatus.PENDING_REVIEW)

            self.db.commit()

            # Log event
            self._log_event(
                loan_id=document.loan_id,
                request_id=request_id,
                document_id=document_id,
                event_type=DocPolicyEventType.DOCUMENT_UPLOADED,
                payload={
                    "decision": decision.value if decision else None,
                    "status": document.status,
                    "is_screenshot": screenshot_result.is_screenshot,
                    "is_expired": document.is_expired,
                },
            )

            logger.info(
                f"Document {document_id} processed: decision={decision.value if decision else 'none'}, "
                f"status={document.status}"
            )

            return result

        except Exception as e:
            logger.exception(f"Error processing document {document_id}: {e}")
            document.status = ProcessingStatus.ERROR.value
            self.db.commit()

            return ProcessingResult(
                document_id=document_id,
                status=ProcessingStatus.ERROR,
                decision=None,
                rejection_category=None,
                rejection_reason=f"Processing error: {str(e)}",
                fix_instructions="Please try uploading the document again. If the problem persists, contact support.",
                screenshot_result=None,
                date_result=None,
                freshness_result=None,
            )

    def _run_screenshot_detection(
        self,
        file_content: bytes,
        mime_type: str,
        filename: str,
    ) -> ScreenshotDetectionResult:
        """Run screenshot detection analysis."""
        try:
            return self.screenshot_detector.detect(
                file_content=file_content,
                mime_type=mime_type,
                filename=filename,
            )
        except Exception as e:
            logger.warning(f"Screenshot detection failed: {e}")
            # Return safe default
            from services.smart_docs.screenshot_detector import DetectionLayer, LayerResult
            return ScreenshotDetectionResult(
                is_screenshot=False,
                confidence=0.0,
                reasons=["Detection unavailable"],
                layer_results=[],
                recommendation="needs_review",
            )

    def _run_date_extraction(
        self,
        file_content: bytes,
        mime_type: str,
        doc_type: Optional[DocType],
    ) -> DateExtractionResult:
        """Run date extraction analysis."""
        try:
            return self.date_extractor.extract(
                file_content=file_content,
                mime_type=mime_type,
                doc_type=doc_type.value if doc_type else None,
            )
        except Exception as e:
            logger.warning(f"Date extraction failed: {e}")
            return DateExtractionResult(
                primary_date=None,
                primary_date_type=None,
                all_dates=[],
                confidence=0.0,
                ocr_text="",
                extracted_data={},
            )

    def _run_freshness_validation(
        self,
        doc_type: DocType,
        doc_date,
        request_id: Optional[int],
    ) -> FreshnessResult:
        """Run freshness validation."""
        # Get custom freshness days from request if available
        freshness_days = None
        if request_id:
            request = self.db.query(DocumentRequest).filter(
                DocumentRequest.id == request_id
            ).first()
            if request:
                freshness_days = request.freshness_days

        return self.freshness_validator.validate(
            doc_type=doc_type,
            doc_date=doc_date,
            freshness_days=freshness_days,
        )

    def _make_decision(
        self,
        document: SmartDocument,
        screenshot_result: ScreenshotDetectionResult,
        date_result: DateExtractionResult,
        freshness_result: Optional[FreshnessResult],
    ) -> Tuple[DocumentDecision, ProcessingResult]:
        """Make final accept/reject/review decision."""

        # Check for screenshot concern (not rejected, but suspicious)
        if screenshot_result.recommendation == "needs_review":
            return DocumentDecision.NEEDS_REVIEW, ProcessingResult(
                document_id=document.id,
                status=ProcessingStatus.NEEDS_REVIEW,
                decision=DocumentDecision.NEEDS_REVIEW,
                rejection_category=None,
                rejection_reason=None,
                fix_instructions=None,
                screenshot_result=self.screenshot_detector.result_to_dict(screenshot_result),
                date_result=self.date_extractor.result_to_dict(date_result),
                freshness_result=self.freshness_validator.result_to_dict(freshness_result) if freshness_result else None,
            )

        # Check for date extraction issues
        if date_result.confidence < 0.5:
            return DocumentDecision.NEEDS_REVIEW, ProcessingResult(
                document_id=document.id,
                status=ProcessingStatus.NEEDS_REVIEW,
                decision=DocumentDecision.NEEDS_REVIEW,
                rejection_category=None,
                rejection_reason=None,
                fix_instructions=None,
                screenshot_result=self.screenshot_detector.result_to_dict(screenshot_result),
                date_result=self.date_extractor.result_to_dict(date_result),
                freshness_result=self.freshness_validator.result_to_dict(freshness_result) if freshness_result else None,
            )

        # Check for expiring soon
        if freshness_result and freshness_result.status == FreshnessStatus.EXPIRING_SOON:
            # Accept but note the warning
            return DocumentDecision.ACCEPT, ProcessingResult(
                document_id=document.id,
                status=ProcessingStatus.APPROVED,
                decision=DocumentDecision.ACCEPT,
                rejection_category=None,
                rejection_reason=None,
                fix_instructions=None,
                screenshot_result=self.screenshot_detector.result_to_dict(screenshot_result),
                date_result=self.date_extractor.result_to_dict(date_result),
                freshness_result=self.freshness_validator.result_to_dict(freshness_result),
            )

        # All checks passed - accept
        return DocumentDecision.ACCEPT, ProcessingResult(
            document_id=document.id,
            status=ProcessingStatus.APPROVED,
            decision=DocumentDecision.ACCEPT,
            rejection_category=None,
            rejection_reason=None,
            fix_instructions=None,
            screenshot_result=self.screenshot_detector.result_to_dict(screenshot_result),
            date_result=self.date_extractor.result_to_dict(date_result),
            freshness_result=self.freshness_validator.result_to_dict(freshness_result) if freshness_result else None,
        )

    def _reject_document(
        self,
        document: SmartDocument,
        category: RejectionCategory,
        reason: str,
        fix_instructions: str,
        screenshot_result: Optional[ScreenshotDetectionResult] = None,
        date_result: Optional[DateExtractionResult] = None,
        freshness_result: Optional[FreshnessResult] = None,
    ) -> ProcessingResult:
        """Reject a document and update records."""
        document.decision = DocumentDecision.REJECT
        document.rejection_category = category
        document.rejection_reason = reason
        document.fix_instructions = fix_instructions
        document.status = ProcessingStatus.REJECTED.value
        document.reviewed_at = datetime.now(timezone.utc)
        document.reviewed_by = "SYSTEM"
        self.db.commit()

        # Log rejection event
        event_type = {
            RejectionCategory.SCREENSHOT: DocPolicyEventType.SCREENSHOT_REJECTED,
            RejectionCategory.EXPIRED: DocPolicyEventType.FRESHNESS_REJECTED,
        }.get(category, DocPolicyEventType.DOCUMENT_UPLOADED)

        self._log_event(
            loan_id=document.loan_id,
            request_id=document.request_id,
            document_id=document.id,
            event_type=event_type,
            payload={
                "category": category.value,
                "reason": reason,
            },
        )

        return ProcessingResult(
            document_id=document.id,
            status=ProcessingStatus.REJECTED,
            decision=DocumentDecision.REJECT,
            rejection_category=category,
            rejection_reason=reason,
            fix_instructions=fix_instructions,
            screenshot_result=self.screenshot_detector.result_to_dict(screenshot_result) if screenshot_result else None,
            date_result=self.date_extractor.result_to_dict(date_result) if date_result else None,
            freshness_result=self.freshness_validator.result_to_dict(freshness_result) if freshness_result else None,
        )

    def _update_request_status(
        self,
        request_id: Optional[int],
        status: RequestStatus,
    ) -> None:
        """Update the associated document request status."""
        if not request_id:
            return

        request = self.db.query(DocumentRequest).filter(
            DocumentRequest.id == request_id
        ).first()

        if request:
            request.status = status
            request.updated_at = datetime.now(timezone.utc)

    def _log_event(
        self,
        loan_id: int,
        request_id: Optional[int],
        document_id: int,
        event_type: DocPolicyEventType,
        payload: Dict,
    ) -> None:
        """Log a policy event."""
        event = DocPolicyEvent(
            loan_id=loan_id,
            request_id=request_id,
            document_id=document_id,
            event_type=event_type,
            payload=payload,
        )
        self.db.add(event)
        self.db.commit()

    def _get_screenshot_rejection_message(
        self, doc_type: Optional[DocType]
    ) -> Tuple[str, str]:
        """Get document-specific screenshot rejection message."""
        messages = {
            DocType.BANK_STATEMENT: (
                "This appears to be a screenshot of a bank statement",
                "We need the actual bank statement PDF downloaded from your bank's "
                "website or mobile app. Screenshots cannot be accepted.",
            ),
            DocType.PAYSTUB: (
                "This appears to be a screenshot of a pay stub",
                "We need the actual pay stub PDF from your employer's payroll portal. "
                "Screenshots cannot be accepted.",
            ),
            DocType.W2: (
                "This appears to be a screenshot of a W-2",
                "We need the actual W-2 PDF from your employer or the IRS. "
                "Screenshots cannot be accepted.",
            ),
            DocType.TAX_RETURN: (
                "This appears to be a screenshot of a tax return",
                "We need the actual tax return PDF from your tax software or CPA. "
                "Screenshots cannot be accepted.",
            ),
            DocType.INVESTMENT_STATEMENT: (
                "This appears to be a screenshot of an investment statement",
                "We need the actual statement PDF from your brokerage. "
                "Screenshots cannot be accepted.",
            ),
        }
        default = (
            "This appears to be a screenshot",
            "Please upload the original PDF document, not a screenshot. "
            "Screenshots cannot be accepted.",
        )
        return messages.get(doc_type, default)

    def _get_freshness_rejection_message(
        self, doc_type: DocType
    ) -> Tuple[str, str]:
        """Get document-specific freshness rejection message."""
        messages = {
            DocType.PAYSTUB: (
                "This pay stub is expired",
                "Pay stubs must be dated within the last 30 days. "
                "Please upload your most recent pay stub.",
            ),
            DocType.BANK_STATEMENT: (
                "This bank statement is expired",
                "Bank statements must be dated within the last 60 days. "
                "Please upload a more recent statement from your bank.",
            ),
            DocType.INVESTMENT_STATEMENT: (
                "This investment statement is expired",
                "Investment statements must be dated within the last 90 days. "
                "Please upload a more recent statement.",
            ),
        }
        default = (
            "This document is expired",
            "Please upload a more recent version of this document.",
        )
        return messages.get(doc_type, default)

    def _get_freshness_fix_instructions(self, doc_type: DocType) -> str:
        """Get fix instructions for freshness rejection."""
        instructions = {
            DocType.PAYSTUB: (
                "Please upload your most recent pay stub dated within the last 30 days."
            ),
            DocType.BANK_STATEMENT: (
                "Please upload a bank statement dated within the last 60 days. "
                "The statement must show a complete statement period."
            ),
            DocType.INVESTMENT_STATEMENT: (
                "Please upload an investment statement dated within the last 90 days."
            ),
            DocType.PROFIT_LOSS: (
                "Please upload a current year-to-date profit and loss statement."
            ),
        }
        return instructions.get(
            doc_type,
            "Please upload a more recent version of this document.",
        )

    def reprocess_document(self, document_id: int) -> ProcessingResult:
        """
        Reprocess a document that was previously processed.

        Retrieves the file from S3 storage and runs it through the pipeline again.
        Useful when fixing issues or updating detection logic.

        Args:
            document_id: ID of the SmartDocument to reprocess

        Returns:
            ProcessingResult with updated decision and analysis

        Raises:
            ValueError: If document not found
            RuntimeError: If file cannot be retrieved from storage
        """
        document = self.db.query(SmartDocument).filter(
            SmartDocument.id == document_id
        ).first()

        if not document:
            raise ValueError(f"Document {document_id} not found")

        # Check if we have a storage key
        if not document.storage_key:
            raise RuntimeError(
                f"Document {document_id} has no storage_key - cannot retrieve file content"
            )

        # Get the S3 service and download the file
        s3_service = get_smart_docs_s3_service()

        if not s3_service.is_available:
            raise RuntimeError(
                "S3 storage is not available - cannot retrieve file for reprocessing"
            )

        logger.info(f"Retrieving document {document_id} from S3: {document.storage_key}")

        download_result = s3_service.download_file(document.storage_key)

        if not download_result.get("success"):
            error = download_result.get("error", "Unknown error")
            if download_result.get("not_found"):
                raise RuntimeError(
                    f"Document file not found in storage: {document.storage_key}"
                )
            raise RuntimeError(f"Failed to retrieve document from storage: {error}")

        file_content = download_result["content"]
        mime_type = download_result.get("content_type", document.mime_type or "application/octet-stream")

        # Reset document state for reprocessing
        document.decision = None
        document.rejection_category = None
        document.rejection_reason = None
        document.fix_instructions = None
        document.detected_is_screenshot = None
        document.screenshot_confidence = None
        document.screenshot_reasons = None
        document.doc_date = None
        document.extracted_dates = None
        document.extraction_confidence = None
        document.is_expired = None
        document.days_until_expiration = None
        document.status = ProcessingStatus.UPLOADED.value
        self.db.commit()

        logger.info(f"Reprocessing document {document_id} ({len(file_content)} bytes)")

        # Run through the full processing pipeline
        return self.process_document(
            document_id=document_id,
            file_content=file_content,
            mime_type=mime_type,
            filename=document.file_name or document.original_filename or "document",
            doc_type=document.doc_type,
            request_id=document.request_id,
        )

    def manual_review(
        self,
        document_id: int,
        decision: str,
        reviewer: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record a manual review decision.

        Args:
            document_id: Document ID to review
            decision: "accept" or "reject"
            reviewer: ID of the reviewer
            notes: Optional reviewer notes

        Returns:
            Updated document details
        """
        document = self.db.query(SmartDocument).filter(
            SmartDocument.id == document_id
        ).first()

        if not document:
            raise ValueError(f"Document {document_id} not found")

        decision_lower = decision.lower()
        decision_enum = DocumentDecision.ACCEPT if decision_lower == "accept" else DocumentDecision.REJECT
        document.decision = decision_enum
        document.reviewed_at = datetime.now(timezone.utc)
        document.reviewed_by = reviewer

        if decision_lower == "accept":
            document.status = ProcessingStatus.APPROVED.value
            if document.request_id:
                self._update_request_status(document.request_id, RequestStatus.ACCEPTED)
        else:
            document.status = ProcessingStatus.REJECTED.value
            document.rejection_reason = notes

        self.db.commit()

        logger.info(f"Manual review: document {document_id} {decision}ed by {reviewer}")

        return {
            "document_id": document_id,
            "decision": decision,
            "reviewer": reviewer,
            "reviewed_at": document.reviewed_at.isoformat(),
        }

    def result_to_dict(self, result: ProcessingResult) -> Dict[str, Any]:
        """Convert processing result to dictionary."""
        return {
            "document_id": result.document_id,
            "status": result.status.value,
            "decision": result.decision.value if result.decision else None,
            "rejection_category": result.rejection_category.value if result.rejection_category else None,
            "rejection_reason": result.rejection_reason,
            "fix_instructions": result.fix_instructions,
            "analysis": {
                "screenshot": result.screenshot_result,
                "dates": result.date_result,
                "freshness": result.freshness_result,
            },
        }
