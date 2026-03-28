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
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_VERCEL_API_BASE = "https://api.vercel.com"


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


def add_domain(domain: str) -> dict:
    """Add a custom domain to the Vercel project.

    POST /v10/projects/{project_id}/domains

    Returns the Vercel API response dict on success, or a dict with
    ``{"error": "..."}`` on failure / missing credentials.
    """
    token, project_id = _get_credentials()
    if not token:
        return {"skipped": True, "reason": "Vercel credentials not configured"}

    url = f"{_VERCEL_API_BASE}/v10/projects/{project_id}/domains"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, headers=_headers(token), json={"name": domain})
        if resp.status_code in (200, 201, 409):
            # 409 = already exists in Vercel — treat as success
            return resp.json()
        logger.warning("Vercel add_domain returned %s: %s", resp.status_code, resp.text)
        return {"error": f"Vercel API error {resp.status_code}", "detail": resp.text}
    except httpx.RequestError as exc:
        logger.exception("Vercel add_domain network error for %s", domain)
        return {"error": str(exc)}


def remove_domain(domain: str) -> bool:
    """Remove a custom domain from the Vercel project.

    DELETE /v10/projects/{project_id}/domains/{domain}

    Returns True on success (including 404 — already gone), False on error.
    """
    token, project_id = _get_credentials()
    if not token:
        logger.info("Vercel credentials not configured — skipping domain removal for %s", domain)
        return True  # Treat as success in manual mode

    url = f"{_VERCEL_API_BASE}/v10/projects/{project_id}/domains/{domain}"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.delete(url, headers=_headers(token))
        if resp.status_code in (200, 204, 404):
            return True
        logger.warning("Vercel remove_domain returned %s: %s", resp.status_code, resp.text)
        return False
    except httpx.RequestError:
        logger.exception("Vercel remove_domain network error for %s", domain)
        return False


def get_domain_config(domain: str) -> dict:
    """Get Vercel's domain configuration record.

    GET /v6/domains/{domain}/config

    Returns the Vercel config dict, or ``{"error": "..."}`` on failure.
    """
    token, _ = _get_credentials()
    if not token:
        return {"skipped": True, "reason": "Vercel credentials not configured"}

    url = f"{_VERCEL_API_BASE}/v6/domains/{domain}/config"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, headers=_headers(token))
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Vercel get_domain_config returned %s for %s", resp.status_code, domain)
        return {"error": f"Vercel API error {resp.status_code}"}
    except httpx.RequestError:
        logger.exception("Vercel get_domain_config network error for %s", domain)
        return {"error": "network error"}


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
