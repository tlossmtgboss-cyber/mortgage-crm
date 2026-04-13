"""
Security Certificate Pinning Routes

Provides endpoints for iOS certificate pinning:
  - GET  /api/v1/security/certificate-pins         — Returns SPKI SHA-256 pin hashes
  - POST /api/v1/security/pin-failure               — Accepts pin failure reports
  - GET  /api/v1/security/certificate-pins/status   — Pin verification status (auth required)
  - POST /api/v1/security/certificate-pins/verify   — Trigger on-demand pin verification (auth required)
  - GET  /api/v1/security/certificate-pins/expiry   — Certificate expiry dates (auth required)

The GET pins endpoint is unauthenticated (called before auth is established).
The POST endpoint accepts auth optionally (fire-and-forget from iOS).
The status/verify/expiry endpoints require authentication (admin monitoring).

Certificate pin verification runs at startup and every 6 hours via a
background task. Results are stored for the status endpoint and warnings
are logged when pins no longer match.
"""
import asyncio
import base64
import hashlib
import logging
import socket
import ssl
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/security", tags=["security"])


# =============================================================================
# Pin Configuration — matches CertificatePinning.swift PinnedDomainConfig
# =============================================================================

# These MUST match the hardcoded fallback pins in CertificatePinning.swift.
# The Swift client decodes the response as [String: PinnedDomainConfig] where:
#   PinnedDomainConfig { spkiHashes: [String], includeSubdomains: Bool, notAfter: String? }
CERTIFICATE_PINS: Dict[str, dict] = {
    "api.perenniaai.com": {
        "spkiHashes": [
            # Primary cert pin — current production certificate
            "STrmUQMdkvmuC5EJ/5StR+WXmwAq6RLFCIPe3rMVgPA=",
            # Backup pin — ISRG Root X1 (Let's Encrypt root CA)
            "C5+lpZ7tcVwmwQIMcRtPbsQtWLABXhQzejna0wHFr8M=",
            # Backup pin — Let's Encrypt R3 intermediate
            "jQJTbIh0grw0/1TkHSumWb+Fs0Ggogr621gT3PvPKG0=",
        ],
        "includeSubdomains": True,
        "notAfter": None,
    },
    "app.perenniaai.com": {
        "spkiHashes": [
            # Primary cert pin — current production certificate (verified 2026-04-10)
            "amKlKR/XR507OEn640jX8dUOfmFxM+fz1umrpwlbi5s=",
            # Backup pin — ISRG Root X1 (Let's Encrypt root CA)
            "C5+lpZ7tcVwmwQIMcRtPbsQtWLABXhQzejna0wHFr8M=",
            # Backup pin — Let's Encrypt R3 intermediate
            "jQJTbIh0grw0/1TkHSumWb+Fs0Ggogr621gT3PvPKG0=",
        ],
        "includeSubdomains": True,
        "notAfter": None,
    },
}


# =============================================================================
# Certificate Pin Verification — live chain comparison
# =============================================================================

# Stores the last verification result (populated at startup, read by status endpoint)
_last_verification: Optional[dict] = None


def _extract_spki_hashes(hostname: str, port: int = 443, timeout: float = 10.0) -> List[str]:
    """Connect to a host via TLS and extract base64-encoded SHA-256 SPKI hashes
    from the certificate chain.

    Returns a list of hashes in the format "base64hash=" (matching the pin format).
    Returns an empty list on any connection or parsing error.
    """
    hashes = []
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as tls_sock:
                # getpeercert(binary_form=True) returns the leaf DER cert
                der_cert = tls_sock.getpeercert(binary_form=True)
                if der_cert:
                    spki_hash = _der_cert_to_spki_hash(der_cert)
                    if spki_hash:
                        hashes.append(spki_hash)

                # Try to get the full chain via get_verified_chain (Python 3.13+)
                # or fall back to getpeercertchain if available
                chain_certs = []
                if hasattr(tls_sock, "get_verified_chain"):
                    try:
                        chain_certs = tls_sock.get_verified_chain() or []
                    except Exception:
                        pass

                for cert_obj in chain_certs:
                    try:
                        cert_der = cert_obj.public_bytes(ssl._ssl.ENCODING_DER) if hasattr(cert_obj, "public_bytes") else None
                        if cert_der:
                            h = _der_cert_to_spki_hash(cert_der)
                            if h and h not in hashes:
                                hashes.append(h)
                    except Exception:
                        continue

    except Exception as exc:
        logger.debug("Failed to extract SPKI hashes from %s:%d: %s", hostname, port, exc)

    return hashes


def _der_cert_to_spki_hash(der_cert: bytes) -> Optional[str]:
    """Extract the SubjectPublicKeyInfo from a DER certificate and return
    its base64-encoded SHA-256 hash.

    Uses a minimal ASN.1 DER parser to locate the SPKI field (the 7th
    element in the TBSCertificate SEQUENCE) without external dependencies.
    """
    try:
        # Parse the outermost SEQUENCE (Certificate)
        tag, _, cert_value = _parse_der_tlv(der_cert, 0)
        if tag != 0x30:
            return None

        # Parse TBSCertificate SEQUENCE
        tbs_tag, _, tbs_value = _parse_der_tlv(cert_value, 0)
        if tbs_tag != 0x30:
            return None

        # Walk through TBSCertificate fields to find SubjectPublicKeyInfo
        # TBSCertificate ::= SEQUENCE {
        #   version         [0] EXPLICIT ...,  (optional, context tag 0xA0)
        #   serialNumber    INTEGER,
        #   signature       AlgorithmIdentifier,
        #   issuer          Name,
        #   validity        SEQUENCE,
        #   subject         Name,
        #   subjectPublicKeyInfo SubjectPublicKeyInfo,  <-- field index 6 (with version)
        #   ...
        # }
        offset = 0
        field_index = 0
        while offset < len(tbs_value):
            f_tag, f_total_len, f_value = _parse_der_tlv(tbs_value, offset)

            if field_index == 6:
                # This is SubjectPublicKeyInfo — hash the raw DER encoding
                spki_der = tbs_value[offset:offset + f_total_len]
                digest = hashlib.sha256(spki_der).digest()
                return base64.b64encode(digest).decode("ascii")

            # version field is context-tagged [0] (0xA0), doesn't count as a
            # "skip" — it IS field 0. If absent, first field is serialNumber.
            if f_tag == 0xA0 and field_index == 0:
                # version present, counts as field 0
                pass

            offset += f_total_len
            field_index += 1

        return None
    except Exception as exc:
        logger.debug("DER SPKI extraction failed: %s", exc)
        return None


def _parse_der_tlv(data: bytes, offset: int):
    """Parse one DER TLV (tag-length-value) at the given offset.

    Returns (tag, total_bytes_consumed, value_bytes).
    """
    if offset >= len(data):
        raise ValueError("Offset past end of data")

    tag = data[offset]
    pos = offset + 1

    # Length
    length_byte = data[pos]
    pos += 1

    if length_byte < 0x80:
        length = length_byte
    elif length_byte == 0x80:
        raise ValueError("Indefinite length not supported")
    else:
        num_bytes = length_byte & 0x7F
        length = int.from_bytes(data[pos:pos + num_bytes], "big")
        pos += num_bytes

    value = data[pos:pos + length]
    total_consumed = (pos - offset) + length
    return tag, total_consumed, value


def verify_certificate_pins() -> dict:
    """Verify that the hardcoded SPKI hashes in CERTIFICATE_PINS still match
    the live certificate chains served by each domain.

    Returns a status dict:
        {
            "last_checked": "2026-04-10T12:00:00Z",
            "domains": {
                "api.perenniaai.com": {
                    "match": True,
                    "actual_hashes": ["hash1", ...],
                    "configured_hashes": ["hash1", "hash2", ...],
                    "error": null
                },
                ...
            },
            "all_match": True
        }

    This function is safe to call at startup. It catches all exceptions
    and never raises.
    """
    global _last_verification

    result = {
        "last_checked": datetime.now(timezone.utc).isoformat(),
        "domains": {},
        "all_match": True,
    }

    for domain, pin_config in CERTIFICATE_PINS.items():
        configured_hashes = pin_config.get("spkiHashes", [])
        domain_result = {
            "match": False,
            "actual_hashes": [],
            "configured_hashes": configured_hashes,
            "error": None,
        }

        try:
            actual_hashes = _extract_spki_hashes(domain)
            domain_result["actual_hashes"] = actual_hashes

            if not actual_hashes:
                domain_result["error"] = "Could not extract certificate hashes"
                domain_result["match"] = False
                logger.warning(
                    "CERTIFICATE PIN CHECK: Could not extract hashes for %s — "
                    "unable to verify pin freshness",
                    domain,
                )
            else:
                # Match if ANY actual hash appears in the configured set
                overlap = set(actual_hashes) & set(configured_hashes)
                domain_result["match"] = len(overlap) > 0

                if domain_result["match"]:
                    logger.info(
                        "CERTIFICATE PIN CHECK: %s — OK (%d/%d hashes match)",
                        domain,
                        len(overlap),
                        len(actual_hashes),
                    )
                else:
                    logger.warning(
                        "CERTIFICATE PIN CHECK: %s — MISMATCH! "
                        "Live hashes %s do not match any configured pins %s. "
                        "Update CERTIFICATE_PINS in security_certificate_routes.py.",
                        domain,
                        actual_hashes,
                        configured_hashes,
                    )

        except Exception as exc:
            domain_result["error"] = str(exc)
            logger.warning(
                "CERTIFICATE PIN CHECK: %s — verification failed: %s",
                domain,
                exc,
            )

        if not domain_result["match"]:
            result["all_match"] = False

        result["domains"][domain] = domain_result

    _last_verification = result
    return result


async def _run_startup_pin_check():
    """Non-blocking startup pin verification. Runs in a thread pool to avoid
    blocking the event loop with synchronous TLS connections."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, verify_certificate_pins)
    except Exception as exc:
        logger.warning("Startup certificate pin check failed (non-fatal): %s", exc)


# =============================================================================
# Scheduled Background Pin Check — runs every 6 hours
# =============================================================================

_PIN_CHECK_INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours
_background_task: Optional[asyncio.Task] = None


async def _periodic_pin_check():
    """Background coroutine that runs verify_certificate_pins() every 6 hours.

    Stores results in _last_verification and logs warnings on mismatches.
    Runs indefinitely until the task is cancelled.
    """
    while True:
        await asyncio.sleep(_PIN_CHECK_INTERVAL_SECONDS)
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, verify_certificate_pins)
            if not result.get("all_match"):
                for domain, info in result.get("domains", {}).items():
                    if not info.get("match"):
                        logger.warning(
                            "PERIODIC PIN CHECK: %s — pin mismatch detected. "
                            "Actual hashes: %s, Configured: %s",
                            domain,
                            info.get("actual_hashes", []),
                            info.get("configured_hashes", []),
                        )
            else:
                logger.info("PERIODIC PIN CHECK: All domains passed pin verification")
        except asyncio.CancelledError:
            logger.info("Periodic pin check task cancelled")
            return
        except Exception as exc:
            logger.warning("Periodic certificate pin check failed (non-fatal): %s", exc)


def start_periodic_pin_check():
    """Start the background periodic pin check task.

    Safe to call multiple times — will not create duplicate tasks.
    Should be called after the event loop is running (e.g., in a startup event).
    """
    global _background_task
    if _background_task is not None and not _background_task.done():
        logger.debug("Periodic pin check already running, skipping duplicate start")
        return
    _background_task = asyncio.create_task(_periodic_pin_check())
    logger.info(
        "Started periodic certificate pin check (every %d hours)",
        _PIN_CHECK_INTERVAL_SECONDS // 3600,
    )


def stop_periodic_pin_check():
    """Cancel the background periodic pin check task."""
    global _background_task
    if _background_task is not None and not _background_task.done():
        _background_task.cancel()
        logger.info("Stopped periodic certificate pin check")
    _background_task = None


# =============================================================================
# Certificate Expiry Extraction
# =============================================================================

def _get_certificate_expiry(hostname: str, port: int = 443, timeout: float = 10.0) -> dict:
    """Connect to a host via TLS and extract the certificate expiry date.

    Returns a dict:
        {
            "expires": "2026-06-15T12:00:00+00:00",
            "days_remaining": 63,
            "warning": False,
            "error": None
        }

    Uses ssl.getpeercert() (non-binary form) to get the 'notAfter' field.
    Sets warning=True when days_remaining < 30.
    """
    result = {
        "expires": None,
        "days_remaining": None,
        "warning": False,
        "error": None,
    }

    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as tls_sock:
                cert = tls_sock.getpeercert()
                if not cert:
                    result["error"] = "No certificate returned by server"
                    return result

                not_after = cert.get("notAfter")
                if not not_after:
                    result["error"] = "Certificate missing notAfter field"
                    return result

                # Parse the date string — format: '%b %d %H:%M:%S %Y GMT'
                # e.g., 'Jun 15 12:00:00 2026 GMT'
                expiry_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                delta = expiry_dt - now
                days_remaining = max(delta.days, 0)

                result["expires"] = expiry_dt.strftime("%Y-%m-%d")
                result["days_remaining"] = days_remaining
                result["warning"] = days_remaining < 30

    except Exception as exc:
        result["error"] = f"Connection failed: {exc}"
        logger.debug("Failed to extract certificate expiry from %s:%d: %s", hostname, port, exc)

    return result


# =============================================================================
# Request Models — matches the JSON structure sent by CertificatePinning.swift
# =============================================================================

class PinFailureReport(BaseModel):
    domain: str = Field(..., max_length=253)
    reason: str = Field(..., max_length=100)
    receivedHashes: List[str] = Field(default_factory=list, max_length=10)
    timestamp: Optional[str] = Field(default=None, max_length=50)
    platform: Optional[str] = Field(default=None, max_length=20)
    appVersion: Optional[str] = Field(default=None, max_length=50)


class DeviceInfo(BaseModel):
    platform: Optional[str] = Field(default=None, max_length=20)
    isNative: Optional[bool] = None
    osVersion: Optional[str] = Field(default=None, max_length=50)
    model: Optional[str] = Field(default=None, max_length=100)


class PinFailureRequest(BaseModel):
    reports: List[PinFailureReport] = Field(..., min_length=1, max_length=10)
    deviceInfo: Optional[DeviceInfo] = None


# =============================================================================
# Server-Side Rate Limiting (per IP, simple in-memory)
# =============================================================================

_rate_limit_window = 60  # seconds
_rate_limit_max = 20  # max reports per IP per window
_rate_limit_buckets: Dict[str, List[float]] = defaultdict(list)


def _check_rate_limit(client_ip: str) -> bool:
    """Return True if the request is within rate limits, False if exceeded."""
    now = time.time()
    bucket = _rate_limit_buckets[client_ip]
    # Prune old entries
    _rate_limit_buckets[client_ip] = [t for t in bucket if now - t < _rate_limit_window]
    bucket = _rate_limit_buckets[client_ip]
    if len(bucket) >= _rate_limit_max:
        return False
    bucket.append(now)
    return True


# =============================================================================
# Routes
# =============================================================================

@router.get("/certificate-pins")
async def get_certificate_pins():
    """Return SPKI SHA-256 pin hashes for pinned domains.

    No authentication required — the iOS app calls this before auth is
    established and uses the response to configure TLS certificate pinning.

    Response format matches Swift's [String: PinnedDomainConfig]:
        {
            "api.perenniaai.com": {
                "spkiHashes": ["hash1", "hash2", ...],
                "includeSubdomains": true,
                "notAfter": null
            },
            ...
        }
    """
    return CERTIFICATE_PINS


@router.post("/pin-failure")
async def report_pin_failure(
    body: PinFailureRequest,
    request: Request,
):
    """Accept certificate pin failure reports from iOS clients.

    This is a security-critical endpoint: pin failures may indicate a
    man-in-the-middle attack. Reports are logged as warnings for monitoring.

    No authentication required — if pinning fails, the client likely cannot
    authenticate either (TLS is broken). Rate-limited server-side.
    """
    client_ip = request.client.host if request.client else "unknown"

    # Server-side rate limiting
    if not _check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many pin failure reports. Try again later.",
        )

    device = body.deviceInfo
    device_summary = ""
    if device:
        parts = []
        if device.platform:
            parts.append(device.platform)
        if device.osVersion:
            parts.append(f"OS {device.osVersion}")
        if device.model:
            parts.append(device.model)
        device_summary = " | ".join(parts)

    for report in body.reports:
        hashes_str = ", ".join(report.receivedHashes[:5]) if report.receivedHashes else "none"
        logger.warning(
            "CERTIFICATE PIN FAILURE: domain=%s reason=%s received_hashes=[%s] "
            "platform=%s app_version=%s timestamp=%s client_ip=%s device=%s",
            report.domain,
            report.reason,
            hashes_str,
            report.platform or "unknown",
            report.appVersion or "unknown",
            report.timestamp or "unknown",
            client_ip,
            device_summary or "unknown",
        )

    return {
        "success": True,
        "message": f"Received {len(body.reports)} pin failure report(s)",
    }


@router.get("/certificate-pins/status")
async def get_certificate_pin_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return the last certificate pin verification result.

    Requires authentication. Shows whether the hardcoded pins still match
    the live certificate chains, when the check was last run, and the
    actual vs. configured hashes for each domain.
    """
    from auth.dependencies import get_current_user_flexible

    user = await get_current_user_flexible(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if _last_verification is None:
        return {
            "status": "not_checked",
            "message": "Pin verification has not run yet. It runs at startup.",
        }

    return _last_verification


@router.post("/certificate-pins/verify")
async def trigger_certificate_pin_verify(
    request: Request,
    db: Session = Depends(get_db),
):
    """Manually trigger a certificate pin verification.

    Requires authentication. Useful for checking pin freshness on-demand
    after a certificate rotation.
    """
    from auth.dependencies import get_current_user_flexible

    user = await get_current_user_flexible(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, verify_certificate_pins)
    return result


@router.get("/certificate-pins/expiry")
async def get_certificate_pin_expiry(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return certificate expiry dates for all pinned domains.

    Requires authentication. Connects to each pinned domain, extracts the
    TLS certificate expiry via ssl.getpeercert(), and returns the expiry
    date, days remaining, and a warning flag when expiry is within 30 days.

    Response format:
        {
            "checked_at": "2026-04-13T12:00:00+00:00",
            "domains": {
                "api.perenniaai.com": {
                    "expires": "2026-06-15",
                    "days_remaining": 63,
                    "warning": false,
                    "error": null
                },
                ...
            }
        }
    """
    from auth.dependencies import get_current_user_flexible

    user = await get_current_user_flexible(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    loop = asyncio.get_event_loop()

    domains_result = {}
    for domain in CERTIFICATE_PINS:
        expiry_info = await loop.run_in_executor(None, _get_certificate_expiry, domain)
        domains_result[domain] = expiry_info

        if expiry_info.get("warning"):
            logger.warning(
                "CERTIFICATE EXPIRY WARNING: %s expires on %s (%d days remaining)",
                domain,
                expiry_info.get("expires"),
                expiry_info.get("days_remaining", 0),
            )

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "domains": domains_result,
    }
