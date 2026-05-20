"""
SSL Certificate Routes

API endpoints for managing SSL certificates for custom domains.
Integrates with Let's Encrypt for automatic certificate issuance.

Usage Flow:
1. Domain must be verified first (via /api/admin/domains)
2. Request certificate via POST /api/admin/ssl/{domain}/request
3. Set up challenge response (HTTP file or DNS record)
4. Complete challenge via POST /api/admin/ssl/{domain}/complete
5. Certificate is issued and stored
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import text, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from routes.auth_deps import require_auth

router = APIRouter(prefix="/api/admin/ssl", tags=["SSL Certificates"], dependencies=[Depends(require_auth)])


# ============================================================================
# Schemas
# ============================================================================

class ChallengeType(str, Enum):
    HTTP_01 = "http-01"
    DNS_01 = "dns-01"


class CertificateRequest(BaseModel):
    challenge_type: ChallengeType = ChallengeType.HTTP_01
    san_domains: Optional[List[str]] = None


class CertificateStatusResponse(BaseModel):
    domain: str
    status: str
    issued_at: Optional[str] = None
    expires_at: Optional[str] = None
    days_until_expiry: Optional[int] = None
    is_valid: bool = False
    needs_renewal: bool = False
    issuer: Optional[str] = None
    fingerprint_sha256: Optional[str] = None
    san_domains: List[str] = []
    error_message: Optional[str] = None


class ChallengeDetailsResponse(BaseModel):
    domain: str
    challenge_type: str
    token: str

    # HTTP-01 challenge
    http_path: Optional[str] = None
    http_content: Optional[str] = None

    # DNS-01 challenge
    dns_record_name: Optional[str] = None
    dns_record_value: Optional[str] = None

    instructions: List[str] = []


class SSLCheckResponse(BaseModel):
    domain: str
    ssl_working: bool
    certificate: Optional[Dict[str, Any]] = None
    errors: List[str] = []


# ============================================================================
# Helper Functions
# ============================================================================

async def verify_domain_ownership(domain: str, db: Session) -> bool:
    """Check if domain is verified in our system."""
    result = db.execute(text("""
        SELECT is_verified FROM custom_domains
        WHERE domain = :domain AND is_active = true
    """), {"domain": domain}).fetchone()

    return result and result[0]


async def update_ssl_status(domain: str, ssl_status: str, db: Session):
    """Update SSL status in custom_domains table."""
    db.execute(text("""
        UPDATE custom_domains
        SET ssl_status = :status, updated_at = CURRENT_TIMESTAMP
        WHERE domain = :domain
    """), {"domain": domain, "status": ssl_status})
    db.commit()


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/{domain}/request", response_model=ChallengeDetailsResponse)
async def request_certificate(
    domain: str,
    request: CertificateRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Request a new SSL certificate for a domain.

    The domain must be verified first via /api/admin/domains.
    Returns challenge details that must be set up before completing.

    For HTTP-01: Create a file at the specified path with the specified content
    For DNS-01: Create a TXT record with the specified name and value
    """
    from services.ssl_certificate_service import (
        ssl_certificate_service,
        ChallengeType as ServiceChallengeType
    )

    # Verify domain ownership
    if not await verify_domain_ownership(domain, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Domain {domain} is not verified. Please verify it first."
        )

    try:
        # Map challenge type
        challenge_type = ServiceChallengeType(request.challenge_type.value)

        # Request certificate
        cert_info = await ssl_certificate_service.request_certificate(
            domain=domain,
            challenge_type=challenge_type,
            san_domains=request.san_domains
        )

        # Get challenge details
        challenge = ssl_certificate_service.get_challenge_details(domain)

        if not challenge:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get challenge details"
            )

        # Update SSL status in database
        await update_ssl_status(domain, "challenge_pending", db)

        # Build response with instructions
        instructions = []

        if challenge.type == ServiceChallengeType.HTTP_01:
            instructions = [
                f"Create a file accessible at: http://{domain}{challenge.http_path}",
                f"File content should be exactly: {challenge.http_content}",
                "",
                "Example (nginx):",
                f"  location = {challenge.http_path} {{",
                f"      return 200 '{challenge.http_content}';",
                "  }",
                "",
                "Once the file is accessible, call POST /api/admin/ssl/{domain}/complete"
            ]
        else:  # DNS-01
            instructions = [
                f"Create a DNS TXT record:",
                f"  Name: {challenge.dns_record_name}",
                f"  Value: {challenge.dns_record_value}",
                "",
                "Wait for DNS propagation (may take up to 48 hours)",
                "Then call POST /api/admin/ssl/{domain}/complete"
            ]

        return {
            "domain": domain,
            "challenge_type": challenge.type.value,
            "token": challenge.token,
            "http_path": challenge.http_path,
            "http_content": challenge.http_content,
            "dns_record_name": challenge.dns_record_name,
            "dns_record_value": challenge.dns_record_value,
            "instructions": instructions
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to request certificate"
        )


@router.post("/{domain}/complete", response_model=CertificateStatusResponse)
async def complete_certificate(
    domain: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Complete the certificate challenge and issue the certificate.

    Call this after setting up the HTTP file or DNS record
    as specified in the challenge details.
    """
    from services.ssl_certificate_service import ssl_certificate_service

    try:
        # Complete the challenge
        cert_info = await ssl_certificate_service.complete_challenge(domain)

        # Update SSL status in database
        if cert_info.status.value == "issued":
            await update_ssl_status(domain, "active", db)
        else:
            await update_ssl_status(domain, cert_info.status.value, db)

        return {
            "domain": cert_info.domain,
            "status": cert_info.status.value,
            "issued_at": cert_info.issued_at.isoformat() if cert_info.issued_at else None,
            "expires_at": cert_info.expires_at.isoformat() if cert_info.expires_at else None,
            "days_until_expiry": cert_info.days_until_expiry,
            "is_valid": cert_info.is_valid,
            "needs_renewal": cert_info.needs_renewal,
            "issuer": cert_info.issuer,
            "fingerprint_sha256": cert_info.fingerprint_sha256,
            "san_domains": cert_info.san_domains,
            "error_message": cert_info.error_message
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request"
        )
    except Exception as e:
        await update_ssl_status(domain, "failed", db)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete certificate"
        )


@router.get("/{domain}/status", response_model=CertificateStatusResponse)
async def get_certificate_status(
    domain: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get the current SSL certificate status for a domain.

    Returns certificate details if issued, or pending status.
    """
    from services.ssl_certificate_service import ssl_certificate_service

    try:
        cert_info = ssl_certificate_service.get_certificate_status(domain)

        return {
            "domain": cert_info.domain,
            "status": cert_info.status.value,
            "issued_at": cert_info.issued_at.isoformat() if cert_info.issued_at else None,
            "expires_at": cert_info.expires_at.isoformat() if cert_info.expires_at else None,
            "days_until_expiry": cert_info.days_until_expiry,
            "is_valid": cert_info.is_valid,
            "needs_renewal": cert_info.needs_renewal,
            "issuer": cert_info.issuer,
            "fingerprint_sha256": cert_info.fingerprint_sha256,
            "san_domains": cert_info.san_domains,
            "error_message": cert_info.error_message
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get certificate status"
        )


@router.get("/{domain}/check", response_model=SSLCheckResponse)
async def check_live_ssl(domain: str):
    """
    Check the live SSL status of a domain.

    Makes an actual HTTPS connection to verify SSL is working.
    """
    from services.ssl_certificate_service import ssl_certificate_service

    try:
        result = await ssl_certificate_service.check_domain_ssl(domain)
        return result

    except Exception as e:
        return {
            "domain": domain,
            "ssl_working": False,
            "certificate": None,
            "errors": [str(e)]
        }


@router.post("/{domain}/renew", response_model=CertificateStatusResponse)
async def renew_certificate(
    domain: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Manually trigger certificate renewal for a domain.

    This will request a new certificate even if current one is still valid.
    """
    from services.ssl_certificate_service import ssl_certificate_service, ChallengeType

    # Verify domain ownership
    if not await verify_domain_ownership(domain, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Domain {domain} is not verified."
        )

    try:
        # Get current certificate info for SAN domains
        current = ssl_certificate_service.get_certificate_status(domain)

        # Request new certificate
        await update_ssl_status(domain, "renewing", db)

        cert_info = await ssl_certificate_service.request_certificate(
            domain=domain,
            challenge_type=ChallengeType.HTTP_01,
            san_domains=current.san_domains if current.san_domains else None
        )

        return {
            "domain": cert_info.domain,
            "status": cert_info.status.value,
            "issued_at": cert_info.issued_at.isoformat() if cert_info.issued_at else None,
            "expires_at": cert_info.expires_at.isoformat() if cert_info.expires_at else None,
            "days_until_expiry": cert_info.days_until_expiry,
            "is_valid": cert_info.is_valid,
            "needs_renewal": cert_info.needs_renewal,
            "issuer": cert_info.issuer,
            "fingerprint_sha256": cert_info.fingerprint_sha256,
            "san_domains": cert_info.san_domains,
            "error_message": cert_info.error_message
        }

    except Exception as e:
        await update_ssl_status(domain, "failed", db)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to renew certificate"
        )


@router.post("/renew-all")
async def renew_all_expiring(
    threshold_days: int = 30,
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Trigger renewal for all certificates expiring within threshold.

    This is typically called by a scheduled job.
    """
    from services.ssl_certificate_service import ssl_certificate_service

    try:
        renewed = await ssl_certificate_service.renew_expiring_certificates(
            threshold_days=threshold_days
        )

        return {
            "success": True,
            "renewed_count": len(renewed),
            "renewed_domains": [c.domain for c in renewed]
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to renew certificates"
        )


@router.get("/{domain}/download")
async def download_certificate(
    domain: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get the certificate and private key paths for a domain.

    Returns paths to the certificate files for server configuration.
    """
    from services.ssl_certificate_service import ssl_certificate_service

    # Verify domain ownership
    if not await verify_domain_ownership(domain, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Domain {domain} is not verified."
        )

    files = ssl_certificate_service.get_certificate_files(domain)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No certificate found for {domain}"
        )

    return {
        "domain": domain,
        "certificate_path": files["certificate"],
        "private_key_path": files["private_key"],
        "note": "These are server-side paths. Configure your reverse proxy to use these files."
    }


@router.get("/expiring")
async def list_expiring_certificates(
    threshold_days: int = 30,
    db: AsyncSession = Depends(get_async_db)
):
    """
    List all certificates expiring within threshold.

    Useful for monitoring and alerting.
    """
    from services.ssl_certificate_service import ssl_certificate_service
    from pathlib import Path

    expiring = []
    storage_path = ssl_certificate_service.storage_path

    for cert_file in Path(storage_path).glob("*.crt"):
        domain = cert_file.stem
        cert_info = ssl_certificate_service.get_certificate_status(domain)

        if cert_info.days_until_expiry is not None and cert_info.days_until_expiry <= threshold_days:
            expiring.append({
                "domain": domain,
                "expires_at": cert_info.expires_at.isoformat() if cert_info.expires_at else None,
                "days_until_expiry": cert_info.days_until_expiry,
                "status": cert_info.status.value
            })

    # Sort by days until expiry
    expiring.sort(key=lambda x: x["days_until_expiry"] or 0)

    return {
        "threshold_days": threshold_days,
        "count": len(expiring),
        "certificates": expiring
    }
