# Multi-Tenant Database Implementation Guide

## Overview

This guide explains how to convert your mortgage CRM from a shared database architecture to a **database-per-tenant** architecture where each organization/user gets their own separate PostgreSQL database.

## Architecture Summary

### Current Architecture (Shared Database)
- Single PostgreSQL database
- All tenants share the same tables
- Data isolation through `organization_id` and `user_id` foreign keys
- Application-level filtering

### New Architecture (Database-Per-Tenant)
- **Master Database**: Stores tenant registry (which tenant uses which database)
- **Tenant Databases**: Each organization gets a separate PostgreSQL database
- Complete data isolation at the database level
- No shared tables between tenants

## Components Implemented

### 1. Tenant Database Manager (`tenant_database_manager.py`)
Manages dynamic database connections for multiple tenant databases.

**Key Features:**
- Creates new PostgreSQL databases for tenants
- Maintains connection pools for each tenant
- Provides session context managers
- Handles tenant database migrations
- Supports database cleanup/deletion

### 2. Tenant Model (`models/tenant.py`)
Stores tenant registry in the master database.

**Key Fields:**
- `tenant_id`: Unique identifier
- `organization_name`: Company name
- `database_name`: PostgreSQL DB name  
- `database_url`: Connection string
- `is_active`, `is_provisioned`: Status flags
- Subscription/plan information

## Implementation Steps

### Step 1: Set Up Environment Variables

Add to your `.env` file:

```bash
# Master database (stores tenant registry)
MASTER_DATABASE_URL=postgresql://user:pass@host:port/master_db

# Database server (for creating new databases)
DATABASE_SERVER_URL=postgresql://user:pass@host:port/postgres

# Or use existing DATABASE_URL as master
DATABASE_URL=postgresql://user:pass@host:port/master_db
```

### Step 2: Create Master Database Tables

Run migrations to create the `tenants` table in your master database:

```python
from database import Base, engine
from models.tenant import Tenant

# Create tenants table
Base.metadata.create_all(bind=engine)
```

### Step 3: Create Middleware for Tenant Routing

Create `middleware/tenant_middleware.py`:

```python
from fastapi import Request, HTTPException
from tenant_database_manager import tenant_db_manager
from models.tenant import Tenant

async def get_current_tenant(request: Request):
    """Extract tenant from request (subdomain, header, or token)."""
    
    # Option 1: From subdomain
    host = request.headers.get("host", "")
    subdomain = host.split(".")[0] if "." in host else None
    
    # Option 2: From header
    tenant_id = request.headers.get("X-Tenant-ID")
    
    # Option 3: From JWT token
    # tenant_id = get_tenant_from_token(request)
    
    if not tenant_id and not subdomain:
        raise HTTPException(status_code=400, detail="Tenant not specified")
    
    # Look up tenant in master database
    with tenant_db_manager.master_db_session() as session:
        query = session.query(Tenant)
        
        if subdomain:
            tenant = query.filter(Tenant.subdomain == subdomain).first()
        else:
            tenant = query.filter(Tenant.tenant_id == tenant_id).first()
        
        if not tenant or not tenant.is_active:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        return tenant

async def get_tenant_db(request: Request):
    """Get database session for current tenant."""
    tenant = await get_current_tenant(request)
    
    # Return tenant database session
    return tenant_db_manager.get_tenant_session(
        tenant.tenant_id,
        tenant.database_url
    )
```

### Step 4: Create Tenant Provisioning Service

Create `services/tenant_provisioning_service.py`:

```python
import uuid
from tenant_database_manager import tenant_db_manager
from models.tenant import Tenant
from datetime import datetime, timezone

class TenantProvisioningService:
    
    def create_tenant(self, organization_name: str, owner_email: str, 
                     subdomain: str = None) -> Tenant:
        """Provision a new tenant with their own database."""
        
        # Generate unique tenant ID
        tenant_id = str(uuid.uuid4())
        
        # Generate database name (PostgreSQL-safe)
        db_name = f"tenant_{tenant_id.replace('-', '_')}"
        
        # Create physical database
        db_url = tenant_db_manager.create_tenant_database(tenant_id, db_name)
        
        # Create tenant record in master database
        with tenant_db_manager.master_db_session() as session:
            tenant = Tenant(
                tenant_id=tenant_id,
                organization_name=organization_name,
                subdomain=subdomain,
                database_name=db_name,
                database_url=db_url,
                owner_email=owner_email,
                is_active=True,
                is_provisioned=False
            )
            session.add(tenant)
            session.commit()
            session.refresh(tenant)
        
        # Run migrations on tenant database
        tenant_db_manager.run_tenant_migrations(tenant_id, db_url)
        
        # Mark as provisioned
        with tenant_db_manager.master_db_session() as session:
            tenant = session.query(Tenant).filter(
                Tenant.tenant_id == tenant_id
            ).first()
            tenant.is_provisioned = True
            tenant.provisioned_at = datetime.now(timezone.utc)
            session.commit()
        
        return tenant
    
    def delete_tenant(self, tenant_id: str):
        """Delete tenant and their database (use with caution!)."""
        
        with tenant_db_manager.master_db_session() as session:
            tenant = session.query(Tenant).filter(
                Tenant.tenant_id == tenant_id
            ).first()
            
            if not tenant:
                raise ValueError(f"Tenant {tenant_id} not found")
            
            # Delete physical database
            tenant_db_manager.delete_tenant_database(
                tenant_id, 
                tenant.database_name
            )
            
            # Soft delete tenant record
            tenant.deleted_at = datetime.now(timezone.utc)
            tenant.is_active = False
            session.commit()

# Global instance
tenant_service = TenantProvisioningService()
```

### Step 5: Update API Routes

Update your FastAPI routes to use tenant-specific databases:

```python
from fastapi import APIRouter, Depends
from middleware.tenant_middleware import get_tenant_db

router = APIRouter()

@router.get("/leads")
async def get_leads(db = Depends(get_tenant_db)):
    """Get leads for current tenant."""
    # db is now the tenant-specific database session
    leads = db.query(Lead).all()
    return leads

@router.post("/leads")
async def create_lead(lead_data: dict, db = Depends(get_tenant_db)):
    """Create lead in tenant database."""
    lead = Lead(**lead_data)
    db.add(lead)
    db.commit()
    return lead
```

### Step 6: Create Tenant Onboarding Endpoint

```python
from services.tenant_provisioning_service import tenant_service

@router.post("/tenants")
async def create_tenant(org_name: str, owner_email: str, subdomain: str):
    """Create a new tenant organization."""
    tenant = tenant_service.create_tenant(
        organization_name=org_name,
        owner_email=owner_email,
        subdomain=subdomain
    )
    return tenant.to_dict()
```

## Migration Strategy

### Option 1: Gradual Migration
1. Keep existing shared database
2. Create new tenants with separate databases
3. Migrate existing tenants one by one
4. Copy data from shared DB to tenant DB

### Option 2: Big Bang Migration
1. Take system offline
2. Create databases for all existing tenants
3. Migrate all data
4. Switch to new architecture

## Security Considerations

1. **Database Credentials**: Each tenant database should use unique credentials
2. **Connection Limits**: Monitor PostgreSQL connection limits (each tenant uses separate connections)
3. **Tenant Isolation**: Ensure middleware properly identifies tenant to prevent cross-tenant data access
4. **Backup Strategy**: Each tenant database needs separate backups

## Performance Considerations

1. **Connection Pooling**: Each tenant has its own connection pool (configured in `TenantDatabaseManager`)
2. **Database Limits**: PostgreSQL has limits on number of databases and connections
3. **Resource Allocation**: Consider resource limits per tenant
4. **Caching**: Implement tenant-aware caching

## Monitoring

Monitor:
- Number of active tenant databases
- Connection pool status per tenant
- Database sizes
- Query performance per tenant

## Next Steps

1. ✅ Implement `TenantDatabaseManager` (Done)
2. ✅ Create `Tenant` model (Done)
3. ⏳ Create tenant middleware
4. ⏳ Create provisioning service
5. ⏳ Update existing routes
6. ⏳ Test with sample tenants
7. ⏳ Plan data migration
8. ⏳ Deploy to production

## Example Usage

```python
# Create a new tenant
from services.tenant_provisioning_service import tenant_service

tenant = tenant_service.create_tenant(
    organization_name="Acme Mortgages",
    owner_email="admin@acme.com",
    subdomain="acme"
)

print(f"Tenant created: {tenant.tenant_id}")
print(f"Database: {tenant.database_name}")
print(f"URL: https://{tenant.subdomain}.yourdomain.com")
```

## Support

For questions or issues, refer to:
- `tenant_database_manager.py` for database operations
- `models/tenant.py` for tenant data structure
- This guide for implementation patterns
