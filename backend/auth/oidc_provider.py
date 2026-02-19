"""
OpenID Connect (OIDC) Provider Service
Enterprise Readiness Check 5.10

Provides OIDC authentication flow:
- Discovery document fetching and caching
- Authorization URL generation
- Token exchange (authorization code -> tokens)
- ID token validation and claims extraction
- UserInfo endpoint fetching

Supports any OIDC-compliant IdP (Okta, Azure AD, Google Workspace, Auth0, etc.)
"""

import hashlib
import logging
import os
import secrets
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import requests as http_requests

logger = logging.getLogger(__name__)

# Callback URL for OIDC
OIDC_CALLBACK_URL = os.getenv(
    "OIDC_CALLBACK_URL",
    "https://api.perenniaai.com/api/v1/auth/sso/oidc/callback",
)

# In-memory discovery document cache: {discovery_url: (doc, expiry_time)}
_discovery_cache: Dict[str, Tuple[dict, float]] = {}
_DISCOVERY_CACHE_TTL = 3600  # 1 hour


def fetch_discovery_document(discovery_url: str) -> Optional[dict]:
    """
    Fetch and cache the OIDC discovery document.

    Args:
        discovery_url: The .well-known/openid-configuration URL.

    Returns:
        Discovery document dict, or None on failure.
    """
    now = time.time()

    # Check cache
    if discovery_url in _discovery_cache:
        doc, expiry = _discovery_cache[discovery_url]
        if now < expiry:
            return doc

    try:
        resp = http_requests.get(discovery_url, timeout=10)
        resp.raise_for_status()
        doc = resp.json()
        _discovery_cache[discovery_url] = (doc, now + _DISCOVERY_CACHE_TTL)
        logger.info(f"OIDC discovery document fetched from {discovery_url}")
        return doc
    except Exception as e:
        logger.error(f"Failed to fetch OIDC discovery document from {discovery_url}: {e}")
        return None


def create_authorization_url(
    discovery_url: str,
    client_id: str,
    scopes: str = "openid profile email",
    state: Optional[str] = None,
    nonce: Optional[str] = None,
    callback_url: Optional[str] = None,
) -> Tuple[Optional[str], str, str]:
    """
    Generate the OIDC authorization URL for login redirect.

    Args:
        discovery_url: OIDC discovery URL.
        client_id: OIDC client ID.
        scopes: Space-separated scopes.
        state: Optional state parameter (generated if not provided).
        nonce: Optional nonce (generated if not provided).
        callback_url: Override callback URL.

    Returns:
        Tuple of (authorization_url, state, nonce).
        authorization_url is None if discovery fails.
    """
    doc = fetch_discovery_document(discovery_url)
    if not doc:
        return None, "", ""

    authorization_endpoint = doc.get("authorization_endpoint")
    if not authorization_endpoint:
        logger.error("No authorization_endpoint in OIDC discovery document")
        return None, "", ""

    _state = state or secrets.token_urlsafe(32)
    _nonce = nonce or secrets.token_urlsafe(32)
    _callback = callback_url or OIDC_CALLBACK_URL

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _callback,
        "scope": scopes,
        "state": _state,
        "nonce": _nonce,
    }

    auth_url = f"{authorization_endpoint}?{urlencode(params)}"
    return auth_url, _state, _nonce


def exchange_code_for_tokens(
    discovery_url: str,
    client_id: str,
    client_secret: str,
    authorization_code: str,
    callback_url: Optional[str] = None,
) -> Optional[dict]:
    """
    Exchange an authorization code for tokens.

    Args:
        discovery_url: OIDC discovery URL.
        client_id: OIDC client ID.
        client_secret: OIDC client secret.
        authorization_code: The code from the callback.
        callback_url: Override callback URL.

    Returns:
        Token response dict (id_token, access_token, etc.) or None on failure.
    """
    doc = fetch_discovery_document(discovery_url)
    if not doc:
        return None

    token_endpoint = doc.get("token_endpoint")
    if not token_endpoint:
        logger.error("No token_endpoint in OIDC discovery document")
        return None

    _callback = callback_url or OIDC_CALLBACK_URL

    try:
        resp = http_requests.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": _callback,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        tokens = resp.json()
        logger.info("OIDC token exchange successful")
        return tokens
    except Exception as e:
        logger.error(f"OIDC token exchange failed: {e}")
        return None


def extract_claims_from_id_token(id_token: str) -> Optional[dict]:
    """
    Decode and extract claims from a JWT ID token.

    NOTE: This performs base64 decoding only (no signature verification).
    For production, you should verify the signature against the IdP's JWKS.
    Consider using PyJWT or python-jose with JWKS key fetching.

    Args:
        id_token: The JWT ID token string.

    Returns:
        Claims dict or None on failure.
    """
    import base64
    import json

    try:
        # Split JWT parts
        parts = id_token.split(".")
        if len(parts) != 3:
            logger.error("Invalid JWT format for ID token")
            return None

        # Decode payload (second part)
        payload_b64 = parts[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        claims = json.loads(payload_bytes)
        return claims
    except Exception as e:
        logger.error(f"Failed to decode ID token: {e}")
        return None


def fetch_userinfo(
    discovery_url: str,
    access_token: str,
) -> Optional[dict]:
    """
    Fetch user info from the OIDC UserInfo endpoint.

    Args:
        discovery_url: OIDC discovery URL.
        access_token: OAuth2 access token.

    Returns:
        UserInfo dict or None on failure.
    """
    doc = fetch_discovery_document(discovery_url)
    if not doc:
        return None

    userinfo_endpoint = doc.get("userinfo_endpoint")
    if not userinfo_endpoint:
        logger.error("No userinfo_endpoint in OIDC discovery document")
        return None

    try:
        resp = http_requests.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"OIDC UserInfo fetch failed: {e}")
        return None


def extract_user_attributes(
    claims: dict,
    userinfo: Optional[dict] = None,
) -> dict:
    """
    Extract standardized user attributes from OIDC claims and/or userinfo.

    Args:
        claims: ID token claims.
        userinfo: Optional UserInfo response (merged with claims).

    Returns:
        Dict with: email, first_name, last_name, groups, sub.
    """
    # Merge userinfo into claims (userinfo takes precedence)
    merged = {**claims}
    if userinfo:
        merged.update(userinfo)

    email = merged.get("email", "").lower()
    sub = merged.get("sub", "")

    # Name extraction
    first_name = merged.get("given_name") or merged.get("first_name")
    last_name = merged.get("family_name") or merged.get("last_name")

    # Fallback: parse "name" field
    if not first_name and not last_name:
        full_name = merged.get("name", "")
        if full_name:
            parts = full_name.strip().split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

    # Groups (varies by IdP)
    groups = merged.get("groups", [])
    if isinstance(groups, str):
        groups = [groups]

    return {
        "email": email,
        "sub": sub,
        "first_name": first_name or "",
        "last_name": last_name or "",
        "groups": groups,
        "raw_claims": merged,
    }
