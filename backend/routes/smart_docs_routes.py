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
    borrower_id: int,
    body: AddCustomRequestBody,
    db: Session = Depends(get_db),
):
    """Add a custom document request to the needs list."""
    generator = NeedsListGenerator(db)
    return generator.add_custom_request(
        loan_id=loan_id,
        borrower_id=borrower_id,
        title=body.title,
        description=body.description,
        instructions=body.instructions,
        priority=body.priority,
        due_date=body.due_date,
    )


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

    # Create document record
    document = SmartDocument(
        request_id=request_id,
        loan_id=loan_id,
        borrower_id=borrower_id,
        file_name=file.filename,
        mime_type=mime_type,
        file_size=file_size,
        storage_key=f"smart-docs/{loan_id}/{borrower_id}/{datetime.utcnow().isoformat()}/{file.filename}",
        doc_type=parsed_doc_type,
        status="UPLOADED",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # TODO: Upload file to S3
    # s3_client.upload_fileobj(BytesIO(file_content), bucket, document.storage_key)

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
