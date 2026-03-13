"""
Smart Docs Borrower Portal Routes

Borrower-facing document portal API endpoints accessed through the PURL
(client portal) system. These endpoints allow borrowers to:

- View their document needs list and overall status
- Upload documents (with AI classification and review)
- Re-upload rejected documents
- Preview uploaded documents via presigned S3 URLs
- Check individual document review status
- Submit Letters of Explanation (LOE)
- View and respond to e-signature requests
- View and manage document-related appointments
- Communicate with their LO about documents
- View a categorized visual checklist

Auth: Every endpoint requires a signed portal JWT token (X-Portal-Token header,
Authorization: Bearer, or ?token= query param). The token encodes loan_id,
borrower_email, and org_id. Workspace slug is cross-checked against the token
claims. Write operations additionally require read_write scope and are rate-
limited. See services/smart_docs/portal_auth_service.py for token generation.
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    UploadFile,
    File,
    Form,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text as sa_text

from database import get_db
from services.smart_docs.portal_auth_service import (
    get_current_portal_user,
    require_write_scope,
    check_upload_rate_limit,
)
from models.smart_docs_models import (
    DocumentRequest,
    SmartDocument,
    DocPolicyEvent,
    DocType,
    RequestStatus,
    RequestPriority,
    DocumentDecision,
)
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
from services.smart_docs.document_validation_engine import get_document_validation_engine
from services.smart_docs.ai_classifier_service import get_ai_classifier_service
from services.smart_docs.ai_review_service import get_ai_review_service
from services.smart_docs.pdf_generation_service import get_pdf_generation_service
from services.smart_docs.followup_automation_service import get_followup_automation_service

from routes.smart_docs_models import _get_loan_org_id, DOCUMENT_ID_TO_DOC_TYPE

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Document Portal"])


# =============================================================================
# Pydantic Request / Response Models
# =============================================================================

class LOESubmission(BaseModel):
    """Request body for Letter of Explanation submission."""
    request_id: Optional[int] = None
    subject: str
    explanation_text: str
    borrower_name: str


class ContactLOMessage(BaseModel):
    """Request body for sending a message to the LO."""
    message: str
    related_request_id: Optional[int] = None


class RescheduleRequest(BaseModel):
    """Request body for rescheduling an appointment."""
    preferred_dates: List[str] = Field(
        ..., description="List of preferred date strings (ISO format)"
    )


# =============================================================================
# Portal Access Verification (token-authenticated)
# =============================================================================

async def _verify_portal_access_authenticated(
    request: Request,
    db: Session,
    workspace_slug: str,
) -> Dict:
    """
    Verify portal access using a signed portal token and return loan/borrower info.

    1. Authenticates the borrower via get_current_portal_user (token verification)
    2. Cross-checks the workspace slug against the token claims
    3. Resolves the associated loan and borrower from the workspace

    Raises:
        HTTPException(401): If no valid token is provided or claims don't match.
        HTTPException(404): If the workspace does not exist.

    Returns:
        Dict with workspace, purl_loan, loan_id, borrower_id, org_id,
        borrower_name, borrower_email, portal_user keys.
    """
    # Step 1: Authenticate via portal token
    portal_user = await get_current_portal_user(
        request=request,
        db=db,
        workspace_slug=workspace_slug,
    )

    # Step 2: Resolve workspace and loan (same ORM lookups as before)
    from models.purl import PURLWorkspace, PURLLoan, PURLContact

    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.slug == workspace_slug
    ).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Portal not found")

    # Get associated loan (most recent active loan in this workspace)
    purl_loan = db.query(PURLLoan).filter(
        PURLLoan.workspace_id == workspace.id
    ).order_by(PURLLoan.created_at.desc()).first()

    # Resolve borrower contact
    borrower_contact = db.query(PURLContact).filter(
        PURLContact.workspace_id == workspace.id,
        PURLContact.contact_type == "borrower",
    ).first()

    loan_id = None
    if purl_loan:
        loan_id = purl_loan.main_loan_id if purl_loan.main_loan_id else purl_loan.id

    # Step 3: Additional verification - borrower email in token must match
    # the workspace borrower (if we have one on file)
    if borrower_contact and borrower_contact.email:
        token_email = portal_user.get("borrower_email", "").lower()
        workspace_email = borrower_contact.email.lower()
        if token_email != workspace_email:
            logger.warning(
                f"Portal token email mismatch: token={token_email}, "
                f"workspace_contact={workspace_email}, slug={workspace_slug}"
            )
            raise HTTPException(
                status_code=401,
                detail="Portal access denied. Token does not match this borrower.",
            )

    return {
        "workspace": workspace,
        "purl_loan": purl_loan,
        "loan_id": loan_id,
        "borrower_id": borrower_contact.id if borrower_contact else None,
        "borrower_name": (
            f"{borrower_contact.first_name or ''} {borrower_contact.last_name or ''}".strip()
            if borrower_contact else workspace.display_name
        ),
        "borrower_email": borrower_contact.email if borrower_contact else None,
        "org_id": workspace.organization_id,
        "portal_user": portal_user,
    }


# =============================================================================
# Document Category Mapping for Checklist
# =============================================================================

_CHECKLIST_CATEGORIES = {
    DocType.DRIVERS_LICENSE: "Identity",
    DocType.PAYSTUB: "Income",
    DocType.W2: "Income",
    DocType.TAX_RETURN: "Income",
    DocType.BUSINESS_TAX_RETURN: "Income",
    DocType.PROFIT_LOSS: "Income",
    DocType.BALANCE_SHEET: "Income",
    DocType.BANK_STATEMENT: "Assets",
    DocType.INVESTMENT_STATEMENT: "Assets",
    DocType.GIFT_LETTER: "Assets",
    DocType.LEASE_AGREEMENT: "Property",
    DocType.PURCHASE_CONTRACT: "Property",
    DocType.APPRAISAL: "Property",
    DocType.TITLE_REPORT: "Property",
    DocType.HOMEOWNERS_INSURANCE: "Property",
    DocType.FHA_CERT: "Special",
    DocType.VA_COE: "Special",
    DocType.DD214: "Special",
    DocType.BANKRUPTCY_DISCHARGE: "Credit",
    DocType.LOE: "Special",
    DocType.OTHER: "Special",
}

_STATUS_ICONS = {
    RequestStatus.OPEN: "circle_outline",
    RequestStatus.PENDING_REVIEW: "hourglass",
    RequestStatus.ACCEPTED: "check_circle",
    RequestStatus.REJECTED: "error",
    RequestStatus.WAIVED: "remove_circle",
}


# =============================================================================
# 1. GET /portal/docs/{workspace_slug}/needs-list
# =============================================================================

@router.get("/portal/docs/{workspace_slug}/needs-list")
async def get_portal_needs_list(
    workspace_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get borrower's document needs list.

    Returns all document requests for the loan associated with this portal
    workspace, including status, instructions, uploaded documents, and any
    rejection details.

    Auth: Requires valid portal token.
    """
    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    loan_id = portal["loan_id"]
    if not loan_id:
        return {"needs_list": [], "total": 0}

    # Get all active document requests for this loan
    requests = (
        db.query(DocumentRequest)
        .filter(
            DocumentRequest.loan_id == loan_id,
            DocumentRequest.is_active == True,
        )
        .order_by(
            DocumentRequest.priority.asc(),
            DocumentRequest.created_at.asc(),
        )
        .all()
    )

    needs_list = []
    for req in requests:
        # Get uploaded documents for this request
        uploaded_docs = (
            db.query(SmartDocument)
            .filter(
                SmartDocument.request_id == req.id,
                SmartDocument.status.notin_(["DELETED", "SUPERSEDED"]),
            )
            .order_by(SmartDocument.uploaded_at.desc())
            .all()
        )

        doc_items = []
        for doc in uploaded_docs:
            doc_items.append({
                "document_id": doc.id,
                "file_name": doc.display_name or doc.file_name,
                "status": doc.status,
                "decision": doc.decision.value if doc.decision else None,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                "rejection_reason": doc.rejection_reason,
                "fix_instructions": doc.fix_instructions,
            })

        # Build the latest rejection info if status is REJECTED
        rejection_reason = None
        fix_instructions = None
        if req.status == RequestStatus.REJECTED and uploaded_docs:
            latest_rejected = next(
                (d for d in uploaded_docs if d.decision == DocumentDecision.REJECT),
                None,
            )
            if latest_rejected:
                rejection_reason = latest_rejected.rejection_reason
                fix_instructions = latest_rejected.fix_instructions

        needs_list.append({
            "request_id": req.id,
            "doc_type": req.doc_type.value if req.doc_type else None,
            "title": req.title,
            "description": req.description,
            "instructions": req.instructions,
            "status": req.status.value if req.status else "OPEN",
            "priority": req.priority.value if req.priority else "NORMAL",
            "due_date": req.due_date.isoformat() if req.due_date else None,
            "uploaded_documents": doc_items,
            "rejection_reason": rejection_reason,
            "fix_instructions": fix_instructions,
        })

    return {
        "workspace_slug": workspace_slug,
        "borrower_name": portal["borrower_name"],
        "loan_id": loan_id,
        "needs_list": needs_list,
        "total": len(needs_list),
    }


# =============================================================================
# 2. POST /portal/docs/{workspace_slug}/upload
# =============================================================================

@router.post("/portal/docs/{workspace_slug}/upload")
async def portal_upload_document(
    workspace_slug: str,
    request: Request,
    file: UploadFile = File(...),
    request_id: Optional[int] = Form(None),
    doc_type: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Upload a document through the borrower portal.

    Validates the file (type, size, magic bytes), uploads to S3 with
    tenant-scoped key, creates a SmartDocument record, triggers AI
    classification if doc_type is not specified, and triggers the AI
    review pipeline.

    Auth: Requires valid portal token with read_write scope.
    Rate limited to 10 uploads per hour per borrower.
    """
    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    require_write_scope(portal["portal_user"])
    check_upload_rate_limit(portal["portal_user"]["borrower_email"])
    loan_id = portal["loan_id"]
    if not loan_id:
        raise HTTPException(status_code=400, detail="No loan associated with this portal")

    borrower_id = portal["borrower_id"]
    org_id = portal["org_id"]

    # -- Validate file presence --
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # -- Read file content with size limit enforcement --
    from middleware.upload_limits import validate_upload_size, MAX_DOCUMENT_SIZE

    file_content = await validate_upload_size(file, MAX_DOCUMENT_SIZE)
    mime_type = file.content_type or "application/octet-stream"
    file_size = len(file_content)

    # -- Validate file (type, size, magic bytes) --
    validation_engine = get_document_validation_engine()
    validation_result = validation_engine.validate_upload(
        file_content=file_content,
        filename=file.filename,
        declared_mime=mime_type,
    )
    if validation_result.get("has_critical"):
        issues = validation_result.get("issues", [])
        critical_msgs = [
            i.get("message", "Validation failed")
            for i in issues
            if i.get("severity") == "CRITICAL"
        ]
        raise HTTPException(
            status_code=400,
            detail="; ".join(critical_msgs) or "File validation failed",
        )

    # -- Malware scan --
    from services.smart_docs.malware_scanner_service import get_malware_scanner
    try:
        malware_scanner = get_malware_scanner()
        scan_result = malware_scanner.validate_file_safety(
            file_bytes=file_content,
            filename=file.filename,
            mime_type=mime_type,
        )
        if not scan_result.clean:
            threat_names = [
                f.threat_name for f in scan_result.findings
                if not f.clean and f.threat_name
            ]
            logger.warning(
                "Portal upload rejected: malware detected in '%s' for workspace %s: %s",
                file.filename, workspace_slug, threat_names,
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    "File rejected: our security scan detected potentially harmful content. "
                    "Please save the document as a new PDF and try again."
                ),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Malware scan error during portal upload: {e}")
        # Fail closed: reject uploads when the scanner errors
        raise HTTPException(
            status_code=400,
            detail="File security scan failed. Please try again.",
        )

    # -- Parse doc_type if provided --
    parsed_doc_type = None
    if doc_type:
        try:
            parsed_doc_type = DocType(doc_type)
        except ValueError:
            logger.warning(f"Portal upload: invalid doc_type '{doc_type}', will classify via AI")

    # -- Upload to S3 --
    s3_service = get_smart_docs_s3_service()
    storage_key = s3_service.generate_storage_key(
        loan_id=loan_id,
        borrower_id=borrower_id,
        file_name=file.filename,
        organization_id=org_id,
    )

    s3_result = s3_service.upload_file(
        file_content=file_content,
        storage_key=storage_key,
        content_type=mime_type,
        metadata={
            "loan_id": str(loan_id),
            "workspace_slug": workspace_slug,
            "source": "borrower_portal",
        },
    )

    if not s3_result.get("success") and s3_service.is_available:
        logger.error(f"Portal upload S3 failure for workspace {workspace_slug}: {s3_result}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # -- Create SmartDocument record --
    document = SmartDocument(
        request_id=request_id,
        loan_id=loan_id,
        borrower_id=borrower_id or 0,
        file_name=file.filename,
        original_filename=file.filename,
        mime_type=mime_type,
        file_size=file_size,
        storage_key=storage_key,
        doc_type=parsed_doc_type,
        status="UPLOADED",
        upload_source="WEB",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # -- AI classification if doc_type not specified --
    classification_result = None
    if not parsed_doc_type:
        try:
            classifier = get_ai_classifier_service()
            classification_result = classifier.classify(
                file_content=file_content,
                filename=file.filename,
                mime_type=mime_type,
            )
            if classification_result and classification_result.get("doc_type"):
                try:
                    detected_type = DocType(classification_result["doc_type"])
                    document.doc_type = detected_type
                    document.detected_doc_type = classification_result["doc_type"]
                except ValueError:
                    document.detected_doc_type = classification_result.get("doc_type")
                db.commit()
        except Exception as e:
            logger.warning(f"AI classification failed for document {document.id}: {e}")

    # -- Trigger AI review pipeline --
    review_status = None
    try:
        review_service = get_ai_review_service(db)
        review_result = review_service.review_document(
            document_id=document.id,
            file_content=file_content,
            mime_type=mime_type,
            filename=file.filename,
        )
        review_status = review_result.get("status") if review_result else None
    except Exception as e:
        logger.warning(f"AI review pipeline failed for document {document.id}: {e}")

    # -- Link to request and update request status --
    if request_id:
        request_obj = db.query(DocumentRequest).filter(
            DocumentRequest.id == request_id,
            DocumentRequest.loan_id == loan_id,
        ).first()
        if request_obj and request_obj.status == RequestStatus.OPEN:
            request_obj.status = RequestStatus.PENDING_REVIEW
            request_obj.updated_at = datetime.now(timezone.utc)
            db.commit()

    # -- Mark follow-up campaign document uploaded if applicable --
    try:
        followup_service = get_followup_automation_service(db)
        followup_service.mark_document_uploaded(
            loan_id=loan_id,
            request_id=request_id,
        )
    except Exception as e:
        logger.warning(f"Follow-up campaign update failed: {e}")

    # -- Log policy event --
    try:
        event = DocPolicyEvent(
            event_type="DOCUMENT_UPLOADED",
            loan_id=loan_id,
            request_id=request_id,
            document_id=document.id,
            payload={
                "source": "borrower_portal",
                "workspace_slug": workspace_slug,
                "file_name": file.filename,
                "file_size": file_size,
                "doc_type": document.doc_type.value if document.doc_type else None,
            },
        )
        db.add(event)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log policy event: {e}")

    return {
        "document_id": document.id,
        "file_name": document.file_name,
        "doc_type": document.doc_type.value if document.doc_type else None,
        "classification": classification_result,
        "review_status": review_status,
        "status": document.status,
        "request_id": request_id,
        "message": "Document uploaded successfully",
    }


# =============================================================================
# 3. GET /portal/docs/{workspace_slug}/status
# =============================================================================

@router.get("/portal/docs/{workspace_slug}/status")
async def get_portal_document_status(
    workspace_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get overall document collection status for the borrower.

    Returns counts of required, submitted, approved, rejected, and
    pending documents, along with completeness percentage and next
    actions the borrower should take.

    Auth: Requires valid portal token.
    """
    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    loan_id = portal["loan_id"]
    if not loan_id:
        return {
            "total_required": 0,
            "submitted": 0,
            "approved": 0,
            "rejected": 0,
            "pending": 0,
            "completeness_percentage": 0,
            "next_actions": [],
            "estimated_time_remaining": None,
        }

    # Get all active requests
    requests = (
        db.query(DocumentRequest)
        .filter(
            DocumentRequest.loan_id == loan_id,
            DocumentRequest.is_active == True,
            DocumentRequest.status != RequestStatus.WAIVED,
        )
        .all()
    )

    total_required = len(requests)
    approved = sum(1 for r in requests if r.status == RequestStatus.ACCEPTED)
    rejected = sum(1 for r in requests if r.status == RequestStatus.REJECTED)
    pending = sum(1 for r in requests if r.status == RequestStatus.PENDING_REVIEW)
    open_count = sum(1 for r in requests if r.status == RequestStatus.OPEN)
    submitted = pending + approved + rejected  # anything that has been uploaded

    completeness = round((approved / total_required) * 100, 1) if total_required > 0 else 0

    # Build next_actions list
    next_actions = []
    if open_count > 0:
        next_actions.append({
            "action": "upload_documents",
            "description": f"Upload {open_count} outstanding document(s)",
            "priority": "high" if open_count > 3 else "normal",
        })
    if rejected > 0:
        next_actions.append({
            "action": "reupload_rejected",
            "description": f"Re-upload {rejected} rejected document(s) with corrections",
            "priority": "high",
        })
    if pending > 0:
        next_actions.append({
            "action": "wait_for_review",
            "description": f"{pending} document(s) are being reviewed",
            "priority": "info",
        })
    if completeness == 100:
        next_actions.append({
            "action": "complete",
            "description": "All documents have been approved",
            "priority": "info",
        })

    # Estimate time remaining based on outstanding items
    remaining_items = open_count + rejected
    estimated_time = None
    if remaining_items > 0:
        # Rough estimate: 1-2 business days per document to collect + review
        est_days = min(remaining_items * 2, 14)
        estimated_time = f"{est_days} business day(s)"

    return {
        "workspace_slug": workspace_slug,
        "borrower_name": portal["borrower_name"],
        "total_required": total_required,
        "submitted": submitted,
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "open": open_count,
        "completeness_percentage": completeness,
        "next_actions": next_actions,
        "estimated_time_remaining": estimated_time,
    }


# =============================================================================
# 4. GET /portal/docs/{workspace_slug}/document/{document_id}/preview
# =============================================================================

@router.get("/portal/docs/{workspace_slug}/document/{document_id}/preview")
async def preview_portal_document(
    workspace_slug: str,
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Generate a time-limited presigned S3 URL for document preview.

    Verifies that the document belongs to the portal's loan before
    generating the URL. Logs an access event.

    Auth: Requires valid portal token.
    """
    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    loan_id = portal["loan_id"]

    # Verify document belongs to this loan
    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id,
        SmartDocument.loan_id == loan_id,
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.storage_key:
        raise HTTPException(status_code=404, detail="Document file not available")

    # Generate presigned URL
    s3_service = get_smart_docs_s3_service()
    expires_in = 600  # 10 minutes
    result = s3_service.get_presigned_download_url(
        storage_key=document.storage_key,
        file_name=document.file_name,
        expires_in=expires_in,
        inline=True,
        organization_id=portal["org_id"],
    )

    if not result.get("presigned_url"):
        raise HTTPException(status_code=500, detail="Internal server error")

    # Log access event
    try:
        event = DocPolicyEvent(
            event_type="DOCUMENT_UPLOADED",  # Closest existing event type for access log
            loan_id=loan_id,
            document_id=document.id,
            payload={
                "action": "portal_preview",
                "workspace_slug": workspace_slug,
                "accessed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(event)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log preview access event: {e}")

    return {
        "document_id": document_id,
        "preview_url": result["presigned_url"],
        "expires_in": expires_in,
        "file_name": document.display_name or document.file_name,
        "mime_type": document.mime_type,
    }


# =============================================================================
# 5. GET /portal/docs/{workspace_slug}/document/{document_id}/status
# =============================================================================

@router.get("/portal/docs/{workspace_slug}/document/{document_id}/status")
async def get_portal_document_review_status(
    workspace_slug: str,
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get the review status for a specific uploaded document.

    Returns the current status, decision, and any rejection details
    including fix instructions.

    Auth: Requires valid portal token.
    """
    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    loan_id = portal["loan_id"]

    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id,
        SmartDocument.loan_id == loan_id,
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "document_id": document.id,
        "file_name": document.display_name or document.file_name,
        "doc_type": document.doc_type.value if document.doc_type else None,
        "status": document.status,
        "decision": document.decision.value if document.decision else None,
        "rejection_reason": document.rejection_reason,
        "rejection_category": document.rejection_category.value if document.rejection_category else None,
        "fix_instructions": document.fix_instructions,
        "reviewed_at": document.reviewed_at.isoformat() if document.reviewed_at else None,
        "reviewed_by": document.reviewed_by,
        "uploaded_at": document.uploaded_at.isoformat() if document.uploaded_at else None,
    }


# =============================================================================
# 6. POST /portal/docs/{workspace_slug}/document/{document_id}/reupload
# =============================================================================

@router.post("/portal/docs/{workspace_slug}/document/{document_id}/reupload")
async def reupload_portal_document(
    workspace_slug: str,
    document_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Re-upload a rejected document.

    Marks the old document as SUPERSEDED, creates a new SmartDocument
    linked to the same request, and triggers the AI review pipeline.

    Auth: Requires valid portal token with read_write scope.
    Rate limited to 10 uploads per hour per borrower.
    """
    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    require_write_scope(portal["portal_user"])
    check_upload_rate_limit(portal["portal_user"]["borrower_email"])
    loan_id = portal["loan_id"]
    org_id = portal["org_id"]
    borrower_id = portal["borrower_id"]

    # Find the original document
    original_doc = db.query(SmartDocument).filter(
        SmartDocument.id == document_id,
        SmartDocument.loan_id == loan_id,
    ).first()
    if not original_doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Validate the file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    from middleware.upload_limits import validate_upload_size as _validate_size
    from middleware.upload_limits import MAX_DOCUMENT_SIZE as _MAX_DOC_SIZE

    file_content = await _validate_size(file, _MAX_DOC_SIZE)
    mime_type = file.content_type or "application/octet-stream"
    file_size = len(file_content)

    # Validate file
    validation_engine = get_document_validation_engine()
    validation_result = validation_engine.validate_upload(
        file_content=file_content,
        filename=file.filename,
        declared_mime=mime_type,
    )
    if validation_result.get("has_critical"):
        issues = validation_result.get("issues", [])
        critical_msgs = [
            i.get("message", "Validation failed")
            for i in issues
            if i.get("severity") == "CRITICAL"
        ]
        raise HTTPException(
            status_code=400,
            detail="; ".join(critical_msgs) or "File validation failed",
        )

    # -- Malware scan --
    from services.smart_docs.malware_scanner_service import get_malware_scanner
    try:
        malware_scanner = get_malware_scanner()
        scan_result = malware_scanner.validate_file_safety(
            file_bytes=file_content,
            filename=file.filename,
            mime_type=mime_type,
        )
        if not scan_result.clean:
            threat_names = [
                f.threat_name for f in scan_result.findings
                if not f.clean and f.threat_name
            ]
            logger.warning(
                "Portal re-upload rejected: malware detected in '%s' for workspace %s: %s",
                file.filename, workspace_slug, threat_names,
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    "File rejected: our security scan detected potentially harmful content. "
                    "Please save the document as a new PDF and try again."
                ),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Malware scan error during portal re-upload: {e}")
        raise HTTPException(
            status_code=400,
            detail="File security scan failed. Please try again.",
        )

    # Upload to S3
    s3_service = get_smart_docs_s3_service()
    storage_key = s3_service.generate_storage_key(
        loan_id=loan_id,
        borrower_id=borrower_id,
        file_name=file.filename,
        organization_id=org_id,
    )

    s3_result = s3_service.upload_file(
        file_content=file_content,
        storage_key=storage_key,
        content_type=mime_type,
        metadata={
            "loan_id": str(loan_id),
            "workspace_slug": workspace_slug,
            "source": "borrower_portal_reupload",
            "supersedes_document_id": str(document_id),
        },
    )

    if not s3_result.get("success") and s3_service.is_available:
        logger.error(f"Portal re-upload S3 failure: {s3_result}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # Mark old document as SUPERSEDED
    original_doc.status = "SUPERSEDED"
    original_doc.updated_at = datetime.now(timezone.utc)

    # Create new document linked to the same request
    new_document = SmartDocument(
        request_id=original_doc.request_id,
        loan_id=loan_id,
        borrower_id=borrower_id or original_doc.borrower_id,
        file_name=file.filename,
        original_filename=file.filename,
        mime_type=mime_type,
        file_size=file_size,
        storage_key=storage_key,
        doc_type=original_doc.doc_type,
        status="UPLOADED",
        upload_source="WEB",
    )
    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    # Update request status back to PENDING_REVIEW
    if original_doc.request_id:
        request_obj = db.query(DocumentRequest).filter(
            DocumentRequest.id == original_doc.request_id,
        ).first()
        if request_obj:
            request_obj.status = RequestStatus.PENDING_REVIEW
            request_obj.updated_at = datetime.now(timezone.utc)
            db.commit()

    # Trigger AI review
    review_status = None
    try:
        review_service = get_ai_review_service(db)
        review_result = review_service.review_document(
            document_id=new_document.id,
            file_content=file_content,
            mime_type=mime_type,
            filename=file.filename,
        )
        review_status = review_result.get("status") if review_result else None
    except Exception as e:
        logger.warning(f"AI review failed for re-uploaded document {new_document.id}: {e}")

    # Log event
    try:
        event = DocPolicyEvent(
            event_type="DOCUMENT_UPLOADED",
            loan_id=loan_id,
            request_id=original_doc.request_id,
            document_id=new_document.id,
            payload={
                "source": "borrower_portal_reupload",
                "supersedes_document_id": document_id,
                "workspace_slug": workspace_slug,
            },
        )
        db.add(event)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log re-upload event: {e}")

    return {
        "document_id": new_document.id,
        "superseded_document_id": document_id,
        "file_name": new_document.file_name,
        "doc_type": new_document.doc_type.value if new_document.doc_type else None,
        "review_status": review_status,
        "status": new_document.status,
        "message": "Document re-uploaded successfully",
    }


# =============================================================================
# 7. GET /portal/docs/{workspace_slug}/signing-requests
# =============================================================================

@router.get("/portal/docs/{workspace_slug}/signing-requests")
async def get_portal_signing_requests(
    workspace_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get pending e-signature requests for this borrower.

    Returns a list of envelopes awaiting the borrower's signature,
    including the signing URL.

    Auth: Requires valid portal token.
    """
    from database.models.esignature import (
        ESignatureEnvelope,
        ESignatureRecipient,
        EnvelopeStatus,
        RecipientStatus,
    )

    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    loan_id = portal["loan_id"]
    borrower_email = portal["borrower_email"]

    if not loan_id:
        return {"signing_requests": [], "total": 0}

    # Find envelopes for this loan that are in a signable state
    envelopes = (
        db.query(ESignatureEnvelope)
        .filter(
            ESignatureEnvelope.loan_id == loan_id,
            ESignatureEnvelope.status.in_([
                EnvelopeStatus.SENT.value,
                EnvelopeStatus.VIEWED.value,
                EnvelopeStatus.PARTIALLY_SIGNED.value,
            ]),
        )
        .order_by(ESignatureEnvelope.sent_at.desc())
        .all()
    )

    signing_requests = []
    for envelope in envelopes:
        # Check if the borrower is a recipient who hasn't signed yet
        recipient = None
        if borrower_email:
            recipient = (
                db.query(ESignatureRecipient)
                .filter(
                    ESignatureRecipient.envelope_id == envelope.id,
                    ESignatureRecipient.email == borrower_email,
                    ESignatureRecipient.status.in_([
                        RecipientStatus.PENDING.value,
                        RecipientStatus.SENT.value,
                        RecipientStatus.VIEWED.value,
                    ]),
                )
                .first()
            )

        if not recipient and borrower_email:
            continue  # Borrower is not a pending recipient for this envelope

        # Build signing URL
        esign_base_url = os.getenv("ESIGN_FRONTEND_URL", "https://app.perenniaai.com/esign")
        signing_url = None
        if recipient and hasattr(recipient, "signing_token"):
            signing_url = f"{esign_base_url}/sign/{envelope.envelope_uuid}?token={recipient.signing_token}"
        else:
            signing_url = f"{esign_base_url}/sign/{envelope.envelope_uuid}"

        signing_requests.append({
            "envelope_uuid": envelope.envelope_uuid,
            "title": envelope.title,
            "description": envelope.description,
            "status": envelope.status,
            "sent_at": envelope.sent_at.isoformat() if envelope.sent_at else None,
            "expires_at": envelope.expires_at.isoformat() if envelope.expires_at else None,
            "signing_url": signing_url,
        })

    return {
        "workspace_slug": workspace_slug,
        "signing_requests": signing_requests,
        "total": len(signing_requests),
    }


# =============================================================================
# 8. POST /portal/docs/{workspace_slug}/loe
# =============================================================================

@router.post("/portal/docs/{workspace_slug}/loe")
async def submit_letter_of_explanation(
    workspace_slug: str,
    body: LOESubmission,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Submit a Letter of Explanation.

    Generates a PDF from the explanation text, uploads it to S3,
    creates a SmartDocument record, and links it to the relevant
    document request if request_id is provided.

    Auth: Requires valid portal token with read_write scope.
    """
    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    require_write_scope(portal["portal_user"])
    loan_id = portal["loan_id"]
    if not loan_id:
        raise HTTPException(status_code=400, detail="No loan associated with this portal")

    borrower_id = portal["borrower_id"]
    org_id = portal["org_id"]

    # Generate LOE PDF
    pdf_service = get_pdf_generation_service()
    try:
        pdf_content = pdf_service.generate_loe_pdf(
            borrower_name=body.borrower_name,
            subject=body.subject,
            explanation_text=body.explanation_text,
            date_str=datetime.now(timezone.utc).strftime("%B %d, %Y"),
        )
    except Exception as e:
        logger.error(f"LOE PDF generation failed: {e}")
        # Fallback: store as plain text document
        pdf_content = body.explanation_text.encode("utf-8")

    file_name = f"LOE_{body.subject.replace(' ', '_')[:40]}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    mime_type = "application/pdf" if isinstance(pdf_content, bytes) and pdf_content[:4] == b'%PDF' else "text/plain"

    # Upload to S3
    s3_service = get_smart_docs_s3_service()
    storage_key = s3_service.generate_storage_key(
        loan_id=loan_id,
        borrower_id=borrower_id,
        file_name=file_name,
        organization_id=org_id,
    )

    s3_result = s3_service.upload_file(
        file_content=pdf_content,
        storage_key=storage_key,
        content_type=mime_type,
        metadata={
            "loan_id": str(loan_id),
            "workspace_slug": workspace_slug,
            "source": "borrower_portal_loe",
            "loe_subject": body.subject,
        },
    )

    if not s3_result.get("success") and s3_service.is_available:
        logger.error(f"LOE S3 upload failure: {s3_result}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # Create SmartDocument record
    loe_doc_type = DocType.LOE if hasattr(DocType, "LOE") else DocType.OTHER
    document = SmartDocument(
        request_id=body.request_id,
        loan_id=loan_id,
        borrower_id=borrower_id or 0,
        file_name=file_name,
        original_filename=file_name,
        mime_type=mime_type,
        file_size=len(pdf_content),
        storage_key=storage_key,
        doc_type=loe_doc_type,
        status="UPLOADED",
        upload_source="WEB",
        display_name=f"Letter of Explanation - {body.subject}",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Update linked request status
    if body.request_id:
        request_obj = db.query(DocumentRequest).filter(
            DocumentRequest.id == body.request_id,
            DocumentRequest.loan_id == loan_id,
        ).first()
        if request_obj:
            request_obj.status = RequestStatus.PENDING_REVIEW
            request_obj.updated_at = datetime.now(timezone.utc)
            db.commit()

    # Log event
    try:
        event = DocPolicyEvent(
            event_type="DOCUMENT_UPLOADED",
            loan_id=loan_id,
            request_id=body.request_id,
            document_id=document.id,
            payload={
                "source": "borrower_portal_loe",
                "subject": body.subject,
                "workspace_slug": workspace_slug,
            },
        )
        db.add(event)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log LOE event: {e}")

    return {
        "document_id": document.id,
        "file_name": document.file_name,
        "doc_type": loe_doc_type.value,
        "status": document.status,
        "message": "Letter of Explanation submitted successfully",
    }


# =============================================================================
# 9. GET /portal/docs/{workspace_slug}/appointments
# =============================================================================

@router.get("/portal/docs/{workspace_slug}/appointments")
async def get_portal_appointments(
    workspace_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get borrower's upcoming document-related appointments.

    Returns scheduled and confirmed appointments including date, time,
    type, location, meeting link, and status.

    Auth: Requires valid portal token.
    """
    from database.models.document_followup import (
        DocumentAppointment,
        AppointmentStatus,
    )

    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    loan_id = portal["loan_id"]
    if not loan_id:
        return {"appointments": [], "total": 0}

    # Get upcoming appointments (not completed, not cancelled)
    appointments = (
        db.query(DocumentAppointment)
        .filter(
            DocumentAppointment.loan_id == loan_id,
            DocumentAppointment.status.in_([
                AppointmentStatus.SCHEDULED.value,
                AppointmentStatus.CONFIRMED.value,
            ]),
        )
        .order_by(DocumentAppointment.scheduled_date.asc())
        .all()
    )

    items = []
    for appt in appointments:
        items.append({
            "appointment_id": appt.id,
            "title": appt.title,
            "description": appt.description,
            "appointment_type": appt.appointment_type.value if hasattr(appt.appointment_type, "value") else appt.appointment_type,
            "status": appt.status.value if hasattr(appt.status, "value") else appt.status,
            "date": appt.scheduled_date.isoformat() if appt.scheduled_date else None,
            "time_start": appt.scheduled_time_start.isoformat() if appt.scheduled_time_start else None,
            "time_end": appt.scheduled_time_end.isoformat() if appt.scheduled_time_end else None,
            "duration_minutes": appt.duration_minutes,
            "location_type": appt.location_type.value if appt.location_type and hasattr(appt.location_type, "value") else appt.location_type,
            "location_details": appt.location_details,
            "meeting_link": appt.meeting_link,
        })

    return {
        "workspace_slug": workspace_slug,
        "appointments": items,
        "total": len(items),
    }


# =============================================================================
# 10. POST /portal/docs/{workspace_slug}/appointments/{appointment_id}/confirm
# =============================================================================

@router.post("/portal/docs/{workspace_slug}/appointments/{appointment_id}/confirm")
async def confirm_portal_appointment(
    workspace_slug: str,
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Confirm a scheduled appointment.

    Sets the appointment status to CONFIRMED and records the confirmation
    timestamp.

    Auth: Requires valid portal token with read_write scope.
    """
    from database.models.document_followup import (
        DocumentAppointment,
        AppointmentStatus,
    )

    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    require_write_scope(portal["portal_user"])
    loan_id = portal["loan_id"]

    appointment = db.query(DocumentAppointment).filter(
        DocumentAppointment.id == appointment_id,
        DocumentAppointment.loan_id == loan_id,
    ).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appointment.status not in (AppointmentStatus.SCHEDULED, AppointmentStatus.SCHEDULED.value):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot confirm appointment in '{appointment.status}' status",
        )

    appointment.status = AppointmentStatus.CONFIRMED
    appointment.confirmed_at = datetime.now(timezone.utc)
    appointment.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "appointment_id": appointment.id,
        "status": "confirmed",
        "confirmed_at": appointment.confirmed_at.isoformat(),
        "message": "Appointment confirmed",
    }


# =============================================================================
# 11. POST /portal/docs/{workspace_slug}/appointments/{appointment_id}/reschedule
# =============================================================================

@router.post("/portal/docs/{workspace_slug}/appointments/{appointment_id}/reschedule")
async def reschedule_portal_appointment(
    workspace_slug: str,
    appointment_id: int,
    body: RescheduleRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Request rescheduling of an appointment.

    Records the borrower's preferred dates and notifies the LO/processor.
    The original appointment remains in its current status until the
    team responds with a new time.

    Auth: Requires valid portal token with read_write scope.
    """
    from database.models.document_followup import DocumentAppointment
    from models.purl import PURLMessage

    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    require_write_scope(portal["portal_user"])
    loan_id = portal["loan_id"]

    appointment = db.query(DocumentAppointment).filter(
        DocumentAppointment.id == appointment_id,
        DocumentAppointment.loan_id == loan_id,
    ).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Create a message to the LO about the reschedule request
    preferred_dates_text = ", ".join(body.preferred_dates)
    message_content = (
        f"Reschedule request for appointment: {appointment.title}\n"
        f"Preferred dates: {preferred_dates_text}"
    )

    try:
        message = PURLMessage(
            organization_id=portal["org_id"],
            workspace_id=portal["workspace"].id,
            message_type="system",
            content=message_content,
            sender_type="contact",
            sender_contact_id=portal["borrower_id"],
        )
        db.add(message)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to create reschedule message: {e}")

    return {
        "appointment_id": appointment.id,
        "status": "reschedule_requested",
        "preferred_dates": body.preferred_dates,
        "message": "Reschedule request sent to your loan team",
    }


# =============================================================================
# 12. GET /portal/docs/{workspace_slug}/messages
# =============================================================================

@router.get("/portal/docs/{workspace_slug}/messages")
async def get_portal_messages(
    workspace_slug: str,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Get document-related messages sent to the borrower.

    Returns follow-up messages, system notifications, and direct messages
    from the LO.

    Auth: Requires valid portal token.
    """
    from models.purl import PURLMessage

    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)

    messages = (
        db.query(PURLMessage)
        .filter(PURLMessage.workspace_id == portal["workspace"].id)
        .order_by(PURLMessage.created_at.desc())
        .limit(limit)
        .all()
    )

    items = []
    for msg in messages:
        items.append({
            "message_id": msg.id,
            "type": msg.message_type,
            "content": msg.content[:500] if msg.content else "",
            "sender_type": msg.sender_type,
            "is_read": msg.is_read_by_borrower,
            "date": msg.created_at.isoformat() if msg.created_at else None,
        })

    return {
        "workspace_slug": workspace_slug,
        "messages": items,
        "total": len(items),
    }


# =============================================================================
# 13. POST /portal/docs/{workspace_slug}/contact
# =============================================================================

@router.post("/portal/docs/{workspace_slug}/contact")
async def send_portal_contact_message(
    workspace_slug: str,
    body: ContactLOMessage,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Send a message to the LO about documents.

    Creates a message in the portal workspace and optionally links it
    to a specific document request. Notifies the LO.

    Auth: Requires valid portal token with read_write scope.
    """
    from models.purl import PURLMessage

    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    require_write_scope(portal["portal_user"])

    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Create message in workspace
    message = PURLMessage(
        organization_id=portal["org_id"],
        workspace_id=portal["workspace"].id,
        message_type="text",
        content=body.message.strip(),
        sender_type="contact",
        sender_contact_id=portal["borrower_id"],
        meta_data={
            "related_request_id": body.related_request_id,
            "source": "document_portal",
        },
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    # Create activity/note on the loan if we have a loan_id
    loan_id = portal["loan_id"]
    if loan_id:
        try:
            db.execute(
                sa_text("""
                    INSERT INTO activities (
                        type, content, loan_id, created_at
                    ) VALUES (
                        'Note', :content, :loan_id, :now
                    )
                """),
                {
                    "content": f"[Portal Message from {portal['borrower_name']}] {body.message.strip()[:500]}",
                    "loan_id": loan_id,
                    "now": datetime.now(timezone.utc),
                },
            )
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to create activity for portal contact message: {e}")

    return {
        "message_id": message.id,
        "status": "sent",
        "message": "Message sent to your loan officer",
    }


# =============================================================================
# 14. GET /portal/docs/{workspace_slug}/checklist
# =============================================================================

@router.get("/portal/docs/{workspace_slug}/checklist")
async def get_portal_checklist(
    workspace_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get a visual checklist categorized for UI display.

    Returns document requests organized by category (Identity, Income,
    Assets, Property, Credit, Special) with status icons, instructions,
    and upload counts.

    Auth: Requires valid portal token.
    """
    portal = await _verify_portal_access_authenticated(request, db, workspace_slug)
    loan_id = portal["loan_id"]
    if not loan_id:
        return {"categories": [], "summary": {"total": 0, "completed": 0}}

    # Get all active requests
    requests = (
        db.query(DocumentRequest)
        .filter(
            DocumentRequest.loan_id == loan_id,
            DocumentRequest.is_active == True,
        )
        .order_by(DocumentRequest.created_at.asc())
        .all()
    )

    # Build categorized checklist
    categories_map: Dict[str, List[Dict]] = {}

    for req in requests:
        # Determine category
        category = _CHECKLIST_CATEGORIES.get(req.doc_type, "Special") if req.doc_type else "Special"

        if category not in categories_map:
            categories_map[category] = []

        # Count uploaded documents for this request
        uploaded_count = (
            db.query(SmartDocument)
            .filter(
                SmartDocument.request_id == req.id,
                SmartDocument.status.notin_(["DELETED", "SUPERSEDED"]),
            )
            .count()
        )

        status_icon = _STATUS_ICONS.get(req.status, "circle_outline")

        categories_map[category].append({
            "request_id": req.id,
            "title": req.title,
            "doc_type": req.doc_type.value if req.doc_type else None,
            "status": req.status.value if req.status else "OPEN",
            "status_icon": status_icon,
            "instructions": req.instructions,
            "priority": req.priority.value if req.priority else "NORMAL",
            "uploaded_count": uploaded_count,
            "required_count": req.required_count or 1,
            "due_date": req.due_date.isoformat() if req.due_date else None,
        })

    # Build ordered category list
    category_order = ["Identity", "Income", "Assets", "Property", "Credit", "Special"]
    categories = []
    for cat_name in category_order:
        items = categories_map.get(cat_name, [])
        if items:
            completed = sum(
                1 for item in items if item["status"] == RequestStatus.ACCEPTED.value
            )
            categories.append({
                "category": cat_name,
                "items": items,
                "total": len(items),
                "completed": completed,
            })

    total_items = sum(c["total"] for c in categories)
    total_completed = sum(c["completed"] for c in categories)

    return {
        "workspace_slug": workspace_slug,
        "borrower_name": portal["borrower_name"],
        "categories": categories,
        "summary": {
            "total": total_items,
            "completed": total_completed,
            "completeness_percentage": round(
                (total_completed / total_items) * 100, 1
            ) if total_items > 0 else 0,
        },
    }
