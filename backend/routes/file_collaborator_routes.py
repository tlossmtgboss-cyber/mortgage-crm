"""
File Collaborator Routes -- Loan file team management.

Manage collaborators (processors, underwriters, closers, assistants, etc.)
on individual loan files.  Supports add, remove, update role/permissions,
bulk-add, and listing files a user collaborates on.

Prefix: /api/v1/files
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index, and_, text
from sqlalchemy.orm import Session

from db import get_db, engine
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["File Collaborators"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class AddCollaboratorRequest(BaseModel):
    user_id: int = Field(..., description="ID of the user to add as collaborator")
    role: str = Field(
        "viewer",
        description="Collaborator role: owner, editor, processor, underwriter, closer, viewer",
    )
    can_edit: bool = Field(True, description="Can edit loan file details")
    can_comment: bool = Field(True, description="Can add comments/notes")
    can_upload: bool = Field(True, description="Can upload documents")
    notify_on_change: bool = Field(True, description="Receive notifications on file changes")


class UpdateCollaboratorRequest(BaseModel):
    role: Optional[str] = Field(None, description="New role for the collaborator")
    can_edit: Optional[bool] = None
    can_comment: Optional[bool] = None
    can_upload: Optional[bool] = None
    notify_on_change: Optional[bool] = None


class BulkAddCollaboratorEntry(BaseModel):
    user_id: int
    role: str = "viewer"
    can_edit: bool = True
    can_comment: bool = True
    can_upload: bool = True
    notify_on_change: bool = True


class BulkAddCollaboratorsRequest(BaseModel):
    collaborators: List[BulkAddCollaboratorEntry] = Field(
        ..., min_length=1, max_length=50, description="List of collaborators to add",
    )


class CollaboratorResponse(BaseModel):
    id: int
    file_id: int
    user_id: int
    role: str
    can_edit: bool
    can_comment: bool
    can_upload: bool
    notify_on_change: bool
    added_by_user_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class FileCollaborationResponse(BaseModel):
    file_id: int
    loan_number: Optional[str] = None
    borrower_name: Optional[str] = None
    property_address: Optional[str] = None
    stage: Optional[str] = None
    role: str
    can_edit: bool
    can_comment: bool
    can_upload: bool
    notify_on_change: bool


# =============================================================================
# SQLAlchemy Model (inline -- no separate model file needed yet)
# =============================================================================

from db import Base


class FileCollaborator(Base):
    """Tracks which users collaborate on which loan files and their permissions."""
    __tablename__ = "file_collaborators"
    __table_args__ = (
        Index("ix_file_collab_file_id", "file_id"),
        Index("ix_file_collab_user_id", "user_id"),
        Index("ix_file_collab_org_id", "organization_id"),
        Index("ix_file_collab_file_user", "file_id", "user_id", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("loans.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    role = Column(String, default="viewer")  # owner, editor, processor, underwriter, closer, viewer
    can_edit = Column(Boolean, default=True)
    can_comment = Column(Boolean, default=True)
    can_upload = Column(Boolean, default=True)
    notify_on_change = Column(Boolean, default=True)
    added_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# =============================================================================
# Valid roles for collaborators
# =============================================================================

VALID_ROLES = {"owner", "editor", "processor", "underwriter", "closer", "viewer"}


# =============================================================================
# Helpers -- lazy model imports
# =============================================================================

_models_loaded = False
_Loan = None
_User = None


def _ensure_models():
    """Lazy-import models on first use to avoid circular imports."""
    global _models_loaded, _Loan, _User
    if _models_loaded:
        return
    from database.models.lead_loan import Loan
    from database.models.core import User
    _Loan = Loan
    _User = User
    _models_loaded = True


def _ensure_table(db: Session):
    """Create the file_collaborators table if it doesn't exist (production-safe)."""
    try:
        FileCollaborator.__table__.create(engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"FileCollaborator table creation check failed (non-fatal): {e}")


def _can_manage_collaborators(user, loan, db: Session) -> bool:
    """Check whether the requesting user can manage collaborators on this loan file.

    Allowed if the user is:
    - An admin or site_admin (by role or permission_role)
    - A branch_manager / leadership / management permission_role
    - The loan officer (owner) of this loan file
    - An existing collaborator with role='owner' on this file
    """
    # Admin / site_admin -- full access
    admin_roles = {"admin", "site_admin"}
    if getattr(user, "role", None) in admin_roles:
        return True
    if getattr(user, "permission_role", None) in admin_roles:
        return True

    # Management roles
    mgmt_roles = {"branch_manager", "leadership", "management"}
    if getattr(user, "permission_role", None) in mgmt_roles:
        return True

    # Loan officer (owner of the file)
    if loan.loan_officer_id == user.id:
        return True

    # Existing collaborator with owner role on this file
    existing = db.query(FileCollaborator).filter(
        FileCollaborator.file_id == loan.id,
        FileCollaborator.user_id == user.id,
        FileCollaborator.role == "owner",
    ).first()
    if existing:
        return True

    return False


def _get_loan_or_404(db: Session, file_id: int, organization_id: int):
    """Retrieve the loan (file) by ID with tenant isolation, or raise 404."""
    _ensure_models()
    loan = db.query(_Loan).filter(
        _Loan.id == file_id,
        _Loan.organization_id == organization_id,
    ).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan file not found")
    return loan


# =============================================================================
# Routes
# =============================================================================

@router.post("/api/v1/files/{file_id}/collaborators", status_code=201)
async def add_collaborator(
    file_id: int,
    body: AddCollaboratorRequest,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Add a collaborator to a loan file."""
    _ensure_models()
    _ensure_table(db)

    loan = _get_loan_or_404(db, file_id, current_user.organization_id)

    if not _can_manage_collaborators(current_user, loan, db):
        raise HTTPException(status_code=403, detail="Not authorized to manage collaborators on this file")

    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}",
        )

    # Verify the target user exists and is in the same org
    target_user = db.query(_User).filter(
        _User.id == body.user_id,
        _User.organization_id == current_user.organization_id,
        _User.is_active == True,  # noqa: E712
    ).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found in your organization")

    # Check for duplicate
    existing = db.query(FileCollaborator).filter(
        FileCollaborator.file_id == file_id,
        FileCollaborator.user_id == body.user_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="User is already a collaborator on this file")

    collab = FileCollaborator(
        file_id=file_id,
        user_id=body.user_id,
        organization_id=current_user.organization_id,
        role=body.role,
        can_edit=body.can_edit,
        can_comment=body.can_comment,
        can_upload=body.can_upload,
        notify_on_change=body.notify_on_change,
        added_by_user_id=current_user.id,
    )
    db.add(collab)
    db.commit()
    db.refresh(collab)

    logger.info(
        f"User {current_user.id} added user {body.user_id} as {body.role} "
        f"on file {file_id} (org={current_user.organization_id})"
    )

    return CollaboratorResponse(
        id=collab.id,
        file_id=collab.file_id,
        user_id=collab.user_id,
        role=collab.role,
        can_edit=collab.can_edit,
        can_comment=collab.can_comment,
        can_upload=collab.can_upload,
        notify_on_change=collab.notify_on_change,
        added_by_user_id=collab.added_by_user_id,
        first_name=target_user.first_name,
        last_name=target_user.last_name,
        email=target_user.email,
        created_at=collab.created_at.isoformat() if collab.created_at else None,
        updated_at=collab.updated_at.isoformat() if collab.updated_at else None,
    )


@router.get("/api/v1/files/{file_id}/collaborators")
async def list_collaborators(
    file_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """List all collaborators on a loan file."""
    _ensure_models()
    _ensure_table(db)

    loan = _get_loan_or_404(db, file_id, current_user.organization_id)

    rows = (
        db.query(FileCollaborator, _User)
        .join(_User, _User.id == FileCollaborator.user_id)
        .filter(
            FileCollaborator.file_id == file_id,
            FileCollaborator.organization_id == current_user.organization_id,
        )
        .order_by(FileCollaborator.created_at.asc())
        .all()
    )

    results = []
    for collab, user in rows:
        results.append(CollaboratorResponse(
            id=collab.id,
            file_id=collab.file_id,
            user_id=collab.user_id,
            role=collab.role,
            can_edit=collab.can_edit,
            can_comment=collab.can_comment,
            can_upload=collab.can_upload,
            notify_on_change=collab.notify_on_change,
            added_by_user_id=collab.added_by_user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            created_at=collab.created_at.isoformat() if collab.created_at else None,
            updated_at=collab.updated_at.isoformat() if collab.updated_at else None,
        ))

    return {"file_id": file_id, "collaborators": results, "count": len(results)}


@router.delete("/api/v1/files/{file_id}/collaborators/{user_id}", status_code=200)
async def remove_collaborator(
    file_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Remove a collaborator from a loan file."""
    _ensure_models()
    _ensure_table(db)

    loan = _get_loan_or_404(db, file_id, current_user.organization_id)

    if not _can_manage_collaborators(current_user, loan, db):
        raise HTTPException(status_code=403, detail="Not authorized to manage collaborators on this file")

    collab = db.query(FileCollaborator).filter(
        FileCollaborator.file_id == file_id,
        FileCollaborator.user_id == user_id,
        FileCollaborator.organization_id == current_user.organization_id,
    ).first()

    if not collab:
        raise HTTPException(status_code=404, detail="Collaborator not found on this file")

    db.delete(collab)
    db.commit()

    logger.info(
        f"User {current_user.id} removed user {user_id} from file {file_id} "
        f"(org={current_user.organization_id})"
    )

    return {"status": "ok", "detail": f"User {user_id} removed from file {file_id}"}


@router.patch("/api/v1/files/{file_id}/collaborators/{user_id}")
async def update_collaborator(
    file_id: int,
    user_id: int,
    body: UpdateCollaboratorRequest,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Update a collaborator's role, permissions, or notification preference."""
    _ensure_models()
    _ensure_table(db)

    loan = _get_loan_or_404(db, file_id, current_user.organization_id)

    if not _can_manage_collaborators(current_user, loan, db):
        raise HTTPException(status_code=403, detail="Not authorized to manage collaborators on this file")

    collab = db.query(FileCollaborator).filter(
        FileCollaborator.file_id == file_id,
        FileCollaborator.user_id == user_id,
        FileCollaborator.organization_id == current_user.organization_id,
    ).first()

    if not collab:
        raise HTTPException(status_code=404, detail="Collaborator not found on this file")

    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}",
            )
        collab.role = body.role
    if body.can_edit is not None:
        collab.can_edit = body.can_edit
    if body.can_comment is not None:
        collab.can_comment = body.can_comment
    if body.can_upload is not None:
        collab.can_upload = body.can_upload
    if body.notify_on_change is not None:
        collab.notify_on_change = body.notify_on_change

    collab.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(collab)

    # Fetch user info for response
    target_user = db.query(_User).filter(_User.id == user_id).first()

    logger.info(
        f"User {current_user.id} updated collaborator {user_id} on file {file_id} "
        f"(org={current_user.organization_id})"
    )

    return CollaboratorResponse(
        id=collab.id,
        file_id=collab.file_id,
        user_id=collab.user_id,
        role=collab.role,
        can_edit=collab.can_edit,
        can_comment=collab.can_comment,
        can_upload=collab.can_upload,
        notify_on_change=collab.notify_on_change,
        added_by_user_id=collab.added_by_user_id,
        first_name=target_user.first_name if target_user else None,
        last_name=target_user.last_name if target_user else None,
        email=target_user.email if target_user else None,
        created_at=collab.created_at.isoformat() if collab.created_at else None,
        updated_at=collab.updated_at.isoformat() if collab.updated_at else None,
    )


@router.get("/api/v1/users/me/files")
async def list_my_files(
    role: Optional[str] = Query(None, description="Filter by collaborator role"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """List all loan files the current user collaborates on."""
    _ensure_models()
    _ensure_table(db)

    query = (
        db.query(FileCollaborator, _Loan)
        .join(_Loan, _Loan.id == FileCollaborator.file_id)
        .filter(
            FileCollaborator.user_id == current_user.id,
            FileCollaborator.organization_id == current_user.organization_id,
        )
    )

    if role:
        if role not in VALID_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role filter. Must be one of: {', '.join(sorted(VALID_ROLES))}",
            )
        query = query.filter(FileCollaborator.role == role)

    total = query.count()
    rows = query.order_by(_Loan.created_at.desc()).offset(offset).limit(limit).all()

    results = []
    for collab, loan in rows:
        results.append(FileCollaborationResponse(
            file_id=loan.id,
            loan_number=loan.loan_number,
            borrower_name=loan.borrower_name,
            property_address=loan.property_address,
            stage=loan.stage,
            role=collab.role,
            can_edit=collab.can_edit,
            can_comment=collab.can_comment,
            can_upload=collab.can_upload,
            notify_on_change=collab.notify_on_change,
        ))

    return {"files": results, "total": total, "limit": limit, "offset": offset}


@router.post("/api/v1/files/{file_id}/collaborators/bulk", status_code=201)
async def bulk_add_collaborators(
    file_id: int,
    body: BulkAddCollaboratorsRequest,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Bulk-add multiple collaborators to a loan file in one request."""
    _ensure_models()
    _ensure_table(db)

    loan = _get_loan_or_404(db, file_id, current_user.organization_id)

    if not _can_manage_collaborators(current_user, loan, db):
        raise HTTPException(status_code=403, detail="Not authorized to manage collaborators on this file")

    # Validate all roles up front
    for entry in body.collaborators:
        if entry.role not in VALID_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role '{entry.role}' for user_id {entry.user_id}. "
                       f"Must be one of: {', '.join(sorted(VALID_ROLES))}",
            )

    # Collect target user IDs and verify they all exist in the org
    target_user_ids = [e.user_id for e in body.collaborators]
    existing_users = db.query(_User).filter(
        _User.id.in_(target_user_ids),
        _User.organization_id == current_user.organization_id,
        _User.is_active == True,  # noqa: E712
    ).all()
    existing_user_map = {u.id: u for u in existing_users}

    missing = set(target_user_ids) - set(existing_user_map.keys())
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Users not found in your organization: {sorted(missing)}",
        )

    # Check for existing collaborators
    already_on_file = db.query(FileCollaborator.user_id).filter(
        FileCollaborator.file_id == file_id,
        FileCollaborator.user_id.in_(target_user_ids),
    ).all()
    already_ids = {row[0] for row in already_on_file}

    added = []
    skipped = []

    for entry in body.collaborators:
        if entry.user_id in already_ids:
            skipped.append({"user_id": entry.user_id, "reason": "already_collaborator"})
            continue

        collab = FileCollaborator(
            file_id=file_id,
            user_id=entry.user_id,
            organization_id=current_user.organization_id,
            role=entry.role,
            can_edit=entry.can_edit,
            can_comment=entry.can_comment,
            can_upload=entry.can_upload,
            notify_on_change=entry.notify_on_change,
            added_by_user_id=current_user.id,
        )
        db.add(collab)
        user_obj = existing_user_map[entry.user_id]
        added.append({
            "user_id": entry.user_id,
            "role": entry.role,
            "first_name": user_obj.first_name,
            "last_name": user_obj.last_name,
        })

    db.commit()

    logger.info(
        f"User {current_user.id} bulk-added {len(added)} collaborators to file {file_id} "
        f"(skipped={len(skipped)}, org={current_user.organization_id})"
    )

    return {
        "file_id": file_id,
        "added": added,
        "skipped": skipped,
        "added_count": len(added),
        "skipped_count": len(skipped),
    }


# =============================================================================
# Registration
# =============================================================================

def register_file_collaborator_routes(app):
    """Register the file collaborator router with the FastAPI app."""
    app.include_router(router)
    logger.info("File collaborator routes registered")
