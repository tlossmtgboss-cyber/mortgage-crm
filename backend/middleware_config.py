"""
Middleware Configuration

Configures the full middleware stack for the FastAPI application.
Order matters (Starlette LIFO: last added = outermost = first to execute).

Extracted from main.py — structural move only, no logic changes.
"""

import logging
import os

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def configure_middleware(
    app: FastAPI,
    *,
    graceful_shutdown,
    secret_key: str,
    get_db,
    SessionLocal,
    User,
    ENVIRONMENT: str,
):
    """
    Apply the full middleware stack in correct order.

    Starlette uses LIFO: last added = outermost = first to execute on request.
    The order below (from first-added/innermost to last-added/outermost) is:

     22. RequestTrackingMiddleware     — tracks in-flight requests for graceful shutdown
     21. SecurityHeadersMiddleware     — security response headers
     20. RequestValidationMiddleware   — (security_middleware) request validation
     19. RequestValidatorMiddleware    — Content-Type, size, injection checks
     18. IPBlockingMiddleware          — blocks malicious IPs
     17. IPAccessControlMiddleware     — environment-aware IP access control
     16. SecurityLoggingMiddleware     — logs security events
      ─  APIVersioningMiddleware      — API version headers
     15. ImpersonationEnforcementMiddleware — blocks writes in read-only impersonation
     14. CSRFProtectionMiddleware      — CSRF token validation on state-changing requests
     13. PerformanceMiddleware         — response time tracking
     12. APIRateLimitMiddleware        — per-user/per-IP sliding window (primary rate limiter)
     11. MobileRateLimitMiddleware     — mobile-specific rate limits
     10. TenantRateLimitMiddleware     — per-org rate limits
      9b. CentralizedRBACMiddleware   — granular route-to-permission mapping
      9. RBACEnforcementMiddleware     — defense-in-depth role checks on admin routes
      8. TenantContextMiddleware       — sets request.state.user/tenant from JWT
      7. BreadcrumbAuditMiddleware     — audit_events table (defense-in-depth, mutations only)
      6. AuditMiddleware (SOC2)        — soc2_audit_log table (compliance)
      5. CacheControlMiddleware        — Cache-Control headers for mobile API
      4. BackpressureMiddleware        — load shedding when in-flight > threshold (503)
      3. DynamicCORSMiddleware         — CORS headers on all responses incl. errors
      2. PIIResponseFilterMiddleware   — masks SSN/account-number leaks in responses
      1. RequestContextMiddleware      — correlation IDs (X-Request-ID), structured logging
      0. GZipMiddleware                — compress responses >= 1 KB
    """
    from utils.shutdown import RequestTrackingMiddleware
    from security_middleware import (
        IPAccessControlMiddleware,
        SecurityHeadersMiddleware,
        IPBlockingMiddleware,
        RequestValidationMiddleware,
        SecurityLoggingMiddleware,
    )
    from middleware.dynamic_cors import DynamicCORSMiddleware
    from middleware.impersonation_middleware import ImpersonationEnforcementMiddleware
    from middleware.tenant_context_middleware import TenantContextMiddleware

    # ── Innermost (added first) ─────────────────────────────────────────

    # Request tracking for graceful shutdown
    app.add_middleware(RequestTrackingMiddleware, shutdown_handler=graceful_shutdown)

    # Security middleware
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestValidationMiddleware)

    # Request Validator — Content-Type, Content-Length / size limit, injection checks
    try:
        from middleware.request_validator import RequestValidatorMiddleware
        app.add_middleware(RequestValidatorMiddleware)
        logger.info("Request validator middleware enabled (Content-Type, size limit, injection checks)")
    except Exception as e:
        logger.warning(f"Request validator middleware not loaded: {e}")

    app.add_middleware(IPBlockingMiddleware)
    app.add_middleware(IPAccessControlMiddleware)
    app.add_middleware(SecurityLoggingMiddleware)

    # API Versioning
    try:
        from middleware.api_versioning import APIVersioningMiddleware
        app.add_middleware(APIVersioningMiddleware, current_version="2.0")
        logger.info("API versioning middleware enabled (V1 deprecation headers active)")
    except Exception as e:
        logger.warning(f"API versioning middleware not loaded: {e}")

    # Impersonation read-only enforcement
    app.add_middleware(ImpersonationEnforcementMiddleware, db_session_factory=SessionLocal)

    # CSRF Protection
    try:
        from middleware.csrf_protection import CSRFProtectionMiddleware
        csrf_enabled = ENVIRONMENT.lower() not in ("development", "test")
        app.add_middleware(
            CSRFProtectionMiddleware,
            enabled=csrf_enabled,
            cookie_secure=ENVIRONMENT == "production",
        )
        logger.info(f"CSRF protection middleware {'enabled' if csrf_enabled else 'disabled (dev mode)'}")
    except Exception as e:
        logger.warning(f"CSRF protection middleware not loaded: {e}")

    # Performance Monitoring
    try:
        from monitoring.performance_service import PerformanceMiddleware
        app.add_middleware(PerformanceMiddleware)
        logger.info("Performance monitoring middleware enabled")
    except Exception as e:
        logger.warning(f"Performance monitoring middleware not loaded: {e}")

    # Per-User/Per-IP API Rate Limiting
    try:
        from middleware.api_rate_limit import APIRateLimitMiddleware
        app.add_middleware(APIRateLimitMiddleware)
        logger.info("API rate limiting middleware enabled (per-user/per-IP sliding window)")
    except Exception as e:
        logger.warning(f"API rate limiting middleware not loaded: {e}")

    # Mobile-Specific Rate Limiting
    try:
        from middleware.mobile_rate_limit import MobileRateLimitMiddleware
        app.add_middleware(MobileRateLimitMiddleware)
        logger.info("Mobile rate limiting middleware enabled (per-user/per-IP, mobile UA only)")
    except Exception as e:
        logger.warning(f"Mobile rate limiting middleware not loaded: {e}")

    # Per-Tenant Rate Limiting
    try:
        from middleware.tenant_rate_limiter import TenantRateLimitMiddleware
        app.add_middleware(TenantRateLimitMiddleware)
        logger.info("Tenant rate limiting middleware enabled")
    except Exception as e:
        logger.warning(f"Tenant rate limiting middleware not loaded: {e}")

    # RBAC Enforcement
    try:
        from middleware.rbac_enforcement import RBACEnforcementMiddleware
        app.add_middleware(RBACEnforcementMiddleware)
        logger.info("RBAC enforcement middleware enabled")
    except Exception as e:
        logger.warning(f"RBAC enforcement middleware not loaded: {e}")

    # Centralized RBAC
    try:
        from middleware.rbac_middleware import CentralizedRBACMiddleware
        app.add_middleware(CentralizedRBACMiddleware)
        logger.info("Centralized RBAC middleware enabled (granular route permissions)")
    except Exception as e:
        logger.warning(f"Centralized RBAC middleware not loaded: {e}")

    # Multi-Tenant context
    try:
        app.add_middleware(
            TenantContextMiddleware,
            secret_key=secret_key,
            get_db=get_db,
            user_model=User,
        )
        logger.info("Tenant context middleware enabled")
    except Exception as e:
        logger.warning(f"Tenant context middleware not loaded: {e}")

    # SOC 2 Type II Compliance — Audit trail
    try:
        from soc2_compliance.middleware.audit_middleware import AuditMiddleware
        app.add_middleware(AuditMiddleware)
        logger.info("SOC 2 audit trail middleware enabled")
    except Exception as e:
        logger.error(f"SOC 2 audit middleware not loaded: {e}")
        if ENVIRONMENT == "production":
            logger.critical("SOC 2 audit middleware failed in production — audit logging degraded")

    # Breadcrumb audit middleware
    try:
        from middleware.audit_middleware import AuditMiddleware as BreadcrumbAuditMiddleware
        app.add_middleware(BreadcrumbAuditMiddleware)
        logger.info("Breadcrumb audit middleware enabled (audit_events table)")
    except Exception as e:
        logger.warning(f"Breadcrumb audit middleware not loaded: {e}")

    logger.info(f"Security middleware enabled (ENVIRONMENT={os.getenv('ENVIRONMENT', 'development')}): "
                "IP access control, rate limiting, IP blocking, security headers, request validation, and logging")

    # ── Outermost (added last) ──────────────────────────────────────────

    # Backpressure / Load Shedding
    try:
        from middleware.backpressure import BackpressureMiddleware
        app.add_middleware(BackpressureMiddleware)
        from middleware.backpressure import MAX_CONCURRENT_REQUESTS as _bp_max
        logger.info(f"Backpressure middleware enabled (max_concurrent={_bp_max})")
    except Exception as e:
        logger.warning(f"Backpressure middleware not loaded: {e}")

    # Cache-Control
    try:
        from middleware.cache_control import CacheControlMiddleware
        app.add_middleware(CacheControlMiddleware)
        logger.info("Cache-Control middleware enabled (path-based response caching)")
    except Exception as e:
        logger.warning(f"Cache-Control middleware not loaded: {e}")

    # CORS — MUST be added LAST to be absolute outermost
    try:
        app.add_middleware(
            DynamicCORSMiddleware,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            allow_headers=[
                "Accept", "Accept-Language", "Authorization", "Content-Language",
                "Content-Type", "Origin", "X-Requested-With", "X-CSRF-Token",
                "X-Request-ID", "X-Visitor-ID", "X-API-Key", "X-Impersonation-Token",
                "X-Mask-PII",
            ],
            expose_headers=[
                "Content-Length", "Content-Type", "X-Request-ID", "X-Response-Time",
                "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset",
                "X-RateLimit-Tier", "Retry-After",
            ],
            max_age=3600,
        )
        logger.info("CORS middleware enabled")
    except Exception as e:
        logger.warning(f"CORS middleware not loaded: {e}")

    # PII Response Filter
    try:
        from middleware.pii_response_filter import PIIResponseFilterMiddleware
        app.add_middleware(
            PIIResponseFilterMiddleware,
            mode=os.environ.get("PII_RESPONSE_MODE", "mask"),
        )
        logger.info("PII response filter middleware enabled (mode=%s)",
                    os.environ.get("PII_RESPONSE_MODE", "mask"))
    except Exception as e:
        logger.warning(f"PII response filter middleware not loaded: {e}")

    # Request Context — correlation IDs and structured request logging
    try:
        from middleware.request_context import RequestContextMiddleware
        app.add_middleware(RequestContextMiddleware)
        logger.info("Request context middleware enabled (correlation IDs + structured request logging)")
    except Exception as e:
        logger.warning(f"Request context middleware not loaded: {e}")

    # GZip Compression
    from starlette.middleware.gzip import GZipMiddleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    logger.info("GZip compression middleware enabled (minimum_size=1000)")


def configure_production_hardening(app: FastAPI, engine, SessionLocal):
    """Configure production hardening: Sentry, structured logging, request tracing."""
    structured_logger = None
    health_checker = None

    try:
        from production_hardening import (
            setup_production_hardening,
            structured_logger as _sl,
            health_checker as _hc,
            get_request_id,
            monitor_performance
        )
        from sqlalchemy import text

        hardening_result = setup_production_hardening(app, engine)
        logger.info(f"Production hardening initialized: {hardening_result}")
        structured_logger = _sl
        health_checker = _hc

        async def check_database():
            try:
                with SessionLocal() as db:
                    db.execute(text("SELECT 1"))
                    return True
            except Exception as e:
                logger.warning(f"Database health check failed: {e}")
                return False

        health_checker.register_check("database", check_database)

    except Exception as e:
        logger.warning(f"Production hardening not fully initialized: {e}")

    return structured_logger, health_checker


def configure_datadog_monitoring(app: FastAPI, health_checker):
    """Configure DataDog monitoring: APM, Metrics, Dashboards."""
    try:
        from datadog_monitoring import (
            setup_datadog_monitoring,
            business_metrics,
            metrics as dd_metrics,
            trace_function,
            track_metric
        )

        dd_result = setup_datadog_monitoring(app)
        logger.info(f"DataDog monitoring initialized: {dd_result}")

        if health_checker:
            async def check_redis():
                try:
                    from services.redis_service import redis_service
                    health = redis_service.check_health()
                    return health.get("status") == "healthy"
                except Exception as e:
                    logger.warning(f"Redis health check failed: {e}")
                    return False
            health_checker.register_check("redis", check_redis)

    except Exception as e:
        logger.warning(f"DataDog monitoring not fully initialized: {e}")


def configure_graceful_degradation(app: FastAPI, SessionLocal, health_checker):
    """Configure graceful degradation: startup health check for dependency tracking."""
    _startup_degradation_check = None

    try:
        from services.graceful_degradation import GracefulDegradation, ServiceLevel

        async def _startup_check():
            """Run once at startup to log initial degradation level."""
            _redis_client = None
            _db = None
            try:
                import redis as _redis_lib
                _redis_url = os.getenv("REDIS_URL")
                if _redis_url:
                    _redis_client = _redis_lib.from_url(_redis_url, socket_timeout=5)
            except Exception as _exc:  # noqa: BLE001
                pass
            try:
                _db = SessionLocal()
            except Exception as _exc:  # noqa: BLE001
                pass

            _breaker = None
            try:
                from services.circuit_breaker import CircuitBreaker
                _breaker = CircuitBreaker(name="anthropic_api", failure_threshold=5, recovery_timeout=30)
            except Exception as _exc:  # noqa: BLE001
                pass

            try:
                degradation = GracefulDegradation(redis_client=_redis_client, db=_db, circuit_breaker=_breaker)
                level = await degradation.determine_service_level()
                health = await degradation.check_service_health()
                unhealthy = [name for name, h in health.items() if not h.healthy]
                if level == ServiceLevel.FULL:
                    logger.info("Graceful degradation startup check: service_level=FULL (all dependencies healthy)")
                else:
                    logger.warning(
                        "Graceful degradation startup check: service_level=%s, unhealthy_services=%s",
                        level.value.upper(), unhealthy,
                    )
            except Exception as e:
                logger.warning(f"Graceful degradation startup check failed: {e}")
            finally:
                if _db:
                    try:
                        _db.close()
                    except Exception as _exc:  # noqa: BLE001
                        pass

        _startup_degradation_check = _startup_check

        if health_checker:
            async def check_degradation_level():
                _db = None
                try:
                    _db = SessionLocal()
                    degradation = GracefulDegradation(db=_db)
                    level = await degradation.determine_service_level()
                    return level == ServiceLevel.FULL
                except Exception as e:
                    logger.warning(f"Degradation health check failed: {e}")
                    return False
                finally:
                    if _db:
                        try:
                            _db.close()
                        except Exception as _exc:  # noqa: BLE001
                            pass

            health_checker.register_check("graceful_degradation", check_degradation_level)

        logger.info("Graceful degradation service registered (startup check + health checker)")
    except Exception as e:
        logger.warning(f"Graceful degradation service not loaded: {e}")

    return _startup_degradation_check


def validate_security_config():
    """Validate security configuration at startup."""
    try:
        from security_config import validate_security_config as _validate
        security_issues = _validate()
        if security_issues:
            for issue in security_issues:
                if issue.startswith("CRITICAL"):
                    logger.error(f"Security: {issue}")
                else:
                    logger.warning(f"Security: {issue}")
            logger.warning(f"Security validation: {len(security_issues)} issue(s) found")
        else:
            logger.info("Security configuration validated — all checks passed")
    except Exception as e:
        logger.warning(f"Security validation could not run: {e}")
