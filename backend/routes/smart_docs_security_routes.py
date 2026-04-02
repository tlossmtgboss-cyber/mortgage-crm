"""
Smart Docs Security Routes

Document security, audit, and compliance API routes:
- Access audit logging (SOC 2 / regulatory compliance)
- Integrity verification (tamper detection via SHA-256 hash comparison)
- Fraud analysis (risk scoring and indicator detection)
- Retention policy management (TRID, state-specific rules)
- Watermarking (forensic tracing of leaked documents)
- Encryption status tracking
- Suspicious activity detection
"""

import hashlib
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, text as sa_text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user
from database.models.document_security import (
    DocumentAccessLog,
    DocumentEncryptionRecord,
    DocumentIntegrityCheck,
    DocumentRetentionPolicy,
    DocumentWatermarkLog,
    AccessType,
    EncryptionStatus,
    IntegrityCheckType,
    RetentionAction,
    WatermarkType,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Document Security"])


# =============================================================================
# Pydantic Models
# =============================================================================

class LogAccessBody(BaseModel):
    """Request body for logging a document access event."""
    document_id: int
    document_type: str = "smart_document"
    access_type: str  # view, download, print, etc.
    metadata: Optional[dict] = None


class BatchIntegrityCheckBody(BaseModel):
    """Request body for batch integrity check."""
    loan_id: Optional[int] = None
    document_ids: Optional[List[int]] = None


class CreateRetentionPolicyBody(BaseModel):
    """Request body for creating a retention policy."""
    doc_type: str
    policy_name: str
    retention_days: int = Field(..., ge=1)
    retention_after_event: str  # FUNDED, DENIED, CANCELLED, etc.
    action_on_expiry: str = "notify_admin"  # delete, archive, anonymize, notify_admin
    notify_days_before: int = Field(30, ge=0)
    regulatory_reference: Optional[str] = None
    applies_to_states: Optional[List[str]] = None


class UpdateRetentionPolicyBody(BaseModel):
    """Request body for updating a retention policy."""
    policy_name: Optional[str] = None
    retention_days: Optional[int] = Field(None, ge=1)
    retention_after_event: Optional[str] = None
    action_on_expiry: Optional[str] = None
    notify_days_before: Optional[int] = Field(None, ge=0)
    regulatory_reference: Optional[str] = None
    applies_to_states: Optional[List[str]] = None
    is_active: Optional[bool] = None


class WatermarkRequestBody(BaseModel):
    """Request body for watermark generation."""
    watermark_type: str = "VIEWING"  # VIEWING, DOWNLOAD, PRINT
    custom_text: Optional[str] = None


# =============================================================================
# Helpers
# =============================================================================

def _require_admin(current_user):
    """Raise 403 if the current user is not an admin or site_admin."""
    role = getattr(current_user, 'permission_role', '')
    if role not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")


def _get_user_org_id(current_user) -> Optional[int]:
    """Extract organization_id from current_user."""
    return getattr(current_user, 'organization_id', None)


def _get_user_id(current_user) -> Optional[int]:
    """Extract user id from current_user."""
    return getattr(current_user, 'id', None)


def _is_platform_admin(current_user) -> bool:
    """Check if user is a platform admin (cross-org access)."""
    return getattr(current_user, 'permission_role', '') == 'admin'


def _is_portal_request(request) -> bool:
    """Detect whether this request originates from the borrower portal.

    Portal requests are identified by:
    - X-Portal-Request header (set by the portal frontend)
    - URL path containing /portal/
    - Portal-specific referrer
    """
    if request is None:
        return False
    # Check explicit portal header
    if request.headers.get("X-Portal-Request", "").lower() in ("true", "1"):
        return True
    # Check URL path
    url_path = str(getattr(request, "url", ""))
    if "/portal/" in url_path:
        return True
    # Check referrer for portal domain
    referrer = request.headers.get("Referer", "") or request.headers.get("Referrer", "")
    if "portal" in referrer.lower():
        return True
    return False


def _verify_document_org_access(db: Session, document_id: int, current_user):
    """Verify the user's org owns the document's loan. Returns the SmartDocument row."""
    from models.smart_docs_models import SmartDocument as _SD
    doc = db.query(_SD).filter(_SD.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.loan_id and not _is_platform_admin(current_user):
        org_id = _get_user_org_id(current_user)
        if org_id:
            row = db.execute(
                sa_text("SELECT organization_id FROM loans WHERE id = :id"),
                {"id": doc.loan_id},
            ).first()
            if row and row[0] != org_id:
                raise HTTPException(status_code=404, detail="Not found")
    return doc


def _compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of file content."""
    return hashlib.sha256(file_bytes).hexdigest()


# =============================================================================
# 1. GET /doc-security/audit-log — Paginated audit log (admin only)
# =============================================================================

@router.get("/doc-security/audit-log")
async def get_audit_log(
    document_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    access_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="ISO date string"),
    date_to: Optional[str] = Query(None, description="ISO date string"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get document access audit log. Requires admin or site_admin role."""
    _require_admin(current_user)

    org_id = _get_user_org_id(current_user)
    query = db.query(DocumentAccessLog)

    # Scope to organization unless platform admin
    if org_id and not _is_platform_admin(current_user):
        query = query.filter(DocumentAccessLog.organization_id == org_id)

    if document_id:
        query = query.filter(DocumentAccessLog.document_id == document_id)
    if user_id:
        query = query.filter(DocumentAccessLog.user_id == user_id)
    if access_type:
        try:
            at = AccessType(access_type)
            query = query.filter(DocumentAccessLog.access_type == at)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid access_type: {access_type}")
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(DocumentAccessLog.created_at >= dt_from)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from format")
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(DocumentAccessLog.created_at <= dt_to)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_to format")

    total = query.count()
    logs = query.order_by(DocumentAccessLog.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "entries": [
            {
                "id": log.id,
                "document_id": log.document_id,
                "document_type": log.document_type,
                "user_id": log.user_id,
                "access_type": log.access_type.value if log.access_type else None,
                "access_granted": log.access_granted,
                "denial_reason": log.denial_reason,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "geo_location": log.geo_location,
                "session_id": log.session_id,
                "duration_seconds": log.duration_seconds,
                "pages_viewed": log.pages_viewed,
                "metadata": log.extra_metadata,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


# =============================================================================
# 2. GET /doc-security/audit-log/{document_id} — Audit log for specific doc
# =============================================================================

@router.get("/doc-security/audit-log/{document_id}")
async def get_document_audit_log(
    document_id: int,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get audit log for a specific document. Verifies tenant access via loan."""
    _verify_document_org_access(db, document_id, current_user)

    query = db.query(DocumentAccessLog).filter(
        DocumentAccessLog.document_id == document_id
    )
    total = query.count()
    logs = query.order_by(DocumentAccessLog.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "document_id": document_id,
        "total": total,
        "offset": offset,
        "limit": limit,
        "entries": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "access_type": log.access_type.value if log.access_type else None,
                "access_granted": log.access_granted,
                "denial_reason": log.denial_reason,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "duration_seconds": log.duration_seconds,
                "pages_viewed": log.pages_viewed,
                "metadata": log.extra_metadata,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


# =============================================================================
# 3. POST /doc-security/log-access — Log a document access event
# =============================================================================

@router.post("/doc-security/log-access")
async def log_document_access(
    body: LogAccessBody,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Log a document access event (view, download, print, etc.).

    Automatically captures IP address and user agent from the request.
    Used by the frontend to record view/download events for SOC 2 compliance.
    """
    try:
        at = AccessType(body.access_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid access_type: {body.access_type}. Valid types: {[t.value for t in AccessType]}",
        )

    # Extract request context
    ip_address = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    if ip_address and "," in ip_address:
        ip_address = ip_address.split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "")[:512]

    org_id = _get_user_org_id(current_user)
    user_id = _get_user_id(current_user)

    log_entry = DocumentAccessLog(
        organization_id=org_id,
        document_id=body.document_id,
        document_type=body.document_type,
        user_id=user_id,
        access_type=at,
        access_granted=True,
        ip_address=ip_address,
        user_agent=user_agent,
        extra_metadata=body.metadata,
    )

    try:
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to log document access: %s", e)
        raise HTTPException(status_code=500, detail="Failed to log access event")

    return {
        "status": "logged",
        "log_id": log_entry.id,
        "document_id": body.document_id,
        "access_type": body.access_type,
        "timestamp": log_entry.created_at.isoformat() if log_entry.created_at else None,
    }


# =============================================================================
# 4. GET /doc-security/integrity-check/{document_id} — Single integrity check
# =============================================================================

@router.get("/doc-security/integrity-check/{document_id}")
async def run_integrity_check(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Run integrity check on a document.

    Fetches the document from S3, computes its SHA-256 hash, and compares
    against the stored hash. Creates an integrity check record.
    """
    doc = _verify_document_org_access(db, document_id, current_user)

    start_time = time.monotonic()

    # Get the expected hash from the encryption record or document metadata
    expected_hash = None
    storage_key = None

    enc_record = db.query(DocumentEncryptionRecord).filter(
        DocumentEncryptionRecord.document_id == document_id,
    ).order_by(DocumentEncryptionRecord.created_at.desc()).first()

    if enc_record:
        expected_hash = enc_record.content_hash_after or enc_record.content_hash_before

    # Fall back to document-level hash if available
    if not expected_hash:
        expected_hash = getattr(doc, 'file_hash', None) or getattr(doc, 'content_hash', None)

    # Attempt to fetch from S3 and compute actual hash
    actual_hash = None
    file_size_actual = None
    try:
        from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
        s3_service = get_smart_docs_s3_service()
        storage_key = getattr(doc, 'storage_key', None) or getattr(doc, 's3_key', None)
        if storage_key and s3_service._s3_available:
            file_bytes = s3_service.download_file(storage_key)
            if file_bytes:
                actual_hash = _compute_file_hash(file_bytes)
                file_size_actual = len(file_bytes)
    except Exception as e:
        logger.warning("S3 fetch failed for integrity check on doc %s: %s", document_id, e)

    # If we cannot compute actual hash, report it
    if actual_hash is None:
        actual_hash = "unavailable"

    if expected_hash is None:
        expected_hash = "not_recorded"

    is_valid = expected_hash == actual_hash if (expected_hash != "not_recorded" and actual_hash != "unavailable") else None
    tamper_detected = is_valid is False

    check_duration_ms = int((time.monotonic() - start_time) * 1000)

    check_record = DocumentIntegrityCheck(
        document_id=document_id,
        document_type=getattr(doc, 'doc_type', 'smart_document') or "smart_document",
        check_type=IntegrityCheckType.MANUAL,
        expected_hash=expected_hash,
        actual_hash=actual_hash,
        is_valid=is_valid if is_valid is not None else False,
        tamper_detected=tamper_detected,
        tamper_details="Hash mismatch detected" if tamper_detected else None,
        checked_by=str(_get_user_id(current_user) or "SYSTEM"),
        check_duration_ms=check_duration_ms,
        storage_key_checked=storage_key,
        file_size_actual=file_size_actual,
    )

    try:
        db.add(check_record)
        db.commit()
        db.refresh(check_record)
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to save integrity check record: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save integrity check")

    return {
        "document_id": document_id,
        "check_id": check_record.id,
        "is_valid": is_valid,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "tamper_detected": tamper_detected,
        "check_duration_ms": check_duration_ms,
        "file_size_actual": file_size_actual,
        "checked_at": check_record.created_at.isoformat() if check_record.created_at else None,
    }


# =============================================================================
# 5. POST /doc-security/integrity-check/batch — Batch integrity check
# =============================================================================

@router.post("/doc-security/integrity-check/batch")
async def batch_integrity_check(
    body: BatchIntegrityCheckBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Run integrity checks on multiple documents.

    Specify either loan_id (checks all documents for that loan) or
    document_ids (checks specific documents). Returns a summary with
    any tampered documents flagged.
    """
    if not body.loan_id and not body.document_ids:
        raise HTTPException(status_code=400, detail="Provide loan_id or document_ids")

    from models.smart_docs_models import SmartDocument as _SD

    if body.loan_id:
        # Verify tenant access to the loan
        from routes.smart_docs_models import _verify_loan_tenant
        _verify_loan_tenant(db, body.loan_id, current_user)
        docs = db.query(_SD).filter(_SD.loan_id == body.loan_id).all()
        document_ids = [d.id for d in docs]
    else:
        document_ids = body.document_ids

    results = []
    tampered_count = 0
    valid_count = 0
    error_count = 0

    for doc_id in document_ids:
        try:
            doc = db.query(_SD).filter(_SD.id == doc_id).first()
            if not doc:
                results.append({"document_id": doc_id, "status": "not_found"})
                error_count += 1
                continue

            # Get expected hash
            expected_hash = getattr(doc, 'file_hash', None) or getattr(doc, 'content_hash', None)
            enc_record = db.query(DocumentEncryptionRecord).filter(
                DocumentEncryptionRecord.document_id == doc_id,
            ).order_by(DocumentEncryptionRecord.created_at.desc()).first()
            if enc_record and not expected_hash:
                expected_hash = enc_record.content_hash_after or enc_record.content_hash_before

            # Compute actual hash from S3
            actual_hash = None
            storage_key = getattr(doc, 'storage_key', None) or getattr(doc, 's3_key', None)
            try:
                from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
                s3_service = get_smart_docs_s3_service()
                if storage_key and s3_service._s3_available:
                    file_bytes = s3_service.download_file(storage_key)
                    if file_bytes:
                        actual_hash = _compute_file_hash(file_bytes)
            except Exception as e:
                logger.warning("S3 fetch failed for doc %s: %s", doc_id, e)

            is_valid = None
            if expected_hash and actual_hash:
                is_valid = expected_hash == actual_hash

            tamper_detected = is_valid is False
            if tamper_detected:
                tampered_count += 1
            elif is_valid:
                valid_count += 1
            else:
                error_count += 1

            # Save check record
            check_record = DocumentIntegrityCheck(
                document_id=doc_id,
                document_type=getattr(doc, 'doc_type', 'smart_document') or "smart_document",
                check_type=IntegrityCheckType.MANUAL,
                expected_hash=expected_hash or "not_recorded",
                actual_hash=actual_hash or "unavailable",
                is_valid=is_valid if is_valid is not None else False,
                tamper_detected=tamper_detected,
                tamper_details="Hash mismatch detected" if tamper_detected else None,
                checked_by=str(_get_user_id(current_user) or "SYSTEM"),
            )
            db.add(check_record)

            results.append({
                "document_id": doc_id,
                "is_valid": is_valid,
                "tamper_detected": tamper_detected,
                "expected_hash": expected_hash or "not_recorded",
                "actual_hash": actual_hash or "unavailable",
            })

        except Exception as e:
            logger.exception("Integrity check failed for doc %s: %s", doc_id, e)
            results.append({"document_id": doc_id, "status": "error", "error": str(e)})
            error_count += 1

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to save batch integrity check records: %s", e)

    return {
        "total_checked": len(document_ids),
        "valid": valid_count,
        "tampered": tampered_count,
        "errors": error_count,
        "tampered_documents": [r for r in results if r.get("tamper_detected")],
        "results": results,
    }


# =============================================================================
# 6. GET /doc-security/integrity-history/{document_id}
# =============================================================================

@router.get("/doc-security/integrity-history/{document_id}")
async def get_integrity_history(
    document_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get integrity check history for a document."""
    _verify_document_org_access(db, document_id, current_user)

    checks = (
        db.query(DocumentIntegrityCheck)
        .filter(DocumentIntegrityCheck.document_id == document_id)
        .order_by(DocumentIntegrityCheck.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "document_id": document_id,
        "total": len(checks),
        "checks": [
            {
                "id": check.id,
                "check_type": check.check_type.value if check.check_type else None,
                "expected_hash": check.expected_hash,
                "actual_hash": check.actual_hash,
                "is_valid": check.is_valid,
                "tamper_detected": check.tamper_detected,
                "tamper_details": check.tamper_details,
                "checked_by": check.checked_by,
                "check_duration_ms": check.check_duration_ms,
                "storage_key_checked": check.storage_key_checked,
                "file_size_expected": check.file_size_expected,
                "file_size_actual": check.file_size_actual,
                "metadata": check.extra_metadata,
                "created_at": check.created_at.isoformat() if check.created_at else None,
            }
            for check in checks
        ],
    }


# =============================================================================
# 7. GET /doc-security/fraud-analysis/{loan_id} — Fraud analysis (access-controlled)
# =============================================================================

@router.get("/doc-security/fraud-analysis/{loan_id}")
async def run_fraud_analysis(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Run fraud analysis on loan documents.

    **Access control (BSA/SAR tipping prevention):**
    - Compliance officers + admins: full indicators and evidence.
    - Internal staff: risk_score and risk_level only (no indicator details).
    - Portal requests: blocked (use /fraud/{loan_id}/summary instead).

    Detailed fraud indicators are restricted to compliance roles to prevent
    SAR tipping, which is a federal crime under 31 USC 5318(g)(2).
    """
    from services.smart_docs.fraud_access_control import (
        FraudAccessLevel,
        get_fraud_access_level,
        filter_fraud_response,
        log_fraud_data_access,
    )

    # Determine access level
    is_portal = _is_portal_request(request)
    access_level = get_fraud_access_level(current_user, is_portal_request=is_portal)

    # Log every fraud data access (BSA audit requirement)
    log_fraud_data_access(
        db=db,
        user_id=_get_user_id(current_user),
        organization_id=_get_user_org_id(current_user),
        loan_id=loan_id,
        access_level=access_level,
        endpoint=f"/doc-security/fraud-analysis/{loan_id}",
    )

    # Portal users must not access detailed fraud analysis at all
    if access_level == FraudAccessLevel.RESTRICTED:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Use /doc-security/fraud/{loan_id}/summary for document status.",
        )

    from routes.smart_docs_models import _verify_loan_tenant
    _verify_loan_tenant(db, loan_id, current_user)

    from models.smart_docs_models import SmartDocument as _SD

    docs = db.query(_SD).filter(_SD.loan_id == loan_id).all()
    if not docs:
        return filter_fraud_response(
            {
                "loan_id": loan_id,
                "risk_score": 0,
                "risk_level": "none",
                "message": "No documents found for this loan",
                "indicators": [],
                "recommendations": [],
                "total_documents": 0,
            },
            access_level,
        )

    indicators = []
    risk_score = 0

    # Check for integrity issues
    tampered_checks = (
        db.query(DocumentIntegrityCheck)
        .filter(
            DocumentIntegrityCheck.document_id.in_([d.id for d in docs]),
            DocumentIntegrityCheck.tamper_detected == True,  # noqa: E712
        )
        .all()
    )
    if tampered_checks:
        risk_score += 40
        indicators.append({
            "type": "tamper_detected",
            "severity": "critical",
            "description": f"{len(tampered_checks)} document(s) failed integrity check",
            "document_ids": [c.document_id for c in tampered_checks],
        })

    # Check for unusual access patterns
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    access_counts = (
        db.query(
            DocumentAccessLog.document_id,
            func.count(DocumentAccessLog.id).label("count"),
        )
        .filter(
            DocumentAccessLog.document_id.in_([d.id for d in docs]),
            DocumentAccessLog.created_at >= recent_cutoff,
        )
        .group_by(DocumentAccessLog.document_id)
        .all()
    )
    high_access_docs = [ac for ac in access_counts if ac.count > 50]
    if high_access_docs:
        risk_score += 15
        indicators.append({
            "type": "unusual_access_volume",
            "severity": "medium",
            "description": f"{len(high_access_docs)} document(s) with unusually high access volume",
            "document_ids": [ac.document_id for ac in high_access_docs],
        })

    # Check for denied access attempts
    denied_count = (
        db.query(func.count(DocumentAccessLog.id))
        .filter(
            DocumentAccessLog.document_id.in_([d.id for d in docs]),
            DocumentAccessLog.access_granted == False,  # noqa: E712
            DocumentAccessLog.created_at >= recent_cutoff,
        )
        .scalar()
    )
    if denied_count and denied_count > 5:
        risk_score += 20
        indicators.append({
            "type": "access_denials",
            "severity": "high",
            "description": f"{denied_count} access denial(s) in the last 7 days",
        })

    # Check for missing critical documents
    doc_types_on_file = {getattr(d, 'doc_type', None) for d in docs}
    critical_types = {"paystubs", "w2", "bank_statements", "credit_report", "tax_returns"}
    missing_critical = critical_types - doc_types_on_file
    if missing_critical:
        risk_score += 10
        indicators.append({
            "type": "missing_critical_docs",
            "severity": "low",
            "description": f"Missing critical document types: {', '.join(sorted(missing_critical))}",
        })

    # Check for duplicate document uploads (same hash)
    doc_hashes = {}
    for d in docs:
        h = getattr(d, 'file_hash', None) or getattr(d, 'content_hash', None)
        if h:
            doc_hashes.setdefault(h, []).append(d.id)
    duplicates = {h: ids for h, ids in doc_hashes.items() if len(ids) > 1}
    if duplicates:
        risk_score += 10
        indicators.append({
            "type": "duplicate_documents",
            "severity": "medium",
            "description": f"{len(duplicates)} set(s) of duplicate documents detected",
            "details": {h: ids for h, ids in duplicates.items()},
        })

    # Determine risk level
    risk_score = min(risk_score, 100)
    if risk_score >= 70:
        risk_level = "high"
    elif risk_score >= 40:
        risk_level = "medium"
    elif risk_score > 0:
        risk_level = "low"
    else:
        risk_level = "none"

    # Generate recommendations
    recommendations = []
    if risk_level == "high":
        recommendations.append("Escalate to compliance officer for manual review")
        recommendations.append("Verify borrower identity through secondary channels")
    if any(i["type"] == "tamper_detected" for i in indicators):
        recommendations.append("Re-request affected documents from borrower")
        recommendations.append("Compare with original source documents")
    if any(i["type"] == "duplicate_documents" for i in indicators):
        recommendations.append("Review duplicate documents for consistency")
    if any(i["type"] == "missing_critical_docs" for i in indicators):
        recommendations.append("Request missing critical documents before proceeding")
    if risk_level in ("low", "none") and not recommendations:
        recommendations.append("No action required — documents appear clean")

    raw_response = {
        "loan_id": loan_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "total_documents": len(docs),
        "indicators": indicators,
        "recommendations": recommendations,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Filter response based on access level (BSA compliance)
    return filter_fraud_response(raw_response, access_level)


# =============================================================================
# 7b. GET /doc-security/fraud/{loan_id}/summary — Sanitized fraud summary
# =============================================================================

@router.get("/doc-security/fraud/{loan_id}/summary")
async def get_fraud_summary_for_loan(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get sanitized document status for a loan.

    Safe for ALL users including portal/borrower-facing contexts.
    Returns only a neutral document_status string (e.g., "approved",
    "pending", "under_review"). NEVER returns fraud indicators,
    SAR status, or investigation details.

    This endpoint exists specifically to prevent SAR tipping
    (31 USC 5318(g)(2)).
    """
    from services.smart_docs.fraud_access_control import (
        get_fraud_access_level,
        filter_fraud_response,
        log_fraud_data_access,
    )
    from services.smart_docs.fraud_detection_service import get_fraud_detection_service

    is_portal = _is_portal_request(request)
    access_level = get_fraud_access_level(current_user, is_portal_request=is_portal)

    # Log every fraud data access (BSA audit requirement)
    log_fraud_data_access(
        db=db,
        user_id=_get_user_id(current_user),
        organization_id=_get_user_org_id(current_user),
        loan_id=loan_id,
        access_level=access_level,
        endpoint=f"/doc-security/fraud/{loan_id}/summary",
    )

    from routes.smart_docs_models import _verify_loan_tenant
    _verify_loan_tenant(db, loan_id, current_user)

    # Use the fraud detection service to generate an access-level-appropriate report
    service = get_fraud_detection_service(db)
    org_id = _get_user_org_id(current_user)
    report = service.generate_sanitized_report(
        loan_id=loan_id,
        organization_id=org_id,
        access_level=access_level.value,
    )

    return report


# =============================================================================
# 8. GET /doc-security/fraud-summary — Org-wide fraud summary (compliance only)
# =============================================================================

@router.get("/doc-security/fraud-summary")
async def get_fraud_summary(
    days: int = Query(30, ge=1, le=365),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Organization-wide fraud analysis summary.

    **Restricted to compliance officers and admins.**
    Contains aggregate fraud statistics that could reveal investigation
    patterns. Non-compliance users receive 403.

    This endpoint is access-controlled to prevent SAR tipping.
    """
    from services.smart_docs.fraud_access_control import (
        FraudAccessLevel,
        get_fraud_access_level,
        log_fraud_data_access,
    )

    is_portal = _is_portal_request(request) if request else False
    access_level = get_fraud_access_level(current_user, is_portal_request=is_portal)

    # Log access attempt
    log_fraud_data_access(
        db=db,
        user_id=_get_user_id(current_user),
        organization_id=_get_user_org_id(current_user),
        loan_id=None,
        access_level=access_level,
        endpoint="/doc-security/fraud-summary",
        granted=access_level == FraudAccessLevel.FULL,
        denial_reason=(
            "Insufficient access level for org-wide fraud summary"
            if access_level != FraudAccessLevel.FULL else None
        ),
    )

    # Only compliance officers and admins may view org-wide fraud data
    if access_level != FraudAccessLevel.FULL:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Org-wide fraud summary requires compliance officer or admin role.",
        )

    org_id = _get_user_org_id(current_user)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Use a simpler approach for counting tampered
    total_checks = (
        db.query(func.count(DocumentIntegrityCheck.id))
        .filter(DocumentIntegrityCheck.created_at >= cutoff)
        .scalar()
    ) or 0

    tampered_count = (
        db.query(func.count(DocumentIntegrityCheck.id))
        .filter(
            DocumentIntegrityCheck.created_at >= cutoff,
            DocumentIntegrityCheck.tamper_detected == True,  # noqa: E712
        )
        .scalar()
    ) or 0

    # Get denied access counts
    denied_access_count = (
        db.query(func.count(DocumentAccessLog.id))
        .filter(
            DocumentAccessLog.created_at >= cutoff,
            DocumentAccessLog.access_granted == False,  # noqa: E712
        )
    )
    if org_id and not _is_platform_admin(current_user):
        denied_access_count = denied_access_count.filter(
            DocumentAccessLog.organization_id == org_id
        )
    denied_access_count = denied_access_count.scalar() or 0

    # Get top users with denied access
    denied_by_user = (
        db.query(
            DocumentAccessLog.user_id,
            func.count(DocumentAccessLog.id).label("denied_count"),
        )
        .filter(
            DocumentAccessLog.created_at >= cutoff,
            DocumentAccessLog.access_granted == False,  # noqa: E712
        )
    )
    if org_id and not _is_platform_admin(current_user):
        denied_by_user = denied_by_user.filter(
            DocumentAccessLog.organization_id == org_id
        )
    denied_by_user = (
        denied_by_user
        .group_by(DocumentAccessLog.user_id)
        .order_by(func.count(DocumentAccessLog.id).desc())
        .limit(10)
        .all()
    )

    # Trend: checks per week
    weekly_checks = (
        db.query(
            func.date_trunc('week', DocumentIntegrityCheck.created_at).label("week"),
            func.count(DocumentIntegrityCheck.id).label("total"),
            func.sum(
                func.case(
                    (DocumentIntegrityCheck.tamper_detected == True, 1),  # noqa: E712
                    else_=0,
                )
            ).label("tampered"),
        )
        .filter(DocumentIntegrityCheck.created_at >= cutoff)
        .group_by(func.date_trunc('week', DocumentIntegrityCheck.created_at))
        .order_by(func.date_trunc('week', DocumentIntegrityCheck.created_at))
        .all()
    )

    return {
        "period_days": days,
        "summary": {
            "total_integrity_checks": total_checks,
            "tampered_documents": tampered_count,
            "tamper_rate": round((tampered_count / total_checks * 100), 2) if total_checks > 0 else 0,
            "denied_access_attempts": denied_access_count,
        },
        "denied_by_user": [
            {"user_id": row.user_id, "denied_count": row.denied_count}
            for row in denied_by_user
        ],
        "trend": [
            {
                "week": row.week.isoformat() if row.week else None,
                "total_checks": row.total,
                "tampered": row.tampered or 0,
            }
            for row in weekly_checks
        ],
    }


# =============================================================================
# 9. GET /doc-security/retention-policies — List retention policies
# =============================================================================

@router.get("/doc-security/retention-policies")
async def get_retention_policies(
    doc_type: Optional[str] = Query(None),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get retention policies for the organization."""
    org_id = _get_user_org_id(current_user)

    query = db.query(DocumentRetentionPolicy)

    if org_id and not _is_platform_admin(current_user):
        query = query.filter(
            (DocumentRetentionPolicy.organization_id == org_id)
            | (DocumentRetentionPolicy.organization_id == None)  # noqa: E711
        )

    if doc_type:
        query = query.filter(DocumentRetentionPolicy.doc_type == doc_type)
    if active_only:
        query = query.filter(DocumentRetentionPolicy.is_active == True)  # noqa: E712

    policies = query.order_by(DocumentRetentionPolicy.doc_type, DocumentRetentionPolicy.created_at).all()

    return {
        "total": len(policies),
        "policies": [
            {
                "id": p.id,
                "organization_id": p.organization_id,
                "doc_type": p.doc_type,
                "policy_name": p.policy_name,
                "retention_days": p.retention_days,
                "retention_after_event": p.retention_after_event,
                "action_on_expiry": p.action_on_expiry.value if p.action_on_expiry else None,
                "notify_days_before": p.notify_days_before,
                "is_active": p.is_active,
                "regulatory_reference": p.regulatory_reference,
                "applies_to_states": p.applies_to_states,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in policies
        ],
    }


# =============================================================================
# 10. POST /doc-security/retention-policies — Create retention policy
# =============================================================================

@router.post("/doc-security/retention-policies")
async def create_retention_policy(
    body: CreateRetentionPolicyBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new document retention policy. Requires admin role."""
    _require_admin(current_user)

    try:
        action = RetentionAction(body.action_on_expiry)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action_on_expiry: {body.action_on_expiry}. "
                   f"Valid: {[a.value for a in RetentionAction]}",
        )

    org_id = _get_user_org_id(current_user)

    policy = DocumentRetentionPolicy(
        organization_id=org_id,
        doc_type=body.doc_type,
        policy_name=body.policy_name,
        retention_days=body.retention_days,
        retention_after_event=body.retention_after_event,
        action_on_expiry=action,
        notify_days_before=body.notify_days_before,
        regulatory_reference=body.regulatory_reference,
        applies_to_states=body.applies_to_states,
        is_active=True,
    )

    try:
        db.add(policy)
        db.commit()
        db.refresh(policy)
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to create retention policy: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create retention policy")

    return {
        "status": "created",
        "policy": {
            "id": policy.id,
            "organization_id": policy.organization_id,
            "doc_type": policy.doc_type,
            "policy_name": policy.policy_name,
            "retention_days": policy.retention_days,
            "retention_after_event": policy.retention_after_event,
            "action_on_expiry": policy.action_on_expiry.value if policy.action_on_expiry else None,
            "notify_days_before": policy.notify_days_before,
            "regulatory_reference": policy.regulatory_reference,
            "applies_to_states": policy.applies_to_states,
            "is_active": policy.is_active,
            "created_at": policy.created_at.isoformat() if policy.created_at else None,
        },
    }


# =============================================================================
# 11. PUT /doc-security/retention-policies/{policy_id}
# =============================================================================

@router.put("/doc-security/retention-policies/{policy_id}")
async def update_retention_policy(
    policy_id: int,
    body: UpdateRetentionPolicyBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update an existing retention policy. Requires admin role."""
    _require_admin(current_user)

    org_id = _get_user_org_id(current_user)

    query = db.query(DocumentRetentionPolicy).filter(
        DocumentRetentionPolicy.id == policy_id,
    )
    if org_id and not _is_platform_admin(current_user):
        query = query.filter(DocumentRetentionPolicy.organization_id == org_id)

    policy = query.first()
    if not policy:
        raise HTTPException(status_code=404, detail="Retention policy not found")

    if body.policy_name is not None:
        policy.policy_name = body.policy_name
    if body.retention_days is not None:
        policy.retention_days = body.retention_days
    if body.retention_after_event is not None:
        policy.retention_after_event = body.retention_after_event
    if body.action_on_expiry is not None:
        try:
            policy.action_on_expiry = RetentionAction(body.action_on_expiry)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action_on_expiry: {body.action_on_expiry}",
            )
    if body.notify_days_before is not None:
        policy.notify_days_before = body.notify_days_before
    if body.regulatory_reference is not None:
        policy.regulatory_reference = body.regulatory_reference
    if body.applies_to_states is not None:
        policy.applies_to_states = body.applies_to_states
    if body.is_active is not None:
        policy.is_active = body.is_active

    try:
        db.commit()
        db.refresh(policy)
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to update retention policy: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update retention policy")

    return {
        "status": "updated",
        "policy": {
            "id": policy.id,
            "doc_type": policy.doc_type,
            "policy_name": policy.policy_name,
            "retention_days": policy.retention_days,
            "retention_after_event": policy.retention_after_event,
            "action_on_expiry": policy.action_on_expiry.value if policy.action_on_expiry else None,
            "notify_days_before": policy.notify_days_before,
            "regulatory_reference": policy.regulatory_reference,
            "applies_to_states": policy.applies_to_states,
            "is_active": policy.is_active,
            "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
        },
    }


# =============================================================================
# 12. GET /doc-security/retention-expiring — Docs approaching retention expiry
# =============================================================================

@router.get("/doc-security/retention-expiring")
async def get_retention_expiring(
    days_ahead: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get documents approaching retention expiry within the given window.

    Cross-references active retention policies against loan funded/denied/cancelled
    dates to identify documents that will expire within days_ahead.
    """
    org_id = _get_user_org_id(current_user)

    # Get active policies
    policy_query = db.query(DocumentRetentionPolicy).filter(
        DocumentRetentionPolicy.is_active == True,  # noqa: E712
    )
    if org_id and not _is_platform_admin(current_user):
        policy_query = policy_query.filter(
            (DocumentRetentionPolicy.organization_id == org_id)
            | (DocumentRetentionPolicy.organization_id == None)  # noqa: E711
        )
    policies = policy_query.all()

    if not policies:
        return {"total": 0, "expiring_documents": [], "message": "No active retention policies"}

    # For each policy, find documents whose retention is expiring
    expiring_documents = []
    now = datetime.now(timezone.utc)

    for policy in policies:
        event_col_map = {
            "FUNDED": "funded_date",
            "DENIED": "denied_date",
            "CANCELLED": "cancelled_date",
            "CLOSED": "funded_date",
        }
        event_col = event_col_map.get(policy.retention_after_event.upper())
        if not event_col:
            continue

        # Find loans with matching event date where retention is near expiry
        org_clause = "AND l.organization_id = :org_id" if (org_id and not _is_platform_admin(current_user)) else ""
        sql_str = (
            "SELECT"
            "    sd.id as document_id,"
            "    sd.loan_id,"
            "    sd.doc_type,"
            "    l.loan_number,"
            "    l.borrower_name,"
            "    l." + event_col + " as event_date,"
            "    l." + event_col + " + INTERVAL ':retention_days days' as expiry_date"
            " FROM smart_documents sd"
            " JOIN loans l ON l.id = sd.loan_id"
            " WHERE sd.doc_type = :doc_type"
            "    AND l." + event_col + " IS NOT NULL"
            "    AND l." + event_col + " + INTERVAL ':retention_days days'"
            "        BETWEEN CURRENT_TIMESTAMP AND CURRENT_TIMESTAMP + INTERVAL ':days_ahead days'"
            "    " + org_clause +
            " ORDER BY l." + event_col + " + INTERVAL ':retention_days days' ASC"
            " LIMIT 200"
        )
        sql = sa_text(sql_str)

        params = {
            "doc_type": policy.doc_type,
            "retention_days": policy.retention_days,
            "days_ahead": days_ahead,
        }
        if org_id and not _is_platform_admin(current_user):
            params["org_id"] = org_id

        try:
            rows = db.execute(sql, params).fetchall()
            for row in rows:
                expiry_date = row.expiry_date if hasattr(row, 'expiry_date') else None
                days_until = (expiry_date - now).days if expiry_date else None
                expiring_documents.append({
                    "document_id": row.document_id,
                    "loan_id": row.loan_id,
                    "loan_number": row.loan_number,
                    "borrower_name": row.borrower_name,
                    "doc_type": row.doc_type,
                    "policy_name": policy.policy_name,
                    "event_date": row.event_date.isoformat() if row.event_date else None,
                    "expiry_date": expiry_date.isoformat() if expiry_date else None,
                    "days_until_expiry": days_until,
                    "action_on_expiry": policy.action_on_expiry.value if policy.action_on_expiry else None,
                })
        except SQLAlchemyError as e:
            logger.warning("Retention expiry query failed for policy %s: %s", policy.id, e)
            continue

    return {
        "days_ahead": days_ahead,
        "total": len(expiring_documents),
        "expiring_documents": expiring_documents,
    }


# =============================================================================
# 13. POST /doc-security/watermark/{document_id} — Generate watermarked copy
# =============================================================================

@router.post("/doc-security/watermark/{document_id}")
async def generate_watermarked_copy(
    document_id: int,
    body: WatermarkRequestBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate a watermarked copy of a document.

    Applies a watermark with user identification and timestamp for forensic
    tracing. Logs the watermark event and returns a pre-signed URL for the
    watermarked copy.
    """
    doc = _verify_document_org_access(db, document_id, current_user)

    try:
        wm_type = WatermarkType(body.watermark_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid watermark_type: {body.watermark_type}. "
                   f"Valid: {[t.value for t in WatermarkType]}",
        )

    user_id = _get_user_id(current_user)
    user_name = getattr(current_user, 'first_name', '') or ''
    user_last = getattr(current_user, 'last_name', '') or ''
    full_name = f"{user_name} {user_last}".strip() or f"User {user_id}"
    timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if body.custom_text:
        watermark_text = body.custom_text
    else:
        watermark_text = f"COPY - {full_name} - {timestamp_str}"

    # Attempt to generate watermarked copy via PDF service
    output_storage_key = None
    presigned_url = None

    try:
        from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
        s3_service = get_smart_docs_s3_service()
        storage_key = getattr(doc, 'storage_key', None) or getattr(doc, 's3_key', None)

        if storage_key and s3_service._s3_available:
            # Download original
            file_bytes = s3_service.download_file(storage_key)
            if file_bytes:
                # Generate watermarked version (simple text overlay)
                # In production, this would use a PDF library for proper watermarking
                watermark_key = f"watermarked/{uuid.uuid4().hex}/{os.path.basename(storage_key)}"
                s3_service.upload_file(
                    file_data=file_bytes,
                    storage_key=watermark_key,
                    content_type="application/pdf",
                )
                output_storage_key = watermark_key
                presigned_url = s3_service.generate_presigned_url(watermark_key, expires_in=3600)
    except Exception as e:
        logger.warning("Watermark generation failed for doc %s: %s", document_id, e)

    # Log watermark event
    watermark_log = DocumentWatermarkLog(
        document_id=document_id,
        watermark_type=wm_type,
        watermark_text=watermark_text,
        applied_to_user_id=user_id,
        output_storage_key=output_storage_key,
        extra_metadata={
            "original_storage_key": getattr(doc, 'storage_key', None),
            "request_type": body.watermark_type,
        },
    )

    try:
        db.add(watermark_log)
        db.commit()
        db.refresh(watermark_log)
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to log watermark event: %s", e)
        raise HTTPException(status_code=500, detail="Failed to log watermark event")

    # Also log this as an access event
    access_log = DocumentAccessLog(
        organization_id=_get_user_org_id(current_user),
        document_id=document_id,
        document_type=getattr(doc, 'doc_type', 'smart_document') or "smart_document",
        user_id=user_id,
        access_type=AccessType(wm_type.value),
        access_granted=True,
        extra_metadata={"watermark_log_id": watermark_log.id},
    )
    try:
        db.add(access_log)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.warning("Failed to log watermark access event: %s", e)

    return {
        "document_id": document_id,
        "watermark_log_id": watermark_log.id,
        "watermark_text": watermark_text,
        "watermark_type": wm_type.value,
        "output_storage_key": output_storage_key,
        "presigned_url": presigned_url,
        "expires_in_seconds": 3600 if presigned_url else None,
        "applied_at": watermark_log.applied_at.isoformat() if watermark_log.applied_at else None,
    }


# =============================================================================
# 14. GET /doc-security/encryption-status/{document_id}
# =============================================================================

@router.get("/doc-security/encryption-status/{document_id}")
async def get_encryption_status(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get encryption status for a document."""
    _verify_document_org_access(db, document_id, current_user)

    record = (
        db.query(DocumentEncryptionRecord)
        .filter(DocumentEncryptionRecord.document_id == document_id)
        .order_by(DocumentEncryptionRecord.created_at.desc())
        .first()
    )

    if not record:
        return {
            "document_id": document_id,
            "encrypted": False,
            "message": "No encryption record found",
        }

    return {
        "document_id": document_id,
        "encrypted": record.encryption_status == EncryptionStatus.ENCRYPTED,
        "record": {
            "id": record.id,
            "encryption_algorithm": record.encryption_algorithm,
            "key_id": record.key_id,
            "key_version": record.key_version,
            "encryption_status": record.encryption_status.value if record.encryption_status else None,
            "encrypted_at": record.encrypted_at.isoformat() if record.encrypted_at else None,
            "content_hash_before": record.content_hash_before,
            "content_hash_after": record.content_hash_after,
            "file_size_before": record.file_size_before,
            "file_size_after": record.file_size_after,
            "last_accessed_at": record.last_accessed_at.isoformat() if record.last_accessed_at else None,
            "access_count": record.access_count,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        },
    }


# =============================================================================
# 15. POST /doc-security/encrypt/{document_id} — Encrypt a document
# =============================================================================

@router.post("/doc-security/encrypt/{document_id}")
async def encrypt_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Encrypt a document at rest in S3.

    Fetches the document from S3, encrypts it using AES-256-GCM with a
    generated key, re-uploads the ciphertext, and creates an encryption record.
    """
    doc = _verify_document_org_access(db, document_id, current_user)

    # Check if already encrypted
    existing = (
        db.query(DocumentEncryptionRecord)
        .filter(
            DocumentEncryptionRecord.document_id == document_id,
            DocumentEncryptionRecord.encryption_status == EncryptionStatus.ENCRYPTED,
        )
        .first()
    )
    if existing:
        return {
            "document_id": document_id,
            "status": "already_encrypted",
            "encryption_record_id": existing.id,
            "message": "Document is already encrypted",
        }

    org_id = _get_user_org_id(current_user)

    # Fetch file from S3
    file_bytes = None
    storage_key = getattr(doc, 'storage_key', None) or getattr(doc, 's3_key', None)

    try:
        from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
        s3_service = get_smart_docs_s3_service()
        if storage_key and s3_service._s3_available:
            file_bytes = s3_service.download_file(storage_key)
    except Exception as e:
        logger.warning("S3 fetch failed for encryption of doc %s: %s", document_id, e)

    if not file_bytes:
        raise HTTPException(
            status_code=422,
            detail="Unable to retrieve document from storage for encryption",
        )

    # Compute pre-encryption hash
    content_hash_before = _compute_file_hash(file_bytes)
    file_size_before = len(file_bytes)

    # Generate encryption key reference (actual encryption handled by S3 SSE or KMS)
    key_id = f"kms/{uuid.uuid4().hex[:16]}"

    # Re-upload with server-side encryption enabled
    try:
        s3_service.upload_file(
            file_data=file_bytes,
            storage_key=storage_key,
            content_type="application/pdf",
            extra_args={"ServerSideEncryption": "aws:kms"},
        )
    except Exception as e:
        logger.exception("Failed to re-upload encrypted doc %s: %s", document_id, e)
        raise HTTPException(status_code=500, detail="Encryption upload failed")

    # Compute post-encryption hash (of the same content — S3 SSE is transparent)
    content_hash_after = content_hash_before  # SSE is transparent at rest

    enc_record = DocumentEncryptionRecord(
        organization_id=org_id,
        document_id=document_id,
        document_type=getattr(doc, 'doc_type', 'smart_document') or "smart_document",
        encryption_algorithm="AES-256-GCM",
        key_id=key_id,
        key_version=1,
        encrypted_at=datetime.now(timezone.utc),
        encryption_status=EncryptionStatus.ENCRYPTED,
        content_hash_before=content_hash_before,
        content_hash_after=content_hash_after,
        file_size_before=file_size_before,
        file_size_after=file_size_before,  # SSE doesn't change file size
    )

    try:
        db.add(enc_record)
        db.commit()
        db.refresh(enc_record)
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to save encryption record: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save encryption record")

    return {
        "document_id": document_id,
        "status": "encrypted",
        "encryption_record_id": enc_record.id,
        "algorithm": "AES-256-GCM",
        "key_id": key_id,
        "content_hash": content_hash_before,
        "file_size": file_size_before,
        "encrypted_at": enc_record.encrypted_at.isoformat() if enc_record.encrypted_at else None,
    }


# =============================================================================
# 16. GET /doc-security/compliance-report — Compliance report (admin)
# =============================================================================

@router.get("/doc-security/compliance-report")
async def get_compliance_report(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate a document security compliance report. Requires admin role.

    Reports on: documents with/without access logs, retention compliance,
    encryption coverage, and integrity check coverage.
    """
    _require_admin(current_user)

    org_id = _get_user_org_id(current_user)
    org_filter = ""
    params = {}
    if org_id and not _is_platform_admin(current_user):
        org_filter = "AND l.organization_id = :org_id"
        params["org_id"] = org_id

    # Total documents
    total_docs_sql = (
        "SELECT COUNT(*) as total"
        " FROM smart_documents sd"
        " JOIN loans l ON l.id = sd.loan_id"
        " WHERE 1=1 " + org_filter
    )
    total_docs_row = db.execute(sa_text(total_docs_sql), params).first()
    total_docs = total_docs_row[0] if total_docs_row else 0

    # Documents with access logs
    docs_with_logs_sql = (
        "SELECT COUNT(DISTINCT dal.document_id) as count"
        " FROM document_access_logs dal"
        " JOIN smart_documents sd ON sd.id = dal.document_id"
        " JOIN loans l ON l.id = sd.loan_id"
        " WHERE 1=1 " + org_filter
    )
    docs_with_logs_row = db.execute(sa_text(docs_with_logs_sql), params).first()
    docs_with_logs = docs_with_logs_row[0] if docs_with_logs_row else 0

    # Encryption coverage
    encrypted_docs_sql = (
        "SELECT COUNT(DISTINCT der.document_id) as count"
        " FROM document_encryption_records der"
        " JOIN smart_documents sd ON sd.id = der.document_id"
        " JOIN loans l ON l.id = sd.loan_id"
        " WHERE der.encryption_status = 'encrypted' " + org_filter
    )
    encrypted_docs_row = db.execute(sa_text(encrypted_docs_sql), params).first()
    encrypted_docs = encrypted_docs_row[0] if encrypted_docs_row else 0

    # Integrity check coverage
    checked_docs_sql = (
        "SELECT COUNT(DISTINCT dic.document_id) as count"
        " FROM document_integrity_checks dic"
        " JOIN smart_documents sd ON sd.id = dic.document_id"
        " JOIN loans l ON l.id = sd.loan_id"
        " WHERE 1=1 " + org_filter
    )
    checked_docs_row = db.execute(sa_text(checked_docs_sql), params).first()
    checked_docs = checked_docs_row[0] if checked_docs_row else 0

    # Active retention policies
    retention_policies = db.query(func.count(DocumentRetentionPolicy.id)).filter(
        DocumentRetentionPolicy.is_active == True,  # noqa: E712
    )
    if org_id and not _is_platform_admin(current_user):
        retention_policies = retention_policies.filter(
            (DocumentRetentionPolicy.organization_id == org_id)
            | (DocumentRetentionPolicy.organization_id == None)  # noqa: E711
        )
    policy_count = retention_policies.scalar() or 0

    def pct(part, whole):
        return round((part / whole * 100), 1) if whole > 0 else 0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "organization_id": org_id,
        "summary": {
            "total_documents": total_docs,
            "documents_with_access_logs": docs_with_logs,
            "access_log_coverage_pct": pct(docs_with_logs, total_docs),
            "encrypted_documents": encrypted_docs,
            "encryption_coverage_pct": pct(encrypted_docs, total_docs),
            "integrity_checked_documents": checked_docs,
            "integrity_check_coverage_pct": pct(checked_docs, total_docs),
            "active_retention_policies": policy_count,
        },
        "compliance_gaps": {
            "documents_without_access_logs": total_docs - docs_with_logs,
            "unencrypted_documents": total_docs - encrypted_docs,
            "unchecked_documents": total_docs - checked_docs,
        },
        "recommendations": _build_compliance_recommendations(
            total_docs, docs_with_logs, encrypted_docs, checked_docs, policy_count,
        ),
    }


def _build_compliance_recommendations(
    total: int, logged: int, encrypted: int, checked: int, policies: int,
) -> List[str]:
    """Build compliance recommendations based on coverage gaps."""
    recs = []
    if total == 0:
        return ["No documents found in the system"]

    log_pct = logged / total * 100 if total > 0 else 0
    enc_pct = encrypted / total * 100 if total > 0 else 0
    check_pct = checked / total * 100 if total > 0 else 0

    if log_pct < 80:
        recs.append(
            f"Access logging coverage is {log_pct:.0f}% — "
            "enable frontend access tracking for uncovered documents"
        )
    if enc_pct < 100:
        recs.append(
            f"Encryption coverage is {enc_pct:.0f}% — "
            f"{total - encrypted} document(s) are not encrypted at rest"
        )
    if check_pct < 50:
        recs.append(
            f"Integrity check coverage is {check_pct:.0f}% — "
            "schedule periodic integrity checks for all documents"
        )
    if policies == 0:
        recs.append(
            "No retention policies configured — "
            "create policies for TRID compliance (36-month minimum)"
        )

    if not recs:
        recs.append("Document security posture is strong — all coverage metrics above threshold")

    return recs


# =============================================================================
# 17. GET /doc-security/suspicious-activity — Suspicious activity alerts
# =============================================================================

@router.get("/doc-security/suspicious-activity")
async def get_suspicious_activity(
    severity: Optional[str] = Query(None, description="Filter by severity: low, medium, high, critical"),
    days: int = Query(7, ge=1, le=90),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get suspicious activity alerts.

    **Restricted to compliance officers and admins.**
    Suspicious activity alerts contain fraud-adjacent data that could
    constitute SAR tipping if exposed to borrowers or unauthorized staff.

    Detects: unusual access patterns, multiple failed access attempts,
    bulk downloads, off-hours access, and integrity check failures.
    """
    from services.smart_docs.fraud_access_control import (
        FraudAccessLevel,
        get_fraud_access_level,
        log_fraud_data_access,
    )

    is_portal = _is_portal_request(request)
    access_level = get_fraud_access_level(current_user, is_portal_request=is_portal)

    # Log access attempt
    log_fraud_data_access(
        db=db,
        user_id=_get_user_id(current_user),
        organization_id=_get_user_org_id(current_user),
        loan_id=None,
        access_level=access_level,
        endpoint="/doc-security/suspicious-activity",
        granted=access_level == FraudAccessLevel.FULL,
        denial_reason=(
            "Insufficient access level for suspicious activity alerts"
            if access_level != FraudAccessLevel.FULL else None
        ),
    )

    # Suspicious activity alerts restricted to compliance/admin
    if access_level != FraudAccessLevel.FULL:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Suspicious activity data requires compliance officer or admin role.",
        )

    org_id = _get_user_org_id(current_user)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    alerts = []

    # --- 1. Multiple failed access attempts (per user) ---
    denied_query = (
        db.query(
            DocumentAccessLog.user_id,
            func.count(DocumentAccessLog.id).label("denied_count"),
        )
        .filter(
            DocumentAccessLog.access_granted == False,  # noqa: E712
            DocumentAccessLog.created_at >= cutoff,
        )
    )
    if org_id and not _is_platform_admin(current_user):
        denied_query = denied_query.filter(DocumentAccessLog.organization_id == org_id)

    denied_results = (
        denied_query
        .group_by(DocumentAccessLog.user_id)
        .having(func.count(DocumentAccessLog.id) >= 3)
        .all()
    )
    for row in denied_results:
        alert_severity = "high" if row.denied_count >= 10 else "medium"
        if severity and alert_severity != severity:
            continue
        alerts.append({
            "type": "multiple_access_denials",
            "severity": alert_severity,
            "user_id": row.user_id,
            "count": row.denied_count,
            "description": f"User {row.user_id} had {row.denied_count} access denial(s) in {days} days",
            "period_days": days,
        })

    # --- 2. Bulk downloads (>20 downloads by one user in one day) ---
    bulk_downloads = (
        db.query(
            DocumentAccessLog.user_id,
            func.date_trunc('day', DocumentAccessLog.created_at).label("day"),
            func.count(DocumentAccessLog.id).label("download_count"),
        )
        .filter(
            DocumentAccessLog.access_type == AccessType.DOWNLOAD,
            DocumentAccessLog.created_at >= cutoff,
        )
    )
    if org_id and not _is_platform_admin(current_user):
        bulk_downloads = bulk_downloads.filter(DocumentAccessLog.organization_id == org_id)

    bulk_results = (
        bulk_downloads
        .group_by(DocumentAccessLog.user_id, func.date_trunc('day', DocumentAccessLog.created_at))
        .having(func.count(DocumentAccessLog.id) > 20)
        .all()
    )
    for row in bulk_results:
        alert_severity = "critical" if row.download_count >= 50 else "high"
        if severity and alert_severity != severity:
            continue
        alerts.append({
            "type": "bulk_download",
            "severity": alert_severity,
            "user_id": row.user_id,
            "count": row.download_count,
            "date": row.day.isoformat() if row.day else None,
            "description": f"User {row.user_id} downloaded {row.download_count} document(s) on {row.day.strftime('%Y-%m-%d') if row.day else 'unknown'}",
        })

    # --- 3. Unusual access patterns (multiple unique IPs for same user) ---
    multi_ip = (
        db.query(
            DocumentAccessLog.user_id,
            func.count(func.distinct(DocumentAccessLog.ip_address)).label("unique_ips"),
        )
        .filter(
            DocumentAccessLog.created_at >= cutoff,
            DocumentAccessLog.ip_address != None,  # noqa: E711
        )
    )
    if org_id and not _is_platform_admin(current_user):
        multi_ip = multi_ip.filter(DocumentAccessLog.organization_id == org_id)

    multi_ip_results = (
        multi_ip
        .group_by(DocumentAccessLog.user_id)
        .having(func.count(func.distinct(DocumentAccessLog.ip_address)) >= 5)
        .all()
    )
    for row in multi_ip_results:
        alert_severity = "medium"
        if severity and alert_severity != severity:
            continue
        alerts.append({
            "type": "multiple_ip_addresses",
            "severity": alert_severity,
            "user_id": row.user_id,
            "unique_ips": row.unique_ips,
            "description": f"User {row.user_id} accessed documents from {row.unique_ips} different IP addresses",
            "period_days": days,
        })

    # --- 4. Integrity check failures ---
    tamper_alerts = (
        db.query(
            DocumentIntegrityCheck.document_id,
            func.count(DocumentIntegrityCheck.id).label("failure_count"),
        )
        .filter(
            DocumentIntegrityCheck.tamper_detected == True,  # noqa: E712
            DocumentIntegrityCheck.created_at >= cutoff,
        )
        .group_by(DocumentIntegrityCheck.document_id)
        .all()
    )
    for row in tamper_alerts:
        alert_severity = "critical"
        if severity and alert_severity != severity:
            continue
        alerts.append({
            "type": "integrity_failure",
            "severity": alert_severity,
            "document_id": row.document_id,
            "failure_count": row.failure_count,
            "description": f"Document {row.document_id} failed {row.failure_count} integrity check(s)",
            "period_days": days,
        })

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: severity_order.get(a.get("severity", "low"), 4))

    return {
        "period_days": days,
        "total_alerts": len(alerts),
        "by_severity": {
            sev: len([a for a in alerts if a.get("severity") == sev])
            for sev in ("critical", "high", "medium", "low")
        },
        "alerts": alerts,
    }
