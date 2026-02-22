"""
Organization (Tenant) Management Routes
=======================================
Admin routes for managing organizations in the multi-tenant system.

These routes require platform admin or site_admin permissions.
"""

import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, EmailStr, field_validator

# Import from main.py
from auth.dependencies import get_current_user
from database import get_db
from database.models import Organization, User, Lead, Loan, Branch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class OrganizationCreate(BaseModel):
    """Schema for creating a new organization."""
    name: str
    slug: Optional[str] = None  # Auto-generated from name if not provided
    domain: Optional[str] = None  # Email domain for auto-assignment
    subscription_tier: str = "lead_management"
    settings: Optional[dict] = None

    @field_validator('slug')
    @classmethod
    def validate_slug(cls, v):
        if v:
            # Ensure slug is URL-friendly
            if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', v) and len(v) > 1:
                raise ValueError('Slug must be lowercase alphanumeric with hyphens')
        return v


class OrganizationUpdate(BaseModel):
    """Schema for updating an organization."""
    name: Optional[str] = None
    domain: Optional[str] = None
    subscription_tier: Optional[str] = None
    settings: Optional[dict] = None
    is_active: Optional[bool] = None


class OrganizationResponse(BaseModel):
    """Response schema for organization."""
    id: int
    name: str
    slug: str
    domain: Optional[str]
    subscription_tier: str
    is_active: bool
    settings: Optional[dict]
    created_at: datetime
    updated_at: datetime
    user_count: Optional[int] = None
    lead_count: Optional[int] = None
    loan_count: Optional[int] = None

    class Config:
        from_attributes = True


class OrganizationListResponse(BaseModel):
    """Response for listing organizations."""
    organizations: List[OrganizationResponse]
    total: int
    page: int
    page_size: int


class UserAssignment(BaseModel):
    """Schema for assigning user to organization."""
    user_id: int
    backfill_data: bool = True  # Also update user's existing data


class BulkUserAssignment(BaseModel):
    """Schema for bulk assigning users to organization."""
    user_ids: List[int]
    backfill_data: bool = True


# =============================================================================
# Permission Helpers
# =============================================================================

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require platform admin or site_admin role."""
    if current_user.permission_role not in ['admin', 'site_admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def require_platform_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require platform admin role (can manage all organizations)."""
    if current_user.permission_role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin access required"
        )
    return current_user


# =============================================================================
# Routes
# =============================================================================

@router.get("", response_model=OrganizationListResponse)
async def list_organizations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """
    List all organizations (platform admin only).

    - **page**: Page number (starts at 1)
    - **page_size**: Number of results per page
    - **is_active**: Filter by active status
    - **search**: Search by name or slug
    """
    query = db.query(Organization)

    if is_active is not None:
        query = query.filter(Organization.is_active == is_active)

    if search:
        search_filter = f"%{search.lower()}%"
        query = query.filter(
            (func.lower(Organization.name).like(search_filter)) |
            (func.lower(Organization.slug).like(search_filter))
        )

    total = query.count()
    offset = (page - 1) * page_size

    organizations = query.order_by(Organization.name).offset(offset).limit(page_size).all()

    # Add counts for each organization
    org_responses = []
    for org in organizations:
        user_count = db.query(func.count(User.id)).filter(User.organization_id == org.id).scalar()
        lead_count = db.query(func.count(Lead.id)).filter(Lead.organization_id == org.id).scalar()
        loan_count = db.query(func.count(Loan.id)).filter(Loan.organization_id == org.id).scalar()

        org_responses.append(OrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            domain=org.domain,
            subscription_tier=org.subscription_tier,
            is_active=org.is_active,
            settings=org.settings,
            created_at=org.created_at,
            updated_at=org.updated_at,
            user_count=user_count,
            lead_count=lead_count,
            loan_count=loan_count,
        ))

    return OrganizationListResponse(
        organizations=org_responses,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """
    Create a new organization (platform admin only).

    The slug will be auto-generated from the name if not provided.
    """
    # Generate slug if not provided
    slug = data.slug
    if not slug:
        # Create slug from name
        slug = re.sub(r'[^a-z0-9]+', '-', data.name.lower()).strip('-')

    # Check for existing slug
    existing = db.query(Organization).filter(Organization.slug == slug).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Organization with slug '{slug}' already exists"
        )

    # Check for existing domain
    if data.domain:
        existing_domain = db.query(Organization).filter(Organization.domain == data.domain).first()
        if existing_domain:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Organization with domain '{data.domain}' already exists"
            )

    org = Organization(
        name=data.name,
        slug=slug,
        domain=data.domain,
        subscription_tier=data.subscription_tier,
        settings=data.settings or {},
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(org)
    db.commit()
    db.refresh(org)

    logger.info(f"Organization created: {org.name} (slug: {org.slug}) by user {current_user.id}")

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        domain=org.domain,
        subscription_tier=org.subscription_tier,
        is_active=org.is_active,
        settings=org.settings,
        created_at=org.created_at,
        updated_at=org.updated_at,
        user_count=0,
        lead_count=0,
        loan_count=0,
    )


@router.get("/my-organization", response_model=OrganizationResponse)
async def get_my_organization(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the current user's organization.

    Returns organization details for the logged-in user.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No organization assigned"
        )

    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    user_count = db.query(func.count(User.id)).filter(User.organization_id == org.id).scalar()
    lead_count = db.query(func.count(Lead.id)).filter(Lead.organization_id == org.id).scalar()
    loan_count = db.query(func.count(Loan.id)).filter(Loan.organization_id == org.id).scalar()

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        domain=org.domain,
        subscription_tier=org.subscription_tier,
        is_active=org.is_active,
        settings=org.settings,
        created_at=org.created_at,
        updated_at=org.updated_at,
        user_count=user_count,
        lead_count=lead_count,
        loan_count=loan_count,
    )


@router.get("/{org_identifier}", response_model=OrganizationResponse)
async def get_organization(
    org_identifier: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get organization by ID or slug.

    - Platform admins can view any organization
    - Site admins can only view their own organization
    """
    # Try to parse as ID first
    try:
        org_id = int(org_identifier)
        org = db.query(Organization).filter(Organization.id == org_id).first()
    except ValueError:
        # Treat as slug
        org = db.query(Organization).filter(Organization.slug == org_identifier).first()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    # Site admins can only view their own org
    if current_user.permission_role == 'site_admin':
        if org.id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

    user_count = db.query(func.count(User.id)).filter(User.organization_id == org.id).scalar()
    lead_count = db.query(func.count(Lead.id)).filter(Lead.organization_id == org.id).scalar()
    loan_count = db.query(func.count(Loan.id)).filter(Loan.organization_id == org.id).scalar()

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        domain=org.domain,
        subscription_tier=org.subscription_tier,
        is_active=org.is_active,
        settings=org.settings,
        created_at=org.created_at,
        updated_at=org.updated_at,
        user_count=user_count,
        lead_count=lead_count,
        loan_count=loan_count,
    )


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: int,
    data: OrganizationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Update an organization.

    - Platform admins can update any organization
    - Site admins can only update their own organization
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    # Site admins can only update their own org
    if current_user.permission_role == 'site_admin':
        if org.id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        # Site admins cannot change subscription_tier
        if data.subscription_tier is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify subscription tier"
            )

    # Check for domain conflict
    if data.domain and data.domain != org.domain:
        existing = db.query(Organization).filter(
            Organization.domain == data.domain,
            Organization.id != org_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Domain '{data.domain}' is already in use"
            )

    # Update fields
    if data.name is not None:
        org.name = data.name
    if data.domain is not None:
        org.domain = data.domain
    if data.subscription_tier is not None:
        org.subscription_tier = data.subscription_tier
    if data.settings is not None:
        org.settings = data.settings
    if data.is_active is not None:
        org.is_active = data.is_active

    org.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(org)

    logger.info(f"Organization updated: {org.name} (ID: {org.id}) by user {current_user.id}")

    user_count = db.query(func.count(User.id)).filter(User.organization_id == org.id).scalar()
    lead_count = db.query(func.count(Lead.id)).filter(Lead.organization_id == org.id).scalar()
    loan_count = db.query(func.count(Loan.id)).filter(Loan.organization_id == org.id).scalar()

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        domain=org.domain,
        subscription_tier=org.subscription_tier,
        is_active=org.is_active,
        settings=org.settings,
        created_at=org.created_at,
        updated_at=org.updated_at,
        user_count=user_count,
        lead_count=lead_count,
        loan_count=loan_count,
    )


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """
    Delete an organization (platform admin only).

    This will NOT delete associated data - it only marks the organization as inactive.
    For complete data deletion, use the data export/deletion workflow.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    # Check for active users
    user_count = db.query(func.count(User.id)).filter(
        User.organization_id == org_id,
        User.is_active == True
    ).scalar()

    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete organization with {user_count} active users. "
                   "Deactivate or reassign users first."
        )

    # Soft delete - mark as inactive
    org.is_active = False
    org.updated_at = datetime.now(timezone.utc)

    db.commit()

    logger.info(f"Organization soft-deleted: {org.name} (ID: {org.id}) by user {current_user.id}")


@router.post("/{org_id}/users", status_code=status.HTTP_200_OK)
async def assign_user_to_organization(
    org_id: int,
    data: UserAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Assign a user to an organization.

    If backfill_data is True, also updates the user's existing leads, loans, etc.
    to belong to the new organization.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    # Site admins can only assign to their own org
    if current_user.permission_role == 'site_admin':
        if org.id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only assign users to your own organization"
            )

    user = db.query(User).filter(User.id == data.user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    old_org_id = user.organization_id
    user.organization_id = org_id

    # Backfill user's existing data if requested
    if data.backfill_data:
        from services.tenant_isolation import backfill_organization_id_for_user
        backfill_organization_id_for_user(db, user.id, org_id)

    db.commit()

    logger.info(
        f"User {user.id} ({user.email}) assigned to org {org.name} (ID: {org_id}) "
        f"from org {old_org_id} by user {current_user.id}"
    )

    return {
        "message": f"User {user.email} assigned to {org.name}",
        "user_id": user.id,
        "organization_id": org_id,
        "data_backfilled": data.backfill_data,
    }


@router.post("/{org_id}/users/bulk", status_code=status.HTTP_200_OK)
async def bulk_assign_users_to_organization(
    org_id: int,
    data: BulkUserAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Bulk assign multiple users to an organization.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    # Site admins can only assign to their own org
    if current_user.permission_role == 'site_admin':
        if org.id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only assign users to your own organization"
            )

    assigned = []
    errors = []

    for user_id in data.user_ids:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            errors.append({"user_id": user_id, "error": "User not found"})
            continue

        user.organization_id = org_id

        if data.backfill_data:
            from services.tenant_isolation import backfill_organization_id_for_user
            try:
                backfill_organization_id_for_user(db, user.id, org_id)
            except Exception as e:
                errors.append({"user_id": user_id, "error": "Backfill failed"})

        assigned.append({"user_id": user_id, "email": user.email})

    db.commit()

    logger.info(
        f"Bulk assigned {len(assigned)} users to org {org.name} (ID: {org_id}) "
        f"by user {current_user.id}. Errors: {len(errors)}"
    )

    return {
        "message": f"Assigned {len(assigned)} users to {org.name}",
        "organization_id": org_id,
        "assigned": assigned,
        "errors": errors,
    }


@router.get("/{org_id}/users")
async def get_organization_users(
    org_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get users belonging to an organization.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    # Site admins can only view their own org
    if current_user.permission_role == 'site_admin':
        if org.id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

    query = db.query(User).filter(User.organization_id == org_id)

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    total = query.count()
    offset = (page - 1) * page_size

    users = query.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()

    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "permission_role": u.permission_role,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{org_id}/stats")
async def get_organization_stats(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get statistics for an organization.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    # Site admins can only view their own org
    if current_user.permission_role == 'site_admin':
        if org.id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

    # Count users
    total_users = db.query(func.count(User.id)).filter(User.organization_id == org_id).scalar()
    active_users = db.query(func.count(User.id)).filter(
        User.organization_id == org_id,
        User.is_active == True
    ).scalar()

    # Count leads
    total_leads = db.query(func.count(Lead.id)).filter(Lead.organization_id == org_id).scalar()

    # Count loans
    total_loans = db.query(func.count(Loan.id)).filter(Loan.organization_id == org_id).scalar()

    # Count branches
    total_branches = db.query(func.count(Branch.id)).filter(Branch.organization_id == org_id).scalar()

    return {
        "organization_id": org_id,
        "organization_name": org.name,
        "subscription_tier": org.subscription_tier,
        "is_active": org.is_active,
        "stats": {
            "total_users": total_users,
            "active_users": active_users,
            "total_leads": total_leads,
            "total_loans": total_loans,
            "total_branches": total_branches,
        },
    }
