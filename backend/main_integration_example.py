"""
Main.py Integration Example - Multi-Tenant Database System

This file shows how to integrate the multi-tenant database system into your main.py.
Copy the relevant sections into your actual main.py file.
"""

import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Your existing imports
from database import SessionLocal, engine, Base
from config import settings

# NEW IMPORTS FOR MULTI-TENANT SYSTEM
from tenant_database_manager import TenantDatabaseManager
from services.tenant_provisioning_service import TenantProvisioningService
from middleware.tenant_middleware import TenantMiddleware
from user_onboarding_tenant_integration import integrate_tenant_provisioning_with_onboarding
from routes import tenant_routes

logger = logging.getLogger(__name__)


# =============================================================================
# STEP 1: Initialize Multi-Tenant Components at Startup
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan management - setup and teardown.
    """
    logger.info("🚀 Starting application...")
    
    # CREATE TABLES (your existing code)
    Base.metadata.create_all(bind=engine)
    
    # --- NEW: Initialize Multi-Tenant System ---
    logger.info("🏢 Initializing multi-tenant database system...")
    
    # Initialize tenant database manager
    app.state.tenant_db_manager = TenantDatabaseManager(
        master_db_url=settings.DATABASE_URL
    )
    
    # Initialize tenant provisioning service
    app.state.tenant_provisioning_service = TenantProvisioningService(
        app.state.tenant_db_manager
    )
    
    # Integrate with user onboarding system
    # Note: You'll need to pass your User model and onboarding models here
    from user_onboarding_integration import create_user_onboarding_models
    from models import User  # Your user model
    
    onboarding_models = create_user_onboarding_models(Base)
    onboarding_models['User'] = User  # Add User model to the collection
    
    app.state.tenant_helpers = integrate_tenant_provisioning_with_onboarding(
        db_manager=app.state.tenant_db_manager,
        provisioning_service=app.state.tenant_provisioning_service,
        onboarding_models=onboarding_models
    )
    
    logger.info("✅ Multi-tenant system initialized successfully")
    
    yield
    
    # Cleanup on shutdown
    logger.info("🛑 Shutting down application...")


# =============================================================================
# STEP 2: Create FastAPI App with Lifespan
# =============================================================================

app = FastAPI(
    title="Mortgage CRM - Multi-Tenant",
    description="AI-powered mortgage CRM with database-per-tenant isolation",
    version="2.0.0",
    lifespan=lifespan  # Use the lifespan context manager
)


# =============================================================================
# STEP 3: Add Tenant Middleware (IMPORTANT - Add this EARLY)
# =============================================================================

# Add tenant middleware BEFORE other middlewares
app.add_middleware(
    TenantMiddleware,
    tenant_db_manager=None  # Will be set from app.state at runtime
)

# Your existing CORS middleware — NEVER use wildcard origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.perenniaai.com",
        "https://api.perenniaai.com",
        "https://www.perenniaai.com",
        "http://localhost:3000",  # dev only
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
)


# =============================================================================
# STEP 4: Include Tenant Management Routes
# =============================================================================

# Include tenant admin routes
app.include_router(
    tenant_routes.router,
    prefix="/api/v1",
    tags=["Multi-Tenant Management"]
)

# Your existing routes
# app.include_router(user_routes.router)
# app.include_router(loan_routes.router)
# etc...


# =============================================================================
# STEP 5: Modify User Onboarding Endpoint (Example)
# =============================================================================

"""
In your user_onboarding_integration.py, modify the create_user_unified endpoint:

@router.post("/create")
async def create_user_unified(
    data: UnifiedCreateUserRequest,
    request: Request,
    db = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # ... existing user creation code ...
    
    # Create user
    new_user = User(...)
    db.add(new_user)
    db.flush()
    
    # Create profile
    profile = UserProfile(...)
    db.add(profile)
    db.flush()
    
    # --- NEW: CREATE TENANT DATABASE ---
    if hasattr(request.app.state, 'tenant_helpers'):
        tenant_helpers = request.app.state.tenant_helpers
        
        # Determine organization name (can be from request data or user name)
        org_name = getattr(data, 'organization_name', None) or f"{data.first_name} {data.last_name}"
        subdomain = getattr(data, 'subdomain', None)
        
        # Create tenant database
        tenant_info = tenant_helpers['create_tenant_for_onboarding_user'](
            db=db,
            user_profile=profile,
            organization_name=org_name,
            subdomain=subdomain
        )
        
        if tenant_info:
            # Store tenant_id in profile
            profile.tenant_id = tenant_info['tenant_id']
            new_user.tenant_id = tenant_info['tenant_id']
            db.commit()
            
            # Add tenant info to response
            response_data['tenant'] = {
                'tenant_id': tenant_info['tenant_id'],
                'database_name': tenant_info['database_name'],
                'subdomain': tenant_info['subdomain'],
                'status': tenant_info['status']
            }
            
            logger.info(f"✅ Created tenant database for user {new_user.id}")
        else:
            logger.warning(f"⚠️  Failed to create tenant database for user {new_user.id}")
    
    return response_data
"""


# =============================================================================
# STEP 6: Health Check Endpoint with Tenant Info
# =============================================================================

@app.get("/health")
async def health_check(request: Request):
    """Health check endpoint with multi-tenant system status."""
    
    health_status = {
        "status": "healthy",
        "database": "connected",
        "multi_tenant_system": "initialized" if hasattr(request.app.state, 'tenant_db_manager') else "not_initialized"
    }
    
    # Check tenant system health
    if hasattr(request.app.state, 'tenant_db_manager'):
        try:
            tenant_db_manager = request.app.state.tenant_db_manager
            with tenant_db_manager.master_db_session() as session:
                # Query tenant count
                from models.tenant import Tenant
                tenant_count = session.query(Tenant).count()
                health_status["tenant_count"] = tenant_count
                health_status["tenant_system_status"] = "operational"
        except Exception as e:
            health_status["tenant_system_status"] = f"error: {str(e)}"
    
    return health_status


# =============================================================================
# STEP 7: Environment Variables Configuration
# =============================================================================

"""
Add these to your .env file:

# Multi-Tenant Database Configuration
MASTER_DATABASE_URL=postgresql://user:password@host:port/master_db
TENANT_DB_PREFIX=tenant_
MAX_TENANT_CONNECTIONS=10
TENANT_POOL_SIZE=5
TENANT_MAX_OVERFLOW=10

# Tenant Creation Settings
AUTO_CREATE_TENANT_ON_SIGNUP=true
TENANT_DB_SCHEMA_VERSION=1.0.0
"""


# =============================================================================
# STEP 8: Running Migrations
# =============================================================================

"""
To set up the multi-tenant system:

1. Run the tenant_id migration:
   python -m migrations.add_tenant_id_to_user_profile

2. Create tenant database for Tim Loss:
   python backend/setup_tim_loss_tenant.py

3. Verify tenant creation:
   psql -d your_master_db -c "SELECT * FROM tenants;"

4. Test tenant database connection:
   psql -d tenant_timloss_cmg -c "SELECT NOW();"
"""


if __name__ == "__main__":
    import uvicorn
    
    logger.info("🎉 Starting Mortgage CRM with Multi-Tenant Support...")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
