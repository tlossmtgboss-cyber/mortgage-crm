# Row-Level Security (RLS) for Perennia AI

## What RLS Is and Why It Matters

PostgreSQL Row-Level Security (RLS) enforces data isolation **at the database level**. Without RLS, tenant isolation relies entirely on application code: every query must include `WHERE organization_id = :org_id`. A single missing filter — or a raw SQL mistake — silently leaks data across tenants.

RLS adds a transparent policy to each table so that PostgreSQL itself filters rows before returning them. Even if application code omits the `organization_id` filter, the database refuses to return rows that don't belong to the current tenant.

This is **defense in depth**: the application layer filters, and the database layer enforces. A bug in one layer doesn't compromise isolation.

## How the Session Variable Works

### Setting the Tenant Context

The FastAPI app sets a PostgreSQL session variable on every request via `db.py`:

```python
# db.py — get_db() dependency
from database.tenant_mixin import set_tenant_context

def get_db(request: Request = None):
    org_id = getattr(request.state, 'organization_id', None)
    db = SessionLocal()
    if org_id and DATABASE_URL.startswith("postgresql"):
        set_tenant_context(db, org_id)  # SET LOCAL app.current_tenant = '<org_id>'
    yield db
    db.close()
```

`SET LOCAL` scopes the variable to the **current transaction**. When the session is closed/returned to the pool, the variable is automatically cleared.

### How the RLS Policy Uses It

Each table gets this policy:

```sql
CREATE POLICY tenant_isolation ON <table>
    FOR ALL
    USING (
        organization_id = NULLIF(current_setting('app.current_tenant', true), '')::integer
    )
    WITH CHECK (
        organization_id = NULLIF(current_setting('app.current_tenant', true), '')::integer
    );
```

- `USING` filters reads (SELECT, UPDATE target, DELETE target)
- `WITH CHECK` filters writes (INSERT, UPDATE new values)
- `current_setting('app.current_tenant', true)` — the `true` means "return NULL instead of error if the variable is not set"
- `NULLIF(..., '')` — converts empty string to NULL
- If the result is NULL, `organization_id = NULL` evaluates to FALSE for every row, so **zero rows are returned** (fail-closed)

## Running the Migration

```bash
# From backend/ directory

# 1. Dry run — see what would happen
python -m migrations.enable_row_level_security --dry-run

# 2. Apply
python -m migrations.enable_row_level_security

# 3. Rollback (if needed)
python -m migrations.enable_row_level_security --rollback

# 4. Rollback dry run
python -m migrations.enable_row_level_security --rollback --dry-run
```

## Testing That RLS Is Working

### Quick Smoke Test (psql)

```sql
-- Connect to the database
-- 1. Without tenant context, queries should return zero rows
SELECT count(*) FROM leads;
-- Expected: 0 (no tenant context set)

-- 2. Set tenant context and verify filtering
SET app.current_tenant = '1';
SELECT count(*) FROM leads;
-- Expected: only org 1's leads

-- 3. Try to read another org's data
SET app.current_tenant = '2';
SELECT count(*) FROM leads WHERE organization_id = 1;
-- Expected: 0 (RLS blocks cross-tenant reads)

-- 4. Clear context
RESET app.current_tenant;
SELECT count(*) FROM leads;
-- Expected: 0 (back to fail-closed)
```

### Application-Level Test

```python
from database.tenant_mixin import set_tenant_context, clear_tenant_context

# In a test:
db = SessionLocal()

# No context — should return empty
results = db.query(Lead).all()
assert len(results) == 0

# Set context to org 1
set_tenant_context(db, 1)
org1_leads = db.query(Lead).all()
assert all(lead.organization_id == 1 for lead in org1_leads)

# Switch to org 2
set_tenant_context(db, 2)
org2_leads = db.query(Lead).all()
assert all(lead.organization_id == 2 for lead in org2_leads)

# Verify isolation
set_tenant_context(db, 1)
cross_tenant = db.query(Lead).filter(Lead.organization_id == 2).all()
assert len(cross_tenant) == 0  # RLS blocks this

db.close()
```

### Verify RLS Is Enabled on a Table

```sql
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class
WHERE relnamespace = 'public'::regnamespace
  AND relrowsecurity = true
ORDER BY relname;
```

### List All RLS Policies

```sql
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename;
```

## Bypassing RLS for Admin and Migration Scripts

RLS is enforced for **all users**, including table owners (`FORCE ROW LEVEL SECURITY` is enabled). There are several ways to bypass it when needed:

### Option 1: Superuser Without the Session Variable (Recommended for Migrations)

If `app.current_tenant` is not set, the policy returns zero rows. But a PostgreSQL **superuser** can bypass RLS entirely:

```sql
-- As superuser: RLS policies are ignored
ALTER ROLE my_migration_user BYPASSRLS;
```

Then connect as that role for migrations. The application role should NOT have `BYPASSRLS`.

### Option 2: Separate Connection Without `set_tenant_context`

For ad-hoc admin scripts that need cross-tenant access, create a raw connection without calling `set_tenant_context()`:

```python
from sqlalchemy import create_engine, text

# Direct connection — no RLS context set
# WARNING: Only use for admin/migration operations
engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    # This bypasses RLS only if the database role has BYPASSRLS
    # or if FORCE ROW LEVEL SECURITY is temporarily disabled
    result = conn.execute(text("SELECT count(*) FROM leads"))
```

### Option 3: Temporarily Disable FORCE RLS (Emergency Only)

```sql
-- Disable FORCE so table owners bypass RLS
ALTER TABLE leads NO FORCE ROW LEVEL SECURITY;

-- Do admin work...

-- Re-enable
ALTER TABLE leads FORCE ROW LEVEL SECURITY;
```

### Option 4: Background Workers (get_db_with_tenant)

Background workers (APScheduler, Celery) should use `get_db_with_tenant(org_id)` from `db.py`, which sets the tenant context explicitly. If a background job needs cross-tenant access, it should iterate over organizations:

```python
from db import get_db_with_tenant

for org_id in org_ids:
    with get_db_with_tenant(org_id) as db:
        # Scoped to this org
        process_org_data(db, org_id)
```

## Important Warnings

1. **Test before production**: Run `--dry-run` first. Then apply in staging. Verify that all API endpoints still return correct data. The fail-closed behavior means any request that doesn't set `app.current_tenant` will get zero rows.

2. **Internal/system routes**: Routes like health checks, cron jobs, or webhook receivers that don't have a user context will get zero rows from RLS-protected tables unless they explicitly set the tenant context. Audit these routes before enabling RLS.

3. **Tables without organization_id**: Some tables (e.g., `organizations`, `users`, `alembic_version`) don't have `organization_id` and are NOT covered by RLS. Access control for these tables remains application-side only.

4. **Direct SQL tools**: Any direct database access (pgAdmin, psql, DBeaver) will return zero rows unless you either set `app.current_tenant` or connect as a `BYPASSRLS` role.

5. **Performance**: RLS adds a filter predicate to every query. Since `organization_id` is already indexed on all tables, the overhead is negligible. But verify with `EXPLAIN ANALYZE` on critical queries after enabling.

6. **INSERT operations**: The `WITH CHECK` clause ensures new rows can only be inserted with the current tenant's `organization_id`. An INSERT with a mismatched `organization_id` will fail with a policy violation error.
