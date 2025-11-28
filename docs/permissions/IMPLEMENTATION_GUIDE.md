# Stage-Based Permissions Implementation Guide

This guide walks through implementing the stage-based permission system step-by-step.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Database Setup](#database-setup)
3. [Backend Implementation](#backend-implementation)
4. [Frontend Implementation](#frontend-implementation)
5. [Integration Points](#integration-points)
6. [Testing Strategy](#testing-strategy)
7. [Migration from Legacy System](#migration-from-legacy-system)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Dependencies

**Backend:**
```bash
pip install fastapi sqlalchemy pydantic python-jose[cryptography]
```

**Frontend:**
```bash
npm install @tanstack/react-query axios
```

### Environment Variables

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/mortgage_crm

# JWT Configuration
JWT_SECRET=your-secret-key
JWT_ALGORITHM=HS256

# Redis (optional, for caching)
REDIS_URL=redis://localhost:6379
```

---

## Database Setup

### Step 1: Create Base Tables

Run the schema in order:

```sql
-- 1. Subscription tiers (organization-level)
CREATE TABLE subscription_tiers (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    allowed_stages TEXT[] NOT NULL,
    -- ... (see full schema)
);

-- 2. Loan stages
CREATE TABLE loan_stages (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    -- ...
);

-- 3. Permission definitions
CREATE TABLE permission_definitions (
    id SERIAL PRIMARY KEY,
    stage_code VARCHAR(50) REFERENCES loan_stages(code),
    permission_key VARCHAR(100) UNIQUE NOT NULL,
    -- ...
);

-- 4. Templates, user access, overrides, etc.
```

### Step 2: Seed Default Data

```sql
-- Insert loan stages
INSERT INTO loan_stages (code, name, description, icon, color, sort_order) VALUES
('lead', 'Lead Management', 'Lead intake, qualification, and nurturing', '👥', '#3B82F6', 1),
('active_loan', 'Active Loan', 'Loan processing through closing', '📄', '#10B981', 2),
('portfolio', 'Portfolio', 'Post-closing client management', '💼', '#8B5CF6', 3);

-- Insert subscription tiers
INSERT INTO subscription_tiers (code, name, allowed_stages, monthly_price) VALUES
('starter', 'Starter', ARRAY['lead'], 99),
('professional', 'Professional', ARRAY['lead', 'active_loan'], 199),
('enterprise', 'Enterprise', ARRAY['lead', 'active_loan', 'portfolio'], 399);
```

### Step 3: Create Helper Functions

```sql
-- Check if user has stage access
CREATE OR REPLACE FUNCTION user_has_stage_access(
    p_user_id INTEGER,
    p_stage_code VARCHAR(50)
) RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM user_stage_access usa
        JOIN users u ON usa.user_id = u.id
        JOIN organization_subscriptions os ON u.organization_id = os.organization_id
        WHERE usa.user_id = p_user_id
          AND usa.stage_code = p_stage_code
          AND usa.is_active = true
          AND p_stage_code = ANY(
              SELECT allowed_stages FROM subscription_tiers
              WHERE id = os.tier_id
          )
    );
END;
$$ LANGUAGE plpgsql;

-- Check if user has specific permission
CREATE OR REPLACE FUNCTION user_has_permission(
    p_user_id INTEGER,
    p_permission_key VARCHAR(100)
) RETURNS BOOLEAN AS $$
DECLARE
    v_stage_code VARCHAR(50);
    v_has_override BOOLEAN;
    v_override_granted BOOLEAN;
    v_template_permissions JSONB;
BEGIN
    -- Extract stage from permission key
    v_stage_code := split_part(p_permission_key, '.', 1);

    -- Check stage access first
    IF NOT user_has_stage_access(p_user_id, v_stage_code) THEN
        RETURN FALSE;
    END IF;

    -- Check for override
    SELECT is_granted INTO v_override_granted
    FROM user_permission_overrides
    WHERE user_id = p_user_id
      AND permission_key = p_permission_key
      AND is_active = true
      AND (expires_at IS NULL OR expires_at > NOW());

    IF FOUND THEN
        RETURN v_override_granted;
    END IF;

    -- Check template permissions
    SELECT spt.permissions INTO v_template_permissions
    FROM user_stage_access usa
    JOIN stage_permission_templates spt ON usa.template_id = spt.id
    WHERE usa.user_id = p_user_id AND usa.stage_code = v_stage_code;

    RETURN COALESCE((v_template_permissions->>p_permission_key)::boolean, FALSE);
END;
$$ LANGUAGE plpgsql;
```

---

## Backend Implementation

### Step 1: Create Pydantic Models

```python
# models/permissions.py

from pydantic import BaseModel
from typing import Optional, List, Dict
from enum import Enum
from datetime import datetime

class DataScope(str, Enum):
    ALL = "all"
    TEAM = "team"
    TERRITORY = "territory"
    BRANCH = "branch"
    ASSIGNED = "assigned"
    NONE = "none"

class LoanStageResponse(BaseModel):
    code: str
    name: str
    description: str
    icon: str
    color: str

    class Config:
        from_attributes = True

class PermissionTemplateResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str
    stage_code: str
    role_type: str
    permissions: Dict[str, bool]
    default_scope: DataScope
    tags: List[str]
    is_system_default: bool

class UserStageAccessCreate(BaseModel):
    user_id: int
    stage_code: str
    template_id: int
    data_scope: DataScope = DataScope.ASSIGNED
    custom_permissions: Optional[Dict[str, bool]] = None

class PermissionCheckRequest(BaseModel):
    user_id: int
    permission_key: str

class PermissionCheckResponse(BaseModel):
    has_permission: bool
    source: str  # 'template', 'override', 'denied'
    expires_at: Optional[datetime] = None
```

### Step 2: Create Database Session

```python
# database/session.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
import os

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Step 3: Implement API Routes

```python
# routers/permissions_routes.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from database.session import get_db
from models.permissions import *

router = APIRouter(prefix="/api/v1/permissions", tags=["Permissions"])

# ============================================================================
# LOAN STAGES
# ============================================================================

@router.get("/stages", response_model=List[LoanStageResponse])
async def get_loan_stages(db: Session = Depends(get_db)):
    """Get all loan stages."""
    result = db.execute("""
        SELECT code, name, description, icon, color, sort_order
        FROM loan_stages
        WHERE is_active = true
        ORDER BY sort_order
    """)
    return result.fetchall()

@router.get("/stages/{stage_code}/available")
async def check_stage_availability(
    stage_code: str,
    user_id: int,
    db: Session = Depends(get_db)
):
    """Check if user has access to a specific stage."""
    result = db.execute(
        "SELECT user_has_stage_access(:user_id, :stage_code)",
        {"user_id": user_id, "stage_code": stage_code}
    )
    has_access = result.scalar()
    return {"stage_code": stage_code, "has_access": has_access}

# ============================================================================
# PERMISSION TEMPLATES
# ============================================================================

@router.get("/templates", response_model=List[PermissionTemplateResponse])
async def get_templates(
    stage_code: Optional[str] = None,
    role_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get permission templates with optional filtering."""
    query = """
        SELECT id, code, name, description, stage_code, role_type,
               permissions, default_scope, tags, is_system_default
        FROM stage_permission_templates
        WHERE is_active = true
    """
    params = {}

    if stage_code:
        query += " AND stage_code = :stage_code"
        params["stage_code"] = stage_code

    if role_type:
        query += " AND role_type = :role_type"
        params["role_type"] = role_type

    query += " ORDER BY stage_code, sort_order"

    result = db.execute(query, params)
    return result.fetchall()

# ============================================================================
# USER PERMISSIONS
# ============================================================================

@router.post("/users/stage-access")
async def grant_stage_access(
    access: UserStageAccessCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Grant a user access to a loan stage with a permission template."""
    # Verify admin permission
    if not user_has_permission(current_user.id, "system.users.manage_permissions"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Check if access already exists
    existing = db.execute("""
        SELECT id FROM user_stage_access
        WHERE user_id = :user_id AND stage_code = :stage_code
    """, {"user_id": access.user_id, "stage_code": access.stage_code}).fetchone()

    if existing:
        # Update existing
        db.execute("""
            UPDATE user_stage_access
            SET template_id = :template_id,
                data_scope = :data_scope,
                custom_permissions = :custom_permissions,
                updated_at = NOW(),
                updated_by = :updated_by
            WHERE user_id = :user_id AND stage_code = :stage_code
        """, {
            **access.dict(),
            "updated_by": current_user.id
        })
    else:
        # Create new
        db.execute("""
            INSERT INTO user_stage_access
            (user_id, stage_code, template_id, data_scope, custom_permissions, granted_by)
            VALUES (:user_id, :stage_code, :template_id, :data_scope, :custom_permissions, :granted_by)
        """, {
            **access.dict(),
            "granted_by": current_user.id
        })

    db.commit()

    # Log the action
    log_permission_change(db, access.user_id, "stage_access_granted", {
        "stage_code": access.stage_code,
        "template_id": access.template_id
    }, current_user.id)

    return {"success": True, "message": "Stage access granted"}

@router.post("/check", response_model=PermissionCheckResponse)
async def check_permission(
    request: PermissionCheckRequest,
    db: Session = Depends(get_db)
):
    """Check if a user has a specific permission."""
    # Check override first
    override = db.execute("""
        SELECT is_granted, expires_at
        FROM user_permission_overrides
        WHERE user_id = :user_id
          AND permission_key = :permission_key
          AND is_active = true
          AND (expires_at IS NULL OR expires_at > NOW())
    """, request.dict()).fetchone()

    if override:
        return PermissionCheckResponse(
            has_permission=override.is_granted,
            source="override",
            expires_at=override.expires_at
        )

    # Check template permission
    has_perm = db.execute(
        "SELECT user_has_permission(:user_id, :permission_key)",
        request.dict()
    ).scalar()

    return PermissionCheckResponse(
        has_permission=has_perm,
        source="template" if has_perm else "denied"
    )

# ============================================================================
# BULK OPERATIONS
# ============================================================================

@router.post("/users/{user_id}/bulk-setup")
async def bulk_setup_permissions(
    user_id: int,
    stages: List[UserStageAccessCreate],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Set up all stage permissions for a user at once."""
    # Verify admin permission
    if not user_has_permission(current_user.id, "system.users.manage_permissions"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Clear existing access
    db.execute(
        "DELETE FROM user_stage_access WHERE user_id = :user_id",
        {"user_id": user_id}
    )

    # Insert new access
    for stage_access in stages:
        db.execute("""
            INSERT INTO user_stage_access
            (user_id, stage_code, template_id, data_scope, custom_permissions, granted_by)
            VALUES (:user_id, :stage_code, :template_id, :data_scope, :custom_permissions, :granted_by)
        """, {
            **stage_access.dict(),
            "user_id": user_id,
            "granted_by": current_user.id
        })

    db.commit()

    return {"success": True, "stages_configured": len(stages)}
```

### Step 4: Create Permission Decorator

```python
# auth/permissions.py

from functools import wraps
from fastapi import HTTPException, status
from typing import List, Union

def require_permission(permission_key: Union[str, List[str]]):
    """Decorator to require specific permission(s) for an endpoint."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get current user from kwargs or request
            current_user = kwargs.get('current_user')
            db = kwargs.get('db')

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )

            # Handle single permission or list
            permissions = [permission_key] if isinstance(permission_key, str) else permission_key

            # Check if user has any of the required permissions
            for perm in permissions:
                result = db.execute(
                    "SELECT user_has_permission(:user_id, :permission_key)",
                    {"user_id": current_user.id, "permission_key": perm}
                )
                if result.scalar():
                    return await func(*args, **kwargs)

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required permission: {permission_key}"
            )

        return wrapper
    return decorator

# Usage example:
@router.get("/leads")
@require_permission("lead.intake.view_all")
async def get_leads(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    # ... implementation
    pass
```

---

## Frontend Implementation

### Step 1: Create Permission Context

```typescript
// contexts/PermissionContext.tsx

import React, { createContext, useContext, useEffect, useState } from 'react';
import { permissionsService, UserPermissionProfile } from '../services/permissionsService';

interface PermissionContextValue {
  profile: UserPermissionProfile | null;
  loading: boolean;
  hasPermission: (key: string) => boolean;
  hasStageAccess: (stageCode: string) => boolean;
  refreshPermissions: () => Promise<void>;
}

const PermissionContext = createContext<PermissionContextValue | undefined>(undefined);

export const PermissionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [profile, setProfile] = useState<UserPermissionProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const loadPermissions = async () => {
    try {
      setLoading(true);
      const data = await permissionsService.getUserPermissions();
      setProfile(data);
    } catch (error) {
      console.error('Failed to load permissions:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPermissions();
  }, []);

  const hasPermission = (key: string): boolean => {
    if (!profile) return false;

    // Check effective permissions
    return profile.effectivePermissions[key] === true;
  };

  const hasStageAccess = (stageCode: string): boolean => {
    if (!profile) return false;

    return profile.stages.some(
      s => s.stageCode === stageCode && s.isActive
    );
  };

  return (
    <PermissionContext.Provider value={{
      profile,
      loading,
      hasPermission,
      hasStageAccess,
      refreshPermissions: loadPermissions
    }}>
      {children}
    </PermissionContext.Provider>
  );
};

export const usePermissions = () => {
  const context = useContext(PermissionContext);
  if (!context) {
    throw new Error('usePermissions must be used within PermissionProvider');
  }
  return context;
};
```

### Step 2: Create Permission Components

```typescript
// components/PermissionGate.tsx

import React from 'react';
import { usePermissions } from '../contexts/PermissionContext';

interface PermissionGateProps {
  permission?: string;
  permissions?: string[];
  stage?: string;
  requireAll?: boolean;
  fallback?: React.ReactNode;
  children: React.ReactNode;
}

export const PermissionGate: React.FC<PermissionGateProps> = ({
  permission,
  permissions = [],
  stage,
  requireAll = false,
  fallback = null,
  children
}) => {
  const { hasPermission, hasStageAccess, loading } = usePermissions();

  if (loading) {
    return null; // Or loading indicator
  }

  // Check stage access if specified
  if (stage && !hasStageAccess(stage)) {
    return <>{fallback}</>;
  }

  // Build permission list
  const allPermissions = permission
    ? [permission, ...permissions]
    : permissions;

  if (allPermissions.length === 0) {
    return <>{children}</>;
  }

  // Check permissions
  const hasAccess = requireAll
    ? allPermissions.every(p => hasPermission(p))
    : allPermissions.some(p => hasPermission(p));

  return hasAccess ? <>{children}</> : <>{fallback}</>;
};

// Usage examples:

// Single permission
<PermissionGate permission="lead.intake.create">
  <CreateLeadButton />
</PermissionGate>

// Multiple permissions (any)
<PermissionGate permissions={["lead.intake.edit", "lead.intake.create"]}>
  <LeadForm />
</PermissionGate>

// Multiple permissions (all required)
<PermissionGate
  permissions={["loan.processing.view", "loan.processing.edit"]}
  requireAll
>
  <ProcessingDashboard />
</PermissionGate>

// Stage access only
<PermissionGate stage="portfolio">
  <PortfolioNavItem />
</PermissionGate>

// With fallback
<PermissionGate
  permission="admin.users.manage"
  fallback={<AccessDeniedMessage />}
>
  <AdminPanel />
</PermissionGate>
```

### Step 3: Create Permission Hooks

```typescript
// hooks/usePermissionCheck.ts

import { useCallback } from 'react';
import { usePermissions } from '../contexts/PermissionContext';

export const usePermissionCheck = () => {
  const { hasPermission, hasStageAccess, profile } = usePermissions();

  const can = useCallback((permission: string) => {
    return hasPermission(permission);
  }, [hasPermission]);

  const canAny = useCallback((permissions: string[]) => {
    return permissions.some(p => hasPermission(p));
  }, [hasPermission]);

  const canAll = useCallback((permissions: string[]) => {
    return permissions.every(p => hasPermission(p));
  }, [hasPermission]);

  const getDataScope = useCallback((stageCode: string) => {
    const stageAccess = profile?.stages.find(s => s.stageCode === stageCode);
    return stageAccess?.dataScope || 'none';
  }, [profile]);

  return {
    can,
    canAny,
    canAll,
    hasStageAccess,
    getDataScope,
    isAdmin: profile?.stages.some(s => s.templateCode?.includes('admin')) ?? false
  };
};

// Usage:
const { can, canAny, hasStageAccess, getDataScope } = usePermissionCheck();

if (can('lead.intake.delete')) {
  // Show delete button
}

if (canAny(['loan.processing.edit', 'loan.processing.create'])) {
  // Show edit/create UI
}

const scope = getDataScope('lead');
// scope: 'all' | 'team' | 'assigned' etc.
```

### Step 4: Integrate with React Router

```typescript
// components/ProtectedRoute.tsx

import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';

interface ProtectedRouteProps {
  permission?: string;
  stage?: string;
  children: React.ReactNode;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  permission,
  stage,
  children
}) => {
  const { hasPermission, hasStageAccess, loading } = usePermissions();
  const location = useLocation();

  if (loading) {
    return <LoadingSpinner />;
  }

  // Check stage access
  if (stage && !hasStageAccess(stage)) {
    return <Navigate to="/access-denied" state={{ from: location }} replace />;
  }

  // Check permission
  if (permission && !hasPermission(permission)) {
    return <Navigate to="/access-denied" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};

// Usage in router:
<Route
  path="/leads"
  element={
    <ProtectedRoute stage="lead" permission="lead.intake.view_all">
      <LeadsPage />
    </ProtectedRoute>
  }
/>
```

---

## Integration Points

### 1. Navigation Menu Filtering

```typescript
// components/Navigation.tsx

const Navigation: React.FC = () => {
  const { hasStageAccess, hasPermission } = usePermissions();

  const menuItems = [
    {
      label: 'Leads',
      path: '/leads',
      stage: 'lead',
      permission: 'lead.intake.view_all',
      icon: '👥'
    },
    {
      label: 'Active Loans',
      path: '/loans',
      stage: 'active_loan',
      permission: 'loan.processing.view_pipeline',
      icon: '📄'
    },
    {
      label: 'Portfolio',
      path: '/portfolio',
      stage: 'portfolio',
      permission: 'portfolio.clients.view_all',
      icon: '💼'
    }
  ];

  const filteredItems = menuItems.filter(item =>
    hasStageAccess(item.stage) && hasPermission(item.permission)
  );

  return (
    <nav>
      {filteredItems.map(item => (
        <NavLink key={item.path} to={item.path}>
          <span>{item.icon}</span>
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
};
```

### 2. API Request Interceptor

```typescript
// services/api.ts

import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1'
});

// Add permission context to requests
api.interceptors.request.use((config) => {
  // Get current stage context from URL or state
  const stageContext = getCurrentStageContext();

  if (stageContext) {
    config.headers['X-Stage-Context'] = stageContext;
  }

  return config;
});

// Handle permission errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 403) {
      // Redirect to access denied or show modal
      const permissionRequired = error.response.headers['x-required-permission'];

      if (permissionRequired) {
        // Show permission request modal
        showPermissionRequestModal(permissionRequired);
      }
    }
    return Promise.reject(error);
  }
);
```

### 3. Data Scoping in Queries

```typescript
// hooks/useLeads.ts

import { useQuery } from '@tanstack/react-query';
import { usePermissionCheck } from './usePermissionCheck';

export const useLeads = () => {
  const { getDataScope } = usePermissionCheck();
  const scope = getDataScope('lead');

  return useQuery(['leads', scope], async () => {
    const response = await api.get('/leads', {
      params: {
        scope: scope,
        // Backend will filter based on scope
      }
    });
    return response.data;
  });
};
```

---

## Testing Strategy

### Unit Tests

```typescript
// __tests__/permissions.test.ts

import { render, screen } from '@testing-library/react';
import { PermissionGate } from '../components/PermissionGate';
import { PermissionProvider } from '../contexts/PermissionContext';

// Mock permission profile
const mockProfile = {
  userId: 1,
  stages: [
    { stageCode: 'lead', isActive: true, templateCode: 'lead_officer' }
  ],
  effectivePermissions: {
    'lead.intake.view_all': true,
    'lead.intake.create': true,
    'lead.intake.edit': false
  }
};

describe('PermissionGate', () => {
  it('renders children when permission is granted', () => {
    render(
      <PermissionProvider initialProfile={mockProfile}>
        <PermissionGate permission="lead.intake.view_all">
          <div data-testid="protected-content">Content</div>
        </PermissionGate>
      </PermissionProvider>
    );

    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
  });

  it('renders fallback when permission is denied', () => {
    render(
      <PermissionProvider initialProfile={mockProfile}>
        <PermissionGate
          permission="lead.intake.edit"
          fallback={<div data-testid="fallback">Access Denied</div>}
        >
          <div data-testid="protected-content">Content</div>
        </PermissionGate>
      </PermissionProvider>
    );

    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
    expect(screen.getByTestId('fallback')).toBeInTheDocument();
  });
});
```

### Integration Tests

```python
# tests/test_permissions_api.py

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

@pytest.fixture
def admin_user():
    # Create admin user with all permissions
    pass

@pytest.fixture
def standard_user():
    # Create standard user with limited permissions
    pass

def test_stage_access_check(standard_user):
    response = client.get(
        f"/api/v1/permissions/stages/lead/available?user_id={standard_user.id}",
        headers={"Authorization": f"Bearer {standard_user.token}"}
    )
    assert response.status_code == 200
    assert response.json()["has_access"] == True

def test_permission_check(standard_user):
    response = client.post(
        "/api/v1/permissions/check",
        json={
            "user_id": standard_user.id,
            "permission_key": "lead.intake.view_all"
        },
        headers={"Authorization": f"Bearer {standard_user.token}"}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["has_permission"] == True
    assert result["source"] == "template"

def test_unauthorized_stage_access(standard_user):
    # User doesn't have portfolio access
    response = client.get(
        f"/api/v1/permissions/stages/portfolio/available?user_id={standard_user.id}",
        headers={"Authorization": f"Bearer {standard_user.token}"}
    )
    assert response.status_code == 200
    assert response.json()["has_access"] == False
```

---

## Migration from Legacy System

### Step 1: Audit Existing Permissions

```python
# scripts/audit_permissions.py

def audit_existing_permissions():
    """Map existing roles to new stage-based system."""

    legacy_roles = db.query("SELECT * FROM user_roles")

    mapping = {
        'Management': {
            'stages': ['lead', 'active_loan', 'portfolio'],
            'template_per_stage': {
                'lead': 'lead_admin',
                'active_loan': 'loan_admin',
                'portfolio': 'portfolio_admin'
            }
        },
        'Sales': {
            'stages': ['lead', 'active_loan'],
            'template_per_stage': {
                'lead': 'lead_officer',
                'active_loan': 'loan_officer'
            }
        },
        'Operations': {
            'stages': ['active_loan'],
            'template_per_stage': {
                'active_loan': 'loan_processor'
            }
        }
    }

    for user_role in legacy_roles:
        new_config = mapping.get(user_role.role_name, {})
        print(f"User {user_role.user_id}: {user_role.role_name} -> {new_config}")

    return mapping
```

### Step 2: Data Migration Script

```python
# scripts/migrate_permissions.py

def migrate_to_stage_based():
    """Migrate users from legacy roles to stage-based permissions."""

    # 1. Create default organization subscription
    db.execute("""
        INSERT INTO organization_subscriptions (organization_id, tier_id, status)
        SELECT id,
               (SELECT id FROM subscription_tiers WHERE code = 'enterprise'),
               'active'
        FROM organizations
        ON CONFLICT DO NOTHING
    """)

    # 2. Map existing users
    legacy_users = db.query("""
        SELECT u.id, u.organization_id, ur.role_name
        FROM users u
        JOIN user_roles ur ON u.id = ur.user_id
    """)

    for user in legacy_users:
        stages_config = ROLE_MAPPING.get(user.role_name, {})

        for stage_code, template_code in stages_config.get('template_per_stage', {}).items():
            template = db.query(
                "SELECT id FROM stage_permission_templates WHERE code = :code",
                {"code": template_code}
            ).fetchone()

            db.execute("""
                INSERT INTO user_stage_access
                (user_id, stage_code, template_id, granted_by)
                VALUES (:user_id, :stage_code, :template_id, 1)
            """, {
                "user_id": user.id,
                "stage_code": stage_code,
                "template_id": template.id
            })

    db.commit()
    print(f"Migrated {len(legacy_users)} users")
```

### Step 3: Verification

```python
# scripts/verify_migration.py

def verify_migration():
    """Verify all users have been properly migrated."""

    # Check all users have stage access
    orphaned = db.query("""
        SELECT u.id, u.email
        FROM users u
        WHERE NOT EXISTS (
            SELECT 1 FROM user_stage_access usa WHERE usa.user_id = u.id
        )
    """)

    if orphaned:
        print(f"WARNING: {len(orphaned)} users without stage access")
        for user in orphaned:
            print(f"  - {user.email}")

    # Verify permission resolution works
    sample_users = db.query("SELECT id FROM users LIMIT 10")

    for user in sample_users:
        # Test a permission from each stage
        tests = [
            ('lead', 'lead.intake.view_all'),
            ('active_loan', 'loan.processing.view_pipeline'),
            ('portfolio', 'portfolio.clients.view_all')
        ]

        for stage, perm in tests:
            has_stage = db.execute(
                "SELECT user_has_stage_access(:uid, :stage)",
                {"uid": user.id, "stage": stage}
            ).scalar()

            has_perm = db.execute(
                "SELECT user_has_permission(:uid, :perm)",
                {"uid": user.id, "perm": perm}
            ).scalar()

            print(f"User {user.id}: {stage}={has_stage}, {perm}={has_perm}")
```

---

## Troubleshooting

### Common Issues

#### 1. Permission Denied When It Should Be Granted

```sql
-- Debug query to trace permission resolution
SELECT
    u.id as user_id,
    u.email,
    os.tier_id,
    st.allowed_stages,
    usa.stage_code,
    usa.template_id,
    spt.code as template_code,
    spt.permissions
FROM users u
LEFT JOIN organization_subscriptions os ON u.organization_id = os.organization_id
LEFT JOIN subscription_tiers st ON os.tier_id = st.id
LEFT JOIN user_stage_access usa ON u.id = usa.user_id
LEFT JOIN stage_permission_templates spt ON usa.template_id = spt.id
WHERE u.id = :user_id;
```

#### 2. Override Not Taking Effect

```sql
-- Check override status
SELECT *
FROM user_permission_overrides
WHERE user_id = :user_id
  AND permission_key = :permission_key
ORDER BY created_at DESC;

-- Verify override hasn't expired
SELECT
    *,
    CASE
        WHEN expires_at IS NULL THEN 'No expiry'
        WHEN expires_at > NOW() THEN 'Active'
        ELSE 'Expired'
    END as status
FROM user_permission_overrides
WHERE user_id = :user_id;
```

#### 3. Cache Invalidation

```typescript
// Force refresh permissions after changes
const { refreshPermissions } = usePermissions();

const handlePermissionChange = async () => {
  await updateUserPermissions(userId, newPermissions);
  await refreshPermissions(); // Reload from server
};
```

#### 4. Stage Access vs Permission Mismatch

```python
# Backend debug endpoint
@router.get("/debug/user/{user_id}/permissions")
async def debug_user_permissions(user_id: int, db: Session = Depends(get_db)):
    """Debug endpoint to view full permission resolution."""

    stages = db.execute("""
        SELECT usa.*, spt.permissions, spt.code as template_code
        FROM user_stage_access usa
        JOIN stage_permission_templates spt ON usa.template_id = spt.id
        WHERE usa.user_id = :user_id
    """, {"user_id": user_id}).fetchall()

    overrides = db.execute("""
        SELECT * FROM user_permission_overrides
        WHERE user_id = :user_id AND is_active = true
    """, {"user_id": user_id}).fetchall()

    return {
        "stages": [dict(s) for s in stages],
        "overrides": [dict(o) for o in overrides]
    }
```

---

## Next Steps

1. **Phase 1**: Deploy database schema and seed data
2. **Phase 2**: Implement backend API routes
3. **Phase 3**: Create frontend permission context and components
4. **Phase 4**: Integrate with existing navigation and routes
5. **Phase 5**: Migrate existing users
6. **Phase 6**: Add permission request workflow
7. **Phase 7**: Implement audit logging dashboard

For questions or issues, refer to the [Architecture Diagram](./ARCHITECTURE_DIAGRAM.md) or contact the development team.
