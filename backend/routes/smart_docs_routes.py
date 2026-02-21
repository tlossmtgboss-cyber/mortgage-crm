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
import os
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from main import get_current_user
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
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)
_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")


def _get_loan_org_id(db: Session, loan_id: int) -> Optional[int]:
    """Look up organization_id for a loan (for S3 tenant isolation)."""
    row = db.execute(sa_text("SELECT organization_id FROM loans WHERE id = :id"), {"id": loan_id}).first()
    return row[0] if row else None


def _verify_loan_tenant(db: Session, loan_id: int, current_user) -> None:
    """Verify the requesting user's org owns the loan. Raises 404 if not."""
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
    if org_id and not is_platform_admin:
        loan_org = _get_loan_org_id(db, loan_id)
        if loan_org is not None and loan_org != org_id:
            raise HTTPException(status_code=404, detail="Not found")


def _verify_document_tenant(db: Session, document_id: int, current_user) -> None:
    """Verify the requesting user's org owns the document's loan. Raises 404 if not."""
    from models.smart_docs_models import SmartDocument as _SD
    doc = db.query(_SD).filter(_SD.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    if doc.loan_id:
        _verify_loan_tenant(db, doc.loan_id, current_user)
    return doc


def _verify_request_tenant(db: Session, request_id: int, current_user) -> None:
    """Verify the requesting user's org owns the document request's loan. Raises 404 if not."""
    from models.smart_docs_models import DocumentRequest as _DR
    req = db.query(_DR).filter(_DR.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    if req.loan_id:
        _verify_loan_tenant(db, req.loan_id, current_user)

router = APIRouter(
    prefix="/api/v1/smart-docs",
    tags=["Smart Documents"],
    dependencies=[Depends(get_current_user)],
)


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


class DeleteDocumentBody(BaseModel):
    """Request to delete (trash) a document."""
    reviewer: str
    reason: Optional[str] = None


class RejectDocumentBody(BaseModel):
    """Request to reject a document."""
    reviewer: str
    reason: str
    rejection_category: Optional[str] = None  # SCREENSHOT, EXPIRED, POOR_QUALITY, INCOMPLETE, WRONG_TYPE, OTHER


class ReRequestDocumentBody(BaseModel):
    """Request to re-request a document (reset request to OPEN)."""
    reviewer: str
    notes: Optional[str] = None
    new_due_date: Optional[str] = None  # ISO date string


class UpdatePayrollFrequencyBody(BaseModel):
    """Request to update payroll frequency."""
    borrower_id: int
    frequency: str  # WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY


class UpdateDocumentTypeBody(BaseModel):
    """Request to update a document's type."""
    doc_type: str  # PAYSTUB, W2, DRIVERS_LICENSE, BANK_STATEMENT, etc.


class MergeDocumentsRequest(BaseModel):
    """Request to merge multiple documents into a single PDF."""
    loan_id: int
    document_ids: List[int]
    recipient_email: Optional[str] = None  # For merge-email endpoint


class ApplicationDocumentItem(BaseModel):
    """A single document requirement from the application."""
    id: str
    name: str
    description: str
    category: str  # 'identity', 'income', 'assets'
    stage: str


class SyncApplicationDocumentsRequest(BaseModel):
    """Request to sync document requirements from application."""
    loan_id: int
    workspace_slug: Optional[str] = None
    borrower_first_name: str
    co_borrower_first_name: Optional[str] = None
    documents: List[ApplicationDocumentItem]


# =============================================================================
# Document ID to DocType Mapping
# =============================================================================

# Maps frontend document IDs to Smart Docs DocType enum
DOCUMENT_ID_TO_DOC_TYPE = {
    # Identity documents
    'id': DocType.DRIVERS_LICENSE,
    'coborrower_id': DocType.DRIVERS_LICENSE,
    'green_card': DocType.OTHER,
    'visa_docs': DocType.OTHER,
    'va_coe': DocType.VA_COE,
    'va_pending_claim': DocType.OTHER,

    # Income documents
    'paystubs': DocType.PAYSTUB,
    'coborrower_paystubs': DocType.PAYSTUB,
    'w2_recent': DocType.W2,
    'w2_prior': DocType.W2,
    'coborrower_w2_recent': DocType.W2,
    'coborrower_w2_prior': DocType.W2,
    'tax_returns': DocType.TAX_RETURN,
    'tax_returns_recent': DocType.TAX_RETURN,
    'tax_returns_prior': DocType.TAX_RETURN,
    'business_tax_returns': DocType.BUSINESS_TAX_RETURN,
    'business_tax_returns_recent': DocType.BUSINESS_TAX_RETURN,
    'business_tax_returns_prior': DocType.BUSINESS_TAX_RETURN,
    'profit_loss': DocType.PROFIT_LOSS,
    'business_bank_statements': DocType.BANK_STATEMENT,
    'articles_incorporation': DocType.OTHER,
    'rental_tax_returns': DocType.TAX_RETURN,

    # Asset documents
    'bank_statements': DocType.BANK_STATEMENT,
    'coborrower_bank_statements': DocType.BANK_STATEMENT,
    'investment_statements': DocType.INVESTMENT_STATEMENT,
    'gift_letter': DocType.GIFT_LETTER,
    'existing_mortgage_statement': DocType.OTHER,
    'lease_agreement': DocType.LEASE_AGREEMENT,
    'new_credit_statement': DocType.OTHER,

    # Special documents
    'divorce_decree': DocType.OTHER,
    'property_settlement': DocType.OTHER,
    'irs_payment_arrangement': DocType.OTHER,
    'irs_payoff': DocType.OTHER,
    'bankruptcy_docs': DocType.BANKRUPTCY_DISCHARGE,
    'bankruptcy_discharge': DocType.BANKRUPTCY_DISCHARGE,
    'ch13_payment_history': DocType.OTHER,
    'ch13_court_approval': DocType.OTHER,
    'ch12_payment_history': DocType.OTHER,
    'ch12_court_approval': DocType.OTHER,
}

# Freshness requirements (days) for different doc types
FRESHNESS_DAYS = {
    DocType.PAYSTUB: 30,
    DocType.BANK_STATEMENT: 60,
    DocType.INVESTMENT_STATEMENT: 90,
    DocType.W2: 365,
    DocType.TAX_RETURN: 365,
    DocType.BUSINESS_TAX_RETURN: 365,
}


# =============================================================================
# Needs List Endpoints
# =============================================================================

@router.post("/needs-list/generate")
async def generate_needs_list(
    request: GenerateNeedsListRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Generate a document needs list for a loan application.

    Based on the loan program, occupancy, and income type, generates
    appropriate document requirements using templates.
    """
    try:
        _verify_loan_tenant(db, request.loan_id, current_user)
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/needs-list/{loan_id}")
async def get_needs_list(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get the current needs list for a loan with borrower info and document URLs."""
    from sqlalchemy import text

    _verify_loan_tenant(db, loan_id, current_user)

    # Get org_id for tenant validation in S3 operations
    org_id = getattr(current_user, 'organization_id', None)

    generator = NeedsListGenerator(db)
    result = generator.get_needs_list(loan_id)

    # Fetch borrower info from loans table
    loan_info = db.execute(text("""
        SELECT borrower_name, borrower_email, loan_number, stage
        FROM loans WHERE id = :loan_id
    """), {"loan_id": loan_id}).fetchone()

    if loan_info:
        result["borrower_name"] = loan_info.borrower_name
        result["borrower_email"] = loan_info.borrower_email
        result["loan_number"] = loan_info.loan_number
        result["stage"] = loan_info.stage
    else:
        # Fallback: try PURL system
        from models.purl import PURLLoan, PURLWorkspace, PURLContact
        purl_loan = db.query(PURLLoan).filter(PURLLoan.id == loan_id).first()
        if purl_loan and purl_loan.workspace_id:
            workspace = db.query(PURLWorkspace).filter(
                PURLWorkspace.id == purl_loan.workspace_id
            ).first()
            if workspace:
                result["borrower_name"] = workspace.display_name
                result["loan_number"] = purl_loan.loan_number
                result["stage"] = purl_loan.loan_purpose
                # Try to get email from contacts
                borrower_contact = db.query(PURLContact).filter(
                    PURLContact.workspace_id == purl_loan.workspace_id,
                    PURLContact.contact_type == 'borrower'
                ).first()
                if borrower_contact:
                    result["borrower_email"] = borrower_contact.email
                    if not result.get("borrower_name"):
                        result["borrower_name"] = f"{borrower_contact.first_name or ''} {borrower_contact.last_name or ''}".strip()

    # Enrich each request with uploaded document info
    for req in result.get("all_requests", []):
        request_id = req.get("id")
        if request_id:
            # Get uploaded documents for this request (exclude deleted/superseded)
            uploaded_docs = db.query(SmartDocument).filter(
                SmartDocument.request_id == request_id,
                SmartDocument.status.notin_(["DELETED", "SUPERSEDED"])
            ).order_by(SmartDocument.created_at.desc()).all()

            if uploaded_docs:
                latest_doc = uploaded_docs[0]
                req["filename"] = latest_doc.file_name
                req["uploaded_at"] = latest_doc.created_at.isoformat() if latest_doc.created_at else None

                # Generate presigned URL for viewing - verify file exists first
                if latest_doc.storage_key:
                    s3_service = get_smart_docs_s3_service()
                    if s3_service.is_available:
                        # Check if file actually exists in S3 before generating URL
                        if s3_service.file_exists(latest_doc.storage_key):
                            url_result = s3_service.get_presigned_download_url(
                                storage_key=latest_doc.storage_key,
                                file_name=latest_doc.file_name,
                                expires_in=3600,  # 1 hour
                                inline=True,  # Use inline disposition for iframe viewing
                                organization_id=org_id  # Pass org_id for tenant validation
                            )
                            if url_result.get("success"):
                                req["file_url"] = url_result["presigned_url"]
                                req["s3_url"] = url_result["presigned_url"]
                        else:
                            # File doesn't exist in S3 - mark as storage error
                            req["storage_error"] = True
                            req["storage_error_message"] = "Document file not found in storage. Please re-upload."
                            logger.warning(f"S3 file not found for document {latest_doc.id}: {latest_doc.storage_key}")

                req["document_id"] = latest_doc.id
                req["doc_date"] = latest_doc.doc_date.isoformat() if latest_doc.doc_date else None
                req["expiration_date"] = latest_doc.doc_expires_at.isoformat() if latest_doc.doc_expires_at else None

    return result


@router.post("/needs-list/sync-from-application")
async def sync_documents_from_application(
    request: SyncApplicationDocumentsRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Sync document requirements from a mortgage application to Smart Docs.

    This endpoint receives the document requirements generated by the frontend
    application form and creates corresponding DocumentRequest records in the
    Smart Docs system. This allows borrowers to see and fulfill their document
    requirements in the client portal.
    """
    try:
        _verify_loan_tenant(db, request.loan_id, current_user)
        created_requests = []
        skipped_count = 0

        # Check for existing requests to avoid duplicates
        existing_requests = db.query(DocumentRequest).filter(
            DocumentRequest.loan_id == request.loan_id,
            DocumentRequest.is_active == True
        ).all()
        existing_titles = {r.title for r in existing_requests}

        for doc in request.documents:
            # Skip if already exists
            if doc.name in existing_titles:
                skipped_count += 1
                continue

            # Map frontend doc ID to DocType
            doc_type = DOCUMENT_ID_TO_DOC_TYPE.get(doc.id, DocType.OTHER)

            # Determine if this is a co-borrower document
            is_coborrower = doc.id.startswith('coborrower_')
            applies_to = AppliesTo.CO_BORROWER if is_coborrower else AppliesTo.BORROWER

            # Determine priority based on category
            if doc.category == 'identity':
                priority = RequestPriority.HIGH
            elif doc.category == 'income':
                priority = RequestPriority.HIGH
            else:
                priority = RequestPriority.NORMAL

            # Get freshness days for this doc type
            freshness_days = FRESHNESS_DAYS.get(doc_type)

            # Create the document request
            doc_request = DocumentRequest(
                loan_id=request.loan_id,
                doc_type=doc_type,
                title=doc.name,
                description=doc.description,
                instructions=f"Please upload {doc.description}",
                priority=priority,
                applies_to=applies_to,
                freshness_days=freshness_days,
                status=RequestStatus.OPEN,
                is_active=True,
            )
            db.add(doc_request)
            created_requests.append({
                "id": doc.id,
                "title": doc.name,
                "doc_type": doc_type.value,
                "priority": priority.value,
            })

        db.commit()

        # Log the sync event
        if created_requests:
            event = DocPolicyEvent(
                loan_id=request.loan_id,
                event_type="NEEDS_LIST_GENERATED",
                payload={
                    "source": "application_sync",
                    "documents_synced": len(created_requests),
                    "skipped": skipped_count,
                    "borrower": request.borrower_first_name,
                    "co_borrower": request.co_borrower_first_name,
                }
            )
            db.add(event)
            db.commit()

        return {
            "success": True,
            "loan_id": request.loan_id,
            "created_count": len(created_requests),
            "skipped_count": skipped_count,
            "created_requests": created_requests,
            "message": f"Synced {len(created_requests)} document requirements"
        }

    except SQLAlchemyError as e:
        logger.exception(f"Failed to sync documents from application: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/needs-list/{loan_id}/custom-request")
async def add_custom_request(
    loan_id: int,
    borrower_id: int = Query(...),
    body: AddCustomRequestBody = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Add a custom document request to the needs list.

    Optionally sends an email notification to the borrower if send_notification
    is set to True and borrower_email is provided.
    """
    _verify_loan_tenant(db, loan_id, current_user)
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
        except SQLAlchemyError as e:
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
    current_user = Depends(get_current_user),
):
    """Waive a document request."""
    _verify_request_tenant(db, request_id, current_user)
    generator = NeedsListGenerator(db)
    try:
        return generator.waive_request(
            request_id=request_id,
            reason=body.reason,
            waived_by=body.waived_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")


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
    current_user = Depends(get_current_user),
):
    """
    Upload and process a document.

    Runs the full processing pipeline including:
    - Screenshot detection
    - Date extraction
    - Freshness validation
    - Accept/reject decision
    """
    _verify_loan_tenant(db, loan_id, current_user)
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

    # Check storage quota (MTR-004)
    try:
        from services.storage_quota_service import check_storage_quota
        org_id_for_quota = _get_loan_org_id(db, loan_id)
        if org_id_for_quota:
            allowed, quota_details = check_storage_quota(db, org_id_for_quota, file_size)
            if not allowed:
                raise HTTPException(
                    status_code=413,
                    detail=quota_details.get("error", "Storage quota exceeded")
                )
    except HTTPException:
        raise
    except Exception as quota_err:
        logger.warning(f"Storage quota check skipped: {quota_err}")

    # Parse doc_type
    parsed_doc_type = None
    if doc_type:
        try:
            parsed_doc_type = DocType(doc_type)
        except ValueError:
            logger.warning(f"Invalid doc_type: {doc_type}")

    # Get S3 service
    s3_service = get_smart_docs_s3_service()

    # Generate storage key with org isolation
    org_id = _get_loan_org_id(db, loan_id)
    storage_key = s3_service.generate_storage_key(
        loan_id=loan_id,
        borrower_id=borrower_id,
        file_name=file.filename,
        organization_id=org_id,
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
    else:
        # Record storage usage for quota tracking (MTR-004)
        try:
            from services.storage_quota_service import record_storage_usage
            record_storage_usage(db, org_id, storage_key, file_size, file_type=parsed_doc_type.value if parsed_doc_type else "document")
        except Exception as track_err:
            logger.warning(f"Storage usage tracking skipped: {track_err}")

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
    current_user = Depends(get_current_user),
):
    """Get document details and processing results."""
    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Tenant isolation: verify document belongs to user's organization via loan
    if document.loan_id:
        _verify_loan_tenant(db, document.loan_id, current_user)

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
    current_user = Depends(get_current_user),
):
    """
    Get a presigned URL to download a document.

    Returns a temporary URL that can be used to download the file directly from S3.
    Requires authentication and verifies the requesting user's org matches the document's loan org.
    """
    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Tenant isolation: verify document belongs to user's organization via loan
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
    if document.loan_id and org_id and not is_platform_admin:
        doc_org_id = _get_loan_org_id(db, document.loan_id)
        if doc_org_id is not None and doc_org_id != org_id:
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
        expires_in=300,  # 5 minutes
        organization_id=org_id  # Pass org_id for tenant validation
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


@router.post("/merge")
async def merge_documents(
    request: MergeDocumentsRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Merge multiple documents into a single PDF for download.

    Downloads specified documents from S3, merges them into a single PDF,
    and returns the merged file.
    """
    from fastapi.responses import StreamingResponse
    from pypdf import PdfWriter, PdfReader
    from models.loan import Loan
    import io

    if not request.document_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    # Tenant isolation - verify loan belongs to user's organization
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

    loan_query = db.query(Loan).filter(Loan.id == request.loan_id)
    if not is_platform_admin and org_id:
        loan_query = loan_query.filter(Loan.organization_id == org_id)

    loan = loan_query.first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Get all requested documents
    documents = db.query(SmartDocument).filter(
        SmartDocument.id.in_(request.document_ids),
        SmartDocument.loan_id == request.loan_id
    ).all()

    if not documents:
        raise HTTPException(status_code=404, detail="No documents found")

    if len(documents) != len(request.document_ids):
        raise HTTPException(
            status_code=400,
            detail=f"Some documents not found. Requested {len(request.document_ids)}, found {len(documents)}"
        )

    s3_service = get_smart_docs_s3_service()
    if not s3_service.is_available:
        raise HTTPException(status_code=503, detail="Document storage not available")

    # Download and merge PDFs using PdfWriter (pypdf 4.x)
    writer = PdfWriter()
    merged_any = False
    errors = []

    for doc in documents:
        if not doc.storage_key:
            errors.append(f"{doc.file_name}: No storage key")
            continue

        try:
            # Download file from S3
            download_result = s3_service.download_file(doc.storage_key)
            if not download_result.get("success"):
                errors.append(f"{doc.file_name}: {download_result.get('error', 'Failed to download')}")
                continue

            file_data = download_result["content"]

            # Check if it's a PDF
            if doc.mime_type == "application/pdf" or doc.file_name.lower().endswith('.pdf'):
                pdf_reader = PdfReader(io.BytesIO(file_data))
                for page in pdf_reader.pages:
                    writer.add_page(page)
                merged_any = True
            else:
                # For non-PDF files, skip with warning
                errors.append(f"{doc.file_name}: Not a PDF, skipping")
        except Exception as e:
            logger.error(f"Error processing document {doc.id}: {e}")
            errors.append(f"{doc.file_name}: processing failed")

    if not merged_any:
        raise HTTPException(
            status_code=400,
            detail=f"No PDF documents could be merged. Errors: {', '.join(errors)}"
        )

    # Write merged PDF to bytes
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)

    # Use already-retrieved loan for filename
    filename = f"merged_documents_{loan.borrower_name if loan.borrower_name else request.loan_id}.pdf"

    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.post("/merge-email")
async def merge_and_email_documents(
    request: MergeDocumentsRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Merge multiple documents into a single PDF and email it.

    Downloads specified documents from S3, merges them into a single PDF,
    and sends via email.
    """
    from pypdf import PdfWriter, PdfReader
    from models.loan import Loan
    import io

    if not request.document_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    # Tenant isolation - verify loan belongs to user's organization
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

    loan_query = db.query(Loan).filter(Loan.id == request.loan_id)
    if not is_platform_admin and org_id:
        loan_query = loan_query.filter(Loan.organization_id == org_id)

    loan = loan_query.first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Get all requested documents
    documents = db.query(SmartDocument).filter(
        SmartDocument.id.in_(request.document_ids),
        SmartDocument.loan_id == request.loan_id
    ).all()

    if not documents:
        raise HTTPException(status_code=404, detail="No documents found")

    s3_service = get_smart_docs_s3_service()
    if not s3_service.is_available:
        raise HTTPException(status_code=503, detail="Document storage not available")

    # Determine recipient email
    recipient_email = request.recipient_email
    if not recipient_email:
        # Try to get from loan officer or borrower
        if loan.loan_officer_email:
            recipient_email = loan.loan_officer_email
        elif hasattr(loan, 'borrower_email') and loan.borrower_email:
            recipient_email = loan.borrower_email
        else:
            raise HTTPException(status_code=400, detail="No recipient email provided or available")

    # Download and merge PDFs using PdfWriter (pypdf 4.x)
    writer = PdfWriter()
    merged_any = False
    doc_names = []

    for doc in documents:
        if not doc.storage_key:
            continue

        try:
            download_result = s3_service.download_file(doc.storage_key)
            if not download_result.get("success"):
                logger.warning(f"Failed to download {doc.file_name}: {download_result.get('error')}")
                continue

            file_data = download_result["content"]

            if doc.mime_type == "application/pdf" or doc.file_name.lower().endswith('.pdf'):
                pdf_reader = PdfReader(io.BytesIO(file_data))
                for page in pdf_reader.pages:
                    writer.add_page(page)
                merged_any = True
                doc_names.append(doc.file_name)
        except Exception as e:
            logger.error(f"Error processing document {doc.id} for email: {e}")

    if not merged_any:
        raise HTTPException(status_code=400, detail="No PDF documents could be merged")

    # Write merged PDF to bytes
    output = io.BytesIO()
    writer.write(output)
    pdf_bytes = output.getvalue()

    # Send email with attachment
    try:
        from email_service import EmailService
        email_service = EmailService()

        filename = f"merged_documents_{loan.borrower_name or loan.id}.pdf"

        email_service.send_email(
            to=recipient_email,
            subject=f"Merged Documents - {loan.borrower_name or 'Loan ' + str(loan.id)}",
            body=f"""
            <p>Please find attached the merged documents for loan {loan.loan_number or loan.id}.</p>
            <p>Documents included:</p>
            <ul>
                {''.join(f'<li>{name}</li>' for name in doc_names)}
            </ul>
            <p>This is an automated message from Perennia AI.</p>
            """,
            attachments=[{
                "filename": filename,
                "content": pdf_bytes,
                "content_type": "application/pdf"
            }]
        )

        return {
            "success": True,
            "message": f"Merged {len(doc_names)} documents and sent to {recipient_email}",
            "documents_merged": doc_names,
            "recipient": recipient_email
        }
    except Exception as e:
        logger.error(f"Failed to send merged documents email: {e}")
        raise HTTPException(status_code=500, detail="Failed to send email")


@router.post("/document/{document_id}/manual-review")
async def manual_review_document(
    document_id: int,
    body: ManualReviewBody,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Submit a manual review decision for a document."""
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
# Document Actions (Delete, Reject, Re-request)
# =============================================================================

@router.delete("/document/{document_id}")
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    reviewer: str = Query(..., description="User performing the delete"),
    reason: Optional[str] = Query(None, description="Reason for deletion"),
):
    """
    Delete (trash) a document.

    Sets the document status to DELETED and optionally deletes from S3.
    The document can be restored later if needed.
    """
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
    document.reviewed_at = datetime.utcnow()
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

    db.commit()

    logger.info(f"Document {document_id} deleted by {reviewer} (was: {old_status})")

    return {
        "document_id": document_id,
        "status": "DELETED",
        "previous_status": old_status,
        "deleted_by": reviewer,
        "deleted_at": datetime.utcnow().isoformat(),
        "message": "Document deleted successfully"
    }


@router.patch("/document/{document_id}/type")
async def update_document_type(
    document_id: int,
    body: UpdateDocumentTypeBody,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Update a document's type.

    Allows correcting the document type when AI misclassified or user uploaded
    to wrong category (e.g., W2 uploaded as Driver's License).
    """
    document = db.query(SmartDocument).filter(
        SmartDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Tenant isolation: verify document belongs to user's organization via loan
    if document.loan_id:
        _verify_loan_tenant(db, document.loan_id, current_user)

    # Validate and parse the new doc_type
    try:
        new_doc_type = DocType(body.doc_type)
    except ValueError:
        valid_types = [dt.value for dt in DocType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document type. Valid types: {', '.join(valid_types)}"
        )

    old_doc_type = document.doc_type
    document.doc_type = new_doc_type
    document.updated_at = datetime.utcnow()

    db.commit()

    logger.info(f"Document {document_id} type changed from {old_doc_type} to {new_doc_type}")

    return {
        "document_id": document_id,
        "doc_type": new_doc_type.value,
        "previous_type": old_doc_type.value if old_doc_type else None,
        "message": "Document type updated successfully"
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
    document.reviewed_at = datetime.utcnow()
    document.reviewed_by = body.reviewer

    # Set rejection category if provided
    if body.rejection_category:
        try:
            document.rejection_category = RejectionCategory(body.rejection_category)
        except ValueError:
            pass  # Invalid category, skip

    # Update linked request to allow re-upload
    if document.request_id:
        request = db.query(DocumentRequest).filter(
            DocumentRequest.id == document.request_id
        ).first()
        if request:
            request.status = RequestStatus.OPEN

    db.commit()

    logger.info(f"Document {document_id} rejected by {body.reviewer}: {body.reason}")

    return {
        "document_id": document_id,
        "status": "REJECTED",
        "rejection_reason": body.reason,
        "rejection_category": body.rejection_category,
        "rejected_by": body.reviewer,
        "rejected_at": datetime.utcnow().isoformat(),
        "message": "Document rejected successfully"
    }


@router.post("/document/{document_id}/approve")
async def approve_document(
    document_id: int,
    reviewer: str = Query(..., description="User performing the approval"),
    notes: Optional[str] = Query(None, description="Approval notes"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Approve a document.

    Sets the document status to APPROVED and updates the linked request.
    """
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
    document.reviewed_at = datetime.utcnow()
    document.reviewed_by = reviewer

    # Update linked request
    if document.request_id:
        request = db.query(DocumentRequest).filter(
            DocumentRequest.id == document.request_id
        ).first()
        if request:
            request.status = RequestStatus.ACCEPTED

    db.commit()

    logger.info(f"Document {document_id} approved by {reviewer}")

    return {
        "document_id": document_id,
        "status": "APPROVED",
        "approved_by": reviewer,
        "approved_at": datetime.utcnow().isoformat(),
        "notes": notes,
        "message": "Document approved successfully"
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
    request.updated_at = datetime.utcnow()

    # Set new due date if provided
    if body.new_due_date:
        try:
            request.due_date = datetime.fromisoformat(body.new_due_date.replace('Z', '+00:00'))
        except ValueError:
            pass
    elif not request.due_date or request.due_date < datetime.utcnow():
        # Default to 7 days from now
        request.due_date = datetime.utcnow() + timedelta(days=7)

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

    db.commit()

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
        "re_requested_at": datetime.utcnow().isoformat(),
        "due_date": request.due_date.isoformat() if request.due_date else None,
        "superseded_documents": superseded_count,
        "notification_sent": notification_sent,
        "notes": body.notes,
        "message": "Document re-requested successfully"
    }


@router.get("/documents/{loan_id}")
async def get_loan_documents(
    loan_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get all documents for a loan."""
    _verify_loan_tenant(db, loan_id, current_user)
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


# Alias route for backward compatibility
@router.get("/loan/{loan_id}/documents")
async def get_loan_documents_alias(
    loan_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Alias for /documents/{loan_id} - backward compatibility."""
    return await get_loan_documents(loan_id, status, db, current_user)


# =============================================================================
# Freshness & Expiration
# =============================================================================

@router.get("/expiring")
async def get_expiring_documents(
    loan_id: Optional[int] = None,
    days_ahead: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get documents expiring within the specified window."""
    if loan_id:
        _verify_loan_tenant(db, loan_id, current_user)
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
    current_user = Depends(get_current_user),
):
    """Update payroll frequency for a loan's paystub requests."""
    _verify_loan_tenant(db, loan_id, current_user)
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
    current_user = Depends(get_current_user),
):
    """Get document policy events for a loan."""
    _verify_loan_tenant(db, loan_id, current_user)
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
    # Default empty response
    default_response = {
        "total": 0,
        "page": page,
        "limit": limit,
        "total_pages": 0,
        "applicants": [],
    }

    try:
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
                        "file_name": doc.original_filename or doc.file_name,
                        "doc_type": doc.doc_type.value if doc.doc_type else None,
                        "uploaded_at": (doc.uploaded_at or doc.created_at).isoformat() if (doc.uploaded_at or doc.created_at) else None,
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
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching pending review applicants: {e}")
        return default_response


@router.get("/applicants/outstanding-docs")
async def get_applicants_with_outstanding_docs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    include_overdue_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get all applicants/loans that have outstanding document requests (needs list items not fulfilled).
    Returns grouped by loan with summary of outstanding requirements.
    """
    from sqlalchemy import func, distinct, case
    from models.purl import PURLLoan, PURLWorkspace
    from models.loan import Loan

    # Tenant isolation
    org_id = getattr(current_user, 'organization_id', None)
    is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'

    # Build filter for outstanding requests
    outstanding_filter = [DocumentRequest.status == RequestStatus.OPEN]

    # Add tenant isolation - filter by loans that belong to user's organization
    if not is_platform_admin and org_id:
        # Subquery to get loan_ids that belong to user's organization
        org_loan_ids = db.query(Loan.id).filter(Loan.organization_id == org_id).subquery()
        outstanding_filter.append(DocumentRequest.loan_id.in_(org_loan_ids))

    if include_overdue_only:
        outstanding_filter.append(DocumentRequest.due_date < func.now())

    # Get loans with outstanding requests
    # Use case() for conditional counting since func.count().filter() isn't valid
    overdue_case = case(
        (DocumentRequest.due_date < func.now(), 1),
        else_=0
    )

    outstanding_query = db.query(
        DocumentRequest.loan_id,
        func.count(DocumentRequest.id).label('outstanding_count'),
        func.sum(overdue_case).label('overdue_count'),
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
        func.sum(overdue_case).desc(),
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

        # Count received documents (any status other than OPEN)
        received_count = db.query(func.count(DocumentRequest.id)).filter(
            DocumentRequest.loan_id == loan_id,
            DocumentRequest.status != RequestStatus.OPEN
        ).scalar() or 0

        applicants.append({
            "loan_id": loan_id,
            "loan_number": loan_number,
            "borrower_name": borrower_name,
            "loan_purpose": loan_purpose,
            "outstanding_count": outstanding_count,
            "received_count": received_count,
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
        DocumentRequest.due_date < func.now()
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
        # Build WHERE clause for active loans (exclude funded)
        # LoanStage enum VALUES (stored in DB): Disclosed, Processing, Submitted, UW Received, Approved, Suspended, CTC, Docs Out, Funded
        where_clauses = ["stage != 'Funded'"]
        params = {"skip": skip, "limit": limit}

        # Filter by specific stage if provided
        if stage:
            where_clauses = ["stage = :stage"]
            params["stage"] = stage

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
            LIMIT :limit OFFSET :skip
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
    except SQLAlchemyError as e:
        logger.exception(f"Error fetching loans for Smart Docs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Queue View Endpoints
# =============================================================================

@router.get("/queue")
async def get_document_queue(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    sla_status: Optional[str] = Query(default=None, description="Filter by SLA status: GOOD, AT_RISK, BREACHED"),
    search: Optional[str] = Query(default=None, description="Search by borrower name or loan number"),
    db: Session = Depends(get_db),
):
    """
    Get the prioritized document queue.

    Returns client-centric view with:
    - completion_percentage (received_valid / requested)
    - sla_status (GOOD, AT_RISK, BREACHED)
    - has_sla_breach boolean
    - last_activity timestamp

    Sorted by: SLA breaches first, then lowest completion, then most recent activity
    """
    from services.smart_docs.queue_service import QueueService

    queue_service = QueueService(db)
    return queue_service.get_queue(
        page=page,
        limit=limit,
        filter_sla_status=sla_status,
        search_query=search,
    )


@router.get("/queue/summary")
async def get_queue_summary(
    db: Session = Depends(get_db),
):
    """Get summary statistics for the document queue."""
    try:
        from services.smart_docs.queue_service import QueueService

        queue_service = QueueService(db)
        return queue_service.get_queue_summary()
    except Exception as e:
        logger.error(f"Queue summary error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Queue service error")


@router.get("/queue/{loan_id}")
async def get_client_queue_detail(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get detailed queue information for a specific client."""
    _verify_loan_tenant(db, loan_id, current_user)
    from services.smart_docs.queue_service import QueueService

    queue_service = QueueService(db)
    result = queue_service.get_client_queue_detail(loan_id)

    if not result:
        raise HTTPException(status_code=404, detail="Client not found in queue")

    # Enrich each request with uploaded document info
    for req in result.get("requests", []):
        request_id = req.get("id")
        if request_id:
            # Get uploaded documents for this request (exclude deleted/superseded)
            uploaded_docs = db.query(SmartDocument).filter(
                SmartDocument.request_id == request_id,
                SmartDocument.status.notin_(["DELETED", "SUPERSEDED"])
            ).order_by(SmartDocument.created_at.desc()).all()

            if uploaded_docs:
                latest_doc = uploaded_docs[0]
                req["filename"] = latest_doc.file_name
                req["uploaded_at"] = latest_doc.created_at.isoformat() if latest_doc.created_at else None

                # Generate presigned URL for viewing - verify file exists first
                if latest_doc.storage_key:
                    s3_service = get_smart_docs_s3_service()
                    if s3_service.is_available:
                        # Check if file actually exists in S3 before generating URL
                        if s3_service.file_exists(latest_doc.storage_key):
                            url_result = s3_service.get_presigned_download_url(
                                storage_key=latest_doc.storage_key,
                                file_name=latest_doc.file_name,
                                expires_in=3600,  # 1 hour
                                inline=True,  # Use inline disposition for iframe viewing
                                organization_id=org_id  # Pass org_id for tenant validation
                            )
                            if url_result.get("success"):
                                req["file_url"] = url_result["presigned_url"]
                                req["s3_url"] = url_result["presigned_url"]
                        else:
                            # File doesn't exist in S3 - mark as storage error
                            req["storage_error"] = True
                            req["storage_error_message"] = "Document file not found in storage. Please re-upload."
                            logger.warning(f"S3 file not found for document {latest_doc.id}: {latest_doc.storage_key}")

                req["document_id"] = latest_doc.id
                req["doc_date"] = latest_doc.doc_date.isoformat() if latest_doc.doc_date else None
                req["expiration_date"] = latest_doc.doc_expires_at.isoformat() if latest_doc.doc_expires_at else None

    # Also add all_requests for frontend compatibility
    result["all_requests"] = result.get("requests", [])

    return result


# =============================================================================
# Client Reminder Settings Endpoints
# =============================================================================

class ReminderSettingsBody(BaseModel):
    """Request body for updating reminder settings."""
    reminders_enabled: bool = True
    reminder_frequency_hours: int = 72


@router.get("/reminders/{loan_id}")
async def get_reminder_settings(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get reminder settings for a loan."""
    _verify_loan_tenant(db, loan_id, current_user)
    from models.smart_docs_models import ClientReminderSettings

    settings = db.query(ClientReminderSettings).filter(
        ClientReminderSettings.loan_id == loan_id
    ).first()

    if not settings:
        # Return defaults if no settings exist
        return {
            "loan_id": loan_id,
            "reminders_enabled": True,
            "reminder_frequency_hours": 72,
            "last_reminder_sent_at": None,
            "reminder_count": 0,
        }

    return {
        "loan_id": settings.loan_id,
        "reminders_enabled": settings.reminders_enabled,
        "reminder_frequency_hours": settings.reminder_frequency_hours,
        "last_reminder_sent_at": settings.last_reminder_sent_at.isoformat() if settings.last_reminder_sent_at else None,
        "reminder_count": settings.reminder_count,
    }


@router.put("/reminders/{loan_id}")
async def update_reminder_settings(
    loan_id: int,
    body: ReminderSettingsBody,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update reminder settings for a loan."""
    _verify_loan_tenant(db, loan_id, current_user)
    from models.smart_docs_models import ClientReminderSettings

    settings = db.query(ClientReminderSettings).filter(
        ClientReminderSettings.loan_id == loan_id
    ).first()

    if not settings:
        settings = ClientReminderSettings(
            loan_id=loan_id,
            reminders_enabled=body.reminders_enabled,
            reminder_frequency_hours=body.reminder_frequency_hours,
        )
        db.add(settings)
    else:
        settings.reminders_enabled = body.reminders_enabled
        settings.reminder_frequency_hours = body.reminder_frequency_hours
        settings.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(settings)

    return {
        "loan_id": settings.loan_id,
        "reminders_enabled": settings.reminders_enabled,
        "reminder_frequency_hours": settings.reminder_frequency_hours,
        "updated": True,
    }


@router.post("/reminders/{loan_id}/send")
async def send_reminder(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Manually trigger a reminder for a loan.

    Updates last_reminder_sent_at and increments reminder_count.
    """
    _verify_loan_tenant(db, loan_id, current_user)
    from models.smart_docs_models import ClientReminderSettings
    from services.smart_docs.notification_service import SmartDocsNotificationService

    # Get pending requests
    pending_requests = db.query(DocumentRequest).filter(
        DocumentRequest.loan_id == loan_id,
        DocumentRequest.is_active == True,
        DocumentRequest.status == RequestStatus.OPEN
    ).all()

    if not pending_requests:
        return {"sent": False, "message": "No pending document requests"}

    # Get or create reminder settings
    settings = db.query(ClientReminderSettings).filter(
        ClientReminderSettings.loan_id == loan_id
    ).first()

    if not settings:
        settings = ClientReminderSettings(loan_id=loan_id)
        db.add(settings)

    # Get borrower info from loan
    from sqlalchemy import text
    loan_info = db.execute(text("""
        SELECT borrower_name, borrower_email FROM loans WHERE id = :loan_id
    """), {"loan_id": loan_id}).fetchone()

    if not loan_info or not loan_info.borrower_email:
        return {"sent": False, "message": "Borrower email not found"}

    # Try to send reminder
    sent = False
    try:
        notification_service = SmartDocsNotificationService(db)
        sent = notification_service.send_bulk_request_notification(
            requests=pending_requests,
            borrower_email=loan_info.borrower_email,
            borrower_name=loan_info.borrower_name or "Borrower",
        )
    except Exception as e:
        logger.warning(f"Failed to send reminder notification: {e}")
        # Still update tracking even if notification fails
        sent = True  # Mark as sent for tracking purposes

    if sent:
        settings.last_reminder_sent_at = datetime.utcnow()
        settings.reminder_count = (settings.reminder_count or 0) + 1
        db.commit()

    return {
        "sent": sent,
        "documents_reminded": len(pending_requests),
        "reminder_count": settings.reminder_count,
    }


# =============================================================================
# Document Extraction & Review Endpoints
# =============================================================================

class ApplyFieldRequest(BaseModel):
    """Single field to apply."""
    field_name: str
    action: str  # "add", "replace", "ignore"
    value: Optional[str] = None


class ApplyFieldsBody(BaseModel):
    """Request to apply extracted fields to Lead/Loan."""
    profile_type: str  # "lead" or "loan"
    profile_id: int
    fields_to_apply: List[ApplyFieldRequest]


class UpdateDocumentNameBody(BaseModel):
    """Request to update document name."""
    display_name: str


class ApproveDocumentBody(BaseModel):
    """Request to approve a document."""
    reviewer: str
    assigned_owner: Optional[str] = None  # "BORROWER", "CO_BORROWER"
    apply_fields: Optional[ApplyFieldsBody] = None
    notes: Optional[str] = None


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
    db.commit()
    db.refresh(extraction)

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
    _verify_document_tenant(db, document_id, current_user)
    from models.document_extraction import SmartDocumentExtraction, FIELD_TO_LEAD_MAPPING, FIELD_TO_LOAN_MAPPING, ReviewStatus
    from sqlalchemy import text

    # Get extraction
    extraction = db.query(SmartDocumentExtraction).filter(
        SmartDocumentExtraction.document_id == document_id
    ).first()

    if not extraction:
        raise HTTPException(status_code=404, detail="No extraction found")

    extracted_fields = extraction.extracted_fields or {}
    field_mapping = FIELD_TO_LEAD_MAPPING if body.profile_type == "lead" else FIELD_TO_LOAN_MAPPING

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

        value = field_req.value or extracted_fields.get(field_req.field_name)
        if value is None:
            skipped.append(field_req.field_name)
            continue

        # Update profile
        table = "leads" if body.profile_type == "lead" else "loans"
        try:
            db.execute(text(f"""
                UPDATE {table} SET {profile_field} = :value WHERE id = :id
            """), {"value": str(value), "id": body.profile_id})

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
    extraction.applied_at = datetime.utcnow()
    extraction.review_status = ReviewStatus.APPLIED

    db.commit()

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
    document.updated_at = datetime.utcnow()
    db.commit()

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
    document.reviewed_at = datetime.utcnow()
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
        extraction.reviewed_at = datetime.utcnow()

    # Apply fields if requested
    applied_result = None
    if body.apply_fields:
        # Commit current changes first
        db.commit()

        # Use the apply-fields endpoint logic
        from models.document_extraction import FIELD_TO_LEAD_MAPPING, FIELD_TO_LOAN_MAPPING
        from sqlalchemy import text

        extracted_fields = extraction.extracted_fields or {} if extraction else {}
        field_mapping = FIELD_TO_LEAD_MAPPING if body.apply_fields.profile_type == "lead" else FIELD_TO_LOAN_MAPPING

        applied = []
        for field_req in body.apply_fields.fields_to_apply:
            if field_req.action == "ignore":
                continue

            profile_field = field_mapping.get(field_req.field_name)
            if not profile_field:
                continue

            value = field_req.value or extracted_fields.get(field_req.field_name)
            if value is None:
                continue

            table = "leads" if body.apply_fields.profile_type == "lead" else "loans"
            try:
                db.execute(text(f"""
                    UPDATE {table} SET {profile_field} = :value WHERE id = :id
                """), {"value": str(value), "id": body.apply_fields.profile_id})
                applied.append(field_req.field_name)
            except SQLAlchemyError as e:
                logger.warning(f"Failed to apply field: {e}")

        if extraction:
            extraction.applied_fields = applied
            extraction.applied_to_profile_type = body.apply_fields.profile_type
            extraction.applied_to_profile_id = body.apply_fields.profile_id
            extraction.applied_at = datetime.utcnow()
            extraction.review_status = ReviewStatus.APPLIED

        applied_result = {"count": len(applied), "fields": applied}

    # Update request status if linked
    if document.request_id:
        request = db.query(DocumentRequest).filter(
            DocumentRequest.id == document.request_id
        ).first()
        if request:
            request.status = RequestStatus.ACCEPTED
            request.completed_at = datetime.utcnow()

    db.commit()

    return {
        "document_id": document_id,
        "status": "APPROVED",
        "reviewed_by": body.reviewer,
        "reviewed_at": datetime.utcnow().isoformat(),
        "assigned_owner": body.assigned_owner,
        "fields_applied": applied_result,
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


# =============================================================================
# Admin Endpoints
# =============================================================================

@router.get("/admin/s3-test")
async def s3_test(
    admin_key: str = Query(...),
):
    """Direct S3 test without any middleware."""
    import boto3
    import os
    from datetime import datetime

    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    results = {}

    try:
        # Create fresh S3 client
        s3 = boto3.client(
            's3',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        )
        results["client_created"] = "ok"

        bucket = os.getenv('SMART_DOCS_S3_BUCKET', 'perennia-smart-docs')
        test_key = f"test/s3_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        test_content = f"S3 test at {datetime.now().isoformat()}".encode('utf-8')

        # Test put_object
        s3.put_object(
            Bucket=bucket,
            Key=test_key,
            Body=test_content,
            ContentType='text/plain'
        )
        results["put_object"] = f"ok - uploaded to {test_key}"

        # Verify by listing
        response = s3.list_objects_v2(Bucket=bucket, Prefix='test/', MaxKeys=5)
        results["list_objects"] = f"ok - found {response.get('KeyCount', 0)} objects"

        # Clean up
        s3.delete_object(Bucket=bucket, Key=test_key)
        results["delete_object"] = "ok"

    except Exception as e:
        results["error"] = "Internal server error"

    return results


@router.get("/admin/upload-diagnostic")
async def upload_diagnostic(
    admin_key: str = Query(...),
    db: Session = Depends(get_db),
):
    """Diagnostic endpoint to test upload capabilities."""
    from sqlalchemy import text

    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    results = {
        "database": "unknown",
        "s3": "unknown",
        "smart_document_table": "unknown",
        "pipeline_import": "unknown",
    }

    # Test database connection
    try:
        db.execute(text("SELECT 1")).fetchone()
        results["database"] = "connected"
    except SQLAlchemyError as e:
        results["database"] = f"error: {str(e)}"

    # Test smart_documents table
    try:
        count = db.execute(text("SELECT COUNT(*) FROM smart_documents")).fetchone()[0]
        results["smart_document_table"] = f"ok ({count} documents)"
    except SQLAlchemyError as e:
        results["smart_document_table"] = f"error: {str(e)}"

    # Test S3 service
    try:
        s3_service = get_smart_docs_s3_service()
        results["s3"] = f"available: {s3_service.is_available}, bucket: {s3_service.bucket_name}"
    except SQLAlchemyError as e:
        results["s3"] = f"error: {str(e)}"

    # Test pipeline import
    try:
        pipeline = DocumentReviewPipeline(db)
        results["pipeline_import"] = "ok"
    except Exception as e:
        results["pipeline_import"] = f"error: {str(e)}"

    return results


@router.post("/admin/test-upload")
async def test_upload(
    file: UploadFile = File(...),
    loan_id: int = Form(146),
    borrower_id: int = Form(574),
    admin_key: str = Query(...),
    db: Session = Depends(get_db),
):
    """Test upload endpoint with detailed error logging."""
    from sqlalchemy import text

    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    steps = {}

    # Step 1: Read file
    try:
        file_content = await file.read()
        steps["read_file"] = f"ok ({len(file_content)} bytes)"
    except Exception as e:
        steps["read_file"] = f"error: {str(e)}"
        return {"steps": steps, "error": "Failed at read_file"}

    # Step 2: Get S3 service
    try:
        s3_service = get_smart_docs_s3_service()
        org_id = _get_loan_org_id(db, loan_id)
        storage_key = s3_service.generate_storage_key(
            loan_id=loan_id,
            borrower_id=borrower_id,
            file_name=file.filename,
            organization_id=org_id,
        )
        steps["s3_service"] = f"ok, key: {storage_key}"
    except Exception as e:
        steps["s3_service"] = f"error: {str(e)}"
        return {"steps": steps, "error": "Failed at s3_service"}

    # Step 3: Create document record
    try:
        document = SmartDocument(
            request_id=None,
            loan_id=loan_id,
            borrower_id=borrower_id,
            file_name=file.filename,
            mime_type=file.content_type or "application/octet-stream",
            file_size=len(file_content),
            storage_key=storage_key,
            doc_type=None,
            status="UPLOADED",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        steps["create_document"] = f"ok, id: {document.id}"
    except SQLAlchemyError as e:
        db.rollback()
        steps["create_document"] = f"error: {str(e)}"
        return {"steps": steps, "error": "Failed at create_document"}

    # Step 4: Upload to S3 using fresh boto3 client
    try:
        import boto3
        import os
        bucket = os.getenv('SMART_DOCS_S3_BUCKET', 'perennia-smart-docs')

        s3_client = boto3.client(
            's3',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        )
        steps["s3_client"] = "created fresh client"

        s3_client.put_object(
            Bucket=bucket,
            Key=storage_key,
            Body=file_content,
            ContentType=file.content_type or "application/octet-stream",
            Metadata={"loan_id": str(loan_id), "document_id": str(document.id)}
        )
        steps["s3_upload"] = f"success - uploaded to {bucket}/{storage_key}"
    except Exception as e:
        steps["s3_upload"] = "error: upload failed"

    # Step 5: Process document
    try:
        pipeline = DocumentReviewPipeline(db)
        result = pipeline.process_document(
            document_id=document.id,
            file_content=file_content,
            mime_type=file.content_type or "application/octet-stream",
            filename=file.filename,
            doc_type=None,
            request_id=None,
        )
        steps["process_document"] = f"ok, status: {result.status.value}"
    except Exception as e:
        steps["process_document"] = f"error: {str(e)}"
        return {"steps": steps, "error": "Failed at process_document", "document_id": document.id}

    return {
        "steps": steps,
        "document_id": document.id,
        "status": "success"
    }


@router.post("/admin/create-test-loan")
async def create_test_loan(
    admin_key: str = Query(...),
    db: Session = Depends(get_db),
):
    """Create a test loan for Smart Docs testing."""
    from sqlalchemy import text

    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # Check if test loan already exists
    existing = db.execute(text(
        "SELECT id FROM loans WHERE borrower_name = 'Test Borrower - Smart Docs' LIMIT 1"
    )).fetchone()

    if existing:
        return {
            "status": "exists",
            "loan_id": existing[0],
            "message": "Test loan already exists",
            "url": f"https://www.perenniaai.com/loans/{existing[0]}",
        }

    # Get a user to assign the loan to
    user = db.execute(text("SELECT id, email FROM users LIMIT 1")).fetchone()
    user_id = user[0] if user else None

    # Create test loan
    result = db.execute(text("""
        INSERT INTO loans (
            borrower_name, loan_amount, property_address,
            loan_type, status, transaction_type,
            loan_officer_id, created_at, updated_at
        ) VALUES (
            'Test Borrower - Smart Docs', 350000, '123 Test Street, Austin TX 78701',
            'Conventional', 'In Processing', 'Purchase',
            :user_id, NOW(), NOW()
        ) RETURNING id
    """), {"user_id": user_id})

    loan_id = result.fetchone()[0]
    db.commit()

    return {
        "status": "created",
        "loan_id": loan_id,
        "message": "Test loan created successfully",
        "url": f"https://www.perenniaai.com/loans/{loan_id}",
    }


@router.get("/diagnostic/storage-health")
async def check_storage_health():
    """Check S3 storage health and configuration."""
    s3_service = get_smart_docs_s3_service()

    return {
        "s3_available": s3_service.is_available,
        "bucket_name": s3_service.bucket_name,
        "region": s3_service.region,
        "prefix": s3_service.prefix,
    }


@router.get("/diagnostic/loan/{loan_id}/documents")
async def check_loan_documents_storage(
    loan_id: int,
    db: Session = Depends(get_db),
):
    """
    Check storage status for all documents in a loan.
    Returns which documents have valid S3 files and which are missing.
    """
    s3_service = get_smart_docs_s3_service()

    documents = db.query(SmartDocument).filter(
        SmartDocument.loan_id == loan_id
    ).all()

    results = []
    missing_count = 0
    valid_count = 0

    for doc in documents:
        doc_info = {
            "id": doc.id,
            "file_name": doc.file_name,
            "doc_type": doc.doc_type.value if doc.doc_type else None,
            "status": doc.status,
            "storage_key": doc.storage_key,
            "file_size": doc.file_size,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }

        if doc.storage_key and s3_service.is_available:
            exists = s3_service.file_exists(doc.storage_key)
            doc_info["s3_exists"] = exists
            if exists:
                valid_count += 1
            else:
                missing_count += 1
                doc_info["error"] = "File not found in S3"
        else:
            doc_info["s3_exists"] = False
            doc_info["error"] = "No storage key or S3 not available"
            missing_count += 1

        results.append(doc_info)

    return {
        "loan_id": loan_id,
        "total_documents": len(documents),
        "valid_files": valid_count,
        "missing_files": missing_count,
        "s3_available": s3_service.is_available,
        "documents": results,
    }


@router.post("/diagnostic/loan/{loan_id}/cleanup-orphans")
async def cleanup_orphan_documents(
    loan_id: int,
    db: Session = Depends(get_db),
):
    """
    Clean up orphan documents (those with missing S3 files).

    For each orphan document:
    - Marks the document as DELETED
    - Resets the linked request to OPEN so borrower can re-upload

    Returns summary of cleaned up documents.
    """
    s3_service = get_smart_docs_s3_service()

    documents = db.query(SmartDocument).filter(
        SmartDocument.loan_id == loan_id,
        SmartDocument.status.notin_(["DELETED", "SUPERSEDED"])
    ).all()

    cleaned = []
    skipped = []

    for doc in documents:
        # Check if file exists in S3
        if doc.storage_key and s3_service.is_available:
            exists = s3_service.file_exists(doc.storage_key)
            if exists:
                skipped.append({
                    "id": doc.id,
                    "file_name": doc.file_name,
                    "reason": "File exists in S3"
                })
                continue

        # File doesn't exist - mark as deleted
        old_status = doc.status
        doc.status = "DELETED"
        doc.rejection_reason = "File not found in storage - cleaned up"
        doc.reviewed_at = datetime.utcnow()
        doc.reviewed_by = "SYSTEM_CLEANUP"

        # Reset linked request to OPEN (always, since document is being deleted)
        if doc.request_id:
            request = db.query(DocumentRequest).filter(
                DocumentRequest.id == doc.request_id
            ).first()
            if request:
                request.status = RequestStatus.OPEN

        cleaned.append({
            "id": doc.id,
            "file_name": doc.file_name,
            "doc_type": doc.doc_type.value if doc.doc_type else None,
            "previous_status": old_status,
            "request_id": doc.request_id,
        })

    db.commit()

    logger.info(f"Cleaned up {len(cleaned)} orphan documents for loan {loan_id}")

    return {
        "loan_id": loan_id,
        "cleaned_count": len(cleaned),
        "skipped_count": len(skipped),
        "cleaned_documents": cleaned,
        "skipped_documents": skipped,
        "message": f"Cleaned up {len(cleaned)} orphan documents"
    }


@router.get("/diagnostic/all-storage-errors")
async def check_all_storage_errors(
    db: Session = Depends(get_db),
):
    """
    Scan all documents across all loans for storage errors.
    Returns summary by loan and list of missing files.
    """
    from sqlalchemy import func

    s3_service = get_smart_docs_s3_service()

    # Get all non-deleted documents grouped by loan
    documents = db.query(SmartDocument).filter(
        SmartDocument.status.notin_(["DELETED", "SUPERSEDED"])
    ).order_by(SmartDocument.loan_id, SmartDocument.id).all()

    by_loan = {}
    total_missing = 0
    total_valid = 0
    missing_docs = []

    for doc in documents:
        loan_id = doc.loan_id or 0

        if loan_id not in by_loan:
            by_loan[loan_id] = {"total": 0, "missing": 0, "valid": 0}

        by_loan[loan_id]["total"] += 1

        # Check S3
        if doc.storage_key and s3_service.is_available:
            exists = s3_service.file_exists(doc.storage_key)
            if exists:
                by_loan[loan_id]["valid"] += 1
                total_valid += 1
            else:
                by_loan[loan_id]["missing"] += 1
                total_missing += 1
                missing_docs.append({
                    "document_id": doc.id,
                    "loan_id": loan_id,
                    "file_name": doc.file_name,
                    "doc_type": doc.doc_type.value if doc.doc_type else None,
                    "status": doc.status,
                    "storage_key": doc.storage_key,
                })
        else:
            by_loan[loan_id]["missing"] += 1
            total_missing += 1
            missing_docs.append({
                "document_id": doc.id,
                "loan_id": loan_id,
                "file_name": doc.file_name,
                "doc_type": doc.doc_type.value if doc.doc_type else None,
                "status": doc.status,
                "storage_key": doc.storage_key,
                "error": "No storage key" if not doc.storage_key else "S3 not available",
            })

    # Filter to only loans with missing files
    loans_with_errors = {k: v for k, v in by_loan.items() if v["missing"] > 0}

    return {
        "total_documents": len(documents),
        "total_valid": total_valid,
        "total_missing": total_missing,
        "loans_with_errors": len(loans_with_errors),
        "by_loan": loans_with_errors,
        "missing_documents": missing_docs,
    }


@router.post("/diagnostic/cleanup-all-orphans")
async def cleanup_all_orphan_documents(
    db: Session = Depends(get_db),
):
    """
    Clean up all orphan documents across all loans.
    """
    s3_service = get_smart_docs_s3_service()

    documents = db.query(SmartDocument).filter(
        SmartDocument.status.notin_(["DELETED", "SUPERSEDED"])
    ).all()

    cleaned = []
    skipped = 0

    for doc in documents:
        # Check if file exists in S3
        if doc.storage_key and s3_service.is_available:
            exists = s3_service.file_exists(doc.storage_key)
            if exists:
                skipped += 1
                continue

        # File doesn't exist - mark as deleted
        old_status = doc.status
        doc.status = "DELETED"
        doc.rejection_reason = "File not found in storage - cleaned up"
        doc.reviewed_at = datetime.utcnow()
        doc.reviewed_by = "SYSTEM_CLEANUP"

        # Reset linked request to OPEN
        if doc.request_id:
            request = db.query(DocumentRequest).filter(
                DocumentRequest.id == doc.request_id
            ).first()
            if request:
                request.status = RequestStatus.OPEN

        cleaned.append({
            "id": doc.id,
            "loan_id": doc.loan_id,
            "file_name": doc.file_name,
            "doc_type": doc.doc_type.value if doc.doc_type else None,
            "previous_status": old_status,
        })

    db.commit()

    logger.info(f"Cleaned up {len(cleaned)} orphan documents across all loans")

    return {
        "cleaned_count": len(cleaned),
        "skipped_count": skipped,
        "cleaned_documents": cleaned,
        "message": f"Cleaned up {len(cleaned)} orphan documents"
    }


# =============================================================================
# Portal DocuSign Integration Endpoints
# =============================================================================

class SendToPortalForSignatureBody(BaseModel):
    """Request to send a document request to the portal for DocuSign."""
    request_id: Optional[int] = None
    doc_type: Optional[str] = None
    title: str
    type: str  # 'signature' or 'loe' (letter of explanation)
    loe_subject: Optional[str] = None
    loe_instructions: Optional[str] = None


@router.post("/portal/send-for-signature/{loan_id}")
async def send_to_portal_for_signature(
    loan_id: int,
    body: SendToPortalForSignatureBody,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Send a document request to the client portal for DocuSign or Letter of Explanation.

    This endpoint:
    1. Creates or updates a document request linked to the portal
    2. Marks it for DocuSign signature or LOE completion
    3. Ensures the document will appear in the client portal

    The client will be able to:
    - For 'signature' type: Sign a document via DocuSign
    - For 'loe' type: Write and sign a letter of explanation
    """
    from sqlalchemy import text
    from models.purl import PURLLoan, PURLWorkspace

    _verify_loan_tenant(db, loan_id, current_user)
    logger.info(f"Sending document request to portal for loan {loan_id}: {body.title}, type={body.type}")

    # Find the PURL loan record that links to this loan
    purl_loan = db.query(PURLLoan).filter(
        PURLLoan.main_loan_id == loan_id
    ).first()

    # If no PURL loan with main_loan_id, try to find by id
    if not purl_loan:
        purl_loan = db.query(PURLLoan).filter(
            PURLLoan.id == loan_id
        ).first()

    if not purl_loan:
        logger.warning(f"No PURL loan found for loan_id {loan_id}")
        # Still create the request - it may be linked later
        workspace_id = None
    else:
        workspace_id = purl_loan.workspace_id
        # Ensure main_loan_id is set correctly
        if not purl_loan.main_loan_id:
            purl_loan.main_loan_id = loan_id
            db.commit()
            logger.info(f"Updated PURLLoan.main_loan_id to {loan_id}")

    # Use the correct loan_id for Smart Docs (this should be the main loans table id)
    smart_docs_loan_id = purl_loan.main_loan_id if purl_loan and purl_loan.main_loan_id else loan_id

    # Map doc_type string to DocType enum
    doc_type_enum = None
    if body.doc_type:
        try:
            doc_type_enum = DocType(body.doc_type.upper())
        except (ValueError, KeyError):
            # Try to find by name
            for dt in DocType:
                if dt.name == body.doc_type.upper() or dt.value == body.doc_type.upper():
                    doc_type_enum = dt
                    break
            if not doc_type_enum:
                doc_type_enum = DocType.OTHER

    # Determine title and description based on type
    if body.type == 'loe':
        title = body.loe_subject or body.title or "Letter of Explanation"
        description = body.loe_instructions or "Please write a letter explaining the situation and sign it."
        instructions = f"Please write a letter of explanation regarding: {body.loe_subject or 'the requested topic'}.\n\n{body.loe_instructions or ''}"
        doc_type_enum = DocType.LOE if hasattr(DocType, 'LOE') else DocType.OTHER
    else:
        title = body.title
        description = f"Document requires signature via DocuSign"
        instructions = "Please review and sign this document electronically."

    # Create or update the document request
    if body.request_id:
        # Update existing request
        request = db.query(DocumentRequest).filter(
            DocumentRequest.id == body.request_id
        ).first()

        if request:
            request.status = RequestStatus.OPEN
            request.is_active = True
            if not request.metadata:
                request.metadata = {}
            request.metadata['portal_docusign'] = {
                'type': body.type,
                'loe_subject': body.loe_subject,
                'loe_instructions': body.loe_instructions,
                'sent_at': datetime.utcnow().isoformat(),
            }
            db.commit()
            logger.info(f"Updated existing request {request.id} for portal DocuSign")
        else:
            raise HTTPException(status_code=404, detail=f"Request {body.request_id} not found")
    else:
        # Create new document request
        request = DocumentRequest(
            loan_id=smart_docs_loan_id,
            doc_type=doc_type_enum,
            title=title,
            description=description,
            instructions=instructions,
            priority=RequestPriority.HIGH,
            status=RequestStatus.OPEN,
            is_active=True,
        )
        db.add(request)
        db.commit()
        db.refresh(request)
        logger.info(f"Created new request {request.id} for portal DocuSign, loan_id={smart_docs_loan_id}")

    # Log event
    event = DocPolicyEvent(
        event_type="PORTAL_DOCUSIGN_REQUEST",
        loan_id=smart_docs_loan_id,
        request_id=request.id,
        message=f"Document request sent to portal for {body.type}: {title}",
        data={
            "type": body.type,
            "title": title,
            "loe_subject": body.loe_subject,
            "workspace_id": workspace_id,
        }
    )
    db.add(event)
    db.commit()

    return {
        "success": True,
        "request_id": request.id,
        "loan_id": smart_docs_loan_id,
        "workspace_id": workspace_id,
        "type": body.type,
        "title": title,
        "message": f"Document request sent to client portal for {body.type}"
    }


# =============================================================================
# Loan ID Mismatch Analysis & Fix Endpoints
# =============================================================================

@router.get("/portal/loan-id-mismatches")
async def analyze_loan_id_mismatches(
    db: Session = Depends(get_db),
):
    """
    Analyze loan ID mismatches between Smart Docs and PURL system.

    This helps identify document requests that won't show in the client portal
    because of incorrect loan_id linkage.
    """
    from sqlalchemy import text
    from models.purl import PURLLoan, PURLWorkspace

    mismatches = []
    fixable = []
    orphaned_requests = []

    # Get all active document requests
    requests = db.query(DocumentRequest).filter(
        DocumentRequest.is_active == True
    ).all()

    # Get all PURL loans
    purl_loans = db.query(PURLLoan).all()

    # Build lookup maps
    purl_by_main_loan_id = {pl.main_loan_id: pl for pl in purl_loans if pl.main_loan_id}
    purl_by_id = {pl.id: pl for pl in purl_loans}

    # Check each document request
    for req in requests:
        loan_id = req.loan_id

        # Check if this loan_id is a main_loan_id in PURL
        purl_loan = purl_by_main_loan_id.get(loan_id)

        if purl_loan:
            # This is correct - loan_id matches a PURL main_loan_id
            continue

        # Check if this loan_id is a PURL loan id (without main_loan_id set)
        purl_loan = purl_by_id.get(loan_id)

        if purl_loan:
            if not purl_loan.main_loan_id:
                # PURL loan exists but main_loan_id not set - fixable
                fixable.append({
                    "request_id": req.id,
                    "request_title": req.title,
                    "request_loan_id": loan_id,
                    "purl_loan_id": purl_loan.id,
                    "workspace_id": purl_loan.workspace_id,
                    "issue": "PURL loan exists but main_loan_id is not set",
                    "fix": f"Set PURLLoan.main_loan_id = {loan_id}",
                })
            else:
                # loan_id doesn't match main_loan_id - mismatch
                mismatches.append({
                    "request_id": req.id,
                    "request_title": req.title,
                    "request_loan_id": loan_id,
                    "purl_loan_id": purl_loan.id,
                    "purl_main_loan_id": purl_loan.main_loan_id,
                    "workspace_id": purl_loan.workspace_id,
                    "issue": "Document request loan_id doesn't match PURL main_loan_id",
                    "fix": f"Update DocumentRequest.loan_id from {loan_id} to {purl_loan.main_loan_id}",
                })
        else:
            # No PURL loan found at all - orphaned
            orphaned_requests.append({
                "request_id": req.id,
                "request_title": req.title,
                "request_loan_id": loan_id,
                "issue": "No PURL loan found for this loan_id",
                "fix": "Need to create PURL loan or link existing one",
            })

    # Also check for PURL loans that have requests with wrong loan_id
    for purl_loan in purl_loans:
        if purl_loan.main_loan_id and purl_loan.main_loan_id != purl_loan.id:
            # Check if there are requests using purl_loan.id instead of main_loan_id
            wrong_id_requests = [r for r in requests if r.loan_id == purl_loan.id]
            for req in wrong_id_requests:
                if req.id not in [m["request_id"] for m in mismatches]:
                    mismatches.append({
                        "request_id": req.id,
                        "request_title": req.title,
                        "request_loan_id": req.loan_id,
                        "purl_loan_id": purl_loan.id,
                        "purl_main_loan_id": purl_loan.main_loan_id,
                        "workspace_id": purl_loan.workspace_id,
                        "issue": "Request uses PURL loan ID instead of main_loan_id",
                        "fix": f"Update DocumentRequest.loan_id from {req.loan_id} to {purl_loan.main_loan_id}",
                    })

    return {
        "summary": {
            "total_requests": len(requests),
            "mismatches": len(mismatches),
            "fixable_purl_loans": len(fixable),
            "orphaned_requests": len(orphaned_requests),
            "correctly_linked": len(requests) - len(mismatches) - len(fixable) - len(orphaned_requests),
        },
        "mismatches": mismatches,
        "fixable_purl_loans": fixable,
        "orphaned_requests": orphaned_requests,
    }


@router.post("/portal/fix-loan-id-mismatches")
async def fix_loan_id_mismatches(
    dry_run: bool = Query(True, description="If true, only report what would be fixed without making changes"),
    db: Session = Depends(get_db),
):
    """
    Fix loan ID mismatches between Smart Docs and PURL system.

    This endpoint will:
    1. Set PURLLoan.main_loan_id where it's missing
    2. Update DocumentRequest.loan_id to match PURL main_loan_id

    Set dry_run=false to actually apply the fixes.
    """
    from models.purl import PURLLoan

    fixes_applied = []
    errors = []

    # Get all active document requests
    requests = db.query(DocumentRequest).filter(
        DocumentRequest.is_active == True
    ).all()

    # Get all PURL loans
    purl_loans = db.query(PURLLoan).all()

    # Build lookup maps
    purl_by_main_loan_id = {pl.main_loan_id: pl for pl in purl_loans if pl.main_loan_id}
    purl_by_id = {pl.id: pl for pl in purl_loans}

    # Fix 1: Set main_loan_id on PURL loans where it's missing
    for purl_loan in purl_loans:
        if not purl_loan.main_loan_id:
            # Check if there are document requests using this PURL loan id
            related_requests = [r for r in requests if r.loan_id == purl_loan.id]
            if related_requests:
                fix_info = {
                    "type": "set_purl_main_loan_id",
                    "purl_loan_id": purl_loan.id,
                    "workspace_id": purl_loan.workspace_id,
                    "new_main_loan_id": purl_loan.id,
                    "affected_requests": len(related_requests),
                }

                if not dry_run:
                    try:
                        purl_loan.main_loan_id = purl_loan.id
                        fix_info["status"] = "applied"
                    except Exception as e:
                        fix_info["status"] = "error"
                        fix_info["error"] = type(e).__name__
                        errors.append(fix_info)
                        continue
                else:
                    fix_info["status"] = "dry_run"

                fixes_applied.append(fix_info)

    # Fix 2: Update DocumentRequest.loan_id to match main_loan_id
    for req in requests:
        loan_id = req.loan_id

        # Skip if already correctly linked
        if loan_id in purl_by_main_loan_id:
            continue

        # Check if using PURL loan id instead of main_loan_id
        purl_loan = purl_by_id.get(loan_id)
        if purl_loan and purl_loan.main_loan_id and purl_loan.main_loan_id != loan_id:
            fix_info = {
                "type": "update_request_loan_id",
                "request_id": req.id,
                "request_title": req.title,
                "old_loan_id": loan_id,
                "new_loan_id": purl_loan.main_loan_id,
                "purl_loan_id": purl_loan.id,
            }

            if not dry_run:
                try:
                    req.loan_id = purl_loan.main_loan_id
                    fix_info["status"] = "applied"
                except Exception as e:
                    fix_info["status"] = "error"
                    fix_info["error"] = type(e).__name__
                    errors.append(fix_info)
                    continue
            else:
                fix_info["status"] = "dry_run"

            fixes_applied.append(fix_info)

    # Also fix SmartDocument records
    documents = db.query(SmartDocument).filter(
        SmartDocument.status.notin_(["DELETED", "SUPERSEDED"])
    ).all()

    for doc in documents:
        loan_id = doc.loan_id

        # Skip if already correctly linked
        if loan_id in purl_by_main_loan_id:
            continue

        # Check if using PURL loan id instead of main_loan_id
        purl_loan = purl_by_id.get(loan_id)
        if purl_loan and purl_loan.main_loan_id and purl_loan.main_loan_id != loan_id:
            fix_info = {
                "type": "update_document_loan_id",
                "document_id": doc.id,
                "file_name": doc.file_name,
                "old_loan_id": loan_id,
                "new_loan_id": purl_loan.main_loan_id,
            }

            if not dry_run:
                try:
                    doc.loan_id = purl_loan.main_loan_id
                    fix_info["status"] = "applied"
                except Exception as e:
                    fix_info["status"] = "error"
                    fix_info["error"] = type(e).__name__
                    errors.append(fix_info)
                    continue
            else:
                fix_info["status"] = "dry_run"

            fixes_applied.append(fix_info)

    # Commit changes if not dry run
    if not dry_run:
        try:
            db.commit()
            logger.info(f"Applied {len(fixes_applied)} loan ID fixes")
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Failed to commit loan ID fixes: {e}")
            return {
                "success": False,
                "error": "Internal server error",
                "fixes_attempted": len(fixes_applied),
            }

    return {
        "success": True,
        "dry_run": dry_run,
        "summary": {
            "total_fixes": len(fixes_applied),
            "purl_main_loan_id_fixes": len([f for f in fixes_applied if f["type"] == "set_purl_main_loan_id"]),
            "request_loan_id_fixes": len([f for f in fixes_applied if f["type"] == "update_request_loan_id"]),
            "document_loan_id_fixes": len([f for f in fixes_applied if f["type"] == "update_document_loan_id"]),
            "errors": len(errors),
        },
        "fixes": fixes_applied,
        "errors": errors,
        "message": "Dry run complete - set dry_run=false to apply fixes" if dry_run else f"Applied {len(fixes_applied)} fixes"
    }
