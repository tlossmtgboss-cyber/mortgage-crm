"""
Smart Document Collection API Routes

REST API endpoints for the intelligent document collection system:
- Needs list management
- Document upload and processing
- Screenshot detection
- Freshness validation
- Auto-renewal management
"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.smart_docs_models import (
    DocumentRequest, SmartDocument, DocPolicyEvent, NeedsListTemplate,
    DocType, RequestStatus, RequestPriority, AppliesTo, PayrollFrequency,
    DocumentDecision
)
from services.smart_docs.needs_list_generator import NeedsListGenerator
from services.smart_docs.document_review_pipeline import DocumentReviewPipeline
from services.smart_docs.auto_renewal_scheduler import AutoRenewalScheduler
from services.smart_docs.freshness_validator import FreshnessValidator
from services.smart_docs.notification_service import SmartDocsNotificationService
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/smart-docs", tags=["Smart Documents"])


# =============================================================================
# Request/Response Models
# =============================================================================

class GenerateNeedsListRequest(BaseModel):
    """Request to generate a needs list."""
    loan_id: int
    loan_program: str  # CONVENTIONAL, FHA, VA, USDA
    occupancy_type: str  # PRIMARY, SECOND_HOME, INVESTMENT
    income_type: str  # W2, SELF_EMPLOYED, RETIREMENT
    borrower_id: int
    co_borrower_id: Optional[int] = None
    has_gift_funds: bool = False
    is_self_employed: bool = False
    has_bankruptcy: bool = False
    property_type: Optional[str] = None


class AddCustomRequestBody(BaseModel):
    """Request to add a custom document request."""
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    priority: str = "NORMAL"
    due_date: Optional[datetime] = None
    # Notification options
    send_notification: bool = False
    borrower_email: Optional[str] = None
    borrower_name: Optional[str] = None


class WaiveRequestBody(BaseModel):
    """Request to waive a document requirement."""
    reason: str
    waived_by: str


class ManualReviewBody(BaseModel):
    """Request for manual document review."""
    decision: str  # "accept" or "reject"
    reviewer: str
    notes: Optional[str] = None


class UpdatePayrollFrequencyBody(BaseModel):
    """Request to update payroll frequency."""
    borrower_id: int
    frequency: str  # WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY


# =============================================================================
# Needs List Endpoints
# =============================================================================

@router.post("/needs-list/generate")
async def generate_needs_list(
    request: GenerateNeedsListRequest,
    db: Session = Depends(get_db),
):
    """
    Generate a document needs list for a loan application.

    Based on the loan program, occupancy, and income type, generates
    appropriate document requirements using templates.
    """
    try:
        generator = NeedsListGenerator(db)
        result = generator.generate_needs_list(
            loan_id=request.loan_id,
            loan_program=request.loan_program,
            occupancy_type=request.occupancy_type,
            income_type=request.income_type,
            borrower_id=request.borrower_id,
            co_borrower_id=request.co_borrower_id,
            has_gift_funds=request.has_gift_funds,
            is_self_employed=request.is_self_employed,
            has_bankruptcy=request.has_bankruptcy,
            property_type=request.property_type,
        )
        return result
    except Exception as e:
        logger.exception(f"Failed to generate needs list: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/needs-list/{loan_id}")
async def get_needs_list(
    loan_id: int,
    db: Session = Depends(get_db),
):
    """Get the current needs list for a loan."""
    generator = NeedsListGenerator(db)
    return generator.get_needs_list(loan_id)


@router.post("/needs-list/{loan_id}/custom-request")
async def add_custom_request(
    loan_id: int,
    borrower_id: int = Query(...),
    body: AddCustomRequestBody = None,
    db: Session = Depends(get_db),
):
    """
    Add a custom document request to the needs list.

    Optionally sends an email notification to the borrower if send_notification
    is set to True and borrower_email is provided.
    """
    generator = NeedsListGenerator(db)
    result = generator.add_custom_request(
        loan_id=loan_id,
        borrower_id=borrower_id,
        title=body.title,
        description=body.description,
        instructions=body.instructions,
        priority=body.priority,
        due_date=body.due_date,
    )

    # Send notification if requested
    notification_sent = False
    if body.send_notification and body.borrower_email:
        try:
            # Get the created request from the database
            request = db.query(DocumentRequest).filter(
                DocumentRequest.loan_id == loan_id,
                DocumentRequest.title == body.title
            ).order_by(DocumentRequest.created_at.desc()).first()

            if request:
                notification_service = SmartDocsNotificationService(db)
                notification_sent = notification_service.send_document_request_notification(
                    request=request,
                    borrower_email=body.borrower_email,
                    borrower_name=body.borrower_name or "Borrower",
                )
        except Exception as e:
            logger.error(f"Failed to send notification for custom request: {e}")

    # Add notification status to response
    if isinstance(result, dict):
        result["notification_sent"] = notification_sent
    return result


@router.post("/needs-list/request/{request_id}/waive")
async def waive_request(
    request_id: int,
    body: WaiveRequestBody,
    db: Session = Depends(get_db),
):
    """Waive a document request."""
    generator = NeedsListGenerator(db)
    try:
        return generator.waive_request(
            request_id=request_id,
            reason=body.reason,
            waived_by=body.waived_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# Document Upload & Processing
# =============================================================================

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    loan_id: int = Form(...),
    borrower_id: int = Form(...),
    request_id: Optional[int] = Form(None),
    doc_type: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Upload and process a document.

    Runs the full processing pipeline including:
    - Screenshot detection
    - Date extraction
    - Freshness validation
    - Accept/reject decision
    """
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Read file content
    file_content = await file.read()

    # Get file info
    mime_type = file.content_type or "application/octet-stream"
    file_size = len(file_content)

    # Validate file size (max 20MB)
    if file_size > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    # Parse doc_type
    parsed_doc_type = None
    if doc_type:
        try:
            parsed_doc_type = DocType(doc_type)
        except ValueError:
            logger.warning(f"Invalid doc_type: {doc_type}")

    # Get S3 service
    s3_service = get_smart_docs_s3_service()

    # Generate storage key
    storage_key = s3_service.generate_storage_key(
        loan_id=loan_id,
        borrower_id=borrower_id,
        file_name=file.filename
    )

    # Create document record
    document = SmartDocument(
        request_id=request_id,
        loan_id=loan_id,
        borrower_id=borrower_id,
        file_name=file.filename,
        mime_type=mime_type,
        file_size=file_size,
        storage_key=storage_key,
        doc_type=parsed_doc_type,
        status="UPLOADED",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Upload file to S3
    upload_result = s3_service.upload_file(
        file_content=file_content,
        storage_key=storage_key,
        content_type=mime_type,
        metadata={
            "loan_id": str(loan_id),
            "borrower_id": str(borrower_id),
            "document_id": str(document.id),
            "original_filename": file.filename
        }
    )

    if not upload_result.get("success"):
        logger.warning(f"S3 upload failed for document {document.id}: {upload_result.get('error')}")
        # Continue processing even if S3 fails (for development/testing without S3)

    # Process the document
    pipeline = DocumentReviewPipeline(db)
    result = pipeline.process_document(
        document_id=document.id,
        file_content=file_content,
        mime_type=mime_type,
        filename=file.filename,
        doc_type=parsed_doc_type,
        request_id=request_id,
    )

    return pipeline.result_to_dict(result)


@router.get("/document/{document_id}")
async def get_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    """Get document details and processing results."""
    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": document.id,
        "loan_id": document.loan_id,
        "borrower_id": document.borrower_id,
        "request_id": document.request_id,
        "file_name": document.file_name,
        "mime_type": document.mime_type,
        "file_size": document.file_size,
        "doc_type": document.doc_type.value if document.doc_type else None,
        "detected_doc_type": document.detected_doc_type,
        "status": document.status,
        "decision": document.decision.value if document.decision else None,
        "rejection_category": document.rejection_category.value if document.rejection_category else None,
        "rejection_reason": document.rejection_reason,
        "fix_instructions": document.fix_instructions,
        "screenshot_detection": {
            "is_screenshot": document.detected_is_screenshot,
            "confidence": document.screenshot_confidence,
            "reasons": document.screenshot_reasons,
        },
        "dates": {
            "doc_date": document.doc_date.isoformat() if document.doc_date else None,
            "extracted_dates": document.extracted_dates,
            "expires_at": document.doc_expires_at.isoformat() if document.doc_expires_at else None,
            "is_expired": document.is_expired,
            "days_until_expiration": document.days_until_expiration,
        },
        "extraction_confidence": document.extraction_confidence,
        "reviewed_at": document.reviewed_at.isoformat() if document.reviewed_at else None,
        "reviewed_by": document.reviewed_by,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    }


@router.get("/document/{document_id}/download")
async def download_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    """
    Get a presigned URL to download a document.

    Returns a temporary URL that can be used to download the file directly from S3.
    """
    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.storage_key:
        raise HTTPException(status_code=404, detail="Document file not available")

    s3_service = get_smart_docs_s3_service()

    if not s3_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Document storage not configured"
        )

    result = s3_service.get_presigned_download_url(
        storage_key=document.storage_key,
        file_name=document.file_name,
        expires_in=300  # 5 minutes
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate download URL: {result.get('error')}"
        )

    return {
        "document_id": document.id,
        "file_name": document.file_name,
        "download_url": result["presigned_url"],
        "expires_in": result["expires_in"],
        "content_type": document.mime_type,
        "file_size": document.file_size
    }


@router.post("/document/{document_id}/manual-review")
async def manual_review_document(
    document_id: int,
    body: ManualReviewBody,
    db: Session = Depends(get_db),
):
    """Submit a manual review decision for a document."""
    pipeline = DocumentReviewPipeline(db)
    try:
        return pipeline.manual_review(
            document_id=document_id,
            decision=body.decision,
            reviewer=body.reviewer,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/document/{document_id}/reprocess")
async def reprocess_document(
    document_id: int,
    db: Session = Depends(get_db),
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
    pipeline = DocumentReviewPipeline(db)
    try:
        result = pipeline.reprocess_document(document_id)
        return pipeline.result_to_dict(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/documents/{loan_id}")
async def get_loan_documents(
    loan_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get all documents for a loan."""
    query = db.query(SmartDocument).filter(
        SmartDocument.loan_id == loan_id
    )

    if status:
        query = query.filter(SmartDocument.status == status)

    documents = query.order_by(SmartDocument.created_at.desc()).all()

    return {
        "loan_id": loan_id,
        "total": len(documents),
        "documents": [
            {
                "id": doc.id,
                "file_name": doc.file_name,
                "doc_type": doc.doc_type.value if doc.doc_type else None,
                "status": doc.status,
                "decision": doc.decision.value if doc.decision else None,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in documents
        ],
    }


# =============================================================================
# Freshness & Expiration
# =============================================================================

@router.get("/expiring")
async def get_expiring_documents(
    loan_id: Optional[int] = None,
    days_ahead: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """Get documents expiring within the specified window."""
    scheduler = AutoRenewalScheduler(db)
    return {
        "days_ahead": days_ahead,
        "expiring_documents": scheduler.get_upcoming_expirations(
            loan_id=loan_id,
            days_ahead=days_ahead,
        ),
    }


@router.post("/check-expiration")
async def run_expiration_check(
    db: Session = Depends(get_db),
):
    """Run expiration check and mark expired documents."""
    scheduler = AutoRenewalScheduler(db)
    return scheduler.run_expiration_check()


@router.post("/process-renewals")
async def process_renewals(
    db: Session = Depends(get_db),
):
    """Process pending document renewals."""
    scheduler = AutoRenewalScheduler(db)
    return scheduler.process_pending_renewals()


# =============================================================================
# Payroll Frequency
# =============================================================================

@router.post("/infer-payroll-frequency/{borrower_id}")
async def infer_payroll_frequency(
    borrower_id: int,
    db: Session = Depends(get_db),
):
    """Infer payroll frequency from historical paystub data."""
    scheduler = AutoRenewalScheduler(db)
    frequency = scheduler.infer_payroll_frequency(borrower_id)

    return {
        "borrower_id": borrower_id,
        "inferred_frequency": frequency.value if frequency else None,
        "inferred": frequency is not None,
    }


@router.post("/payroll-frequency/{loan_id}")
async def update_payroll_frequency(
    loan_id: int,
    body: UpdatePayrollFrequencyBody,
    db: Session = Depends(get_db),
):
    """Update payroll frequency for a loan's paystub requests."""
    try:
        frequency = PayrollFrequency(body.frequency)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid frequency. Must be one of: {[f.value for f in PayrollFrequency]}"
        )

    scheduler = AutoRenewalScheduler(db)
    updated = scheduler.update_payroll_frequency(
        loan_id=loan_id,
        borrower_id=body.borrower_id,
        frequency=frequency,
    )

    return {
        "loan_id": loan_id,
        "borrower_id": body.borrower_id,
        "frequency": frequency.value,
        "requests_updated": updated,
    }


# =============================================================================
# Templates
# =============================================================================

@router.get("/templates")
async def list_templates(
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    """List available needs list templates."""
    import json

    query = db.query(NeedsListTemplate)
    if active_only:
        query = query.filter(NeedsListTemplate.is_active == True)

    templates = query.order_by(NeedsListTemplate.name).all()

    return {
        "total": len(templates),
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "description": t.description,
                "loan_programs": json.loads(t.loan_programs) if t.loan_programs else [],
                "occupancy_types": json.loads(t.occupancy_types) if t.occupancy_types else [],
                "income_types": json.loads(t.income_types) if t.income_types else [],
                "is_active": t.is_active,
                "version": t.version,
            }
            for t in templates
        ],
    }


@router.get("/templates/{template_id}")
async def get_template(
    template_id: int,
    db: Session = Depends(get_db),
):
    """Get a specific needs list template."""
    import json

    template = db.query(NeedsListTemplate).filter(
        NeedsListTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return {
        "id": template.id,
        "name": template.name,
        "slug": template.slug,
        "description": template.description,
        "loan_programs": json.loads(template.loan_programs) if template.loan_programs else [],
        "occupancy_types": json.loads(template.occupancy_types) if template.occupancy_types else [],
        "income_types": json.loads(template.income_types) if template.income_types else [],
        "request_templates": json.loads(template.request_templates) if template.request_templates else [],
        "is_active": template.is_active,
        "version": template.version,
    }


# =============================================================================
# Events / Audit Log
# =============================================================================

@router.get("/events/{loan_id}")
async def get_loan_events(
    loan_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Get document policy events for a loan."""
    events = db.query(DocPolicyEvent).filter(
        DocPolicyEvent.loan_id == loan_id
    ).order_by(
        DocPolicyEvent.created_at.desc()
    ).limit(limit).all()

    return {
        "loan_id": loan_id,
        "total": len(events),
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type.value,
                "request_id": e.request_id,
                "document_id": e.document_id,
                "payload": e.payload,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
    }


# =============================================================================
# Applicant Views - Dashboard Endpoints
# =============================================================================

@router.get("/applicants/pending-review")
async def get_applicants_with_pending_review(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Get all applicants/loans that have documents pending review.
    Returns grouped by loan with summary of pending documents.
    """
    from sqlalchemy import func, distinct
    from models.purl import PURLLoan, PURLWorkspace

    # Get loans with pending documents
    pending_docs_query = db.query(
        SmartDocument.loan_id,
        func.count(SmartDocument.id).label('pending_count'),
        func.min(SmartDocument.uploaded_at).label('oldest_upload')
    ).filter(
        SmartDocument.status == 'PENDING_REVIEW'
    ).group_by(SmartDocument.loan_id)

    # Get total count
    total_query = db.query(func.count(distinct(SmartDocument.loan_id))).filter(
        SmartDocument.status == 'PENDING_REVIEW'
    ).scalar() or 0

    # Paginate
    offset = (page - 1) * limit
    pending_loans = pending_docs_query.order_by(
        func.min(SmartDocument.uploaded_at).asc()
    ).offset(offset).limit(limit).all()

    applicants = []
    for loan_id, pending_count, oldest_upload in pending_loans:
        # Get loan/workspace info
        loan = db.query(PURLLoan).filter(PURLLoan.id == loan_id).first()
        workspace = None
        if loan and loan.workspace_id:
            workspace = db.query(PURLWorkspace).filter(
                PURLWorkspace.id == loan.workspace_id
            ).first()

        # Get pending document details
        pending_docs = db.query(SmartDocument).filter(
            SmartDocument.loan_id == loan_id,
            SmartDocument.status == 'PENDING_REVIEW'
        ).all()

        applicants.append({
            "loan_id": loan_id,
            "loan_number": loan.loan_number if loan else None,
            "borrower_name": workspace.display_name if workspace else f"Loan {loan_id}",
            "loan_purpose": loan.loan_purpose if loan else None,
            "pending_count": pending_count,
            "oldest_upload": oldest_upload.isoformat() if oldest_upload else None,
            "documents": [
                {
                    "id": doc.id,
                    "file_name": doc.original_filename,
                    "doc_type": doc.doc_type.value if doc.doc_type else None,
                    "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                }
                for doc in pending_docs
            ]
        })

    return {
        "total": total_query,
        "page": page,
        "limit": limit,
        "total_pages": (total_query + limit - 1) // limit,
        "applicants": applicants,
    }


@router.get("/applicants/outstanding-docs")
async def get_applicants_with_outstanding_docs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    include_overdue_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """
    Get all applicants/loans that have outstanding document requests (needs list items not fulfilled).
    Returns grouped by loan with summary of outstanding requirements.
    """
    from sqlalchemy import func, distinct
    from models.purl import PURLLoan, PURLWorkspace

    # Build filter for outstanding requests
    outstanding_filter = [DocumentRequest.status == RequestStatus.OPEN]

    if include_overdue_only:
        outstanding_filter.append(DocumentRequest.due_date < datetime.utcnow())

    # Get loans with outstanding requests
    outstanding_query = db.query(
        DocumentRequest.loan_id,
        func.count(DocumentRequest.id).label('outstanding_count'),
        func.count().filter(
            DocumentRequest.due_date < datetime.utcnow()
        ).label('overdue_count'),
        func.min(DocumentRequest.due_date).label('nearest_due')
    ).filter(
        *outstanding_filter
    ).group_by(DocumentRequest.loan_id)

    # Get total count
    total_query = db.query(func.count(distinct(DocumentRequest.loan_id))).filter(
        *outstanding_filter
    ).scalar() or 0

    # Paginate - prioritize by overdue and nearest due date
    offset = (page - 1) * limit
    outstanding_loans = outstanding_query.order_by(
        func.count().filter(DocumentRequest.due_date < datetime.utcnow()).desc(),
        func.min(DocumentRequest.due_date).asc().nullslast()
    ).offset(offset).limit(limit).all()

    applicants = []
    for loan_id, outstanding_count, overdue_count, nearest_due in outstanding_loans:
        # Get loan/workspace info - try PURLLoan first
        loan = db.query(PURLLoan).filter(PURLLoan.id == loan_id).first()
        workspace = None
        borrower_name = None
        loan_number = None
        loan_purpose = None

        if loan:
            loan_number = loan.loan_number
            loan_purpose = loan.loan_purpose
            if loan.workspace_id:
                workspace = db.query(PURLWorkspace).filter(
                    PURLWorkspace.id == loan.workspace_id
                ).first()

        # Try to get borrower name from various sources
        if workspace and workspace.display_name:
            borrower_name = workspace.display_name
        else:
            # Try to get borrower from purl_contacts
            from models.purl import PURLContact
            if loan and loan.workspace_id:
                borrower_contact = db.query(PURLContact).filter(
                    PURLContact.workspace_id == loan.workspace_id,
                    PURLContact.contact_type == 'borrower'
                ).first()
                if borrower_contact:
                    borrower_name = f"{borrower_contact.first_name or ''} {borrower_contact.last_name or ''}".strip()

            # If still no borrower name, try the main loans table
            if not borrower_name:
                from models.leads import Lead
                try:
                    # Check if there's a lead associated
                    if workspace and workspace.meta_data:
                        lead_id = workspace.meta_data.get('lead_id')
                        if lead_id:
                            lead = db.query(Lead).filter(Lead.id == lead_id).first()
                            if lead:
                                borrower_name = lead.name
                except Exception:
                    pass

        # Fallback to loan ID if no name found
        if not borrower_name:
            borrower_name = f"Loan {loan_id}"

        # Get outstanding requests
        requests = db.query(DocumentRequest).filter(
            DocumentRequest.loan_id == loan_id,
            DocumentRequest.status == RequestStatus.OPEN
        ).order_by(
            DocumentRequest.priority.desc(),
            DocumentRequest.due_date.asc().nullslast()
        ).all()

        applicants.append({
            "loan_id": loan_id,
            "loan_number": loan_number,
            "borrower_name": borrower_name,
            "loan_purpose": loan_purpose,
            "outstanding_count": outstanding_count,
            "overdue_count": overdue_count or 0,
            "nearest_due": nearest_due.isoformat() if nearest_due else None,
            "requests": [
                {
                    "id": req.id,
                    "title": req.title,
                    "doc_type": req.doc_type.value if req.doc_type else None,
                    "priority": req.priority.value if req.priority else "NORMAL",
                    "due_date": req.due_date.isoformat() if req.due_date else None,
                    "is_overdue": req.due_date and req.due_date < datetime.utcnow(),
                }
                for req in requests
            ]
        })

    return {
        "total": total_query,
        "page": page,
        "limit": limit,
        "total_pages": (total_query + limit - 1) // limit,
        "applicants": applicants,
    }


@router.get("/dashboard/summary")
async def get_document_dashboard_summary(
    db: Session = Depends(get_db),
):
    """
    Get summary statistics for the document management dashboard.
    """
    from sqlalchemy import func

    # Pending review count
    pending_review = db.query(func.count(SmartDocument.id)).filter(
        SmartDocument.status == 'PENDING_REVIEW'
    ).scalar() or 0

    # Pending review by unique loans
    pending_review_loans = db.query(func.count(func.distinct(SmartDocument.loan_id))).filter(
        SmartDocument.status == 'PENDING_REVIEW'
    ).scalar() or 0

    # Outstanding requests
    outstanding = db.query(func.count(DocumentRequest.id)).filter(
        DocumentRequest.status == RequestStatus.OPEN
    ).scalar() or 0

    # Outstanding by unique loans
    outstanding_loans = db.query(func.count(func.distinct(DocumentRequest.loan_id))).filter(
        DocumentRequest.status == RequestStatus.OPEN
    ).scalar() or 0

    # Overdue requests
    overdue = db.query(func.count(DocumentRequest.id)).filter(
        DocumentRequest.status == RequestStatus.OPEN,
        DocumentRequest.due_date < datetime.utcnow()
    ).scalar() or 0

    # Documents processed today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    processed_today = db.query(func.count(SmartDocument.id)).filter(
        SmartDocument.reviewed_at >= today_start
    ).scalar() or 0

    return {
        "pending_review": {
            "documents": pending_review,
            "applicants": pending_review_loans,
        },
        "outstanding_requests": {
            "total": outstanding,
            "applicants": outstanding_loans,
            "overdue": overdue,
        },
        "activity": {
            "processed_today": processed_today,
        },
        "generated_at": datetime.utcnow().isoformat(),
    }


# =============================================================================
# Loans for Smart Docs (All Active Loans)
# =============================================================================

@router.get("/loans")
async def get_smart_docs_loans(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    stage: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Get all loans for Smart Docs dashboard.

    This endpoint returns all loans in active stages for document tracking purposes.
    Unlike the main /api/v1/loans/ endpoint, this does NOT filter by loan_officer_id
    because Smart Docs is a document management tool that should show all active loans.
    """
    from sqlalchemy import text

    try:
        # Build WHERE clause for active loans (exclude funded, cancelled, denied)
        where_clauses = ["stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED', 'DENIED')"]
        params = {"skip": skip, "limit": limit}

        # Filter by specific stage if provided
        if stage:
            where_clauses = [f"UPPER(stage) = :stage"]
            params["stage"] = stage.upper()

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        sql = f"""
            SELECT id, loan_number, borrower_name, borrower_email, borrower_phone,
                   coborrower_name, co_borrower_email,
                   stage, program, amount, rate,
                   closing_date, days_in_stage, sla_status, created_at,
                   loan_officer_name, loan_officer_email, processor, processor_email,
                   underwriter, underwriter_email, closer, closer_email,
                   property_address, loan_type, purchase_price, down_payment
            FROM loans
            WHERE {where_sql}
            ORDER BY created_at DESC
            OFFSET :skip LIMIT :limit
        """

        results = db.execute(text(sql), params).fetchall()

        # Convert to list of dicts
        loans = []
        for row in results:
            row_dict = dict(row._mapping)
            # Normalize stage
            stage_val = row_dict.get('stage', '')
            if stage_val:
                row_dict['stage'] = str(stage_val).upper()
            else:
                row_dict['stage'] = 'PROCESSING'
            loans.append(row_dict)

        # Get total count for pagination
        count_sql = f"SELECT COUNT(*) FROM loans WHERE {where_sql}"
        total = db.execute(text(count_sql), params).scalar() or 0

        return {
            "loans": loans,
            "total": total,
            "page": skip // limit + 1 if limit > 0 else 1,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if limit > 0 else 1,
        }
    except Exception as e:
        logger.exception(f"Error fetching loans for Smart Docs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Health Check
# =============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "smart-docs",
        "timestamp": datetime.utcnow().isoformat(),
    }
