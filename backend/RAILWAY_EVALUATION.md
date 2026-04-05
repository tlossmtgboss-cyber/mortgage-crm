# Railway Platform Evaluation

## Current Configuration

| Resource | Current Setting | Railway Limit | Utilization |
|----------|---------------|--------------|-------------|
| **DB Connections** | pool_size=3 + max_overflow=5 = 8 max | 97 total (PostgreSQL) | ~8% per instance |
| **Pool Strategy** | Direct: QueuePool(3+5). PgBouncer: NullPool | PgBouncer available | Direct mode (pooled URL = direct URL on Railway) |
| **Statement Timeout** | 30s | None enforced | Self-imposed |
| **Pool Recycle** | 900s (15 min) | N/A | Appropriate |
| **Connection Keepalive** | 30s idle, 10s interval, 5 retries | N/A | Appropriate |
| **Slow Query Threshold** | 500ms | N/A | Logged only |

## Bottlenecks Identified

### 1. Connection Pool Pressure (CRITICAL)
**Problem:** 8 max connections per instance with 259 startup migrations running sequentially.
Each migration opens its own connection via `engine.connect()`.

**Evidence:** `db.py:87-89` — pool_size=3, max_overflow=5. Comment says "Railway has 97 connections max"
but startup runs dozens of migrations serially, and APScheduler background jobs also consume connections.

**Impact:** Under concurrent load (10+ simultaneous API requests + scheduler + migrations), pool_timeout=20s
can trigger "connection pool exhausted" errors.

**Fix (immediate):**
- Bump to pool_size=5, max_overflow=10 (still only 15 of 97 connections)
- Add `pool_use_lifo=True` to prefer reusing warm connections
- Set `pool_pre_ping=True` (already done)

**Fix (longer-term):**
- Enable PgBouncer on Railway (separate service) for true connection multiplexing
- This changes the effective limit from 97 physical to 10,000+ virtual connections

### 2. Startup Migration Storm (HIGH)
**Problem:** 18 migrations in init_db.py + 4 in main.py = 22 migration calls at startup.
Each calls `engine.connect()`, runs SQL, commits, closes. With pool_size=3, these
serialize through the pool.

**Impact:** Cold start takes 15-30s on Railway (observed in logs). Each deploy triggers
a restart.

**Fix:** The `squash_migrations.py` utility (just created) generates a single baseline
schema. Run `--output 000_baseline_schema.sql`, then replace the 22 individual
migration calls with one `psql < baseline_schema.sql` step.

### 3. No Read Replicas (MEDIUM)
**Problem:** All reads (dashboard analytics, pipeline views, reporting) hit the primary.
Dashboard routes aggregate across loans, leads, tasks, appointments — heavy queries
that compete with writes.

**Impact:** Under multi-tenant load, analytics queries lock rows and slow down
CRUD operations.

**Fix:** Railway supports PostgreSQL read replicas via "Replica" service type.
Add a read-only engine for analytics endpoints:
```python
READONLY_URL = os.getenv("DATABASE_READONLY_URL")
if READONLY_URL:
    readonly_engine = create_engine(READONLY_URL, pool_size=3)
```

### 4. No Connection-Level Tenant Isolation Verification (LOW)
**Problem:** RLS via `SET app.current_tenant` relies on `get_db()` being called
correctly. If any code path uses `SessionLocal()` directly (like the MUM promotion
loop we just fixed), it bypasses tenant isolation.

**Fix:** Add a connection checkout event that verifies `app.current_tenant` is set:
```python
@event.listens_for(engine, "after_begin")
def verify_tenant_set(session, transaction, connection):
    # Log warning if tenant not set (don't block — some startup code is intentional)
```

## Scale Ceiling Assessment

| Metric | Current Capacity | Next Bottleneck | When |
|--------|-----------------|----------------|------|
| **Concurrent API users** | ~50 (8 pool × ~6 req/conn/sec) | Connection pool | 50+ concurrent LOs |
| **Total leads** | ~100K (indexed queries) | Full table scans in analytics | 500K+ leads |
| **Total loans** | ~50K (active pipeline index) | Dashboard aggregation | 100K+ loans |
| **Scheduled jobs** | ~30 (APScheduler) | Job overlap at scale | 100+ orgs |
| **File storage** | S3/R2 (unlimited) | No ceiling | N/A |

## Migration Path Options

### Option A: Stay on Railway + Optimize (Recommended for next 6 months)
1. Enable PgBouncer (Railway add-on, 5 min setup)
2. Squash migrations (reduce startup from 30s to 5s)
3. Add read replica for analytics
4. Bump pool to pool_size=5, max_overflow=10
5. **Cost:** ~$20/mo additional for PgBouncer + replica

### Option B: Railway → Fly.io
- **Pros:** Edge deployment, built-in PgBouncer, better pricing at scale
- **Cons:** Migration effort, different deploy pipeline, less mature dashboard
- **When:** If Railway costs exceed $200/mo or need multi-region

### Option C: Railway → AWS (ECS/RDS)
- **Pros:** Full control, RDS read replicas, Aurora Serverless for variable load
- **Cons:** Significant DevOps overhead, longer deploy cycles
- **When:** If you need SOC 2 Type II, HIPAA BAA, or 99.99% SLA

## Recommended Next Steps (Priority Order)

1. **Now:** Squash migrations → faster cold starts
2. **This week:** Bump pool_size to 5+10 in db.py
3. **This month:** Enable Railway PgBouncer service
4. **Next quarter:** Add read replica for dashboard/analytics routes
5. **If/when needed:** Evaluate Fly.io or AWS based on load patterns
