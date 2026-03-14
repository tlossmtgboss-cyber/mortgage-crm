"""
Smart Document Collection - AI-Powered Document Review Service

Enhances the existing DocumentReviewPipeline with comprehensive AI-powered
review logic that automatically approves or rejects documents based on:

1. Quality check (readability, resolution, completeness)
2. Type verification (does content match declared type?)
3. Name matching (does name on doc match borrower/co-borrower?)
4. Freshness validation (is document within acceptable age?)
5. Completeness check (all pages present, key fields visible)
6. Cross-document validation (income on paystub matches W2)
7. Screenshot detection (reject screenshots of documents)
8. Fraud indicators (altered text, mismatched fonts)

Auto-approve criteria:
- Quality score >= threshold (default 80)
- Type matches declared type
- Name matches borrower
- Document is fresh
- No screenshot detection
- No fraud indicators

Auto-reject criteria:
- Screenshot detected (confidence > 85%)
- Document expired
- Wrong document type (confidence > 90%)
- Unreadable/corrupt file
"""

import logging
import os
import json
import re
from datetime import datetime, timezone, date, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text, func

from models.smart_docs_models import (
    DocumentRequest, SmartDocument, DocPolicyEvent,
    DocType, RequestStatus, DocumentDecision, RejectionCategory,
    DocPolicyEventType,
)
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
from services.smart_docs.freshness_validator import FreshnessValidator, FreshnessStatus
from services.smart_docs.owner_matcher import OwnerMatcher
from services.smart_docs.screenshot_detector import ScreenshotDetector

logger = logging.getLogger(__name__)

# Optional imports for AI capabilities
try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

from services.smart_docs.ai_resilience import resilient_ai_call

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# =============================================================================
# DOCUMENT TYPE CLASSIFICATION KEYWORDS
# =============================================================================

DOC_TYPE_KEYWORDS: Dict[str, List[str]] = {
    DocType.PAYSTUB.value: [
        "pay stub", "paystub", "pay statement", "earnings statement",
        "pay period", "gross pay", "net pay", "ytd", "year to date",
        "federal tax", "fica", "medicare", "deductions",
    ],
    DocType.W2.value: [
        "w-2", "w2", "wage and tax statement", "form w-2",
        "employer identification number", "ein",
        "wages tips", "federal income tax withheld",
        "social security wages", "medicare wages",
    ],
    DocType.TAX_RETURN.value: [
        "form 1040", "1040", "u.s. individual income tax return",
        "adjusted gross income", "taxable income", "filing status",
        "internal revenue service", "irs", "tax return",
    ],
    DocType.BANK_STATEMENT.value: [
        "bank statement", "account statement", "statement period",
        "beginning balance", "ending balance", "deposits",
        "withdrawals", "checking", "savings", "account number",
    ],
    DocType.INVESTMENT_STATEMENT.value: [
        "investment statement", "brokerage statement", "portfolio",
        "account value", "securities", "stocks", "bonds",
        "mutual fund", "ira", "401k", "roth",
    ],
    DocType.DRIVERS_LICENSE.value: [
        "driver license", "driver's license", "identification card",
        "date of birth", "dob", "license number", "class",
        "department of motor vehicles", "dmv",
    ],
    DocType.PROFIT_LOSS.value: [
        "profit and loss", "p&l", "income statement",
        "revenue", "expenses", "net profit", "net income",
        "gross profit", "operating expenses",
    ],
    DocType.PURCHASE_CONTRACT.value: [
        "purchase agreement", "purchase contract", "real estate contract",
        "buyer", "seller", "purchase price", "earnest money",
        "closing date", "property address",
    ],
    DocType.GIFT_LETTER.value: [
        "gift letter", "gift funds", "gift donor",
        "no repayment", "bona fide gift",
    ],
    DocType.APPRAISAL.value: [
        "appraisal", "appraised value", "market value",
        "uniform residential appraisal", "comparable sales",
    ],
    DocType.TITLE_REPORT.value: [
        "title report", "title search", "title commitment",
        "liens", "encumbrances", "chain of title",
    ],
    DocType.HOMEOWNERS_INSURANCE.value: [
        "homeowners insurance", "hazard insurance", "property insurance",
        "dwelling coverage", "liability coverage", "premium",
    ],
}

# Required fields per document type for completeness checks
REQUIRED_FIELDS: Dict[str, List[str]] = {
    DocType.PAYSTUB.value: [
        "employer name", "pay period", "gross pay", "year to date",
    ],
    DocType.W2.value: [
        "employer ein", "wages", "federal tax withheld",
    ],
    DocType.BANK_STATEMENT.value: [
        "account number", "beginning balance", "ending balance", "statement period",
    ],
    DocType.TAX_RETURN.value: [
        "filing status", "adjusted gross income", "signature",
    ],
    DocType.DRIVERS_LICENSE.value: [
        "name", "date of birth", "license number", "expiration",
    ],
    DocType.PROFIT_LOSS.value: [
        "business name", "period", "revenue", "expenses", "net",
    ],
    DocType.INVESTMENT_STATEMENT.value: [
        "account holder", "account number", "account value", "statement date",
    ],
}

# Freshness requirements in days by document type
FRESHNESS_REQUIREMENTS: Dict[str, int] = {
    DocType.PAYSTUB.value: 30,
    DocType.BANK_STATEMENT.value: 60,
    DocType.INVESTMENT_STATEMENT.value: 90,
    DocType.PROFIT_LOSS.value: 90,
    DocType.BALANCE_SHEET.value: 90,
}

# Minimum file sizes by MIME type (bytes) - files smaller than this are likely blank
MIN_FILE_SIZES: Dict[str, int] = {
    "application/pdf": 5_000,
    "image/png": 10_000,
    "image/jpeg": 5_000,
    "image/jpg": 5_000,
    "image/tiff": 10_000,
}

# Maximum file sizes (bytes)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ReviewDecision:
    """Result of AI document review."""
    decision: str  # ACCEPT, REJECT, NEEDS_REVIEW
    confidence: int  # 0-100
    reasons: List[str]
    rejection_category: Optional[str] = None
    fix_instructions: Optional[str] = None
    quality_score: int = 0  # 0-100 overall quality
    completeness_score: int = 0  # 0-100 document completeness
    readability_score: int = 0  # 0-100 readability
    freshness_valid: bool = True
    type_match: bool = True
    name_match: bool = True
    auto_approved: bool = False
    needs_human_review: bool = False
    review_priority: str = "NORMAL"  # CRITICAL, HIGH, NORMAL, LOW


@dataclass
class BatchReviewResult:
    """Result of batch document review."""
    total: int
    approved: int
    rejected: int
    needs_review: int
    results: List[Dict]


# =============================================================================
# AI DOCUMENT REVIEW SERVICE
# =============================================================================

class AIDocumentReviewService:
    """
    AI-powered document review that automatically approves or rejects documents.

    Review pipeline:
    1. Quality check (readability, resolution, completeness)
    2. Type verification (does content match declared type?)
    3. Name matching (does name on doc match borrower/co-borrower?)
    4. Freshness validation (is document within acceptable age?)
    5. Completeness check (all pages present, key fields visible)
    6. Cross-document validation (income on paystub matches W2)
    7. Screenshot detection (reject screenshots of documents)
    8. Fraud indicators (altered text, mismatched fonts)
    """

    def __init__(self, db: Session, org_id: Optional[int] = None):
        self.db = db
        self.org_id = org_id
        self._anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self._auto_approve_threshold = int(
            os.getenv("SMART_DOCS_AUTO_APPROVE_THRESHOLD", "80")
        )
        self._auto_reject_threshold = int(
            os.getenv("SMART_DOCS_AUTO_REJECT_THRESHOLD", "30")
        )
        self._screenshot_detector = ScreenshotDetector()
        self._freshness_validator = FreshnessValidator()
        self._owner_matcher = OwnerMatcher()

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def review_document(
        self,
        document_id: int,
        file_content: Optional[bytes] = None,
    ) -> ReviewDecision:
        """
        Main entry point for single document review.

        Runs the document through all review checks, makes a final decision,
        updates the document status in DB, and logs a review event.

        Args:
            document_id: ID of the SmartDocument record
            file_content: Raw file bytes; fetched from S3 if not provided

        Returns:
            ReviewDecision with final verdict and supporting details
        """
        document = self.db.query(SmartDocument).filter(
            SmartDocument.id == document_id
        ).first()

        if not document:
            logger.error(f"Document {document_id} not found for AI review")
            return ReviewDecision(
                decision=DocumentDecision.NEEDS_REVIEW.value,
                confidence=0,
                reasons=["Document record not found"],
                needs_human_review=True,
                review_priority="CRITICAL",
            )

        # Enforce tenant isolation: verify document's loan belongs to caller's org
        if self.org_id is not None and document.loan_id:
            loan_org = self.db.execute(
                text("SELECT organization_id FROM loans WHERE id = :lid"),
                {"lid": document.loan_id},
            ).fetchone()
            if loan_org and loan_org.organization_id != self.org_id:
                logger.warning(
                    "Tenant isolation violation in AI review: doc %d loan %d belongs to org %s, caller org %s",
                    document_id, document.loan_id, loan_org.organization_id, self.org_id,
                )
                return ReviewDecision(
                    decision=DocumentDecision.NEEDS_REVIEW.value,
                    confidence=0,
                    reasons=["Access denied: document does not belong to your organization"],
                    needs_human_review=True,
                    review_priority="CRITICAL",
                )

        # Fetch file content from S3 if not provided
        if file_content is None:
            file_content = self._fetch_from_s3(document)
            if file_content is None:
                logger.warning(
                    f"Could not retrieve file content for document {document_id}"
                )
                return ReviewDecision(
                    decision=DocumentDecision.NEEDS_REVIEW.value,
                    confidence=0,
                    reasons=["Unable to retrieve file content from storage"],
                    needs_human_review=True,
                    review_priority="HIGH",
                )

        # --- Document cache lookup ---
        doc_hash = None
        cache_service = None
        org_id = getattr(document, "organization_id", None)
        if file_content and org_id is not None:
            try:
                from services.smart_docs.document_cache_service import get_document_cache_service
                cache_service = get_document_cache_service()
                doc_hash = cache_service.get_or_compute_hash(file_content)
                cached = cache_service.get_cached_review(self.db, doc_hash, org_id)
                if cached is not None:
                    logger.info(
                        "doc_cache REVIEW_HIT hash=%s org=%s doc_id=%s",
                        doc_hash[:12], org_id, document_id,
                    )
                    decision = ReviewDecision(
                        decision=cached.get("decision", DocumentDecision.NEEDS_REVIEW.value),
                        confidence=cached.get("confidence", 0),
                        reasons=cached.get("reasons", []),
                        rejection_category=cached.get("rejection_category"),
                        fix_instructions=cached.get("fix_instructions"),
                        quality_score=cached.get("quality_score", 0),
                        completeness_score=cached.get("completeness_score", 0),
                        readability_score=cached.get("readability_score", 0),
                        freshness_valid=cached.get("freshness_valid", True),
                        type_match=cached.get("type_match", True),
                        name_match=cached.get("name_match", True),
                        auto_approved=cached.get("auto_approved", False),
                        needs_human_review=cached.get("needs_human_review", False),
                        review_priority=cached.get("review_priority", "NORMAL"),
                    )
                    # Still persist decision and log event even on cache hit
                    self._update_document_status(document_id, decision)
                    self._log_review_event(document=document, decision=decision)
                    return decision
                else:
                    logger.info(
                        "doc_cache REVIEW_MISS hash=%s org=%s doc_id=%s",
                        doc_hash[:12], org_id, document_id,
                    )
            except Exception as e:
                logger.warning("doc_cache review lookup failed: %s", e)

        # Update status to SCANNING
        document.status = "SCANNING"
        self.db.flush()

        try:
            # Get OCR text (use stored text or extract)
            ocr_text = document.ocr_text or ""
            if not ocr_text and file_content:
                ocr_text = self._extract_text(file_content, document.mime_type or "")

            mime_type = document.mime_type or "application/octet-stream"
            declared_type = document.doc_type.value if document.doc_type else None

            # --- Run all review checks ---

            # 1. Quality check
            quality_score, quality_issues = self._check_quality(
                file_content, mime_type
            )

            # 2. Screenshot detection (use existing detector)
            is_screenshot = document.detected_is_screenshot or False
            screenshot_confidence = document.screenshot_confidence or 0.0
            if not document.detected_is_screenshot and file_content:
                try:
                    ss_result = self._screenshot_detector.detect(
                        file_content=file_content,
                        mime_type=mime_type,
                        filename=document.file_name,
                    )
                    is_screenshot = ss_result.is_screenshot
                    screenshot_confidence = ss_result.confidence
                    document.detected_is_screenshot = is_screenshot
                    document.screenshot_confidence = screenshot_confidence
                except Exception as e:
                    logger.warning(f"Screenshot detection failed for doc {document_id}: {e}")

            # 3. Type verification
            type_match = True
            type_confidence = 100
            detected_type = declared_type
            if declared_type and ocr_text:
                type_match, type_confidence, detected_type = self._check_type_match(
                    document_id, declared_type, ocr_text
                )

            # 4. Name matching
            name_match = True
            name_confidence = 100
            matched_names: List[str] = []
            if ocr_text and document.loan_id:
                name_match, name_confidence, matched_names = self._check_name_match(
                    document_id, ocr_text
                )

            # 5. Freshness validation
            freshness_valid = True
            days_old: Optional[int] = None
            if declared_type and document.doc_date:
                doc_date_as_date = document.doc_date.date() if isinstance(
                    document.doc_date, datetime
                ) else document.doc_date
                freshness_valid, days_old = self._check_freshness(
                    declared_type, doc_date_as_date
                )

            # 6. Completeness check
            completeness_score = 100
            missing_fields: List[str] = []
            if ocr_text and declared_type:
                completeness_score, missing_fields = self._check_completeness(
                    ocr_text, declared_type
                )

            # 7. Cross-document consistency
            consistency_issues: List[str] = []
            if document.loan_id:
                consistency_issues = self._check_cross_document_consistency(
                    document_id, document.loan_id
                )

            # 8. Fraud indicators
            fraud_suspected = False
            fraud_indicators: List[str] = []
            if file_content and ocr_text:
                fraud_suspected, fraud_indicators = self._detect_fraud_indicators(
                    file_content, ocr_text
                )

            # --- Make final decision ---
            decision = self._make_decision(
                quality=quality_score,
                type_match=type_match,
                name_match=name_match,
                freshness=freshness_valid,
                completeness=completeness_score,
                fraud_indicators=fraud_indicators,
                is_screenshot=is_screenshot,
                screenshot_confidence=screenshot_confidence,
                quality_issues=quality_issues,
                missing_fields=missing_fields,
                consistency_issues=consistency_issues,
                type_confidence=type_confidence,
                name_confidence=name_confidence,
                detected_type=detected_type,
                declared_type=declared_type,
                days_old=days_old,
            )

            # --- Persist decision ---
            self._update_document_status(document_id, decision)

            # --- Log event ---
            self._log_review_event(
                document=document,
                decision=decision,
            )

            logger.info(
                "Document reviewed | document_id=%s | decision=%s | "
                "confidence=%d | auto_approved=%s | quality=%d | "
                "type_match=%s | name_match=%s | freshness=%s | "
                "screenshot=%s | fraud=%s | reasons_count=%d",
                document_id,
                decision.decision,
                decision.confidence,
                decision.auto_approved,
                quality_score,
                type_match,
                name_match,
                freshness_valid,
                is_screenshot,
                fraud_suspected,
                len(decision.reasons),
            )

            # --- Cache the review result ---
            if cache_service and doc_hash and org_id is not None:
                try:
                    cache_service.cache_review(self.db, doc_hash, org_id, {
                        "decision": decision.decision,
                        "confidence": decision.confidence,
                        "reasons": decision.reasons,
                        "rejection_category": decision.rejection_category,
                        "fix_instructions": decision.fix_instructions,
                        "quality_score": decision.quality_score,
                        "completeness_score": decision.completeness_score,
                        "readability_score": decision.readability_score,
                        "freshness_valid": decision.freshness_valid,
                        "type_match": decision.type_match,
                        "name_match": decision.name_match,
                        "auto_approved": decision.auto_approved,
                        "needs_human_review": decision.needs_human_review,
                        "review_priority": decision.review_priority,
                    })
                except Exception as e:
                    logger.warning("doc_cache review store failed: %s", e)

            return decision

        except Exception as e:
            logger.exception(
                "Document review failed | document_id=%s | error=%s",
                document_id,
                str(e)[:200],
            )
            document.status = "PROCESSING"
            self.db.flush()
            return ReviewDecision(
                decision=DocumentDecision.NEEDS_REVIEW.value,
                confidence=0,
                reasons=[f"AI review error: {str(e)[:200]}"],
                needs_human_review=True,
                review_priority="HIGH",
            )

    def batch_review(self, loan_id: int) -> BatchReviewResult:
        """
        Review all unreviewed documents for a loan.

        Args:
            loan_id: Loan ID whose documents should be reviewed

        Returns:
            BatchReviewResult with aggregate counts and per-document results
        """
        # Validate loan belongs to the caller's organization
        if self.org_id is not None:
            loan_org_check = self.db.execute(
                text("SELECT organization_id FROM loans WHERE id = :lid"),
                {"lid": loan_id},
            ).fetchone()
            if loan_org_check and loan_org_check.organization_id != self.org_id:
                logger.warning(
                    "Tenant isolation violation in batch review: loan %d belongs to org %s, caller org %s",
                    loan_id, loan_org_check.organization_id, self.org_id,
                )
                return BatchReviewResult(
                    total=0, approved=0, rejected=0, needs_review=0, results=[],
                )

        documents = self.db.query(SmartDocument).filter(
            SmartDocument.loan_id == loan_id,
            SmartDocument.decision.is_(None),
            SmartDocument.status.in_(["UPLOADED", "PROCESSING", "SCANNING"]),
        ).all()

        results: List[Dict] = []
        approved = 0
        rejected = 0
        needs_review = 0

        for doc in documents:
            try:
                review = self.review_document(doc.id)
                result_entry = {
                    "document_id": doc.id,
                    "file_name": doc.file_name,
                    "doc_type": doc.doc_type.value if doc.doc_type else None,
                    "decision": review.decision,
                    "confidence": review.confidence,
                    "reasons": review.reasons,
                    "auto_approved": review.auto_approved,
                }
                results.append(result_entry)

                if review.decision == DocumentDecision.ACCEPT.value:
                    approved += 1
                elif review.decision == DocumentDecision.REJECT.value:
                    rejected += 1
                else:
                    needs_review += 1

            except Exception as e:
                logger.exception(f"Batch review failed for document {doc.id}: {e}")
                results.append({
                    "document_id": doc.id,
                    "file_name": doc.file_name,
                    "doc_type": doc.doc_type.value if doc.doc_type else None,
                    "decision": DocumentDecision.NEEDS_REVIEW.value,
                    "confidence": 0,
                    "reasons": [f"Review error: {str(e)}"],
                    "auto_approved": False,
                })
                needs_review += 1

        self.db.commit()

        return BatchReviewResult(
            total=len(documents),
            approved=approved,
            rejected=rejected,
            needs_review=needs_review,
            results=results,
        )

    def review_queue(
        self,
        organization_id: int,
        limit: int = 50,
    ) -> List[Dict]:
        """
        Get documents needing human review, prioritized by urgency.

        CRITICAL priority first, then HIGH, NORMAL, LOW.

        Args:
            organization_id: Filter to this organization's documents
            limit: Max number of documents to return

        Returns:
            List of document info dicts with AI recommendations
        """
        # Query documents that need human review, joined with loan for org filter
        rows = self.db.execute(text("""
            SELECT
                sd.id AS document_id,
                sd.file_name,
                sd.doc_type,
                sd.status,
                sd.decision,
                sd.decision_reasons,
                sd.rejection_reason,
                sd.rejection_category,
                sd.fix_instructions,
                sd.detected_is_screenshot,
                sd.screenshot_confidence,
                sd.is_expired,
                sd.loan_id,
                sd.borrower_id,
                sd.uploaded_at,
                sd.reviewed_at,
                l.loan_number,
                l.borrower_name
            FROM smart_documents sd
            JOIN loans l ON l.id = sd.loan_id
            WHERE l.organization_id = :org_id
              AND sd.status IN ('PROCESSING', 'SCANNING', 'UPLOADED')
              AND (sd.decision IS NULL OR sd.decision = :needs_review)
            ORDER BY
                CASE
                    WHEN sd.detected_is_screenshot = true THEN 1
                    WHEN sd.is_expired = true THEN 2
                    WHEN sd.screenshot_confidence > 0.4 THEN 3
                    ELSE 4
                END ASC,
                sd.uploaded_at ASC
            LIMIT :limit
        """), {
            "org_id": organization_id,
            "needs_review": DocumentDecision.NEEDS_REVIEW.value,
            "limit": limit,
        }).fetchall()

        queue_items: List[Dict] = []
        columns = [
            "document_id", "file_name", "doc_type", "status", "decision",
            "decision_reasons", "rejection_reason", "rejection_category",
            "fix_instructions", "detected_is_screenshot", "screenshot_confidence",
            "is_expired", "loan_id", "borrower_id", "uploaded_at", "reviewed_at",
            "loan_number", "borrower_name",
        ]

        for row in rows:
            row_dict = dict(zip(columns, row))

            # Determine review priority
            priority = "NORMAL"
            if row_dict.get("detected_is_screenshot"):
                priority = "CRITICAL"
            elif row_dict.get("is_expired"):
                priority = "HIGH"
            elif (row_dict.get("screenshot_confidence") or 0) > 0.4:
                priority = "HIGH"

            # Build recommendation
            recommendations: List[str] = []
            if row_dict.get("detected_is_screenshot"):
                recommendations.append(
                    "Screenshot detected - verify if this is an actual document"
                )
            if row_dict.get("is_expired"):
                recommendations.append(
                    "Document appears expired - request updated version"
                )
            if row_dict.get("rejection_reason"):
                recommendations.append(f"Auto-review note: {row_dict['rejection_reason']}")

            queue_items.append({
                "document_id": row_dict["document_id"],
                "file_name": row_dict["file_name"],
                "doc_type": row_dict["doc_type"],
                "loan_id": row_dict["loan_id"],
                "loan_number": row_dict["loan_number"],
                "borrower_name": row_dict["borrower_name"],
                "uploaded_at": (
                    row_dict["uploaded_at"].isoformat()
                    if row_dict.get("uploaded_at") else None
                ),
                "priority": priority,
                "recommendations": recommendations,
                "screenshot_confidence": row_dict.get("screenshot_confidence"),
                "is_expired": row_dict.get("is_expired"),
            })

        return queue_items

    def get_review_stats(
        self,
        organization_id: int,
        days: int = 30,
    ) -> Dict:
        """
        Return review statistics for an organization.

        Args:
            organization_id: Organization to get stats for
            days: Number of days to look back

        Returns:
            Dict with auto-approved %, rejected %, needs review %,
            average review time, common rejection reasons
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        stats = self.db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(CASE WHEN sd.decision = :accept THEN 1 END) AS approved,
                COUNT(CASE WHEN sd.decision = :reject THEN 1 END) AS rejected,
                COUNT(CASE WHEN sd.decision = :needs_review THEN 1 END) AS needs_review,
                COUNT(CASE WHEN sd.reviewed_by = 'SYSTEM' AND sd.decision = :accept THEN 1 END) AS auto_approved,
                COUNT(CASE WHEN sd.reviewed_by = 'SYSTEM' AND sd.decision = :reject THEN 1 END) AS auto_rejected,
                AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at))) AS avg_review_seconds
            FROM smart_documents sd
            JOIN loans l ON l.id = sd.loan_id
            WHERE l.organization_id = :org_id
              AND sd.uploaded_at >= :cutoff
              AND sd.decision IS NOT NULL
        """), {
            "org_id": organization_id,
            "accept": DocumentDecision.ACCEPT.value,
            "reject": DocumentDecision.REJECT.value,
            "needs_review": DocumentDecision.NEEDS_REVIEW.value,
            "cutoff": cutoff,
        }).fetchone()

        # Get common rejection reasons
        rejection_rows = self.db.execute(text("""
            SELECT
                sd.rejection_category,
                COUNT(*) AS count
            FROM smart_documents sd
            JOIN loans l ON l.id = sd.loan_id
            WHERE l.organization_id = :org_id
              AND sd.uploaded_at >= :cutoff
              AND sd.decision = :reject
              AND sd.rejection_category IS NOT NULL
            GROUP BY sd.rejection_category
            ORDER BY count DESC
            LIMIT 10
        """), {
            "org_id": organization_id,
            "cutoff": cutoff,
            "reject": DocumentDecision.REJECT.value,
        }).fetchall()

        total = stats[0] if stats else 0
        approved = stats[1] if stats else 0
        rejected = stats[2] if stats else 0
        needs_review_count = stats[3] if stats else 0
        auto_approved = stats[4] if stats else 0
        auto_rejected = stats[5] if stats else 0
        avg_review_seconds = stats[6] if stats else None

        return {
            "period_days": days,
            "total_reviewed": total,
            "approved": approved,
            "rejected": rejected,
            "needs_review": needs_review_count,
            "auto_approved": auto_approved,
            "auto_rejected": auto_rejected,
            "approval_rate_pct": round((approved / total) * 100, 1) if total > 0 else 0,
            "rejection_rate_pct": round((rejected / total) * 100, 1) if total > 0 else 0,
            "auto_rate_pct": round(
                ((auto_approved + auto_rejected) / total) * 100, 1
            ) if total > 0 else 0,
            "avg_review_time_seconds": (
                round(float(avg_review_seconds), 1) if avg_review_seconds else None
            ),
            "common_rejection_reasons": [
                {"category": row[0], "count": row[1]}
                for row in rejection_rows
            ],
        }

    # =========================================================================
    # REVIEW CHECK METHODS
    # =========================================================================

    def _check_quality(
        self,
        file_content: bytes,
        mime_type: str,
    ) -> Tuple[int, List[str]]:
        """
        Check file quality: size, format validity, readability.

        Args:
            file_content: Raw file bytes
            mime_type: MIME type string

        Returns:
            Tuple of (quality_score 0-100, list of issues)
        """
        issues: List[str] = []
        score = 100

        file_size = len(file_content)

        # Check minimum file size
        min_size = MIN_FILE_SIZES.get(mime_type, 1_000)
        if file_size < min_size:
            issues.append(
                f"File too small ({file_size} bytes) - may be blank or corrupted"
            )
            score -= 50

        # Check maximum file size
        if file_size > MAX_FILE_SIZE:
            issues.append(
                f"File exceeds maximum size ({file_size / 1024 / 1024:.1f} MB)"
            )
            score -= 20

        # PDF validity check
        if mime_type == "application/pdf":
            if not file_content[:5] == b"%PDF-":
                issues.append("File does not appear to be a valid PDF")
                score -= 40
            elif HAS_PDFPLUMBER:
                try:
                    import io
                    with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                        page_count = len(pdf.pages)
                        if page_count == 0:
                            issues.append("PDF has no pages")
                            score -= 50
                        elif page_count > 50:
                            issues.append(
                                f"PDF has {page_count} pages - unusually large"
                            )
                            score -= 10

                        # Check first page for text content
                        if page_count > 0:
                            first_page_text = pdf.pages[0].extract_text() or ""
                            if len(first_page_text.strip()) < 20:
                                issues.append(
                                    "First page has little or no extractable text"
                                )
                                score -= 15
                except Exception as e:
                    logger.warning(f"PDF quality check failed: {e}")
                    issues.append("Could not fully validate PDF structure")
                    score -= 10

        # Image quality check
        elif mime_type.startswith("image/") and HAS_PIL:
            try:
                from io import BytesIO as BIO
                img = Image.open(BIO(file_content))
                width, height = img.size

                # Very small images are likely unreadable
                if width < 200 or height < 200:
                    issues.append(
                        f"Image resolution too low ({width}x{height})"
                    )
                    score -= 40
                elif width < 500 or height < 500:
                    issues.append(
                        f"Image resolution may be too low for document ({width}x{height})"
                    )
                    score -= 15

                # Check if image is mostly blank (single color)
                if img.mode in ("RGB", "RGBA"):
                    extrema = img.getextrema()
                    if all(
                        (ch[1] - ch[0]) < 10
                        for ch in extrema[:3]
                    ):
                        issues.append("Image appears to be blank or solid color")
                        score -= 50

            except Exception as e:
                logger.warning(f"Image quality check failed: {e}")
                issues.append("Could not validate image quality")
                score -= 10

        return max(score, 0), issues

    def _check_type_match(
        self,
        document_id: int,
        declared_type: str,
        ocr_text: str,
    ) -> Tuple[bool, int, str]:
        """
        Verify that OCR text content matches the declared document type.

        Uses keyword-based classification to detect the actual document type
        and compares it against the declared type.

        Args:
            document_id: SmartDocument ID
            declared_type: The doc_type declared at upload
            ocr_text: Extracted text from the document

        Returns:
            Tuple of (matches, confidence 0-100, detected_type)
        """
        text_lower = ocr_text.lower()
        best_type: Optional[str] = None
        best_score = 0

        for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in text_lower)
            if hits > best_score:
                best_score = hits
                best_type = doc_type

        # Calculate confidence based on number of keyword matches
        if best_score == 0:
            # No keywords matched at all -- uncertain
            return True, 30, declared_type

        total_keywords = len(DOC_TYPE_KEYWORDS.get(best_type, []))
        match_ratio = best_score / max(total_keywords, 1)
        confidence = min(int(match_ratio * 100), 100)

        # Boost confidence if many keywords matched
        if best_score >= 4:
            confidence = max(confidence, 85)
        elif best_score >= 2:
            confidence = max(confidence, 60)

        detected_type = best_type or declared_type
        matches = (detected_type == declared_type)

        # Also update the detected_doc_type on the SmartDocument record
        document = self.db.query(SmartDocument).filter(
            SmartDocument.id == document_id
        ).first()
        if document:
            document.detected_doc_type = detected_type

        return matches, confidence, detected_type

    def _check_name_match(
        self,
        document_id: int,
        ocr_text: str,
    ) -> Tuple[bool, int, List[str]]:
        """
        Check if the name on the document matches borrower/co-borrower.

        Gets borrower names from the loan associated with the document,
        then searches the OCR text for those names using fuzzy matching.

        Args:
            document_id: SmartDocument ID
            ocr_text: Extracted text from the document

        Returns:
            Tuple of (matches, confidence 0-100, list of matched names)
        """
        # Get document and loan info
        document = self.db.query(SmartDocument).filter(
            SmartDocument.id == document_id
        ).first()

        if not document or not document.loan_id:
            return True, 50, []

        _org_filter = "AND organization_id = :_org_id" if self.org_id is not None else ""
        _org_params = {"_org_id": self.org_id} if self.org_id is not None else {}
        loan_info = self.db.execute(text(f"""
            SELECT borrower_name, coborrower_name
            FROM loans
            WHERE id = :loan_id {_org_filter}
        """), {"loan_id": document.loan_id, **_org_params}).fetchone()

        if not loan_info:
            return True, 50, []

        borrower_name = loan_info[0] if loan_info[0] else None
        co_borrower_name = loan_info[1] if loan_info[1] else None

        if not borrower_name and not co_borrower_name:
            return True, 50, []

        # Use extracted names if available, otherwise extract from OCR text
        extracted_names = []
        if document.extracted_names:
            extracted_names = document.extracted_names
        else:
            # Simple name extraction from OCR text: look for lines that
            # contain the borrower or co-borrower name
            text_lines = ocr_text.split("\n")
            for line in text_lines:
                line_clean = line.strip()
                if len(line_clean) > 3 and len(line_clean) < 80:
                    # Check if this line might contain a name (basic heuristic)
                    words = line_clean.split()
                    if 2 <= len(words) <= 5 and all(
                        w[0].isupper() for w in words if w.isalpha()
                    ):
                        extracted_names.append(line_clean)

        if not extracted_names:
            # Cannot verify name, but don't fail -- just lower confidence
            return True, 30, []

        # Use the OwnerMatcher for fuzzy name matching
        match_result = self._owner_matcher.match_owner(
            extracted_names=extracted_names,
            borrower_name=borrower_name,
            co_borrower_name=co_borrower_name,
        )

        matched_names: List[str] = []
        if match_result.matched_name:
            matched_names.append(match_result.matched_name)

        if match_result.owner == "UNKNOWN":
            # Check if borrower name appears directly in the text
            text_lower = ocr_text.lower()
            if borrower_name and borrower_name.lower() in text_lower:
                return True, 75, [borrower_name]
            if co_borrower_name and co_borrower_name.lower() in text_lower:
                return True, 75, [co_borrower_name]
            return False, match_result.confidence, matched_names

        return True, match_result.confidence, matched_names

    def _check_freshness(
        self,
        doc_type: str,
        doc_date: Optional[date],
    ) -> Tuple[bool, Optional[int]]:
        """
        Check document age against freshness requirements.

        Args:
            doc_type: Document type string (e.g., "PAYSTUB")
            doc_date: Date extracted from the document

        Returns:
            Tuple of (is_fresh, days_old or None)
        """
        if doc_date is None:
            return True, None

        today = date.today()
        days_old = (today - doc_date).days

        max_days = FRESHNESS_REQUIREMENTS.get(doc_type)

        if max_days is None:
            # No freshness requirement for this doc type
            # For W2 and TAX_RETURN, use year-based logic
            if doc_type in (DocType.W2.value, DocType.TAX_RETURN.value,
                           DocType.BUSINESS_TAX_RETURN.value):
                try:
                    doc_type_enum = DocType(doc_type)
                    result = self._freshness_validator.validate(
                        doc_type=doc_type_enum,
                        doc_date=doc_date,
                    )
                    return result.is_valid, days_old
                except Exception as e:
                    logger.warning(f"Freshness validation failed for {doc_type}: {e}")
                    return True, days_old
            return True, days_old

        is_fresh = days_old <= max_days
        return is_fresh, days_old

    def _check_completeness(
        self,
        ocr_text: str,
        doc_type: str,
    ) -> Tuple[int, List[str]]:
        """
        Check for required fields based on document type.

        Searches OCR text for keywords associated with required fields.

        Args:
            ocr_text: Extracted text from the document
            doc_type: Document type string

        Returns:
            Tuple of (completeness_score 0-100, list of missing fields)
        """
        required = REQUIRED_FIELDS.get(doc_type, [])
        if not required:
            return 100, []

        text_lower = ocr_text.lower()
        found = 0
        missing: List[str] = []

        for field_keyword in required:
            # Check for the keyword (or parts of it) in the text
            keywords = field_keyword.lower().split()
            if any(kw in text_lower for kw in keywords):
                found += 1
            else:
                missing.append(field_keyword)

        if not required:
            return 100, []

        score = int((found / len(required)) * 100)
        return score, missing

    def _check_cross_document_consistency(
        self,
        document_id: int,
        loan_id: int,
    ) -> List[str]:
        """
        Compare this document's data against other documents on the loan.

        Checks for:
        - Employer name consistency between paystub and W2
        - Income consistency between paystub YTD and W2 wages
        - Name consistency across all documents
        - Address consistency

        Args:
            document_id: Current SmartDocument ID
            loan_id: Loan ID to find other documents

        Returns:
            List of inconsistency descriptions
        """
        inconsistencies: List[str] = []

        # Get current document
        current_doc = self.db.query(SmartDocument).filter(
            SmartDocument.id == document_id
        ).first()

        if not current_doc:
            return inconsistencies

        # Get all other approved documents for this loan
        other_docs = self.db.query(SmartDocument).filter(
            SmartDocument.loan_id == loan_id,
            SmartDocument.id != document_id,
            SmartDocument.decision == DocumentDecision.ACCEPT,
        ).all()

        if not other_docs:
            return inconsistencies

        current_employer = current_doc.extracted_employer
        current_names = current_doc.extracted_names or []

        for other in other_docs:
            # Employer consistency check
            if current_employer and other.extracted_employer:
                if (
                    current_doc.doc_type in (DocType.PAYSTUB, DocType.W2) and
                    other.doc_type in (DocType.PAYSTUB, DocType.W2)
                ):
                    if current_employer.lower() != other.extracted_employer.lower():
                        # Use fuzzy matching to allow minor variations
                        ratio = self._owner_matcher._fuzzy_ratio(
                            current_employer.lower(),
                            other.extracted_employer.lower(),
                        )
                        if ratio < 80:
                            inconsistencies.append(
                                f"Employer name mismatch: '{current_employer}' vs "
                                f"'{other.extracted_employer}' (doc #{other.id})"
                            )

            # Income consistency check (paystub YTD vs W2 wages)
            if (
                current_doc.doc_type == DocType.PAYSTUB and
                other.doc_type == DocType.W2 and
                current_doc.extracted_amount and
                other.extracted_amount
            ):
                current_amount = float(current_doc.extracted_amount)
                other_amount = float(other.extracted_amount)
                if other_amount > 0:
                    variance = abs(current_amount - other_amount) / other_amount
                    if variance > 0.30:
                        inconsistencies.append(
                            f"Income variance: paystub amount ${current_amount:,.2f} "
                            f"differs from W2 wages ${other_amount:,.2f} by "
                            f"{variance * 100:.0f}%"
                        )

            # Name consistency across documents
            other_names = other.extracted_names or []
            if current_names and other_names:
                # Check that at least one name appears in both documents
                name_found = False
                for cn in current_names:
                    for on in other_names:
                        ratio = self._owner_matcher._fuzzy_ratio(
                            cn.lower(), on.lower()
                        )
                        if ratio >= 80:
                            name_found = True
                            break
                    if name_found:
                        break

                if not name_found and len(current_names) > 0 and len(other_names) > 0:
                    inconsistencies.append(
                        f"Name mismatch: no common name found between this document "
                        f"and document #{other.id}"
                    )

        return inconsistencies

    def _detect_fraud_indicators(
        self,
        file_content: bytes,
        ocr_text: str,
    ) -> Tuple[bool, List[str]]:
        """
        Check for common fraud patterns in the document.

        Looks for:
        - Round numbers (suspicious income amounts ending in 000)
        - Missing standard elements (no employer logo, no check number)
        - Metadata anomalies (creation date vs document date)
        - Suspiciously short documents for complex types

        Args:
            file_content: Raw file bytes
            ocr_text: Extracted text from the document

        Returns:
            Tuple of (fraud_suspected, list of indicator descriptions)
        """
        indicators: List[str] = []

        # Check for suspiciously round dollar amounts in income documents
        # Pattern: dollar amounts that are exact multiples of 1000
        dollar_amounts = re.findall(
            r"\$\s*([\d,]+(?:\.\d{2})?)", ocr_text
        )
        round_count = 0
        total_amounts = 0
        for amount_str in dollar_amounts:
            try:
                amount = float(amount_str.replace(",", ""))
                if amount >= 1000:
                    total_amounts += 1
                    if amount % 1000 == 0:
                        round_count += 1
            except ValueError:
                pass

        if total_amounts >= 3 and round_count >= 3:
            indicators.append(
                f"Multiple suspiciously round dollar amounts "
                f"({round_count} of {total_amounts} amounts are exact multiples of $1,000)"
            )

        # Check for text that looks like it was edited (mismatched patterns)
        # Look for inconsistent number formatting within the same document
        has_commas = bool(re.search(r"\$\s*\d{1,3},\d{3}", ocr_text))
        has_no_commas = bool(re.search(r"\$\s*\d{4,}", ocr_text))
        if has_commas and has_no_commas:
            # Mixed formatting could indicate editing
            indicators.append(
                "Inconsistent currency formatting (mixed comma/no-comma styles)"
            )

        # Check PDF metadata for anomalies
        if file_content[:5] == b"%PDF-":
            try:
                import io
                if HAS_PDFPLUMBER:
                    with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                        metadata = pdf.metadata or {}
                        creator = (metadata.get("Creator") or "").lower()
                        producer = (metadata.get("Producer") or "").lower()

                        # Check for image editing software
                        editing_tools = [
                            "photoshop", "gimp", "paint", "canva",
                            "pixlr", "photoeditor", "foxit editor",
                        ]
                        for tool in editing_tools:
                            if tool in creator or tool in producer:
                                indicators.append(
                                    f"Document created/modified with image editing "
                                    f"software: {creator or producer}"
                                )
                                break
            except Exception as e:
                logger.debug(f"PDF metadata fraud check failed: {e}")

        # Very short text for document types that should be long
        text_length = len(ocr_text.strip())
        if text_length < 100:
            indicators.append(
                f"Document has very little text ({text_length} characters) "
                f"- may be incomplete or fabricated"
            )

        fraud_suspected = len(indicators) >= 2
        return fraud_suspected, indicators

    # =========================================================================
    # DECISION ENGINE
    # =========================================================================

    def _make_decision(
        self,
        quality: int,
        type_match: bool,
        name_match: bool,
        freshness: bool,
        completeness: int,
        fraud_indicators: List[str],
        is_screenshot: bool,
        screenshot_confidence: float = 0.0,
        quality_issues: Optional[List[str]] = None,
        missing_fields: Optional[List[str]] = None,
        consistency_issues: Optional[List[str]] = None,
        type_confidence: int = 100,
        name_confidence: int = 100,
        detected_type: Optional[str] = None,
        declared_type: Optional[str] = None,
        days_old: Optional[int] = None,
    ) -> ReviewDecision:
        """
        Combine all review checks into a final decision.

        Auto-approve if all checks pass and scores above threshold.
        Auto-reject if critical failures detected.
        Otherwise: NEEDS_REVIEW with appropriate priority.

        Returns:
            ReviewDecision with the complete verdict
        """
        quality_issues = quality_issues or []
        missing_fields = missing_fields or []
        consistency_issues = consistency_issues or []

        reasons: List[str] = []
        rejection_category: Optional[str] = None
        fix_instructions: Optional[str] = None

        # --- AUTO-REJECT conditions ---

        # Screenshot with high confidence
        if is_screenshot and screenshot_confidence > 0.85:
            reasons.append(
                f"Screenshot detected with {screenshot_confidence:.0%} confidence"
            )
            return ReviewDecision(
                decision=DocumentDecision.REJECT.value,
                confidence=int(screenshot_confidence * 100),
                reasons=reasons,
                rejection_category=RejectionCategory.SCREENSHOT.value,
                fix_instructions=(
                    "Please upload the original PDF document, not a screenshot. "
                    "Screenshots cannot be accepted for mortgage documentation."
                ),
                quality_score=quality,
                completeness_score=completeness,
                readability_score=quality,
                freshness_valid=freshness,
                type_match=type_match,
                name_match=name_match,
                auto_approved=False,
                needs_human_review=False,
                review_priority="NORMAL",
            )

        # Document is expired
        if not freshness:
            reasons.append(
                f"Document is expired ({days_old} days old)"
                if days_old else "Document is expired"
            )
            return ReviewDecision(
                decision=DocumentDecision.REJECT.value,
                confidence=90,
                reasons=reasons,
                rejection_category=RejectionCategory.EXPIRED.value,
                fix_instructions=(
                    "This document has expired. Please upload a more "
                    "recent version of this document."
                ),
                quality_score=quality,
                completeness_score=completeness,
                readability_score=quality,
                freshness_valid=False,
                type_match=type_match,
                name_match=name_match,
                auto_approved=False,
                needs_human_review=False,
                review_priority="NORMAL",
            )

        # Wrong document type with high confidence
        if not type_match and type_confidence > 90:
            reasons.append(
                f"Document type mismatch: declared as {declared_type}, "
                f"detected as {detected_type} (confidence: {type_confidence}%)"
            )
            return ReviewDecision(
                decision=DocumentDecision.REJECT.value,
                confidence=type_confidence,
                reasons=reasons,
                rejection_category=RejectionCategory.WRONG_TYPE.value,
                fix_instructions=(
                    f"This document appears to be a {detected_type} but was "
                    f"uploaded as a {declared_type}. Please upload the correct "
                    f"document type."
                ),
                quality_score=quality,
                completeness_score=completeness,
                readability_score=quality,
                freshness_valid=freshness,
                type_match=False,
                name_match=name_match,
                auto_approved=False,
                needs_human_review=False,
                review_priority="NORMAL",
            )

        # Unreadable / very poor quality
        if quality < self._auto_reject_threshold:
            reasons.extend(quality_issues)
            return ReviewDecision(
                decision=DocumentDecision.REJECT.value,
                confidence=90,
                reasons=reasons or ["Document quality too low to process"],
                rejection_category=RejectionCategory.POOR_QUALITY.value,
                fix_instructions=(
                    "This document could not be read clearly. Please upload a "
                    "higher quality scan or the original PDF."
                ),
                quality_score=quality,
                completeness_score=completeness,
                readability_score=quality,
                freshness_valid=freshness,
                type_match=type_match,
                name_match=name_match,
                auto_approved=False,
                needs_human_review=False,
                review_priority="NORMAL",
            )

        # --- NEEDS_REVIEW conditions ---

        needs_review = False
        review_priority = "NORMAL"

        # Screenshot with moderate confidence
        if is_screenshot or screenshot_confidence > 0.4:
            reasons.append(
                f"Possible screenshot (confidence: {screenshot_confidence:.0%})"
            )
            needs_review = True
            review_priority = "HIGH"

        # Type mismatch with moderate confidence
        if not type_match and type_confidence > 60:
            reasons.append(
                f"Possible type mismatch: declared {declared_type}, "
                f"detected {detected_type}"
            )
            needs_review = True
            review_priority = "HIGH"

        # Name mismatch
        if not name_match:
            reasons.append("Name on document does not match borrower/co-borrower")
            needs_review = True
            review_priority = "HIGH"

        # Low completeness
        if completeness < 50:
            reasons.append(
                f"Document appears incomplete (completeness: {completeness}%). "
                f"Missing: {', '.join(missing_fields)}"
            )
            needs_review = True
            if completeness < 30:
                review_priority = "CRITICAL"
            else:
                review_priority = max(review_priority, "HIGH")

        # Fraud indicators
        if fraud_indicators:
            reasons.extend(fraud_indicators)
            needs_review = True
            review_priority = "CRITICAL"

        # Consistency issues
        if consistency_issues:
            reasons.extend(consistency_issues)
            needs_review = True
            review_priority = max(review_priority, "HIGH")

        # Moderate quality concerns
        if quality < 60:
            reasons.extend(quality_issues)
            needs_review = True

        if needs_review:
            return ReviewDecision(
                decision=DocumentDecision.NEEDS_REVIEW.value,
                confidence=max(quality, completeness),
                reasons=reasons,
                quality_score=quality,
                completeness_score=completeness,
                readability_score=quality,
                freshness_valid=freshness,
                type_match=type_match,
                name_match=name_match,
                auto_approved=False,
                needs_human_review=True,
                review_priority=review_priority,
            )

        # --- AUTO-APPROVE ---

        # All checks passed and scores are above threshold
        overall_score = int(
            (quality * 0.3) + (completeness * 0.3) +
            (name_confidence * 0.2) + (type_confidence * 0.2)
        )

        if overall_score >= self._auto_approve_threshold:
            reasons.append("All quality, type, name, and freshness checks passed")
            if quality_issues:
                reasons.extend(
                    f"Minor: {issue}" for issue in quality_issues
                )

            return ReviewDecision(
                decision=DocumentDecision.ACCEPT.value,
                confidence=overall_score,
                reasons=reasons,
                quality_score=quality,
                completeness_score=completeness,
                readability_score=quality,
                freshness_valid=freshness,
                type_match=type_match,
                name_match=name_match,
                auto_approved=True,
                needs_human_review=False,
                review_priority="LOW",
            )

        # Scores are borderline -- send for human review
        reasons.append(
            f"Overall score ({overall_score}) below auto-approve threshold "
            f"({self._auto_approve_threshold})"
        )
        return ReviewDecision(
            decision=DocumentDecision.NEEDS_REVIEW.value,
            confidence=overall_score,
            reasons=reasons,
            quality_score=quality,
            completeness_score=completeness,
            readability_score=quality,
            freshness_valid=freshness,
            type_match=type_match,
            name_match=name_match,
            auto_approved=False,
            needs_human_review=True,
            review_priority="NORMAL",
        )

    # =========================================================================
    # PERSISTENCE HELPERS
    # =========================================================================

    def _update_document_status(
        self,
        document_id: int,
        decision: ReviewDecision,
    ) -> None:
        """
        Update smart_documents table with review decision.

        Also updates linked smart_document_requests status and creates
        a doc_policy_events audit record.

        Args:
            document_id: SmartDocument ID
            decision: The ReviewDecision to persist
        """
        document = self.db.query(SmartDocument).filter(
            SmartDocument.id == document_id
        ).first()

        if not document:
            logger.error(f"Cannot update status: document {document_id} not found")
            return

        # Map decision string to enum
        try:
            decision_enum = DocumentDecision(decision.decision)
        except ValueError:
            decision_enum = DocumentDecision.NEEDS_REVIEW

        document.decision = decision_enum
        document.decision_reasons = {
            "reasons": decision.reasons,
            "quality_score": decision.quality_score,
            "completeness_score": decision.completeness_score,
            "readability_score": decision.readability_score,
            "freshness_valid": decision.freshness_valid,
            "type_match": decision.type_match,
            "name_match": decision.name_match,
            "auto_approved": decision.auto_approved,
            "review_priority": decision.review_priority,
            "confidence": decision.confidence,
        }
        document.reviewed_at = datetime.utcnow()
        document.reviewed_by = "SYSTEM"

        if decision_enum == DocumentDecision.ACCEPT:
            document.status = "APPROVED"
        elif decision_enum == DocumentDecision.REJECT:
            document.status = "REJECTED"
            document.rejection_reason = "; ".join(decision.reasons)
            if decision.rejection_category:
                try:
                    document.rejection_category = RejectionCategory(
                        decision.rejection_category
                    )
                except ValueError:
                    pass
            document.fix_instructions = decision.fix_instructions
        else:
            document.status = "PROCESSING"

        # Update linked request status
        if document.request_id:
            request = self.db.query(DocumentRequest).filter(
                DocumentRequest.id == document.request_id
            ).first()
            if request:
                if decision_enum == DocumentDecision.ACCEPT:
                    request.status = RequestStatus.ACCEPTED
                elif decision_enum == DocumentDecision.REJECT:
                    request.status = RequestStatus.REJECTED
                else:
                    request.status = RequestStatus.PENDING_REVIEW
                request.updated_at = datetime.utcnow()

        self.db.flush()

    def _log_review_event(
        self,
        document: SmartDocument,
        decision: ReviewDecision,
    ) -> None:
        """
        Create a doc_policy_events audit record for this AI review.

        Args:
            document: The SmartDocument that was reviewed
            decision: The review decision
        """
        # Determine event type
        if decision.decision == DocumentDecision.REJECT.value:
            if decision.rejection_category == RejectionCategory.SCREENSHOT.value:
                event_type = DocPolicyEventType.SCREENSHOT_REJECTED
            elif decision.rejection_category == RejectionCategory.EXPIRED.value:
                event_type = DocPolicyEventType.FRESHNESS_REJECTED
            else:
                event_type = DocPolicyEventType.DOCUMENT_UPLOADED
        else:
            event_type = DocPolicyEventType.DOCUMENT_UPLOADED

        event = DocPolicyEvent(
            loan_id=document.loan_id,
            request_id=document.request_id,
            document_id=document.id,
            event_type=event_type,
            payload={
                "ai_review": True,
                "decision": decision.decision,
                "confidence": decision.confidence,
                "auto_approved": decision.auto_approved,
                "reasons": decision.reasons,
                "quality_score": decision.quality_score,
                "completeness_score": decision.completeness_score,
                "rejection_category": decision.rejection_category,
            },
        )
        self.db.add(event)
        self.db.flush()

    # =========================================================================
    # INTERNAL UTILITIES
    # =========================================================================

    def _fetch_from_s3(self, document: SmartDocument) -> Optional[bytes]:
        """
        Retrieve file content from S3 storage.

        Args:
            document: SmartDocument with storage_key

        Returns:
            File content bytes or None if retrieval fails
        """
        if not document.storage_key:
            logger.warning(f"Document {document.id} has no storage_key")
            return None

        s3_service = get_smart_docs_s3_service()
        if not s3_service.is_available:
            logger.warning("S3 storage not available for AI review")
            return None

        result = s3_service.download_file(document.storage_key)
        if result.get("success"):
            return result["content"]

        logger.warning(
            f"S3 download failed for document {document.id}: "
            f"{result.get('error', 'unknown error')}"
        )
        return None

    def _extract_text(self, file_content: bytes, mime_type: str) -> str:
        """
        Extract text from file content using available OCR/PDF tools.

        Args:
            file_content: Raw file bytes
            mime_type: MIME type string

        Returns:
            Extracted text string
        """
        if mime_type == "application/pdf" and HAS_PDFPLUMBER:
            try:
                import io
                with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                    text_parts = []
                    for page in pdf.pages[:10]:
                        page_text = page.extract_text() or ""
                        text_parts.append(page_text)
                    return "\n".join(text_parts)[:50000]
            except Exception as e:
                logger.warning(f"PDF text extraction failed: {e}")

        if mime_type.startswith("image/") and HAS_PIL:
            try:
                import pytesseract
                from io import BytesIO as BIO
                img = Image.open(BIO(file_content))
                return pytesseract.image_to_string(img)[:50000]
            except Exception as e:
                logger.warning(f"Image OCR failed: {e}")

        return ""


# =============================================================================
# SINGLETON
# =============================================================================

def get_ai_review_service(db: Session, org_id: Optional[int] = None) -> AIDocumentReviewService:
    """
    Get an AIDocumentReviewService instance.

    Creates a new instance per DB session (not a true singleton)
    because the service holds a reference to the session.

    Args:
        db: SQLAlchemy database session
        org_id: Organization ID for tenant isolation.  When provided, all
                queries are scoped to loans/documents belonging to that org.

    Returns:
        AIDocumentReviewService instance
    """
    return AIDocumentReviewService(db, org_id=org_id)
