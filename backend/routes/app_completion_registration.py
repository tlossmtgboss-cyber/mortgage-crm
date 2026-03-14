"""
Application Completion Orchestrator (ACO) — Route Registration

Registers all ACO routes and runs database migrations on startup.
The ACO automatically scores submitted applications for completeness,
identifies missing fields and documents, and orchestrates borrower
outreach to resolve gaps before the file reaches underwriting.

Route modules:
- Application Completion (/api/smart-docs/app-complete/*)

Usage in main.py:
    from routes.app_completion_registration import register_app_completion_routes
    register_app_completion_routes(app)
"""

import logging

logger = logging.getLogger(__name__)


def register_app_completion_routes(app):
    """
    Register Application Completion Orchestrator routes and run migrations.

    Follows the same pattern as register_smart_docs_v2_routes:
    1. Run database migration (creates tables if not exist)
    2. Register route modules
    """
    prefix = "/api/smart-docs"
    registered = []

    # --- Database migration ---
    try:
        from db import engine as db_engine
        from migrations.add_app_completion_tables import run_migration
        run_migration(db_engine)
        logger.info("ACO: database migration complete")
    except Exception as e:
        logger.warning(f"ACO: migration skipped or failed: {e}")

    # --- Application Completion routes ---
    try:
        from routes.app_completion_routes import router as aco_router
        app.include_router(aco_router, prefix=prefix)
        registered.append("app-complete")
        logger.info("ACO: routes registered at /api/smart-docs/app-complete/*")
    except Exception as e:
        logger.warning(f"Failed to register ACO routes: {e}")

    logger.info(
        f"Application Completion Orchestrator: "
        f"registered {len(registered)} route module(s): {', '.join(registered)}"
    )

    return registered
