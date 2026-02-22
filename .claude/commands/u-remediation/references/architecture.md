# Architecture Remediation

## Table of Contents
1. [main.py Dependency Graph Breakup](#mainpy)
2. [Monolithic File Splitting](#monoliths)
3. [API Endpoint Consolidation](#api-consolidation)
4. [Migration Tooling](#migrations)

---

<a name="mainpy"></a>
## 1. main.py Dependency Graph Breakup

### Current State
- 157 files import from main.py
- main.py exports auth functions, database access, and utility functions
- Circular import workarounds exist (lazy imports, `_exported_functions` dicts)
- Any change to main.py risks breaking 157 dependent files

### Target Architecture

```
app/
├── main.py              # ONLY FastAPI app creation + router mounting (< 200 lines)
├── core/
│   ├── __init__.py      # Re-exports for backward compat (temporary)
│   ├── database.py      # Engine, SessionLocal, get_db dependency
│   ├── config.py        # Settings, environment variables
│   └── security.py      # Password hashing, token utilities
├── auth/
│   ├── __init__.py
│   ├── dependencies.py  # get_current_user, get_current_active_user
│   ├── router.py        # Auth endpoints
│   └── service.py       # Auth business logic
├── models/
│   ├── __init__.py      # Re-exports all models
│   ├── base.py          # Base model class
│   ├── user.py
│   ├── lead.py
│   ├── loan.py
│   └── ...
├── schemas/
│   ├── __init__.py
│   └── ...              # Pydantic schemas by domain
└── routes/
    └── ...              # Route files import from core/, auth/, models/
```

### Migration Strategy (Zero-Downtime)

The key insight: you can't update 157 files at once without risking everything. Use a **shim pattern** to migrate incrementally.

#### Step 1: Create new modules (Day 1)

```python
# app/core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, pool_size=20, max_overflow=10)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
```

```python
# app/core/security.py
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
```

```python
# app/auth/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.database import get_db
from app.core.security import verify_password
from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db = Depends(get_db)
):
    # Token validation logic
    ...

async def get_current_active_user(current_user = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
```

#### Step 2: Add backward-compatible shims to main.py (Day 1)

```python
# main.py — add at the top, KEEPING all existing exports
# This allows gradual migration without breaking anything

# New canonical locations
from app.core.database import engine, AsyncSessionLocal, get_db, Base
from app.core.security import verify_password, get_password_hash, create_access_token
from app.auth.dependencies import get_current_user, get_current_active_user

# Everything still importable from main.py — but now it's just re-exports
```

#### Step 3: Migrate files in batches (Week 1–2)

Use a script to identify and update imports:

```bash
# Find all files importing specific functions from main
grep -rn "from main import\|from app.main import" --include="*.py" | sort

# For each file, update imports:
# OLD: from main import get_db, get_current_user
# NEW: from app.core.database import get_db
#      from app.auth.dependencies import get_current_user
```

Migrate in order of risk (lowest-traffic files first):
1. Utility/helper files (least imported by others)
2. Service files
3. Route files
4. High-traffic route files (auth, leads, loans, pipeline)

After each batch (10–15 files), run the test suite and deploy.

#### Step 4: Remove shims from main.py (Week 3)

Once all 157 files are migrated, remove the re-exports from main.py. At this point main.py should only contain:
- FastAPI app creation
- Middleware registration
- Router mounting
- Startup/shutdown events

Target: main.py < 200 lines.

### Verification

```bash
# Count remaining main.py imports (should decrease each batch)
grep -rn "from main import\|from app.main import" --include="*.py" | wc -l

# Check for circular imports
python -c "import app.main" 2>&1 | grep "circular"

# Verify no lazy import workarounds remain
grep -rn "_exported_functions\|importlib.import_module" --include="*.py" | wc -l
```

---

<a name="monoliths"></a>
## 2. Monolithic File Splitting

### Current Offenders

| File | Lines | Domain |
|------|-------|--------|
| Settings.js | 6,966 | Frontend |
| ai_command_routes.py | 5,419 | Backend |
| App.jsx | 4,203 | Frontend |
| OnboardingWizard | 3,433 | Frontend |

Plus 24 Python files >2,500 lines and 9 frontend files >3,000 lines.

### Backend Splitting Strategy

#### ai_command_routes.py (5,419 lines)

Split by AI agent domain:

```
routes/ai/
├── __init__.py          # Router aggregation
├── command_router.py    # Main command dispatch (< 200 lines)
├── lead_agent.py        # Lead-related AI commands
├── loan_agent.py        # Loan-related AI commands
├── pipeline_agent.py    # Pipeline AI commands
├── content_agent.py     # Content generation commands
├── compliance_agent.py  # Compliance AI commands
└── utility_agent.py     # Misc utility commands
```

Each file should:
1. Define its own APIRouter with a prefix
2. Contain only the route handlers for its domain
3. Import shared utilities from a common module

```python
# routes/ai/__init__.py
from fastapi import APIRouter
from .lead_agent import router as lead_router
from .loan_agent import router as loan_router
# ... etc

router = APIRouter(prefix="/api/ai")
router.include_router(lead_router, tags=["AI - Leads"])
router.include_router(loan_router, tags=["AI - Loans"])
```

#### General Backend Splitting Rules

1. **Identify natural boundaries**: Each route file should cover one REST resource or domain
2. **Extract shared logic**: Common patterns (pagination, filtering, auth checks) → shared utilities
3. **One router per file**: No file should define more than one APIRouter
4. **Max 500 lines per route file**: If it's longer, the domain needs further splitting

### Frontend Splitting Strategy

#### Settings.js (6,966 lines)

Split into feature-based tabs/sections:

```
components/settings/
├── index.jsx              # Tab container + routing (< 100 lines)
├── ProfileSettings.jsx    # User profile
├── CompanySettings.jsx    # Company/brokerage config
├── IntegrationSettings.jsx # Third-party integrations
├── NotificationSettings.jsx # Email/SMS preferences
├── BillingSettings.jsx    # Subscription & billing
├── SecuritySettings.jsx   # Password, 2FA, sessions
├── AISettings.jsx         # Agent preferences
└── hooks/
    └── useSettings.js     # Shared settings state/API calls
```

#### App.jsx (4,203 lines)

```
app/
├── App.jsx                # Top-level providers + <RouterProvider> (< 100 lines)
├── AppProviders.jsx       # Auth, Theme, Query providers
├── AppRoutes.jsx          # Route definitions (lazy imports)
├── layouts/
│   ├── MainLayout.jsx     # Sidebar + header + content area
│   ├── AuthLayout.jsx     # Login/register layout
│   └── PortalLayout.jsx   # Borrower/realtor portal layout
└── guards/
    ├── AuthGuard.jsx      # Protected route wrapper
    └── RoleGuard.jsx      # Role-based access
```

#### OnboardingWizard (3,433 lines)

```
components/onboarding/
├── OnboardingWizard.jsx   # Step orchestration (< 200 lines)
├── steps/
│   ├── WelcomeStep.jsx
│   ├── CompanySetup.jsx
│   ├── IntegrationStep.jsx
│   ├── TeamSetup.jsx
│   ├── PipelineConfig.jsx
│   └── ReviewStep.jsx
├── hooks/
│   └── useOnboarding.js   # Wizard state management
└── OnboardingProgress.jsx # Progress indicator
```

### Splitting Process

For each file:

1. **Map the sections**: Read the file and identify logical boundaries (often marked by comment blocks)
2. **Extract shared state**: Identify state/hooks used across sections → extract to shared module
3. **Create the new files**: Move each section into its own file
4. **Update imports**: All files that imported from the monolith now import from specific modules
5. **Test**: Verify the feature still works end-to-end
6. **Delete the monolith**: Only after all consumers are updated

---

<a name="api-consolidation"></a>
## 3. API Endpoint Consolidation

### Current State
- ~3,876 API endpoints across 240 route files
- For comparison: Stripe has ~300, Salesforce ~400, GitHub ~600

### Audit Process

#### Step 1: Generate Endpoint Inventory

```python
# scripts/audit_endpoints.py
from app.main import app

endpoints = []
for route in app.routes:
    if hasattr(route, 'methods'):
        for method in route.methods:
            endpoints.append({
                "method": method,
                "path": route.path,
                "name": route.name,
                "tags": getattr(route, 'tags', [])
            })

# Categorize
categories = {
    "core_crud": [],      # Standard CRUD — keep
    "debug": [],          # /debug/, /test/ — remove in prod
    "duplicate": [],      # Multiple endpoints doing same thing
    "admin_only": [],     # Internal admin — gate behind admin auth
    "deprecated": [],     # Old versions — remove
    "consolidatable": []  # Multiple specific endpoints → one generic
}
```

#### Step 2: Identify Consolidation Targets

Common patterns to consolidate:

```
# BEFORE: 5 endpoints for lead filtering
GET /api/leads/by-source/{source}
GET /api/leads/by-status/{status}
GET /api/leads/by-date-range
GET /api/leads/by-loan-officer/{lo_id}
GET /api/leads/by-tags

# AFTER: 1 endpoint with query parameters
GET /api/leads?source=website&status=new&date_from=2026-01-01&lo_id=123&tags=hot
```

#### Step 3: Deprecation Strategy

1. **Phase 1**: Add deprecation headers to consolidated endpoints
2. **Phase 2**: Route old endpoints to new ones (HTTP 301)
3. **Phase 3**: Remove old endpoints after 30 days with zero traffic

### Target

Reduce from ~3,876 to ~800–1,200 well-documented endpoints. This makes the API:
- Securable (smaller attack surface)
- Documentable (feasible to maintain OpenAPI docs)
- Testable (realistic to achieve coverage)

---

<a name="migrations"></a>
## 4. Migration Tooling

### Current State
- 153 hand-written migration files (not Alembic autogenerated)
- 169 database models
- Schema changes require manual SQL writing

### Switch to Alembic Autogeneration

#### Step 1: Set up Alembic (if not already)

```bash
pip install alembic
alembic init migrations
```

Update `alembic.ini`:
```ini
sqlalchemy.url = %(DATABASE_URL)s
```

Update `migrations/env.py` to import all models:
```python
from app.core.database import Base
from app.models import *  # Import all models so Alembic sees them

target_metadata = Base.metadata
```

#### Step 2: Create Baseline Migration

```bash
# Stamp current DB as the baseline (don't try to replay 153 migrations)
alembic stamp head

# Now autogenerate detects only FUTURE changes
alembic revision --autogenerate -m "baseline_after_manual_migrations"
```

#### Step 3: New Workflow

```bash
# After changing a model:
alembic revision --autogenerate -m "add_column_loan_encompass_id"

# Review the generated migration (ALWAYS review — autogenerate isn't perfect)
# Then apply:
alembic upgrade head
```

#### Step 4: CI Integration

Add to GitHub Actions:
```yaml
- name: Check for pending migrations
  run: |
    alembic check  # Fails if models differ from latest migration
```

This catches cases where someone changes a model but forgets to create a migration.
