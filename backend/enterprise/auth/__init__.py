"""
Authentication Module for Mortgage CRM

Provides SSO/SAML, OIDC, and LDAP authentication support.
"""

from .sso import (
    SSOProvider,
    SSOStatus,
    SAMLConfig,
    OIDCConfig,
    LDAPConfig,
    SSOConfiguration,
    SSOSession,
    SSOUser,
    SAMLHandler,
    OIDCHandler,
    SSOManager,
    create_sso_routes,
)

__all__ = [
    "SSOProvider",
    "SSOStatus",
    "SAMLConfig",
    "OIDCConfig",
    "LDAPConfig",
    "SSOConfiguration",
    "SSOSession",
    "SSOUser",
    "SAMLHandler",
    "OIDCHandler",
    "SSOManager",
    "create_sso_routes",
]
