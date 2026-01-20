"""
Database configuration and session management
Shared by main.py and other modules to avoid circular imports

Production settings (Railway PostgreSQL):
- Connection pooling: 3 permanent + 5 overflow (max 8 total)
- Pool recycling: Refresh connections every 15 min
- Pool pre-ping: Verify connections before use
- TCP keepalives: Detect dead connections quickly
- Statement timeout: 30 seconds (PostgreSQL only)
- Slow query logging: Configurable threshold

Connection exhaustion prevention:
- Conservative pool size stays under Railway's ~20 connection limit
- TCP keepalives detect network issues before they cause pool exhaustion
- Pool events logged for debugging connection issues
"""
import os
import time
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
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
else:
    # PostgreSQL production settings
    # Railway has ~20 connections max; conservative pool to prevent exhaustion
    # Key: pool_size + max_overflow should not exceed ~50% of Railway's limit
    # This leaves room for migrations, admin tools, and connection spikes
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,           # CRITICAL: Verify connections before use (catches stale/dead connections)
        pool_size=3,                  # Permanent connections (reduced to stay under Railway limits)
        max_overflow=5,               # Additional connections under load (total max: 8)
        pool_recycle=900,             # Recycle connections every 15 min (was 30 - faster recycling prevents stale connections)
        pool_timeout=20,              # Wait max 20s for a connection (fail fast if pool exhausted)
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
@event.listens_for(engine, "checkout")
def on_checkout(dbapi_conn, connection_record, connection_proxy):
    """Log when a connection is checked out from the pool."""
    pool = engine.pool
    logger.debug(
        f"DB connection checkout - Pool status: "
        f"size={pool.size()}, checkedin={pool.checkedin()}, "
        f"checkedout={pool.checkedout()}, overflow={pool.overflow()}"
    )

@event.listens_for(engine, "checkin")
def on_checkin(dbapi_conn, connection_record):
    """Log when a connection is returned to the pool."""
    pool = engine.pool
    logger.debug(
        f"DB connection checkin - Pool status: "
        f"size={pool.size()}, checkedin={pool.checkedin()}, "
        f"checkedout={pool.checkedout()}, overflow={pool.overflow()}"
    )

@event.listens_for(engine, "connect")
def on_connect(dbapi_conn, connection_record):
    """Log when a new connection is created."""
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


def get_db():
    """Database session dependency for FastAPI"""
    db = SessionLocal()
    try:
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
        return {
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
