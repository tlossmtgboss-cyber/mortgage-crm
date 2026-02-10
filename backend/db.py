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
from sqlalchemy import create_engine, event
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
print(f"DB.PY: PgBouncer detected: {USE_PGBOUNCER} (pooled_url_set={bool(_raw_pooled)}, urls_differ={_raw_pooled != _raw_direct})", flush=True)

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
    print("DB.PY: Using PgBouncer connection pooling (NullPool)", flush=True)
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
    print("DB.PY: Using direct PostgreSQL with QueuePool (pool_size=3, max_overflow=5, max=8)", flush=True)
    logger.info("Using direct PostgreSQL connection with SQLAlchemy pooling")
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


def get_db(request: Request = None):
    """Database session dependency for FastAPI.

    If request has tenant context (set by TenantContextMiddleware),
    sets PostgreSQL RLS session variable for defense-in-depth.

    FastAPI automatically injects Request when this is used as Depends(get_db).
    Non-FastAPI callers (scripts, tests) pass request=None and skip RLS.
    """
    db = SessionLocal()
    try:
        # Set RLS tenant context if available from middleware
        if request and hasattr(request, 'state'):
            org_id = getattr(request.state, 'organization_id', None)
            if org_id and DATABASE_URL.startswith("postgresql"):
                try:
                    from database.tenant_mixin import set_tenant_context
                    set_tenant_context(db, org_id)
                except Exception as e:
                    logger.warning(f"Failed to set RLS tenant context: {e}")
        yield db
    finally:
        db.close()


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
        return {"error": str(e), "status": "unknown"}
