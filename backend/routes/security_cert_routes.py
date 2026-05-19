"""
Security Certificate Pinning Routes

GET  /api/v1/security/certificate-pins — Return current SPKI pin hashes per domain
POST /api/v1/security/pin-failure      — Receive pin validation failure reports from iOS

The GET endpoint returns a JSON object shaped as { domain: PinnedDomainConfig }
so the iOS CertificatePinning.swift RemotePinManager can decode it directly as
`[String: PinnedDomainConfig]`.  Each PinnedDomainConfig has:
    spkiHashes: [String]       — base64-encoded SHA-256 SPKI hashes
    includeSubdomains: Bool
    notAfter: String?          — ISO 8601 pin expiry (serves as expires_at)

Pin hashes are configurable via environment variables:
    CERT_PIN_PRIMARY   — primary leaf-cert SPKI hash for api.perenniaai.com
    CERT_PIN_BACKUP    — backup/CA SPKI hash shared across domains

The POST endpoint is intentionally unauthenticated because the iOS app may be
unable to establish a TLS session (and therefore authenticate) when pins fail.
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user_flexible
from db import get_db
from services.audit_events import audit_event
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/security",
    tags=["security"],
)

# ---------------------------------------------------------------------------
# Default pin hashes — overridden by env vars in production
# ---------------------------------------------------------------------------

# Railway / Let's Encrypt defaults matching CertificatePinning.swift hardcoded values
_DEFAULT_PRIMARY_API = "STrmUQMdkvmuC5EJ/5StR+WXmwAq6RLFCIPe3rMVgPA="
_DEFAULT_PRIMARY_APP = "amKlKR/XR507OEn640jX8dUOfmFxM+fz1umrpwlbi5s="
_DEFAULT_BACKUP_ISRG = "C5+lpZ7tcVwmwQIMcRtPbsQtWLABXhQzejna0wHFr8M="   # ISRG Root X1
_DEFAULT_BACKUP_LE_R3 = "jQJTbIh0grw0/1TkHSumWb+Fs0Ggogr621gT3PvPKG0="  # Let's Encrypt R3


def _build_pin_config() -> dict:
    """Build the pin configuration dict from environment variables.

    Environment variables:
        CERT_PIN_PRIMARY     — overrides the api.perenniaai.com leaf-cert pin
        CERT_PIN_PRIMARY_APP — overrides the app.perenniaai.com leaf-cert pin
        CERT_PIN_BACKUP      — overrides the ISRG Root X1 backup pin
        CERT_PIN_BACKUP_LE   — overrides the Let's Encrypt R3 backup pin
        CERT_PIN_EXPIRY_DAYS — days until notAfter (default: 90)
    """
    primary_api = os.environ.get("CERT_PIN_PRIMARY", _DEFAULT_PRIMARY_API)
    primary_app = os.environ.get("CERT_PIN_PRIMARY_APP", _DEFAULT_PRIMARY_APP)
    backup_isrg = os.environ.get("CERT_PIN_BACKUP", _DEFAULT_BACKUP_ISRG)
    backup_le = os.environ.get("CERT_PIN_BACKUP_LE", _DEFAULT_BACKUP_LE_R3)

    expiry_days = int(os.environ.get("CERT_PIN_EXPIRY_DAYS", "90"))
    not_after = (
        datetime.now(timezone.utc) + timedelta(days=expiry_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "api.perenniaai.com": {
            "spkiHashes": [primary_api, backup_isrg, backup_le],
            "includeSubdomains": True,
            "notAfter": not_after,
        },
        "app.perenniaai.com": {
            "spkiHashes": [primary_app, backup_isrg, backup_le],
            "includeSubdomains": True,
            "notAfter": not_after,
        },
    }


# ---------------------------------------------------------------------------
# GET /api/v1/security/certificate-pins
# ---------------------------------------------------------------------------

@router.get("/certificate-pins")
async def get_certificate_pins(
    request: Request,
    user=Depends(get_current_user_flexible),
    db: AsyncSession = Depends(get_async_db),
):
    """Return current SPKI pin hashes for the app's pinned domains.

    Response body is a flat JSON object keyed by domain, matching the
    iOS PinnedDomainConfig Codable struct so RemotePinManager can
    decode it directly as `[String: PinnedDomainConfig]`.
    """
    pins = _build_pin_config()

    # Audit the pin fetch (informational, not security-critical)
    try:
        user_id = getattr(user, "id", None) if user else None
        audit_event(
            db,
            event_type="CERTIFICATE_PINS_FETCHED",
            outcome="success",
            actor_id=user_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            metadata={"domains": list(pins.keys())},
        )
        await db.commit()
    except Exception as e:
        logger.warning("Failed to audit certificate-pins fetch: %s", e)

    return pins


# ---------------------------------------------------------------------------
# POST /api/v1/security/pin-failure
# ---------------------------------------------------------------------------

class PinFailureReport(BaseModel):
    domain: str
    reason: str = "pin_mismatch"
    receivedHashes: List[str] = Field(default_factory=list)
    timestamp: Optional[str] = None
    platform: Optional[str] = None
    appVersion: Optional[str] = None


class PinFailureDeviceInfo(BaseModel):
    platform: Optional[str] = None
    isNative: Optional[bool] = None
    osVersion: Optional[str] = None
    model: Optional[str] = None


class PinFailureRequest(BaseModel):
    """Matches the JSON payload from CertificatePinning.swift reportFailure()."""
    reports: List[PinFailureReport]
    deviceInfo: Optional[PinFailureDeviceInfo] = None


@router.post("/pin-failure")
async def report_pin_failure(
    payload: PinFailureRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Receive certificate pin validation failure reports from the iOS app.

    This endpoint is intentionally unauthenticated — if certificate pins
    are failing, the app cannot establish a trusted TLS session and therefore
    cannot obtain or present a valid JWT.

    Each report is logged as a SECURITY-CRITICAL audit event.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    device = payload.deviceInfo.dict() if payload.deviceInfo else {}

    for report in payload.reports:
        logger.warning(
            "CERTIFICATE PIN FAILURE — domain=%s reason=%s ip=%s platform=%s hashes=%s",
            report.domain,
            report.reason,
            client_ip,
            report.platform or device.get("platform", "unknown"),
            ", ".join(report.receivedHashes[:5]),
        )

        try:
            audit_event(
                db,
                event_type="CERTIFICATE_PIN_FAILURE",
                outcome="failure",
                ip=client_ip,
                user_agent=user_agent,
                resource_type="certificate_pin",
                resource_id=report.domain,
                metadata={
                    "domain": report.domain,
                    "reason": report.reason,
                    "received_hashes": report.receivedHashes[:5],
                    "report_timestamp": report.timestamp,
                    "platform": report.platform,
                    "app_version": report.appVersion,
                    "device_info": device,
                },
            )
        except Exception as e:
            logger.exception(
                "Failed to persist pin-failure audit event for %s: %s",
                report.domain,
                e,
            )

    try:
        await db.commit()
    except Exception as e:
        logger.exception("Failed to commit pin-failure audit events: %s", e)

    return {
        "status": "received",
        "count": len(payload.reports),
    }


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_security_cert_routes(app):
    """Register the certificate pinning routes with the FastAPI app."""
    app.include_router(router)
    logger.info("Registered security certificate pinning routes")
