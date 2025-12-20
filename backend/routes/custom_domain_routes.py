"""
Custom Domain Routes

API endpoints for managing custom domains.
Allows admins to add, remove, verify, and list custom domains.

Verification Flow:
1. User adds domain via POST /api/admin/domains
2. System generates verification token
3. User adds TXT record to their DNS
4. User calls POST /api/admin/domains/{domain}/verify-dns
5. System checks TXT record and DNS configuration
6. Domain is marked as verified if all checks pass
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
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
    verification_token: Optional[str] = None
    organization_id: Optional[int]
    user_id: Optional[int]
    created_at: Optional[str]
    verified_at: Optional[str] = None

    class Config:
        from_attributes = True


class DomainListResponse(BaseModel):
    domains: List[DomainResponse]
    total: int


class VerificationInstructions(BaseModel):
    domain: str
    verification_token: str
    txt_record_name: str
    txt_record_value: str
    cname_target: str
    a_record_ip: str
    instructions: List[str]


class VerificationResult(BaseModel):
    domain: str
    fully_verified: bool
    ownership_verified: bool
    dns_configured: bool
    txt_verification: Dict[str, Any]
    dns_verification: Dict[str, Any]
    next_steps: List[Dict[str, Any]]


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

    This creates the domain entry with a verification token.
    The domain is NOT immediately active - it must be verified first.

    Steps after adding:
    1. Get verification instructions via GET /api/admin/domains/{domain}/verification-instructions
    2. Add TXT record to your DNS
    3. Configure CNAME or A record
    4. Verify via POST /api/admin/domains/{domain}/verify-dns
    """
    from sqlalchemy import text
    from services.dns_verification_service import dns_verification_service

    # Clean domain (remove protocol if provided)
    domain = domain_data.domain.lower().strip()
    if domain.startswith("https://"):
        domain = domain[8:]
    if domain.startswith("http://"):
        domain = domain[7:]

    try:
        # Check if already exists
        existing = db.execute(text(
            "SELECT id FROM custom_domains WHERE domain = :domain"
        ), {"domain": domain}).fetchone()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Domain {domain} already exists"
            )

        # Generate verification token
        verification_token = dns_verification_service.generate_verification_token(domain)

        # Insert new domain with verification token (not verified yet)
        db.execute(text("""
            INSERT INTO custom_domains
            (domain, user_id, organization_id, is_active, is_verified, verification_token, notes, created_at)
            VALUES (:domain, :user_id, :org_id, true, false, :token, :notes, CURRENT_TIMESTAMP)
        """), {
            "domain": domain,
            "user_id": domain_data.user_id,
            "org_id": domain_data.organization_id,
            "token": verification_token,
            "notes": domain_data.notes
        })
        db.commit()

        # Get the inserted domain
        result = db.execute(text("""
            SELECT id, domain, is_verified, is_active, ssl_status, verification_token,
                   organization_id, user_id, created_at, verified_at
            FROM custom_domains WHERE domain = :domain
        """), {"domain": domain}).fetchone()

        return {
            "id": result[0],
            "domain": result[1],
            "is_verified": result[2],
            "is_active": result[3],
            "ssl_status": result[4],
            "verification_token": result[5],
            "organization_id": result[6],
            "user_id": result[7],
            "created_at": result[8].isoformat() if result[8] else None,
            "verified_at": result[9].isoformat() if result[9] else None
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
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


@router.get("/{domain}/verification-instructions", response_model=VerificationInstructions)
async def get_verification_instructions(domain: str, db: Session = Depends(get_db)):
    """
    Get DNS verification instructions for a domain.

    Returns the TXT record and CNAME/A record configuration needed
    to verify domain ownership and configure routing.
    """
    from sqlalchemy import text
    from services.dns_verification_service import dns_verification_service

    try:
        # Get domain and verification token
        result = db.execute(text("""
            SELECT domain, verification_token, is_verified
            FROM custom_domains
            WHERE domain = :domain
        """), {"domain": domain}).fetchone()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Domain {domain} not found"
            )

        domain_name = result[0]
        verification_token = result[1]
        is_verified = result[2]

        # If no token exists, generate one
        if not verification_token:
            verification_token = dns_verification_service.generate_verification_token(domain_name)
            db.execute(text("""
                UPDATE custom_domains
                SET verification_token = :token
                WHERE domain = :domain
            """), {"token": verification_token, "domain": domain_name})
            db.commit()

        txt_record_name = dns_verification_service.get_txt_record_name(domain_name)

        instructions = [
            f"Step 1: Add a TXT record to verify domain ownership",
            f"   Record Name: {txt_record_name}",
            f"   Record Value: {verification_token}",
            f"",
            f"Step 2: Configure DNS to point to our servers (choose one):",
            f"   Option A - CNAME Record (recommended):",
            f"      Name: {domain_name}",
            f"      Value: {dns_verification_service.EXPECTED_CNAME_TARGETS[0]}",
            f"",
            f"   Option B - A Record:",
            f"      Name: {domain_name}",
            f"      Value: {dns_verification_service.EXPECTED_A_RECORDS[0]}",
            f"",
            f"Step 3: Wait for DNS propagation (up to 48 hours, usually faster)",
            f"",
            f"Step 4: Verify your domain at POST /api/admin/domains/{domain_name}/verify-dns"
        ]

        if is_verified:
            instructions.insert(0, "✓ This domain is already verified!")

        return {
            "domain": domain_name,
            "verification_token": verification_token,
            "txt_record_name": txt_record_name,
            "txt_record_value": verification_token,
            "cname_target": dns_verification_service.EXPECTED_CNAME_TARGETS[0],
            "a_record_ip": dns_verification_service.EXPECTED_A_RECORDS[0],
            "instructions": instructions
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get verification instructions: {str(e)}"
        )


@router.post("/{domain}/verify-dns", response_model=VerificationResult)
async def verify_domain_dns(domain: str, db: Session = Depends(get_db)):
    """
    Perform DNS verification for a domain.

    Checks:
    1. TXT record for ownership verification
    2. CNAME or A record for DNS configuration

    If both pass, the domain is marked as verified.
    """
    from sqlalchemy import text
    from services.dns_verification_service import dns_verification_service

    try:
        # Get domain and verification token
        result = db.execute(text("""
            SELECT domain, verification_token, is_verified
            FROM custom_domains
            WHERE domain = :domain
        """), {"domain": domain}).fetchone()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Domain {domain} not found"
            )

        domain_name = result[0]
        verification_token = result[1]

        if not verification_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No verification token found. Get instructions first."
            )

        # Perform full verification
        verification_result = dns_verification_service.perform_full_verification(
            domain=domain_name,
            verification_token=verification_token
        )

        # If fully verified, update database
        if verification_result["fully_verified"]:
            db.execute(text("""
                UPDATE custom_domains
                SET is_verified = true,
                    verified_at = CURRENT_TIMESTAMP,
                    ssl_status = 'pending'
                WHERE domain = :domain
            """), {"domain": domain_name})
            db.commit()

            # Refresh the domain cache
            from services.custom_domain_service import get_domain_service
            get_domain_service()._refresh_cache()

        return verification_result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify domain: {str(e)}"
        )


@router.post("/{domain}/verify")
async def verify_domain_manual(domain: str, db: Session = Depends(get_db)):
    """
    Manually mark a domain as verified (admin override).

    Use this only for domains that have been verified through
    other means (e.g., direct communication with domain owner).
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

        # Refresh the domain cache
        from services.custom_domain_service import get_domain_service
        get_domain_service()._refresh_cache()

        return {"success": True, "message": f"Domain {domain} manually verified"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify domain: {str(e)}"
        )


@router.get("/{domain}/status")
async def get_domain_status(domain: str, db: Session = Depends(get_db)):
    """
    Get detailed status of a domain including DNS verification status.

    Performs real-time DNS checks to show current configuration.
    """
    from sqlalchemy import text
    from services.dns_verification_service import dns_verification_service

    try:
        # Get domain from database
        result = db.execute(text("""
            SELECT id, domain, is_verified, is_active, ssl_status,
                   verification_token, verified_at, created_at,
                   organization_id, user_id
            FROM custom_domains
            WHERE domain = :domain
        """), {"domain": domain}).fetchone()

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Domain {domain} not found"
            )

        domain_info = {
            "id": result[0],
            "domain": result[1],
            "is_verified": result[2],
            "is_active": result[3],
            "ssl_status": result[4],
            "verification_token": result[5],
            "verified_at": result[6].isoformat() if result[6] else None,
            "created_at": result[7].isoformat() if result[7] else None,
            "organization_id": result[8],
            "user_id": result[9]
        }

        # Perform live DNS checks
        dns_config = dns_verification_service.verify_dns_configuration(result[1])
        reachability = dns_verification_service.check_domain_reachability(result[1])

        # Check TXT record if we have a token
        txt_status = None
        if result[5]:
            txt_result = dns_verification_service.verify_txt_record(result[1], result[5])
            txt_status = txt_result.to_dict()

        return {
            "domain": domain_info,
            "dns_configuration": dns_config.to_dict(),
            "txt_verification": txt_status,
            "reachability": reachability,
            "ready_for_traffic": domain_info["is_verified"] and dns_config.success
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get domain status: {str(e)}"
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
