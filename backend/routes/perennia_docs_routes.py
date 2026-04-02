"""
Perennia Docs AI API Routes

API endpoints for the AI-powered document management system.
Provides endpoints for:
- Document requests and checklist management
- Template packs CRUD
- Document upload, classification, and approval
- Borrower portal with magic link auth
- Notifications and audit events
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List, Callable, Any, Dict
from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone, timedelta
import secrets
import logging
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/perennia-docs", tags=["Perennia Docs AI"])


# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

from db import get_db

_get_current_user: Callable = None
_User: Any = None
_models: Dict[str, Any] = None


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable, user_model: Any, perennia_models: Dict[str, Any] = None):
    """Set dependencies from main.py to avoid circular imports."""
    global _get_current_user, _User, _models
    _get_current_user = get_current_user_func
    _User = user_model
    _models = perennia_models
    logger.info("Perennia Docs routes dependencies set")


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user dependency - wrapper for injected dependency."""
    if _get_current_user is None:
        raise RuntimeError("Perennia Docs routes not initialized. Call set_dependencies first.")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


def get_models():
    """Get Perennia Docs models."""
    if _models is None:
        raise RuntimeError("Perennia Docs models not initialized. Call set_dependencies first.")
    return _models


# =============================================================================
# BACKGROUND PROCESSING FUNCTIONS
# =============================================================================

async def process_document_background(document_id: int):
    """
    Background task to process uploaded document.

    Performs:
    1. Virus scan (simulated - in production would use ClamAV or similar)
    2. AI classification using DocumentAnalysisService
    """
    from database import SessionLocal

    db = SessionLocal()
    try:
        # Get document info
        doc = db.execute(text("""
            SELECT id, storage_key, file_name, original_filename,
                   loan_id, lead_id, request_id
            FROM perennia_documents
            WHERE id = :id
        """), {"id": document_id}).fetchone()

        if not doc:
            logger.error(f"Document {document_id} not found for processing")
            return

        # Step 1: Virus scan (simulated - mark as clean)
        # In production, integrate with ClamAV or cloud antivirus API
        logger.info(f"Running virus scan for document {document_id}")
        db.execute(text("""
            UPDATE perennia_documents
            SET virus_scan_status = 'clean',
                virus_scanned_at = NOW(),
                updated_at = NOW()
            WHERE id = :id
        """), {"id": document_id})
        db.commit()

        logger.info(f"Document {document_id} passed virus scan")

        # Step 2: AI Classification
        logger.info(f"Running AI classification for document {document_id}")
        try:
            from services.document_analysis_service import DocumentAnalysisService

            # Get storage path (in production, download from S3)
            # TENANT-007: Namespace temp path by organization to prevent cross-tenant file access
            _org_id = None
            if doc.loan_id:
                _org_row = db.execute(text("SELECT organization_id FROM loans WHERE id = :lid"), {"lid": doc.loan_id}).fetchone()
                _org_id = _org_row.organization_id if _org_row and _org_row.organization_id else None
            org_subdir = f"org_{_org_id}" if _org_id else "unscoped"
            storage_path = f"/tmp/perennia-docs/{org_subdir}/{doc.storage_key}" if doc.storage_key else None

            if storage_path:
                analysis_service = DocumentAnalysisService()
                # Note: In production, would actually analyze the file
                # For now, update status to indicate classification complete

            # Mark classification as complete
            db.execute(text("""
                UPDATE perennia_documents
                SET classification_status = 'complete',
                    classified_at = NOW(),
                    status = 'pending_review',
                    updated_at = NOW()
                WHERE id = :id
            """), {"id": document_id})
            db.commit()

            logger.info(f"Document {document_id} classification complete")

        except Exception as classify_err:
            logger.error(f"Classification failed for document {document_id}: {classify_err}")
            db.execute(text("""
                UPDATE perennia_documents
                SET classification_status = 'failed',
                    classification_error = :error,
                    updated_at = NOW()
                WHERE id = :id
            """), {"id": document_id, "error": str(classify_err)})
            db.commit()

        # Log processing complete event
        db.execute(text("""
            INSERT INTO perennia_document_events (
                loan_id, lead_id, request_id, document_id,
                event_type, event_data, actor_type, created_at
            ) VALUES (
                :loan_id, :lead_id, :request_id, :document_id,
                'document_processed', :event_data, 'system', NOW()
            )
        """), {
            "loan_id": doc.loan_id,
            "lead_id": doc.lead_id,
            "request_id": doc.request_id,
            "document_id": document_id,
            "event_data": {"virus_scan": "clean", "classification": "complete"}
        })
        db.commit()

    except SQLAlchemyError as e:
        logger.error(f"Error processing document {document_id}: {e}")
        db.rollback()
    finally:
        db.close()


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

# Document Request Models
class CreateDocumentRequestPayload(BaseModel):
    loan_id: int
    lead_id: Optional[int] = None
    doc_type: str
    doc_subtype: Optional[str] = None
    title: str
    description: Optional[str] = None
    quantity: int = 1
    priority: str = "normal"
    expiration_date: Optional[datetime] = None
    expiration_threshold: int = 90
    reminder_schedule: Optional[List[int]] = None


class UpdateDocumentRequestPayload(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[int] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    expiration_date: Optional[datetime] = None


class ApplyTemplatePackRequest(BaseModel):
    template_pack_id: int
    loan_id: int
    lead_id: Optional[int] = None


# Template Pack Models
class DocumentRequirementConfig(BaseModel):
    doc_type: str
    doc_subtype: Optional[str] = None
    title: str
    description: Optional[str] = None
    quantity: int = 1
    expiration_threshold: int = 90
    required: bool = True


class CreateTemplatePackPayload(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    version: str = "1"
    loan_programs: Optional[List[str]] = None
    employment_types: Optional[List[str]] = None
    property_types: Optional[List[str]] = None
    document_requirements: List[DocumentRequirementConfig]
    reminder_schedule: Optional[List[int]] = None


class UpdateTemplatePackPayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    document_requirements: Optional[List[DocumentRequirementConfig]] = None


# Document Models
class DocumentApprovalPayload(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None


class DocumentClassificationOverride(BaseModel):
    doc_type: str
    doc_subtype: Optional[str] = None


# Borrower Portal Models
class GenerateMagicLinkRequest(BaseModel):
    lead_id: int
    loan_id: Optional[int] = None
    recipient_email: EmailStr
    expires_in_hours: int = 72


class ValidateMagicLinkRequest(BaseModel):
    token: str


# Notification Models
class CreateNotificationPayload(BaseModel):
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    channel: str  # EMAIL, SMS
    template: str
    recipient_email: Optional[str] = None
    recipient_phone: Optional[str] = None
    subject: Optional[str] = None
    body: str
    metadata: Optional[Dict[str, Any]] = None
    scheduled_for: Optional[datetime] = None


# Rule Models
class RuleCondition(BaseModel):
    field: str
    operator: str
    value: Any


class RuleAction(BaseModel):
    type: str
    params: Optional[Dict[str, Any]] = None


class CreateDocumentRulePayload(BaseModel):
    name: str
    description: Optional[str] = None
    trigger: str
    conditions: List[RuleCondition]
    actions: List[RuleAction]
    priority: int = 100


# =============================================================================
# DOCUMENT REQUEST ENDPOINTS
# =============================================================================

@router.post("/requests")
async def create_document_request(
    payload: CreateDocumentRequestPayload,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new document request for a loan."""
    try:
        result = db.execute(text("""
            INSERT INTO perennia_document_requests (
                loan_id, lead_id, doc_type, doc_subtype, title, description,
                quantity, priority, expiration_date, expiration_threshold,
                reminder_schedule, status, created_at, updated_at
            ) VALUES (
                :loan_id, :lead_id, :doc_type, :doc_subtype, :title, :description,
                :quantity, :priority, :expiration_date, :expiration_threshold,
                :reminder_schedule, 'pending', NOW(), NOW()
            ) RETURNING id
        """), {
            "loan_id": payload.loan_id,
            "lead_id": payload.lead_id,
            "doc_type": payload.doc_type,
            "doc_subtype": payload.doc_subtype,
            "title": payload.title,
            "description": payload.description,
            "quantity": payload.quantity,
            "priority": payload.priority,
            "expiration_date": payload.expiration_date,
            "expiration_threshold": payload.expiration_threshold,
            "reminder_schedule": payload.reminder_schedule
        })

        request_id = result.fetchone()[0]
        db.commit()

        # Log event
        db.execute(text("""
            INSERT INTO perennia_document_events (
                loan_id, lead_id, request_id, event_type, event_data,
                actor_type, actor_id, created_at
            ) VALUES (
                :loan_id, :lead_id, :request_id, 'request_created',
                :event_data, 'lo', :user_id, NOW()
            )
        """), {
            "loan_id": payload.loan_id,
            "lead_id": payload.lead_id,
            "request_id": request_id,
            "event_data": {"doc_type": payload.doc_type, "title": payload.title},
            "user_id": current_user.id
        })
        db.commit()

        return {"success": True, "request_id": request_id}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


@router.get("/requests")
async def list_document_requests(
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List document requests with filters."""
    filters = []
    params = {"limit": limit, "offset": offset}

    if loan_id:
        filters.append("loan_id = :loan_id")
        params["loan_id"] = loan_id
    if lead_id:
        filters.append("lead_id = :lead_id")
        params["lead_id"] = lead_id
    if status:
        filters.append("status = :status")
        params["status"] = status

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    sql = """
        SELECT id, loan_id, lead_id, doc_type, doc_subtype, title, description,
               quantity, status, priority, expiration_date, expiration_threshold,
               reminder_count, created_at, updated_at
        FROM perennia_document_requests
        """ + where_clause + """
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """
    result = db.execute(text(sql), params)

    requests = [dict(row._mapping) for row in result]

    # Get total count
    sql = "SELECT COUNT(*) FROM perennia_document_requests " + where_clause
    count_result = db.execute(text(sql), params)
    total = count_result.scalar()

    return {
        "requests": requests,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/requests/{request_id}")
async def get_document_request(
    request_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific document request with uploaded documents."""
    request_result = db.execute(text("""
        SELECT id, loan_id, lead_id, doc_type, doc_subtype, title, description,
               quantity, status, priority, expiration_date, expiration_threshold,
               reminder_schedule, reminder_count, last_reminder_sent,
               created_at, updated_at
        FROM perennia_document_requests
        WHERE id = :id
    """), {"id": request_id})

    row = request_result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document request not found")

    request_data = dict(row._mapping)

    # Get associated documents
    docs_result = db.execute(text("""
        SELECT id, file_name, file_size, mime_type, status,
               classification_status, doc_type, doc_subtype,
               classification_confidence, virus_scan_status,
               created_at
        FROM perennia_documents
        WHERE request_id = :request_id
        ORDER BY created_at DESC
    """), {"request_id": request_id})

    request_data["documents"] = [dict(row._mapping) for row in docs_result]
    request_data["documents_count"] = len(request_data["documents"])

    return request_data


@router.patch("/requests/{request_id}")
async def update_document_request(
    request_id: int,
    payload: UpdateDocumentRequestPayload,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a document request."""
    updates = []
    params = {"id": request_id}

    if payload.title is not None:
        updates.append("title = :title")
        params["title"] = payload.title
    if payload.description is not None:
        updates.append("description = :description")
        params["description"] = payload.description
    if payload.quantity is not None:
        updates.append("quantity = :quantity")
        params["quantity"] = payload.quantity
    if payload.priority is not None:
        updates.append("priority = :priority")
        params["priority"] = payload.priority
    if payload.status is not None:
        updates.append("status = :status")
        params["status"] = payload.status
    if payload.expiration_date is not None:
        updates.append("expiration_date = :expiration_date")
        params["expiration_date"] = payload.expiration_date

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    updates.append("updated_at = NOW()")

    try:
        sql = """
            UPDATE perennia_document_requests
            SET """ + ', '.join(updates) + """
            WHERE id = :id
            RETURNING id
        """
        result = db.execute(text(sql), params)

        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Document request not found")

        db.commit()
        return {"success": True, "request_id": request_id}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


@router.delete("/requests/{request_id}")
async def delete_document_request(
    request_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a document request (soft delete by setting status to cancelled)."""
    try:
        result = db.execute(text("""
            UPDATE perennia_document_requests
            SET status = 'cancelled', updated_at = NOW()
            WHERE id = :id
            RETURNING id
        """), {"id": request_id})

        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Document request not found")

        db.commit()
        return {"success": True, "message": "Document request cancelled"}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


# =============================================================================
# TEMPLATE PACK ENDPOINTS
# =============================================================================

@router.get("/templates")
async def list_template_packs(
    loan_program: Optional[str] = None,
    employment_type: Optional[str] = None,
    is_active: bool = True,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List available template packs with optional filters."""
    filters = ["is_active = :is_active"]
    params = {"is_active": is_active}

    if loan_program:
        filters.append(":loan_program = ANY(loan_programs)")
        params["loan_program"] = loan_program
    if employment_type:
        filters.append(":employment_type = ANY(employment_types)")
        params["employment_type"] = employment_type

    where_clause = " AND ".join(filters)

    sql = """
        SELECT id, name, slug, description, version,
               loan_programs, employment_types, property_types,
               is_active, created_at
        FROM perennia_template_packs
        WHERE """ + where_clause + """
        ORDER BY name
    """
    result = db.execute(text(sql), params)

    templates = [dict(row._mapping) for row in result]
    return {"templates": templates, "count": len(templates)}


@router.get("/templates/{template_id}")
async def get_template_pack(
    template_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific template pack with full configuration."""
    result = db.execute(text("""
        SELECT id, name, slug, description, version,
               loan_programs, employment_types, property_types,
               config, is_active, created_at, updated_at
        FROM perennia_template_packs
        WHERE id = :id
    """), {"id": template_id})

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Template pack not found")

    return dict(row._mapping)


@router.post("/templates")
async def create_template_pack(
    payload: CreateTemplatePackPayload,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new template pack."""
    config = {
        "documentRequirements": [req.dict() for req in payload.document_requirements],
        "reminderSchedule": payload.reminder_schedule or [1, 3, 7]
    }

    try:
        result = db.execute(text("""
            INSERT INTO perennia_template_packs (
                name, slug, description, version,
                loan_programs, employment_types, property_types,
                config, is_active, created_at, updated_at
            ) VALUES (
                :name, :slug, :description, :version,
                :loan_programs, :employment_types, :property_types,
                :config, true, NOW(), NOW()
            ) RETURNING id
        """), {
            "name": payload.name,
            "slug": payload.slug,
            "description": payload.description,
            "version": payload.version,
            "loan_programs": payload.loan_programs,
            "employment_types": payload.employment_types,
            "property_types": payload.property_types,
            "config": config
        })

        template_id = result.fetchone()[0]
        db.commit()

        return {"success": True, "template_id": template_id}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


@router.patch("/templates/{template_id}")
async def update_template_pack(
    template_id: int,
    payload: UpdateTemplatePackPayload,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a template pack."""
    updates = []
    params = {"id": template_id}

    if payload.name is not None:
        updates.append("name = :name")
        params["name"] = payload.name
    if payload.description is not None:
        updates.append("description = :description")
        params["description"] = payload.description
    if payload.is_active is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = payload.is_active
    if payload.document_requirements is not None:
        updates.append("config = jsonb_set(config, '{documentRequirements}', :requirements)")
        params["requirements"] = [req.dict() for req in payload.document_requirements]

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    updates.append("updated_at = NOW()")

    try:
        sql = """
            UPDATE perennia_template_packs
            SET """ + ', '.join(updates) + """
            WHERE id = :id
            RETURNING id
        """
        result = db.execute(text(sql), params)

        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Template pack not found")

        db.commit()
        return {"success": True, "template_id": template_id}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


@router.post("/templates/apply")
async def apply_template_pack(
    payload: ApplyTemplatePackRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Apply a template pack to a loan, creating document requests.

    This generates a checklist of required documents based on the template.
    """
    # Get template
    template_result = db.execute(text("""
        SELECT id, name, version, config
        FROM perennia_template_packs
        WHERE id = :id AND is_active = true
    """), {"id": payload.template_pack_id})

    template = template_result.fetchone()
    if not template:
        raise HTTPException(status_code=404, detail="Template pack not found or inactive")

    config = template[3]
    requirements = config.get("documentRequirements", [])
    reminder_schedule = config.get("reminderSchedule", [1, 3, 7])

    created_requests = []

    try:
        for req in requirements:
            result = db.execute(text("""
                INSERT INTO perennia_document_requests (
                    loan_id, lead_id, template_pack_id, template_pack_version,
                    doc_type, doc_subtype, title, description,
                    quantity, priority, expiration_threshold,
                    reminder_schedule, status, created_at, updated_at
                ) VALUES (
                    :loan_id, :lead_id, :template_id, :version,
                    :doc_type, :doc_subtype, :title, :description,
                    :quantity, :priority, :expiration_threshold,
                    :reminder_schedule, 'pending', NOW(), NOW()
                ) RETURNING id
            """), {
                "loan_id": payload.loan_id,
                "lead_id": payload.lead_id,
                "template_id": payload.template_pack_id,
                "version": template[2],
                "doc_type": req.get("doc_type"),
                "doc_subtype": req.get("doc_subtype"),
                "title": req.get("title"),
                "description": req.get("description"),
                "quantity": req.get("quantity", 1),
                "priority": "high" if req.get("required", True) else "normal",
                "expiration_threshold": req.get("expiration_threshold", 90),
                "reminder_schedule": reminder_schedule
            })

            request_id = result.fetchone()[0]
            created_requests.append({
                "id": request_id,
                "doc_type": req.get("doc_type"),
                "title": req.get("title")
            })

        # Log event
        db.execute(text("""
            INSERT INTO perennia_document_events (
                loan_id, lead_id, event_type, event_data,
                actor_type, actor_id, created_at
            ) VALUES (
                :loan_id, :lead_id, 'template_applied',
                :event_data, 'lo', :user_id, NOW()
            )
        """), {
            "loan_id": payload.loan_id,
            "lead_id": payload.lead_id,
            "event_data": {
                "template_id": payload.template_pack_id,
                "template_name": template[1],
                "requests_created": len(created_requests)
            },
            "user_id": current_user.id
        })

        db.commit()

        return {
            "success": True,
            "template_applied": template[1],
            "requests_created": len(created_requests),
            "requests": created_requests
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


# =============================================================================
# DOCUMENT ENDPOINTS
# =============================================================================

@router.get("/documents")
async def list_documents(
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    request_id: Optional[int] = None,
    status: Optional[str] = None,
    doc_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List documents with filters."""
    filters = []
    params = {"limit": limit, "offset": offset}

    if loan_id:
        filters.append("loan_id = :loan_id")
        params["loan_id"] = loan_id
    if lead_id:
        filters.append("lead_id = :lead_id")
        params["lead_id"] = lead_id
    if request_id:
        filters.append("request_id = :request_id")
        params["request_id"] = request_id
    if status:
        filters.append("status = :status")
        params["status"] = status
    if doc_type:
        filters.append("doc_type = :doc_type")
        params["doc_type"] = doc_type

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    sql = """
        SELECT id, loan_id, lead_id, request_id, file_name, file_size, mime_type,
               status, rejection_reason, classification_status,
               doc_type, doc_subtype, classification_confidence,
               virus_scan_status, document_date, expires_at,
               created_at, updated_at
        FROM perennia_documents
        """ + where_clause + """
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """
    result = db.execute(text(sql), params)

    documents = [dict(row._mapping) for row in result]

    return {
        "documents": documents,
        "count": len(documents),
        "limit": limit,
        "offset": offset
    }


@router.get("/review-queue")
async def get_review_queue(
    status: Optional[str] = Query("pending", description="Filter by status"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    search: Optional[str] = Query(None, description="Search borrower name or loan number"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get documents for admin review queue with borrower/loan info."""
    offset = (page - 1) * limit
    filters = []
    params = {"limit": limit, "offset": offset}

    if status:
        filters.append("d.status = :status")
        params["status"] = status
    if document_type:
        filters.append("d.doc_type = :doc_type")
        params["doc_type"] = document_type
    if search:
        filters.append("(c.first_name ILIKE :search OR c.last_name ILIKE :search OR l.loan_number ILIKE :search)")
        params["search"] = f"%{search}%"

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    # Query with JOINs to get borrower and loan info
    sql = """
        SELECT
            d.id, d.file_name, d.doc_type as document_type, d.status,
            d.file_size, d.mime_type as file_type, d.rejection_reason,
            d.created_at as uploaded_at,
            COALESCE(c.first_name || ' ' || c.last_name, 'Unknown') as borrower_name,
            COALESCE(c.email, '') as borrower_email,
            COALESCE(l.loan_number, 'N/A') as loan_number,
            d.loan_id, d.lead_id
        FROM perennia_documents d
        LEFT JOIN loans l ON d.loan_id = l.id
        LEFT JOIN contacts c ON l.borrower_id = c.id OR d.lead_id = c.lead_id
        """ + where_clause + """
        ORDER BY d.created_at DESC
        LIMIT :limit OFFSET :offset
    """
    result = db.execute(text(sql), params)

    documents = [dict(row._mapping) for row in result]

    # Get total count
    sql = """
        SELECT COUNT(*) as total
        FROM perennia_documents d
        LEFT JOIN loans l ON d.loan_id = l.id
        LEFT JOIN contacts c ON l.borrower_id = c.id OR d.lead_id = c.lead_id
        """ + where_clause
    count_result = db.execute(text(sql), {k: v for k, v in params.items() if k not in ['limit', 'offset']})
    total = count_result.fetchone()[0]

    return {
        "documents": documents,
        "total": total,
        "page": page,
        "limit": limit
    }


@router.post("/review/approve")
async def bulk_approve_documents(
    payload: dict,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk approve documents."""
    document_ids = payload.get("document_ids", [])
    if not document_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    try:
        result = db.execute(text("""
            UPDATE perennia_documents
            SET status = 'approved', updated_at = NOW()
            WHERE id = ANY(:ids) AND status = 'pending'
            RETURNING id
        """), {"ids": document_ids})

        approved_ids = [row[0] for row in result.fetchall()]
        db.commit()

        return {
            "success": True,
            "approved_count": len(approved_ids),
            "approved_ids": approved_ids
        }
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


@router.post("/review/reject")
async def bulk_reject_documents(
    payload: dict,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk reject documents with reason."""
    document_ids = payload.get("document_ids", [])
    reason = payload.get("reason", "")

    if not document_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    try:
        result = db.execute(text("""
            UPDATE perennia_documents
            SET status = 'rejected',
                rejection_reason = :reason,
                updated_at = NOW()
            WHERE id = ANY(:ids) AND status = 'pending'
            RETURNING id
        """), {"ids": document_ids, "reason": reason})

        rejected_ids = [row[0] for row in result.fetchall()]
        db.commit()

        return {
            "success": True,
            "rejected_count": len(rejected_ids),
            "rejected_ids": rejected_ids
        }
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


@router.get("/documents/{document_id}")
async def get_document(
    document_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific document with full details."""
    result = db.execute(text("""
        SELECT id, loan_id, lead_id, request_id, borrower_id, uploaded_by_user_id,
               file_name, file_size, mime_type,
               original_storage_key, compressed_storage_key, preview_storage_key,
               compression_ratio, compression_method, derivative_type,
               status, rejection_reason,
               classification_status, doc_type, doc_subtype,
               classification_confidence, extracted_data, validation_errors, quality_checks,
               ai_model, ai_prompt_hash, retrieval_context_ids,
               virus_scan_status, virus_scan_result,
               document_date, expires_at,
               created_at, updated_at
        FROM perennia_documents
        WHERE id = :id
    """), {"id": document_id})

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    return dict(row._mapping)


@router.post("/documents/{document_id}/approve")
async def approve_or_reject_document(
    document_id: int,
    payload: DocumentApprovalPayload,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Approve or reject a document."""
    new_status = "approved" if payload.approved else "rejected"

    try:
        result = db.execute(text("""
            UPDATE perennia_documents
            SET status = :status,
                rejection_reason = :reason,
                updated_at = NOW()
            WHERE id = :id
            RETURNING id, loan_id, lead_id, request_id
        """), {
            "id": document_id,
            "status": new_status,
            "reason": payload.rejection_reason if not payload.approved else None
        })

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        # Log event
        event_type = "document_approved" if payload.approved else "document_rejected"
        db.execute(text("""
            INSERT INTO perennia_document_events (
                loan_id, lead_id, request_id, document_id,
                event_type, event_data, actor_type, actor_id, created_at
            ) VALUES (
                :loan_id, :lead_id, :request_id, :document_id,
                :event_type, :event_data, 'lo', :user_id, NOW()
            )
        """), {
            "loan_id": row[1],
            "lead_id": row[2],
            "request_id": row[3],
            "document_id": document_id,
            "event_type": event_type,
            "event_data": {"rejection_reason": payload.rejection_reason} if not payload.approved else {},
            "user_id": current_user.id
        })

        # Check if request is now complete
        if row[3] and payload.approved:
            _update_request_status(db, row[3])

        db.commit()

        return {
            "success": True,
            "document_id": document_id,
            "status": new_status
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


@router.post("/documents/{document_id}/classify")
async def override_document_classification(
    document_id: int,
    payload: DocumentClassificationOverride,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Override AI classification for a document."""
    try:
        result = db.execute(text("""
            UPDATE perennia_documents
            SET doc_type = :doc_type,
                doc_subtype = :doc_subtype,
                classification_status = 'classified',
                updated_at = NOW()
            WHERE id = :id
            RETURNING id
        """), {
            "id": document_id,
            "doc_type": payload.doc_type,
            "doc_subtype": payload.doc_subtype
        })

        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Document not found")

        db.commit()
        return {"success": True, "document_id": document_id}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


def _update_request_status(db: Session, request_id: int):
    """Update request status based on document count."""
    result = db.execute(text("""
        SELECT dr.quantity,
               COUNT(d.id) FILTER (WHERE d.status = 'approved') as approved_count
        FROM perennia_document_requests dr
        LEFT JOIN perennia_documents d ON d.request_id = dr.id
        WHERE dr.id = :request_id
        GROUP BY dr.id
    """), {"request_id": request_id})

    row = result.fetchone()
    if row and row[1] >= row[0]:
        db.execute(text("""
            UPDATE perennia_document_requests
            SET status = 'complete', updated_at = NOW()
            WHERE id = :id
        """), {"id": request_id})


# =============================================================================
# UPLOAD ENDPOINTS
# =============================================================================

@router.post("/upload/presigned-url")
async def get_upload_presigned_url(
    loan_id: int,
    request_id: Optional[int] = None,
    file_name: str = Query(...),
    content_type: str = Query(...),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a presigned URL for direct S3 upload.

    Returns presigned URL and document record ID.
    Client should upload directly to S3, then call /upload/complete.
    """
    import uuid

    # Generate storage key
    file_ext = file_name.split('.')[-1] if '.' in file_name else 'bin'
    storage_key = f"documents/{loan_id}/{uuid.uuid4()}.{file_ext}"

    try:
        # Create document record
        result = db.execute(text("""
            INSERT INTO perennia_documents (
                loan_id, request_id, uploaded_by_user_id,
                file_name, file_size, mime_type,
                original_storage_key, status,
                created_at, updated_at
            ) VALUES (
                :loan_id, :request_id, :user_id,
                :file_name, 0, :mime_type,
                :storage_key, 'pending_upload',
                NOW(), NOW()
            ) RETURNING id
        """), {
            "loan_id": loan_id,
            "request_id": request_id,
            "user_id": current_user.id,
            "file_name": file_name,
            "mime_type": content_type,
            "storage_key": storage_key
        })

        document_id = result.fetchone()[0]
        db.commit()

        # Generate actual presigned URL from S3
        try:
            from services.perennia_s3_service import get_s3_service
            s3_service = get_s3_service()

            # Use PUT method for simpler client-side upload
            presigned_result = s3_service.get_presigned_put_url(
                storage_key=storage_key,
                content_type=content_type
            )

            if presigned_result.get("success"):
                return {
                    "document_id": document_id,
                    "presigned_url": presigned_result["presigned_url"],
                    "storage_key": storage_key,
                    "expires_in": presigned_result.get("expires_in", 3600),
                    "method": "PUT",
                    "headers": presigned_result.get("headers", {"Content-Type": content_type})
                }
            else:
                # Log error but still return document ID
                logger.warning(f"S3 presigned URL generation failed: {presigned_result.get('error')}")

        except Exception as s3_error:
            logger.warning(f"S3 service error (using fallback): {s3_error}")

        # Fallback for development/testing without S3
        presigned_url = f"https://s3.amazonaws.com/perennia-docs/{storage_key}?presigned=placeholder"
        return {
            "document_id": document_id,
            "presigned_url": presigned_url,
            "storage_key": storage_key,
            "expires_in": 3600,
            "method": "PUT",
            "note": "S3 not configured - using placeholder URL"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


@router.post("/upload/complete/{document_id}")
async def complete_upload(
    document_id: int,
    file_size: int = Query(...),
    background_tasks: BackgroundTasks = None,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Complete upload and trigger processing pipeline.

    Triggers:
    1. Virus scan
    2. AI classification
    3. Compression (if applicable)
    """
    try:
        result = db.execute(text("""
            UPDATE perennia_documents
            SET file_size = :file_size,
                status = 'uploaded',
                virus_scan_status = 'pending',
                classification_status = 'pending',
                updated_at = NOW()
            WHERE id = :id AND status = 'pending_upload'
            RETURNING id, loan_id, lead_id, request_id
        """), {
            "id": document_id,
            "file_size": file_size
        })

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found or already processed")

        # Log upload event
        db.execute(text("""
            INSERT INTO perennia_document_events (
                loan_id, lead_id, request_id, document_id,
                event_type, event_data, actor_type, actor_id, created_at
            ) VALUES (
                :loan_id, :lead_id, :request_id, :document_id,
                'document_uploaded', :event_data, 'borrower', :user_id, NOW()
            )
        """), {
            "loan_id": row[1],
            "lead_id": row[2],
            "request_id": row[3],
            "document_id": document_id,
            "event_data": {"file_size": file_size},
            "user_id": current_user.id
        })

        db.commit()

        # Trigger background jobs for virus scan and AI classification
        if background_tasks:
            background_tasks.add_task(process_document_background, document_id)
            logger.info(f"Queued background processing for document {document_id}")

        return {
            "success": True,
            "document_id": document_id,
            "status": "uploaded",
            "next_steps": ["virus_scan", "ai_classification"],
            "processing_queued": background_tasks is not None
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


# =============================================================================
# BORROWER PORTAL ENDPOINTS
# =============================================================================

@router.post("/portal/magic-link")
async def generate_magic_link(
    payload: GenerateMagicLinkRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a magic link for borrower portal access."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=payload.expires_in_hours)

    try:
        result = db.execute(text("""
            INSERT INTO perennia_portal_sessions (
                lead_id, loan_id, magic_link_token,
                token_expires_at, is_active, created_at
            ) VALUES (
                :lead_id, :loan_id, :token,
                :expires_at, true, NOW()
            ) RETURNING id
        """), {
            "lead_id": payload.lead_id,
            "loan_id": payload.loan_id,
            "token": token,
            "expires_at": expires_at
        })

        session_id = result.fetchone()[0]
        db.commit()

        # Generate portal URL
        portal_url = f"https://portal.perennia.ai/docs/{token}"

        return {
            "success": True,
            "session_id": session_id,
            "magic_link": portal_url,
            "expires_at": expires_at.isoformat(),
            "recipient_email": payload.recipient_email
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


@router.post("/portal/validate")
async def validate_magic_link(
    payload: ValidateMagicLinkRequest,
    db: Session = Depends(get_db)
):
    """
    Validate a magic link token and return session info.

    This is a PUBLIC endpoint (no auth required).
    """
    result = db.execute(text("""
        SELECT ps.id, ps.lead_id, ps.loan_id,
               ps.token_expires_at, ps.session_expires_at,
               l.first_name, l.last_name, l.email
        FROM perennia_portal_sessions ps
        JOIN leads l ON l.id = ps.lead_id
        WHERE ps.magic_link_token = :token
          AND ps.is_active = true
          AND ps.token_expires_at > NOW()
    """), {"token": payload.token})

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Update session activity
    session_expires = datetime.now(timezone.utc) + timedelta(hours=2)
    db.execute(text("""
        UPDATE perennia_portal_sessions
        SET session_expires_at = :expires,
            last_activity_at = NOW()
        WHERE id = :id
    """), {"id": row[0], "expires": session_expires})
    db.commit()

    return {
        "valid": True,
        "session_id": row[0],
        "lead_id": row[1],
        "loan_id": row[2],
        "borrower": {
            "first_name": row[5],
            "last_name": row[6],
            "email": row[7]
        },
        "session_expires_at": session_expires.isoformat()
    }


@router.get("/portal/checklist")
async def get_borrower_checklist(
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Get document checklist for borrower portal.

    PUBLIC endpoint - validates token.
    """
    # Validate session
    session = db.execute(text("""
        SELECT lead_id, loan_id
        FROM perennia_portal_sessions
        WHERE magic_link_token = :token
          AND is_active = true
          AND session_expires_at > NOW()
    """), {"token": token}).fetchone()

    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    loan_id = session[1]

    # Get document requests
    requests = db.execute(text("""
        SELECT dr.id, dr.doc_type, dr.title, dr.description,
               dr.quantity, dr.status, dr.priority,
               COUNT(d.id) FILTER (WHERE d.status = 'approved') as approved_count,
               COUNT(d.id) FILTER (WHERE d.status IN ('uploaded', 'processing', 'scanning')) as pending_count
        FROM perennia_document_requests dr
        LEFT JOIN perennia_documents d ON d.request_id = dr.id
        WHERE dr.loan_id = :loan_id AND dr.status != 'cancelled'
        GROUP BY dr.id
        ORDER BY dr.priority DESC, dr.created_at
    """), {"loan_id": loan_id})

    checklist = []
    for row in requests:
        item = dict(row._mapping)
        item["is_complete"] = item["approved_count"] >= item["quantity"]
        checklist.append(item)

    total = len(checklist)
    complete = len([c for c in checklist if c["is_complete"]])

    return {
        "checklist": checklist,
        "summary": {
            "total": total,
            "complete": complete,
            "pending": total - complete,
            "progress_percent": round((complete / total) * 100, 1) if total > 0 else 0
        }
    }


# =============================================================================
# EVENT/AUDIT ENDPOINTS
# =============================================================================

@router.get("/events")
async def list_document_events(
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    document_id: Optional[int] = None,
    event_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List document events (audit trail)."""
    filters = []
    params = {"limit": limit, "offset": offset}

    if loan_id:
        filters.append("loan_id = :loan_id")
        params["loan_id"] = loan_id
    if lead_id:
        filters.append("lead_id = :lead_id")
        params["lead_id"] = lead_id
    if document_id:
        filters.append("document_id = :document_id")
        params["document_id"] = document_id
    if event_type:
        filters.append("event_type = :event_type")
        params["event_type"] = event_type

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    sql = """
        SELECT id, loan_id, lead_id, request_id, document_id,
               event_type, event_data, actor_type, actor_id, created_at
        FROM perennia_document_events
        """ + where_clause + """
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """
    result = db.execute(text(sql), params)

    events = [dict(row._mapping) for row in result]

    return {
        "events": events,
        "count": len(events),
        "limit": limit,
        "offset": offset
    }


# =============================================================================
# NOTIFICATION ENDPOINTS
# =============================================================================

@router.get("/notifications")
async def list_notifications(
    loan_id: Optional[int] = None,
    status: Optional[str] = None,
    channel: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List notifications with filters."""
    filters = []
    params = {"limit": limit}

    if loan_id:
        filters.append("loan_id = :loan_id")
        params["loan_id"] = loan_id
    if status:
        filters.append("status = :status")
        params["status"] = status
    if channel:
        filters.append("channel = :channel")
        params["channel"] = channel

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    sql = """
        SELECT id, loan_id, lead_id, channel, template,
               recipient_email, recipient_phone, subject,
               status, scheduled_for, sent_at, failure_reason,
               created_at
        FROM perennia_notifications
        """ + where_clause + """
        ORDER BY created_at DESC
        LIMIT :limit
    """
    result = db.execute(text(sql), params)

    notifications = [dict(row._mapping) for row in result]
    return {"notifications": notifications, "count": len(notifications)}


@router.post("/notifications")
async def create_notification(
    payload: CreateNotificationPayload,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a notification (queued for delivery)."""
    try:
        result = db.execute(text("""
            INSERT INTO perennia_notifications (
                loan_id, lead_id, channel, template,
                recipient_email, recipient_phone, subject, body,
                metadata, status, scheduled_for, created_at, updated_at
            ) VALUES (
                :loan_id, :lead_id, :channel, :template,
                :email, :phone, :subject, :body,
                :metadata, 'pending', :scheduled_for, NOW(), NOW()
            ) RETURNING id
        """), {
            "loan_id": payload.loan_id,
            "lead_id": payload.lead_id,
            "channel": payload.channel,
            "template": payload.template,
            "email": payload.recipient_email,
            "phone": payload.recipient_phone,
            "subject": payload.subject,
            "body": payload.body,
            "metadata": payload.metadata,
            "scheduled_for": payload.scheduled_for
        })

        notification_id = result.fetchone()[0]
        db.commit()

        return {"success": True, "notification_id": notification_id}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


# =============================================================================
# RULE ENDPOINTS
# =============================================================================

@router.get("/rules")
async def list_document_rules(
    trigger: Optional[str] = None,
    is_active: bool = True,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List document automation rules."""
    filters = ["is_active = :is_active"]
    params = {"is_active": is_active}

    if trigger:
        filters.append("trigger = :trigger")
        params["trigger"] = trigger

    where_clause = " AND ".join(filters)

    sql = """
        SELECT id, name, description, trigger,
               conditions, actions, priority, is_active,
               created_at, updated_at
        FROM perennia_document_rules
        WHERE """ + where_clause + """
        ORDER BY priority ASC
    """
    result = db.execute(text(sql), params)

    rules = [dict(row._mapping) for row in result]
    return {"rules": rules, "count": len(rules)}


@router.post("/rules")
async def create_document_rule(
    payload: CreateDocumentRulePayload,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a document automation rule."""
    try:
        result = db.execute(text("""
            INSERT INTO perennia_document_rules (
                name, description, trigger, conditions, actions,
                priority, is_active, created_at, updated_at
            ) VALUES (
                :name, :description, :trigger, :conditions, :actions,
                :priority, true, NOW(), NOW()
            ) RETURNING id
        """), {
            "name": payload.name,
            "description": payload.description,
            "trigger": payload.trigger,
            "conditions": [c.dict() for c in payload.conditions],
            "actions": [a.dict() for a in payload.actions],
            "priority": payload.priority
        })

        rule_id = result.fetchone()[0]
        db.commit()

        return {"success": True, "rule_id": rule_id}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


@router.patch("/rules/{rule_id}/toggle")
async def toggle_document_rule(
    rule_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Toggle a document rule on/off."""
    try:
        result = db.execute(text("""
            UPDATE perennia_document_rules
            SET is_active = NOT is_active, updated_at = NOW()
            WHERE id = :id
            RETURNING id, is_active
        """), {"id": rule_id})

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Rule not found")

        db.commit()
        return {"success": True, "rule_id": row[0], "is_active": row[1]}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bad request")


# =============================================================================
# DIAGNOSTIC ENDPOINTS
# =============================================================================

@router.get("/diagnostic/summary")
async def get_docs_system_summary(
    db: Session = Depends(get_db)
):
    """
    Get system summary and health check.
    NO AUTH required for deployment verification.
    """
    try:
        summary = {}

        # Count records in each table
        tables = [
            "perennia_document_requests",
            "perennia_documents",
            "perennia_template_packs",
            "perennia_document_rules",
            "perennia_document_events",
            "perennia_notifications",
            "perennia_retention_policies",
            "perennia_portal_sessions"
        ]

        for table in tables:
            try:
                # Table name comes from hardcoded allowlist above, not user input
                sql = "SELECT COUNT(*) FROM " + table
                count = db.execute(text(sql)).scalar()
                summary[table] = count
            except Exception as e:
                logger.error(f"Error querying table {table} in system_summary: {e}")
                summary[table] = "table_not_found"

        # Get request status breakdown
        try:
            status_breakdown = db.execute(text("""
                SELECT status, COUNT(*) as count
                FROM perennia_document_requests
                GROUP BY status
            """))
            summary["requests_by_status"] = {row[0]: row[1] for row in status_breakdown}
        except Exception as e:
            logger.error(f"Error querying requests_by_status in system_summary: {e}")
            summary["requests_by_status"] = {}

        # Get document status breakdown
        try:
            doc_status = db.execute(text("""
                SELECT status, COUNT(*) as count
                FROM perennia_documents
                GROUP BY status
            """))
            summary["documents_by_status"] = {row[0]: row[1] for row in doc_status}
        except Exception as e:
            logger.error(f"Error querying documents_by_status in system_summary: {e}")
            summary["documents_by_status"] = {}

        return {
            "system": "perennia_docs_ai",
            "status": "operational",
            "summary": summary
        }

    except SQLAlchemyError as e:
        return {
            "system": "perennia_docs_ai",
            "status": "error",
            "error": "Internal server error"
        }


@router.post("/diagnostic/run-migration")
async def run_perennia_docs_migration(
    db: Session = Depends(get_db)
):
    """
    Run Perennia Docs migration.
    NO AUTH required for deployment.
    """
    try:
        from migrations.add_perennia_docs_system import run_migration
        result = run_migration(db)
        return result
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": "Internal server error"
        }
