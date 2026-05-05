"""
SSO Routes - SAML 2.0 and OIDC Single Sign-On
Enterprise Readiness Checks 4.5, 5.9, 5.10, 5.11, 5.12

Endpoints:
  SAML:
    GET  /api/v1/auth/sso/saml/metadata  - SP metadata XML
    GET  /api/v1/auth/sso/saml/login     - Initiate SAML login (redirect to IdP)
    POST /api/v1/auth/sso/saml/acs       - Assertion Consumer Service (IdP callback)
    GET  /api/v1/auth/sso/saml/slo       - Single Logout

  OIDC:
    GET  /api/v1/auth/sso/oidc/login     - Initiate OIDC login (redirect to IdP)
    GET  /api/v1/auth/sso/oidc/callback  - OIDC authorization code callback

  Admin:
    GET  /api/v1/admin/sso/config        - Get SSO config for org
    PUT  /api/v1/admin/sso/config        - Create/update SSO config
"""

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["SSO - Single Sign-On"])

# In-memory OIDC state store (production should use Redis)
# Maps state -> {org_id, nonce, created_at}
_oidc_state_store: dict = {}


# =============================================================================
# SCHEMAS
# =============================================================================

class SSOConfigUpdate(BaseModel):
    """Request body for creating/updating SSO configuration."""
    provider_type: str = "saml"  # 'saml', 'oidc', or 'both'

    # SAML fields
    idp_entity_id: Optional[str] = None
    idp_sso_url: Optional[str] = None
    idp_slo_url: Optional[str] = None
    idp_certificate: Optional[str] = None
    sp_entity_id: Optional[str] = None

    # OIDC fields
    oidc_discovery_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_scopes: Optional[str] = "openid profile email"

    # Common
    default_role: str = "loan_officer"
    default_permission_role: str = "sales"
    auto_provision: bool = True
    enabled: bool = False


class SSOConfigResponse(BaseModel):
    """Response for SSO configuration."""
    id: int
    organization_id: int
    provider_type: str
    idp_entity_id: Optional[str] = None
    idp_sso_url: Optional[str] = None
    idp_slo_url: Optional[str] = None
    has_idp_certificate: bool = False
    sp_entity_id: Optional[str] = None
    oidc_discovery_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    has_oidc_client_secret: bool = False
    oidc_scopes: Optional[str] = None
    default_role: str = "loan_officer"
    default_permission_role: str = "sales"
    auto_provision: bool = True
    enabled: bool = False


# =============================================================================
# HELPERS
# =============================================================================

def _get_current_user_dep():
    """Get current user dependency at runtime to avoid circular imports."""
    import main
    return main.get_current_user


def _get_auth_functions():
    """Get auth functions at runtime."""
    import main
    return {
        "create_access_token": main.create_access_token,
        "create_refresh_token": main.create_refresh_token,
    }


def _get_sso_config(db: Session, organization_id: int):
    """Load SSO config for an organization."""
    from database.models.sso import SSOConfig
    return db.query(SSOConfig).filter(
        SSOConfig.organization_id == organization_id,
        SSOConfig.enabled == True,
    ).first()


def _get_sso_config_by_domain(db: Session, email_domain: str):
    """Load SSO config by email domain."""
    from database.models.core import Organization
    from database.models.sso import SSOConfig

    org = db.query(Organization).filter(
        Organization.domain == email_domain,
        Organization.is_active == True,
    ).first()

    if not org:
        return None, None

    config = db.query(SSOConfig).filter(
        SSOConfig.organization_id == org.id,
        SSOConfig.enabled == True,
    ).first()

    return org, config


def _find_or_provision_user(
    db: Session,
    email: str,
    first_name: Optional[str],
    last_name: Optional[str],
    organization_id: int,
    sso_provider: str,
    sso_subject_id: str,
    groups: list,
    sso_config,
):
    """Find existing user or JIT-provision a new one."""
    from database.models.core import User
    from auth.jit_provisioning import provision_user_from_sso, update_user_from_sso

    # Look up existing user by email
    user = db.query(User).filter(User.email == email.lower()).first()

    if user:
        # Update SSO attributes on existing user
        update_user_from_sso(
            db, user,
            first_name=first_name,
            last_name=last_name,
            groups=groups,
            sso_provider=sso_provider,
            sso_subject_id=sso_subject_id,
        )
        return user

    # No existing user - check if auto-provisioning is enabled
    if not sso_config or not sso_config.auto_provision:
        logger.warning(f"SSO login for unknown user {email} - auto-provisioning disabled")
        return None

    # JIT provision
    user = provision_user_from_sso(
        db=db,
        email=email,
        first_name=first_name,
        last_name=last_name,
        organization_id=organization_id,
        sso_provider=sso_provider,
        sso_subject_id=sso_subject_id,
        groups=groups,
        default_role=sso_config.default_role or "loan_officer",
        default_permission_role=sso_config.default_permission_role or "sales",
    )

    return user


def _create_sso_tokens(user, auth_funcs: dict) -> dict:
    """Create JWT tokens for an SSO-authenticated user."""
    tenant_id = str(user.organization_id) if user.organization_id else None

    access_token = auth_funcs["create_access_token"](
        data={"sub": user.email},
        user_id=user.id,
        tenant_id=tenant_id,
    )
    refresh_token = auth_funcs["create_refresh_token"](
        data={"sub": user.email},
        user_id=user.id,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


# =============================================================================
# SSO DISCOVERY (for mobile app and login flow)
# =============================================================================


class SSODiscoverResponse(BaseModel):
    """Response for SSO discovery check."""
    has_sso: bool = False
    provider_type: Optional[str] = None  # 'saml', 'oidc', 'both'
    provider_name: Optional[str] = None  # 'okta', 'azure_ad', 'google', 'generic'
    auth_url: Optional[str] = None       # Direct URL to initiate SSO
    organization_name: Optional[str] = None


@router.get("/api/v1/auth/sso/discover", response_model=SSODiscoverResponse)
async def sso_discover(
    domain: Optional[str] = None,
    email: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Check if an email domain has SSO configured.

    Used by the login form to detect enterprise SSO before the user
    enters a password. Provide either `domain` or `email`.

    This endpoint is unauthenticated so the login page can call it.
    """
    if email and "@" in email:
        domain = email.split("@")[1].lower()
    elif domain:
        domain = domain.lower()
    else:
        return SSODiscoverResponse(has_sso=False)

    org, sso_config = _get_sso_config_by_domain(db, domain)

    if not org or not sso_config:
        return SSODiscoverResponse(has_sso=False)

    # Determine provider name from IdP URLs for display purposes
    provider_name = "generic"
    idp_url = (sso_config.idp_sso_url or sso_config.oidc_discovery_url or "").lower()
    if "okta" in idp_url:
        provider_name = "okta"
    elif "microsoftonline" in idp_url or "login.microsoft" in idp_url:
        provider_name = "azure_ad"
    elif "accounts.google" in idp_url:
        provider_name = "google"
    elif "auth0" in idp_url:
        provider_name = "auth0"
    elif "onelogin" in idp_url:
        provider_name = "onelogin"
    elif "ping" in idp_url:
        provider_name = "ping_identity"

    # Build the auth URL based on provider type
    base_api = os.getenv("API_BASE_URL", "https://api.perenniaai.com")
    if sso_config.provider_type in ("oidc", "both"):
        auth_url = f"{base_api}/api/v1/auth/sso/oidc/login?org_id={org.id}"
    else:
        auth_url = f"{base_api}/api/v1/auth/sso/saml/login?org_id={org.id}"

    return SSODiscoverResponse(
        has_sso=True,
        provider_type=sso_config.provider_type,
        provider_name=provider_name,
        auth_url=auth_url,
        organization_name=org.name,
    )


@router.post("/api/v1/auth/sso/exchange")
async def sso_exchange_token(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Exchange an SSO callback token for a full session.

    Used by the mobile app after capturing the SSO redirect.
    The mobile app receives the access_token and refresh_token from the
    callback URL and sends them here to validate and get user info.
    """
    body = await request.json()
    access_token = body.get("access_token")
    refresh_token = body.get("refresh_token")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing access_token",
        )

    # Validate the token by loading the user
    try:
        import main
        payload = main._verify_secure_token(access_token)
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

        from database.models.core import User
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "user_id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "full_name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
                "role": user.role,
                "permission_role": user.permission_role,
                "organization_id": user.organization_id,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SSO token exchange failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired SSO token",
        )


# =============================================================================
# SAML ENDPOINTS
# =============================================================================

@router.get("/api/v1/auth/sso/saml/metadata")
async def saml_sp_metadata():
    """
    Return SAML 2.0 SP metadata XML.

    IdP administrators use this to configure trust with Perennia AI.
    """
    from auth.saml_sso import generate_sp_metadata

    metadata_xml = generate_sp_metadata()
    return Response(
        content=metadata_xml,
        media_type="application/xml",
    )


@router.get("/api/v1/auth/sso/saml/login")
async def saml_login(
    email: Optional[str] = None,
    org_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Initiate SAML login by redirecting to the IdP.

    Provide either `email` (to auto-detect org by domain) or `org_id`.
    """
    from auth.saml_sso import create_authn_request

    sso_config = None
    organization = None

    if org_id:
        from database.models.core import Organization
        from database.models.sso import SSOConfig
        organization = db.query(Organization).filter(Organization.id == org_id).first()
        if organization:
            sso_config = db.query(SSOConfig).filter(
                SSOConfig.organization_id == org_id,
                SSOConfig.enabled == True,
            ).first()
    elif email and "@" in email:
        domain = email.split("@")[1].lower()
        organization, sso_config = _get_sso_config_by_domain(db, domain)

    if not sso_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO not configured for this organization.",
        )

    if sso_config.provider_type not in ("saml", "both"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SAML is not configured for this organization. Use OIDC.",
        )

    if not sso_config.idp_sso_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SAML IdP SSO URL not configured.",
        )

    # Generate relay state with org ID for the ACS callback
    relay_state = f"org_{organization.id}"

    redirect_url = create_authn_request(
        idp_sso_url=sso_config.idp_sso_url,
        sp_entity_id=sso_config.sp_entity_id,
        relay_state=relay_state,
    )

    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/api/v1/auth/sso/saml/acs")
async def saml_acs(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    SAML Assertion Consumer Service (ACS).

    Receives the SAML Response from the IdP via HTTP-POST binding,
    validates the assertion, and creates a session.
    """
    from auth.saml_sso import parse_saml_response

    form_data = await request.form()
    saml_response_b64 = form_data.get("SAMLResponse")
    relay_state = form_data.get("RelayState", "")

    if not saml_response_b64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing SAMLResponse parameter.",
        )

    # Extract org ID from relay state
    org_id = None
    if relay_state.startswith("org_"):
        try:
            org_id = int(relay_state.split("_")[1])
        except (ValueError, IndexError):
            pass

    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid relay state - cannot determine organization.",
        )

    # Load SSO config
    sso_config = _get_sso_config(db, org_id)
    if not sso_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO configuration not found or disabled.",
        )

    # Parse and validate the SAML response
    is_valid, attributes = parse_saml_response(
        saml_response_b64=saml_response_b64,
        idp_certificate=sso_config.idp_certificate,
        expected_audience=sso_config.sp_entity_id,
    )

    if not is_valid:
        error_msg = attributes.get("error", "Unknown error")
        logger.warning(f"SAML validation failed for org {org_id}: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"SAML assertion validation failed: {error_msg}",
        )

    email = attributes.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email address in SAML assertion.",
        )

    # Find or provision user
    user = _find_or_provision_user(
        db=db,
        email=email,
        first_name=attributes.get("first_name"),
        last_name=attributes.get("last_name"),
        organization_id=org_id,
        sso_provider="saml",
        sso_subject_id=attributes.get("name_id", email),
        groups=attributes.get("groups", []),
        sso_config=sso_config,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found and auto-provisioning is disabled. Contact your administrator.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact your administrator.",
        )

    # Create tokens
    auth_funcs = _get_auth_functions()
    tokens = _create_sso_tokens(user, auth_funcs)

    db.commit()

    # Redirect to frontend with tokens in URL fragment (not query string)
    # Fragments are never sent to servers in Referer headers or logged by proxies
    frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
    redirect_url = (
        f"{frontend_url}/sso/callback"
        f"#access_token={tokens['access_token']}"
        f"&refresh_token={tokens['refresh_token']}"
        f"&token_type=bearer"
    )

    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/api/v1/auth/sso/saml/slo")
async def saml_slo(
    email: Optional[str] = None,
    org_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Initiate SAML Single Logout (SLO).

    Redirects to IdP logout endpoint.
    """
    from auth.saml_sso import create_logout_request

    if not org_id or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="org_id and email are required for SLO.",
        )

    sso_config = _get_sso_config(db, org_id)
    if not sso_config or not sso_config.idp_slo_url:
        # If no SLO configured, just redirect to frontend logout
        frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
        return RedirectResponse(url=f"{frontend_url}/logout", status_code=302)

    redirect_url = create_logout_request(
        idp_slo_url=sso_config.idp_slo_url,
        name_id=email,
        sp_entity_id=sso_config.sp_entity_id,
    )

    return RedirectResponse(url=redirect_url, status_code=302)


# =============================================================================
# OIDC ENDPOINTS
# =============================================================================

@router.get("/api/v1/auth/sso/oidc/login")
async def oidc_login(
    email: Optional[str] = None,
    org_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Initiate OIDC login by redirecting to the authorization endpoint.

    Provide either `email` (to auto-detect org by domain) or `org_id`.
    """
    from auth.oidc_provider import create_authorization_url

    sso_config = None
    organization = None

    if org_id:
        from database.models.core import Organization
        from database.models.sso import SSOConfig
        organization = db.query(Organization).filter(Organization.id == org_id).first()
        if organization:
            sso_config = db.query(SSOConfig).filter(
                SSOConfig.organization_id == org_id,
                SSOConfig.enabled == True,
            ).first()
    elif email and "@" in email:
        domain = email.split("@")[1].lower()
        organization, sso_config = _get_sso_config_by_domain(db, domain)

    if not sso_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO not configured for this organization.",
        )

    if sso_config.provider_type not in ("oidc", "both"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OIDC is not configured for this organization. Use SAML.",
        )

    if not sso_config.oidc_discovery_url or not sso_config.oidc_client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OIDC discovery URL or client ID not configured.",
        )

    auth_url, state, nonce = create_authorization_url(
        discovery_url=sso_config.oidc_discovery_url,
        client_id=sso_config.oidc_client_id,
        scopes=sso_config.oidc_scopes or "openid profile email",
    )

    if not auth_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create OIDC authorization URL. Check IdP configuration.",
        )

    # Store state for callback validation
    _oidc_state_store[state] = {
        "org_id": organization.id,
        "nonce": nonce,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Clean up old states (older than 10 minutes)
    _cleanup_oidc_states()

    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/api/v1/auth/sso/oidc/callback")
async def oidc_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    OIDC authorization code callback.

    Exchanges the authorization code for tokens, extracts user info,
    and creates a session.
    """
    from auth.oidc_provider import (
        exchange_code_for_tokens,
        extract_claims_from_id_token,
        fetch_userinfo,
        extract_user_attributes,
    )

    if error:
        logger.warning(f"OIDC callback error: {error} - {error_description}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OIDC authentication error: {error_description or error}",
        )

    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code or state parameter.",
        )

    # Validate state
    state_data = _oidc_state_store.pop(state, None)
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter. Please try logging in again.",
        )

    org_id = state_data["org_id"]

    # Load SSO config
    sso_config = _get_sso_config(db, org_id)
    if not sso_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO configuration not found or disabled.",
        )

    # Exchange code for tokens
    token_response = exchange_code_for_tokens(
        discovery_url=sso_config.oidc_discovery_url,
        client_id=sso_config.oidc_client_id,
        client_secret=sso_config.oidc_client_secret or "",
        authorization_code=code,
    )

    if not token_response:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to exchange authorization code. Check IdP configuration.",
        )

    # Extract claims from ID token
    id_token = token_response.get("id_token")
    claims = {}
    if id_token:
        claims = extract_claims_from_id_token(id_token) or {}

    # Optionally fetch userinfo
    access_token_idp = token_response.get("access_token")
    userinfo = None
    if access_token_idp and sso_config.oidc_discovery_url:
        userinfo = fetch_userinfo(sso_config.oidc_discovery_url, access_token_idp)

    # Extract user attributes
    user_attrs = extract_user_attributes(claims, userinfo)

    email = user_attrs.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email address in OIDC response.",
        )

    # Find or provision user
    user = _find_or_provision_user(
        db=db,
        email=email,
        first_name=user_attrs.get("first_name"),
        last_name=user_attrs.get("last_name"),
        organization_id=org_id,
        sso_provider="oidc",
        sso_subject_id=user_attrs.get("sub", email),
        groups=user_attrs.get("groups", []),
        sso_config=sso_config,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found and auto-provisioning is disabled. Contact your administrator.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact your administrator.",
        )

    # Create tokens
    auth_funcs = _get_auth_functions()
    tokens = _create_sso_tokens(user, auth_funcs)

    db.commit()

    # Redirect to frontend with tokens in URL fragment (not query string)
    # Fragments are never sent to servers in Referer headers or logged by proxies
    frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
    redirect_url = (
        f"{frontend_url}/sso/callback"
        f"#access_token={tokens['access_token']}"
        f"&refresh_token={tokens['refresh_token']}"
        f"&token_type=bearer"
    )

    return RedirectResponse(url=redirect_url, status_code=302)


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================

@router.get("/api/v1/admin/sso/config", response_model=SSOConfigResponse)
async def get_sso_config(
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user_dep()),
):
    """
    Get SSO configuration for the current user's organization.

    Requires admin or site_admin role.
    """
    from database.models.sso import SSOConfig

    if current_user.permission_role not in ("admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User is not assigned to an organization")

    config = db.query(SSOConfig).filter(
        SSOConfig.organization_id == current_user.organization_id,
    ).first()

    if not config:
        raise HTTPException(
            status_code=404,
            detail="SSO not configured for this organization.",
        )

    return SSOConfigResponse(
        id=config.id,
        organization_id=config.organization_id,
        provider_type=config.provider_type,
        idp_entity_id=config.idp_entity_id,
        idp_sso_url=config.idp_sso_url,
        idp_slo_url=config.idp_slo_url,
        has_idp_certificate=bool(config.idp_certificate),
        sp_entity_id=config.sp_entity_id,
        oidc_discovery_url=config.oidc_discovery_url,
        oidc_client_id=config.oidc_client_id,
        has_oidc_client_secret=bool(config.oidc_client_secret),
        oidc_scopes=config.oidc_scopes,
        default_role=config.default_role or "loan_officer",
        default_permission_role=config.default_permission_role or "sales",
        auto_provision=config.auto_provision,
        enabled=config.enabled,
    )


@router.put("/api/v1/admin/sso/config", response_model=SSOConfigResponse)
async def update_sso_config(
    request: SSOConfigUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user_dep()),
):
    """
    Create or update SSO configuration for the current user's organization.

    Requires admin or site_admin role.
    """
    from database.models.sso import SSOConfig

    if current_user.permission_role not in ("admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User is not assigned to an organization")

    org_id = current_user.organization_id

    # Find existing config or create new one
    config = db.query(SSOConfig).filter(
        SSOConfig.organization_id == org_id,
    ).first()

    if not config:
        config = SSOConfig(organization_id=org_id)
        db.add(config)

    # Update fields
    config.provider_type = request.provider_type
    config.default_role = request.default_role
    config.default_permission_role = request.default_permission_role
    config.auto_provision = request.auto_provision
    config.enabled = request.enabled

    # SAML fields
    if request.idp_entity_id is not None:
        config.idp_entity_id = request.idp_entity_id
    if request.idp_sso_url is not None:
        config.idp_sso_url = request.idp_sso_url
    if request.idp_slo_url is not None:
        config.idp_slo_url = request.idp_slo_url
    if request.idp_certificate is not None:
        config.idp_certificate = request.idp_certificate
    if request.sp_entity_id is not None:
        config.sp_entity_id = request.sp_entity_id

    # OIDC fields
    if request.oidc_discovery_url is not None:
        config.oidc_discovery_url = request.oidc_discovery_url
    if request.oidc_client_id is not None:
        config.oidc_client_id = request.oidc_client_id
    if request.oidc_client_secret is not None:
        config.oidc_client_secret = request.oidc_client_secret
    if request.oidc_scopes is not None:
        config.oidc_scopes = request.oidc_scopes

    config.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(config)

    logger.info(f"SSO config updated for org {org_id} by user {current_user.id}")

    return SSOConfigResponse(
        id=config.id,
        organization_id=config.organization_id,
        provider_type=config.provider_type,
        idp_entity_id=config.idp_entity_id,
        idp_sso_url=config.idp_sso_url,
        idp_slo_url=config.idp_slo_url,
        has_idp_certificate=bool(config.idp_certificate),
        sp_entity_id=config.sp_entity_id,
        oidc_discovery_url=config.oidc_discovery_url,
        oidc_client_id=config.oidc_client_id,
        has_oidc_client_secret=bool(config.oidc_client_secret),
        oidc_scopes=config.oidc_scopes,
        default_role=config.default_role or "loan_officer",
        default_permission_role=config.default_permission_role or "sales",
        auto_provision=config.auto_provision,
        enabled=config.enabled,
    )


# =============================================================================
# HELPERS
# =============================================================================

def _cleanup_oidc_states():
    """Remove OIDC states older than 10 minutes."""
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    expired_keys = []

    for state_key, state_data in _oidc_state_store.items():
        created_str = state_data.get("created_at", "")
        try:
            created = datetime.fromisoformat(created_str)
            if created < cutoff:
                expired_keys.append(state_key)
        except (ValueError, TypeError):
            expired_keys.append(state_key)

    for key in expired_keys:
        _oidc_state_store.pop(key, None)

    if expired_keys:
        logger.debug(f"Cleaned up {len(expired_keys)} expired OIDC states")
