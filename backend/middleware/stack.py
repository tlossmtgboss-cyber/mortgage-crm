"""
Middleware Stack Configuration

Centralizes all middleware registration for the FastAPI application.
Middleware execution order is LIFO (last added = first executed).

Order of execution (outer to inner):
1. CORS - Must be outermost to handle preflight requests
2. Security Headers - Add security response headers
3. Request Validation - Validate incoming requests
4. IP Blocking - Block malicious IPs
5. Rate Limiting - Per-user/IP rate limits
6. IP Access Control - Environment-aware access control
7. Security Logging - Log security events
8. Impersonation Enforcement - Block writes during impersonation
9. Tenant Context - Set tenant/user context for multi-tenancy
10. Performance Monitoring - Track response times

Usage:
    from middleware.stack import configure_middleware
    configure_middleware(app, settings, get_db, SessionLocal)
"""

import logging
from typing import Callable, Optional

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def configure_middleware(
    app: FastAPI,
    secret_key: str,
    get_db: Callable,
    session_local: Callable,
    user_model,
    environment: str = "development",
) -> None:
    """
    Configure all middleware for the FastAPI application.

    Args:
        app: FastAPI application instance
        secret_key: Secret key for JWT verification
        get_db: Database session dependency function
        session_local: SQLAlchemy session factory
        user_model: User SQLAlchemy model
        environment: Environment name (development/production)

    Note:
        Middleware is added in reverse order of execution.
        Last added middleware executes first.
    """
    # Import security middleware
    from security_middleware import (
        IPAccessControlMiddleware,
        RateLimitMiddleware,
        SecurityHeadersMiddleware,
        IPBlockingMiddleware,
        RequestValidationMiddleware,
        SecurityLoggingMiddleware,
    )

    # =========================================================================
    # Performance Monitoring (innermost - runs last)
    # =========================================================================
    try:
        from monitoring.performance_service import PerformanceMiddleware
        app.add_middleware(PerformanceMiddleware)
        logger.info("Performance monitoring middleware enabled")
    except Exception as e:
        logger.warning(f"Performance monitoring middleware not loaded: {e}")

    # =========================================================================
    # Tenant Context (multi-tenant isolation)
    # =========================================================================
    try:
        from middleware.tenant_context_middleware import TenantContextMiddleware
        app.add_middleware(
            TenantContextMiddleware,
            secret_key=secret_key,
            get_db=get_db,
            user_model=user_model,
        )
        logger.info("Tenant context middleware enabled")
    except Exception as e:
        logger.warning(f"Tenant context middleware not loaded: {e}")

    # =========================================================================
    # Subscription Enforcement (block access after grace period expires)
    # =========================================================================
    try:
        from middleware.subscription_enforcement import SubscriptionEnforcementMiddleware
        app.add_middleware(SubscriptionEnforcementMiddleware)
        logger.info("Subscription enforcement middleware enabled")
    except Exception as e:
        logger.warning(f"Subscription enforcement middleware not loaded: {e}")

    # =========================================================================
    # Impersonation Enforcement (block writes during impersonation)
    # =========================================================================
    try:
        from middleware.impersonation_middleware import ImpersonationEnforcementMiddleware
        app.add_middleware(
            ImpersonationEnforcementMiddleware,
            db_session_factory=session_local,
        )
        logger.info("Impersonation enforcement middleware enabled")
    except Exception as e:
        logger.warning(f"Impersonation enforcement middleware not loaded: {e}")

    # =========================================================================
    # Dynamic CORS (checks database for allowed custom domains)
    # =========================================================================
    try:
        from middleware.dynamic_cors import DynamicCORSMiddleware
        app.add_middleware(
            DynamicCORSMiddleware,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["*"],
            max_age=3600,
        )
        logger.info("Dynamic CORS middleware enabled")
    except Exception as e:
        logger.warning(f"Dynamic CORS middleware not loaded: {e}")
        # Fallback to standard CORS with explicit origins (never wildcard)
        import os as _os
        from fastapi.middleware.cors import CORSMiddleware
        _fallback_origins = [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:5173",
            "https://perenniaai.com",
            "https://www.perenniaai.com",
            "https://app.perenniaai.com",
            "https://api.perenniaai.com",
        ]
        _railway_url = _os.getenv("RAILWAY_PUBLIC_DOMAIN")
        if _railway_url:
            _fallback_origins.append(f"https://{_railway_url}")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_fallback_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
        )
        logger.info("Standard CORS middleware enabled (fallback, explicit origins)")

    # =========================================================================
    # Security Middleware Stack
    # =========================================================================
    app.add_middleware(SecurityLoggingMiddleware)
    app.add_middleware(IPAccessControlMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=5000,
        requests_per_hour=100000,
    )
    app.add_middleware(IPBlockingMiddleware)
    app.add_middleware(RequestValidationMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    logger.info(
        f"Security middleware stack enabled (ENVIRONMENT={environment}): "
        "CORS, IP access control, rate limiting, IP blocking, security headers, "
        "request validation, logging"
    )


def configure_production_hardening(
    app: FastAPI,
    engine,
    session_local: Callable,
) -> tuple:
    """
    Configure production hardening features.

    Args:
        app: FastAPI application instance
        engine: SQLAlchemy engine
        session_local: SQLAlchemy session factory

    Returns:
        Tuple of (structured_logger, health_checker) or (None, None) on failure
    """
    try:
        from production_hardening import (
            setup_production_hardening,
            structured_logger,
            health_checker,
        )
        from sqlalchemy import text

        # Initialize production hardening
        hardening_result = setup_production_hardening(app, engine)
        logger.info(f"Production hardening initialized: {hardening_result}")

        # Register database health check
        async def check_database():
            try:
                with session_local() as db:
                    db.execute(text("SELECT 1"))
                    return True
            except Exception:
                return False

        health_checker.register_check("database", check_database)

        return structured_logger, health_checker

    except Exception as e:
        logger.warning(f"Production hardening not fully initialized: {e}")
        return None, None


def configure_datadog_monitoring(
    app: FastAPI,
    health_checker=None,
) -> tuple:
    """
    Configure DataDog APM and monitoring.

    Args:
        app: FastAPI application instance
        health_checker: Health checker instance for Redis check registration

    Returns:
        Tuple of (business_metrics, dd_metrics) or (None, None) on failure
    """
    try:
        from datadog_monitoring import (
            setup_datadog_monitoring,
            business_metrics,
            metrics as dd_metrics,
        )

        # Initialize DataDog monitoring
        dd_result = setup_datadog_monitoring(app)
        logger.info(f"DataDog monitoring initialized: {dd_result}")

        # Register Redis health check with DataDog
        if health_checker:
            async def check_redis():
                try:
                    from services.redis_cache import redis_cache
                    return await redis_cache.health_check()
                except Exception:
                    return False

            health_checker.register_check("redis", check_redis)

        return business_metrics, dd_metrics

    except Exception as e:
        logger.warning(f"DataDog monitoring not fully initialized: {e}")
        return None, None
