"""
Smart Docs CRUD Routes

Needs list management, document upload/download, merge, loan listing,
templates, events, freshness/expiration, payroll, queue, dashboard,
reminders, and health endpoints.
"""

import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from database import get_db
from auth.dependencies import get_current_user
from models.smart_docs_models import (
    DocumentRequest, SmartDocument, DocPolicyEvent, NeedsListTemplate,
    DocType, RequestStatus, RequestPriority, AppliesTo, PayrollFrequency,
)
from services.smart_docs.needs_list_generator import NeedsListGenerator
from services.smart_docs.document_review_pipeline import DocumentReviewPipeline
from services.smart_docs.auto_renewal_scheduler import AutoRenewalScheduler
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

from routes.smart_docs_models import (
    GenerateNeedsListRequest,
    SyncApplicationDocumentsRequest,
    UpdatePayrollFrequencyBody,
    MergeDocumentsRequest,
    ReminderSettingsBody,
    DOCUMENT_ID_TO_DOC_TYPE,
    FRESHNESS_DAYS,
    _get_loan_org_id,
    _verify_loan_tenant,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Smart Documents"],
)


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
                except Exception as e:
                    logger.error(f"Error fetching lead name for loan {loan_id}: {e}")

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

    # Get org_id for S3 presigned URLs
    org_id = getattr(current_user, 'organization_id', None)

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
