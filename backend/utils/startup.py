"""
Startup checks for the Perennia AI backend.

Verifies critical services are reachable and logs startup configuration.
Called during FastAPI's startup event before the app begins serving traffic.
"""

import logging
import os
import time
from typing import Optional

from sqlalchemy import text
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)


def startup_checks(engine, session_factory) -> dict:
    """Run startup health checks and log configuration.

    Args:
        engine: SQLAlchemy engine instance
        session_factory: SessionLocal factory for creating DB sessions

    Returns:
        dict with startup check results
    """
    start = time.monotonic()
    results = {
        "database": False,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "checks_passed": 0,
        "checks_failed": 0,
    }

    # 1. Verify database connectivity
    try:
        db = session_factory()
        try:
            row = db.execute(text("SELECT 1 AS ok")).fetchone()
            if row and row[0] == 1:
                results["database"] = True
                results["checks_passed"] += 1
                logger.info("Startup check: database connectivity OK")
            else:
                results["checks_failed"] += 1
                logger.error("Startup check: database query returned unexpected result")
        finally:
            db.close()
    except Exception as e:
        results["checks_failed"] += 1
        logger.error(f"Startup check: database connectivity FAILED — {e}")

    # 2. Log database pool configuration
    pool = engine.pool
    if isinstance(pool, NullPool):
        results["pool_config"] = {
            "type": "NullPool (PgBouncer)",
            "note": "Connection pooling handled externally by PgBouncer",
        }
    else:
        pool_size = getattr(pool, '_pool', None)
        results["pool_config"] = {
            "type": "QueuePool",
            "pool_size": pool.size(),
            "max_overflow": getattr(pool, '_max_overflow', 'unknown'),
            "pool_timeout": getattr(pool, '_timeout', 'unknown'),
            "pool_recycle": getattr(pool, '_recycle', 'unknown'),
        }

    # 3. Log environment configuration
    env = os.getenv("ENVIRONMENT", "development")
    railway_env = os.getenv("RAILWAY_ENVIRONMENT")
    deployment_id = os.getenv("RAILWAY_DEPLOYMENT_ID", "local")

    results["config"] = {
        "environment": env,
        "railway_environment": railway_env,
        "deployment_id": deployment_id[:12] if deployment_id else None,
        "log_level": logging.getLogger().getEffectiveLevel(),
        "database_url_set": bool(os.getenv("DATABASE_URL")),
        "redis_url_set": bool(os.getenv("REDIS_URL")),
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "secret_key_set": bool(os.getenv("SECRET_KEY")),
    }

    # 4. Verify webhook verification env vars in production/staging
    effective_env = (railway_env or env or "").lower()
    is_production_like = effective_env not in ("development", "local", "test")
    if is_production_like:
        if not os.getenv("TELNYX_PUBLIC_KEY"):
            results["checks_failed"] += 1
            logger.error(
                "Startup check: TELNYX_PUBLIC_KEY not set — Telnyx webhooks "
                "will be rejected until this is configured"
            )
        else:
            results["checks_passed"] += 1
            logger.info("Startup check: TELNYX_PUBLIC_KEY configured OK")

        if not os.getenv("VAPI_WEBHOOK_SECRET"):
            results["checks_failed"] += 1
            logger.error(
                "Startup check: VAPI_WEBHOOK_SECRET not set — Vapi webhooks "
                "will be rejected until this is configured"
            )
        else:
            results["checks_passed"] += 1
            logger.info("Startup check: VAPI_WEBHOOK_SECRET configured OK")

    elapsed = time.monotonic() - start
    results["startup_check_time_ms"] = round(elapsed * 1000, 1)
    results["startup_timestamp"] = time.time()

    # Summary log
    total = results["checks_passed"] + results["checks_failed"]
    logger.info(
        f"Startup checks complete: {results['checks_passed']}/{total} passed "
        f"in {results['startup_check_time_ms']}ms "
        f"(env={env}, deployment={deployment_id[:12] if deployment_id else 'local'})"
    )

    if results["checks_failed"] > 0:
        logger.warning(
            f"Startup checks: {results['checks_failed']} check(s) failed — "
            "application may not function correctly"
        )

    return results
