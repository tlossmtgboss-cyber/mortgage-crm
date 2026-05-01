"""
SSO Pydantic Schemas

Request and response schemas for SSO configuration and authentication endpoints.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Admin Configuration Schemas
# =============================================================================

class SSOConfigCreate(BaseModel):
    """Request body for creating/updating SSO configuration."""

    provider: str = Field(
        "custom",
        description="IdP provider: okta, azure_ad, onelogin, google, ping_identity, custom",
    )

    # SAML fields
    entity_id: Optional[str] = Field(None, description="IdP Entity ID (issuer)")
    sso_url: Optional[str] = Field(None, description="IdP SSO endpoint URL")
    slo_url: Optional[str] = Field(None, description="IdP Single Logout URL")
    x509_cert: Optional[str] = Field(None, description="PEM-encoded IdP X.509 signing certificate")
    sp_entity_id: Optional[str] = Field(None, description="SP Entity ID override")

    # Attribute mapping
    attribute_mapping: Optional[Dict[str, str]] = Field(
        None,
        description="IdP attribute name -> CRM field mapping (email, first_name, last_name, groups)",
    )

    # Defaults for JIT provisioning
    default_role: str = Field("loan_officer", description="Default legacy role for new SSO users")
    default_permission_role: str = Field("sales", description="Default permission role for new SSO users")

    # Enforcement
    enforce_sso: bool = Field(False, description="Block password login when True")
    auto_provision: bool = Field(True, description="Auto-create users on first SSO login")

    # OIDC fields
    oidc_discovery_url: Optional[str] = Field(None, description="OIDC discovery URL")
    oidc_client_id: Optional[str] = Field(None, description="OIDC client ID")
    oidc_client_secret: Optional[str] = Field(None, description="OIDC client secret")


class SSOConfigUpdate(BaseModel):
    """Partial update for SSO configuration. All fields optional."""

    provider: Optional[str] = None
    entity_id: Optional[str] = None
    sso_url: Optional[str] = None
    slo_url: Optional[str] = None
    x509_cert: Optional[str] = None
    sp_entity_id: Optional[str] = None
    attribute_mapping: Optional[Dict[str, str]] = None
    default_role: Optional[str] = None
    default_permission_role: Optional[str] = None
    enforce_sso: Optional[bool] = None
    auto_provision: Optional[bool] = None
    oidc_discovery_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None


class SSOConfigResponse(BaseModel):
    """Response for SSO configuration (secrets redacted)."""

    id: str
    organization_id: int
    provider: str
    provider_display_name: str

    # SAML
    entity_id: Optional[str] = None
    sso_url: Optional[str] = None
    slo_url: Optional[str] = None
    has_x509_cert: bool = False
    sp_entity_id: Optional[str] = None

    # Attribute mapping
    attribute_mapping: Optional[Dict[str, str]] = None

    # Provisioning defaults
    default_role: str = "loan_officer"
    default_permission_role: str = "sales"
    enforce_sso: bool = False
    auto_provision: bool = True
    is_active: bool = True

    # OIDC
    oidc_discovery_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    has_oidc_client_secret: bool = False

    # Status
    is_saml_configured: bool = False
    is_oidc_configured: bool = False

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SSOTestRequest(BaseModel):
    """Request to test SSO configuration."""
    test_email: Optional[str] = Field(
        None,
        description="Optional email to simulate SSO login for (dry run only)",
    )


class SSOTestResponse(BaseModel):
    """Response for SSO configuration test."""
    saml_configured: bool = False
    saml_metadata_valid: bool = False
    saml_sso_url_reachable: bool = False
    oidc_configured: bool = False
    oidc_discovery_reachable: bool = False
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# =============================================================================
# SSO Login Flow Schemas
# =============================================================================

class SSOLoginInitResponse(BaseModel):
    """Response when initiating SSO login (redirect info)."""
    redirect_url: str
    request_id: str


class SSOCallbackResponse(BaseModel):
    """Response after successful SSO callback."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    email: str
    organization_id: int


class SSOMetadataResponse(BaseModel):
    """SP metadata info (non-XML summary)."""
    entity_id: str
    acs_url: str
    slo_url: str
    metadata_url: str


class IdPMetadataUpload(BaseModel):
    """Upload IdP metadata XML to auto-configure SSO."""
    metadata_xml: str = Field(..., description="IdP metadata XML content")


__all__ = [
    "SSOConfigCreate",
    "SSOConfigUpdate",
    "SSOConfigResponse",
    "SSOTestRequest",
    "SSOTestResponse",
    "SSOLoginInitResponse",
    "SSOCallbackResponse",
    "SSOMetadataResponse",
    "IdPMetadataUpload",
]
