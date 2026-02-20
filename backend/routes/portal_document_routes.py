"""
Portal Document Routes
Perennia AI - Mortgage CRM

Document upload and management endpoints for the borrower portal.
Handles presigned URL generation, upload confirmation, and processing triggers.
"""

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Path, BackgroundTasks, UploadFile, File, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/portal/documents", tags=["Portal Documents"])


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

_get_db = None
_s3_client = None


def set_dependencies(get_db_func, s3_client=None):
    """Set dependencies from main.py."""
    global _get_db, _s3_client
    _get_db = get_db_func
    _s3_client = s3_client
    logger.info("Portal Document routes dependencies set")


def get_db():
    """Get database session."""
    if _get_db is None:
        raise RuntimeError("Portal Document routes not initialized")
    yield from _get_db()


def get_s3_client():
    """Get S3 client (lazy initialization)."""
    global _s3_client
    if _s3_client is None:
        try:
            import boto3
            _s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION', 'us-east-1')
            )
        except Exception as e:
            logger.warning(f"S3 client initialization failed: {e}")
            _s3_client = None
    return _s3_client


# =============================================================================
# CONFIGURATION
# =============================================================================

S3_BUCKET = os.getenv('PERENNIA_DOCS_S3_BUCKET', 'perennia-documents')
CLOUDFRONT_DOMAIN = os.getenv('PERENNIA_CLOUDFRONT_DOMAIN', '')
CLOUDFRONT_KEY_PAIR_ID = os.getenv('CLOUDFRONT_KEY_PAIR_ID', '')
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB

ALLOWED_MIME_TYPES = [
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/heic',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'doc', 'docx'}

# Map MIME types to their valid extensions for consistency check
_MIME_TO_EXTENSIONS = {
    'application/pdf': {'pdf'},
    'image/jpeg': {'jpg', 'jpeg'},
    'image/png': {'png'},
    'image/gif': {'gif'},
    'image/webp': {'webp'},
    'image/heic': {'heic'},
    'application/msword': {'doc'},
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': {'docx'},
}


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class InitiateUploadRequest(BaseModel):
    """Request to initiate a document upload."""
    workspace_id: int
    request_id: Optional[int] = None
    file_name: str = Field(..., min_length=1, max_length=255)
    file_size: int = Field(..., gt=0, le=MAX_FILE_SIZE)
    mime_type: str
    document_type: Optional[str] = None
    document_subtype: Optional[str] = None


class InitiateUploadResponse(BaseModel):
    """Response with presigned upload URL."""
    document_id: int
    upload_url: str
    storage_key: str
    expires_in: int = 3600
    fields: Optional[Dict[str, str]] = None  # For POST-based uploads


class ConfirmUploadRequest(BaseModel):
    """Request to confirm upload completion."""
    workspace_id: int
    document_id: int
    etag: Optional[str] = None  # S3 ETag for verification


class DocumentPreviewResponse(BaseModel):
    """Response with document preview URL."""
    document_id: int
    preview_url: str
    expires_in: int = 3600
    content_type: str
    file_name: str


class DocumentReviewRequest(BaseModel):
    """Request to review (approve/reject) a document."""
    action: str = Field(..., pattern="^(approve|reject|request_info)$")
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None
    notify_borrower: bool = True


class DocumentStatusUpdate(BaseModel):
    """Update document status."""
    status: str
    notes: Optional[str] = None


# =============================================================================
# UPLOAD ENDPOINTS
# =============================================================================

@router.post("/upload/initiate", response_model=InitiateUploadResponse)
async def initiate_document_upload(
    request: InitiateUploadRequest,
    http_request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Initiate document upload by generating a presigned S3 URL.

    Flow:
    1. Client calls this endpoint with file metadata
    2. Backend creates document record and generates presigned URL
    3. Client uploads directly to S3 using presigned URL
    4. Client calls /upload/confirm when complete
    """
    # Validate portal session
    from routes.portal_auth_routes import validate_portal_session
    session = await validate_portal_session(http_request, db) if http_request else None
    if not session or session.get("workspace_id") != request.workspace_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Validate mime type
    if request.mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: PDF, JPEG, PNG, Word documents"
        )

    # Validate workspace exists
    workspace = db.execute(text("""
        SELECT id, organization_id, meta_data
        FROM purl_workspaces
        WHERE id = :workspace_id
    """), {"workspace_id": request.workspace_id}).fetchone()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    org_id = workspace[1]
    meta_data = workspace[2] or {}
    lead_id = meta_data.get("lead_id")

    # Get loan_id if available
    loan = db.execute(text("""
        SELECT id FROM purl_loans
        WHERE workspace_id = :workspace_id
        ORDER BY created_at DESC LIMIT 1
    """), {"workspace_id": request.workspace_id}).fetchone()

    loan_id = loan[0] if loan else None

    # Generate unique storage key with validated extension
    file_ext = request.file_name.rsplit('.', 1)[-1].lower() if '.' in request.file_name else ''
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File extension '.{file_ext}' not allowed")

    # Validate MIME type matches file extension (prevent type mismatch)
    valid_exts = _MIME_TO_EXTENSIONS.get(request.mime_type)
    if valid_exts and file_ext not in valid_exts:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '.{file_ext}' does not match MIME type '{request.mime_type}'"
        )
    unique_id = str(uuid.uuid4())
    storage_key = f"workspaces/{request.workspace_id}/documents/{unique_id}.{file_ext}"

    try:
        # Create document record in pending_upload status
        result = db.execute(text("""
            INSERT INTO perennia_documents (
                loan_id, lead_id, request_id,
                file_name, file_size, mime_type,
                original_storage_key, status,
                doc_type, doc_subtype,
                classification_status, virus_scan_status,
                created_at, updated_at
            ) VALUES (
                :loan_id, :lead_id, :request_id,
                :file_name, :file_size, :mime_type,
                :storage_key, 'pending_upload',
                :doc_type, :doc_subtype,
                'pending', 'pending',
                NOW(), NOW()
            ) RETURNING id
        """), {
            "loan_id": loan_id,
            "lead_id": lead_id,
            "request_id": request.request_id,
            "file_name": request.file_name,
            "file_size": request.file_size,
            "mime_type": request.mime_type,
            "storage_key": storage_key,
            "doc_type": request.document_type,
            "doc_subtype": request.document_subtype,
        })

        document_id = result.fetchone()[0]
        db.commit()

        # Generate presigned URL
        s3_client = get_s3_client()
        if s3_client:
            try:
                presigned_url = s3_client.generate_presigned_url(
                    'put_object',
                    Params={
                        'Bucket': S3_BUCKET,
                        'Key': storage_key,
                        'ContentType': request.mime_type,
                    },
                    ExpiresIn=3600
                )
            except SQLAlchemyError as e:
                logger.error(f"Failed to generate presigned URL: {e}")
                presigned_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{storage_key}?presigned=mock"
        else:
            # Mock URL for development
            presigned_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{storage_key}?presigned=mock"

        # Log event
        db.execute(text("""
            INSERT INTO perennia_document_events (
                loan_id, lead_id, request_id, document_id,
                event_type, event_data, actor_type, created_at
            ) VALUES (
                :loan_id, :lead_id, :request_id, :document_id,
                'upload_initiated', :event_data, 'borrower', NOW()
            )
        """), {
            "loan_id": loan_id,
            "lead_id": lead_id,
            "request_id": request.request_id,
            "document_id": document_id,
            "event_data": {
                "file_name": request.file_name,
                "file_size": request.file_size,
                "mime_type": request.mime_type,
            }
        })
        db.commit()

        return InitiateUploadResponse(
            document_id=document_id,
            upload_url=presigned_url,
            storage_key=storage_key,
            expires_in=3600
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to initiate upload: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/upload/confirm")
async def confirm_document_upload(
    request: ConfirmUploadRequest,
    background_tasks: BackgroundTasks,
    http_request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Confirm document upload completed and trigger processing.

    Processing pipeline:
    1. Virus scan
    2. AI document classification
    3. Data extraction
    4. Compression (if applicable)
    5. Thumbnail/preview generation
    """
    # Validate portal session
    from routes.portal_auth_routes import validate_portal_session
    session = await validate_portal_session(http_request, db) if http_request else None
    if not session or session.get("workspace_id") != request.workspace_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Get document record
    document = db.execute(text("""
        SELECT id, loan_id, lead_id, request_id, original_storage_key, file_name, file_size
        FROM perennia_documents
        WHERE id = :document_id AND status = 'pending_upload'
    """), {"document_id": request.document_id}).fetchone()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found or already processed")

    # Optionally verify file exists in S3
    s3_client = get_s3_client()
    if s3_client:
        try:
            head_response = s3_client.head_object(
                Bucket=S3_BUCKET,
                Key=document[4]  # storage_key
            )
            actual_size = head_response.get('ContentLength', 0)

            # Verify size matches (within tolerance)
            if abs(actual_size - document[6]) > 1024:  # 1KB tolerance
                logger.warning(f"Size mismatch for document {request.document_id}: expected {document[6]}, got {actual_size}")
        except Exception as e:
            logger.warning(f"Could not verify S3 object: {e}")

    try:
        # Update document status
        db.execute(text("""
            UPDATE perennia_documents
            SET status = 'uploaded',
                virus_scan_status = 'pending',
                classification_status = 'pending',
                updated_at = NOW()
            WHERE id = :document_id
        """), {"document_id": request.document_id})

        # Log event
        db.execute(text("""
            INSERT INTO perennia_document_events (
                loan_id, lead_id, request_id, document_id,
                event_type, event_data, actor_type, created_at
            ) VALUES (
                :loan_id, :lead_id, :request_id, :document_id,
                'upload_completed', :event_data, 'borrower', NOW()
            )
        """), {
            "loan_id": document[1],
            "lead_id": document[2],
            "request_id": document[3],
            "document_id": request.document_id,
            "event_data": {
                "file_name": document[5],
                "file_size": document[6],
            }
        })

        db.commit()

        # Queue background processing jobs
        # background_tasks.add_task(process_document_pipeline, request.document_id)

        return {
            "success": True,
            "document_id": request.document_id,
            "status": "uploaded",
            "processing_queue": ["virus_scan", "ai_classification", "data_extraction"],
            "message": "Document uploaded successfully. Processing will begin shortly."
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to confirm upload: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# PREVIEW AND DOWNLOAD ENDPOINTS
# =============================================================================

@router.get("/{document_id}/preview", response_model=DocumentPreviewResponse)
async def get_document_preview(
    document_id: int = Path(..., description="Document ID"),
    workspace_id: int = Query(..., description="Workspace ID for authorization"),
    http_request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Get a signed URL for document preview.

    Uses CloudFront signed URLs if configured, otherwise S3 presigned URLs.
    """
    # Validate portal session
    from routes.portal_auth_routes import validate_portal_session
    session = await validate_portal_session(http_request, db) if http_request else None
    if not session or session.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # SEC DOC-008: Verify document belongs to the requested workspace
    document = db.execute(text("""
        SELECT d.id, d.file_name, d.mime_type, d.original_storage_key,
               d.preview_storage_key, d.status, d.workspace_id
        FROM perennia_documents d
        WHERE d.id = :document_id
    """), {"document_id": document_id}).fetchone()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # DOC-008: Verify workspace ownership — document must belong to requested workspace
    doc_workspace_id = document[6]
    if doc_workspace_id != workspace_id:
        logger.warning(f"Document access denied: doc {document_id} belongs to workspace {doc_workspace_id}, requested {workspace_id}")
        raise HTTPException(status_code=403, detail="Access denied: document does not belong to this workspace")

    # Also verify the workspace exists and is active
    workspace = db.execute(text("""
        SELECT id, status FROM purl_workspaces WHERE id = :workspace_id
    """), {"workspace_id": workspace_id}).fetchone()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if document[5] == 'pending_upload':
        raise HTTPException(status_code=400, detail="Document upload not complete")

    # Use preview if available, otherwise original
    storage_key = document[4] or document[3]

    # Generate signed URL
    if CLOUDFRONT_DOMAIN and CLOUDFRONT_KEY_PAIR_ID:
        # Use CloudFront signed URL
        try:
            from botocore.signers import CloudFrontSigner
            import rsa

            # Load private key
            private_key_path = os.getenv('CLOUDFRONT_PRIVATE_KEY_PATH')
            if private_key_path and os.path.exists(private_key_path):
                with open(private_key_path, 'rb') as key_file:
                    private_key = rsa.PrivateKey.load_pkcs1(key_file.read())

                def rsa_signer(message):
                    return rsa.sign(message, private_key, 'SHA-1')

                cf_signer = CloudFrontSigner(CLOUDFRONT_KEY_PAIR_ID, rsa_signer)

                expires = datetime.now(timezone.utc) + timedelta(hours=1)
                preview_url = cf_signer.generate_presigned_url(
                    f"https://{CLOUDFRONT_DOMAIN}/{storage_key}",
                    date_less_than=expires
                )
            else:
                # Fall back to S3
                raise Exception("CloudFront key not configured")
        except Exception as e:
            logger.warning(f"CloudFront signing failed, using S3: {e}")
            # Fall back to S3 presigned URL
            s3_client = get_s3_client()
            if s3_client:
                preview_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': S3_BUCKET, 'Key': storage_key},
                    ExpiresIn=3600
                )
            else:
                preview_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{storage_key}"
    else:
        # Use S3 presigned URL
        s3_client = get_s3_client()
        if s3_client:
            preview_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET, 'Key': storage_key},
                ExpiresIn=3600
            )
        else:
            preview_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{storage_key}"

    return DocumentPreviewResponse(
        document_id=document_id,
        preview_url=preview_url,
        expires_in=3600,
        content_type=document[2],
        file_name=document[1]
    )


@router.get("/{document_id}/download")
async def get_document_download_url(
    document_id: int = Path(..., description="Document ID"),
    workspace_id: int = Query(..., description="Workspace ID for authorization"),
    http_request: Request = None,
    db: Session = Depends(get_db)
):
    """Get a signed URL for document download."""
    # Validate portal session
    from routes.portal_auth_routes import validate_portal_session
    session = await validate_portal_session(http_request, db) if http_request else None
    if not session or session.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # SEC DOC-008: Verify document belongs to the requested workspace
    document = db.execute(text("""
        SELECT d.id, d.file_name, d.original_storage_key, d.workspace_id
        FROM perennia_documents d
        WHERE d.id = :document_id
    """), {"document_id": document_id}).fetchone()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # DOC-008: Verify workspace ownership — document must belong to requested workspace
    doc_workspace_id = document[3]
    if doc_workspace_id != workspace_id:
        logger.warning(f"Document download denied: doc {document_id} belongs to workspace {doc_workspace_id}, requested {workspace_id}")
        raise HTTPException(status_code=403, detail="Access denied: document does not belong to this workspace")

    # Verify the workspace exists and get organization_id for tenant validation
    workspace = db.execute(text("""
        SELECT id, organization_id FROM purl_workspaces WHERE id = :workspace_id
    """), {"workspace_id": workspace_id}).fetchone()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_org_id = workspace[1]

    # SEC DOC-013: Validate S3 key belongs to workspace's organization
    storage_key = document[2]
    if workspace_org_id and storage_key:
        # Check that the storage key belongs to the correct tenant
        expected_prefix = f"org-{workspace_org_id}/"
        if storage_key.startswith("org-") and not storage_key.startswith(expected_prefix):
            logger.warning(
                f"Document download denied: storage key {storage_key} does not belong to org {workspace_org_id}"
            )
            raise HTTPException(
                status_code=403,
                detail="Access denied: document belongs to another organization"
            )

    s3_client = get_s3_client()
    if s3_client:
        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': S3_BUCKET,
                'Key': storage_key,
                'ResponseContentDisposition': f'attachment; filename="{document[1]}"'
            },
            ExpiresIn=3600
        )
    else:
        download_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{storage_key}"

    return {
        "document_id": document_id,
        "download_url": download_url,
        "file_name": document[1],
        "expires_in": 3600
    }


# =============================================================================
# DOCUMENT REVIEW ENDPOINTS (Admin)
# =============================================================================

@router.post("/{document_id}/review")
async def review_document(
    document_id: int,
    review: DocumentReviewRequest,
    background_tasks: BackgroundTasks,
    http_request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Review a document (approve, reject, or request more info).

    Admin-only endpoint for document reviewers.
    """
    # Require CRM user auth (not portal session) for admin actions
    from main import get_current_user_flexible
    try:
        auth_header = http_request.headers.get("Authorization", "") if http_request else ""
        token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
        current_user = await get_current_user_flexible(token=token, request=http_request, db=db)
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication required")
    document = db.execute(text("""
        SELECT id, loan_id, lead_id, request_id, status
        FROM perennia_documents
        WHERE id = :document_id
    """), {"document_id": document_id}).fetchone()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    new_status = {
        "approve": "approved",
        "reject": "rejected",
        "request_info": "needs_info"
    }.get(review.action)

    if not new_status:
        raise HTTPException(status_code=400, detail="Invalid action")

    try:
        # Update document status
        db.execute(text("""
            UPDATE perennia_documents
            SET status = :status,
                rejection_reason = :rejection_reason,
                updated_at = NOW()
            WHERE id = :document_id
        """), {
            "document_id": document_id,
            "status": new_status,
            "rejection_reason": review.rejection_reason if review.action == "reject" else None
        })

        # Log event
        event_type = f"document_{review.action}d"
        db.execute(text("""
            INSERT INTO perennia_document_events (
                loan_id, lead_id, request_id, document_id,
                event_type, event_data, actor_type, created_at
            ) VALUES (
                :loan_id, :lead_id, :request_id, :document_id,
                :event_type, :event_data, 'lo', NOW()
            )
        """), {
            "loan_id": document[1],
            "lead_id": document[2],
            "request_id": document[3],
            "document_id": document_id,
            "event_type": event_type,
            "event_data": {
                "action": review.action,
                "rejection_reason": review.rejection_reason,
                "notes": review.notes
            }
        })

        # Update request status if applicable
        if document[3] and review.action == "approve":
            _update_request_completion(db, document[3])

        db.commit()

        # Notify borrower if requested
        if review.notify_borrower:
            # background_tasks.add_task(send_document_review_notification, document_id, review.action)
            pass

        return {
            "success": True,
            "document_id": document_id,
            "status": new_status,
            "action": review.action
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to review document: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _update_request_completion(db: Session, request_id: int):
    """Check if request is complete based on approved documents."""
    result = db.execute(text("""
        SELECT dr.quantity,
               COUNT(d.id) FILTER (WHERE d.status = 'approved') as approved_count
        FROM perennia_document_requests dr
        LEFT JOIN perennia_documents d ON d.request_id = dr.id
        WHERE dr.id = :request_id
        GROUP BY dr.id
    """), {"request_id": request_id}).fetchone()

    if result and result[1] >= result[0]:
        db.execute(text("""
            UPDATE perennia_document_requests
            SET status = 'complete', updated_at = NOW()
            WHERE id = :id
        """), {"id": request_id})


# =============================================================================
# DOCUMENT LIST ENDPOINTS
# =============================================================================

@router.get("/workspace/{workspace_id}")
async def list_workspace_documents(
    workspace_id: int,
    http_request: Request,
    status: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db)
):
    """List all documents for a workspace."""
    # Validate portal session
    from routes.portal_auth_routes import validate_portal_session
    session = await validate_portal_session(http_request, db)
    if not session or session.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Get loan_id and lead_id for workspace
    workspace = db.execute(text("""
        SELECT w.meta_data,
               (SELECT id FROM purl_loans WHERE workspace_id = w.id ORDER BY created_at DESC LIMIT 1) as loan_id
        FROM purl_workspaces w
        WHERE w.id = :workspace_id
    """), {"workspace_id": workspace_id}).fetchone()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    meta_data = workspace[0] or {}
    loan_id = workspace[1]
    lead_id = meta_data.get("lead_id")

    # Build query
    filters = []
    params = {"limit": limit, "offset": offset}

    if loan_id:
        filters.append("loan_id = :loan_id")
        params["loan_id"] = loan_id
    elif lead_id:
        filters.append("lead_id = :lead_id")
        params["lead_id"] = lead_id
    else:
        return {"documents": [], "total": 0}

    if status:
        filters.append("status = :status")
        params["status"] = status
    if doc_type:
        filters.append("doc_type = :doc_type")
        params["doc_type"] = doc_type

    where_clause = " AND ".join(filters)

    documents = db.execute(text(f"""
        SELECT id, file_name, file_size, mime_type, status,
               doc_type, doc_subtype, classification_status,
               classification_confidence, rejection_reason,
               created_at, updated_at
        FROM perennia_documents
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    total = db.execute(text(f"""
        SELECT COUNT(*) FROM perennia_documents WHERE {where_clause}
    """), params).scalar()

    return {
        "documents": [
            {
                "id": doc[0],
                "file_name": doc[1],
                "file_size": doc[2],
                "mime_type": doc[3],
                "status": doc[4],
                "doc_type": doc[5],
                "doc_subtype": doc[6],
                "classification_status": doc[7],
                "classification_confidence": doc[8],
                "rejection_reason": doc[9],
                "created_at": doc[10].isoformat() if doc[10] else None,
                "updated_at": doc[11].isoformat() if doc[11] else None,
            }
            for doc in documents
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/health")
async def portal_documents_health():
    """Portal documents health check."""
    s3_status = "connected" if get_s3_client() else "not_configured"
    return {
        "status": "healthy",
        "service": "portal_documents",
        "s3": s3_status,
        "bucket": S3_BUCKET,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
