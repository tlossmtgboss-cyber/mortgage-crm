"""
SSO Configuration Model
Enterprise Readiness Checks 4.5, 5.9, 5.10, 5.11, 5.12

Stores SAML and OIDC configuration per organization for single sign-on.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text,
    ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db import Base


class SSOConfig(Base):
    """SSO configuration per organization. Supports SAML 2.0 and OIDC."""
    __tablename__ = "sso_configs"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uix_sso_config_org"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )

    # Provider type: 'saml', 'oidc', or 'both'
    provider_type = Column(String, nullable=False, default="saml")

    # ---- SAML 2.0 fields ----
    idp_entity_id = Column(String, nullable=True)
    idp_sso_url = Column(String, nullable=True)       # IdP login URL
    idp_slo_url = Column(String, nullable=True)        # IdP logout URL
    idp_certificate = Column(Text, nullable=True)      # PEM-encoded X.509 cert

    # SP (Service Provider) entity ID override; defaults to app URL
    sp_entity_id = Column(String, nullable=True)

    # ---- OIDC fields ----
    oidc_discovery_url = Column(String, nullable=True)  # e.g. https://accounts.google.com/.well-known/openid-configuration
    oidc_client_id = Column(String, nullable=True)
    oidc_client_secret = Column(Text, nullable=True)    # Encrypted at rest in production
    oidc_scopes = Column(String, default="openid profile email")

    # ---- Common fields ----
    # Default role assigned to JIT-provisioned users
    default_role = Column(String, default="loan_officer")
    default_permission_role = Column(String, default="sales")

    # Whether to auto-create users on first SSO login
    auto_provision = Column(Boolean, default=True)

    # Whether this SSO config is active
    enabled = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship
    organization = relationship("Organization", backref="sso_config")


__all__ = ["SSOConfig"]
