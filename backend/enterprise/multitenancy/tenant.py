"""
Multi-Tenancy Architecture for Mortgage CRM

Supports multiple isolation models:
- Database-per-tenant: Complete isolation with separate databases
- Schema-per-tenant: Shared database with separate schemas
- Row-level: Shared tables with tenant_id column filtering

Enterprise Features:
- Tenant provisioning and lifecycle management
- Data isolation and cross-tenant query prevention
- Tenant-specific configuration and branding
- Resource quotas and usage tracking
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypeVar

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


class TenantIsolationLevel(str, Enum):
    """Tenant isolation levels."""
    DATABASE = "database"      # Separate database per tenant
    SCHEMA = "schema"          # Separate schema per tenant
    ROW_LEVEL = "row_level"    # Shared tables with tenant_id


class TenantStatus(str, Enum):
    """Tenant lifecycle status."""
    PENDING = "pending"
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEPROVISIONING = "deprovisioning"
    ARCHIVED = "archived"


class TenantTier(str, Enum):
    """Tenant subscription tiers."""
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    DEDICATED = "dedicated"


@dataclass
class TenantConfig:
    """Tenant-specific configuration."""
    tenant_id: str
    name: str
    domain: str
    tier: TenantTier
    status: TenantStatus
    isolation_level: TenantIsolationLevel

    # Branding
    logo_url: Optional[str] = None
    primary_color: str = "#1a73e8"
    secondary_color: str = "#4285f4"

    # Features
    enabled_features: List[str] = field(default_factory=list)
    max_users: int = 10
    max_loans_per_month: int = 100
    max_storage_gb: int = 10

    # Database connection
    database_url: Optional[str] = None
    schema_name: Optional[str] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TenantContext:
    """Current tenant context for request handling."""
    tenant_id: str
    tenant: TenantConfig
    user_id: Optional[str] = None
    session: Optional[Session] = None

    def __post_init__(self):
        """Validate context."""
        if not self.tenant_id:
            raise ValueError("tenant_id is required")


# Thread-local storage for current tenant context
import threading
_tenant_context = threading.local()


def get_current_tenant() -> Optional[TenantContext]:
    """Get current tenant context from thread-local storage."""
    return getattr(_tenant_context, "context", None)


def set_current_tenant(context: TenantContext) -> None:
    """Set current tenant context in thread-local storage."""
    _tenant_context.context = context


def clear_current_tenant() -> None:
    """Clear current tenant context."""
    _tenant_context.context = None


class TenantManager:
    """Manages tenant lifecycle and configuration."""

    def __init__(
        self,
        master_db_url: str,
        isolation_level: TenantIsolationLevel = TenantIsolationLevel.ROW_LEVEL
    ):
        self.master_db_url = master_db_url
        self.default_isolation = isolation_level
        self._master_engine = create_engine(master_db_url)
        self._tenant_engines: Dict[str, Engine] = {}
        self._tenant_cache: Dict[str, TenantConfig] = {}

    def create_tenant(
        self,
        name: str,
        domain: str,
        tier: TenantTier = TenantTier.STARTER,
        isolation_level: Optional[TenantIsolationLevel] = None,
        admin_email: str = None,
    ) -> TenantConfig:
        """Create a new tenant."""
        tenant_id = str(uuid.uuid4())
        isolation = isolation_level or self.default_isolation

        tenant = TenantConfig(
            tenant_id=tenant_id,
            name=name,
            domain=domain,
            tier=tier,
            status=TenantStatus.PROVISIONING,
            isolation_level=isolation,
            enabled_features=self._get_tier_features(tier),
            max_users=self._get_tier_limits(tier)["max_users"],
            max_loans_per_month=self._get_tier_limits(tier)["max_loans"],
            max_storage_gb=self._get_tier_limits(tier)["max_storage_gb"],
        )

        # Provision tenant resources
        self._provision_tenant(tenant)

        # Store tenant config
        self._store_tenant(tenant)

        # Create admin user if email provided
        if admin_email:
            self._create_tenant_admin(tenant, admin_email)

        tenant.status = TenantStatus.ACTIVE
        self._update_tenant(tenant)

        logger.info(f"Created tenant: {tenant_id} ({name})")
        return tenant

    def _provision_tenant(self, tenant: TenantConfig) -> None:
        """Provision tenant resources based on isolation level."""
        if tenant.isolation_level == TenantIsolationLevel.DATABASE:
            self._create_tenant_database(tenant)
        elif tenant.isolation_level == TenantIsolationLevel.SCHEMA:
            self._create_tenant_schema(tenant)
        # ROW_LEVEL doesn't need special provisioning

    def _create_tenant_database(self, tenant: TenantConfig) -> None:
        """Create a dedicated database for tenant."""
        db_name = f"mortgage_crm_tenant_{tenant.tenant_id.replace('-', '_')}"

        with self._master_engine.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(f"CREATE DATABASE {db_name}"))

        # Build tenant database URL
        base_url = self.master_db_url.rsplit("/", 1)[0]
        tenant.database_url = f"{base_url}/{db_name}"

        # Run migrations on tenant database
        self._run_tenant_migrations(tenant)

    def _create_tenant_schema(self, tenant: TenantConfig) -> None:
        """Create a dedicated schema for tenant."""
        schema_name = f"tenant_{tenant.tenant_id.replace('-', '_')}"
        tenant.schema_name = schema_name

        with self._master_engine.connect() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
            conn.commit()

        # Run migrations in tenant schema
        self._run_tenant_migrations(tenant)

    def _run_tenant_migrations(self, tenant: TenantConfig) -> None:
        """Run database migrations for tenant."""
        # Get tenant engine
        engine = self.get_tenant_engine(tenant.tenant_id)

        # Apply base schema migrations
        # This would integrate with Alembic or similar
        logger.info(f"Running migrations for tenant: {tenant.tenant_id}")

    def _get_tier_features(self, tier: TenantTier) -> List[str]:
        """Get enabled features for tier."""
        base_features = [
            "lead_management",
            "loan_processing",
            "document_management",
            "basic_reporting",
        ]

        professional_features = base_features + [
            "advanced_reporting",
            "api_access",
            "workflow_automation",
            "email_integration",
        ]

        enterprise_features = professional_features + [
            "ai_underwriting",
            "custom_branding",
            "sso_saml",
            "audit_logging",
            "compliance_monitoring",
            "multi_branch",
        ]

        dedicated_features = enterprise_features + [
            "dedicated_infrastructure",
            "custom_sla",
            "priority_support",
            "custom_integrations",
        ]

        return {
            TenantTier.STARTER: base_features,
            TenantTier.PROFESSIONAL: professional_features,
            TenantTier.ENTERPRISE: enterprise_features,
            TenantTier.DEDICATED: dedicated_features,
        }.get(tier, base_features)

    def _get_tier_limits(self, tier: TenantTier) -> Dict[str, int]:
        """Get resource limits for tier."""
        return {
            TenantTier.STARTER: {
                "max_users": 5,
                "max_loans": 50,
                "max_storage_gb": 5,
            },
            TenantTier.PROFESSIONAL: {
                "max_users": 25,
                "max_loans": 500,
                "max_storage_gb": 50,
            },
            TenantTier.ENTERPRISE: {
                "max_users": 100,
                "max_loans": 5000,
                "max_storage_gb": 500,
            },
            TenantTier.DEDICATED: {
                "max_users": -1,  # Unlimited
                "max_loans": -1,
                "max_storage_gb": -1,
            },
        }.get(tier, {"max_users": 5, "max_loans": 50, "max_storage_gb": 5})

    def _store_tenant(self, tenant: TenantConfig) -> None:
        """Store tenant configuration in master database."""
        with self._master_engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO tenants (
                    id, name, domain, tier, status, isolation_level,
                    database_url, schema_name, max_users, max_loans_per_month,
                    max_storage_gb, enabled_features, settings, created_at
                ) VALUES (
                    :id, :name, :domain, :tier, :status, :isolation_level,
                    :database_url, :schema_name, :max_users, :max_loans,
                    :max_storage_gb, :features, :settings, :created_at
                )
            """), {
                "id": tenant.tenant_id,
                "name": tenant.name,
                "domain": tenant.domain,
                "tier": tenant.tier.value,
                "status": tenant.status.value,
                "isolation_level": tenant.isolation_level.value,
                "database_url": tenant.database_url,
                "schema_name": tenant.schema_name,
                "max_users": tenant.max_users,
                "max_loans": tenant.max_loans_per_month,
                "max_storage_gb": tenant.max_storage_gb,
                "features": ",".join(tenant.enabled_features),
                "settings": "{}",
                "created_at": tenant.created_at,
            })
            conn.commit()

        self._tenant_cache[tenant.tenant_id] = tenant

    def _update_tenant(self, tenant: TenantConfig) -> None:
        """Update tenant configuration."""
        with self._master_engine.connect() as conn:
            conn.execute(text("""
                UPDATE tenants SET
                    name = :name,
                    domain = :domain,
                    tier = :tier,
                    status = :status,
                    max_users = :max_users,
                    max_loans_per_month = :max_loans,
                    enabled_features = :features
                WHERE id = :id
            """), {
                "id": tenant.tenant_id,
                "name": tenant.name,
                "domain": tenant.domain,
                "tier": tenant.tier.value,
                "status": tenant.status.value,
                "max_users": tenant.max_users,
                "max_loans": tenant.max_loans_per_month,
                "features": ",".join(tenant.enabled_features),
            })
            conn.commit()

        self._tenant_cache[tenant.tenant_id] = tenant

    def _create_tenant_admin(self, tenant: TenantConfig, email: str) -> None:
        """Create admin user for tenant."""
        # Generate temporary password
        temp_password = secrets.token_urlsafe(12)

        engine = self.get_tenant_engine(tenant.tenant_id)
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO users (
                    id, email, role, tenant_id, is_active, created_at
                ) VALUES (
                    :id, :email, 'admin', :tenant_id, true, :created_at
                )
            """), {
                "id": str(uuid.uuid4()),
                "email": email,
                "tenant_id": tenant.tenant_id,
                "created_at": datetime.utcnow(),
            })
            conn.commit()

        # Send welcome email with password
        logger.info(f"Created admin user for tenant {tenant.tenant_id}: {email}")

    def get_tenant(self, tenant_id: str) -> Optional[TenantConfig]:
        """Get tenant by ID."""
        if tenant_id in self._tenant_cache:
            return self._tenant_cache[tenant_id]

        with self._master_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM tenants WHERE id = :id
            """), {"id": tenant_id})
            row = result.fetchone()

            if not row:
                return None

            tenant = TenantConfig(
                tenant_id=row.id,
                name=row.name,
                domain=row.domain,
                tier=TenantTier(row.tier),
                status=TenantStatus(row.status),
                isolation_level=TenantIsolationLevel(row.isolation_level),
                database_url=row.database_url,
                schema_name=row.schema_name,
                max_users=row.max_users,
                max_loans_per_month=row.max_loans_per_month,
                max_storage_gb=row.max_storage_gb,
                enabled_features=row.enabled_features.split(",") if row.enabled_features else [],
                created_at=row.created_at,
            )

            self._tenant_cache[tenant_id] = tenant
            return tenant

    def get_tenant_by_domain(self, domain: str) -> Optional[TenantConfig]:
        """Get tenant by domain."""
        with self._master_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id FROM tenants WHERE domain = :domain AND status = 'active'
            """), {"domain": domain})
            row = result.fetchone()

            if row:
                return self.get_tenant(row.id)
            return None

    def get_tenant_engine(self, tenant_id: str) -> Engine:
        """Get database engine for tenant."""
        if tenant_id in self._tenant_engines:
            return self._tenant_engines[tenant_id]

        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant not found: {tenant_id}")

        if tenant.isolation_level == TenantIsolationLevel.DATABASE:
            engine = create_engine(tenant.database_url)
        elif tenant.isolation_level == TenantIsolationLevel.SCHEMA:
            engine = create_engine(
                self.master_db_url,
                connect_args={"options": f"-csearch_path={tenant.schema_name},public"}
            )
        else:
            engine = self._master_engine

        self._tenant_engines[tenant_id] = engine
        return engine

    def suspend_tenant(self, tenant_id: str, reason: str = None) -> None:
        """Suspend a tenant."""
        tenant = self.get_tenant(tenant_id)
        if tenant:
            tenant.status = TenantStatus.SUSPENDED
            self._update_tenant(tenant)
            logger.warning(f"Suspended tenant: {tenant_id}, reason: {reason}")

    def archive_tenant(self, tenant_id: str) -> None:
        """Archive a tenant (soft delete)."""
        tenant = self.get_tenant(tenant_id)
        if tenant:
            tenant.status = TenantStatus.ARCHIVED
            self._update_tenant(tenant)

            # Clean up cached resources
            if tenant_id in self._tenant_engines:
                self._tenant_engines[tenant_id].dispose()
                del self._tenant_engines[tenant_id]

            if tenant_id in self._tenant_cache:
                del self._tenant_cache[tenant_id]

            logger.info(f"Archived tenant: {tenant_id}")


class TenantAwareSession:
    """Database session with automatic tenant filtering."""

    def __init__(
        self,
        tenant_id: str,
        engine: Engine,
        isolation_level: TenantIsolationLevel
    ):
        self.tenant_id = tenant_id
        self.engine = engine
        self.isolation_level = isolation_level
        self._session_factory = sessionmaker(bind=engine)

    @contextmanager
    def session(self):
        """Get a tenant-aware database session."""
        session = self._session_factory()

        try:
            if self.isolation_level == TenantIsolationLevel.ROW_LEVEL:
                # Enable row-level security
                self._enable_rls(session)

            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if self.isolation_level == TenantIsolationLevel.ROW_LEVEL:
                self._disable_rls(session)
            session.close()

    def _enable_rls(self, session: Session) -> None:
        """Enable row-level security for session."""
        session.execute(text(f"SET app.current_tenant = '{self.tenant_id}'"))

    def _disable_rls(self, session: Session) -> None:
        """Disable row-level security."""
        session.execute(text("RESET app.current_tenant"))


class TenantMiddleware:
    """FastAPI middleware for tenant context."""

    def __init__(self, app, tenant_manager: TenantManager):
        self.app = app
        self.tenant_manager = tenant_manager

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract tenant from request
        tenant_id = self._extract_tenant_id(scope)

        if tenant_id:
            tenant = self.tenant_manager.get_tenant(tenant_id)

            if tenant and tenant.status == TenantStatus.ACTIVE:
                context = TenantContext(
                    tenant_id=tenant_id,
                    tenant=tenant
                )
                set_current_tenant(context)

        try:
            await self.app(scope, receive, send)
        finally:
            clear_current_tenant()

    def _extract_tenant_id(self, scope) -> Optional[str]:
        """Extract tenant ID from request."""
        headers = dict(scope.get("headers", []))

        # Try X-Tenant-ID header
        tenant_header = headers.get(b"x-tenant-id")
        if tenant_header:
            return tenant_header.decode()

        # Try subdomain
        host = headers.get(b"host", b"").decode()
        if host:
            parts = host.split(".")
            if len(parts) >= 3:
                subdomain = parts[0]
                tenant = self.tenant_manager.get_tenant_by_domain(subdomain)
                if tenant:
                    return tenant.tenant_id

        return None


# Decorator for tenant-required endpoints
F = TypeVar("F", bound=Callable[..., Any])


def require_tenant(func: F) -> F:
    """Decorator to require tenant context."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        context = get_current_tenant()
        if not context:
            raise ValueError("Tenant context required")
        return func(*args, **kwargs)
    return wrapper


def require_feature(feature: str):
    """Decorator to require specific feature enabled for tenant."""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            context = get_current_tenant()
            if not context:
                raise ValueError("Tenant context required")

            if feature not in context.tenant.enabled_features:
                raise PermissionError(f"Feature not enabled: {feature}")

            return func(*args, **kwargs)
        return wrapper
    return decorator


# SQL helpers for row-level security
RLS_POLICIES = """
-- Enable RLS on tenant tables
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE loans ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Create policies
CREATE POLICY tenant_isolation_leads ON leads
    USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE POLICY tenant_isolation_loans ON loans
    USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE POLICY tenant_isolation_documents ON documents
    USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE POLICY tenant_isolation_users ON users
    USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
"""
