"""
Custom Domain Routes

API endpoints for managing custom domains.
Allows admins to add, remove, and list custom domains.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from database import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/admin/domains", tags=["Custom Domains"])


# ============================================================================
# Schemas
# ============================================================================

class DomainCreate(BaseModel):
    domain: str  # e.g., "www.timloss.com" (without https://)
    organization_id: Optional[int] = None
    user_id: Optional[int] = None
    notes: Optional[str] = None


class DomainResponse(BaseModel):
    id: int
    domain: str
    is_verified: bool
    is_active: bool
    ssl_status: str
    organization_id: Optional[int]
    user_id: Optional[int]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class DomainListResponse(BaseModel):
    domains: List[DomainResponse]
    total: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=DomainListResponse)
async def list_domains(db: Session = Depends(get_db)):
    """
    List all custom domains.

    Returns all configured custom domains with their status.
    """
    try:
        from services.custom_domain_service import get_domain_service
        service = get_domain_service()
        domains = service.list_domains()

        return {
            "domains": domains,
            "total": len(domains)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list domains: {str(e)}"
        )


@router.post("", response_model=DomainResponse)
async def add_domain(
    domain_data: DomainCreate,
    db: Session = Depends(get_db)
):
    """
    Add a new custom domain.

    The domain will be immediately active for CORS.
    Make sure to:
    1. Add the domain to Vercel
    2. Configure DNS to point to Vercel
    """
    # Clean domain (remove protocol if provided)
    domain = domain_data.domain.lower().strip()
    if domain.startswith("https://"):
        domain = domain[8:]
    if domain.startswith("http://"):
        domain = domain[7:]

    try:
        from services.custom_domain_service import get_domain_service
        service = get_domain_service()

        success = service.add_domain(
            domain=domain,
            user_id=domain_data.user_id,
            organization_id=domain_data.organization_id
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Domain {domain} already exists"
            )

        # Return the new domain info
        domains = service.list_domains()
        for d in domains:
            if d["domain"] == domain:
                return d

        return {
            "id": 0,
            "domain": domain,
            "is_verified": True,
            "is_active": True,
            "ssl_status": "pending",
            "organization_id": domain_data.organization_id,
            "user_id": domain_data.user_id,
            "created_at": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add domain: {str(e)}"
        )


@router.delete("/{domain}")
async def remove_domain(domain: str, db: Session = Depends(get_db)):
    """
    Remove (deactivate) a custom domain.

    The domain will no longer be allowed for CORS.
    """
    try:
        from services.custom_domain_service import get_domain_service
        service = get_domain_service()

        success = service.remove_domain(domain)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Domain {domain} not found"
            )

        return {"success": True, "message": f"Domain {domain} deactivated"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove domain: {str(e)}"
        )


@router.post("/{domain}/verify")
async def verify_domain(domain: str, db: Session = Depends(get_db)):
    """
    Mark a domain as verified.

    In a production system, this would check DNS/TXT records.
    For now, it just marks the domain as verified.
    """
    from sqlalchemy import text

    try:
        result = db.execute(text("""
            UPDATE custom_domains
            SET is_verified = true, verified_at = CURRENT_TIMESTAMP
            WHERE domain = :domain
        """), {"domain": domain})
        db.commit()

        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Domain {domain} not found"
            )

        return {"success": True, "message": f"Domain {domain} verified"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify domain: {str(e)}"
        )


@router.get("/check/{origin}")
async def check_origin(origin: str):
    """
    Check if an origin is allowed (for debugging).

    Pass the full origin (e.g., https://www.timloss.com).
    """
    try:
        from services.custom_domain_service import get_domain_service
        service = get_domain_service()

        is_allowed = service.is_allowed_origin(origin)

        return {
            "origin": origin,
            "is_allowed": is_allowed
        }

    except Exception as e:
        return {
            "origin": origin,
            "is_allowed": False,
            "error": str(e)
        }
