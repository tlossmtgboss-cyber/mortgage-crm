"""
Inline legacy routes — "Register extracted route modules" section.

Extracted mechanically from `backend/routes/inline_legacy_routes.py`
(lines 201–322 in the pre-split file).

This module wires up a contiguous block of `register_*` calls for route groups
that have already been extracted into their own files. No route paths or
function bodies changed — only the surrounding wiring moved.

The caller (the orchestrator inside `register_inline_routes`) supplies the
FastAPI `app`, the standard auth/db dependencies, and a `deps` dict that
matches the original `kwargs` payload. Any exports produced by sub-modules
(currently `email_management_routes`) are returned so the orchestrator can
merge them into its own `_exported_functions` dict.
"""
import logging

logger = logging.getLogger(__name__)


def register_extracted_modules(
    app,
    get_db,
    get_current_user,
    get_current_user_flexible,
    *,
    SessionLocal,
    Lead,
    Loan,
    LoanStage,
    LoanTeamMember,
    ReferralPartner,
    MUMClient,
    filter_leads_by_permissions,
    kwargs,
):
    """Register the "extracted route modules" block.

    Returns a dict of exported functions (currently only email management
    exports anything) for the caller to merge into `_exported_functions`.
    """
    exported: dict = {}

    try:
        from routes.health_routes import register_health_routes
        register_health_routes(app, get_db, health_checker=kwargs.get('health_checker'), SessionLocal=SessionLocal)
        logger.info("✅ Health routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Health routes failed: {e}")

    try:
        from routes.db_migration_routes import register_migration_routes
        register_migration_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ Migration routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Migration routes failed: {e}")

    try:
        from routes.admin_ops_routes import register_admin_ops_routes
        register_admin_ops_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs)
        logger.info("✅ Admin ops routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Admin ops routes failed: {e}")

    try:
        from routes.email_management_routes import register_email_management_routes
        _email_exports = register_email_management_routes(app, get_db, get_current_user, **kwargs)
        if _email_exports:
            exported.update(_email_exports)
        logger.info("✅ Email management routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Email management routes failed: {e}")

    try:
        from routes.mum_activity_routes import register_mum_activity_routes
        register_mum_activity_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs)
        logger.info("✅ MUM/Activity routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ MUM/Activity routes failed: {e}")

    try:
        from routes.api_key_routes import register_api_key_routes
        register_api_key_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ API key routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ API key routes failed: {e}")

    try:
        from routes.cache_routes import register_cache_routes
        register_cache_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ Cache routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Cache routes failed: {e}")

    try:
        from routes.calculator_settings_routes import register_calculator_settings_routes
        register_calculator_settings_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ Calculator settings routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Calculator settings routes failed: {e}")

    try:
        from routes.scorecard_routes import register_scorecard_routes
        register_scorecard_routes(app, get_db, get_current_user, Lead=Lead, Loan=Loan, LoanStage=LoanStage, **kwargs)
        logger.info("✅ Scorecard routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Scorecard routes failed: {e}")

    try:
        from routes.backup_routes import register_backup_routes
        register_backup_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ Backup & DR routes loaded (enterprise readiness)")
    except Exception as e:
        logger.error(f"❌ Backup & DR routes failed: {e}")

    try:
        from routes.dr_routes import register_dr_routes
        register_dr_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ DR management routes loaded (failover, retention, degradation)")
    except Exception as e:
        logger.error(f"❌ DR management routes failed: {e}")

    try:
        from routes.gdpr_routes import register_gdpr_routes
        register_gdpr_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ GDPR/CCPA data deletion routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ GDPR routes failed: {e}")

    try:
        from routes.data_quality_routes import register_data_quality_routes
        register_data_quality_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ Data quality routes loaded (enterprise readiness 3.9 orphan detection)")
    except Exception as e:
        logger.error(f"❌ Data quality routes failed: {e}")

    try:
        from routes.scim_provisioning_routes import register_scim_provisioning_routes
        register_scim_provisioning_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ SCIM 2.0 provisioning, CSV import, MFA onboarding routes loaded (enterprise 5.11/5.12/5.15)")
    except Exception as e:
        logger.error(f"❌ SCIM provisioning routes failed: {e}")

    try:
        from routes.data_import_routes import register_data_import_routes
        register_data_import_routes(app, get_db, get_current_user, **kwargs)
        logger.info("✅ Data import routes loaded (CSV/Excel import, field mapping, rollback)")
    except Exception as e:
        logger.error(f"❌ Data import routes failed: {e}")

    try:
        from routes.search_routes import register_search_routes
        register_search_routes(app, get_db, get_current_user_flexible=get_current_user_flexible, Lead=Lead, Loan=Loan, LoanTeamMember=LoanTeamMember, ReferralPartner=ReferralPartner, MUMClient=MUMClient, filter_leads_by_permissions=filter_leads_by_permissions, **kwargs)
        logger.info("✅ Global search routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ Global search routes failed: {e}")

    try:
        from routes.ai_underwriter_routes import router as ai_underwriter_router
        app.include_router(ai_underwriter_router, prefix="/api/v1/ai-underwriter", tags=["AI Underwriter"])
        logger.info("✅ AI Underwriter routes loaded (extracted)")
    except Exception as e:
        logger.error(f"❌ AI Underwriter routes failed: {e}")

    return exported
