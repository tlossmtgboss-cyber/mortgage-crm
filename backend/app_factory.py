"""
Application Factory

Creates and configures the FastAPI application instance.
Orchestrates middleware, router registration, and lifespan events.

Usage:
    # main.py calls this to create the app
    from app_factory import create_app
    app = create_app(...)
"""

import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

logger = logging.getLogger(__name__)


def create_app(
    *,
    # All dependencies passed in from main.py to avoid circular imports
    engine,
    SessionLocal,
    get_db,
    get_current_user,
    get_current_user_flexible,
    oauth2_scheme,
    pwd_context,
    scheduler,
    openai_client,
    graceful_shutdown,
    SECRET_KEY: str,
    ENVIRONMENT: str,
    DATABASE_URL: str,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    get_cached,
    set_cached,
    clear_cache,
    log_ai_action_to_mission_control,
    update_ai_action_outcome,
    security_stats,
    User,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    All dependencies are passed in from main.py to preserve backward
    compatibility and avoid circular import issues.

    Returns:
        Configured FastAPI application.
    """
    _IS_PROD = ENVIRONMENT.lower() == "production"

    app = FastAPI(
        title="Agentic AI Mortgage CRM",
        description="Complete mortgage CRM with AI automation - All features implemented",
        version="4.0.0",
        docs_url=None if _IS_PROD else "/docs",
        redoc_url=None if _IS_PROD else "/redoc",
        openapi_url=None if _IS_PROD else "/openapi.json",
        redirect_slashes=False,  # Prevent HTTP redirects that cause mixed content errors
    )

    # ── Middleware ───────────────────────────────────────────────────────
    from middleware_config import (
        configure_middleware,
        configure_production_hardening,
        configure_datadog_monitoring,
        configure_graceful_degradation,
        validate_security_config,
    )

    configure_middleware(
        app,
        graceful_shutdown=graceful_shutdown,
        secret_key=SECRET_KEY,
        get_db=get_db,
        SessionLocal=SessionLocal,
        User=User,
        ENVIRONMENT=ENVIRONMENT,
    )

    # Signal handlers
    from utils.shutdown import install_signal_handlers
    install_signal_handlers(graceful_shutdown)

    # Production hardening
    structured_logger, health_checker = configure_production_hardening(app, engine, SessionLocal)

    # DataDog monitoring
    configure_datadog_monitoring(app, health_checker)

    # Graceful degradation
    _startup_degradation_check = configure_graceful_degradation(app, SessionLocal, health_checker)

    # Security config validation
    validate_security_config()

    # ── Static files ────────────────────────────────────────────────────
    static_dir = Path("static")
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    reports_dir = Path("static/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/reports", StaticFiles(directory=str(reports_dir), html=True), name="reports")

    uploads_sms_dir = Path("uploads/sms")
    uploads_sms_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads/sms", StaticFiles(directory=str(uploads_sms_dir)), name="uploads_sms")

    # ── Exception handlers ──────────────────────────────────────────────
    try:
        from utils.error_handling import register_exception_handlers
        register_exception_handlers(app)
    except Exception as e:
        logger.warning(f"Exception handlers not registered: {e}")

    # ── Routers ─────────────────────────────────────────────────────────
    from router_registry import register_routers

    register_routers(
        app,
        get_db=get_db,
        get_current_user=get_current_user,
        get_current_user_flexible=get_current_user_flexible,
        oauth2_scheme=oauth2_scheme,
        pwd_context=pwd_context,
        scheduler=scheduler,
        openai_client=openai_client,
        SECRET_KEY=SECRET_KEY,
        ENVIRONMENT=ENVIRONMENT,
        DATABASE_URL=DATABASE_URL,
        create_access_token=create_access_token,
        create_refresh_token=create_refresh_token,
        get_password_hash=get_password_hash,
        verify_password=verify_password,
        get_cached=get_cached,
        set_cached=set_cached,
        clear_cache=clear_cache,
        log_ai_action_to_mission_control=log_ai_action_to_mission_control,
        update_ai_action_outcome=update_ai_action_outcome,
        security_stats=security_stats,
        engine=engine,
        SessionLocal=SessionLocal,
    )

    # ── Lifespan events ─────────────────────────────────────────────────
    from app_lifespan import (
        register_startup_event,
        register_shutdown_event,
        register_seed_demo_endpoint,
    )

    register_startup_event(
        app, engine, scheduler, SessionLocal,
        _startup_degradation_check=_startup_degradation_check,
    )
    register_shutdown_event(app)
    register_seed_demo_endpoint(app, SECRET_KEY)

    # ── Re-export standalone utilities for backward compatibility ───────
    # These are set on the main module by main.py after create_app returns.

    return app
