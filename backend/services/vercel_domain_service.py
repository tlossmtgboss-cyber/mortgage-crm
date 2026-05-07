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

# Retry configuration for transient errors
_RETRY_DELAY_SECONDS = 5
_MAX_RETRIES = 1


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
    except Exception:
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


def _is_retryable(exc: Exception) -> bool:
    """Return True if the error warrants a retry."""
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

    Retries once with a 5-second delay for transient errors (5xx, network,
    rate limit).

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
                logger.info(
                    "Retrying Vercel add_domain for '%s' after %ss (attempt %d): %s",
                    domain, _RETRY_DELAY_SECONDS, attempt + 1, exc.message,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
                last_exc = exc
                continue

            return {"error": exc.message, "error_type": type(exc).__name__, "detail": exc.detail}

        except httpx.RequestError as exc:
            logger.exception("Vercel add_domain network error for %s (attempt %d)", domain, attempt + 1)
            if attempt < _MAX_RETRIES:
                logger.info("Retrying after network error in %ss", _RETRY_DELAY_SECONDS)
                time.sleep(_RETRY_DELAY_SECONDS)
                last_exc = exc
                continue
            return {"error": f"Network error connecting to Vercel: {exc}", "error_type": "VercelTransientError"}

    # Should not reach here, but safety net
    return {"error": str(last_exc) if last_exc else "Unknown error", "error_type": "VercelDomainError"}


def remove_domain(domain: str) -> bool:
    """Remove a custom domain from the Vercel project.

    DELETE /v10/projects/{project_id}/domains/{domain}

    Returns True on success (including 404 — already gone), False on error.
    Retries once for transient errors.
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
                logger.info(
                    "Retrying Vercel remove_domain for '%s' in %ss: %s",
                    domain, _RETRY_DELAY_SECONDS, exc.message,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
                continue

            return False

        except httpx.RequestError:
            logger.exception("Vercel remove_domain network error for %s (attempt %d)", domain, attempt + 1)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            return False

    return False


def get_domain_config(domain: str) -> dict:
    """Get Vercel's domain configuration record.

    GET /v6/domains/{domain}/config

    Returns the Vercel config dict, or ``{"error": "..."}`` on failure.
    Retries once for transient errors.
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
                logger.info(
                    "Retrying Vercel get_domain_config for '%s' in %ss: %s",
                    domain, _RETRY_DELAY_SECONDS, exc.message,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
                continue

            return {"error": exc.message, "error_type": type(exc).__name__}

        except httpx.RequestError:
            logger.exception("Vercel get_domain_config network error for %s (attempt %d)", domain, attempt + 1)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_SECONDS)
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


def get_ssl_expiry(domain: str) -> Optional[datetime]:
    """Retrieve the SSL certificate expiry date from Vercel for a domain.

    Returns the earliest cert expiry as a UTC datetime, or None if unavailable.
    Vercel's domain config response includes a ``certs`` array with
    ``expiresAt`` (epoch ms) on each certificate.
    """
    config = get_domain_config(domain)

    if config.get("skipped") or config.get("error"):
        return None

    certs = config.get("certs", [])
    if not certs:
        return None

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

    if not expires_list:
        return None

    # Return the earliest expiry (most urgent)
    return min(expires_list)
