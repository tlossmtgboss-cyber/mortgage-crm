"""
Smart Docs V2 Route Registration

Registers all new Smart Docs v2 API routers with the FastAPI app.
Call register_smart_docs_v2_routes(app) from main.py.

New route modules:
- E-Signature (/api/v1/esign/*) — has its own absolute prefix
- Document Intelligence (/api/smart-docs/doc-intel/*)
- Income Calculation (/api/smart-docs/income/*)
- Follow-up & Scheduling (/api/smart-docs/followup/*)
- Document Security (/api/smart-docs/doc-security/*)
- Document Review Queue (/api/smart-docs/doc-review/*)
- Bank Statement Analysis (/api/smart-docs/bank-analysis/*)
- Document Analytics (/api/smart-docs/doc-analytics/*)
- Borrower Portal (/api/smart-docs/portal/docs/*)
"""

import logging

logger = logging.getLogger(__name__)


def register_smart_docs_v2_routes(app):
    """
    Register all Smart Docs v2 API routes.

    Call this from main.py after the existing route registration.

    Usage in main.py:
        from routes.smart_docs_v2_registration import register_smart_docs_v2_routes
        register_smart_docs_v2_routes(app)
    """
    prefix = "/api/smart-docs"
    registered = []

    # E-Signature routes
    # Note: esign router defines its own prefix="/api/v1/esign", so we mount
    # it without an additional prefix to avoid double-prefixing.
    try:
        from routes.smart_docs_esign_routes import router as esign_router
        app.include_router(esign_router)
        registered.append("esign")
    except Exception as e:
        logger.warning(f"Failed to register e-signature routes: {e}")

    # Document Intelligence routes
    try:
        from routes.smart_docs_intelligence_routes import router as intel_router
        app.include_router(intel_router, prefix=prefix)
        registered.append("intelligence")
    except Exception as e:
        logger.warning(f"Failed to register intelligence routes: {e}")

    # Income Calculation routes
    try:
        from routes.smart_docs_income_routes import router as income_router
        app.include_router(income_router, prefix=prefix)
        registered.append("income")
    except Exception as e:
        logger.warning(f"Failed to register income routes: {e}")

    # Follow-up & Scheduling routes
    # Note: also registered via smart_docs_routes.py under /api/v1/smart-docs;
    # this mounts under /api/smart-docs for the v2 API surface.
    try:
        from routes.smart_docs_followup_routes import router as followup_router
        app.include_router(followup_router, prefix=prefix)
        registered.append("followup")
    except Exception as e:
        logger.warning(f"Failed to register follow-up routes: {e}")

    # Document Security routes
    try:
        from routes.smart_docs_security_routes import router as security_router
        app.include_router(security_router, prefix=prefix)
        registered.append("security")
    except Exception as e:
        logger.warning(f"Failed to register security routes: {e}")

    # Document Review Queue routes
    # Note: also registered via smart_docs_routes.py under /api/v1/smart-docs;
    # this mounts under /api/smart-docs for the v2 API surface.
    try:
        from routes.smart_docs_review_routes import router as review_router
        app.include_router(review_router, prefix=prefix)
        registered.append("review")
    except Exception as e:
        logger.warning(f"Failed to register review routes: {e}")

    # Bank Statement Analysis routes
    try:
        from routes.smart_docs_bank_analysis_routes import router as bank_router
        app.include_router(bank_router, prefix=prefix)
        registered.append("bank-analysis")
    except Exception as e:
        logger.warning(f"Failed to register bank analysis routes: {e}")

    # Document Analytics routes
    # Note: also registered via smart_docs_routes.py under /api/v1/smart-docs;
    # this mounts under /api/smart-docs for the v2 API surface.
    try:
        from routes.smart_docs_analytics_routes import router as analytics_router
        app.include_router(analytics_router, prefix=prefix)
        registered.append("analytics")
    except Exception as e:
        logger.warning(f"Failed to register analytics routes: {e}")

    # Borrower Portal Document routes
    try:
        from routes.smart_docs_portal_routes import router as portal_router
        app.include_router(portal_router, prefix=prefix)
        registered.append("portal")
    except Exception as e:
        logger.warning(f"Failed to register portal routes: {e}")

    logger.info(f"Smart Docs V2: registered {len(registered)} route modules: {', '.join(registered)}")

    # Run database migration on startup (creates tables if not exist)
    try:
        from migrations.smart_docs_v2_migration import run_migration
        from db import engine as db_engine
        run_migration(db_engine)
        logger.info("Smart Docs V2: database migration complete")
    except Exception as e:
        logger.warning(f"Smart Docs V2: migration skipped or failed: {e}")

    return registered


def register_smart_docs_cron_tasks(scheduler):
    """
    Register Smart Docs cron tasks with the application scheduler.

    Call this if using APScheduler or similar.

    Usage:
        from routes.smart_docs_v2_registration import register_smart_docs_cron_tasks
        register_smart_docs_cron_tasks(scheduler)
    """
    try:
        from tasks.smart_docs_cron_tasks import SMART_DOCS_CRON_TASKS

        for task_name, config in SMART_DOCS_CRON_TASKS.items():
            try:
                # Parse cron expression
                parts = config["schedule"].split()
                if len(parts) == 5:
                    scheduler.add_job(
                        config["func"],
                        trigger='cron',
                        minute=parts[0],
                        hour=parts[1],
                        day=parts[2],
                        month=parts[3],
                        day_of_week=parts[4],
                        id=f"smart_docs_{task_name}",
                        name=config["description"],
                        replace_existing=True,
                    )
                    logger.info(f"Registered cron task: {task_name}")
            except Exception as e:
                logger.warning(f"Failed to register cron task {task_name}: {e}")

        logger.info(f"Smart Docs V2: registered {len(SMART_DOCS_CRON_TASKS)} cron tasks")
    except Exception as e:
        logger.warning(f"Failed to register cron tasks: {e}")
