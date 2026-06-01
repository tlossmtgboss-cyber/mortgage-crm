"""POS document upload endpoint.

Allows borrowers to upload supporting documents (pay stubs, W-2s, tax returns,
bank statements, photo ID) directly from the POS application form.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from database import get_db
from middleware.purl_auth import PURLAuthContext, check_purl_rate_limit, require_purl_write_scope
from database.models.pos import POSApplication
from ._helpers import resolve_application_for_borrower_write, build_audit_context
from services.pos.application_service import AuditContext

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/pos/applications",
    tags=["pos-upload"],
    # Per-token rate limit, matching every other POS router (documents, tasks,
    # application, etc.). Uploads are the most resource-intensive POS endpoint,
    # so this was the most important one to gate — it was the only POS router
    # missing it.
    dependencies=[Depends(check_purl_rate_limit)],
)

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/heic",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
VALID_CATEGORIES = {"paystubs", "w2s", "tax_returns", "bank_statements", "id", "other"}


@router.post(
    "/{application_id}/documents/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a supporting document for a POS application",
)
async def upload_pos_document(
    application_id: UUID,
    file: UploadFile = File(...),
    category: str = Form("other"),
    application: POSApplication = Depends(resolve_application_for_borrower_write),
    purl_ctx: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db),
    ctx: AuditContext = Depends(build_audit_context),
):
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid document category")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="File type not allowed")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    # Store via S3 if available, otherwise store metadata only
    s3_key = None
    try:
        import boto3
        s3_bucket = os.getenv("S3_DOCUMENT_BUCKET")
        if s3_bucket:
            s3 = boto3.client("s3")
            org_id = application.organization_id
            app_id = str(application.id)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            safe_filename = "".join(c if c.isalnum() or c in ".-_" else "_" for c in file.filename)
            s3_key = f"pos/{org_id}/{app_id}/{category}/{timestamp}_{safe_filename}"
            s3.put_object(
                Bucket=s3_bucket,
                Key=s3_key,
                Body=content,
                ContentType=mime_type,
                ServerSideEncryption="AES256",
                Metadata={
                    "organization_id": str(org_id),
                    "application_id": app_id,
                    "contact_id": str(purl_ctx.contact_id),
                    "category": category,
                },
            )
    except Exception as e:
        logger.exception("S3 upload failed for app %s: %s", application.id, e)
        # Fall through — we still record the metadata

    # Try to create a SmartDocument record if the model is available
    doc_id = None
    try:
        from models.smart_docs_models import SmartDocument
        doc = SmartDocument(
            organization_id=application.organization_id,
            loan_id=application.loan_id,
            borrower_id=purl_ctx.contact_id or 0,
            file_name=file.filename,
            original_filename=file.filename,
            mime_type=mime_type,
            file_size=len(content),
            storage_key=s3_key or "",
            doc_type=category,
            status="UPLOADED",
            upload_source="POS",
            uploaded_at=datetime.now(timezone.utc),
        )
        db.add(doc)
        db.flush()
        doc_id = doc.id
    except Exception as e:
        logger.warning("SmartDocument creation failed (table may not exist): %s", e)
        try:
            db.rollback()
        except Exception:
            pass

    db.commit()

    logger.info(
        "POS document uploaded: app=%s category=%s filename=%s size=%d",
        application.id, category, file.filename, len(content),
    )

    return {
        "status": "uploaded",
        "document_id": doc_id,
        "filename": file.filename,
        "category": category,
        "size": len(content),
        "s3_key": s3_key,
    }
