"""
Smart Docs Enterprise Route Registration (Wave 3)

Registers all enterprise-tier Smart Docs routes and middleware with the
FastAPI app.  Each module is imported lazily inside a try/except so a
single missing dependency (e.g. plaid-python) does not bring down the
entire application.

New route modules (all under /api/smart-docs):
- Config / Rules         /config/*        (enterprise-specific config routes)

Note: Plaid, AUS, eClosing, MISMO, Transcript, and Monitoring routes were
moved to smart_docs_v2_registration.py.  They are NOT re-registered here
to avoid duplicate router mounts.

Middleware:
- TraceIDMiddleware      — propagates X-Trace-ID across the request
- Smart Docs metrics     — latency + error-rate counters per route group
- PII log redaction      — strips SSN/CC/DOB from all log output

Migration:
- Creates 10 new tables for enterprise features

Usage in main.py (or from smart_docs_v2_registration.py):
    from routes.smart_docs_enterprise_registration import (
        register_smart_docs_enterprise_routes,
        register_smart_docs_middleware,
    )
    register_smart_docs_middleware(app)
    register_smart_docs_enterprise_routes(app)
"""

from __future__ import annotations

import logging
import time
from typing import List

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

ENTERPRISE_PREFIX = "/api/smart-docs"

# Module specs: (human label, import path, attribute name for the router,
#                extra prefix to append to ENTERPRISE_PREFIX or None)
_ROUTE_MODULES = [
    # NOTE: plaid, aus, eclosing, mismo, transcript, and monitoring routes are
    # already registered by smart_docs_v2_registration.py (which calls us).
    # They were previously listed here too, causing each router to be mounted
    # twice at the same /api/smart-docs prefix.  Removed to fix the duplicate.
    (
        "config",
        "routes.smart_docs_enterprise_config_routes",
        "router",
        None,
    ),
]


# ============================================================================
# Smart Docs Metrics Middleware
# ============================================================================

class SmartDocsMetricsMiddleware(BaseHTTPMiddleware):
    """
    Lightweight middleware that records per-request latency and error counts
    for Smart Docs enterprise endpoints.

    Metrics are accumulated in-memory and exposed via the /monitoring
    routes.  Only requests whose path starts with /api/smart-docs are
    tracked to avoid adding overhead to unrelated endpoints.
    """

    def __init__(self, app, *, path_prefix: str = ENTERPRISE_PREFIX):
        super().__init__(app)
        self.path_prefix = path_prefix
        # Simple in-memory counters — replaced by Prometheus/DataDog in prod
        self.request_count: int = 0
        self.error_count: int = 0
        self.total_duration_ms: float = 0.0

    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith(self.path_prefix):
            return await call_next(request)

        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            self.request_count += 1
            self.error_count += 1
            self.total_duration_ms += round(
                (time.monotonic() - start) * 1000, 2
            )
            raise

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        self.request_count += 1
        self.total_duration_ms += duration_ms
        if response.status_code >= 500:
            self.error_count += 1

        return response

    @property
    def avg_latency_ms(self) -> float:
        if self.request_count == 0:
            return 0.0
        return round(self.total_duration_ms / self.request_count, 2)


# ============================================================================
# Middleware Registration
# ============================================================================

def register_smart_docs_middleware(app: FastAPI) -> List[str]:
    """
    Register enterprise middleware in the correct order.

    Starlette processes middleware LIFO, so the *last* added middleware
    runs *first*.  We want:
        1. TraceID  (outermost — runs first)
        2. Metrics
        3. PII filter (innermost)

    So we add them in reverse: PII, Metrics, TraceID.

    Returns a list of successfully registered middleware names.
    """
    registered: List[str] = []

    # --- 3. PII log filter (install on root logger, not HTTP middleware) ---
    try:
        from middleware.pii_log_filter import install_pii_filter
        install_pii_filter()
        registered.append("pii_log_filter")
        logger.info("Smart Docs Enterprise: PII log redaction filter installed")
    except Exception as e:
        logger.warning(f"Smart Docs Enterprise: PII log filter not installed: {e}")

    # --- 2. Metrics middleware ---
    try:
        app.add_middleware(SmartDocsMetricsMiddleware, path_prefix=ENTERPRISE_PREFIX)
        registered.append("metrics")
        logger.info("Smart Docs Enterprise: metrics middleware registered")
    except Exception as e:
        logger.warning(f"Smart Docs Enterprise: metrics middleware failed: {e}")

    # --- 1. TraceID middleware (added last so it runs first) ---
    try:
        from middleware.trace_middleware import TraceIDMiddleware
        app.add_middleware(TraceIDMiddleware)
        registered.append("trace_id")
        logger.info("Smart Docs Enterprise: TraceID middleware registered")
    except Exception as e:
        logger.warning(f"Smart Docs Enterprise: TraceID middleware failed: {e}")

    logger.info(
        f"Smart Docs Enterprise: {len(registered)} middleware components "
        f"registered: {', '.join(registered)}"
    )
    return registered


# ============================================================================
# Route Registration
# ============================================================================

def register_smart_docs_enterprise_routes(app: FastAPI) -> List[str]:
    """
    Register all Wave 3 enterprise route modules.

    Each module is imported lazily.  If a module is not yet implemented or
    a third-party SDK is missing, the error is logged and startup continues.

    After routes, the enterprise database migration is executed so that any
    new tables are created before the first request arrives.

    Returns a list of successfully registered module labels.
    """
    import importlib

    registered: List[str] = []

    for label, module_path, attr_name, extra_prefix in _ROUTE_MODULES:
        try:
            mod = importlib.import_module(module_path)
            router = getattr(mod, attr_name)

            if extra_prefix:
                app.include_router(router, prefix=f"{ENTERPRISE_PREFIX}{extra_prefix}")
            else:
                app.include_router(router, prefix=ENTERPRISE_PREFIX)

            registered.append(label)
            logger.info(f"Smart Docs Enterprise: registered '{label}' routes")
        except ImportError as e:
            logger.info(
                f"Smart Docs Enterprise: '{label}' routes not available "
                f"(module not found: {e})"
            )
        except AttributeError as e:
            logger.warning(
                f"Smart Docs Enterprise: '{label}' module loaded but "
                f"router attribute '{attr_name}' missing: {e}"
            )
        except Exception as e:
            logger.warning(
                f"Smart Docs Enterprise: failed to register '{label}' routes: {e}"
            )

    logger.info(
        f"Smart Docs Enterprise: {len(registered)}/{len(_ROUTE_MODULES)} "
        f"route modules registered: {', '.join(registered) or '(none)'}"
    )

    # ---- Run enterprise database migration ----
    _run_enterprise_migration()

    return registered


# ============================================================================
# Database Migration Helper
# ============================================================================

def _run_enterprise_migration() -> None:
    """Execute the enterprise table migration, logging but not raising errors."""
    try:
        from migrations.smart_docs_enterprise_migration import run_migration
        from db import engine as db_engine

        result = run_migration(db_engine)
        if result and result.get("success"):
            table_count = len(result.get("tables_created", []))
            logger.info(
                f"Smart Docs Enterprise: migration complete "
                f"({table_count} tables ensured)"
            )
        else:
            logger.warning(
                "Smart Docs Enterprise: migration returned without success flag"
            )
    except ImportError as e:
        logger.info(
            f"Smart Docs Enterprise: migration module not available ({e})"
        )
    except Exception as e:
        logger.warning(f"Smart Docs Enterprise: migration failed: {e}")
