"""
Migration History Tracker

Tracks which migrations have been executed, preventing duplicate runs
and providing audit trail for schema changes.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy import text

logger = logging.getLogger(__name__)

_TRACKER_TABLE = "migration_history"

def ensure_tracker_table(engine):
    """Create migration_history table if it doesn't exist."""
    with engine.connect() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {_TRACKER_TABLE} (
                id SERIAL PRIMARY KEY,
                migration_name VARCHAR(255) UNIQUE NOT NULL,
                executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                success BOOLEAN DEFAULT TRUE,
                duration_ms INTEGER,
                error_message TEXT
            )
        """))
        conn.commit()

def has_run(engine, migration_name: str) -> bool:
    """Check if a migration has already been executed successfully."""
    with engine.connect() as conn:
        result = conn.execute(
            text(f"SELECT 1 FROM {_TRACKER_TABLE} WHERE migration_name = :name AND success = TRUE"),
            {"name": migration_name}
        )
        return result.fetchone() is not None

def record_migration(engine, migration_name: str, success: bool = True, duration_ms: int = None, error: str = None):
    """Record a migration execution."""
    with engine.connect() as conn:
        conn.execute(
            text(f"""
                INSERT INTO {_TRACKER_TABLE} (migration_name, success, duration_ms, error_message)
                VALUES (:name, :success, :duration_ms, :error)
                ON CONFLICT (migration_name) DO UPDATE SET
                    executed_at = NOW(),
                    success = :success,
                    duration_ms = :duration_ms,
                    error_message = :error
            """),
            {"name": migration_name, "success": success, "duration_ms": duration_ms, "error": error}
        )
        conn.commit()

def run_tracked(engine, migration_name: str, migration_func):
    """Run a migration with tracking. Skips if already successfully run."""
    if has_run(engine, migration_name):
        logger.debug(f"Migration '{migration_name}' already applied, skipping")
        return False

    start = datetime.now(timezone.utc)
    try:
        migration_func(engine)
        duration = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        record_migration(engine, migration_name, success=True, duration_ms=duration)
        logger.info(f"Migration '{migration_name}' applied successfully ({duration}ms)")
        return True
    except Exception as e:
        duration = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        record_migration(engine, migration_name, success=False, duration_ms=duration, error=str(e)[:500])
        logger.error(f"Migration '{migration_name}' FAILED ({duration}ms): {e}")
        raise
