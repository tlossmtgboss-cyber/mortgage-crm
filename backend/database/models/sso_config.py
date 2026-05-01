"""
SSO Configuration Model (Enterprise SAML/OIDC)

Per-organization SSO configuration for enterprise customers.
Stores IdP metadata, certificates (encrypted at rest), attribute mappings,
and enforcement settings.

Usage:
    from database.models.sso_config import SSOConfiguration

    config = db.query(SSOConfiguration).filter(
        SSOConfiguration.organization_id == org_id,
        SSOConfiguration.is_active == True,
    ).first()
"""

import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from db import Base

logger = logging.getLogger(__name__)

# Attempt to import EncryptedString for at-rest encryption of certificates
try:
    from encryption_utils import EncryptedString
    _HAS_ENCRYPTION = True
except ImportError:
    _HAS_ENCRYPTION = False
    is_production = any([
        os.getenv("RAILWAY_ENVIRONMENT", "").lower() in ("production", "staging"),
        os.getenv("ENVIRONMENT", "").lower() in ("production", "staging"),
    ])
    if is_production:
        raise RuntimeError(
            "Encryption service required in production/staging for SSO certificate storage"
        )
    logger.warning("EncryptedString unavailable; SSO secrets stored as plaintext in dev mode")


# Valid SSO provider types
SSO_PROVIDERS = ("okta", "azure_ad", "onelogin", "google", "ping_identity", "custom")


class SSOConfiguration(Base):
    """Per-organization SSO configuration for enterprise SAML 2.0 / OIDC.

    Stores IdP connection details, X.509 certificates (encrypted at rest),
    attribute mapping rules, and enforcement settings.

    Security: x509_cert and oidc_client_secret are encrypted at rest using
    Fernet symmetric encryption (EncryptedString TypeDecorator).

    Enforcement: When enforce_sso is True, password-based login is blocked
    for all users in the organization. They must authenticate via the IdP.
    """
    __tablename__ = "sso_configurations"
    __table_args__ = (
        Index("ix_sso_configurations_org_active", "organization_id", "is_active"),
        UniqueConstraint("organization_id", name="uq_sso_configurations_org_id"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # Provider identification
    provider = Column(
        String(50),
        nullable=False,
        default="custom",
        comment="IdP provider: okta, azure_ad, onelogin, google, ping_identity, custom",
    )

    # SAML 2.0 IdP metadata
    entity_id = Column(String(500), nullable=True, comment="IdP Entity ID (issuer)")
    sso_url = Column(String(1000), nullable=True, comment="IdP SSO endpoint URL")
    slo_url = Column(String(1000), nullable=True, comment="IdP Single Logout URL")

    # X.509 certificate - encrypted at rest
    x509_cert = Column(
        EncryptedString(8000) if _HAS_ENCRYPTION else Text,
        nullable=True,
        comment="PEM-encoded IdP X.509 signing certificate (encrypted at rest)",
    )

    # SP (Service Provider) configuration overrides
    sp_entity_id = Column(
        String(500),
        nullable=True,
        comment="SP Entity ID override (defaults to api.perenniaai.com)",
    )

    # Attribute mapping: JSON dict mapping IdP attribute names to CRM fields
    # Example: {"email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    #           "first_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
    #           "last_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
    #           "groups": "http://schemas.xmlsoap.org/claims/Group"}
    attribute_mapping = Column(
        JSONB,
        nullable=True,
        default=dict,
        comment="IdP attribute name -> CRM field mapping",
    )

    # Default role for JIT-provisioned users
    default_role = Column(String(50), default="loan_officer")
    default_permission_role = Column(String(50), default="sales")

    # Enforcement: when True, password login is blocked for this org
    enforce_sso = Column(Boolean, default=False, comment="Block password login when True")

    # Auto-provision users on first SSO login
    auto_provision = Column(Boolean, default=True)

    # Whether this configuration is active
    is_active = Column(Boolean, default=True)

    # OIDC fields (for providers that use OIDC instead of / in addition to SAML)
    oidc_discovery_url = Column(String(1000), nullable=True)
    oidc_client_id = Column(String(500), nullable=True)
    oidc_client_secret = Column(
        EncryptedString(1000) if _HAS_ENCRYPTION else Text,
        nullable=True,
        comment="OIDC client secret (encrypted at rest)",
    )

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    organization = relationship("Organization", backref="sso_configuration")

    @property
    def is_saml_configured(self) -> bool:
        """True when SAML IdP metadata is minimally configured."""
        return bool(self.entity_id and self.sso_url)

    @property
    def is_oidc_configured(self) -> bool:
        """True when OIDC is minimally configured."""
        return bool(self.oidc_discovery_url and self.oidc_client_id)

    @property
    def provider_display_name(self) -> str:
        """Human-readable provider name."""
        names = {
            "okta": "Okta",
            "azure_ad": "Azure AD (Entra ID)",
            "onelogin": "OneLogin",
            "google": "Google Workspace",
            "ping_identity": "Ping Identity",
            "custom": "Custom SAML",
        }
        return names.get(self.provider, self.provider)


__all__ = ["SSOConfiguration", "SSO_PROVIDERS"]
