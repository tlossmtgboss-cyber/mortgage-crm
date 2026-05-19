"""
Vercel Domain Management Service

Manages custom domain provisioning via Vercel API.
Requires: VERCEL_TOKEN and VERCEL_PROJECT_ID environment variables.

If env vars are not set, all methods return safe no-op defaults and log a
warning — the rest of the custom-domain flow (DNS verification, DB updates)
continues unaffected.

API Reference: https://vercel.com/docs/rest-api/endpoints/projects/domains
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_VERCEL_API_BASE = "https://api.vercel.com"

# Retry configuration for transient errors (exponential backoff: 2s, 4s, 8s)
_BASE_RETRY_DELAY_SECONDS = 2
_MAX_RETRIES = 3


class VercelDomainError(Exception):
    """Base class for Vercel domain operation errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class VercelRateLimitError(VercelDomainError):
    """Raised when Vercel API returns 429 Too Many Requests."""
    pass


class VercelInvalidDomainError(VercelDomainError):
    """Raised when the domain is invalid or rejected by Vercel."""
    pass


class VercelDNSNotPropagatedError(VercelDomainError):
    """Raised when DNS has not propagated for the domain."""
    pass


class VercelTransientError(VercelDomainError):
    """Raised for transient/retryable Vercel API errors (5xx, network)."""
    pass


def _get_credentials() -> tuple[Optional[str], Optional[str]]:
    """Return (token, project_id) from env vars, or (None, None) if missing."""
    token = os.getenv("VERCEL_TOKEN")
    project_id = os.getenv("VERCEL_PROJECT_ID")
    if not token or not project_id:
        logger.warning(
            "VERCEL_TOKEN or VERCEL_PROJECT_ID not set — Vercel domain "
            "operations will be skipped (manual DNS-only mode)."
        )
        return None, None
    return token, project_id


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _classify_vercel_error(resp: httpx.Response, domain: str) -> VercelDomainError:
    """Classify a Vercel API error response into a specific exception type.

    Returns the appropriate VercelDomainError subclass based on status code
    and response body.
    """
    status_code = resp.status_code
    try:
        body = resp.json()
    except Exception as _exc:  # noqa: BLE001
        logger.exception("unhandled exception")
        body = {"message": resp.text}

    error_code = body.get("error", {}).get("code", "") if isinstance(body.get("error"), dict) else ""
    error_message = body.get("error", {}).get("message", "") if isinstance(body.get("error"), dict) else str(body)

    logger.warning(
        "Vercel API error for domain '%s': status=%s, code=%s, message=%s, body=%s",
        domain, status_code, error_code, error_message, resp.text[:500],
    )

    if status_code == 429:
        return VercelRateLimitError(
            message=f"Vercel rate limit exceeded for domain '{domain}'. Please retry later.",
            status_code=429,
            detail=error_message,
        )

    if status_code == 400:
        # Check for DNS-not-propagated or invalid domain patterns
        lower_msg = error_message.lower()
        if "dns" in lower_msg or "not propagated" in lower_msg or "resolve" in lower_msg:
            return VercelDNSNotPropagatedError(
                message=(
                    f"DNS has not propagated for '{domain}'. "
                    "Ensure your CNAME record points to cname.vercel-dns.com "
                    "and allow up to 48 hours for propagation."
                ),
                status_code=400,
                detail=error_message,
            )
        return VercelInvalidDomainError(
            message=f"Vercel rejected domain '{domain}': {error_message}",
            status_code=400,
            detail=error_message,
        )

    if status_code == 403:
        return VercelDomainError(
            message=f"Vercel authorization failed for domain '{domain}'. Check VERCEL_TOKEN permissions.",
            status_code=403,
            detail=error_message,
        )

    if status_code == 404:
        return VercelDomainError(
            message=f"Vercel project or domain '{domain}' not found.",
            status_code=404,
            detail=error_message,
        )

    if status_code == 422:
        return VercelInvalidDomainError(
            message=f"Vercel rejected domain '{domain}' as invalid: {error_message}",
            status_code=422,
            detail=error_message,
        )

    if status_code >= 500:
        return VercelTransientError(
            message=f"Vercel server error ({status_code}) for domain '{domain}'. Retrying may help.",
            status_code=status_code,
            detail=error_message,
        )

    # Catch-all
    return VercelDomainError(
        message=f"Vercel API error {status_code} for domain '{domain}': {error_message}",
        status_code=status_code,
        detail=error_message,
    )


def _retry_delay(attempt: int) -> float:
    """Return the exponential backoff delay in seconds for the given attempt.

    attempt 0 -> 2s, attempt 1 -> 4s, attempt 2 -> 8s, etc.
    """
    return _BASE_RETRY_DELAY_SECONDS * (2 ** attempt)


def _is_retryable(exc: Exception) -> bool:
    """Return True if the error warrants a retry.

    Only retries on:
    - 429 Too Many Requests (VercelRateLimitError)
    - 5xx Server Errors (VercelTransientError)
    - Network/connection errors (httpx.RequestError)
    """
    if isinstance(exc, (VercelTransientError, VercelRateLimitError)):
        return True
    if isinstance(exc, httpx.RequestError):
        return True
    return False


def add_domain(domain: str) -> dict:
    """Add a custom domain to the Vercel project.

    POST /v10/projects/{project_id}/domains

    Returns the Vercel API response dict on success, or a dict with
    ``{"error": "..."}`` on failure / missing credentials.

    Retries up to 3 times with exponential backoff (2s, 4s, 8s) for
    transient errors (429 rate limit, 5xx server errors, network errors).

    Raises VercelDomainError subclasses for non-retryable failures, which
    callers can catch for user-friendly error messages.
    """
    token, project_id = _get_credentials()
    if not token:
        return {"skipped": True, "reason": "Vercel credentials not configured"}

    url = f"{_VERCEL_API_BASE}/v10/projects/{project_id}/domains"
    last_exc: Optional[Exception] = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(url, headers=_headers(token), json={"name": domain})

            if resp.status_code in (200, 201, 409):
                # 409 = already exists in Vercel — treat as success
                return resp.json()

            exc = _classify_vercel_error(resp, domain)
            if _is_retryable(exc) and attempt < _MAX_RETRIES:
                delay = _retry_delay(attempt)
                logger.info(
                    "Retrying Vercel add_domain for '%s' after %ss (attempt %d/%d): %s",
                    domain, delay, attempt + 1, _MAX_RETRIES, exc.message,
                )
                time.sleep(delay)
                last_exc = exc
                continue

            return {"error": exc.message, "error_type": type(exc).__name__, "detail": exc.detail}

        except httpx.RequestError as exc:
            logger.exception("Vercel add_domain network error for %s (attempt %d)", domain, attempt + 1)
            if attempt < _MAX_RETRIES:
                delay = _retry_delay(attempt)
                logger.info("Retrying after network error in %ss", delay)
                time.sleep(delay)
                last_exc = exc
                continue
            return {"error": f"Network error connecting to Vercel: {exc}", "error_type": "VercelTransientError"}

    # Should not reach here, but safety net
    return {"error": str(last_exc) if last_exc else "Unknown error", "error_type": "VercelDomainError"}


def remove_domain(domain: str) -> bool:
    """Remove a custom domain from the Vercel project.

    DELETE /v10/projects/{project_id}/domains/{domain}

    Returns True on success (including 404 — already gone), False on error.
    Retries up to 3 times with exponential backoff for transient errors.
    """
    token, project_id = _get_credentials()
    if not token:
        logger.info("Vercel credentials not configured — skipping domain removal for %s", domain)
        return True  # Treat as success in manual mode

    url = f"{_VERCEL_API_BASE}/v10/projects/{project_id}/domains/{domain}"

    for attempt in range(_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.delete(url, headers=_headers(token))
            if resp.status_code in (200, 204, 404):
                return True

            exc = _classify_vercel_error(resp, domain)
            if _is_retryable(exc) and attempt < _MAX_RETRIES:
                delay = _retry_delay(attempt)
                logger.info(
                    "Retrying Vercel remove_domain for '%s' in %ss (attempt %d/%d): %s",
                    domain, delay, attempt + 1, _MAX_RETRIES, exc.message,
                )
                time.sleep(delay)
                continue

            return False

        except httpx.RequestError:
            logger.exception("Vercel remove_domain network error for %s (attempt %d)", domain, attempt + 1)
            if attempt < _MAX_RETRIES:
                time.sleep(_retry_delay(attempt))
                continue
            return False

    return False


def get_domain_config(domain: str) -> dict:
    """Get Vercel's domain configuration record.

    GET /v6/domains/{domain}/config

    Returns the Vercel config dict, or ``{"error": "..."}`` on failure.
    Retries up to 3 times with exponential backoff for transient errors.
    """
    token, _ = _get_credentials()
    if not token:
        return {"skipped": True, "reason": "Vercel credentials not configured"}

    url = f"{_VERCEL_API_BASE}/v6/domains/{domain}/config"

    for attempt in range(_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(url, headers=_headers(token))
            if resp.status_code == 200:
                return resp.json()

            exc = _classify_vercel_error(resp, domain)
            if _is_retryable(exc) and attempt < _MAX_RETRIES:
                delay = _retry_delay(attempt)
                logger.info(
                    "Retrying Vercel get_domain_config for '%s' in %ss (attempt %d/%d): %s",
                    domain, delay, attempt + 1, _MAX_RETRIES, exc.message,
                )
                time.sleep(delay)
                continue

            return {"error": exc.message, "error_type": type(exc).__name__}

        except httpx.RequestError:
            logger.exception("Vercel get_domain_config network error for %s (attempt %d)", domain, attempt + 1)
            if attempt < _MAX_RETRIES:
                time.sleep(_retry_delay(attempt))
                continue
            return {"error": f"Network error checking domain config for {domain}"}

    return {"error": f"Failed to get domain config for {domain} after retries"}


def check_ssl_status(domain: str) -> str:
    """Check whether Vercel has provisioned an SSL certificate for the domain.

    Returns one of: ``"active"``, ``"provisioning"``, ``"pending"``, ``"failed"``,
    or ``"unknown"`` if Vercel is not configured.
    """
    config = get_domain_config(domain)

    if config.get("skipped") or config.get("error"):
        return "unknown"

    # Vercel returns misconfigured=false + certs array when SSL is live
    misconfigured = config.get("misconfigured", True)
    certs = config.get("certs", [])

    if not misconfigured and certs:
        return "active"
    if not misconfigured:
        return "provisioning"
    return "pending"


def _get_ssl_expiry_via_socket(domain: str) -> Optional[datetime]:
    """Fallback: fetch SSL certificate expiry by connecting to the domain directly.

    Uses ssl.get_server_certificate() to retrieve the PEM cert and parses the
    notAfter date. This works even when the Vercel API doesn't return cert data.

    Returns a UTC datetime or None if the check fails.
    """
    import ssl
    import socket
    from datetime import datetime as _dt

    try:
        # Connect via TLS and read the peer certificate
        ctx = ssl.create_default_context()

        with socket.create_connection((domain, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert_info = ssock.getpeercert()

        if cert_info and "notAfter" in cert_info:
            # Format: 'Mon DD HH:MM:SS YYYY GMT'
            expiry = _dt.strptime(cert_info["notAfter"], "%b %d %H:%M:%S %Y %Z")
            return expiry.replace(tzinfo=timezone.utc)

    except Exception as e:
        logger.warning(
            "DNS fallback SSL expiry check failed for '%s': %s", domain, e,
        )

    return None


def get_ssl_expiry(domain: str) -> Optional[datetime]:
    """Retrieve the SSL certificate expiry date for a domain.

    Primary: queries the Vercel domain config API for cert expiry data.
    Fallback: if Vercel doesn't return cert info, connects directly to the
    domain via TLS and reads the certificate's notAfter date.

    Returns the earliest cert expiry as a UTC datetime, or None if unavailable.
    """
    config = get_domain_config(domain)

    # Try Vercel API first
    if not config.get("skipped") and not config.get("error"):
        certs = config.get("certs", [])
        expires_list = []
        for cert in certs:
            expires_at = cert.get("expiresAt")
            if expires_at:
                try:
                    # Vercel returns epoch milliseconds
                    expires_list.append(
                        datetime.fromtimestamp(expires_at / 1000, tz=timezone.utc)
                    )
                except (TypeError, ValueError, OSError) as e:
                    logger.warning("Could not parse cert expiresAt=%s for %s: %s", expires_at, domain, e)

        if expires_list:
            return min(expires_list)

    # Fallback: direct TLS connection to read the certificate
    logger.info(
        "Vercel API did not return cert expiry for '%s' — attempting DNS/TLS fallback.",
        domain,
    )
    return _get_ssl_expiry_via_socket(domain)
