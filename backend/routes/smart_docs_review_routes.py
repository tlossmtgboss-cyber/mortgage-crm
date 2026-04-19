"""
Smart Docs Review Routes

AI document review and review queue management API routes.
Provides endpoints for:
- Single and batch AI document review
- Review queue management (get, claim, release)
- Pre-upload file validation
- Cross-document consistency validation
- Review history and statistics
- Auto-review settings configuration
- Loan document completeness tracking
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from auth.dependencies import get_current_user
from validation.smart_docs_validators import validate_threshold_pair
from models.smart_docs_models import (
    SmartDocument, DocumentRequest, DocumentDecision,
    DocType, RequestStatus, DocPolicyEvent, DocPolicyEventType,
)
from routes.smart_docs_models import (
    _verify_loan_tenant,
    _verify_document_tenant,
    FRESHNESS_DAYS,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/doc-review",
    tags=["Document Review"],
)


# =============================================================================
# Pydantic Models
# =============================================================================

class AIReviewResponse(BaseModel):
    """Response from AI document review."""
    document_id: int
    decision: str  # ACCEPT, REJECT, NEEDS_REVIEW
    confidence: int
    reasons: List[str]
    quality_score: int
    completeness_score: int
    fix_instructions: Optional[str] = None
    auto_approved: bool = False
    review_priority: str = "NORMAL"


class BatchReviewResponse(BaseModel):
    """Response from batch AI review."""
    loan_id: int
    total: int
    approved: int
    rejected: int
    needs_review: int
    results: List[dict]


class ReviewQueueFilters(BaseModel):
    """Filters for the review queue."""
    priority: Optional[str] = None
    doc_type: Optional[str] = None
    limit: int = 50
    offset: int = 0


class ClaimDocumentBody(BaseModel):
    """Body for claiming a document for review."""
    notes: Optional[str] = None


class AutoReviewSettingsBody(BaseModel):
    """Body for updating auto-review settings."""
    auto_approve_threshold: Optional[int] = None  # 0-100
    auto_reject_threshold: Optional[int] = None  # 0-100
    enabled_checks: Optional[List[str]] = None


class ValidateUploadResponse(BaseModel):
    """Response from pre-upload file validation."""
    is_valid: bool
    score: int
    issues: List[dict]
    passed_rules: List[str]


class CrossValidationResult(BaseModel):
    """Result of cross-document validation."""
    loan_id: int
    inconsistencies: List[dict]
    risk_level: str  # LOW, MEDIUM, HIGH
    document_count: int


class LoanCompletenessResponse(BaseModel):
    """Response for loan document completeness check."""
    loan_id: int
    total_required: int
    received: int
    approved: int
    rejected: int
    missing: int
    completeness_pct: float
    documents: List[dict]
    estimated_days_to_complete: Optional[float] = None


# =============================================================================
# 1. POST /doc-review/ai-review/{document_id}
# =============================================================================

@router.post("/ai-review/{document_id}")
async def ai_review_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Trigger AI review of a single document.

    Runs the document through quality checks, type verification, name matching,
    freshness validation, completeness, screenshot detection, and fraud indicators.

    Returns decision (ACCEPT/REJECT/NEEDS_REVIEW) with confidence and details.
    """
    from services.smart_docs.ai_review_service import get_ai_review_service

    _verify_document_tenant(db, document_id, current_user)

    review_service = get_ai_review_service(db)
    review = review_service.review_document(document_id)

    return {
        "document_id": document_id,
        "decision": review.decision,
        "confidence": review.confidence,
        "reasons": review.reasons,
        "quality_score": review.quality_score,
        "completeness_score": review.completeness_score,
        "fix_instructions": review.fix_instructions,
        "auto_approved": review.auto_approved,
        "needs_human_review": review.needs_human_review,
        "review_priority": review.review_priority,
        "freshness_valid": review.freshness_valid,
        "type_match": review.type_match,
        "name_match": review.name_match,
    }


# =============================================================================
# 2. POST /doc-review/ai-review/batch/{loan_id}
# =============================================================================

@router.post("/ai-review/batch/{loan_id}")
async def batch_ai_review(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Batch AI review all unreviewed documents for a loan.

    Reviews every document that has not yet received a decision, returning
    per-document results and aggregate summary counts.
    """
    from services.smart_docs.ai_review_service import get_ai_review_service

    _verify_loan_tenant(db, loan_id, current_user)

    review_service = get_ai_review_service(db)
    batch_result = review_service.batch_review(loan_id)

    return {
        "loan_id": loan_id,
        "total": batch_result.total,
        "approved": batch_result.approved,
        "rejected": batch_result.rejected,
        "needs_review": batch_result.needs_review,
        "results": batch_result.results,
    }


# =============================================================================
# 3. GET /doc-review/queue
# =============================================================================

@router.get("/queue")
async def get_review_queue(
    priority: Optional[str] = Query(None, description="Filter by priority: CRITICAL, HIGH, NORMAL, LOW"),
    doc_type: Optional[str] = Query(None, description="Filter by document type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get the review queue for the current user's organization.

    Returns documents needing human review, ordered by priority.
    Includes AI recommendations for each document.
    """
    from services.smart_docs.ai_review_service import get_ai_review_service

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization ID required")

    review_service = get_ai_review_service(db)
    queue_items, total = review_service.review_queue(
        organization_id=org_id,
        limit=limit,
        offset=offset,
        priority=priority,
        doc_type=doc_type,
    )

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": queue_items,
    }


# =============================================================================
# 4. GET /doc-review/queue/stats
# =============================================================================

@router.get("/queue/stats")
async def get_queue_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get review queue statistics for the current user's organization.

    Returns total documents in queue, breakdown by priority and doc type,
    average time in queue, and SLA compliance metrics.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization ID required")

    stats = db.execute(text("""
        SELECT
            COUNT(*) AS total_in_queue,
            COUNT(CASE WHEN sd.detected_is_screenshot = true THEN 1 END) AS critical_priority,
            COUNT(CASE WHEN sd.is_expired = true THEN 1 END) AS high_priority,
            AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - sd.uploaded_at)) / 3600) AS avg_hours_in_queue,
            COUNT(CASE WHEN sd.doc_type IS NOT NULL THEN 1 END) AS typed_count
        FROM smart_documents sd
        JOIN loans l ON l.id = sd.loan_id
        WHERE l.organization_id = :org_id
          AND sd.status IN ('PROCESSING', 'SCANNING', 'UPLOADED')
          AND (sd.decision IS NULL OR sd.decision = :needs_review)
    """), {
        "org_id": org_id,
        "needs_review": DocumentDecision.NEEDS_REVIEW.value,
    }).fetchone()

    # Get breakdown by doc type
    by_type_rows = db.execute(text("""
        SELECT
            COALESCE(sd.doc_type, 'UNKNOWN') AS doc_type,
            COUNT(*) AS count
        FROM smart_documents sd
        JOIN loans l ON l.id = sd.loan_id
        WHERE l.organization_id = :org_id
          AND sd.status IN ('PROCESSING', 'SCANNING', 'UPLOADED')
          AND (sd.decision IS NULL OR sd.decision = :needs_review)
        GROUP BY sd.doc_type
        ORDER BY count DESC
    """), {
        "org_id": org_id,
        "needs_review": DocumentDecision.NEEDS_REVIEW.value,
    }).fetchall()

    # SLA compliance: documents reviewed within 24 hours
    sla_row = db.execute(text("""
        SELECT
            COUNT(*) AS total_reviewed,
            COUNT(CASE
                WHEN EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) <= 86400 THEN 1
            END) AS within_sla
        FROM smart_documents sd
        JOIN loans l ON l.id = sd.loan_id
        WHERE l.organization_id = :org_id
          AND sd.reviewed_at IS NOT NULL
          AND sd.uploaded_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
    """), {"org_id": org_id}).fetchone()

    total_reviewed = sla_row[0] if sla_row else 0
    within_sla = sla_row[1] if sla_row else 0

    total = stats[0] if stats else 0
    critical = stats[1] if stats else 0
    high = stats[2] if stats else 0
    avg_hours = float(stats[3]) if stats and stats[3] else 0

    return {
        "total_in_queue": total,
        "by_priority": {
            "critical": critical,
            "high": high,
            "normal": total - critical - high,
        },
        "by_doc_type": [
            {"doc_type": row[0], "count": row[1]}
            for row in by_type_rows
        ],
        "avg_hours_in_queue": round(avg_hours, 1),
        "sla_compliance": {
            "target_hours": 24,
            "total_reviewed_30d": total_reviewed,
            "within_sla": within_sla,
            "compliance_pct": round((within_sla / total_reviewed) * 100, 1) if total_reviewed > 0 else 100.0,
        },
    }


# =============================================================================
# 5. POST /doc-review/queue/{document_id}/claim
# =============================================================================

@router.post("/queue/{document_id}/claim")
async def claim_document(
    document_id: int,
    body: Optional[ClaimDocumentBody] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Claim a document for review.

    Marks the document as being reviewed by the current user to prevent
    double-claiming. Returns the claimed document details.
    """
    doc = _verify_document_tenant(db, document_id, current_user)

    user_id = str(getattr(current_user, "id", "unknown"))
    user_name = getattr(current_user, "first_name", "") or ""
    last_name = getattr(current_user, "last_name", "") or ""
    reviewer_name = f"{user_name} {last_name}".strip() or user_id

    # Check if already claimed by someone else
    if doc.reviewed_by and doc.reviewed_by != "SYSTEM" and doc.reviewed_by != user_id:
        if doc.status in ("PROCESSING", "SCANNING", "UPLOADED", "NEEDS_REVIEW"):
            raise HTTPException(
                status_code=409,
                detail=f"Document already claimed by {doc.reviewed_by}",
            )

    # Mark as claimed
    doc.reviewed_by = user_id
    doc.status = "NEEDS_REVIEW"
    doc.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"Document {document_id} claimed by {reviewer_name}")

    return {
        "document_id": document_id,
        "claimed_by": reviewer_name,
        "claimed_by_id": user_id,
        "claimed_at": datetime.now(timezone.utc).isoformat(),
        "file_name": doc.file_name,
        "doc_type": doc.doc_type.value if doc.doc_type else None,
        "loan_id": doc.loan_id,
        "status": doc.status,
        "decision": doc.decision.value if doc.decision else None,
        "rejection_reason": doc.rejection_reason,
        "screenshot_confidence": doc.screenshot_confidence,
        "is_expired": doc.is_expired,
    }


# =============================================================================
# 6. POST /doc-review/queue/{document_id}/release
# =============================================================================

@router.post("/queue/{document_id}/release")
async def release_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Release a claimed document back to the review queue.

    Removes the reviewer assignment so other users can claim it.
    """
    doc = _verify_document_tenant(db, document_id, current_user)

    user_id = str(getattr(current_user, "id", "unknown"))

    # Only the claimer or an admin can release
    is_admin = getattr(current_user, "permission_role", "") == "admin"
    if doc.reviewed_by and doc.reviewed_by != user_id and not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Only the claiming reviewer or an admin can release this document",
        )

    # Only release if the document hasn't been decided
    if doc.decision and doc.decision != DocumentDecision.NEEDS_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot release document with decision '{doc.decision.value}'",
        )

    previous_reviewer = doc.reviewed_by
    doc.reviewed_by = None
    doc.status = "UPLOADED"
    doc.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"Document {document_id} released by {user_id} (was claimed by {previous_reviewer})")

    return {
        "document_id": document_id,
        "released_by": user_id,
        "released_at": datetime.now(timezone.utc).isoformat(),
        "previous_reviewer": previous_reviewer,
        "status": "UPLOADED",
        "message": "Document returned to review queue",
    }


# =============================================================================
# 7. POST /doc-review/validate-upload
# =============================================================================

@router.post("/validate-upload")
async def validate_upload(
    file: UploadFile = File(...),
    doc_type: Optional[str] = Query(None, description="Declared document type"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Validate a file before upload without saving it.

    Runs the document validation engine to check file type, size, security,
    and format, plus malware scanning. Used by the frontend for pre-upload
    validation to give immediate feedback.
    """
    from services.smart_docs.document_validation_engine import get_document_validation_engine
    from services.smart_docs.malware_scanner_service import get_malware_scanner
    from middleware.upload_limits import validate_upload_size, MAX_DOCUMENT_SIZE

    file_content = await validate_upload_size(file, MAX_DOCUMENT_SIZE)
    filename = file.filename or "unknown"
    mime_type = file.content_type or "application/octet-stream"

    engine = get_document_validation_engine()
    result = engine.validate_upload(
        file_content=file_content,
        filename=filename,
        mime_type=mime_type,
        declared_doc_type=doc_type,
    )

    # Run malware scan
    scanner = get_malware_scanner()
    scan_result = scanner.validate_file_safety(
        file_bytes=file_content,
        filename=filename,
        mime_type=mime_type,
    )

    response = result.to_dict()
    response["malware_scan"] = scan_result.to_dict()

    if not scan_result.clean:
        response["is_valid"] = False
        response["malware_scan"]["rejected"] = True
        logger.warning(
            "Pre-upload validation: malware detected in '%s' by user %s",
            filename,
            getattr(current_user, "id", "unknown"),
        )

    return response


# =============================================================================
# 8. GET /doc-review/validation-rules/{doc_type}
# =============================================================================

@router.get("/validation-rules/{doc_type}")
async def get_validation_rules(
    doc_type: str,
    current_user=Depends(get_current_user),
):
    """
    Get validation rules for a specific document type.

    Returns applicable rules, requirements, freshness days, and allowed
    file formats. Used by the frontend to display upload requirements.
    """
    from services.smart_docs.document_validation_engine import get_document_validation_engine

    engine = get_document_validation_engine()
    rules = engine.get_validation_rules_for_type(doc_type)

    return rules


# =============================================================================
# 9. POST /doc-review/cross-validate/{loan_id}
# =============================================================================

@router.post("/cross-validate/{loan_id}")
async def cross_validate_documents(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Cross-validate all approved documents for a loan.

    Runs cross-document consistency checks comparing employer names, income
    amounts, borrower names, and other data across all documents on the loan.
    Returns inconsistencies found and a risk assessment.
    """
    from services.smart_docs.ai_review_service import get_ai_review_service

    _verify_loan_tenant(db, loan_id, current_user)

    # Get all approved documents for this loan
    documents = db.query(SmartDocument).filter(
        SmartDocument.loan_id == loan_id,
        SmartDocument.decision == DocumentDecision.ACCEPT,
    ).all()

    if not documents:
        return {
            "loan_id": loan_id,
            "inconsistencies": [],
            "risk_level": "LOW",
            "document_count": 0,
            "message": "No approved documents to cross-validate",
        }

    review_service = get_ai_review_service(db)

    all_inconsistencies = []
    checked_pairs = set()

    for doc in documents:
        # Use the service's private cross-document check for each document
        issues = review_service._check_cross_document_consistency(doc.id, loan_id)
        for issue in issues:
            # Deduplicate issue descriptions
            issue_key = issue.lower().strip()
            if issue_key not in checked_pairs:
                checked_pairs.add(issue_key)
                all_inconsistencies.append({
                    "source_document_id": doc.id,
                    "source_doc_type": doc.doc_type.value if doc.doc_type else None,
                    "source_file_name": doc.file_name,
                    "description": issue,
                })

    # Determine risk level based on inconsistency count and severity
    if len(all_inconsistencies) == 0:
        risk_level = "LOW"
    elif len(all_inconsistencies) <= 2:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    return {
        "loan_id": loan_id,
        "inconsistencies": all_inconsistencies,
        "inconsistency_count": len(all_inconsistencies),
        "risk_level": risk_level,
        "document_count": len(documents),
    }


# =============================================================================
# 10. GET /doc-review/document/{document_id}/review-history
# =============================================================================

@router.get("/document/{document_id}/review-history")
async def get_review_history(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get review history for a document.

    Returns all review decisions (both AI and human) in chronological order,
    sourced from the doc_policy_events audit trail.
    """
    _verify_document_tenant(db, document_id, current_user)

    # Get the current document state
    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get all policy events related to this document
    events = db.execute(text("""
        SELECT
            id, event_type, payload, created_at
        FROM doc_policy_events
        WHERE document_id = :document_id
        ORDER BY created_at ASC
    """), {"document_id": document_id}).fetchall()

    history = []
    for event in events:
        payload = event[2] or {}
        history.append({
            "event_id": event[0],
            "event_type": event[1],
            "decision": payload.get("decision"),
            "reason": payload.get("reason"),
            "category": payload.get("category"),
            "reviewer": payload.get("reviewer", "SYSTEM"),
            "timestamp": event[3].isoformat() if event[3] else None,
            "details": payload,
        })

    # Include current document state as the latest entry
    current_state = {
        "document_id": document_id,
        "current_status": document.status,
        "current_decision": document.decision.value if document.decision else None,
        "reviewed_by": document.reviewed_by,
        "reviewed_at": document.reviewed_at.isoformat() if document.reviewed_at else None,
        "rejection_reason": document.rejection_reason,
        "rejection_category": document.rejection_category.value if document.rejection_category else None,
    }

    return {
        "document_id": document_id,
        "file_name": document.file_name,
        "doc_type": document.doc_type.value if document.doc_type else None,
        "current_state": current_state,
        "history": history,
        "total_events": len(history),
    }


# =============================================================================
# 11. POST /doc-review/auto-review-settings
# =============================================================================

@router.post("/auto-review-settings")
async def update_auto_review_settings(
    body: AutoReviewSettingsBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Update auto-review settings for the organization.

    Requires admin role. Controls thresholds for automatic approval and
    rejection, and which checks are enabled.
    """
    # Require admin role
    permission_role = getattr(current_user, "permission_role", "")
    if permission_role not in ("admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization ID required")

    # Validate thresholds individually
    if body.auto_approve_threshold is not None:
        if not (0 <= body.auto_approve_threshold <= 100):
            raise HTTPException(status_code=400, detail="auto_approve_threshold must be 0-100")
    if body.auto_reject_threshold is not None:
        if not (0 <= body.auto_reject_threshold <= 100):
            raise HTTPException(status_code=400, detail="auto_reject_threshold must be 0-100")

    # Validate the pair relationship: reject < approve
    if body.auto_approve_threshold is not None and body.auto_reject_threshold is not None:
        try:
            validate_threshold_pair(body.auto_approve_threshold, body.auto_reject_threshold)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Auto-reject threshold must be lower than auto-approve threshold",
            )

    # Upsert settings in the organization's configuration
    existing = db.execute(text("""
        SELECT id, settings FROM organization_settings
        WHERE organization_id = :org_id AND setting_key = 'auto_review'
    """), {"org_id": org_id}).fetchone()

    import json

    if existing:
        current_settings = json.loads(existing[1]) if existing[1] else {}
    else:
        current_settings = {
            "auto_approve_threshold": 80,
            "auto_reject_threshold": 30,
            "enabled_checks": [
                "quality", "screenshot", "type_match", "name_match",
                "freshness", "completeness", "fraud",
            ],
        }

    # Apply updates
    if body.auto_approve_threshold is not None:
        current_settings["auto_approve_threshold"] = body.auto_approve_threshold
    if body.auto_reject_threshold is not None:
        current_settings["auto_reject_threshold"] = body.auto_reject_threshold
    if body.enabled_checks is not None:
        current_settings["enabled_checks"] = body.enabled_checks

    current_settings["updated_at"] = datetime.now(timezone.utc).isoformat()
    current_settings["updated_by"] = str(getattr(current_user, "id", "unknown"))

    settings_json = json.dumps(current_settings)

    if existing:
        db.execute(text("""
            UPDATE organization_settings
            SET settings = :settings, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"settings": settings_json, "id": existing[0]})
    else:
        db.execute(text("""
            INSERT INTO organization_settings (organization_id, setting_key, settings, created_at, updated_at)
            VALUES (:org_id, 'auto_review', :settings, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """), {"org_id": org_id, "settings": settings_json})

    db.commit()

    logger.info(f"Auto-review settings updated for org {org_id}")

    return {
        "organization_id": org_id,
        "settings": current_settings,
        "message": "Auto-review settings updated",
    }


# =============================================================================
# 12. GET /doc-review/auto-review-settings
# =============================================================================

@router.get("/auto-review-settings")
async def get_auto_review_settings(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get current auto-review settings for the organization.

    Returns thresholds and enabled checks.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization ID required")

    import json

    row = db.execute(text("""
        SELECT settings FROM organization_settings
        WHERE organization_id = :org_id AND setting_key = 'auto_review'
    """), {"org_id": org_id}).fetchone()

    if row and row[0]:
        settings = json.loads(row[0])
    else:
        # Return defaults
        settings = {
            "auto_approve_threshold": 80,
            "auto_reject_threshold": 30,
            "enabled_checks": [
                "quality", "screenshot", "type_match", "name_match",
                "freshness", "completeness", "fraud",
            ],
        }

    return {
        "organization_id": org_id,
        "settings": settings,
    }


# =============================================================================
# 13. GET /doc-review/stats
# =============================================================================

@router.get("/stats")
async def get_review_stats(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get review statistics for the organization.

    Returns auto-approved %, rejected %, needs_review %, common rejection
    reasons, average review time, and accuracy metrics (human overrides).
    """
    from services.smart_docs.ai_review_service import get_ai_review_service

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization ID required")

    review_service = get_ai_review_service(db)
    stats = review_service.get_review_stats(organization_id=org_id, days=days)

    # Get human override stats (where human decision differs from AI)
    override_row = db.execute(text("""
        SELECT
            COUNT(*) AS total_human_reviews,
            COUNT(CASE
                WHEN sd.reviewed_by != 'SYSTEM'
                AND EXISTS (
                    SELECT 1 FROM doc_policy_events dpe
                    WHERE dpe.document_id = sd.id
                    AND dpe.event_type = 'DOCUMENT_UPLOADED'
                    AND (dpe.payload->>'decision') IS NOT NULL
                    AND (dpe.payload->>'decision') != sd.decision::text
                )
                THEN 1
            END) AS overrides
        FROM smart_documents sd
        JOIN loans l ON l.id = sd.loan_id
        WHERE l.organization_id = :org_id
          AND sd.reviewed_by IS NOT NULL
          AND sd.reviewed_by != 'SYSTEM'
          AND sd.uploaded_at >= CURRENT_TIMESTAMP - make_interval(days => :days)
    """), {"org_id": org_id, "days": days}).fetchone()

    total_human = override_row[0] if override_row else 0
    overrides = override_row[1] if override_row else 0

    stats["human_reviews"] = total_human
    stats["ai_overrides"] = overrides
    stats["ai_accuracy_pct"] = (
        round(((total_human - overrides) / total_human) * 100, 1)
        if total_human > 0 else 100.0
    )

    return stats


# =============================================================================
# 14. POST /doc-review/document/{document_id}/ai-extract-and-review
# =============================================================================

@router.post("/document/{document_id}/ai-extract-and-review")
async def ai_extract_and_review(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Combined AI extraction and review in one call.

    Triggers AI data extraction AND review for a document, returning both
    extraction results and the review decision. More efficient than calling
    extract and review separately for processing new uploads.
    """
    from services.smart_docs.ai_review_service import get_ai_review_service
    from services.smart_docs.document_data_extractor import get_document_data_extractor
    from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

    doc = _verify_document_tenant(db, document_id, current_user)

    # --- Extraction Phase ---
    extraction_result = None

    try:
        from models.document_extraction import SmartDocumentExtraction, ReviewStatus, DetectedOwner
        from services.smart_docs.owner_matcher import get_owner_matcher

        # Check for existing extraction
        existing_extraction = db.query(SmartDocumentExtraction).filter(
            SmartDocumentExtraction.document_id == document_id
        ).first()

        if existing_extraction:
            extraction_result = {
                "extraction_id": existing_extraction.id,
                "extracted_fields": existing_extraction.extracted_fields or {},
                "confidence_scores": existing_extraction.confidence_scores or {},
                "overall_confidence": existing_extraction.overall_confidence or 0,
                "detected_owner": existing_extraction.detected_owner.value if existing_extraction.detected_owner else "UNKNOWN",
                "cached": True,
            }
        else:
            # Get file content from S3
            s3_service = get_smart_docs_s3_service()
            file_content = None

            if doc.storage_key and s3_service.is_available:
                download_result = s3_service.download_file(doc.storage_key)
                if download_result.get("success"):
                    file_content = download_result.get("content")

            if file_content:
                extractor = get_document_data_extractor()
                result = extractor.extract(
                    file_content=file_content,
                    mime_type=doc.mime_type,
                    doc_type=doc.doc_type,
                    ocr_text=doc.ocr_text,
                )

                if result.success:
                    # Get borrower names for owner matching
                    borrower_name = None
                    co_borrower_name = None
                    if doc.loan_id:
                        loan_info = db.execute(text("""
                            SELECT borrower_name, coborrower_name FROM loans WHERE id = :loan_id
                        """), {"loan_id": doc.loan_id}).fetchone()
                        if loan_info:
                            borrower_name = loan_info[0]
                            co_borrower_name = loan_info[1]

                    owner_matcher = get_owner_matcher()
                    owner_result = owner_matcher.match_owner(
                        extracted_names=result.detected_names,
                        borrower_name=borrower_name,
                        co_borrower_name=co_borrower_name,
                    )

                    owner_enum = DetectedOwner.UNKNOWN
                    if owner_result.owner == "BORROWER":
                        owner_enum = DetectedOwner.BORROWER
                    elif owner_result.owner == "CO_BORROWER":
                        owner_enum = DetectedOwner.CO_BORROWER

                    extraction = SmartDocumentExtraction(
                        document_id=document_id,
                        extracted_fields=result.extracted_fields,
                        confidence_scores=result.confidence_scores,
                        provenance=result.provenance,
                        mappable_fields=result.mappable_fields,
                        field_categories=result.field_categories,
                        detected_owner=owner_enum,
                        owner_confidence=owner_result.confidence,
                        owner_match_details=owner_result.match_details,
                        overall_confidence=result.overall_confidence,
                        extraction_model=result.extraction_model,
                        extraction_duration_ms=result.extraction_duration_ms,
                        review_status=ReviewStatus.PENDING,
                    )
                    db.add(extraction)
                    db.flush()

                    extraction_result = {
                        "extraction_id": extraction.id,
                        "extracted_fields": result.extracted_fields,
                        "confidence_scores": result.confidence_scores,
                        "overall_confidence": result.overall_confidence,
                        "detected_owner": owner_result.owner,
                        "cached": False,
                    }

    except ImportError:
        logger.warning("document_extraction models not available, skipping extraction")
    except Exception as e:
        logger.exception(f"Extraction failed for document {document_id}: {e}")

    # --- Review Phase ---
    review_service = get_ai_review_service(db)
    review = review_service.review_document(document_id)

    db.commit()

    return {
        "document_id": document_id,
        "extraction": extraction_result,
        "review": {
            "decision": review.decision,
            "confidence": review.confidence,
            "reasons": review.reasons,
            "quality_score": review.quality_score,
            "completeness_score": review.completeness_score,
            "fix_instructions": review.fix_instructions,
            "auto_approved": review.auto_approved,
            "needs_human_review": review.needs_human_review,
            "review_priority": review.review_priority,
        },
    }


# =============================================================================
# 15. GET /doc-review/loan/{loan_id}/completeness
# =============================================================================

@router.get("/loan/{loan_id}/completeness")
async def get_loan_completeness(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get loan document completeness report.

    Compares the needs list (required documents) against received and approved
    documents. Returns total required, received, approved, rejected, missing
    counts, per-document status, overall completeness percentage, and an
    estimated time to complete based on historical data.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    # Get all document requests (needs list) for this loan
    requests = db.query(DocumentRequest).filter(
        DocumentRequest.loan_id == loan_id,
        DocumentRequest.is_active == True,
    ).all()

    if not requests:
        return {
            "loan_id": loan_id,
            "total_required": 0,
            "received": 0,
            "approved": 0,
            "rejected": 0,
            "missing": 0,
            "completeness_pct": 100.0,
            "documents": [],
            "estimated_days_to_complete": None,
            "message": "No document requirements found for this loan",
        }

    # Get all documents for this loan
    documents = db.query(SmartDocument).filter(
        SmartDocument.loan_id == loan_id,
        SmartDocument.status.notin_(["DELETED", "SUPERSEDED"]),
    ).all()

    # Build a map of request_id -> documents
    docs_by_request = {}
    for doc in documents:
        if doc.request_id:
            if doc.request_id not in docs_by_request:
                docs_by_request[doc.request_id] = []
            docs_by_request[doc.request_id].append(doc)

    total_required = len(requests)
    received = 0
    approved = 0
    rejected = 0
    missing = 0
    doc_details = []

    for req in requests:
        req_docs = docs_by_request.get(req.id, [])

        # Determine the best document for this request
        best_doc = None
        for d in req_docs:
            if d.decision == DocumentDecision.ACCEPT:
                best_doc = d
                break
        if not best_doc and req_docs:
            best_doc = req_docs[-1]  # Most recent

        if req.status == RequestStatus.WAIVED:
            status = "WAIVED"
            approved += 1
        elif req.status == RequestStatus.ACCEPTED:
            status = "APPROVED"
            received += 1
            approved += 1
        elif best_doc and best_doc.decision == DocumentDecision.ACCEPT:
            status = "APPROVED"
            received += 1
            approved += 1
        elif best_doc and best_doc.decision == DocumentDecision.REJECT:
            status = "REJECTED"
            received += 1
            rejected += 1
        elif best_doc:
            status = "PENDING_REVIEW"
            received += 1
        else:
            status = "MISSING"
            missing += 1

        doc_details.append({
            "request_id": req.id,
            "doc_type": req.doc_type.value if req.doc_type else None,
            "title": req.title,
            "priority": req.priority.value if req.priority else "NORMAL",
            "status": status,
            "document_id": best_doc.id if best_doc else None,
            "file_name": best_doc.file_name if best_doc else None,
            "uploaded_at": best_doc.uploaded_at.isoformat() if best_doc and best_doc.uploaded_at else None,
            "decision": best_doc.decision.value if best_doc and best_doc.decision else None,
            "rejection_reason": best_doc.rejection_reason if best_doc else None,
            "due_date": req.due_date.isoformat() if req.due_date else None,
        })

    completeness_pct = round((approved / total_required) * 100, 1) if total_required > 0 else 100.0

    # Estimate days to complete based on historical average time from first doc to all approved
    estimated_days = None
    if missing > 0 or rejected > 0:
        avg_row = db.execute(text("""
            SELECT AVG(days_to_complete) AS avg_days
            FROM (
                SELECT
                    dr.loan_id,
                    EXTRACT(EPOCH FROM (MAX(sd.reviewed_at) - MIN(sd.uploaded_at))) / 86400 AS days_to_complete
                FROM smart_document_requests dr
                JOIN smart_documents sd ON sd.request_id = dr.id
                WHERE dr.status = 'ACCEPTED'
                  AND sd.decision = :accept
                GROUP BY dr.loan_id
                HAVING COUNT(DISTINCT dr.id) >= 3
            ) completed_loans
        """), {"accept": DocumentDecision.ACCEPT.value}).fetchone()

        if avg_row and avg_row[0]:
            # Scale by ratio of remaining to total
            remaining = missing + rejected
            ratio = remaining / total_required if total_required > 0 else 0
            estimated_days = round(float(avg_row[0]) * ratio, 1)

    return {
        "loan_id": loan_id,
        "total_required": total_required,
        "received": received,
        "approved": approved,
        "rejected": rejected,
        "missing": missing,
        "completeness_pct": completeness_pct,
        "documents": doc_details,
        "estimated_days_to_complete": estimated_days,
    }
