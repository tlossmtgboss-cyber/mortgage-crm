"""
PURL (Persistent URL) API Routes
Perennia AI - Mortgage CRM

Provides API endpoints for the PURL borrower portal system:
- Public endpoints (PURL token auth): workspace access, applications, documents, timeline
- Internal endpoints (user auth): workspace management, token management
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Path, UploadFile, File, Form, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db

# Use TYPE_CHECKING to avoid circular import - User is only needed for type hints
if TYPE_CHECKING:
    from main import User
from sqlalchemy.exc import SQLAlchemyError

# Lazy import wrapper for get_current_user to avoid circular import
# This function returns a dependency that can be used with Depends()
def get_authenticated_user():
    """
    Lazy import wrapper for get_current_user to avoid circular import.
    Returns the get_current_user dependency from main module.
    """
    from main import get_current_user
    return get_current_user

# Models and schemas
from models.purl import (
    PURLWorkspace,
    PURLContact,
    PURLAccessToken,
    PURLApplication,
    PURLLoan,
    PURLDocument,
    PURLTask,
    PURLMessage,
    PURLAuditLog,
    WorkspaceStatus,
    TokenScope,
    ApplicationStatus,
    TaskStatus,
    MessageType,
    # Pydantic schemas
    WorkspaceCreate,
    WorkspaceResponse,
    ContactCreate,
    ContactResponse,
    TokenCreate,
    TokenResponse,
    ApplicationUpdate,
    ApplicationResponse,
    DocumentResponse,
    TaskResponse,
    TaskUpdate,
    MessageCreate,
    MessageResponse,
    MilestoneResponse,
)

# Services
from services.purl_workspace_service import PURLWorkspaceService
from services.purl_token_service import PURLTokenService
from services.purl_application_service import PURLApplicationService
from services.purl_document_service import PURLDocumentService
from services.purl_timeline_service import PURLTimelineService

# Middleware
from middleware.purl_auth import (
    PURLAuthContext,
    require_purl_token,
    require_purl_write_scope,
    require_purl_full_scope,
    get_purl_context_optional,
    get_purl_token,
    verify_workspace_access,
    log_purl_action,
    check_purl_rate_limit,
)


logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_user_org_id(user) -> int:
    """
    Get user's organization_id, defaulting to 1 if NULL.
    This handles cases where users don't have an explicit organization assigned.
    """
    return user.organization_id if user.organization_id else 1


# =============================================================================
# AUTO-CREATE LEAD_CONDITIONS TABLE IF NOT EXISTS
# =============================================================================

def ensure_lead_conditions_table():
    """Ensure the lead_conditions table exists in the database."""
    from database import get_db
    from sqlalchemy import text

    try:
        db = next(get_db())
        # Check if table exists
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'lead_conditions'
            )
        """))
        exists = result.scalar()

        if not exists:
            logger.info("Creating lead_conditions table...")
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS lead_conditions (
                    id SERIAL PRIMARY KEY,
                    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    category VARCHAR(100) DEFAULT 'other',
                    priority VARCHAR(50) DEFAULT 'required',
                    due_date DATE,
                    status VARCHAR(50) DEFAULT 'pending',
                    is_new BOOLEAN DEFAULT true,
                    created_by_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_lead_conditions_lead_id ON lead_conditions(lead_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_lead_conditions_status ON lead_conditions(status)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_lead_conditions_category ON lead_conditions(category)"))
            db.commit()
            logger.info("✅ lead_conditions table created successfully")
        else:
            logger.debug("lead_conditions table already exists")
        db.close()
    except SQLAlchemyError as e:
        logger.warning(f"Could not auto-create lead_conditions table: {e}")

# Run table creation check on module load
try:
    ensure_lead_conditions_table()
except SQLAlchemyError as e:
    logger.warning(f"Error during lead_conditions table check: {e}")

# =============================================================================
# ROUTERS
# =============================================================================

# Public PURL router (token-based auth)
purl_router = APIRouter(prefix="/api/purl", tags=["PURL Portal"])

# Internal PURL management router (user auth)
purl_admin_router = APIRouter(prefix="/api/v1/purl-admin", tags=["PURL Administration"])


# =============================================================================
# HEALTH CHECK (no auth required for debugging)
# =============================================================================

@purl_admin_router.get("/health", summary="PURL Admin Health Check")
async def purl_admin_health():
    """
    Health check endpoint for PURL admin routes.
    Returns status information for debugging connection issues.
    """
    return {
        "status": "ok",
        "service": "purl-admin",
        "routes_loaded": True,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class StandardResponse(BaseModel):
    """Standard API response."""
    success: bool = True
    message: str = ""


class WorkspaceDataResponse(BaseModel):
    """Complete workspace data for borrower portal."""
    workspace: Dict[str, Any]
    contacts: List[Dict[str, Any]]
    application: Optional[Dict[str, Any]] = None
    loan: Optional[Dict[str, Any]] = None
    lead: Optional[Dict[str, Any]] = None  # Linked CRM lead data for milestone sync
    loanOfficer: Optional[Dict[str, Any]] = None  # Loan officer info for portal display
    documents: List[Dict[str, Any]] = []
    document_requirements: List[Dict[str, Any]] = []  # Smart Docs needs list
    tasks: List[Dict[str, Any]] = []
    milestones: List[Dict[str, Any]] = []
    timeline: List[Dict[str, Any]] = []
    modules: List[Dict[str, Any]] = []
    unread_messages_count: int = 0


class UploadUrlResponse(BaseModel):
    """Presigned upload URL response."""
    upload_url: str
    document_key: str
    expires_in: int = 3600


class ApplicationSaveResponse(BaseModel):
    """Application save response."""
    id: int
    version: int
    updated_at: Optional[str] = None
    completeness_pct: int
    validation_errors: List[str] = []


class ApplicationSubmitResponse(BaseModel):
    """Application submission response."""
    application_id: int
    loan_id: int
    submitted_at: str
    portal_url: Optional[str] = None


# =============================================================================
# PUBLIC PURL ENDPOINTS - Workspace Access
# =============================================================================

@purl_router.get(
    "/workspace/{slug}",
    response_model=WorkspaceDataResponse,
    summary="Get workspace data",
    description="Get complete workspace data for borrower portal"
)
async def get_workspace_data(
    slug: str = Path(..., description="Workspace slug"),
    context: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db)
):
    """
    Get complete workspace data for the borrower portal.

    Returns workspace info, contacts, application status, documents,
    tasks, milestones, and timeline events.
    """
    import traceback

    try:
        # Verify access to this workspace
        verify_workspace_access(context, slug)

        service = PURLWorkspaceService(db)
        data = service.get_complete_workspace_data(context.organization_id, context.workspace_id)

        if not data:
            raise HTTPException(status_code=404, detail="Workspace not found")

        logger.info(f"get_workspace_data: Successfully built response for {slug}")
        return WorkspaceDataResponse(**data)
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        logger.error(f"get_workspace_data failed for {slug}: {e}\n{error_tb}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get workspace data"
        )


@purl_router.get(
    "/workspace/{slug}/status",
    summary="Get workspace status",
    description="Get current workspace status and high-level summary"
)
async def get_workspace_status(
    slug: str = Path(..., description="Workspace slug"),
    context: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db)
):
    """Get workspace status summary."""
    verify_workspace_access(context, slug)

    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == context.workspace_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return {
        "workspace_id": workspace.id,
        "slug": workspace.slug,
        "status": workspace.status,
        "updated_at": workspace.updated_at.isoformat() if workspace.updated_at else None
    }


# =============================================================================
# PUBLIC PURL ENDPOINTS - Application
# =============================================================================

@purl_router.get(
    "/workspace/{slug}/application",
    summary="Get current application",
    description="Get the current loan application for this workspace"
)
async def get_application(
    slug: str = Path(..., description="Workspace slug"),
    context: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db)
):
    """Get current application data."""
    verify_workspace_access(context, slug)

    service = PURLApplicationService(db)
    # Include submitted applications so users can view their submitted application
    application = service.get_workspace_application(context.workspace_id, include_submitted=True)

    if not application:
        return {"application": None, "message": "No application started"}

    return {
        "application": {
            "id": application.id,
            "status": application.status,
            "version": application.version,
            "data": application.data,
            "derived": application.derived,
            "completeness_pct": application.completeness_pct,
            "validation_errors": application.validation_errors,
            "started_at": application.started_at.isoformat() if application.started_at else None,
            "submitted_at": application.submitted_at.isoformat() if application.submitted_at else None
        }
    }


@purl_router.post(
    "/workspace/{slug}/application",
    response_model=ApplicationSaveResponse,
    summary="Save application data",
    description="Save partial application data (auto-save)"
)
async def save_application(
    slug: str = Path(..., description="Workspace slug"),
    data: Dict[str, Any] = None,
    context: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db)
):
    """
    Save application data (partial save).

    Creates a new application if none exists.
    Merges provided data with existing data.
    Calculates completeness and validation.
    """
    verify_workspace_access(context, slug)

    if not data:
        raise HTTPException(status_code=400, detail="No data provided")

    service = PURLApplicationService(db)
    result = service.save_application(
        organization_id=context.organization_id,
        workspace_id=context.workspace_id,
        data=data
    )

    # Log the action
    await log_purl_action(
        db=db,
        context=context,
        action="application_save",
        resource_type="application",
        resource_id=result["id"],
        metadata={"completeness_pct": result["completeness_pct"]}
    )

    return ApplicationSaveResponse(**result)


@purl_router.post(
    "/workspace/{slug}/application/submit",
    response_model=ApplicationSubmitResponse,
    summary="Submit application",
    description="Submit completed application for processing"
)
async def submit_application(
    slug: str = Path(..., description="Workspace slug"),
    context: PURLAuthContext = Depends(require_purl_write_scope),
    token: Optional[str] = Depends(get_purl_token),
    db: Session = Depends(get_db)
):
    """
    Submit the completed application.

    Validates all required fields are present.
    Creates a loan record.
    Initializes loan workflow (milestones, tasks).
    Returns portal_url for redirect after submission.
    """
    verify_workspace_access(context, slug)

    service = PURLApplicationService(db)

    try:
        result = service.submit_application(
            organization_id=context.organization_id,
            workspace_id=context.workspace_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")

    # Construct portal URL with the same token used for submission
    base_domain = os.getenv("PURL_BASE_DOMAIN", "perenniaai.com")
    portal_url = f"https://{base_domain}/portal/{context.workspace_slug}"
    if token:
        portal_url = f"{portal_url}?token={token}"

    result["portal_url"] = portal_url

    # Log the action
    await log_purl_action(
        db=db,
        context=context,
        action="application_submit",
        resource_type="application",
        resource_id=result["application_id"],
        metadata={"loan_id": result["loan_id"]}
    )

    return ApplicationSubmitResponse(**result)


# =============================================================================
# PUBLIC PURL ENDPOINTS - Documents
# =============================================================================

@purl_router.get(
    "/workspace/{slug}/documents",
    summary="List documents",
    description="Get all documents for this workspace"
)
async def list_documents(
    slug: str = Path(..., description="Workspace slug"),
    category: Optional[str] = Query(None, description="Filter by category"),
    context: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db)
):
    """List all documents for the workspace."""
    verify_workspace_access(context, slug)

    query = db.query(PURLDocument).filter(
        PURLDocument.workspace_id == context.workspace_id
    )

    if category:
        query = query.filter(PURLDocument.doc_category == category)

    documents = query.order_by(PURLDocument.created_at.desc()).all()

    return {
        "documents": [
            {
                "id": doc.id,
                "filename": doc.file_name,
                "document_type": doc.doc_type,
                "category": doc.doc_category,
                "status": doc.status,
                "file_size": doc.size_bytes,
                "uploaded_at": doc.created_at.isoformat() if doc.created_at else None
            }
            for doc in documents
        ]
    }


@purl_router.post(
    "/workspace/{slug}/documents/upload-url",
    response_model=UploadUrlResponse,
    summary="Get upload URL",
    description="Get presigned URL for document upload"
)
async def get_upload_url(
    slug: str = Path(..., description="Workspace slug"),
    filename: str = Query(..., description="Original filename"),
    content_type: str = Query(..., description="MIME type"),
    document_type: Optional[str] = Query(None, description="Document type (paystub, w2, etc.)"),
    context: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db)
):
    """
    Get a presigned URL for uploading a document.

    The client uploads directly to S3 using this URL,
    then calls the upload-complete endpoint.
    """
    verify_workspace_access(context, slug)

    service = PURLDocumentService(db)

    try:
        result = service.generate_upload_url(
            organization_id=context.organization_id,
            workspace_id=context.workspace_id,
            filename=filename,
            content_type=content_type,
            document_type=document_type
        )
    except Exception as e:
        logger.error(f"Failed to generate upload URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate upload URL")

    return UploadUrlResponse(**result)


@purl_router.post(
    "/workspace/{slug}/documents/upload-complete",
    summary="Complete document upload",
    description="Register uploaded document after S3 upload completes"
)
async def complete_document_upload(
    slug: str = Path(..., description="Workspace slug"),
    document_key: str = Query(..., description="S3 document key from upload-url"),
    filename: str = Query(..., description="Original filename"),
    file_size: int = Query(..., description="File size in bytes"),
    content_type: str = Query(..., description="MIME type"),
    document_type: Optional[str] = Query(None, description="Document type"),
    context: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db)
):
    """
    Complete the document upload process.

    Called after the client successfully uploads to S3.
    Creates the document record in the database.
    """
    verify_workspace_access(context, slug)

    service = PURLDocumentService(db)

    document = service.complete_upload(
        organization_id=context.organization_id,
        workspace_id=context.workspace_id,
        document_key=document_key,
        filename=filename,
        file_size=file_size,
        content_type=content_type,
        document_type=document_type,
        uploaded_by_contact_id=context.contact_id
    )

    # Log the action
    await log_purl_action(
        db=db,
        context=context,
        action="document_upload",
        resource_type="document",
        resource_id=document.id,
        metadata={"filename": filename, "document_type": document_type}
    )

    return {
        "success": True,
        "document": {
            "id": document.id,
            "filename": document.file_name,
            "document_type": document.doc_type,
            "category": document.doc_category,
            "status": document.status
        }
    }


@purl_router.post(
    "/workspace/{slug}/documents/upload-direct",
    summary="Direct document upload",
    description="Upload document directly to server (fallback when S3 unavailable)"
)
async def upload_document_direct(
    slug: str = Path(..., description="Workspace slug"),
    file: UploadFile = File(..., description="Document file"),
    document_type: Optional[str] = Form(None, description="Document type"),
    context: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db)
):
    """
    Direct document upload endpoint.

    This is a fallback for when S3 presigned URLs don't work.
    Stores documents in local storage or S3 directly.
    """
    import os
    import uuid
    from pathlib import Path as FilePath

    verify_workspace_access(context, slug)

    # Create storage directory if needed
    storage_dir = FilePath(os.getenv("LOCAL_UPLOAD_PATH", "uploads"))
    doc_dir = storage_dir / "org" / str(context.organization_id) / "workspaces" / str(context.workspace_id) / "documents"
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    upload_id = uuid.uuid4().hex
    safe_filename = "".join(c for c in file.filename if c.isalnum() or c in "._- ")[:200]
    storage_key = f"org/{context.organization_id}/workspaces/{context.workspace_id}/documents/{upload_id}/{safe_filename}"

    # Save file locally
    file_path = doc_dir / f"{upload_id}_{safe_filename}"
    content = await file.read()
    file_size = len(content)

    with open(file_path, "wb") as f:
        f.write(content)

    logger.info(f"Saved document locally: {file_path}")

    # Create document record
    service = PURLDocumentService(db)
    document = service.complete_upload(
        organization_id=context.organization_id,
        workspace_id=context.workspace_id,
        document_key=storage_key,
        filename=file.filename,
        file_size=file_size,
        content_type=file.content_type or "application/octet-stream",
        document_type=document_type,
        uploaded_by_contact_id=context.contact_id
    )

    # Log the action
    await log_purl_action(
        db=db,
        context=context,
        action="document_upload",
        resource_type="document",
        resource_id=document.id,
        metadata={"filename": file.filename, "document_type": document_type, "upload_method": "direct"}
    )

    return {
        "success": True,
        "document": {
            "id": document.id,
            "filename": document.file_name,
            "document_type": document.doc_type,
            "category": document.doc_category,
            "status": document.status
        }
    }


@purl_router.get(
    "/workspace/{slug}/documents/{document_id}/download-url",
    summary="Get download URL",
    description="Get presigned URL for document download"
)
async def get_download_url(
    slug: str = Path(..., description="Workspace slug"),
    document_id: int = Path(..., description="Document ID"),
    context: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db)
):
    """Get presigned URL for downloading a document."""
    verify_workspace_access(context, slug)

    # Verify document belongs to workspace
    document = db.query(PURLDocument).filter(
        PURLDocument.id == document_id,
        PURLDocument.workspace_id == context.workspace_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    service = PURLDocumentService(db)

    try:
        url = service.generate_download_url(document.s3_key)
    except SQLAlchemyError as e:
        logger.error(f"Failed to generate download URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate download URL")

    return {
        "download_url": url,
        "filename": document.filename,
        "expires_in": 3600
    }


# =============================================================================
# PUBLIC PURL ENDPOINTS - Tasks
# =============================================================================

@purl_router.get(
    "/workspace/{slug}/tasks",
    summary="List tasks",
    description="Get borrower tasks for this workspace"
)
async def list_tasks(
    slug: str = Path(..., description="Workspace slug"),
    status: Optional[str] = Query(None, description="Filter by status"),
    context: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db)
):
    """List all borrower tasks."""
    verify_workspace_access(context, slug)

    service = PURLTimelineService(db)
    tasks = service.get_borrower_tasks(
        organization_id=context.organization_id,
        workspace_id=context.workspace_id,
        include_completed=(status == "completed") if status else False
    )

    return {"tasks": tasks}


@purl_router.patch(
    "/workspace/{slug}/tasks/{task_id}",
    summary="Update task",
    description="Update task status or add notes"
)
async def update_task(
    slug: str = Path(..., description="Workspace slug"),
    task_id: int = Path(..., description="Task ID"),
    update: TaskUpdate = None,
    context: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db)
):
    """Update a borrower task."""
    verify_workspace_access(context, slug)

    # Verify task belongs to workspace
    task = db.query(PURLTask).filter(
        PURLTask.id == task_id,
        PURLTask.workspace_id == context.workspace_id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    service = PURLTimelineService(db)
    updated_task = service.update_task(task_id, update.dict(exclude_unset=True))

    # Log the action
    await log_purl_action(
        db=db,
        context=context,
        action="task_update",
        resource_type="task",
        resource_id=task_id,
        changes=update.dict(exclude_unset=True)
    )

    return {"success": True, "task": updated_task}


# =============================================================================
# PUBLIC PURL ENDPOINTS - Conditions (Needs List)
# =============================================================================

@purl_router.get(
    "/workspace/{slug}/conditions",
    summary="List conditions",
    description="Get conditions/needs list for this workspace (documents needed from borrower)"
)
async def list_conditions(
    slug: str = Path(..., description="Workspace slug"),
    status: Optional[str] = Query(None, description="Filter by status (pending, received, approved, waived)"),
    context: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db)
):
    """List all conditions (needs list items) for the workspace."""
    from sqlalchemy import text

    verify_workspace_access(context, slug)

    # Get the workspace to find the lead_id
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == context.workspace_id
    ).first()

    # Extract lead_id from meta_data (not a direct column on PURLWorkspace)
    # Note: lead_id is stored as a string in meta_data but needs to be int for DB queries
    lead_id = None
    if workspace and workspace.meta_data:
        lead_id_str = workspace.meta_data.get('lead_id')
        if lead_id_str:
            try:
                lead_id = int(lead_id_str)
            except (ValueError, TypeError):
                lead_id = None

    if not workspace or not lead_id:
        return {"conditions": [], "message": "No lead associated with workspace"}

    # Build query for lead_conditions
    query = """
        SELECT
            id, lead_id, name, description, category, priority,
            due_date, status, is_new, created_at, updated_at
        FROM lead_conditions
        WHERE lead_id = :lead_id
    """
    params = {"lead_id": lead_id}

    if status:
        query += " AND status = :status"
        params["status"] = status

    query += " ORDER BY CASE WHEN status = 'pending' THEN 0 WHEN status = 'received' THEN 1 WHEN status = 'approved' THEN 2 ELSE 3 END, created_at DESC"

    try:
        result = db.execute(text(query), params)
        rows = result.fetchall()

        conditions = []
        for row in rows:
            # Handle dates - SQLite returns strings, PostgreSQL returns datetime objects
            def format_date(val):
                if val is None:
                    return None
                if hasattr(val, 'isoformat'):
                    return val.isoformat()
                return str(val)  # Already a string from SQLite

            conditions.append({
                "id": row.id,
                "lead_id": row.lead_id,
                "name": row.name,
                "description": row.description,
                "category": row.category,
                "priority": row.priority,
                "due_date": format_date(row.due_date),
                "status": row.status,
                "is_new": row.is_new,
                "created_at": format_date(row.created_at),
                "updated_at": format_date(row.updated_at),
            })

        return {
            "conditions": conditions,
            "total": len(conditions),
            "pending_count": len([c for c in conditions if c["status"] == "pending"]),
            "received_count": len([c for c in conditions if c["status"] == "received"]),
            "approved_count": len([c for c in conditions if c["status"] == "approved"]),
        }
    except Exception as e:
        logger.error(f"Failed to fetch conditions: {e}")
        return {"conditions": [], "message": "Failed to fetch conditions", "error": "Internal server error"}


@purl_router.patch(
    "/workspace/{slug}/conditions/{condition_id}/mark-received",
    summary="Mark condition as received",
    description="Mark a condition as received when borrower uploads documents"
)
async def mark_condition_received(
    slug: str = Path(..., description="Workspace slug"),
    condition_id: int = Path(..., description="Condition ID"),
    context: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db)
):
    """Mark a condition as received (borrower uploaded documents)."""
    from sqlalchemy import text

    verify_workspace_access(context, slug)

    # Get the workspace to find the lead_id
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == context.workspace_id
    ).first()

    # Extract lead_id from meta_data (not a direct column on PURLWorkspace)
    # Note: lead_id is stored as a string in meta_data but needs to be int for DB queries
    lead_id = None
    if workspace and workspace.meta_data:
        lead_id_str = workspace.meta_data.get('lead_id')
        if lead_id_str:
            try:
                lead_id = int(lead_id_str)
            except (ValueError, TypeError):
                lead_id = None

    if not workspace or not lead_id:
        raise HTTPException(status_code=404, detail="No lead associated with workspace")

    # Update the condition
    try:
        result = db.execute(
            text("""
                UPDATE lead_conditions
                SET status = 'received', is_new = false, updated_at = NOW()
                WHERE id = :condition_id AND lead_id = :lead_id
                RETURNING id, name, status
            """),
            {"condition_id": condition_id, "lead_id": lead_id}
        )
        row = result.fetchone()
        db.commit()

        if not row:
            raise HTTPException(status_code=404, detail="Condition not found")

        # Log the action
        await log_purl_action(
            db=db,
            context=context,
            action="condition_received",
            resource_type="condition",
            resource_id=condition_id,
            changes={"status": "received"}
        )

        return {"success": True, "condition_id": row.id, "name": row.name, "status": row.status}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update condition: {e}")
        raise HTTPException(status_code=500, detail="Failed to update condition")


# =============================================================================
# PUBLIC PURL ENDPOINTS - Timeline & Milestones
# =============================================================================

@purl_router.get(
    "/workspace/{slug}/timeline",
    summary="Get timeline",
    description="Get timeline of events and activities"
)
async def get_timeline(
    slug: str = Path(..., description="Workspace slug"),
    limit: int = Query(50, ge=1, le=200, description="Max events to return"),
    context: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db)
):
    """Get timeline of events for the workspace."""
    verify_workspace_access(context, slug)

    service = PURLTimelineService(db)
    result = service.get_workspace_timeline(
        organization_id=context.organization_id,
        workspace_id=context.workspace_id
    )

    return {"timeline": result.get("events", [])[:limit]}


@purl_router.get(
    "/workspace/{slug}/milestones",
    summary="Get milestones",
    description="Get loan milestones and progress"
)
async def get_milestones(
    slug: str = Path(..., description="Workspace slug"),
    context: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db)
):
    """Get loan milestones and current status."""
    verify_workspace_access(context, slug)

    service = PURLTimelineService(db)
    result = service.get_workspace_timeline(
        organization_id=context.organization_id,
        workspace_id=context.workspace_id
    )

    milestones = result.get("milestones", [])
    loan_status = result.get("loan_status")

    if not milestones:
        return {"milestones": [], "message": "No active loan"}

    return {"milestones": milestones, "loan_status": loan_status}


# =============================================================================
# PUBLIC PURL ENDPOINTS - Messages
# =============================================================================

@purl_router.get(
    "/workspace/{slug}/messages",
    summary="List messages",
    description="Get messages for this workspace"
)
async def list_messages(
    slug: str = Path(..., description="Workspace slug"),
    limit: int = Query(50, ge=1, le=200, description="Max messages"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    context: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db)
):
    """List messages for the workspace."""
    verify_workspace_access(context, slug)

    messages = db.query(PURLMessage).filter(
        PURLMessage.workspace_id == context.workspace_id
    ).order_by(PURLMessage.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "messages": [
            {
                "id": msg.id,
                "message_type": msg.message_type,
                "sender_type": msg.sender_type,
                "content": msg.content,
                "is_read": msg.is_read_by_borrower,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            }
            for msg in messages
        ]
    }


@purl_router.post(
    "/workspace/{slug}/messages",
    summary="Send message",
    description="Send a message to the loan team"
)
async def send_message(
    slug: str = Path(..., description="Workspace slug"),
    message: MessageCreate = None,
    context: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db)
):
    """Send a message to the loan team."""
    verify_workspace_access(context, slug)

    new_message = PURLMessage(
        organization_id=context.organization_id,
        workspace_id=context.workspace_id,
        message_type=message.message_type.value if hasattr(message.message_type, 'value') else MessageType.TEXT.value,
        content=message.content,
        sender_type="contact",
        sender_contact_id=context.contact_id
    )

    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    # Log the action
    await log_purl_action(
        db=db,
        context=context,
        action="message_send",
        resource_type="message",
        resource_id=new_message.id
    )

    return {
        "success": True,
        "message": {
            "id": new_message.id,
            "created_at": new_message.created_at.isoformat()
        }
    }


@purl_router.patch(
    "/workspace/{slug}/messages/{message_id}/read",
    summary="Mark message read",
    description="Mark a message as read"
)
async def mark_message_read(
    slug: str = Path(..., description="Workspace slug"),
    message_id: int = Path(..., description="Message ID"),
    context: PURLAuthContext = Depends(require_purl_token),
    db: Session = Depends(get_db)
):
    """Mark a message as read."""
    verify_workspace_access(context, slug)

    message = db.query(PURLMessage).filter(
        PURLMessage.id == message_id,
        PURLMessage.workspace_id == context.workspace_id
    ).first()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    message.is_read_by_borrower = True
    message.read_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True}


# =============================================================================
# INTERNAL ADMIN ENDPOINTS - Lead/Contact Search
# =============================================================================

@purl_admin_router.get(
    "/contacts/search",
    summary="Search leads/contacts by name",
    description="Search for leads by name to create a workspace"
)
async def search_contacts_for_workspace(
    q: str = Query(..., min_length=1, description="Search query (name)"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """
    Search leads by name for workspace creation.
    Returns leads that match the search query along with their existing workspace status.
    """
    from main import Lead
    from sqlalchemy import or_, cast, String

    search_term = f"%{q}%"
    org_id = get_user_org_id(current_user)

    # Search leads by name (full name or first/last name) with tenant isolation
    query = db.query(Lead).filter(
        Lead.owner_id == current_user.id,
        or_(
            Lead.name.ilike(search_term),
            Lead.first_name.ilike(search_term),
            Lead.last_name.ilike(search_term),
            (Lead.first_name + " " + Lead.last_name).ilike(search_term)
        )
    )
    # Defense in depth: also filter by organization
    if org_id:
        query = query.filter(Lead.organization_id == org_id)

    leads = query.order_by(Lead.name).limit(limit).all()

    # Check which leads already have workspaces
    lead_ids = [str(lead.id) for lead in leads]
    existing_workspaces = {}

    if lead_ids:
        # Find workspaces that have these lead_ids in their metadata
        org_id = get_user_org_id(current_user)
        workspaces_with_leads = db.query(PURLWorkspace).filter(
            PURLWorkspace.organization_id == org_id,
            PURLWorkspace.meta_data['lead_id'].astext.in_(lead_ids)
        ).all()

        for ws in workspaces_with_leads:
            lead_id = ws.meta_data.get('lead_id')
            if lead_id:
                existing_workspaces[str(lead_id)] = {
                    "workspace_id": ws.id,
                    "workspace_slug": ws.slug,
                    "status": ws.status
                }

    return {
        "contacts": [
            {
                "id": lead.id,
                "name": lead.name,
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "email": lead.email,
                "phone": lead.phone,
                "stage": lead.stage.value if lead.stage else None,
                "has_workspace": str(lead.id) in existing_workspaces,
                "existing_workspace": existing_workspaces.get(str(lead.id))
            }
            for lead in leads
        ],
        "total": len(leads)
    }


# =============================================================================
# INTERNAL ADMIN ENDPOINTS - Workspace Management
# =============================================================================

class WorkspaceCreateRequest(BaseModel):
    """Extended workspace creation request with lead linking."""
    lead_id: Optional[int] = Field(None, description="Lead ID to link to this workspace")
    borrower_name: Optional[str] = Field(None, description="Borrower name (required if no lead_id)")
    first_name: Optional[str] = Field(None, description="Borrower first name")
    last_name: Optional[str] = Field(None, description="Borrower last name")
    email: Optional[str] = Field(None, description="Borrower email")
    phone: Optional[str] = Field(None, description="Borrower phone")
    loan_id: Optional[int] = Field(None, description="Optional loan ID to link")
    custom_slug: Optional[str] = Field(None, description="Custom workspace slug")


@purl_admin_router.post(
    "/workspaces",
    summary="Create workspace",
    description="Create a new PURL workspace"
)
async def create_workspace(
    request: WorkspaceCreateRequest,
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Create a new PURL workspace with duplicate prevention."""
    from main import Lead

    org_id = get_user_org_id(current_user)

    # Get lead if lead_id provided
    lead = None
    if request.lead_id:
        # First try to find lead owned by current user
        lead = db.query(Lead).filter(
            Lead.id == request.lead_id,
            Lead.owner_id == current_user.id
        ).first()

        # If not found, try to find lead within the same organization
        if not lead:
            lead = db.query(Lead).filter(
                Lead.id == request.lead_id,
                Lead.organization_id == org_id
            ).first()

        # Check for existing workspace for this lead/loan (even if lead not found)
        existing = db.query(PURLWorkspace).filter(
            PURLWorkspace.organization_id == org_id,
            PURLWorkspace.meta_data['lead_id'].astext == str(request.lead_id)
        ).first()

        if not existing and request.loan_id:
            existing = db.query(PURLWorkspace).filter(
                PURLWorkspace.organization_id == org_id,
                PURLWorkspace.meta_data['loan_id'].astext == str(request.loan_id)
            ).first()

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"A client portal already exists for this borrower (workspace: {existing.slug})"
            )

    # Determine display name
    if lead:
        display_name = lead.name or f"{lead.first_name or ''} {lead.last_name or ''}".strip()
    elif request.borrower_name:
        display_name = request.borrower_name
    elif request.first_name or request.last_name:
        display_name = f"{request.first_name or ''} {request.last_name or ''}".strip()
    else:
        raise HTTPException(status_code=400, detail="Borrower name is required")

    # Build metadata with lead/loan linking
    metadata = {}
    if request.lead_id:
        metadata['lead_id'] = str(request.lead_id)
    if request.loan_id:
        metadata['loan_id'] = str(request.loan_id)

    # Extract borrower name components for PURL slug generation (firstname.lastname format)
    borrower_email = lead.email if lead else request.email
    borrower_phone = lead.phone if lead else request.phone
    borrower_first = (lead.first_name if lead else request.first_name) or (display_name.split()[0] if display_name else None)
    borrower_last = (lead.last_name if lead else request.last_name) or (display_name.split()[-1] if len(display_name.split()) > 1 else None)

    # Create workspace using service
    service = PURLWorkspaceService(db)

    workspace_data = WorkspaceCreate(
        display_name=display_name,
        slug=request.custom_slug or None,
        source="purl_manager",
        owner_user_id=current_user.id,
        metadata=metadata
    )

    try:
        result = service.create_workspace(
            organization_id=org_id,
            data=workspace_data,
            owner_user_id=current_user.id,
            first_name=borrower_first,  # For firstname.lastname slug format
            last_name=borrower_last      # For firstname.lastname slug format
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")

    # Add borrower as primary contact

    if borrower_email or borrower_phone:
        contact = PURLContact(
            organization_id=org_id,
            workspace_id=result["id"],
            contact_type="borrower",
            first_name=borrower_first,
            last_name=borrower_last,
            email=borrower_email,
            phone=borrower_phone
        )
        db.add(contact)
        db.commit()

    return {
        "success": True,
        "workspace": result
    }


@purl_admin_router.get(
    "/workspaces",
    summary="List workspaces",
    description="List all PURL workspaces"
)
async def list_workspaces(
    status: Optional[str] = Query(None, description="Filter by status (active, completed, all)"),
    search: Optional[str] = Query(None, description="Search by name or slug"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """List PURL workspaces for the organization."""
    # Handle NULL organization_id - default to 1 (main organization)
    org_id = get_user_org_id(current_user)

    logger.info(f"list_workspaces: user={current_user.email}, org_id={org_id} (user.org_id={current_user.organization_id})")

    query = db.query(PURLWorkspace).filter(
        PURLWorkspace.organization_id == org_id
    )

    # Map frontend filter values to actual workspace statuses
    if status and status != 'all':
        from sqlalchemy import or_
        if status == 'active':
            # Active = any workspace that's not post_close (completed), including NULL status
            active_statuses = [
                WorkspaceStatus.LEAD.value,
                WorkspaceStatus.APPLICATION.value,
                WorkspaceStatus.ACTIVE_LOAN.value,
                WorkspaceStatus.CLOSING.value,
            ]
            query = query.filter(
                or_(
                    PURLWorkspace.status.in_(active_statuses),
                    PURLWorkspace.status.is_(None)  # Include workspaces with NULL status
                )
            )
        elif status == 'completed':
            # Completed = post_close status
            query = query.filter(PURLWorkspace.status == WorkspaceStatus.POST_CLOSE.value)
        else:
            # Allow direct status value filtering as well
            query = query.filter(PURLWorkspace.status == status)

    if search:
        query = query.filter(
            PURLWorkspace.display_name.ilike(f"%{search}%") |
            PURLWorkspace.slug.ilike(f"%{search}%")
        )

    total = query.count()
    workspaces = query.order_by(PURLWorkspace.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "workspaces": [
            {
                "id": ws.id,
                "slug": ws.slug,
                "display_name": ws.display_name,
                "borrower_name": ws.display_name,  # Alias for frontend compatibility
                "status": ws.status or "lead",  # Default to 'lead' if NULL
                "progress": 0,  # Default progress - could be calculated from application completeness
                "created_at": ws.created_at.isoformat() if ws.created_at else None,
                "lead_id": ws.meta_data.get('lead_id') if ws.meta_data else None,
                "loan_id": ws.meta_data.get('loan_id') if ws.meta_data else None,
            }
            for ws in workspaces
        ]
    }


# =============================================================================
# PROFILE INTEGRATION ENDPOINTS (must be before {workspace_id} to avoid route conflicts)
# =============================================================================

@purl_admin_router.get(
    "/workspaces/by-lead/{lead_id}",
    summary="Get workspace by lead ID",
    description="Get workspace and tokens for a specific lead (used by profile widget)"
)
async def get_workspace_by_lead(
    lead_id: str = Path(..., description="Lead ID"),
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Get workspace for a specific lead - used by PURLWidget in profile pages."""
    from sqlalchemy import or_, cast, String

    org_id = get_user_org_id(current_user)

    # Try to find workspace by lead_id in metadata
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.organization_id == org_id,
        or_(
            PURLWorkspace.meta_data['lead_id'].astext == lead_id,
            PURLWorkspace.meta_data['loan_id'].astext == lead_id
        )
    ).first()

    # If not found by metadata, try finding via purl_loans.main_loan_id
    if not workspace:
        purl_loan = db.query(PURLLoan).filter(
            PURLLoan.organization_id == org_id,
            PURLLoan.main_loan_id == int(lead_id) if lead_id.isdigit() else None
        ).first()
        if purl_loan:
            workspace = db.query(PURLWorkspace).filter(
                PURLWorkspace.id == purl_loan.workspace_id
            ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found for this lead")

    # Get workspace stats
    document_count = db.query(PURLDocument).filter(
        PURLDocument.workspace_id == workspace.id
    ).count()

    application = db.query(PURLApplication).filter(
        PURLApplication.workspace_id == workspace.id
    ).order_by(PURLApplication.created_at.desc()).first()

    # Get active tokens
    tokens = db.query(PURLAccessToken).filter(
        PURLAccessToken.workspace_id == workspace.id,
        PURLAccessToken.revoked_at.is_(None)
    ).order_by(PURLAccessToken.created_at.desc()).all()

    # Get last activity
    last_activity = db.query(PURLAuditLog).filter(
        PURLAuditLog.workspace_id == workspace.id
    ).order_by(PURLAuditLog.created_at.desc()).first()

    return {
        "workspace": {
            "workspace_id": workspace.id,
            "workspace_slug": workspace.slug,
            "slug": workspace.slug,
            "display_name": workspace.display_name,
            "status": workspace.status if workspace.status else "lead",
            "document_count": document_count,
            "application_status": application.status if application else None,
            "last_activity": last_activity.created_at.isoformat() if last_activity else None,
            "created_at": workspace.created_at.isoformat() if workspace.created_at else None
        },
        "tokens": [
            {
                "id": token.id,
                "token_prefix": token.token_prefix or "purl_",
                "status": "active" if not token.revoked_at else "revoked",
                "scope": token.scope if token.scope else "read",
                "last_used_at": token.last_used_at.isoformat() if token.last_used_at else None,
                "expires_at": token.expires_at.isoformat() if token.expires_at else None,
                "created_at": token.created_at.isoformat() if token.created_at else None
            }
            for token in tokens
        ]
    }


@purl_admin_router.get(
    "/workspaces/by-loan/{loan_id}",
    summary="Get workspace by loan ID",
    description="Get workspace and tokens for a specific loan (used by profile widget)"
)
async def get_workspace_by_loan(
    loan_id: str = Path(..., description="Loan ID"),
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Get workspace for a specific loan - used by PURLWidget in loan profile pages."""
    # Reuse the lead lookup logic
    return await get_workspace_by_lead(loan_id, current_user, db)


# =============================================================================
# WORKSPACE DETAIL ENDPOINTS
# =============================================================================

@purl_admin_router.get(
    "/workspaces/{workspace_id}",
    summary="Get workspace",
    description="Get workspace details"
)
async def get_workspace(
    workspace_id: int = Path(..., description="Workspace ID"),
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Get workspace details."""
    org_id = get_user_org_id(current_user)

    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    service = PURLWorkspaceService(db)
    return service.get_complete_workspace_data(org_id, workspace_id)


@purl_admin_router.patch(
    "/workspaces/{workspace_id}",
    summary="Update workspace",
    description="Update workspace settings"
)
async def update_workspace(
    workspace_id: int = Path(..., description="Workspace ID"),
    updates: Dict[str, Any] = None,
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Update workspace settings."""
    org_id = get_user_org_id(current_user)

    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Update allowed fields
    allowed_fields = ["display_name", "settings", "status"]
    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    for field, value in (updates or {}).items():
        if field in allowed_fields and hasattr(workspace, field) and field not in _protected:
            setattr(workspace, field, value)

    db.commit()
    db.refresh(workspace)

    return {"success": True, "workspace_id": workspace.id}


# =============================================================================
# INTERNAL ADMIN ENDPOINTS - Token Management
# =============================================================================

@purl_admin_router.post(
    "/workspaces/{workspace_id}/tokens",
    summary="Create access token",
    description="Create a new PURL access token"
)
async def create_token(
    workspace_id: int = Path(..., description="Workspace ID"),
    token_data: TokenCreate = None,
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Create a new access token for a workspace."""
    import os
    import traceback

    try:
        org_id = get_user_org_id(current_user)

        # Verify workspace ownership
        workspace = db.query(PURLWorkspace).filter(
            PURLWorkspace.id == workspace_id,
            PURLWorkspace.organization_id == org_id
        ).first()

        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        service = PURLTokenService(db)

        # Service returns Tuple[token_id, full_token]
        token_id, full_token = service.create_token(
            organization_id=org_id,
            workspace_id=workspace_id,
            scope=token_data.scope if token_data else TokenScope.WRITE,
            contact_id=token_data.contact_id if token_data else None,
            expires_in_days=token_data.expires_in_days if token_data else 365,
            created_by=current_user.id
        )

        # Get the expiry from the token record
        token_record = db.query(PURLAccessToken).filter(PURLAccessToken.id == token_id).first()

        # Build full portal URL with token
        base_domain = os.getenv("PURL_BASE_DOMAIN", "perenniaai.com")
        portal_url = f"https://{base_domain}/portal/{workspace.slug}?token={full_token}"

        return {
            "success": True,
            "token": full_token,  # Only returned once!
            "token_id": token_id,
            "portal_url": portal_url,  # Full URL with token - only returned on creation!
            "workspace_slug": workspace.slug,
            "expires_at": token_record.expires_at.isoformat() if token_record and token_record.expires_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create token: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Token creation failed")


# Temporary endpoint to regenerate token for workspace (remove after use)
@purl_router.post(
    "/admin/regenerate-token/{workspace_id}",
    summary="Regenerate token (temporary)",
    include_in_schema=False
)
async def regenerate_token_temp(
    workspace_id: int = Path(...),
    admin_key: str = Query(..., description="Admin key"),
    db: Session = Depends(get_db)
):
    """Temporary endpoint to regenerate a token for a workspace."""
    import os
    import secrets
    import hashlib
    from datetime import timezone, timedelta

    # Simple admin key check
    expected_key = os.getenv("ADMIN_REGEN_KEY", "temp_regen_key_2024")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # Get workspace
    workspace = db.query(PURLWorkspace).filter(PURLWorkspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Generate new token
    token_raw = secrets.token_hex(32)
    full_token = f"purl_live_{token_raw}"
    token_hash = hashlib.sha256(full_token.encode()).hexdigest()
    token_prefix = full_token[:16]

    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc + timedelta(days=365)

    # Insert token
    from sqlalchemy import text
    result = db.execute(text("""
        INSERT INTO purl_access_tokens (
            organization_id, workspace_id, token_hash, token_prefix,
            scope, status, expires_at, created_at
        ) VALUES (
            :org_id, :workspace_id, :token_hash, :token_prefix,
            'full', 'active', :expires_at, :created_at
        ) RETURNING id
    """), {
        "org_id": workspace.organization_id,
        "workspace_id": workspace_id,
        "token_hash": token_hash,
        "token_prefix": token_prefix,
        "expires_at": expires_at,
        "created_at": now_utc
    })
    token_id = result.scalar()
    db.commit()

    base_domain = os.getenv("PURL_BASE_DOMAIN", "perenniaai.com")
    portal_url = f"https://{base_domain}/portal/{workspace.slug}?token={full_token}"

    logger.info(f"Regenerated token for workspace {workspace_id}: token_id={token_id}")

    return {
        "success": True,
        "token_id": token_id,
        "token": full_token,
        "portal_url": portal_url,
        "workspace_slug": workspace.slug,
        "expires_at": expires_at.isoformat()
    }


@purl_admin_router.get(
    "/workspaces/{workspace_id}/tokens",
    summary="List tokens",
    description="List access tokens for a workspace"
)
async def list_tokens(
    workspace_id: int = Path(..., description="Workspace ID"),
    include_revoked: bool = Query(False, description="Include revoked tokens"),
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """List access tokens for a workspace."""
    org_id = get_user_org_id(current_user)

    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    query = db.query(PURLAccessToken).filter(
        PURLAccessToken.workspace_id == workspace_id
    )

    if not include_revoked:
        query = query.filter(PURLAccessToken.revoked_at.is_(None))

    tokens = query.order_by(PURLAccessToken.created_at.desc()).all()

    return {
        "tokens": [
            {
                "id": t.id,
                "scope": t.scope.value if hasattr(t.scope, 'value') else t.scope,
                "token_prefix": t.token_prefix,
                "expires_at": t.expires_at.isoformat() if t.expires_at else None,
                "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
                "revoked_at": t.revoked_at.isoformat() if t.revoked_at else None,
                "created_at": t.created_at.isoformat() if t.created_at else None
            }
            for t in tokens
        ]
    }


@purl_admin_router.delete(
    "/workspaces/{workspace_id}/tokens/{token_id}",
    summary="Revoke token",
    description="Revoke an access token"
)
async def revoke_token(
    workspace_id: int = Path(..., description="Workspace ID"),
    token_id: int = Path(..., description="Token ID"),
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Revoke an access token."""
    org_id = get_user_org_id(current_user)

    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    service = PURLTokenService(db)
    success = service.revoke_token(token_id)

    if not success:
        raise HTTPException(status_code=404, detail="Token not found")

    return {"success": True}


# =============================================================================
# INTERNAL ADMIN ENDPOINTS - Contact Management
# =============================================================================

@purl_admin_router.post(
    "/workspaces/{workspace_id}/contacts",
    summary="Add contact",
    description="Add a contact to a workspace"
)
async def add_contact(
    workspace_id: int = Path(..., description="Workspace ID"),
    contact: ContactCreate = None,
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Add a contact to a workspace."""
    org_id = get_user_org_id(current_user)

    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    service = PURLWorkspaceService(db)

    try:
        result = service.add_contact(
            organization_id=org_id,
            workspace_id=workspace_id,
            data=contact
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")

    return {"success": True, "contact": result}


@purl_admin_router.get(
    "/workspaces/{workspace_id}/contacts",
    summary="List contacts",
    description="List contacts for a workspace"
)
async def list_contacts(
    workspace_id: int = Path(..., description="Workspace ID"),
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """List contacts for a workspace."""
    org_id = get_user_org_id(current_user)

    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    contacts = db.query(PURLContact).filter(
        PURLContact.workspace_id == workspace_id
    ).all()

    return {
        "contacts": [
            {
                "id": c.id,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "email": c.email,
                "phone": c.phone,
                "contact_type": c.contact_type,
                "is_primary": c.contact_type == "borrower"
            }
            for c in contacts
        ]
    }


# =============================================================================
# INTERNAL ADMIN ENDPOINTS - Document Requests
# =============================================================================

@purl_admin_router.post(
    "/workspaces/{workspace_id}/document-requests",
    summary="Create document request",
    description="Request documents from borrower"
)
async def create_document_request(
    workspace_id: int = Path(..., description="Workspace ID"),
    request_data: Dict[str, Any] = None,
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Create a document request for the borrower."""
    org_id = get_user_org_id(current_user)

    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    service = PURLDocumentService(db)

    result = service.create_document_request(
        organization_id=org_id,
        workspace_id=workspace_id,
        document_types=request_data.get("document_types", []),
        due_in_days=request_data.get("due_in_days", 5),
        message=request_data.get("message"),
        created_by_user_id=current_user.id
    )

    return {"success": True, "request": result}


# =============================================================================
# INTERNAL ADMIN ENDPOINTS - Analytics
# =============================================================================

@purl_admin_router.get(
    "/analytics/summary",
    summary="Get analytics summary",
    description="Get PURL system analytics"
)
async def get_analytics_summary(
    days: int = Query(30, ge=1, le=365, description="Days to analyze"),
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Get PURL analytics summary."""
    from sqlalchemy import func
    from datetime import timedelta

    org_id = get_user_org_id(current_user)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Workspace stats
    total_workspaces = db.query(func.count(PURLWorkspace.id)).filter(
        PURLWorkspace.organization_id == org_id
    ).scalar() or 0

    active_workspaces = db.query(func.count(PURLWorkspace.id)).filter(
        PURLWorkspace.organization_id == org_id,
        PURLWorkspace.status.in_([
            WorkspaceStatus.APPLICATION.value,
            WorkspaceStatus.ACTIVE_LOAN.value
        ])
    ).scalar() or 0

    # Application stats
    applications_started = db.query(func.count(PURLApplication.id)).filter(
        PURLApplication.organization_id == org_id,
        PURLApplication.started_at >= since
    ).scalar() or 0

    applications_submitted = db.query(func.count(PURLApplication.id)).filter(
        PURLApplication.organization_id == org_id,
        PURLApplication.submitted_at >= since
    ).scalar() or 0

    # Document stats
    documents_uploaded = db.query(func.count(PURLDocument.id)).filter(
        PURLDocument.organization_id == org_id,
        PURLDocument.created_at >= since
    ).scalar() or 0

    # Token count (active tokens)
    active_tokens = db.query(func.count(PURLAccessToken.id)).filter(
        PURLAccessToken.organization_id == org_id,
        PURLAccessToken.revoked_at.is_(None)
    ).scalar() or 0

    return {
        "period_days": days,
        "workspaces": {
            "total": total_workspaces,
            "active": active_workspaces
        },
        "applications": {
            "started": applications_started,
            "submitted": applications_submitted,
            "conversion_rate": round((applications_submitted / applications_started * 100), 1) if applications_started > 0 else 0
        },
        "documents": {
            "uploaded": documents_uploaded
        },
        "tokens": {
            "active_count": active_tokens
        }
    }


# =============================================================================
# INTERNAL ADMIN ENDPOINTS - Token Revocation
# =============================================================================

@purl_admin_router.post(
    "/tokens/{token_id}/revoke",
    summary="Revoke token",
    description="Revoke an access token with reason"
)
async def revoke_token_with_reason(
    token_id: int = Path(..., description="Token ID"),
    reason: Optional[str] = Query(None, description="Reason for revocation"),
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Revoke an access token with optional reason."""
    # Get token and verify ownership
    token = db.query(PURLAccessToken).filter(
        PURLAccessToken.id == token_id
    ).first()

    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    # Verify workspace belongs to user's organization
    org_id = get_user_org_id(current_user)
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == token.workspace_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=403, detail="Access denied")

    # Revoke token
    service = PURLTokenService(db)
    success = service.revoke_token(token_id, reason=reason)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to revoke token")

    return {"success": True, "message": "Token revoked"}


# =============================================================================
# INTERNAL ADMIN ENDPOINTS - Workspace Activity
# =============================================================================

@purl_admin_router.get(
    "/workspaces/{workspace_id}/activity",
    summary="Get workspace activity",
    description="Get activity log for a workspace"
)
async def get_workspace_activity(
    workspace_id: int = Path(..., description="Workspace ID"),
    limit: int = Query(50, ge=1, le=200, description="Max activities"),
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Get activity history for a workspace."""
    org_id = get_user_org_id(current_user)

    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Get audit log entries
    activities = db.query(PURLAuditLog).filter(
        PURLAuditLog.workspace_id == workspace_id
    ).order_by(PURLAuditLog.created_at.desc()).limit(limit).all()

    # Map action types to icons
    action_icons = {
        "application_save": "📝",
        "application_submit": "✅",
        "document_upload": "📄",
        "task_update": "✓",
        "message_send": "💬",
        "token_create": "🔑",
        "token_revoke": "🚫",
        "workspace_update": "⚙️"
    }

    return {
        "activities": [
            {
                "id": a.id,
                "action": a.action,
                "action_icon": action_icons.get(a.action, "●"),
                "resource_type": a.resource_type,
                "resource_id": a.resource_id,
                "actor_name": "Borrower" if a.actor_type == "contact" else "System",
                "metadata": a.meta_data,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in activities
        ]
    }


@purl_admin_router.get(
    "/workspaces/{workspace_id}/purl-url",
    summary="Get PURL URL",
    description="Generate full PURL URL with active token"
)
async def get_purl_url(
    workspace_id: int = Path(..., description="Workspace ID"),
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Get the full PURL URL for a workspace."""
    import os

    org_id = get_user_org_id(current_user)

    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Get active token
    token = db.query(PURLAccessToken).filter(
        PURLAccessToken.workspace_id == workspace_id,
        PURLAccessToken.revoked_at.is_(None),
        PURLAccessToken.expires_at > datetime.now(timezone.utc)
    ).first()

    if not token:
        return {
            "has_active_token": False,
            "message": "No active token found. Create a new token first."
        }

    # Build URL with token for authenticated access
    base_domain = os.getenv("PURL_BASE_DOMAIN", "perenniaai.com")
    portal_url = f"https://{base_domain}/portal/{workspace.slug}?token={token.token}"

    return {
        "has_active_token": True,
        "portal_url": portal_url,
        "workspace_slug": workspace.slug,
        "token_expires_at": token.expires_at.isoformat() if token.expires_at else None
    }


@purl_admin_router.get(
    "/metrics",
    summary="Get PURL dashboard metrics",
    description="Get aggregate metrics for PURL dashboard"
)
async def get_purl_metrics(
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Get aggregate metrics for the PURL dashboard."""
    from sqlalchemy import func

    org_id = get_user_org_id(current_user)
    today = datetime.now(timezone.utc).date()

    # Total workspaces
    total_workspaces = db.query(func.count(PURLWorkspace.id)).filter(
        PURLWorkspace.organization_id == org_id
    ).scalar() or 0

    # Applications submitted
    applications_submitted = db.query(func.count(PURLApplication.id)).join(
        PURLWorkspace, PURLApplication.workspace_id == PURLWorkspace.id
    ).filter(
        PURLWorkspace.organization_id == org_id,
        PURLApplication.status == ApplicationStatus.SUBMITTED
    ).scalar() or 0

    # Active today (workspaces with activity today)
    active_today = db.query(func.count(func.distinct(PURLAuditLog.workspace_id))).join(
        PURLWorkspace, PURLAuditLog.workspace_id == PURLWorkspace.id
    ).filter(
        PURLWorkspace.organization_id == org_id,
        func.date(PURLAuditLog.created_at) == today
    ).scalar() or 0

    # Completion rate (submitted / total with application started)
    total_with_app = db.query(func.count(PURLApplication.id)).join(
        PURLWorkspace, PURLApplication.workspace_id == PURLWorkspace.id
    ).filter(
        PURLWorkspace.organization_id == org_id
    ).scalar() or 1  # Avoid division by zero

    completion_rate = round((applications_submitted / total_with_app) * 100) if total_with_app > 0 else 0

    # Documents uploaded
    documents_uploaded = db.query(func.count(PURLDocument.id)).join(
        PURLWorkspace, PURLDocument.workspace_id == PURLWorkspace.id
    ).filter(
        PURLWorkspace.organization_id == org_id
    ).scalar() or 0

    # Pending review (applications in review status)
    pending_review = db.query(func.count(PURLApplication.id)).join(
        PURLWorkspace, PURLApplication.workspace_id == PURLWorkspace.id
    ).filter(
        PURLWorkspace.organization_id == org_id,
        PURLApplication.status == ApplicationStatus.SUBMITTED  # Submitted = pending review
    ).scalar() or 0

    return {
        "total_workspaces": total_workspaces,
        "applications_submitted": applications_submitted,
        "active_today": active_today,
        "completion_rate": completion_rate,
        "documents_uploaded": documents_uploaded,
        "pending_review": pending_review
    }


@purl_admin_router.post(
    "/workspaces/{workspace_id}/resend-invite",
    summary="Resend portal invitation",
    description="Resend invitation email to borrower"
)
async def resend_invite(
    workspace_id: int = Path(..., description="Workspace ID"),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Resend portal invitation email to borrower."""
    org_id = get_user_org_id(current_user)

    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Get primary contact (borrower)
    contact = db.query(PURLContact).filter(
        PURLContact.workspace_id == workspace_id,
        PURLContact.contact_type == "borrower"
    ).first()

    if not contact or not contact.email:
        raise HTTPException(status_code=400, detail="No email address found for this workspace")

    # Get active token
    token = db.query(PURLAccessToken).filter(
        PURLAccessToken.workspace_id == workspace_id,
        PURLAccessToken.revoked_at.is_(None),
        PURLAccessToken.expires_at > datetime.now(timezone.utc)
    ).first()

    if not token:
        raise HTTPException(status_code=400, detail="No active token. Please generate a new token first.")

    # Queue email send (if email service available)
    try:
        from services.purl_email_service import PURLEmailService
        email_service = PURLEmailService(db)
        if background_tasks:
            background_tasks.add_task(
                email_service.send_portal_invitation,
                workspace_id=workspace_id,
                token_id=token.id,
                recipient_email=contact.email,
                recipient_name=contact.first_name
            )
    except ImportError:
        logger.warning("Email service not available for resend invite")

    # Log action
    audit_log = PURLAuditLog(
        organization_id=org_id,
        workspace_id=workspace_id,
        action="invite_resent",
        actor_type="user",
        actor_id=current_user.id,
        metadata={"email": contact.email}
    )
    db.add(audit_log)
    db.commit()

    return {
        "success": True,
        "message": f"Invitation resent to {contact.email}"
    }


class BulkResendRequest(BaseModel):
    """Request model for bulk resend invites."""
    workspace_ids: List[int]


@purl_admin_router.post(
    "/bulk/resend-invites",
    summary="Bulk resend invitations",
    description="Resend invitations to multiple workspaces"
)
async def bulk_resend_invites(
    request: BulkResendRequest,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Bulk resend portal invitations."""
    workspace_ids = request.workspace_ids
    sent_count = 0
    failed_count = 0

    for workspace_id in workspace_ids:
        try:
            await resend_invite(workspace_id, background_tasks, current_user, db)
            sent_count += 1
        except HTTPException:
            failed_count += 1
        except Exception as e:
            logger.error(f"Failed to resend invite for workspace {workspace_id}: {e}")
            failed_count += 1

    return {
        "success": True,
        "sent": sent_count,
        "failed": failed_count,
        "message": f"Sent {sent_count} invitations, {failed_count} failed"
    }


@purl_admin_router.post(
    "/tokens/{token_id}/revoke",
    summary="Revoke access token",
    description="Revoke a PURL access token"
)
async def revoke_token_by_id(
    token_id: int = Path(..., description="Token ID"),
    reason: Optional[str] = None,
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Revoke a PURL access token by ID."""
    org_id = get_user_org_id(current_user)

    # Get token and verify ownership through workspace
    token = db.query(PURLAccessToken).join(
        PURLWorkspace, PURLAccessToken.workspace_id == PURLWorkspace.id
    ).filter(
        PURLAccessToken.id == token_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    if token.revoked_at:
        return {"success": True, "message": "Token already revoked"}

    # Revoke the token
    token.revoked_at = datetime.now(timezone.utc)
    token.revoked_by = current_user.id

    # Log action
    audit_log = PURLAuditLog(
        organization_id=org_id,
        workspace_id=token.workspace_id,
        action="token_revoked",
        actor_type="user",
        actor_id=current_user.id,
        metadata={"token_id": token_id, "reason": reason}
    )
    db.add(audit_log)
    db.commit()

    return {
        "success": True,
        "message": "Token revoked successfully"
    }


# =============================================================================
# RESEND PORTAL INVITE
# =============================================================================

@purl_admin_router.post(
    "/workspaces/{workspace_id}/resend-invite",
    summary="Resend portal invite",
    description="Generate a new token and resend portal invite email to borrower"
)
async def resend_portal_invite(
    workspace_id: int = Path(..., description="Workspace ID"),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Resend portal invite with a fresh token."""
    from services.purl_email_service import email_service

    org_id = get_user_org_id(current_user)

    # Get workspace
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == org_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Get borrower contact
    borrower = db.query(PURLContact).filter(
        PURLContact.workspace_id == workspace_id,
        PURLContact.contact_type == "borrower"
    ).first()

    if not borrower or not borrower.email:
        raise HTTPException(
            status_code=400,
            detail="No borrower contact with email found for this workspace"
        )

    # Create new token
    token_service = PURLTokenService(db)
    token_id, full_token = token_service.create_token(
        organization_id=org_id,
        workspace_id=workspace_id,
        scope=TokenScope.WRITE,
        contact_id=borrower.id,
        created_by=current_user.id
    )

    # Get loan officer info for the email
    lo_name = current_user.full_name or current_user.email
    lo_email = current_user.email

    # Send the welcome email with portal link
    email_sent = await email_service.send_welcome_email(
        to_email=borrower.email,
        first_name=borrower.first_name or "there",
        workspace_slug=workspace.slug,
        token=full_token,
        loan_officer_name=lo_name,
        loan_officer_email=lo_email
    )

    # Log action
    audit_log = PURLAuditLog(
        organization_id=org_id,
        workspace_id=workspace_id,
        action="portal_invite_resent",
        actor_type="user",
        actor_id=current_user.id,
        metadata={
            "token_id": token_id,
            "sent_to": borrower.email,
            "email_sent": email_sent
        }
    )
    db.add(audit_log)
    db.commit()

    portal_url = f"https://app.perenniaai.com/portal/{workspace.slug}?token={full_token}"

    return {
        "success": True,
        "message": f"Portal invite sent to {borrower.email}",
        "portal_url": portal_url,
        "email_sent": email_sent,
        "token_id": token_id
    }


@purl_admin_router.post(
    "/workspaces/by-slug/{slug}/resend-invite",
    summary="Resend portal invite by slug",
    description="Generate a new token and resend portal invite email to borrower (lookup by slug)"
)
async def resend_portal_invite_by_slug(
    slug: str = Path(..., description="Workspace slug"),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_authenticated_user()),
    db: Session = Depends(get_db)
):
    """Resend portal invite by workspace slug."""
    try:
        from services.purl_email_service import email_service

        org_id = get_user_org_id(current_user)
        logger.info(f"Resend invite: slug={slug}, org_id={org_id}, user={current_user.email}")

        # Get workspace by slug - try without org filter first to see if it exists
        workspace = db.query(PURLWorkspace).filter(
            PURLWorkspace.slug == slug
        ).first()

        if not workspace:
            raise HTTPException(status_code=404, detail=f"Workspace '{slug}' not found in database")

        if workspace.organization_id != org_id:
            logger.warning(f"Workspace {slug} belongs to org {workspace.organization_id}, not {org_id}")
            # Allow access if user is admin/owner or workspace org is 1 (default)
            if workspace.organization_id != 1:
                raise HTTPException(status_code=403, detail=f"Workspace belongs to different organization")

        logger.info(f"Found workspace: id={workspace.id}, display_name={workspace.display_name}")

        # Get borrower contact - try any contact type first
        borrower = db.query(PURLContact).filter(
            PURLContact.workspace_id == workspace.id,
            PURLContact.contact_type == "borrower"
        ).first()

        if not borrower:
            # Try getting any contact
            any_contact = db.query(PURLContact).filter(
                PURLContact.workspace_id == workspace.id
            ).first()
            if any_contact:
                logger.info(f"No borrower contact, using contact type: {any_contact.contact_type}")
                borrower = any_contact
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"No contacts found for workspace {slug}"
                )

        if not borrower.email:
            raise HTTPException(
                status_code=400,
                detail=f"Contact {borrower.first_name} has no email address"
            )

        logger.info(f"Found borrower ID: {borrower.id}")

        # Create new token
        token_service = PURLTokenService(db)
        token_id, full_token = token_service.create_token(
            organization_id=workspace.organization_id,  # Use workspace's org
            workspace_id=workspace.id,
            scope=TokenScope.WRITE,
            contact_id=borrower.id,
            created_by=current_user.id
        )

        logger.info(f"Created token: id={token_id}")

        # Get loan officer info for the email
        lo_name = current_user.full_name or current_user.email
        lo_email = current_user.email

        # Send the welcome email with portal link
        try:
            email_sent = await email_service.send_welcome_email(
                to_email=borrower.email,
                first_name=borrower.first_name or "there",
                workspace_slug=workspace.slug,
                token=full_token,
                loan_officer_name=lo_name,
                loan_officer_email=lo_email
            )
        except Exception as email_error:
            logger.error(f"Email sending failed: {email_error}")
            email_sent = False

        # Log action - skip if it fails
        try:
            audit_log = PURLAuditLog(
                organization_id=workspace.organization_id,
                workspace_id=workspace.id,
                action="portal_invite_resent",
                actor_type="user",
                actor_id=current_user.id,
                metadata={
                    "token_id": token_id,
                    "sent_to": borrower.email,
                    "email_sent": email_sent
                }
            )
            db.add(audit_log)
            db.commit()
        except Exception as audit_error:
            logger.warning(f"Audit log failed: {audit_error}")
            db.rollback()

        portal_url = f"https://app.perenniaai.com/portal/{workspace.slug}?token={full_token}"

        return {
            "success": True,
            "message": f"Portal invite sent to {borrower.email}",
            "portal_url": portal_url,
            "email_sent": email_sent,
            "token_id": token_id,
            "borrower_name": f"{borrower.first_name or ''} {borrower.last_name or ''}".strip(),
            "borrower_email": borrower.email
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Resend invite failed: {e}")
        raise HTTPException(status_code=500, detail="Internal error")


# =============================================================================
# HEALTH CHECK
# =============================================================================

@purl_router.get("/health", summary="Health check")
async def purl_health_check():
    """PURL system health check."""
    return {
        "status": "healthy",
        "service": "purl",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
