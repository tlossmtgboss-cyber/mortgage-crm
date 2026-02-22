"""
Tenant Management API Routes
Provides endpoints for creating, managing, and deleting tenants.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
import logging

from services.tenant_provisioning_service import tenant_provisioning_service
from models.tenant import Tenant
from database import get_master_db

logger = logging.getLogger(__name__)


def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/tenants",
    tags=["tenants"],
    dependencies=[Depends(_get_current_user())],
)


# Pydantic Models
class TenantCreateRequest(BaseModel):
    organization_name: str = Field(..., min_length=3, max_length=100, description="Organization name")
    subdomain: str = Field(..., min_length=3, max_length=63, description="Subdomain for tenant access")
    admin_email: Optional[str] = Field(None, description="Admin email address")
    
    class Config:
        json_schema_extra = {
            "example": {
                "organization_name": "Acme Corporation",
                "subdomain": "acme",
                "admin_email": "admin@acme.com"
            }
        }


class TenantResponse(BaseModel):
    id: str
    organization_name: str
    subdomain: str
    database_name: str
    is_active: bool
    created_at: str
    
    class Config:
        from_attributes = True


class TenantListResponse(BaseModel):
    tenants: List[TenantResponse]
    total: int


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreateRequest,
    db: Session = Depends(get_master_db)
):
    """
    Create a new tenant with its own isolated database.
    
    - **organization_name**: Name of the organization
    - **subdomain**: Subdomain for accessing the tenant (e.g., 'acme' for acme.yourdomain.com)
    - **admin_email**: Optional admin email address
    
    Returns the created tenant information.
    """
    try:
        logger.info(f"Creating tenant: {tenant_data.subdomain}")
        
        # Create tenant using provisioning service
        tenant = await tenant_provisioning_service.create_tenant(
            organization_name=tenant_data.organization_name,
            subdomain=tenant_data.subdomain,
            master_db_session=db
        )
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create tenant. Subdomain may already exist or database creation failed."
            )
        
        logger.info(f"Successfully created tenant: {tenant.subdomain}")
        return tenant
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating tenant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while creating tenant"
        )


@router.get("/", response_model=TenantListResponse)
def list_tenants(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    db: Session = Depends(get_master_db)
):
    """
    List all tenants with pagination.
    
    - **skip**: Number of records to skip (for pagination)
    - **limit**: Maximum number of records to return
    - **active_only**: Filter to only show active tenants
    """
    try:
        query = db.query(Tenant)
        
        if active_only:
            query = query.filter(Tenant.is_active == True)
        
        total = query.count()
        tenants = query.offset(skip).limit(limit).all()
        
        return {
            "tenants": tenants,
            "total": total
        }
    except Exception as e:
        logger.error(f"Error listing tenants: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while listing tenants"
        )


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(
    tenant_id: str,
    db: Session = Depends(get_master_db)
):
    """
    Get detailed information about a specific tenant.
    
    - **tenant_id**: UUID of the tenant
    """
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant with ID {tenant_id} not found"
            )
        
        return tenant
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving tenant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving tenant"
        )


@router.get("/subdomain/{subdomain}", response_model=TenantResponse)
def get_tenant_by_subdomain(
    subdomain: str,
    db: Session = Depends(get_master_db)
):
    """
    Get tenant information by subdomain.
    
    - **subdomain**: Subdomain of the tenant
    """
    try:
        tenant = db.query(Tenant).filter(Tenant.subdomain == subdomain).first()
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant with subdomain '{subdomain}' not found"
            )
        
        return tenant
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving tenant by subdomain: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving tenant"
        )


@router.patch("/{tenant_id}/toggle-status")
async def toggle_tenant_status(
    tenant_id: str,
    db: Session = Depends(get_master_db)
):
    """
    Toggle tenant active status (enable/disable).
    
    - **tenant_id**: UUID of the tenant
    """
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant with ID {tenant_id} not found"
            )
        
        tenant.is_active = not tenant.is_active
        db.commit()
        db.refresh(tenant)
        
        logger.info(f"Toggled tenant {tenant.subdomain} status to: {tenant.is_active}")
        
        return {
            "message": f"Tenant {'activated' if tenant.is_active else 'deactivated'} successfully",
            "tenant": tenant
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling tenant status: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while updating tenant status"
        )


@router.delete("/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    confirm: bool = False,
    db: Session = Depends(get_master_db)
):
    """
    Delete a tenant and its database. THIS ACTION IS IRREVERSIBLE!
    
    - **tenant_id**: UUID of the tenant
    - **confirm**: Must be set to true to confirm deletion
    """
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deletion must be confirmed by setting confirm=true"
        )
    
    try:
        success = await tenant_provisioning_service.delete_tenant(
            tenant_id=tenant_id,
            master_db_session=db
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found or deletion failed"
            )
        
        logger.info(f"Successfully deleted tenant: {tenant_id}")
        
        return {
            "message": "Tenant and its database deleted successfully",
            "tenant_id": tenant_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting tenant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while deleting tenant"
        )
