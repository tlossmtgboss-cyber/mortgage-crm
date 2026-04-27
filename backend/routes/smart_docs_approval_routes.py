"""
Smart Docs Approval Routes

Document review, approve, reject, re-request workflow endpoints.
Also includes data extraction, field comparison, and apply-fields endpoints.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from database import get_db
from auth.dependencies import get_current_user
from models.smart_docs_models import (
    DocumentRequest, SmartDocument, RequestStatus, DocumentDecision,
)
from services.smart_docs.document_review_pipeline import DocumentReviewPipeline
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
from services.smart_docs.notification_service import SmartDocsNotificationService

from routes.smart_docs_models import (
    ManualReviewBody,
    RejectDocumentBody,
    ReRequestDocumentBody,
    ApplyFieldsBody,
    UpdateDocumentNameBody,
    ApproveDocumentBody,
    _verify_loan_tenant,
    _verify_document_tenant,
    _verify_request_tenant,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Smart Documents"],
)

# Roles allowed to perform document approval actions
APPROVAL_ROLES = {'admin', 'site_admin', 'processor', 'underwriter', 'closer', 'manager'}


def _require_approval_role(current_user) -> None:
    """Verify the user has a role that permits document approval actions.
    Raises 403 if the user lacks an appropriate role.
    """
    user_role = getattr(current_user, 'permission_role', '') or ''
    user_role_lower = user_role.lower().strip()

    # Platform admins always have access
    if user_role_lower == 'admin':
        return

    # Check against allowed roles
    if user_role_lower not in APPROVAL_ROLES:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to perform approval actions. Required role: processor, underwriter, or manager."
        )


# =============================================================================
# Manual Review & Reprocess
# =============================================================================

@router.post("/document/{document_id}/manual-review")
async def manual_review_document(
    document_id: int,
    body: ManualReviewBody,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Submit a manual review decision for a document."""
    _require_approval_role(current_user)
    _verify_document_tenant(db, document_id, current_user)
    pipeline = DocumentReviewPipeline(db)
    try:
        return pipeline.manual_review(
            document_id=document_id,
            decision=body.decision,
            reviewer=body.reviewer,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/document/{document_id}/reprocess")
async def reprocess_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Reprocess a document through the validation pipeline.

    Retrieves the file from S3 storage and runs it through screenshot detection,
    date extraction, and freshness validation again. Useful when:
    - Detection logic has been updated
    - A document was incorrectly rejected
    - Document metadata needs to be refreshed

    Returns:
        Updated processing result with new decision
    """
    _require_approval_role(current_user)
    _verify_document_tenant(db, document_id, current_user)
    pipeline = DocumentReviewPipeline(db)
    try:
        result = pipeline.reprocess_document(document_id)
        return pipeline.result_to_dict(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail="Bad request")


# =============================================================================
# Document Actions (Delete, Reject, Approve, Re-request)
# =============================================================================

@router.delete("/document/{document_id}")
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    reviewer: Optional[str] = Query(None, description="(deprecated) Use current_user instead"),
    reason: Optional[str] = Query(None, description="Reason for deletion"),
):
    """
    Delete (trash) a document.

    Sets the document status to DELETED and optionally deletes from S3.
    The document can be restored later if needed.
    """
    _require_approval_role(current_user)
    reviewer = reviewer or getattr(current_user, 'email', None) or 'Unknown'

    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Tenant isolation: verify document belongs to user's organization via loan
    if document.loan_id:
        _verify_loan_tenant(db, document.loan_id, current_user)

    # Store deletion info
    old_status = document.status
    document.status = "DELETED"
    document.reviewed_at = datetime.now(timezone.utc)
    document.reviewed_by = reviewer
    document.rejection_reason = reason or "Deleted by user"

    # Update linked request status if exists
    if document.request_id:
        request = db.query(DocumentRequest).filter(
            DocumentRequest.id == document.request_id
        ).first()
        if request:
            # Reset request to OPEN so borrower can re-upload
            request.status = RequestStatus.OPEN

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(f"Database error deleting document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete document")

    logger.info(f"Document {document_id} deleted by {reviewer} (was: {old_status})")

    return {
        "document_id": document_id,
        "status": "DELETED",
        "previous_status": old_status,
        "deleted_by": reviewer,
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "message": "Document deleted successfully"
    }


@router.post("/document/{document_id}/reject")
async def reject_document(
    document_id: int,
    body: RejectDocumentBody,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Reject a document with a reason.

    Sets the document status to REJECTED and stores the rejection reason.
    Updates the linked request to allow re-upload.
    """
    _require_approval_role(current_user)

    from models.smart_docs_models import RejectionCategory

    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Tenant isolation: verify document belongs to user's organization via loan
    if document.loan_id:
        _verify_loan_tenant(db, document.loan_id, current_user)

    # Update document status
    document.status = "REJECTED"
    document.decision = DocumentDecision.REJECT
    document.rejection_reason = body.reason
    document.reviewed_at = datetime.now(timezone.utc)
    document.reviewed_by = body.reviewer

    if body.rejection_category:
        try:
            document.rejection_category = RejectionCategory(body.rejection_category)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid rejection category: {body.rejection_category}. Valid: {[c.value for c in RejectionCategory]}",
            )

    # Update linked request to allow re-upload
    if document.request_id:
        request = db.query(DocumentRequest).filter(
            DocumentRequest.id == document.request_id
        ).first()
        if request:
            request.status = RequestStatus.OPEN

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(f"Database error rejecting document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject document")

    logger.info(f"Document {document_id} rejected by {body.reviewer}: {body.reason}")

    return {
        "document_id": document_id,
        "status": "REJECTED",
        "action": "rejected",
        "action_by": body.reviewer,
        "action_at": datetime.now(timezone.utc).isoformat(),
        "rejection_reason": body.reason,
        "rejection_category": body.rejection_category,
        "notes": None,
        "message": "Document rejected successfully",
    }


@router.post("/document/{document_id}/approve")
async def approve_document(
    document_id: int,
    body: Optional[ApproveDocumentBody] = None,
    reviewer: Optional[str] = Query(None, description="(deprecated) Use request body instead"),
    notes: Optional[str] = Query(None, description="(deprecated) Use request body instead"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Approve a document.

    Sets the document status to APPROVED and updates the linked request.
    """
    _require_approval_role(current_user)
    reviewer = (body.reviewer if body and body.reviewer else reviewer) or getattr(current_user, 'email', None) or 'Unknown'
    notes = (body.notes if body else None) or notes

    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Tenant isolation: verify document belongs to user's organization via loan
    if document.loan_id:
        _verify_loan_tenant(db, document.loan_id, current_user)

    # Update document status
    document.status = "APPROVED"
    document.decision = DocumentDecision.ACCEPT
    document.reviewed_at = datetime.now(timezone.utc)
    document.reviewed_by = reviewer

    # Update linked request
    if document.request_id:
        request = db.query(DocumentRequest).filter(
            DocumentRequest.id == document.request_id
        ).first()
        if request:
            request.status = RequestStatus.ACCEPTED
            request.completed_at = datetime.now(timezone.utc)
            request.fulfilled_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(f"Database error approving document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve document")

    logger.info(f"Document {document_id} approved by {reviewer}")

    return {
        "document_id": document_id,
        "status": "APPROVED",
        "action": "approved",
        "action_by": reviewer,
        "action_at": datetime.now(timezone.utc).isoformat(),
        "rejection_reason": None,
        "rejection_category": None,
        "notes": notes,
        "message": "Document approved successfully",
    }


@router.post("/request/{request_id}/re-request")
async def re_request_document(
    request_id: int,
    body: ReRequestDocumentBody,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Re-request a document (reset request to OPEN).

    Clears any linked documents and resets the request to allow fresh upload.
    Optionally sets a new due date.
    """
    from datetime import timedelta

    _verify_request_tenant(db, request_id, current_user)
    request = db.query(DocumentRequest).filter(
        DocumentRequest.id == request_id
    ).first()

    if not request:
        raise HTTPException(status_code=404, detail="Document request not found")

    old_status = request.status

    # Reset request status
    request.status = RequestStatus.OPEN
    request.updated_at = datetime.now(timezone.utc)

    if body.new_due_date:
        try:
            parsed_date = datetime.fromisoformat(body.new_due_date.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail=f"Invalid date format: {body.new_due_date}")
        if parsed_date < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Due date must be in the future")
        request.due_date = parsed_date
    elif not request.due_date or request.due_date < datetime.now(timezone.utc):
        # Default to 7 days from now
        request.due_date = datetime.now(timezone.utc) + timedelta(days=7)

    # Mark any linked documents as superseded
    linked_docs = db.query(SmartDocument).filter(
        SmartDocument.request_id == request_id,
        SmartDocument.status.notin_(["DELETED"])
    ).all()

    superseded_count = 0
    for doc in linked_docs:
        if doc.status not in ["APPROVED", "ACCEPTED"]:
            doc.status = "SUPERSEDED"
            doc.rejection_reason = f"Re-requested by {body.reviewer}"
            superseded_count += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(f"Database error re-requesting document request {request_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to re-request document")

    # Send notification to borrower
    try:
        notification_service = SmartDocsNotificationService(db)
        notification_service.send_request_reminder(request)
        notification_sent = True
    except SQLAlchemyError as e:
        logger.warning(f"Failed to send re-request notification: {e}")
        notification_sent = False

    logger.info(f"Request {request_id} re-requested by {body.reviewer} (was: {old_status})")

    return {
        "request_id": request_id,
        "status": "OPEN",
        "previous_status": old_status.value if hasattr(old_status, 'value') else str(old_status),
        "re_requested_by": body.reviewer,
        "re_requested_at": datetime.now(timezone.utc).isoformat(),
        "due_date": request.due_date.isoformat() if request.due_date else None,
        "superseded_documents": superseded_count,
        "notification_sent": notification_sent,
        "notes": body.notes,
        "message": "Document re-requested successfully"
    }


# =============================================================================
# Document Extraction & Review Endpoints
# =============================================================================

@router.post("/document/{document_id}/extract")
async def extract_document_data(
    document_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Trigger AI extraction for a document.

    Extracts structured data from the document using AI/OCR,
    including names for owner matching and values that can be
    applied to the Lead/Loan profile.
    """
    from models.document_extraction import SmartDocumentExtraction, ReviewStatus, DetectedOwner
    from services.smart_docs.document_data_extractor import get_document_data_extractor
    from services.smart_docs.owner_matcher import get_owner_matcher

    # Get the document
    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Tenant isolation: verify document belongs to user's organization via loan
    if document.loan_id:
        _verify_loan_tenant(db, document.loan_id, current_user)

    # Check if extraction already exists
    existing = db.query(SmartDocumentExtraction).filter(
        SmartDocumentExtraction.document_id == document_id
    ).first()

    if existing:
        # Return existing extraction
        return {
            "extraction_id": existing.id,
            "document_id": document_id,
            "extracted_fields": existing.extracted_fields or {},
            "confidence_scores": existing.confidence_scores or {},
            "provenance": existing.provenance or {},
            "mappable_fields": existing.mappable_fields or [],
            "field_categories": existing.field_categories or {},
            "detected_owner": existing.detected_owner.value if existing.detected_owner else "UNKNOWN",
            "owner_confidence": existing.owner_confidence or 0,
            "overall_confidence": existing.overall_confidence or 0,
            "review_status": existing.review_status.value if existing.review_status else "PENDING",
            "cached": True,
        }

    # Get file content from S3
    s3_service = get_smart_docs_s3_service()
    file_content = None

    if document.storage_key and s3_service.is_available:
        download_result = s3_service.download_file(document.storage_key)
        if download_result.get("success"):
            file_content = download_result.get("content")

    if not file_content:
        raise HTTPException(
            status_code=400,
            detail="Unable to retrieve document content for extraction"
        )

    # Run extraction
    extractor = get_document_data_extractor()
    result = extractor.extract(
        file_content=file_content,
        mime_type=document.mime_type,
        doc_type=document.doc_type,
        ocr_text=document.ocr_text,
    )

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {result.error}"
        )

    # Get borrower/co-borrower names for owner matching
    borrower_name = None
    co_borrower_name = None

    if document.loan_id:
        from sqlalchemy import text
        loan_info = db.execute(text("""
            SELECT borrower_name, coborrower_name FROM loans WHERE id = :loan_id
        """), {"loan_id": document.loan_id}).fetchone()

        if loan_info:
            borrower_name = loan_info.borrower_name
            co_borrower_name = loan_info.coborrower_name

    # Match owner
    owner_matcher = get_owner_matcher()
    owner_result = owner_matcher.match_owner(
        extracted_names=result.detected_names,
        borrower_name=borrower_name,
        co_borrower_name=co_borrower_name,
    )

    # Map owner string to enum
    owner_enum = DetectedOwner.UNKNOWN
    if owner_result.owner == "BORROWER":
        owner_enum = DetectedOwner.BORROWER
    elif owner_result.owner == "CO_BORROWER":
        owner_enum = DetectedOwner.CO_BORROWER

    # Store extraction result
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
    try:
        db.commit()
        db.refresh(extraction)
    except Exception as e:
        db.rollback()
        logger.exception(f"Database error saving extraction for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save extraction results")

    return {
        "extraction_id": extraction.id,
        "document_id": document_id,
        "extracted_fields": result.extracted_fields,
        "confidence_scores": result.confidence_scores,
        "provenance": result.provenance,
        "mappable_fields": result.mappable_fields,
        "field_categories": result.field_categories,
        "detected_owner": owner_result.owner,
        "owner_confidence": owner_result.confidence,
        "owner_match_details": owner_result.match_details,
        "overall_confidence": result.overall_confidence,
        "review_status": "PENDING",
        "extraction_duration_ms": result.extraction_duration_ms,
        "cached": False,
    }


@router.get("/document/{document_id}/extraction")
async def get_document_extraction(
    document_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get existing extraction results for a document."""
    _verify_document_tenant(db, document_id, current_user)
    from models.document_extraction import SmartDocumentExtraction

    extraction = db.query(SmartDocumentExtraction).filter(
        SmartDocumentExtraction.document_id == document_id
    ).first()

    if not extraction:
        raise HTTPException(
            status_code=404,
            detail="No extraction found. Trigger extraction first with POST /document/{id}/extract"
        )

    return {
        "extraction_id": extraction.id,
        "document_id": document_id,
        "extracted_fields": extraction.extracted_fields or {},
        "confidence_scores": extraction.confidence_scores or {},
        "provenance": extraction.provenance or {},
        "mappable_fields": extraction.mappable_fields or [],
        "field_categories": extraction.field_categories or {},
        "detected_owner": extraction.detected_owner.value if extraction.detected_owner else "UNKNOWN",
        "owner_confidence": extraction.owner_confidence or 0,
        "overall_confidence": extraction.overall_confidence or 0,
        "review_status": extraction.review_status.value if extraction.review_status else "PENDING",
        "reviewed_by": extraction.reviewed_by,
        "reviewed_at": extraction.reviewed_at.isoformat() if extraction.reviewed_at else None,
        "applied_fields": extraction.applied_fields,
        "created_at": extraction.created_at.isoformat() if extraction.created_at else None,
    }


@router.get("/document/{document_id}/comparison")
async def get_field_comparison(
    document_id: int,
    profile_type: str = Query(default="lead", description="Profile type: 'lead' or 'loan'"),
    profile_id: Optional[int] = Query(default=None, description="Profile ID to compare against"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Compare extracted data against existing profile data.

    Returns side-by-side comparison with differences highlighted.
    """
    _verify_document_tenant(db, document_id, current_user)
    from models.document_extraction import SmartDocumentExtraction, FIELD_TO_LEAD_MAPPING, FIELD_TO_LOAN_MAPPING

    # Get extraction
    extraction = db.query(SmartDocumentExtraction).filter(
        SmartDocumentExtraction.document_id == document_id
    ).first()

    if not extraction:
        raise HTTPException(
            status_code=404,
            detail="No extraction found. Trigger extraction first."
        )

    # Get document to find loan_id if profile_id not provided
    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not profile_id and document:
        profile_id = document.loan_id

    # Get current profile values
    current_values = {}
    from sqlalchemy import text

    if profile_type == "lead" and profile_id:
        lead_data = db.execute(text("""
            SELECT first_name, last_name, address, city, state, zip_code,
                   annual_income, employer_name, credit_score, email, phone
            FROM leads WHERE id = :id
        """), {"id": profile_id}).fetchone()

        if lead_data:
            current_values = dict(lead_data._mapping)
    elif profile_type == "loan" and profile_id:
        loan_data = db.execute(text("""
            SELECT borrower_name, property_address, property_city,
                   property_state, property_zip
            FROM loans WHERE id = :id
        """), {"id": profile_id}).fetchone()

        if loan_data:
            current_values = dict(loan_data._mapping)

    # Build comparison
    field_mapping = FIELD_TO_LEAD_MAPPING if profile_type == "lead" else FIELD_TO_LOAN_MAPPING
    extracted_fields = extraction.extracted_fields or {}
    confidence_scores = extraction.confidence_scores or {}

    comparison = []
    for field_name, extracted_value in extracted_fields.items():
        profile_field = field_mapping.get(field_name)
        current_value = current_values.get(profile_field) if profile_field else None

        # Determine if there's a conflict
        has_conflict = False
        if current_value and extracted_value:
            # Normalize for comparison
            current_str = str(current_value).strip().lower()
            extracted_str = str(extracted_value).strip().lower()
            has_conflict = current_str != extracted_str

        is_new = current_value is None and extracted_value is not None

        comparison.append({
            "field_name": field_name,
            "extracted_value": extracted_value,
            "current_value": current_value,
            "profile_field": profile_field,
            "can_map": profile_field is not None,
            "confidence": confidence_scores.get(field_name, 0),
            "has_conflict": has_conflict,
            "is_new": is_new,
            "category": (extraction.field_categories or {}).get(field_name, "other"),
        })

    # Sort by category
    category_order = ["identity", "address", "income", "employment", "assets", "tax", "dates", "other"]
    comparison.sort(key=lambda x: (
        category_order.index(x["category"]) if x["category"] in category_order else 99,
        x["field_name"]
    ))

    return {
        "document_id": document_id,
        "profile_type": profile_type,
        "profile_id": profile_id,
        "comparison": comparison,
        "summary": {
            "total_fields": len(comparison),
            "mappable_fields": len([c for c in comparison if c["can_map"]]),
            "conflicts": len([c for c in comparison if c["has_conflict"]]),
            "new_values": len([c for c in comparison if c["is_new"]]),
        },
    }


@router.post("/document/{document_id}/apply-fields")
async def apply_extracted_fields(
    document_id: int,
    body: ApplyFieldsBody,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Apply selected extracted fields to Lead/Loan profile.

    Creates audit trail via DataConflict records.
    """
    _require_approval_role(current_user)
    _verify_document_tenant(db, document_id, current_user)
    from models.document_extraction import SmartDocumentExtraction, FIELD_TO_LEAD_MAPPING, FIELD_TO_LOAN_MAPPING, ReviewStatus
    from sqlalchemy import text

    # Validate profile_type against whitelist to prevent SQL injection
    ALLOWED_PROFILE_TYPES = {"lead": "leads", "loan": "loans"}
    if body.profile_type not in ALLOWED_PROFILE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid profile_type '{body.profile_type}'. Must be 'lead' or 'loan'."
        )
    table = ALLOWED_PROFILE_TYPES[body.profile_type]

    # Get extraction
    extraction = db.query(SmartDocumentExtraction).filter(
        SmartDocumentExtraction.document_id == document_id
    ).first()

    if not extraction:
        raise HTTPException(status_code=404, detail="No extraction found")

    extracted_fields = extraction.extracted_fields or {}
    field_mapping = FIELD_TO_LEAD_MAPPING if body.profile_type == "lead" else FIELD_TO_LOAN_MAPPING

    # Build whitelist of allowed DB column names from the mapping values
    allowed_columns = set(field_mapping.values())

    applied = []
    skipped = []

    for field_req in body.fields_to_apply:
        if field_req.action == "ignore":
            skipped.append(field_req.field_name)
            continue

        profile_field = field_mapping.get(field_req.field_name)
        if not profile_field:
            skipped.append(field_req.field_name)
            continue

        # Validate profile_field is in the allowed column whitelist
        if profile_field not in allowed_columns:
            raise HTTPException(
                status_code=400,
                detail=f"Field '{field_req.field_name}' maps to disallowed column."
            )

        value = field_req.value or extracted_fields.get(field_req.field_name)
        if value is None:
            skipped.append(field_req.field_name)
            continue

        # Update profile using whitelisted table and column names
        try:
            update_query = "UPDATE " + table + " SET " + profile_field + " = :value WHERE id = :id"
            db.execute(text(update_query), {"value": str(value), "id": body.profile_id})

            applied.append({
                "field_name": field_req.field_name,
                "profile_field": profile_field,
                "value": str(value),
                "action": field_req.action,
            })
        except SQLAlchemyError as e:
            logger.warning(f"Failed to apply field {field_req.field_name}: {e}")
            skipped.append(field_req.field_name)

    # Update extraction record
    extraction.applied_fields = applied
    extraction.applied_to_profile_type = body.profile_type
    extraction.applied_to_profile_id = body.profile_id
    extraction.applied_at = datetime.now(timezone.utc)
    extraction.review_status = ReviewStatus.APPLIED

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(f"Database error applying fields for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to apply extracted fields")

    return {
        "document_id": document_id,
        "profile_type": body.profile_type,
        "profile_id": body.profile_id,
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "applied": applied,
        "skipped": skipped,
    }


@router.patch("/document/{document_id}/name")
async def update_document_name(
    document_id: int,
    body: UpdateDocumentNameBody,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update document display name."""
    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Tenant isolation: verify document belongs to user's organization via loan
    if document.loan_id:
        _verify_loan_tenant(db, document.loan_id, current_user)

    document.display_name = body.display_name
    document.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(f"Database error updating document name {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update document name")

    return {
        "document_id": document_id,
        "display_name": body.display_name,
        "updated": True,
    }


@router.post("/document/{document_id}/review-approve")
async def approve_document_with_review(
    document_id: int,
    body: ApproveDocumentBody,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Approve a document after review.

    Optionally applies selected field values to Lead/Loan profile.
    """
    from models.document_extraction import SmartDocumentExtraction, ReviewStatus

    # Get document
    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Tenant isolation: verify document belongs to user's organization via loan
    if document.loan_id:
        _verify_loan_tenant(db, document.loan_id, current_user)

    # Update document status
    document.status = "APPROVED"
    document.decision = DocumentDecision.ACCEPT
    document.reviewed_at = datetime.now(timezone.utc)
    document.reviewed_by = body.reviewer

    if body.assigned_owner:
        document.assigned_owner = body.assigned_owner

    # Update extraction if exists
    extraction = db.query(SmartDocumentExtraction).filter(
        SmartDocumentExtraction.document_id == document_id
    ).first()

    if extraction:
        extraction.review_status = ReviewStatus.REVIEWED
        extraction.reviewed_by = body.reviewer
        extraction.reviewed_at = datetime.now(timezone.utc)

    # Apply fields if requested
    applied_result = None
    if body.apply_fields:
        # Commit current changes first
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.exception(f"Database error during review-approve for document {document_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to save document approval")

        # Use the apply-fields endpoint logic
        from models.document_extraction import FIELD_TO_LEAD_MAPPING, FIELD_TO_LOAN_MAPPING
        from sqlalchemy import text

        # Validate profile_type against whitelist to prevent SQL injection
        ALLOWED_PROFILE_TYPES = {"lead": "leads", "loan": "loans"}
        if body.apply_fields.profile_type not in ALLOWED_PROFILE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid profile_type '{body.apply_fields.profile_type}'. Must be 'lead' or 'loan'."
            )
        apply_table = ALLOWED_PROFILE_TYPES[body.apply_fields.profile_type]

        extracted_fields = extraction.extracted_fields or {} if extraction else {}
        field_mapping = FIELD_TO_LEAD_MAPPING if body.apply_fields.profile_type == "lead" else FIELD_TO_LOAN_MAPPING

        # Build whitelist of allowed DB column names from the mapping values
        allowed_columns = set(field_mapping.values())

        applied = []
        for field_req in body.apply_fields.fields_to_apply:
            if field_req.action == "ignore":
                continue

            profile_field = field_mapping.get(field_req.field_name)
            if not profile_field:
                continue

            # Validate profile_field is in the allowed column whitelist
            if profile_field not in allowed_columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"Field '{field_req.field_name}' maps to disallowed column."
                )

            value = field_req.value or extracted_fields.get(field_req.field_name)
            if value is None:
                continue

            try:
                apply_query = "UPDATE " + apply_table + " SET " + profile_field + " = :value WHERE id = :id"
                db.execute(text(apply_query), {"value": str(value), "id": body.apply_fields.profile_id})
                applied.append(field_req.field_name)
            except SQLAlchemyError as e:
                logger.warning(f"Failed to apply field: {e}")

        if extraction:
            extraction.applied_fields = applied
            extraction.applied_to_profile_type = body.apply_fields.profile_type
            extraction.applied_to_profile_id = body.apply_fields.profile_id
            extraction.applied_at = datetime.now(timezone.utc)
            extraction.review_status = ReviewStatus.APPLIED

        applied_result = {"count": len(applied), "fields": applied}

    # Update request status if linked
    if document.request_id:
        request = db.query(DocumentRequest).filter(
            DocumentRequest.id == document.request_id
        ).first()
        if request:
            request.status = RequestStatus.ACCEPTED
            request.completed_at = datetime.now(timezone.utc)
            request.fulfilled_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(f"Database error finalizing review-approve for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to finalize document approval")

    return {
        "document_id": document_id,
        "status": "APPROVED",
        "reviewed_by": body.reviewer,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "assigned_owner": body.assigned_owner,
        "fields_applied": applied_result,
    }
