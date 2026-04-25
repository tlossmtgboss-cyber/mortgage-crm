"""
Smart Docs Requests Routes

Custom document requests, waive, type updates, portal DocuSign integration,
loan-ID mismatch analysis/fix, admin endpoints, and diagnostic endpoints.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from database import get_db
from auth.dependencies import get_current_user
from models.smart_docs_models import (
    DocumentRequest, SmartDocument, DocPolicyEvent, DocPolicyEventType,
    DocType, RequestStatus, RequestPriority,
)
from services.smart_docs.needs_list_generator import NeedsListGenerator
from services.smart_docs.document_review_pipeline import DocumentReviewPipeline
from services.smart_docs.notification_service import SmartDocsNotificationService
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

from routes.smart_docs_models import (
    AddCustomRequestBody,
    WaiveRequestBody,
    UpdateDocumentTypeBody,
    SendToPortalForSignatureBody,
    _get_loan_org_id,
    _verify_loan_tenant,
    _verify_request_tenant,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Smart Documents"],
)



# =============================================================================
# Custom Request & Waive
# =============================================================================

@router.post("/needs-list/{loan_id}/custom-request")
async def add_custom_request(
    loan_id: int,
    borrower_id: Optional[int] = Query(None),
    body: AddCustomRequestBody = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Add a custom document request to the needs list.

    Optionally sends an email notification to the borrower if send_notification
    is set to True and borrower_email is provided.
    """
    try:
        _verify_loan_tenant(db, loan_id, current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("custom-request: tenant verification failed for loan %s", loan_id)
        raise HTTPException(status_code=400, detail="Tenant verification failed")

    if not borrower_id:
        borrower_id = 0

    try:
        generator = NeedsListGenerator(db)
        result = generator.add_custom_request(
            loan_id=loan_id,
            borrower_id=borrower_id,
            title=body.title,
            description=body.description,
            instructions=body.instructions,
            priority=body.priority,
            due_date=body.due_date,
            doc_type=body.doc_type,
            requires_esign=body.requires_esign,
        )
    except Exception as e:
        db.rollback()
        logger.exception("custom-request: add_custom_request failed for loan %s", loan_id)
        raise HTTPException(status_code=500, detail="Failed to create custom document request")

    # Send notification if requested
    notification_sent = False
    if body.send_notification and body.borrower_email:
        try:
            from sqlalchemy import text as _text

            request = db.query(DocumentRequest).filter(
                DocumentRequest.loan_id == loan_id,
                DocumentRequest.title == body.title
            ).order_by(DocumentRequest.created_at.desc()).first()

            if request:
                lo_name = "Your Loan Officer"
                borrower_phone = None

                lo_row = db.execute(_text(
                    "SELECT u.first_name, u.last_name "
                    "FROM users u JOIN loans l ON l.loan_officer_id = u.id "
                    "WHERE l.id = :lid"
                ), {"lid": loan_id}).first()
                if lo_row:
                    lo_name = f"{lo_row[0] or ''} {lo_row[1] or ''}".strip() or "Your Loan Officer"

                phone_row = db.execute(_text(
                    "SELECT COALESCE(l2.borrower_phone, ld.phone) "
                    "FROM loans l2 "
                    "LEFT JOIN leads ld ON ld.id = l2.lead_id "
                    "WHERE l2.id = :lid"
                ), {"lid": loan_id}).first()
                if phone_row and phone_row[0]:
                    borrower_phone = phone_row[0]

                notification_service = SmartDocsNotificationService(db)
                notification_sent = notification_service.send_document_request_notification(
                    request=request,
                    borrower_email=body.borrower_email,
                    borrower_name=body.borrower_name or "Borrower",
                    loan_officer_name=lo_name,
                    borrower_phone=borrower_phone,
                    loan_id=loan_id,
                )
        except Exception as e:
            logger.error(f"Failed to send notification for custom request: {e}")

    if isinstance(result, dict):
        result["notification_sent"] = notification_sent
    return result


@router.delete("/needs-list/request/{request_id}")
async def delete_document_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Delete a document request and its associated documents."""
    _verify_request_tenant(db, request_id, current_user)

    request = db.query(DocumentRequest).filter(DocumentRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    linked_docs = db.query(SmartDocument).filter(
        SmartDocument.request_id == request_id
    ).all()
    for doc in linked_docs:
        doc.status = "DELETED"
        doc.request_id = None

    db.delete(request)
    db.commit()

    logger.info(f"Deleted document request {request_id} (loan {request.loan_id})")
    return {"success": True, "request_id": request_id, "documents_unlinked": len(linked_docs)}


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
# Document Type Update
# =============================================================================

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
    document.updated_at = datetime.now(timezone.utc)

    db.commit()

    logger.info(f"Document {document_id} type changed from {old_doc_type} to {new_doc_type}")

    return {
        "document_id": document_id,
        "doc_type": new_doc_type.value,
        "previous_type": old_doc_type.value if old_doc_type else None,
        "message": "Document type updated successfully"
    }


# =============================================================================
# Portal DocuSign Integration Endpoints
# =============================================================================

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
            if not request.request_metadata:
                request.request_metadata = {}
            request.request_metadata['portal_docusign'] = {
                'type': body.type,
                'loe_subject': body.loe_subject,
                'loe_instructions': body.loe_instructions,
                'sent_at': datetime.now(timezone.utc).isoformat(),
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
        event_type=DocPolicyEventType.PORTAL_DOCUSIGN_REQUEST,
        loan_id=smart_docs_loan_id,
        request_id=request.id,
        payload={
            "type": body.type,
            "title": title,
            "loe_subject": body.loe_subject,
            "workspace_id": workspace_id,
            "message": f"Document request sent to portal for {body.type}: {title}",
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
    current_user = Depends(get_current_user),
):
    """
    Analyze loan ID mismatches between Smart Docs and PURL system.

    This helps identify document requests that won't show in the client portal
    because of incorrect loan_id linkage.
    """
    if getattr(current_user, 'permission_role', '') not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

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
    current_user = Depends(get_current_user),
):
    """
    Fix loan ID mismatches between Smart Docs and PURL system.

    This endpoint will:
    1. Set PURLLoan.main_loan_id where it's missing
    2. Update DocumentRequest.loan_id to match PURL main_loan_id

    Set dry_run=false to actually apply the fixes.
    """
    if getattr(current_user, 'permission_role', '') not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

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


# =============================================================================
# Admin Endpoints
# =============================================================================

@router.get("/admin/s3-test")
async def s3_test(
    current_user = Depends(get_current_user),
):
    """Direct S3 test without any middleware."""
    import boto3
    import os
    from datetime import datetime

    if getattr(current_user, 'permission_role', '') not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Diagnostic endpoint to test upload capabilities."""
    from sqlalchemy import text

    if getattr(current_user, 'permission_role', '') not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

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
        logger.error(f"Upload diagnostic - database error: {e}")
        results["database"] = "error"

    # Test smart_documents table
    try:
        count = db.execute(text("SELECT COUNT(*) FROM smart_documents")).fetchone()[0]
        results["smart_document_table"] = f"ok ({count} documents)"
    except SQLAlchemyError as e:
        logger.error(f"Upload diagnostic - smart_documents table error: {e}")
        results["smart_document_table"] = "error"

    # Test S3 service
    try:
        s3_service = get_smart_docs_s3_service()
        results["s3"] = f"available: {s3_service.is_available}, bucket: {s3_service.bucket_name}"
    except Exception as e:
        logger.error(f"Upload diagnostic - S3 error: {e}")
        results["s3"] = "error"

    # Test pipeline import
    try:
        pipeline = DocumentReviewPipeline(db)
        results["pipeline_import"] = "ok"
    except Exception as e:
        logger.error(f"Upload diagnostic - pipeline import error: {e}")
        results["pipeline_import"] = "error"

    return results


@router.post("/admin/test-upload")
async def test_upload(
    file: UploadFile = File(...),
    loan_id: int = Form(146),
    borrower_id: int = Form(574),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Test upload endpoint with detailed error logging."""
    from sqlalchemy import text

    if getattr(current_user, 'permission_role', '') not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a test loan for Smart Docs testing."""
    from sqlalchemy import text

    if getattr(current_user, 'permission_role', '') not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

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


# =============================================================================
# Diagnostic Endpoints
# =============================================================================

@router.get("/diagnostic/storage-health")
async def check_storage_health(
    current_user = Depends(get_current_user),
):
    """Check S3 storage health and configuration."""
    if getattr(current_user, 'permission_role', '') not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

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
    current_user = Depends(get_current_user),
):
    """
    Check storage status for all documents in a loan.
    Returns which documents have valid S3 files and which are missing.
    """
    if getattr(current_user, 'permission_role', '') not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

    _verify_loan_tenant(db, loan_id, current_user)
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
    current_user = Depends(get_current_user),
):
    """
    Clean up orphan documents (those with missing S3 files).

    For each orphan document:
    - Marks the document as DELETED
    - Resets the linked request to OPEN so borrower can re-upload

    Returns summary of cleaned up documents.
    """
    if getattr(current_user, 'permission_role', '') not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

    _verify_loan_tenant(db, loan_id, current_user)
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
        doc.reviewed_at = datetime.now(timezone.utc)
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
    current_user = Depends(get_current_user),
):
    """
    Scan all documents across all loans for storage errors.
    Returns summary by loan and list of missing files.
    """
    if getattr(current_user, 'permission_role', '') not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

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
    current_user = Depends(get_current_user),
):
    """
    Clean up all orphan documents across all loans.
    """
    if getattr(current_user, 'permission_role', '') not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

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
        doc.reviewed_at = datetime.now(timezone.utc)
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
