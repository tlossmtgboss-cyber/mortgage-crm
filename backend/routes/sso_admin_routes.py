"""
SSO Admin Routes - Enterprise SSO Configuration Management

Provides admin endpoints for managing the SSOConfiguration model
(the new per-org SSO config with encrypted certificate storage).

Endpoints:
    GET    /api/v1/admin/sso/configuration   - Get org SSO config
    PUT    /api/v1/admin/sso/configuration   - Update SSO config
    POST   /api/v1/admin/sso/test            - Test SSO configuration
    DELETE /api/v1/admin/sso/configuration   - Disable SSO

All endpoints require admin or site_admin permission_role.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from schemas.sso_schemas import (
    SSOConfigCreate,
    SSOConfigUpdate,
    SSOConfigResponse,
    SSOTestRequest,
    SSOTestResponse,
    IdPMetadataUpload,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["SSO - Admin Configuration"])


# =============================================================================
# Helpers
# =============================================================================

def _get_current_user_dep():
    """Get current user dependency at runtime to avoid circular imports."""
    import main
    return main.get_current_user


def _require_admin(current_user) -> None:
    """Verify admin or site_admin role. Raises 403 if not."""
    user_role = getattr(current_user, "permission_role", "") or ""
    is_admin = (
        getattr(current_user, "is_platform_admin", False)
        or user_role in ("admin", "platform_admin", "site_admin")
    )
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Site Admin role required for SSO configuration.",
        )


def _require_org(current_user) -> int:
    """Extract and validate organization_id. Raises 400 if missing."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not assigned to an organization.",
        )
    return org_id


def _config_to_response(config) -> SSOConfigResponse:
    """Convert SSOConfiguration model to response schema."""
    return SSOConfigResponse(
        id=config.id,
        organization_id=config.organization_id,
        provider=config.provider,
        provider_display_name=config.provider_display_name,
        entity_id=config.entity_id,
        sso_url=config.sso_url,
        slo_url=config.slo_url,
        has_x509_cert=bool(config.x509_cert),
        sp_entity_id=config.sp_entity_id,
        attribute_mapping=config.attribute_mapping,
        default_role=config.default_role or "loan_officer",
        default_permission_role=config.default_permission_role or "sales",
        enforce_sso=config.enforce_sso,
        auto_provision=config.auto_provision,
        is_active=config.is_active,
        oidc_discovery_url=config.oidc_discovery_url,
        oidc_client_id=config.oidc_client_id,
        has_oidc_client_secret=bool(config.oidc_client_secret),
        is_saml_configured=config.is_saml_configured,
        is_oidc_configured=config.is_oidc_configured,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


# =============================================================================
# GET /api/v1/admin/sso/configuration
# =============================================================================

@router.get(
    "/api/v1/admin/sso/configuration",
    response_model=SSOConfigResponse,
)
async def get_sso_config(
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user_dep()),
):
    """Get SSO configuration for the current user's organization.

    Returns the SSOConfiguration record with secrets redacted
    (has_x509_cert, has_oidc_client_secret booleans instead of values).
    """
    _require_admin(current_user)
    org_id = _require_org(current_user)

    from database.models.sso_config import SSOConfiguration

    config = db.query(SSOConfiguration).filter(
        SSOConfiguration.organization_id == org_id,
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO not configured for this organization. Use PUT to create.",
        )

    return _config_to_response(config)


# =============================================================================
# PUT /api/v1/admin/sso/configuration
# =============================================================================

@router.put(
    "/api/v1/admin/sso/configuration",
    response_model=SSOConfigResponse,
)
async def update_sso_config(
    request: SSOConfigCreate,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user_dep()),
):
    """Create or update SSO configuration for the current user's organization.

    Accepts full or partial configuration. Can be used to:
    - Set up SSO for the first time (provide IdP entity_id, sso_url, certificate)
    - Update existing configuration (change provider, URLs, certificate)
    - Enable/disable enforcement (enforce_sso)
    - Configure attribute mapping

    The x509_cert is encrypted at rest automatically by the model.
    """
    _require_admin(current_user)
    org_id = _require_org(current_user)

    from database.models.sso_config import SSOConfiguration, SSO_PROVIDERS

    # Validate provider
    if request.provider and request.provider not in SSO_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider '{request.provider}'. Must be one of: {', '.join(SSO_PROVIDERS)}",
        )

    # Find or create
    config = db.query(SSOConfiguration).filter(
        SSOConfiguration.organization_id == org_id,
    ).first()

    if not config:
        config = SSOConfiguration(organization_id=org_id)
        db.add(config)

    # Update all provided fields
    config.provider = request.provider
    config.default_role = request.default_role
    config.default_permission_role = request.default_permission_role
    config.enforce_sso = request.enforce_sso
    config.auto_provision = request.auto_provision

    if request.entity_id is not None:
        config.entity_id = request.entity_id
    if request.sso_url is not None:
        config.sso_url = request.sso_url
    if request.slo_url is not None:
        config.slo_url = request.slo_url
    if request.x509_cert is not None:
        config.x509_cert = request.x509_cert
    if request.sp_entity_id is not None:
        config.sp_entity_id = request.sp_entity_id
    if request.attribute_mapping is not None:
        config.attribute_mapping = request.attribute_mapping

    # OIDC fields
    if request.oidc_discovery_url is not None:
        config.oidc_discovery_url = request.oidc_discovery_url
    if request.oidc_client_id is not None:
        config.oidc_client_id = request.oidc_client_id
    if request.oidc_client_secret is not None:
        config.oidc_client_secret = request.oidc_client_secret

    config.is_active = True
    config.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(config)

    logger.info(
        f"SSO configuration updated: org_id={org_id}, provider={config.provider}, "
        f"user_id={current_user.id}"
    )

    return _config_to_response(config)


# =============================================================================
# POST /api/v1/admin/sso/test
# =============================================================================

@router.post(
    "/api/v1/admin/sso/test",
    response_model=SSOTestResponse,
)
async def test_sso_config(
    request: SSOTestRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user_dep()),
):
    """Test SSO configuration for the current user's organization.

    Validates that:
    - SAML: entity_id, sso_url, and x509_cert are present
    - SAML: SP metadata XML can be generated
    - OIDC: discovery_url is reachable and returns valid JSON (if configured)

    Does NOT perform a full SAML login — that requires IdP interaction.
    """
    _require_admin(current_user)
    org_id = _require_org(current_user)

    from database.models.sso_config import SSOConfiguration

    config = db.query(SSOConfiguration).filter(
        SSOConfiguration.organization_id == org_id,
    ).first()

    if not config:
        return SSOTestResponse(
            errors=["SSO not configured. Use PUT /api/v1/admin/sso/configuration first."],
        )

    errors = []
    warnings = []
    saml_configured = False
    saml_metadata_valid = False
    saml_sso_url_reachable = False
    oidc_configured = False
    oidc_discovery_reachable = False

    # --- SAML checks ---
    if config.entity_id or config.sso_url:
        if not config.entity_id:
            errors.append("SAML: entity_id (IdP Entity ID) is missing.")
        if not config.sso_url:
            errors.append("SAML: sso_url (IdP SSO URL) is missing.")
        if not config.x509_cert:
            warnings.append(
                "SAML: x509_cert (IdP signing certificate) is missing. "
                "Signature verification will be skipped — not recommended for production."
            )

        if config.entity_id and config.sso_url:
            saml_configured = True

            # Test SP metadata generation
            try:
                from auth.sso import generate_sp_metadata_xml
                from database.models.core import Organization

                org = db.query(Organization).filter(Organization.id == org_id).first()
                org_slug = org.slug if org else None
                metadata = generate_sp_metadata_xml(org_slug=org_slug)
                if metadata and "EntityDescriptor" in metadata:
                    saml_metadata_valid = True
                else:
                    errors.append("SAML: SP metadata generation produced invalid XML.")
            except Exception as e:
                errors.append(f"SAML: SP metadata generation failed: {e}")

            # Test SSO URL reachability (HEAD request)
            try:
                import urllib.request
                req = urllib.request.Request(config.sso_url, method="HEAD")
                req.add_header("User-Agent", "Perennia-SSO-Test/1.0")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status < 500:
                        saml_sso_url_reachable = True
            except Exception as e:
                # Many IdPs block HEAD; try GET
                try:
                    import urllib.request
                    req = urllib.request.Request(config.sso_url, method="GET")
                    req.add_header("User-Agent", "Perennia-SSO-Test/1.0")
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if resp.status < 500:
                            saml_sso_url_reachable = True
                except Exception:
                    warnings.append(f"SAML: Could not reach SSO URL ({config.sso_url}): {e}")

    # --- OIDC checks ---
    if config.oidc_discovery_url or config.oidc_client_id:
        if not config.oidc_discovery_url:
            errors.append("OIDC: discovery_url is missing.")
        if not config.oidc_client_id:
            errors.append("OIDC: client_id is missing.")
        if not config.oidc_client_secret:
            warnings.append("OIDC: client_secret is missing.")

        if config.oidc_discovery_url and config.oidc_client_id:
            oidc_configured = True

            # Test discovery URL reachability
            try:
                import urllib.request
                import json

                req = urllib.request.Request(config.oidc_discovery_url)
                req.add_header("User-Agent", "Perennia-SSO-Test/1.0")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    body = json.loads(resp.read())
                    if "authorization_endpoint" in body:
                        oidc_discovery_reachable = True
                    else:
                        errors.append("OIDC: Discovery document missing authorization_endpoint.")
            except Exception as e:
                warnings.append(f"OIDC: Could not reach discovery URL: {e}")

    # --- General checks ---
    if not saml_configured and not oidc_configured:
        errors.append("Neither SAML nor OIDC is configured. Provide at minimum entity_id + sso_url for SAML.")

    if config.enforce_sso and not config.is_active:
        errors.append("enforce_sso is True but configuration is not active.")

    if not config.auto_provision:
        warnings.append(
            "auto_provision is disabled. New SSO users will be rejected unless "
            "pre-created in the system."
        )

    return SSOTestResponse(
        saml_configured=saml_configured,
        saml_metadata_valid=saml_metadata_valid,
        saml_sso_url_reachable=saml_sso_url_reachable,
        oidc_configured=oidc_configured,
        oidc_discovery_reachable=oidc_discovery_reachable,
        errors=errors,
        warnings=warnings,
    )


# =============================================================================
# DELETE /api/v1/admin/sso/configuration
# =============================================================================

@router.delete("/api/v1/admin/sso/configuration")
async def disable_sso_config(
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user_dep()),
):
    """Disable SSO for the current user's organization.

    Sets is_active = False and enforce_sso = False on the SSOConfiguration.
    Does NOT delete the record (preserves audit trail and allows re-enabling).

    After disabling, users will need to log in with email/password.
    """
    _require_admin(current_user)
    org_id = _require_org(current_user)

    from database.models.sso_config import SSOConfiguration

    config = db.query(SSOConfiguration).filter(
        SSOConfiguration.organization_id == org_id,
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO not configured for this organization.",
        )

    config.is_active = False
    config.enforce_sso = False
    config.updated_at = datetime.now(timezone.utc)

    # Also disable enforcement on the Organization model if it was set
    from database.models.core import Organization
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org and org.sso_enforced:
        org.sso_enforced = False

    db.commit()

    logger.info(f"SSO disabled for org_id={org_id} by user_id={current_user.id}")

    return {
        "status": "disabled",
        "message": "SSO has been disabled. Users can now log in with email and password.",
        "organization_id": org_id,
    }


# =============================================================================
# POST /api/v1/admin/sso/configuration/metadata-upload
# =============================================================================

@router.post(
    "/api/v1/admin/sso/configuration/metadata-upload",
    response_model=SSOConfigResponse,
)
async def upload_idp_metadata(
    request: IdPMetadataUpload,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user_dep()),
):
    """Upload IdP metadata XML to auto-configure SSO.

    Parses the metadata XML and extracts:
    - entity_id
    - sso_url
    - slo_url
    - x509_cert

    These values are saved to the SSOConfiguration. Existing values
    for these fields are overwritten.
    """
    _require_admin(current_user)
    org_id = _require_org(current_user)

    from auth.sso import parse_idp_metadata_xml
    from database.models.sso_config import SSOConfiguration

    # Parse the metadata
    try:
        parsed = parse_idp_metadata_xml(request.metadata_xml)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse IdP metadata: {e}",
        )

    if not parsed.get("entity_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IdP metadata missing entityID attribute.",
        )

    if not parsed.get("sso_url"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IdP metadata missing SingleSignOnService endpoint.",
        )

    # Find or create config
    config = db.query(SSOConfiguration).filter(
        SSOConfiguration.organization_id == org_id,
    ).first()

    if not config:
        config = SSOConfiguration(organization_id=org_id)
        db.add(config)

    config.entity_id = parsed["entity_id"]
    config.sso_url = parsed["sso_url"]
    if parsed.get("slo_url"):
        config.slo_url = parsed["slo_url"]
    if parsed.get("x509_cert"):
        config.x509_cert = parsed["x509_cert"]

    config.is_active = True
    config.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(config)

    logger.info(
        f"IdP metadata uploaded for org_id={org_id}: "
        f"entity_id={config.entity_id}, sso_url={config.sso_url}"
    )

    return _config_to_response(config)


__all__ = ["router"]
