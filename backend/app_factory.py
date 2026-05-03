"""
Application Factory

Creates and configures the FastAPI application instance.
This is the entry point for the application, following the
factory pattern for better testability and modularity.

Usage:
    # Production (uvicorn)
    uvicorn app_factory:create_app --factory

    # Or with the created app
    uvicorn app_factory:app

    # Testing
    from app_factory import create_app
    app = create_app(testing=True)
"""

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


def create_app(
    testing: bool = False,
    skip_middleware: bool = False,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        testing: If True, use test configuration
        skip_middleware: If True, skip middleware registration (useful for testing)

    Returns:
        Configured FastAPI application
    """
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()

    # Configure logging first
    _configure_logging()

    # Create FastAPI app
    app = FastAPI(
        title="Agentic AI Mortgage CRM",
        description="Complete mortgage CRM with AI automation",
        version="4.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        redirect_slashes=False,  # Prevent HTTP redirects that cause mixed content errors
    )

    # Get dependencies
    from database import engine, SessionLocal, get_db
    from config import settings, is_production

    # Get secret key (with development fallback)
    secret_key = _get_secret_key()

    # Configure middleware (unless skipped for testing)
    if not skip_middleware:
        _configure_middleware(app, secret_key, get_db, SessionLocal)

    # Mount static files
    _mount_static_files(app)

    # Include routers
    _include_routers(app)

    # Register exception handlers
    _register_exception_handlers(app)

    # Initialize background services
    if not testing:
        _initialize_services(app, engine)

    logger.info("Application factory: FastAPI app created successfully")
    return app


def _configure_logging() -> None:
    """Configure application logging."""
    is_production = (
        os.getenv("RAILWAY_ENVIRONMENT") or
        os.getenv("ENVIRONMENT") == "production"
    )
    log_level = logging.WARNING if is_production else logging.INFO

    logging.basicConfig(
        level=log_level,
        format='%(levelname)s:%(name)s:%(message)s'
    )

    # Suppress noisy loggers in production
    if is_production:
        for noisy_logger in [
            "apscheduler", "apscheduler.scheduler", "apscheduler.executors",
            "uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"
        ]:
            logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def _get_secret_key() -> str:
    """
    Get secret key from environment.

    Raises ValueError in production if not set.
    Generates a random key for development.
    """
    import secrets as secrets_module

    secret_key = os.getenv("SECRET_KEY")
    environment = os.getenv("ENVIRONMENT", "development")

    if environment == "production" and not secret_key:
        raise ValueError(
            "SECRET_KEY environment variable is required in production. "
            "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    if not secret_key:
        logger.warning("SECRET_KEY not set - using generated key for development only")
        return secrets_module.token_hex(32)

    return secret_key


def _configure_middleware(
    app: FastAPI,
    secret_key: str,
    get_db,
    session_local,
) -> None:
    """Configure all middleware for the application."""
    try:
        from middleware.stack import (
            configure_middleware,
            configure_production_hardening,
            configure_datadog_monitoring,
        )

        # Get User model for tenant context
        # Import here to avoid circular imports
        try:
            from models import User
        except ImportError:
            # Fallback - User might be defined in main.py
            User = None

        # Configure security and application middleware
        if User:
            configure_middleware(
                app=app,
                secret_key=secret_key,
                get_db=get_db,
                session_local=session_local,
                user_model=User,
                environment=os.getenv("ENVIRONMENT", "development"),
            )

        # Configure production hardening
        from database import engine
        structured_logger, health_checker = configure_production_hardening(
            app=app,
            engine=engine,
            session_local=session_local,
        )

        # Configure DataDog monitoring
        configure_datadog_monitoring(
            app=app,
            health_checker=health_checker,
        )

    except Exception as e:
        logger.warning(f"Middleware configuration incomplete: {e}")
        # Fallback to basic CORS with explicit origins (never wildcard)
        from fastapi.middleware.cors import CORSMiddleware
        _fallback_origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "https://perenniaai.com",
            "https://www.perenniaai.com",
            "https://app.perenniaai.com",
            "https://api.perenniaai.com",
        ]
        # Add any Railway deployment URLs
        _railway_url = os.getenv("RAILWAY_PUBLIC_DOMAIN")
        if _railway_url:
            _fallback_origins.append(f"https://{_railway_url}")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_fallback_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
        )


def _mount_static_files(app: FastAPI) -> None:
    """Mount static files directory."""
    static_dir = Path("static")
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"Static files mounted at /static from {static_dir.absolute()}")


def _include_routers(app: FastAPI) -> None:
    """
    Include all API routers.

    Note: During migration, routers are still defined in main.py.
    This function will be expanded as routes are extracted.
    """
    # Health check router
    try:
        from api.health import get_health_router
        from database import SessionLocal, get_db
        from config import is_production

        health_router = get_health_router(
            get_db=get_db,
            SessionLocal=SessionLocal,
            is_production_func=is_production,
        )
        app.include_router(health_router)
        logger.info("Health check router included")
    except Exception as e:
        logger.warning(f"Health router not loaded: {e}")

    # Additional routers will be added here as they are extracted from main.py
    # Example:
    # from api.v1.auth import router as auth_router
    # app.include_router(auth_router, prefix="/api/v1")


def _register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "type": type(exc).__name__,
            },
        )


def _initialize_services(app: FastAPI, engine) -> None:
    """
    Initialize background services and schedulers.

    Note: During migration, services are still initialized in main.py.
    This function will be expanded as services are extracted.
    """
    # Create database tables if needed
    try:
        from database import Base
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified/created")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")


# Create default app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app_factory:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENVIRONMENT") != "production",
    )
