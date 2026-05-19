"""
Document Visibility Routes
Perennia AI - Mortgage CRM

API endpoints for managing document visibility to borrowers and partners.
Supports hiding documents, scheduling auto-release on milestones, and audit logging.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from document_visibility_service import DocumentVisibilityService
from models.document_visibility import ReleaseMode, ChangeSource
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["Document Visibility"])


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

_get_db = None
_get_current_user = None


def set_dependencies(get_db_func, get_current_user_func=None):
    """Set dependencies from main.py."""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    logger.info("Document Visibility routes dependencies set")


def get_db():
    """Get database session."""
    if _get_db is None:
        raise RuntimeError("Document Visibility routes not initialized")
    yield from _get_db()


from auth.dependencies import get_current_user  # dedup: was local wrapper
# Allowed roles for document visibility management
DOCUMENT_VISIBILITY_ROLES = [
    'admin', 'site_admin', 'management', 'leadership',
    'loan_officer', 'processor', 'underwriter', 'closer'
]

ADMIN_ONLY_ROLES = ['admin', 'site_admin']


def check_document_visibility_permission(current_user) -> bool:
    """Check if user has permission to manage document visibility."""
    if current_user is None:
        return False
    role = getattr(current_user, 'permission_role', None) or getattr(current_user, 'role', None)
    return role in DOCUMENT_VISIBILITY_ROLES


def check_admin_permission(current_user) -> bool:
    """Check if user has admin permission."""
    if current_user is None:
        return False
    role = getattr(current_user, 'permission_role', None) or getattr(current_user, 'role', None)
    return role in ADMIN_ONLY_ROLES


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class VisibilityUpdateRequest(BaseModel):
    """Request to update document visibility."""
    visible_to_borrower: Optional[bool] = None
    visible_to_partner: Optional[bool] = None
    visible_to_internal: Optional[bool] = None
    release_mode: Optional[str] = Field(None, description="manual, milestone, or datetime")
    release_milestone: Optional[str] = Field(None, description="e.g., funded, clear_to_close")
    release_at: Optional[datetime] = None
    hidden_reason: Optional[str] = None
    visibility_locked: Optional[bool] = None


class VisibilityResponse(BaseModel):
    """Response with visibility settings."""
    id: int
    document_table: str
    document_id: int
    loan_id: int
    visible_to_borrower: bool
    visible_to_partner: bool
    visible_to_internal: bool
    release_mode: str
    release_milestone: Optional[str]
    release_at: Optional[datetime]
    visibility_locked: bool
    hidden_reason: Optional[str]
    last_changed_by: Optional[int]
    last_changed_at: Optional[datetime]


class BulkVisibilityRequest(BaseModel):
    """Request for bulk visibility update."""
    documents: List[dict]  # [{"table": "perennia_documents", "id": 123}, ...]
    visible_to_borrower: Optional[bool] = None
    visible_to_partner: Optional[bool] = None
    reason: Optional[str] = None


class AuditEntryResponse(BaseModel):
    """Response for audit log entry."""
    id: int
    field_changed: str
    old_value: Optional[bool]
    new_value: Optional[bool]
    change_source: str
    changed_by: Optional[int]
    change_reason: Optional[str]
    created_at: datetime


# =============================================================================
# VISIBILITY ENDPOINTS
# =============================================================================

@router.get("/{document_table}/{document_id}/visibility")
async def get_document_visibility(
    document_table: str,
    document_id: int,
    loan_id: int = Query(..., description="Loan ID for context"),
    db: Session = Depends(get_db)
):
    """
    Get visibility settings for a document.

    Returns the current visibility state including:
    - Whether visible to borrower/partner/internal
    - Release mode and trigger settings
    - Lock status and hidden reason
    """
    service = DocumentVisibilityService(db)
    visibility = service.get_or_create_visibility(
        document_table=document_table,
        document_id=document_id,
        loan_id=loan_id
    )

    return visibility.to_dict()


@router.put("/{document_table}/{document_id}/visibility")
async def update_document_visibility(
    document_table: str,
    document_id: int,
    loan_id: int = Query(..., description="Loan ID for context"),
    request: VisibilityUpdateRequest = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Update visibility settings for a document.

    Requires admin/LO/processor role. Creates audit log entry.

    Fields that can be updated:
    - visible_to_borrower: Hide/show from borrower portal
    - visible_to_partner: Hide/show from partner portal
    - release_mode: 'manual', 'milestone', or 'datetime'
    - release_milestone: Trigger milestone (e.g., 'funded')
    - hidden_reason: Explanation for hiding
    - visibility_locked: Prevent auto-release from changing
    """
    if not check_document_visibility_permission(current_user):
        raise HTTPException(status_code=403, detail="Permission denied: insufficient role for document visibility management")

    service = DocumentVisibilityService(db)

    try:
        visibility = service.set_visibility(
            document_table=document_table,
            document_id=document_id,
            loan_id=loan_id,
            visible_to_borrower=request.visible_to_borrower if request else None,
            visible_to_partner=request.visible_to_partner if request else None,
            visible_to_internal=request.visible_to_internal if request else None,
            release_mode=request.release_mode if request else None,
            release_milestone=request.release_milestone if request else None,
            release_at=request.release_at if request else None,
            hidden_reason=request.hidden_reason if request else None,
            visibility_locked=request.visibility_locked if request else None,
            changed_by_user_id=current_user.id,
            change_source=ChangeSource.MANUAL.value,
            change_reason=request.hidden_reason if request else None
        )
        db.commit()

        return {
            "success": True,
            "visibility": visibility.to_dict()
        }
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating visibility: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{document_table}/{document_id}/visibility/history")
async def get_visibility_history(
    document_table: str,
    document_id: int,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """
    Get audit history for document visibility changes.

    Returns chronological list of all visibility changes including:
    - What field changed (e.g., visible_to_borrower)
    - Old and new values
    - Who made the change
    - When and why
    """
    service = DocumentVisibilityService(db)
    history = service.get_visibility_history(
        document_table=document_table,
        document_id=document_id,
        limit=limit
    )

    return {
        "document_table": document_table,
        "document_id": document_id,
        "history": history
    }


@router.post("/loan/{loan_id}/visibility/bulk")
async def bulk_update_visibility(
    loan_id: int,
    request: BulkVisibilityRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Bulk update visibility for multiple documents.

    Useful for hiding/showing all documents of a certain type,
    or batch operations on selected documents.
    """
    if not check_document_visibility_permission(current_user):
        raise HTTPException(status_code=403, detail="Permission denied: insufficient role for document visibility management")

    service = DocumentVisibilityService(db)

    try:
        updated = service.bulk_set_visibility(
            loan_id=loan_id,
            document_ids=request.documents,
            visible_to_borrower=request.visible_to_borrower,
            visible_to_partner=request.visible_to_partner,
            changed_by_user_id=current_user.id,
            change_reason=request.reason
        )
        db.commit()

        return {
            "success": True,
            "updated_count": updated
        }
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error in bulk visibility update: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{document_table}/{document_id}/release")
async def release_document(
    document_table: str,
    document_id: int,
    loan_id: int = Query(..., description="Loan ID for context"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Immediately release a hidden document.

    Makes the document visible to borrowers and partners.
    Equivalent to setting visible_to_borrower=True and visible_to_partner=True.
    """
    if not check_document_visibility_permission(current_user):
        raise HTTPException(status_code=403, detail="Permission denied: insufficient role for document visibility management")

    service = DocumentVisibilityService(db)

    try:
        visibility = service.set_visibility(
            document_table=document_table,
            document_id=document_id,
            loan_id=loan_id,
            visible_to_borrower=True,
            visible_to_partner=True,
            changed_by_user_id=current_user.id,
            change_source=ChangeSource.MANUAL.value,
            change_reason="Manual release"
        )
        db.commit()

        return {
            "success": True,
            "message": "Document released",
            "visibility": visibility.to_dict()
        }
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error releasing document: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# UTILITY ENDPOINTS
# =============================================================================

@router.get("/loan/{loan_id}/hidden")
async def get_hidden_documents(
    loan_id: int,
    document_table: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get list of hidden documents for a loan.

    Returns all documents that are hidden from borrowers or partners.
    Useful for admin dashboard to see what's hidden.
    """
    service = DocumentVisibilityService(db)

    # Get documents hidden from borrower
    borrower_hidden = service.get_hidden_document_ids(
        loan_id=loan_id,
        document_table=document_table or 'perennia_documents',
        for_borrower=True
    )

    # Get documents hidden from partner
    partner_hidden = service.get_hidden_document_ids(
        loan_id=loan_id,
        document_table=document_table or 'perennia_documents',
        for_borrower=False
    )

    return {
        "loan_id": loan_id,
        "document_table": document_table or 'perennia_documents',
        "hidden_from_borrower": borrower_hidden,
        "hidden_from_partner": partner_hidden
    }


@router.post("/loan/{loan_id}/process-milestone")
async def process_milestone_release(
    loan_id: int,
    milestone: str = Query(..., description="Milestone name, e.g., 'funded'"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Process auto-release for a milestone (admin/system use).

    Called when loan reaches a milestone to release scheduled documents.
    Normally triggered automatically by lifecycle service.
    """
    if not check_admin_permission(current_user):
        raise HTTPException(status_code=403, detail="Permission denied: admin access required for milestone processing")

    service = DocumentVisibilityService(db)

    try:
        released = service.process_milestone_release(
            loan_id=loan_id,
            milestone=milestone
        )
        db.commit()

        logger.info(f"Milestone '{milestone}' processed for loan {loan_id} by user {current_user.id}: {len(released)} documents released")

        return {
            "success": True,
            "milestone": milestone,
            "released_count": len(released),
            "released_documents": [
                {"table": v.document_table, "id": v.document_id}
                for v in released
            ]
        }
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error processing milestone release: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
