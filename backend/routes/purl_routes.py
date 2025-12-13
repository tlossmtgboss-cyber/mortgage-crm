"""
PURL (Persistent URL) API Routes
Perennia AI - Mortgage CRM

Provides API endpoints for the PURL borrower portal system:
- Public endpoints (PURL token auth): workspace access, applications, documents, timeline
- Internal endpoints (user auth): workspace management, token management
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Path, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db

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
    verify_workspace_access,
    log_purl_action,
    check_purl_rate_limit,
)

# Internal auth (existing system)
from main import get_current_user, User


logger = logging.getLogger(__name__)

# =============================================================================
# ROUTERS
# =============================================================================

# Public PURL router (token-based auth)
purl_router = APIRouter(prefix="/api/purl", tags=["PURL Portal"])

# Internal PURL management router (user auth)
purl_admin_router = APIRouter(prefix="/api/v1/purl-admin", tags=["PURL Administration"])


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
    documents: List[Dict[str, Any]] = []
    tasks: List[Dict[str, Any]] = []
    milestones: List[Dict[str, Any]] = []
    timeline: List[Dict[str, Any]] = []
    modules: List[Dict[str, Any]] = []


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
    # Verify access to this workspace
    verify_workspace_access(context, slug)

    service = PURLWorkspaceService(db)
    data = service.get_workspace_portal_data(context.workspace_id)

    if not data:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return WorkspaceDataResponse(**data)


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
    application = service.get_workspace_application(context.workspace_id)

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
    db: Session = Depends(get_db)
):
    """
    Submit the completed application.

    Validates all required fields are present.
    Creates a loan record.
    Initializes loan workflow (milestones, tasks).
    """
    verify_workspace_access(context, slug)

    service = PURLApplicationService(db)

    try:
        result = service.submit_application(
            organization_id=context.organization_id,
            workspace_id=context.workspace_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
        query = query.filter(PURLDocument.category == category)

    documents = query.order_by(PURLDocument.created_at.desc()).all()

    return {
        "documents": [
            {
                "id": doc.id,
                "filename": doc.filename,
                "document_type": doc.document_type,
                "category": doc.category,
                "status": doc.status,
                "file_size": doc.file_size,
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
            "filename": document.filename,
            "document_type": document.document_type,
            "category": document.category,
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
    except Exception as e:
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
        workspace_id=context.workspace_id,
        status=TaskStatus(status) if status else None
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
    timeline = service.get_timeline(
        workspace_id=context.workspace_id,
        limit=limit
    )

    return {"timeline": timeline}


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

    # Get active loan
    loan = db.query(PURLLoan).filter(
        PURLLoan.workspace_id == context.workspace_id
    ).order_by(PURLLoan.created_at.desc()).first()

    if not loan:
        return {"milestones": [], "message": "No active loan"}

    service = PURLTimelineService(db)
    milestones = service.get_milestones(loan.id)

    return {"loan_id": loan.id, "milestones": milestones}


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
# INTERNAL ADMIN ENDPOINTS - Workspace Management
# =============================================================================

@purl_admin_router.post(
    "/workspaces",
    summary="Create workspace",
    description="Create a new PURL workspace"
)
async def create_workspace(
    workspace: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new PURL workspace with initial contacts."""
    service = PURLWorkspaceService(db)

    try:
        result = service.create_workspace(
            organization_id=current_user.organization_id,
            data=workspace.dict()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by name or slug"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List PURL workspaces for the organization."""
    query = db.query(PURLWorkspace).filter(
        PURLWorkspace.organization_id == current_user.organization_id
    )

    if status:
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
                "status": ws.status,
                "created_at": ws.created_at.isoformat() if ws.created_at else None
            }
            for ws in workspaces
        ]
    }


@purl_admin_router.get(
    "/workspaces/{workspace_id}",
    summary="Get workspace",
    description="Get workspace details"
)
async def get_workspace(
    workspace_id: int = Path(..., description="Workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get workspace details."""
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == current_user.organization_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    service = PURLWorkspaceService(db)
    return service.get_workspace_portal_data(workspace_id)


@purl_admin_router.patch(
    "/workspaces/{workspace_id}",
    summary="Update workspace",
    description="Update workspace settings"
)
async def update_workspace(
    workspace_id: int = Path(..., description="Workspace ID"),
    updates: Dict[str, Any] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update workspace settings."""
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == current_user.organization_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Update allowed fields
    allowed_fields = ["display_name", "settings", "status"]
    for field, value in (updates or {}).items():
        if field in allowed_fields and hasattr(workspace, field):
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new access token for a workspace."""
    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == current_user.organization_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    service = PURLTokenService(db)

    result = service.create_token(
        organization_id=current_user.organization_id,
        workspace_id=workspace_id,
        scope=token_data.scope if token_data else TokenScope.READ,
        name=token_data.name if token_data else "Access Token",
        contact_id=token_data.contact_id if token_data else None,
        expires_in_days=token_data.expires_in_days if token_data else 365,
        created_by_user_id=current_user.id
    )

    return {
        "success": True,
        "token": result["token"],  # Only returned once!
        "token_id": result["token_id"],
        "expires_at": result["expires_at"]
    }


@purl_admin_router.get(
    "/workspaces/{workspace_id}/tokens",
    summary="List tokens",
    description="List access tokens for a workspace"
)
async def list_tokens(
    workspace_id: int = Path(..., description="Workspace ID"),
    include_revoked: bool = Query(False, description="Include revoked tokens"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List access tokens for a workspace."""
    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == current_user.organization_id
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Revoke an access token."""
    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == current_user.organization_id
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a contact to a workspace."""
    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == current_user.organization_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    service = PURLWorkspaceService(db)

    try:
        result = service.add_contact(
            workspace_id=workspace_id,
            contact_data=contact.dict()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, "contact": result}


@purl_admin_router.get(
    "/workspaces/{workspace_id}/contacts",
    summary="List contacts",
    description="List contacts for a workspace"
)
async def list_contacts(
    workspace_id: int = Path(..., description="Workspace ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List contacts for a workspace."""
    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == current_user.organization_id
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a document request for the borrower."""
    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == current_user.organization_id
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    service = PURLDocumentService(db)

    result = service.create_document_request(
        organization_id=current_user.organization_id,
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get PURL analytics summary."""
    from sqlalchemy import func
    from datetime import timedelta

    org_id = current_user.organization_id
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
    current_user: User = Depends(get_current_user),
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
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == token.workspace_id,
        PURLWorkspace.organization_id == current_user.organization_id
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get activity history for a workspace."""
    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == current_user.organization_id
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the full PURL URL for a workspace."""
    import os

    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == current_user.organization_id
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

    # Build URL
    base_domain = os.getenv("PURL_BASE_DOMAIN", "client.perennia.ai")
    portal_url = f"https://{base_domain}/portal/{workspace.slug}"

    return {
        "has_active_token": True,
        "portal_url": portal_url,
        "workspace_slug": workspace.slug,
        "token_expires_at": token.expires_at.isoformat() if token.expires_at else None
    }


# =============================================================================
# PROFILE INTEGRATION ENDPOINTS
# =============================================================================

@purl_admin_router.get(
    "/workspaces/by-lead/{lead_id}",
    summary="Get workspace by lead ID",
    description="Get workspace and tokens for a specific lead (used by profile widget)"
)
async def get_workspace_by_lead(
    lead_id: str = Path(..., description="Lead ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get workspace for a specific lead - used by PURLWidget in profile pages."""
    from sqlalchemy import or_, cast, String

    # Try to find workspace by lead_id in metadata
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.organization_id == current_user.organization_id,
        or_(
            PURLWorkspace.meta_data['lead_id'].astext == lead_id,
            PURLWorkspace.meta_data['loan_id'].astext == lead_id
        )
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
            "status": workspace.status.value if workspace.status else "lead",
            "document_count": document_count,
            "application_status": application.status.value if application else None,
            "last_activity": last_activity.created_at.isoformat() if last_activity else None,
            "created_at": workspace.created_at.isoformat() if workspace.created_at else None
        },
        "tokens": [
            {
                "id": token.id,
                "token_prefix": token.token_prefix or "purl_",
                "status": "active" if not token.revoked_at else "revoked",
                "scope": token.scope.value if token.scope else "read",
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get workspace for a specific loan - used by PURLWidget in loan profile pages."""
    # Reuse the lead lookup logic
    return await get_workspace_by_lead(loan_id, current_user, db)


@purl_admin_router.get(
    "/metrics",
    summary="Get PURL dashboard metrics",
    description="Get aggregate metrics for PURL dashboard"
)
async def get_purl_metrics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get aggregate metrics for the PURL dashboard."""
    from sqlalchemy import func

    org_id = current_user.organization_id
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Resend portal invitation email to borrower."""
    # Verify workspace ownership
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == workspace_id,
        PURLWorkspace.organization_id == current_user.organization_id
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
        organization_id=current_user.organization_id,
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Revoke a PURL access token by ID."""
    # Get token and verify ownership through workspace
    token = db.query(PURLAccessToken).join(
        PURLWorkspace, PURLAccessToken.workspace_id == PURLWorkspace.id
    ).filter(
        PURLAccessToken.id == token_id,
        PURLWorkspace.organization_id == current_user.organization_id
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
        organization_id=current_user.organization_id,
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
