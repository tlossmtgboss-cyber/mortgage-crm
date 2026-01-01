"""
Multi-Tenancy Module for Mortgage CRM

Provides tenant isolation, management, and lifecycle handling.
"""

from .tenant import (
    TenantIsolationLevel,
    TenantStatus,
    TenantTier,
    TenantConfig,
    TenantContext,
    TenantManager,
    TenantAwareSession,
    TenantMiddleware,
    get_current_tenant,
    set_current_tenant,
    clear_current_tenant,
    require_tenant,
    require_feature,
)

__all__ = [
    "TenantIsolationLevel",
    "TenantStatus",
    "TenantTier",
    "TenantConfig",
    "TenantContext",
    "TenantManager",
    "TenantAwareSession",
    "TenantMiddleware",
    "get_current_tenant",
    "set_current_tenant",
    "clear_current_tenant",
    "require_tenant",
    "require_feature",
]
