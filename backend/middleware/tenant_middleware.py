"""
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
DEPRECATED — DO NOT USE IN NEW CODE  [Deprecated 2026-05-14]
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

Tenant Middleware — Multi-Database Routing by Subdomain/Header/JWT

STATUS: UNUSED.  This module is NOT registered in main.py.  It is only
imported by main_integration_example.py (an example file, not production code).

This was designed for a multi-database-per-tenant architecture that was never
adopted.  The actual tenant isolation system uses:

  - middleware/tenant_context_middleware.py (TenantContextMiddleware)
      Registered in main.py.  Sets request.state.user, request.state.tenant_context,
      and request.state.organization_id from JWT tokens.  This is the ACTIVE
      tenant context middleware.

  - middleware/tenant_filter.py
      Query helpers (require_tenant_filter, verify_entity_tenant, TenantMixin)
      for enforcing organization_id isolation at the query level.  Used by
      routes and tests.

  - services/tenant_isolation.py (TenantContext dataclass)
      The TenantContext used in production — distinct from the TenantContext
      class in THIS file which wraps a per-tenant DB session.

Tenant Middleware Architecture (consolidated 2026-05-14):
    ACTIVE:
    - middleware/tenant_context_middleware.py — JWT-based context setting (middleware)
    - middleware/tenant_filter.py             — query-level isolation helpers
    DEPRECATED:
    - middleware/tenant_middleware.py (THIS FILE) — unused multi-DB routing
"""
import logging
import os
import warnings
from typing import Optional
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone

warnings.warn(
    "middleware.tenant_middleware is deprecated and unused in production. "
    "Active tenant isolation is handled by middleware/tenant_context_middleware.py "
    "(request context) and middleware/tenant_filter.py (query helpers). "
    "The only importer is main_integration_example.py (example file).",
    DeprecationWarning,
    stacklevel=2,
)

from tenant_database_manager import tenant_db_manager
from models.tenant import Tenant

logger = logging.getLogger(__name__)

logger.warning(
    "DEPRECATED: middleware.tenant_middleware imported — this module is not used "
    "in production. Only importer is main_integration_example.py (example file)."
)


class TenantContext:
    """
    Holds the current tenant information for the request.
    """
    def __init__(self, tenant: Tenant, db_session: Session):
        self.tenant = tenant
        self.db_session = db_session
        self.tenant_id = tenant.tenant_id
        self.organization_name = tenant.organization_name
        self.database_name = tenant.database_name
    
    def close(self):
        """Close the database session."""
        if self.db_session:
            self.db_session.close()


async def get_tenant_from_request(request: Request) -> Optional[Tenant]:
    """
    Extract tenant identifier from request.
    Supports multiple methods:
    1. Subdomain (e.g., acme.yourdomain.com)
    2. X-Tenant-ID header
    3. JWT token (if authentication is implemented)
    
    Args:
        request: FastAPI request object
    
    Returns:
        Tenant object or None
    """
    tenant_id = None
    subdomain = None
    
    # Method 1: Extract from subdomain
    host = request.headers.get("host", "")
    if "." in host:
        subdomain = host.split(".")[0]
        # Ignore common subdomains
        if subdomain not in ["www", "api", "localhost"]:
            logger.debug(f"Extracted subdomain: {subdomain}")
    
    # Method 2: Extract from X-Tenant-ID header
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        logger.debug(f"Found tenant ID in header: {tenant_id}")
    
    # Method 3: Extract from JWT token (if you have auth implemented)
    # Uncomment and customize based on your auth implementation
    # try:
    #     from auth import get_current_user
    #     user = await get_current_user(request)
    #     tenant_id = user.get("tenant_id")
    # except Exception as e:
    #     logger.debug(f"Could not extract tenant from token: {e}")
    
    # Method 4: Query parameter (for testing/development only)
    tenant_id_param = request.query_params.get("tenant_id")
    if tenant_id_param:
        _env = os.getenv("RAILWAY_ENVIRONMENT", os.getenv("ENVIRONMENT", "")).lower()
        if _env in ("production", "prod"):
            logger.warning("tenant_id query param rejected in production")
        else:
            tenant_id = tenant_id_param
            logger.debug(f"Found tenant ID in query param: {tenant_id}")
    
    # Look up tenant in master database
    if not tenant_id and not subdomain:
        return None
    
    try:
        with tenant_db_manager.master_db_session() as session:
            query = session.query(Tenant)
            
            if subdomain:
                tenant = query.filter(
                    Tenant.subdomain == subdomain,
                    Tenant.is_active == True
                ).first()
            else:
                tenant = query.filter(
                    Tenant.tenant_id == tenant_id,
                    Tenant.is_active == True
                ).first()
            
            if tenant:
                # Update last accessed time
                tenant.last_accessed = datetime.now(timezone.utc)
                session.commit()
                
                # Detach from session to use in different context
                session.expunge(tenant)
                
                logger.info(f"Found tenant: {tenant.tenant_id} - {tenant.organization_name}")
                return tenant
            
            return None
    
    except Exception as e:
        logger.error(f"Error looking up tenant: {e}")
        return None


async def get_current_tenant(request: Request) -> Tenant:
    """
    Dependency to get the current tenant from the request.
    Raises HTTPException if tenant is not found or invalid.
    
    Usage in FastAPI routes:
        @router.get("/endpoint")
        async def endpoint(tenant: Tenant = Depends(get_current_tenant)):
            ...
    """
    tenant = await get_tenant_from_request(request)
    
    if not tenant:
        logger.warning("Tenant not specified or not found")
        raise HTTPException(
            status_code=400,
            detail="Tenant not specified. Please provide a valid subdomain or X-Tenant-ID header."
        )
    
    if not tenant.is_provisioned:
        logger.warning(f"Tenant {tenant.tenant_id} is not provisioned")
        raise HTTPException(
            status_code=503,
            detail="Tenant database is not provisioned yet. Please contact support."
        )
    
    return tenant


async def get_tenant_db(request: Request) -> Session:
    """
    Dependency to get a database session for the current tenant.
    
    Usage in FastAPI routes:
        @router.get("/leads")
        async def get_leads(db: Session = Depends(get_tenant_db)):
            leads = db.query(Lead).all()
            return leads
    
    The session will be automatically closed after the request.
    """
    tenant = await get_current_tenant(request)
    
    # Get tenant-specific database session
    db_session = tenant_db_manager.get_tenant_session(
        tenant.tenant_id,
        tenant.database_url
    )
    
    try:
        yield db_session
    finally:
        db_session.close()


async def get_tenant_context(request: Request) -> TenantContext:
    """
    Dependency to get both tenant info and database session.
    
    Usage in FastAPI routes:
        @router.get("/dashboard")
        async def dashboard(ctx: TenantContext = Depends(get_tenant_context)):
            # Access tenant info
            org_name = ctx.organization_name
            
            # Access database
            leads = ctx.db_session.query(Lead).all()
            
            return {"org": org_name, "leads": leads}
    """
    tenant = await get_current_tenant(request)
    
    db_session = tenant_db_manager.get_tenant_session(
        tenant.tenant_id,
        tenant.database_url
    )
    
    context = TenantContext(tenant, db_session)
    
    try:
        yield context
    finally:
        context.close()


def require_master_db() -> Session:
    """
    Dependency to get the master database session.
    Use this for operations that need to access the tenant registry.
    
    Usage:
        @router.post("/tenants")
        async def create_tenant(db: Session = Depends(require_master_db)):
            # Access tenant registry
            tenants = db.query(Tenant).all()
            return tenants
    """
    db_session = tenant_db_manager.get_master_session()
    try:
        yield db_session
    finally:
        db_session.close()
