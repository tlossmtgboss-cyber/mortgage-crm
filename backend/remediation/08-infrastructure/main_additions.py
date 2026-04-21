"""
08-infrastructure/main_additions.py

The shape of the new main.py after remediation. Keep this as reference — merge
into your existing main.py manually since main.py is 4,000+ lines and needs
careful migration rather than wholesale replacement.

Key changes from the previous main.py:
  - Lifespan hook runs startup validation (fails fast on bad config)
  - AuditMiddleware registered before route inclusion
  - SecurityHeadersMiddleware registered on app creation
  - Rate limiter registered with exception handler
  - CORS locked down (no more '*' origin)
  - Sync DB queries in auth paths deleted — use app.auth.dependencies instead
  - Legacy JWT code paths deleted — use app.auth.tokens
  - /health and /health/ready replace any ad-hoc healthcheck endpoints
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.middleware.audit import AuditMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.security.startup import validate_startup_config

# Routers
from app.auth.routes import router as auth_router
from app.routes.health import router as health_router
# ... plus all your existing feature routers

logger = logging.getLogger(__name__)

IS_PROD = os.environ.get("ENV") == "production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: validate config + prewarm critical resources. Shutdown: clean up."""
    logger.info("Starting Perennia AI backend")
    await validate_startup_config()
    logger.info("Startup validation passed — ready to serve traffic")
    yield
    logger.info("Shutting down")
    # Dispose DB engine
    from app.core.db import engine
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Perennia AI",
        docs_url="/docs" if not IS_PROD else None,  # no public docs in prod
        redoc_url="/redoc" if not IS_PROD else None,
        openapi_url="/openapi.json" if not IS_PROD else None,
        lifespan=lifespan,
    )

    # --- Middleware (order matters: last added runs first on request) -------

    # Security headers — outermost, runs on every response
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS — locked down. No wildcards.
    allowed_origins = [
        origin.strip()
        for origin in os.environ.get(
            "CORS_ALLOWED_ORIGINS",
            "https://app.perennia.ai,https://portal.perennia.ai",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,  # required for cookie auth
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],
        max_age=600,
    )

    # Audit — catches mutating requests, writes breadcrumbs
    app.add_middleware(AuditMiddleware)

    # --- Rate limiter -------------------------------------------------------
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # --- Routes -------------------------------------------------------------
    app.include_router(health_router)
    app.include_router(auth_router)
    # ... include all your existing feature routers here

    return app


app = create_app()
