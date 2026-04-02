"""
Database configuration and session management
Shared by main.py and other modules to avoid circular imports

NOTE: This file was renamed from database.py to db.py to avoid naming
conflict with the database/ package. All existing imports continue to work:
    from database import Base, SessionLocal, get_db  # Uses database/__init__.py

Production settings (Railway PostgreSQL):
- PgBouncer support: Use DATABASE_POOLED_URL for connection pooling
- Direct connection fallback: 3 permanent + 5 overflow (max 8 total)
- Pool recycling: Refresh connections every 15 min
- Pool pre-ping: Verify connections before use
- TCP keepalives: Detect dead connections quickly
- Statement timeout: 30 seconds (PostgreSQL only, direct connections)
- Slow query logging: Configurable threshold

Connection exhaustion prevention:
- Prefer PgBouncer (Railway's pooled URL) for unlimited virtual connections
- Conservative pool size for direct connections
- TCP keepalives detect network issues before they cause pool exhaustion
- Pool events logged for debugging connection issues
"""
import os
import time
import logging
import contextlib
from datetime import datetime, timezone
from typing import Dict
from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from starlette.requests import Request

logger = logging.getLogger(__name__)

# Database URL from environment
# Prefer pooled URL (PgBouncer) if available - handles connection pooling externally
DATABASE_POOLED_URL = os.getenv("DATABASE_POOLED_URL") or os.getenv("DATABASE_PUBLIC_URL")
DATABASE_URL = DATABASE_POOLED_URL or os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")

# Detect if using PgBouncer (pooled connection)
# Only treat as PgBouncer if the pooled URL is DIFFERENT from the direct URL
# Railway sets DATABASE_POOLED_URL even when there's no PgBouncer, so we must check
_raw_direct = os.getenv("DATABASE_URL", "")
_raw_pooled = os.getenv("DATABASE_POOLED_URL", "")
USE_PGBOUNCER = bool(_raw_pooled and _raw_pooled != _raw_direct)
logger.info(f"PgBouncer detected: {USE_PGBOUNCER} (pooled_url_set={bool(_raw_pooled)}, urls_differ={_raw_pooled != _raw_direct})")

# Fix postgres:// to postgresql:// for SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Configuration
SLOW_QUERY_THRESHOLD_MS = float(os.getenv("SLOW_QUERY_THRESHOLD_MS", "500"))
STATEMENT_TIMEOUT_MS = int(os.getenv("STATEMENT_TIMEOUT_MS", "30000"))  # 30 seconds

# Create Base
Base = declarative_base()

# Create engine with appropriate settings
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
elif USE_PGBOUNCER:
    # PgBouncer mode: Let PgBouncer handle connection pooling
    # Use NullPool - each request gets a fresh connection from PgBouncer
    # This prevents "too many clients" errors by using PgBouncer's pool
    logger.info("Using PgBouncer connection pooling (NullPool)")
    engine = create_engine(
        DATABASE_URL,
        poolclass=NullPool,           # No SQLAlchemy pooling - PgBouncer handles it
        echo=False,
        connect_args={
            # Note: statement_timeout not supported in PgBouncer transaction mode
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5
        }
    )
else:
    # Direct PostgreSQL connection with SQLAlchemy pooling
    # Railway has 97 connections max; conservative pool to prevent exhaustion
    # Key: pool_size + max_overflow should not exceed ~50% of Railway's limit
    logger.info("Using direct PostgreSQL connection with SQLAlchemy pooling (pool_size=3, max_overflow=5, max=8)")
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,           # CRITICAL: Verify connections before use (catches stale/dead connections)
        pool_size=3,                  # Permanent connections (reduced to stay under Railway limits)
        max_overflow=5,               # Additional connections under load (total max: 8)
        pool_recycle=900,             # Recycle connections every 15 min (was 30 - faster recycling prevents stale connections)
        pool_timeout=20,              # Wait max 20s for a connection (fail fast if pool exhaustion)
        echo=False,                   # Set True for SQL debugging
        connect_args={
            "options": f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
            "keepalives": 1,          # Enable TCP keepalives
            "keepalives_idle": 30,    # Start keepalives after 30s idle
            "keepalives_interval": 10, # Send keepalive every 10s
            "keepalives_count": 5     # Close connection after 5 failed keepalives
        }
    )

# Connection pool event logging (for debugging connection exhaustion)
# Note: These events work differently with NullPool vs QueuePool

@event.listens_for(engine, "checkout")
def on_checkout(dbapi_conn, connection_record, connection_proxy):
    """Log when a connection is checked out from the pool."""
    if USE_PGBOUNCER:
        logger.debug("DB connection acquired from PgBouncer")
    else:
        pool = engine.pool
        logger.debug(
            f"DB connection checkout - Pool status: "
            f"size={pool.size()}, checkedin={pool.checkedin()}, "
            f"checkedout={pool.checkedout()}, overflow={pool.overflow()}"
        )

@event.listens_for(engine, "checkin")
def on_checkin(dbapi_conn, connection_record):
    """Log when a connection is returned to the pool."""
    if USE_PGBOUNCER:
        logger.debug("DB connection returned to PgBouncer")
    else:
        pool = engine.pool
        logger.debug(
            f"DB connection checkin - Pool status: "
            f"size={pool.size()}, checkedin={pool.checkedin()}, "
            f"checkedout={pool.checkedout()}, overflow={pool.overflow()}"
        )

@event.listens_for(engine, "connect")
def on_connect(dbapi_conn, connection_record):
    """Log when a new connection is created."""
    if USE_PGBOUNCER:
        logger.debug("New PgBouncer connection established")
    else:
        logger.info("New database connection established")

@event.listens_for(engine, "invalidate")
def on_invalidate(dbapi_conn, connection_record, exception):
    """Log when a connection is invalidated (detected as stale)."""
    logger.warning(f"Database connection invalidated: {exception}")

# Slow query logging
@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("query_start_time", []).append(time.time())

@event.listens_for(engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total_time = time.time() - conn.info["query_start_time"].pop(-1)
    total_time_ms = total_time * 1000

    if total_time_ms > SLOW_QUERY_THRESHOLD_MS:
        # Truncate long queries for logging
        truncated_statement = statement[:500] + "..." if len(statement) > 500 else statement
        logger.warning(
            f"Slow query detected ({total_time_ms:.1f}ms > {SLOW_QUERY_THRESHOLD_MS}ms): "
            f"{truncated_statement}"
        )

# Create SessionLocal
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Per-tenant connection tracking (PERF-008)
# Prevents one org from exhausting all DB connections
import threading

_tenant_connection_counts: Dict[int, int] = {}
_tenant_conn_lock = threading.Lock()

# Max concurrent DB connections per tenant (configurable via env)
MAX_CONNECTIONS_PER_TENANT = int(os.getenv("MAX_DB_CONNECTIONS_PER_TENANT", "3"))


def get_db(request: Request = None):
    """Database session dependency for FastAPI.

    If request has tenant context (set by TenantContextMiddleware),
    sets PostgreSQL RLS session variable for defense-in-depth.

    Also enforces per-tenant connection limits (PERF-008) to prevent
    one organization from exhausting the connection pool.

    FastAPI automatically injects Request when this is used as Depends(get_db).
    Non-FastAPI callers (scripts, tests) pass request=None and skip RLS.
    """
    org_id = None
    if request and hasattr(request, 'state'):
        org_id = getattr(request.state, 'organization_id', None)

    # Per-tenant connection limit check (PERF-008)
    # Only enforce per-tenant limits when using QueuePool (not NullPool/PgBouncer).
    # PgBouncer handles connection pooling externally — per-tenant counting would
    # add overhead without benefit and could cause false 503s (PERF-003).
    _enforce_tenant_limits = not USE_PGBOUNCER and org_id and MAX_CONNECTIONS_PER_TENANT > 0

    if _enforce_tenant_limits:
        with _tenant_conn_lock:
            current = _tenant_connection_counts.get(org_id, 0)
            if current >= MAX_CONNECTIONS_PER_TENANT:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=503,
                    detail="Service temporarily unavailable — too many concurrent requests for your organization. Please retry shortly.",
                    headers={"Retry-After": "2"},
                )
            _tenant_connection_counts[org_id] = current + 1

    db = SessionLocal()
    try:
        # Set RLS tenant context if available from middleware
        if org_id and DATABASE_URL.startswith("postgresql"):
            try:
                from database.tenant_mixin import set_tenant_context
                set_tenant_context(db, org_id)
            except Exception as e:
                # TENANT-006: Fail loudly in production/staging — silent RLS failure
                # means queries run WITHOUT tenant isolation, leaking data cross-tenant.
                env = os.environ.get("RAILWAY_ENVIRONMENT", os.environ.get("ENV", "development"))
                if env in ("production", "staging"):
                    logger.error(f"CRITICAL: RLS tenant context failed: {e}")
                    raise
                logger.warning(f"RLS context failed (dev mode): {e}")
        yield db
    finally:
        db.close()
        # Release the per-tenant connection slot
        if _enforce_tenant_limits:
            with _tenant_conn_lock:
                current = _tenant_connection_counts.get(org_id, 1)
                if current <= 1:
                    _tenant_connection_counts.pop(org_id, None)
                else:
                    _tenant_connection_counts[org_id] = current - 1


@contextlib.contextmanager
def get_db_with_tenant(org_id: int):
    """Database session context manager with RLS tenant context for background workers.

    Background tasks (APScheduler, Celery) run outside the FastAPI request lifecycle,
    so they don't get tenant context from TenantContextMiddleware. This function
    creates a session AND sets the PostgreSQL RLS session variable, ensuring that
    Row-Level Security policies are enforced even in background workers.

    Args:
        org_id: Organization/tenant ID. Must be a positive integer.

    Yields:
        SQLAlchemy Session with RLS tenant context set.

    Usage:
        for org_id in org_ids:
            with get_db_with_tenant(org_id) as db:
                # All queries in this block are RLS-filtered to org_id
                results = db.query(MyModel).all()

    Raises:
        ValueError: If org_id is not a positive integer.
    """
    if not isinstance(org_id, int) or org_id <= 0:
        raise ValueError(f"org_id must be a positive integer, got: {org_id}")

    db = SessionLocal()
    try:
        # Set RLS tenant context (PostgreSQL only; no-op on SQLite)
        if DATABASE_URL.startswith("postgresql"):
            try:
                from database.tenant_mixin import set_tenant_context
                set_tenant_context(db, org_id)
                logger.debug(f"Background worker: RLS tenant context set to org_id={org_id}")
            except Exception as e:
                env = os.environ.get("RAILWAY_ENVIRONMENT", os.environ.get("ENV", "development"))
                if env in ("production", "staging"):
                    logger.error(
                        f"CRITICAL: Background worker RLS tenant context failed for org_id={org_id}: {e}. "
                        "Refusing to yield unscoped session in production/staging."
                    )
                    raise
                logger.warning(
                    f"Background worker: Failed to set RLS tenant context for org_id={org_id}: {e}. "
                    "Queries will run WITHOUT tenant isolation (dev mode only)."
                )
        else:
            logger.debug(
                f"Background worker: Skipping RLS (non-PostgreSQL database) for org_id={org_id}"
            )
        yield db
    except Exception as e:
        logger.exception(f"Error in tenant-scoped DB session for org_id={org_id}: {e}")
        db.rollback()
        raise
    finally:
        db.close()


# =============================================================================
# CMP-002: Auto-instrumentation for mutation audit logging
# =============================================================================
# SQLAlchemy ORM event listeners that automatically log INSERT/UPDATE/DELETE
# operations with tenant context to the audit_logs table.

_AUDIT_SKIP_TABLES = frozenset({
    'audit_logs',           # Don't audit the audit table itself
    'alembic_version',      # Migration metadata
    'user_sessions',        # High-frequency session touches
    'ai_token_usage_log',   # High-frequency AI usage
    'rate_limit_events',    # Rate limiter internal state
})

_audit_enabled = os.getenv("ENABLE_MUTATION_AUDIT", "true").lower() == "true"


def _setup_mutation_audit():
    """Register ORM-level after_flush listener for auto audit logging."""

    if not _audit_enabled:
        logger.info("Mutation audit logging disabled (ENABLE_MUTATION_AUDIT=false)")
        return

    from sqlalchemy.orm import Session as SASession
    from sqlalchemy import event as sa_event, inspect

    @sa_event.listens_for(SASession, "after_flush")
    def after_flush(session, flush_context):
        """Capture new/modified/deleted objects and write audit entries.

        CRITICAL: This entire handler is wrapped in try/except because exceptions
        in after_flush propagate through SQLAlchemy's event system back to the
        db.commit() caller. An unhandled error here would turn routine commits
        (e.g., updating api_key.last_used_at in auth) into 500 Internal Server Errors.
        """
        if not DATABASE_URL.startswith("postgresql"):
            return  # Only audit on PostgreSQL

        try:
            # Extract authenticated user from request context (COMP-001)
            current_user_id = None
            try:
                from middleware.request_context import get_user_id
                uid_str = get_user_id()
                if uid_str is not None:
                    current_user_id = int(uid_str)
            except (ImportError, ValueError, TypeError):
                pass  # No request context or non-integer user_id

            # Collect changes from the flush
            audit_entries = []

            for obj in session.new:
                table = getattr(obj, '__tablename__', None)
                if not table or table in _AUDIT_SKIP_TABLES:
                    continue
                org_id = getattr(obj, 'organization_id', None)
                entity_id = getattr(obj, 'id', None)
                audit_entries.append({
                    "change_type": "insert",
                    "entity_type": table,
                    "entity_id": entity_id,
                    "organization_id": org_id,
                    "user_id": current_user_id,
                    "after_state": _safe_state(obj),
                })

            for obj in session.dirty:
                table = getattr(obj, '__tablename__', None)
                if not table or table in _AUDIT_SKIP_TABLES:
                    continue
                insp = inspect(obj)
                changes = {}
                for attr in insp.attrs:
                    hist = attr.history
                    if hist.has_changes():
                        changes[attr.key] = {
                            "old": _serialize(hist.deleted[0]) if hist.deleted else None,
                            "new": _serialize(hist.added[0]) if hist.added else None,
                        }
                if not changes:
                    continue
                org_id = getattr(obj, 'organization_id', None)
                entity_id = getattr(obj, 'id', None)
                audit_entries.append({
                    "change_type": "update",
                    "entity_type": table,
                    "entity_id": entity_id,
                    "organization_id": org_id,
                    "user_id": current_user_id,
                    "before_state": {k: v["old"] for k, v in changes.items()},
                    "after_state": {k: v["new"] for k, v in changes.items()},
                })

            for obj in session.deleted:
                table = getattr(obj, '__tablename__', None)
                if not table or table in _AUDIT_SKIP_TABLES:
                    continue
                org_id = getattr(obj, 'organization_id', None)
                entity_id = getattr(obj, 'id', None)
                audit_entries.append({
                    "change_type": "delete",
                    "entity_type": table,
                    "entity_id": entity_id,
                    "organization_id": org_id,
                    "user_id": current_user_id,
                    "before_state": _safe_state(obj),
                })

            # Write audit entries (use a separate connection to avoid flush recursion)
            if audit_entries:
                _write_audit_batch(audit_entries)

        except Exception as e:
            logger.warning(f"Mutation audit after_flush failed (non-fatal): {e}")


def _safe_state(obj) -> dict:
    """Extract a JSON-safe dict of an ORM object's columns (no relationships)."""
    try:
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(type(obj))
        state = {}
        for col in mapper.columns:
            val = getattr(obj, col.key, None)
            state[col.key] = _serialize(val)
        return state
    except Exception as e:
        logger.exception(f"Failed to extract safe state from ORM object: {e}")
        return {}


def _serialize(val):
    """Make a value JSON-serializable."""
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    return str(val)


def _write_audit_batch(entries: list):
    """Write audit log entries in a background thread to avoid holding two pool
    connections simultaneously (the caller's session + this write connection).

    Previously this ran synchronously inside after_flush, which meant every
    db.commit() needed TWO pool connections at once.  With pool_size=3 +
    max_overflow=5 (8 total), concurrent requests could exhaust the pool and
    cause TimeoutError → 500 Internal Server Error on login and other routes.
    """
    import json as _json

    # Snapshot the data needed — entries are plain dicts, already safe to pass
    # across threads.  Capture timestamp now so it reflects commit time.
    ts = datetime.now(timezone.utc)

    def _bg_write():
        try:
            with engine.connect() as conn:
                for entry in entries:
                    conn.execute(
                        text("""
                            INSERT INTO audit_logs
                                (user_id, changed_by_id, change_type, entity_type, entity_id,
                                 before_state, after_state, timestamp, organization_id)
                            VALUES
                                (:user_id, :changed_by_id, :change_type, :entity_type, :entity_id,
                                 :before_state, :after_state, :ts, :org_id)
                        """),
                        {
                            "user_id": entry.get("user_id"),
                            "changed_by_id": entry.get("user_id"),
                            "change_type": entry["change_type"],
                            "entity_type": entry["entity_type"],
                            "entity_id": entry.get("entity_id"),
                            "before_state": _json.dumps(entry.get("before_state")) if entry.get("before_state") else None,
                            "after_state": _json.dumps(entry.get("after_state")) if entry.get("after_state") else None,
                            "ts": ts,
                            "org_id": entry.get("organization_id"),
                        },
                    )
                conn.commit()
        except Exception as e:
            logger.warning(f"Mutation audit batch write failed: {e}")

    thread = threading.Thread(target=_bg_write, daemon=True)
    thread.start()


# Initialize on module load
try:
    _setup_mutation_audit()
except Exception as e:
    logger.warning(f"Failed to setup mutation audit: {e}")


def get_db_url():
    """Get database URL (helper for migrations)"""
    url = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
    # Fix postgres:// to postgresql:// for SQLAlchemy
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def get_pool_status():
    """
    Get current connection pool status for debugging and health checks.

    Returns:
        dict: Pool status with size, checked in/out, and overflow counts
    """
    try:
        pool = engine.pool

        # NullPool (PgBouncer mode) doesn't track connections
        if isinstance(pool, NullPool):
            return {
                "pool_type": "NullPool (PgBouncer)",
                "status": "healthy",
                "note": "Connection pooling handled by PgBouncer"
            }

        return {
            "pool_type": "QueuePool (SQLAlchemy)",
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "total_connections": pool.checkedout() + pool.checkedin(),
            "max_connections": pool.size() + pool._max_overflow,
            "status": "healthy" if pool.checkedout() < (pool.size() + pool._max_overflow) else "saturated"
        }
    except Exception as e:
        return {"error": "Internal server error", "status": "unknown"}
