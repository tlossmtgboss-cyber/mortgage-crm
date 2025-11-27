"""
Database configuration and session management
Shared by main.py and other modules to avoid circular imports

Production settings:
- Connection pooling: 5 permanent + 10 overflow connections
- Pool recycling: Refresh connections every hour
- Pool pre-ping: Verify connections before use
- Statement timeout: 30 seconds (PostgreSQL only)
- Slow query logging: Configurable threshold
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
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,           # Verify connections before use
        pool_size=5,                  # Permanent connections
        max_overflow=10,              # Additional connections under load
        pool_recycle=3600,            # Recycle connections after 1 hour
        pool_timeout=30,              # Wait max 30s for a connection
        echo=False,                   # Set True for SQL debugging
        connect_args={
            "options": f"-c statement_timeout={STATEMENT_TIMEOUT_MS}"
        }
    )

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
