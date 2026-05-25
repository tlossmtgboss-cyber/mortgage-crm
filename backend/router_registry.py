"""
Router Registry

Registers all API routers with the FastAPI application, grouped by domain.
Extracted from main.py — structural move only, no logic changes.
"""

import logging
import os

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def register_routers(
    app: FastAPI,
    *,
    get_db,
    get_current_user,
    get_current_user_flexible,
    oauth2_scheme,
    pwd_context,
    scheduler,
    openai_client,
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
    engine,
    SessionLocal,
):
    """Register all API routers grouped by domain."""

    _register_enterprise_routes(app, get_db, get_current_user, get_current_user_flexible)
    _register_smart_docs_routes(app)
    _register_compliance_routes(app, get_db, get_current_user)
    _register_voice_ai_routes(app)
    _register_borrower_routes(app, get_db, get_current_user)
    _register_scheduler_routes(app, get_db, get_current_user, get_current_user_flexible)
    _register_mobile_routes(app, get_db, get_current_user)
    _register_api_v2_routes(app)
    _register_branding_routes(app, get_db, get_current_user_flexible)
    _register_aggregate_routes(
        app, get_db, get_current_user, get_current_user_flexible,
        oauth2_scheme, pwd_context, scheduler, log_ai_action_to_mission_control,
        update_ai_action_outcome,
    )
    _register_core_crm_routes(app, get_db, get_current_user, get_current_user_flexible)
    _register_admin_routes(app, get_db, get_current_user, get_current_user_flexible)
    _register_infrastructure_routes(app, get_db, get_current_user)
    _register_inline_legacy_routes(
        app, get_db, get_current_user, get_current_user_flexible,
        scheduler, openai_client, pwd_context, SECRET_KEY, ENVIRONMENT,
        create_access_token, create_refresh_token, get_password_hash,
        verify_password, get_cached, set_cached, clear_cache, oauth2_scheme,
        log_ai_action_to_mission_control, update_ai_action_outcome,
        DATABASE_URL, security_stats,
    )
    _register_post_legacy_routes(
        app, get_db, get_current_user, get_current_user_flexible,
        pwd_context, get_password_hash, create_access_token, DATABASE_URL,
    )
    _register_new_routes(app, get_db, get_current_user, get_current_user_flexible)
    _register_late_routes(app, get_db, get_current_user, engine, SessionLocal)


def _register_enterprise_routes(app, get_db, get_current_user, get_current_user_flexible):
    """Enterprise readiness, API gateway, tenant lifecycle, billing, legal, regulatory."""

    # App version check routes (no-auth version gate)
    try:
        from routes.app_version_routes import register_app_version_routes
        register_app_version_routes(app=app)
        logger.info("App version check routes loaded (no-auth version gate)")
    except Exception as e:
        logger.error(f"App version check routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # API Gateway routes
    try:
        from routes.api_gateway_routes import register_api_gateway_routes
        register_api_gateway_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("API Gateway routes loaded (Domain 11: API Key CRUD, Webhooks, Rate Limiting)")
    except Exception as e:
        logger.error(f"API Gateway routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Tenant lifecycle routes
    try:
        from routes.tenant_lifecycle_routes import register_tenant_lifecycle_routes
        register_tenant_lifecycle_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Tenant lifecycle routes loaded (signup, provision, export, suspend, hard-delete)")
    except Exception as e:
        logger.error(f"Tenant lifecycle routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Billing admin routes
    try:
        from routes.billing_admin_routes import register_billing_admin_routes
        register_billing_admin_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Billing admin routes loaded (Stripe, subscriptions, invoices)")
    except Exception as e:
        logger.error(f"Billing admin routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Email template routes
    try:
        from routes.email_template_routes import register_email_template_routes
        register_email_template_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Email template routes loaded (per-tenant template editor)")
    except Exception as e:
        logger.error(f"Email template routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Legal document routes
    try:
        from routes.legal_document_routes import register_legal_document_routes
        register_legal_document_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Legal document routes loaded (T&C, Privacy Policy management)")
    except Exception as e:
        logger.error(f"Legal document routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Regulatory report routes
    try:
        from routes.regulatory_report_routes import register_regulatory_report_routes
        register_regulatory_report_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Regulatory report routes loaded (HMDA LAR, state filings)")
    except Exception as e:
        logger.error(f"Regulatory report routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Report export & performance monitoring routes
    try:
        from routes.report_export_routes import register_report_export_routes
        register_report_export_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Report export & performance monitoring routes loaded (PDF, Excel, SLA compliance, scheduled delivery)")
    except Exception as e:
        logger.error(f"Report export routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Audit report share routes
    try:
        from routes.audit_report_routes import register_audit_report_routes
        register_audit_report_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Audit report share routes loaded (public HTML report pages)")
    except Exception as e:
        logger.error(f"Audit report share routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # API developer experience routes
    try:
        from routes.api_developer_routes import register_api_developer_routes
        register_api_developer_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("API developer routes loaded (changelog, SDK, Postman, sandbox, webhooks)")
    except Exception as e:
        logger.error(f"API developer routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Enterprise readiness routes
    try:
        from routes.enterprise_readiness_routes import register_enterprise_readiness_routes
        register_enterprise_readiness_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Enterprise readiness routes loaded (data quality, security, onboarding, white-label, import templates)")
    except Exception as e:
        logger.error(f"Enterprise readiness routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Ops Manager routes
    try:
        from routes.ops_manager_routes import register_ops_manager_routes
        register_ops_manager_routes(
            app=app, get_db=get_db, get_current_user=get_current_user_flexible
        )
        logger.info("Ops Manager routes loaded (sweep, summary, history)")
    except Exception as e:
        logger.error(f"Ops Manager routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Encompass LOS integration routes
    try:
        from routes.encompass_integration_routes import register_encompass_integration_routes
        register_encompass_integration_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Encompass LOS integration routes loaded (connect, sync, search, import)")
    except Exception as e:
        logger.error(f"Encompass integration routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # GDPR / CCPA data privacy routes
    try:
        from routes.gdpr_routes import register_gdpr_routes
        register_gdpr_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("GDPR/CCPA data privacy routes loaded (export, deletion, DSAR)")
    except Exception as e:
        logger.error(f"GDPR routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Enterprise documentation portal routes
    try:
        from routes.enterprise_documentation_routes import register_enterprise_documentation_routes
        register_enterprise_documentation_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Enterprise Documentation Portal routes loaded (content, search, analytics)")
    except Exception as e:
        logger.error(f"Enterprise Documentation Portal routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    try:
        from routes.enterprise_documentation_admin_routes import register_content_management_routes
        register_content_management_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Enterprise Documentation Admin routes loaded (content management)")
    except Exception as e:
        logger.error(f"Enterprise Documentation Admin routes failed to load: {e}")
        import traceback
        traceback.print_exc()


def _register_smart_docs_routes(app):
    """Smart Docs V2 routes."""
    try:
        from routes.smart_docs_v2_registration import register_smart_docs_v2_routes
        register_smart_docs_v2_routes(app=app)
        logger.info("Smart Docs V2 routes loaded (intelligence, income, review, followup, security, bank-analysis, analytics, portal, esign)")
    except Exception as e:
        logger.error(f"Smart Docs V2 routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Cadence sequence-level endpoints (pause/resume/cancel by execution ID)
    # Frontend expects: POST /api/v1/cadence/sequences/{id}/pause|resume|cancel
    try:
        from routes.smart_docs_cadence_routes import sequences_router
        app.include_router(sequences_router, prefix="/api/v1", tags=["cadence-sequences"])
        logger.info("Cadence sequence routes loaded (pause, resume, cancel)")
    except Exception as e:
        logger.error(f"Cadence sequence routes failed to load: {e}")
        import traceback
        traceback.print_exc()


def _register_compliance_routes(app, get_db, get_current_user):
    """SOC 2, TCPA, credit monitoring, content governance, scheduling intelligence."""

    # SOC 2 Type II compliance routes
    try:
        from soc2_compliance.api.router import soc2_router
        app.include_router(soc2_router, prefix="/api/v1/compliance", tags=["SOC 2 Compliance"])
        logger.info("SOC 2 compliance routes loaded (audit, incidents, dashboard)")
    except Exception as e:
        logger.error(f"SOC 2 compliance routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # TCPA Consent Management
    try:
        from routes.tcpa_consent_routes import router as tcpa_consent_router
        app.include_router(tcpa_consent_router, tags=["TCPA Compliance"])
        logger.info("TCPA Consent routes loaded")
    except Exception as e:
        logger.warning(f"TCPA Consent routes skipped: {e}")

    # Unified Consent Audit Trail
    try:
        from routes.tcpa_consent_routes import consent_audit_router
        app.include_router(consent_audit_router, tags=["Consent Audit"])
        logger.info("Consent Audit routes loaded")
    except Exception as e:
        logger.warning(f"Consent Audit routes skipped: {e}")

    # Credit Bureau Monitoring
    try:
        from routes.credit_monitoring_routes import router as credit_monitoring_router
        app.include_router(credit_monitoring_router, tags=["Credit Monitoring"])
        logger.info("Credit Monitoring routes loaded")
    except Exception as e:
        logger.warning(f"Credit Monitoring routes skipped: {e}")

    # Content Governance
    try:
        from routes.content_governance_routes import router as content_governance_router
        app.include_router(content_governance_router, tags=["Content Governance"])
        logger.info("Content Governance routes loaded")
    except Exception as e:
        logger.warning(f"Content Governance routes skipped: {e}")

    # Scheduling Intelligence
    try:
        from routes.scheduling_intelligence_routes import router as scheduling_intelligence_router
        app.include_router(scheduling_intelligence_router, tags=["Scheduling Intelligence"])
        logger.info("Scheduling Intelligence routes loaded")
    except Exception as e:
        logger.warning(f"Scheduling Intelligence routes skipped: {e}")

    # SOC 2 Compliance Admin Dashboard
    try:
        from routes.soc2_compliance_routes import router as soc2_admin_router
        app.include_router(soc2_admin_router, tags=["SOC 2 Admin"])
        logger.info("SOC 2 Compliance admin routes loaded")
    except Exception as e:
        logger.warning(f"SOC 2 Compliance admin routes skipped: {e}")

    # SOC 2 Security Training Tracking
    try:
        from routes.security_training_routes import router as security_training_router
        app.include_router(security_training_router, tags=["SOC 2 Training"])
        logger.info("Security training routes loaded")
    except Exception as e:
        logger.warning(f"Security training routes skipped: {e}")


def _register_voice_ai_routes(app):
    """Voice AI receptionist, call queues, Aria chat."""

    try:
        from routes.voice_ai_receptionist_routes import webhook_router, sms_router, debug_router
        app.include_router(webhook_router, tags=["Voice Webhooks"])
        app.include_router(sms_router, tags=["SMS Messaging"])
        app.include_router(debug_router, tags=["Debug"])
        logger.info("Voice AI Receptionist sub-routes loaded (webhooks, SMS, debug)")
    except Exception as e:
        logger.error(f"Voice AI Receptionist routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    try:
        from ai_receptionist_dashboard_routes import router as ai_receptionist_dashboard_router
        app.include_router(ai_receptionist_dashboard_router, tags=["AI Receptionist Dashboard"])
        logger.info("AI Receptionist Dashboard routes loaded")
    except Exception as e:
        logger.error(f"AI Receptionist Dashboard routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Call queue routes
    try:
        from routes.call_queue_routes import router as call_queue_router
        app.include_router(call_queue_router, tags=["Call Queues"])
        logger.info("Call Queue routes loaded")
    except Exception as e:
        logger.error(f"Call Queue routes failed to load: {e}")
        import traceback
        traceback.print_exc()


def _register_borrower_routes(app, get_db, get_current_user):
    """Borrower application, POS consent, prospect re-engagement."""

    # Legacy borrower_application_routes deregistered — 20+ endpoints with no
    # frontend consumers, replaced by routes/pos/ (new Digital 1003 flow).
    # File retained for reference but no longer mounted.

    try:
        from routes.pos_consent_routes import router as pos_consent_router
        app.include_router(pos_consent_router, tags=["POS Consent"])
        logger.info("POS Consent routes loaded")
    except Exception as e:
        logger.warning(f"POS Consent routes failed to load: {e}")

    # AI Prospect Re-Engagement routes
    try:
        from routes.prospect_reengagement_routes import router as prospect_reengagement_router
        app.include_router(prospect_reengagement_router, tags=["Prospect Re-Engagement"])
        logger.info("AI Prospect Re-Engagement routes loaded")

        try:
            from database.models.ai_prospect_conversation import create_tables_if_needed
            from db import engine
            create_tables_if_needed(engine)
        except Exception as e:
            logger.warning(f"AI Re-Engagement table creation skipped: {e}")
    except Exception as e:
        logger.error(f"AI Prospect Re-Engagement routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Booking branding routes
    try:
        from routes.booking_branding_routes import register_booking_branding_routes
        register_booking_branding_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("Booking branding routes loaded (public org pages, admin branding)")
    except Exception as e:
        logger.warning(f"Booking branding routes skipped: {e}")


def _register_scheduler_routes(app, get_db, get_current_user, get_current_user_flexible):
    """Scheduler enhancement routes."""

    # Pipeline appointment trigger routes
    try:
        from routes.pipeline_appointment_routes import register_pipeline_appointment_routes
        register_pipeline_appointment_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Pipeline appointment trigger routes loaded")
    except Exception as e:
        logger.warning(f"Pipeline appointment trigger routes skipped: {e}")

    # Pipeline alerts routes
    try:
        from routes.pipeline_alerts_routes import router as pipeline_alerts_router
        app.include_router(pipeline_alerts_router, tags=["Pipeline Alerts"])
        logger.info("Pipeline alerts routes loaded")
    except Exception as e:
        logger.warning(f"Pipeline alerts routes skipped: {e}")

    # Audit trail routes (scheduler compliance logging)
    try:
        from routes.audit_routes import router as audit_router, set_dependencies as audit_set_deps
        audit_set_deps(get_db, get_current_user, {})
        app.include_router(audit_router, prefix="/api/v1/scheduler", tags=["Scheduler Audit"])
        logger.info("Scheduler audit routes loaded")
    except Exception as e:
        logger.warning(f"Scheduler audit routes skipped: {e}")

    # Scheduling rules engine routes
    try:
        from routes.scheduler_rules_routes import router as rules_router, set_dependencies as rules_set_deps
        rules_set_deps(get_db, get_current_user, {})
        app.include_router(rules_router, prefix="/api/v1/scheduler", tags=["Scheduling Rules"])
        logger.info("Scheduling rules routes loaded")
    except Exception as e:
        logger.warning(f"Scheduling rules routes skipped: {e}")

    # Slot hold routes
    try:
        from routes.slot_hold_routes import router as slot_hold_router, set_dependencies as hold_set_deps
        hold_set_deps(get_db, get_current_user, {})
        app.include_router(slot_hold_router, prefix="/api/v1/scheduler", tags=["Slot Holds"])
        logger.info("Slot hold routes loaded")
    except Exception as e:
        logger.warning(f"Slot hold routes skipped: {e}")

    # Scheduling optimizer routes
    try:
        from routes.scheduling_optimizer_routes import router as optimizer_router, set_dependencies as opt_set_deps
        opt_set_deps(get_db, get_current_user)
        app.include_router(optimizer_router, prefix="/api/v1/scheduler", tags=["Scheduling Optimizer"])
        logger.info("Scheduling optimizer routes loaded")
    except Exception as e:
        logger.warning(f"Scheduling optimizer routes skipped: {e}")

    # AI outbound calling routes
    try:
        from routes.ai_outbound_routes import router as ai_outbound_router
        app.include_router(ai_outbound_router, tags=["AI Outbound Calling"])
        logger.info("AI outbound calling routes loaded")
    except Exception as e:
        logger.warning(f"AI outbound calling routes skipped: {e}")

    # SMS scheduler webhook routes
    try:
        from routes.sms_scheduler_webhook import router as sms_sched_router, set_dependencies as sms_set_deps
        sms_set_deps(get_db, {})
        app.include_router(sms_sched_router, prefix="/api/v1/scheduler", tags=["Scheduler SMS"])
        logger.info("SMS scheduler webhook routes loaded")
    except Exception as e:
        logger.warning(f"SMS scheduler webhook routes skipped: {e}")

    # No-show recovery opt-out routes
    try:
        from routes.recovery_opt_out_routes import router as recovery_router, set_dependencies as recovery_set_deps
        recovery_set_deps(get_current_user_func=get_current_user)
        app.include_router(recovery_router, prefix="/api/v1/scheduler", tags=["No-Show Recovery"])
        logger.info("Recovery opt-out routes loaded")
    except Exception as e:
        logger.warning(f"Recovery opt-out routes skipped: {e}")

    # Scheduler analytics routes
    try:
        from routes.scheduler_analytics_routes import router as sched_analytics_router
        app.include_router(sched_analytics_router, tags=["Scheduler Analytics"])
        logger.info("Scheduler analytics routes loaded")
    except Exception as e:
        logger.warning(f"Scheduler analytics routes skipped: {e}")

    # Capacity dashboard routes
    try:
        from routes.capacity_dashboard_routes import register_capacity_dashboard_routes
        register_capacity_dashboard_routes(app, get_current_user, {})
        logger.info("Capacity dashboard routes loaded")
    except Exception as e:
        logger.warning(f"Capacity dashboard routes skipped: {e}")


def _register_mobile_routes(app, get_db, get_current_user):
    """Mobile-specific routes."""

    # Mobile tasks routes
    try:
        from routes.mobile_tasks_routes import router as mobile_tasks_router
        app.include_router(mobile_tasks_router, tags=["Mobile Tasks"])
        logger.info("Mobile tasks routes loaded")
    except Exception as e:
        logger.warning(f"Mobile tasks routes not loaded: {e}")

    # Task snooze routes
    try:
        from routes.task_snooze_routes import router as task_snooze_router
        app.include_router(task_snooze_router, tags=["Tasks"])
        logger.info("Task snooze routes loaded")
    except Exception as e:
        logger.warning(f"Task snooze routes not loaded: {e}")

    # Mobile analytics routes
    try:
        from routes.mobile_analytics_routes import router as mobile_analytics_router
        app.include_router(mobile_analytics_router, tags=["Mobile Analytics"])
        logger.info("Mobile analytics routes loaded")
    except Exception as e:
        logger.warning(f"Mobile analytics routes not loaded: {e}")

    # Mobile dashboard routes
    try:
        from routes.mobile_dashboard_routes import router as mobile_dashboard_router
        app.include_router(mobile_dashboard_router, tags=["Mobile Dashboard"])
        logger.info("Mobile dashboard routes loaded")
    except Exception as e:
        logger.warning(f"Mobile dashboard routes not loaded: {e}")

    # Mobile notification routes
    try:
        from routes.mobile_notification_routes import router as mobile_notification_router
        app.include_router(mobile_notification_router, tags=["Mobile Notifications"])
        logger.info("Mobile notification routes loaded")
    except Exception as e:
        logger.warning(f"Mobile notification routes not loaded: {e}")

    # Mobile sync routes
    try:
        from routes.mobile_sync_routes import router as mobile_sync_router
        app.include_router(mobile_sync_router, tags=["Mobile Sync"])
        logger.info("Mobile sync routes loaded")
    except Exception as e:
        logger.warning(f"Mobile sync routes not loaded: {e}")

    # Voice profile routes
    try:
        from routes.voice_profile_routes import router as voice_profile_router
        app.include_router(voice_profile_router, tags=["Voice Profile"])
        logger.info("Voice profile routes loaded")
    except Exception as e:
        logger.warning(f"Voice profile routes not loaded: {e}")

    try:
        from mobile_voice_routes import router as mobile_voice_router
        app.include_router(mobile_voice_router, tags=["Mobile Voice"])
        logger.info("Mobile voice routes loaded (ElevenLabs TTS)")
    except Exception as e:
        logger.warning(f"Mobile voice routes not loaded: {e}")

    # LiveKit voice routes
    try:
        from routes.livekit_routes import router as livekit_router
        app.include_router(livekit_router, tags=["LiveKit Voice"])
        logger.info("LiveKit voice routes loaded")
    except Exception as e:
        logger.warning(f"LiveKit voice routes not loaded: {e}")

    # Aria chat routes
    try:
        from routes.aria_chat_routes import router as aria_chat_router
        app.include_router(aria_chat_router, tags=["Aria Chat"])
        logger.info("Aria chat routes loaded")
    except Exception as e:
        logger.warning(f"Aria chat routes not loaded: {e}")

    try:
        from routes.aria_analytics_routes import router as aria_analytics_router
        app.include_router(aria_analytics_router, tags=["Aria Analytics"])
        logger.info("Aria analytics routes loaded")
    except Exception as e:
        logger.warning(f"Aria analytics routes not loaded: {e}")

    # Aria internal routes
    for _mod, _label in [
        ("routes.internal.aria_tool_routes", "Aria internal tool"),
        ("routes.internal.aria_call_routes", "Aria internal call"),
        ("routes.internal.aria_memory_routes", "Aria internal memory"),
        ("routes.internal.aria_workflow_routes", "Aria internal workflow"),
    ]:
        try:
            import importlib as _il
            _m = _il.import_module(_mod)
            app.include_router(_m.router)
            logger.info(f"{_label} routes loaded")
        except Exception as e:
            logger.warning(f"{_label} routes not loaded: {e}")

    # App compatibility routes
    try:
        from routes.app_compatibility_routes import router as app_compatibility_router
        app.include_router(app_compatibility_router, tags=["App Compatibility"])
        logger.info("App Compatibility routes loaded")
    except Exception as e:
        logger.warning(f"App Compatibility routes not loaded: {e}")


def _register_api_v2_routes(app):
    """API V2 routes (cursor pagination, RFC 7807 errors)."""
    try:
        from routes.api_v2 import v2_router
        app.include_router(v2_router, tags=["API V2"])
        logger.info("API V2 routes loaded (leads, loans, pipeline, scheduler, docs)")
    except Exception as e:
        logger.warning(f"API V2 routes skipped: {e}")

    # V2 OpenAPI schema
    try:
        from fastapi.openapi.utils import get_openapi

        @app.get("/api/v2/openapi.json", tags=["API V2"], include_in_schema=False)
        async def v2_openapi():
            """Serve an OpenAPI 3.1 schema containing only V2 routes."""
            all_routes = app.routes
            v2_routes = [r for r in all_routes if hasattr(r, "path") and r.path.startswith("/api/v2")]
            openapi_schema = get_openapi(
                title="Perennia AI API V2",
                version="2.0.0",
                description=(
                    "V2 API for Perennia AI. Cursor-based pagination, "
                    "RFC 7807 error responses, consistent envelope format."
                ),
                routes=v2_routes,
            )
            return openapi_schema

        logger.info("V2 OpenAPI schema endpoint registered at /api/v2/openapi.json")
    except Exception as e:
        logger.warning(f"V2 OpenAPI schema endpoint skipped: {e}")

    # Deprecation notices endpoint
    try:
        from services.api_deprecation import deprecation_router
        app.include_router(deprecation_router)
        logger.info("API deprecation notices endpoint loaded")
    except Exception as e:
        logger.warning(f"API deprecation notices endpoint skipped: {e}")


def _register_branding_routes(app, get_db, get_current_user_flexible):
    """App branding and custom domain routes."""
    try:
        from routes.branding_routes import register_branding_routes
        register_branding_routes(
            app=app, get_db_func=get_db, get_current_user_flexible=get_current_user_flexible,
        )
        logger.info("App branding routes loaded")
    except Exception as e:
        logger.warning(f"App branding routes skipped: {e}")

    try:
        from routes.custom_domain_routes import register_custom_domain_routes
        register_custom_domain_routes(
            app=app, get_db_func=get_db, get_current_user_flexible=get_current_user_flexible,
        )
        logger.info("Custom domain routes loaded")
    except Exception as e:
        logger.warning(f"Custom domain routes skipped: {e}")

    # URLA 1003 Voice Agent
    try:
        from routes.urla_call_intelligence_routes import router as urla_ci_router
        app.include_router(urla_ci_router, tags=["URLA Call Intelligence"])
        logger.info("URLA call intelligence routes loaded")
    except Exception as e:
        logger.warning(f"URLA call intelligence routes skipped: {e}")


def _register_aggregate_routes(
    app, get_db, get_current_user, get_current_user_flexible,
    oauth2_scheme, pwd_context, scheduler, log_ai_action_to_mission_control,
    update_ai_action_outcome,
):
    """Aggregate route registrations — Auth, Security, Settings, Telephony, etc."""

    # Auth & Security
    try:
        from routes._register_auth_security import register_auth_security_routes
        register_auth_security_routes(
            app=app, get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
            oauth2_scheme=oauth2_scheme,
        )
        logger.info("Auth & security routes loaded")
    except Exception as e:
        logger.warning(f"Auth & security routes failed to load: {e}")

    # Settings & Configuration
    try:
        from routes._register_settings import register_settings_routes
        register_settings_routes(
            app=app, get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
            pwd_context=pwd_context,
        )
        logger.info("Settings routes loaded")
    except Exception as e:
        logger.warning(f"Settings routes failed to load: {e}")

    # Telephony & Voice
    try:
        from routes._register_telephony import register_telephony_routes
        register_telephony_routes(
            app=app, get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
        )
        logger.info("Telephony routes loaded")
    except Exception as e:
        logger.warning(f"Telephony routes failed to load: {e}")

    # Video & Media
    try:
        from routes._register_video_media import register_video_media_routes
        register_video_media_routes(
            app=app, get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
            pwd_context=pwd_context,
        )
        logger.info("Video & media routes loaded")
    except Exception as e:
        logger.warning(f"Video & media routes failed to load: {e}")

    # Documents & Income
    try:
        from routes._register_documents_income import register_documents_income_routes
        register_documents_income_routes(
            app=app, get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
        )
        logger.info("Documents & income routes loaded")
    except Exception as e:
        logger.warning(f"Documents & income routes failed to load: {e}")

    # AI & ML
    try:
        from routes._register_ai_routes import register_ai_routes
        register_ai_routes(
            app=app, get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
            log_ai_action_to_mission_control=log_ai_action_to_mission_control,
            update_ai_action_outcome=update_ai_action_outcome,
        )
        logger.info("AI & ML routes loaded")
    except Exception as e:
        logger.warning(f"AI & ML routes failed to load: {e}")

    # Third-Party Integrations
    try:
        from routes._register_integrations import register_integration_routes
        register_integration_routes(
            app=app, get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
            scheduler=scheduler,
        )
        logger.info("Integration routes loaded")
    except Exception as e:
        logger.warning(f"Integration routes failed to load: {e}")

    # Recruiting
    try:
        from routes._register_recruiting import register_recruiting_routes
        register_recruiting_routes(
            app=app, get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
        )
        logger.info("Recruiting routes loaded")
    except Exception as e:
        logger.warning(f"Recruiting routes failed to load: {e}")

    # Agent feedback routes
    try:
        from routes.agent_feedback_routes import register_agent_feedback_routes
        register_agent_feedback_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("Agent feedback routes loaded")
    except Exception as e:
        logger.warning(f"Agent feedback routes skipped: {e}")

    # Autonomous AI agent task routes
    try:
        from routes.autonomous_task_routes import register_autonomous_task_routes
        register_autonomous_task_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("Autonomous task routes loaded")
    except Exception as e:
        logger.warning(f"Autonomous task routes skipped: {e}")


def _register_core_crm_routes(app, get_db, get_current_user, get_current_user_flexible):
    """Core CRM routes: health, leads, search, MUM, email, compliance."""
    from database.models import Lead, Loan, LoanTeamMember, ReferralPartner, MUMClient
    from database.enums import LoanStage

    # Health & system status
    try:
        from database import SessionLocal
        from routes.health_routes import register_health_routes
        register_health_routes(app=app, get_db=get_db, SessionLocal=SessionLocal)
        logger.info("Health routes loaded")
    except Exception as e:
        logger.warning(f"Health routes failed to load: {e}")

    # Leads detail
    try:
        from routes.leads_detail_routes import register_leads_detail_routes
        register_leads_detail_routes(
            app=app, get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
        )
        logger.info("Leads detail routes loaded")
    except Exception as e:
        logger.warning(f"Leads detail routes failed to load: {e}")

    # Global search
    try:
        from routes.search_routes import register_search_routes
        from routes.permission_core_routes import filter_leads_by_permissions
        register_search_routes(
            app=app, get_db=get_db,
            get_current_user_flexible=get_current_user_flexible,
            Lead=Lead, Loan=Loan, LoanTeamMember=LoanTeamMember,
            ReferralPartner=ReferralPartner, MUMClient=MUMClient,
            filter_leads_by_permissions=filter_leads_by_permissions,
        )
        logger.info("Search routes loaded")
    except Exception as e:
        logger.warning(f"Search routes failed to load: {e}")

    # MUM client & activity
    try:
        from routes.mum_activity_routes import register_mum_activity_routes
        register_mum_activity_routes(
            app=app, get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
        )
        logger.info("MUM activity routes loaded")
    except Exception as e:
        logger.warning(f"MUM activity routes failed to load: {e}")

    # Email management
    try:
        from routes.email_management_routes import register_email_management_routes
        from services.dre_helpers import refresh_microsoft_token
        register_email_management_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
            refresh_microsoft_token=refresh_microsoft_token,
        )
        logger.info("Email management routes loaded")
    except Exception as e:
        logger.warning(f"Email management routes failed to load: {e}")

    # Escalation
    try:
        from routes.escalation_routes import register_escalation_routes
        register_escalation_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("Escalation routes loaded")
    except Exception as e:
        logger.warning(f"Escalation routes failed to load: {e}")

    # Compliance
    try:
        from routes.compliance_routes import register_compliance_routes
        register_compliance_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("Compliance routes loaded")
    except Exception as e:
        logger.warning(f"Compliance routes failed to load: {e}")

    # Compliance Calculation Engine (deterministic, no LLM)
    try:
        from routes.compliance_engine_routes import register_compliance_engine_routes
        register_compliance_engine_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("Compliance calculation engine routes loaded")
    except Exception as e:
        logger.warning(f"Compliance engine routes failed to load: {e}")

    # State Licensing Compliance
    try:
        from routes.state_licensing_routes import register_state_licensing_routes
        register_state_licensing_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("State licensing compliance routes loaded")
    except Exception as e:
        logger.warning(f"State licensing routes failed to load: {e}")

    # TRID Deadline Tracking
    try:
        from routes.trid_routes import register_trid_routes
        register_trid_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("TRID deadline routes loaded (LE/CD deadline tracking)")
    except Exception as e:
        logger.warning(f"TRID deadline routes failed to load: {e}")

    # Data import
    try:
        from routes.data_import_routes import register_data_import_routes
        register_data_import_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("Data import routes loaded")
    except Exception as e:
        logger.warning(f"Data import routes failed to load: {e}")


def _register_admin_routes(app, get_db, get_current_user, get_current_user_flexible):
    """Enterprise & admin routes: LOS, SCIM, Scorecard, DR, Quality."""
    from database.models import Lead, Loan, User
    from database.enums import LoanStage

    # LOS integration API
    try:
        from routes.los_routes import register_los_routes
        register_los_routes(app=app, get_db=get_db, get_current_user=get_current_user)
        logger.info("LOS integration routes loaded")
    except Exception as e:
        logger.warning(f"LOS integration routes failed to load: {e}")

    # LOS webhook routes
    try:
        from routes.los_webhook_routes import register_los_webhook_routes
        register_los_webhook_routes(app=app, get_db=get_db)
        logger.info("LOS webhook routes loaded")
    except Exception as e:
        logger.warning(f"LOS webhook routes failed to load: {e}")

    # SCIM provisioning
    try:
        from routes.scim_provisioning_routes import register_scim_provisioning_routes
        register_scim_provisioning_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("SCIM provisioning routes loaded")
    except Exception as e:
        logger.warning(f"SCIM provisioning routes failed to load: {e}")

    # Scorecard
    try:
        from routes.scorecard_routes import register_scorecard_routes
        register_scorecard_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
            Lead=Lead, Loan=Loan, LoanStage=LoanStage,
        )
        logger.info("Scorecard routes loaded")
    except Exception as e:
        logger.warning(f"Scorecard routes failed to load: {e}")

    # State disclosure
    try:
        from routes.state_disclosure_routes import register_state_disclosure_routes
        register_state_disclosure_routes(app=app, get_db=get_db)
        logger.info("State disclosure routes loaded")
    except Exception as e:
        logger.warning(f"State disclosure routes failed to load: {e}")

    # Data quality
    try:
        from routes.data_quality_routes import register_data_quality_routes
        register_data_quality_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("Data quality routes loaded")
    except Exception as e:
        logger.warning(f"Data quality routes failed to load: {e}")

    # Data freshness monitoring
    try:
        from routes.data_freshness_routes import register_data_freshness_routes
        register_data_freshness_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("Data freshness routes loaded (Domain 3: freshness, completeness, score)")
    except Exception as e:
        logger.warning(f"Data freshness routes failed to load: {e}")

    # Disaster recovery
    try:
        from routes.dr_routes import register_dr_routes
        register_dr_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("DR routes loaded")
    except Exception as e:
        logger.warning(f"DR routes failed to load: {e}")

    # Team calendar
    try:
        from routes.team_calendar_routes import register_team_calendar_routes
        register_team_calendar_routes(app=app, get_current_user=get_current_user)
        logger.info("Team calendar routes loaded")
    except Exception as e:
        logger.warning(f"Team calendar routes failed to load: {e}")

    # SSE notifications
    try:
        from routes.sse_notification_routes import register_sse_notification_routes
        register_sse_notification_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("SSE notification routes loaded")
    except Exception as e:
        logger.warning(f"SSE notification routes failed to load: {e}")

    # Remote config
    try:
        from routes.remote_config_routes import register_remote_config_routes
        register_remote_config_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("Remote config routes loaded")
    except Exception as e:
        logger.warning(f"Remote config routes failed to load: {e}")

    # Calculator settings
    try:
        from routes.calculator_settings_routes import register_calculator_settings_routes
        register_calculator_settings_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("Calculator settings routes loaded")
    except Exception as e:
        logger.warning(f"Calculator settings routes failed to load: {e}")


def _register_infrastructure_routes(app, get_db, get_current_user):
    """Infrastructure routes: backup, cache, API keys, agents, debug."""

    try:
        from routes.backup_routes import register_backup_routes
        register_backup_routes(app=app, get_db=get_db, get_current_user=get_current_user)
        logger.info("Backup routes loaded")
    except Exception as e:
        logger.warning(f"Backup routes failed to load: {e}")

    try:
        from routes.cache_routes import register_cache_routes
        register_cache_routes(app=app, get_db=get_db, get_current_user=get_current_user)
        logger.info("Cache routes loaded")
    except Exception as e:
        logger.warning(f"Cache routes failed to load: {e}")

    try:
        from routes.api_key_routes import register_api_key_routes
        register_api_key_routes(app=app, get_db=get_db, get_current_user=get_current_user)
        logger.info("API key routes loaded")
    except Exception as e:
        logger.warning(f"API key routes failed to load: {e}")

    try:
        from routes.agent_metrics_routes import register_agent_metrics_routes
        register_agent_metrics_routes(app=app, get_db=get_db, get_current_user=get_current_user)
        logger.info("Agent metrics routes loaded")
    except Exception as e:
        logger.warning(f"Agent metrics routes failed to load: {e}")

    try:
        from routes.app_completion_registration import register_app_completion_routes
        register_app_completion_routes(app=app)
        logger.info("App completion routes loaded")
    except Exception as e:
        logger.warning(f"App completion routes failed to load: {e}")

    try:
        from routes.debug_status_routes import register_debug_status_routes
        register_debug_status_routes(app=app, get_db=get_db, get_current_user=get_current_user)
        logger.info("Debug status routes loaded")
    except Exception as e:
        logger.warning(f"Debug status routes failed to load: {e}")


def _register_inline_legacy_routes(
    app, get_db, get_current_user, get_current_user_flexible,
    scheduler, openai_client, pwd_context, SECRET_KEY, ENVIRONMENT,
    create_access_token, create_refresh_token, get_password_hash,
    verify_password, get_cached, set_cached, clear_cache, oauth2_scheme,
    log_ai_action_to_mission_control, update_ai_action_outcome,
    DATABASE_URL, security_stats,
):
    """Register inline legacy routes and set up re-exports."""
    import sys
    import types

    try:
        from routes.inline_legacy_routes import register_inline_routes
        register_inline_routes(
            app=app,
            get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
            scheduler=scheduler,
            openai_client=openai_client,
            pwd_context=pwd_context,
            SECRET_KEY=SECRET_KEY,
            ENVIRONMENT=ENVIRONMENT,
            create_access_token=create_access_token,
            create_refresh_token=create_refresh_token,
            get_password_hash=get_password_hash,
            verify_password=verify_password,
            get_cached=get_cached,
            set_cached=set_cached,
            clear_cache=clear_cache,
            oauth2_scheme=oauth2_scheme,
            log_ai_action_to_mission_control=log_ai_action_to_mission_control,
            update_ai_action_outcome=update_ai_action_outcome,
            DATABASE_URL=DATABASE_URL,
            security_stats=security_stats,
        )
        logger.info("Legacy inline routes loaded")

        # Re-export key functions for backward compatibility (from main import X)
        from routes.inline_legacy_routes import get_exported_function as _gef
        _main_module = sys.modules.get('main')
        if _main_module:
            for _fname in ('process_microsoft_email_to_dre', 'fetch_microsoft_emails',
                           'generate_email_signature_html', 'calculate_lead_score',
                           'get_entity_name', 'classify_email_intent', 'generate_recommended_action',
                           'classify_email_content', 'extract_loan_fields', 'extract_borrower_from_subject',
                           'match_entity', 'apply_extracted_data', 'delete_microsoft_email'):
                _fn = _gef(_fname)
                if _fn:
                    setattr(_main_module, _fname, _fn)

    except Exception as e:
        logger.error(f"Legacy inline routes failed to load: {e}")
        import traceback
        traceback.print_exc()


def _register_post_legacy_routes(
    app, get_db, get_current_user, get_current_user_flexible,
    pwd_context, get_password_hash, create_access_token, DATABASE_URL,
):
    """Routes that depend on functions exported from inline_legacy_routes."""

    # Admin ops routes
    try:
        from routes.admin_ops_routes import register_admin_ops_routes
        register_admin_ops_routes(
            app=app, get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
            pwd_context=pwd_context,
            get_password_hash=get_password_hash,
            create_access_token=create_access_token,
            DATABASE_URL=DATABASE_URL,
        )
        logger.info("Admin ops routes loaded")
    except Exception as e:
        logger.warning(f"Admin ops routes failed to load: {e}")

    # Debug data & email routes
    try:
        from routes.debug_data_routes import register_debug_data_routes
        from services.dre_helpers import (
            process_microsoft_email_to_dre as _dre_process,
            fetch_microsoft_emails as _dre_fetch,
            match_entity as _dre_match,
            refresh_microsoft_token as _dre_refresh,
        )
        register_debug_data_routes(
            app=app, get_db=get_db,
            get_current_user=get_current_user,
            get_current_user_flexible=get_current_user_flexible,
            process_microsoft_email_to_dre=_dre_process,
            fetch_microsoft_emails=_dre_fetch,
            match_entity=_dre_match,
            refresh_microsoft_token=_dre_refresh,
        )
        logger.info("Debug data routes loaded")
    except Exception as e:
        logger.warning(f"Debug data routes failed to load: {e}")

    # Enterprise challenge routes
    try:
        from routes.file_collaborator_routes import register_file_collaborator_routes
        register_file_collaborator_routes(app)
        logger.info("File collaborator routes registered")
    except Exception as e:
        logger.warning(f"File collaborator routes skipped: {e}")

    try:
        from routes.unified_timeline_routes import register_unified_timeline_routes
        register_unified_timeline_routes(app)
        logger.info("Unified timeline routes registered")
    except Exception as e:
        logger.warning(f"Unified timeline routes skipped: {e}")

    try:
        from routes.vendor_management_routes import register_vendor_management_routes
        register_vendor_management_routes(app)
        logger.info("Vendor management routes registered")
    except Exception as e:
        logger.warning(f"Vendor management routes skipped: {e}")

    try:
        from routes.marketing_campaign_routes import register_marketing_campaign_routes
        register_marketing_campaign_routes(app)
        logger.info("Marketing campaign routes registered")
    except Exception as e:
        logger.warning(f"Marketing campaign routes skipped: {e}")

    try:
        from routes.learning_routes import register_learning_routes
        register_learning_routes(app)
        logger.info("Learning routes registered")
    except Exception as e:
        logger.warning(f"Learning routes skipped: {e}")

    try:
        from routes.ai_activity_routes import register_ai_activity_routes
        register_ai_activity_routes(app)
        logger.info("AI activity routes registered")
    except Exception as e:
        logger.warning(f"AI activity routes not loaded: {e}")

    try:
        from routes.aria_test_routes import register_aria_test_routes
        register_aria_test_routes(app=app)
        logger.info("Aria test page registered at /aria-test")
    except Exception as e:
        logger.warning(f"Aria test page not loaded: {e}")


def _register_new_routes(app, get_db, get_current_user, get_current_user_flexible):
    """New route registrations: security, dashboard, CRM, telephony, compliance."""

    # Builder Portal (CMG Builder Application submissions)
    try:
        from routes.builder_portal_routes import router as builder_portal_router
        app.include_router(builder_portal_router, tags=["Builder Portal"])
        logger.info("Builder portal routes loaded")
    except Exception as e:
        logger.warning(f"Builder portal routes skipped: {e}")

    # Security Audit
    try:
        from routes.security_audit_routes import router as security_audit_router
        app.include_router(security_audit_router, tags=["Security Audit"])
        logger.info("Security audit routes loaded")
    except Exception as e:
        logger.warning(f"Security audit routes skipped: {e}")

    # Audit Management
    try:
        from routes.audit_management_routes import router as audit_management_router
        app.include_router(audit_management_router, tags=["Audit Management"])
        logger.info("Audit management routes loaded")
    except Exception as e:
        logger.warning(f"Audit management routes skipped: {e}")

    # Security Certificate Pinning
    try:
        from routes.security_certificate_routes import router as security_certificate_router
        app.include_router(security_certificate_router, tags=["Security Certificates"])
        logger.info("Security certificate routes loaded")
    except Exception as e:
        logger.warning(f"Security certificate routes skipped: {e}")

    # Security Dashboard
    try:
        from routes.security_dashboard_routes import router as security_dashboard_router
        app.include_router(security_dashboard_router, tags=["Security Dashboard"])
        logger.info("Security dashboard routes loaded")
    except Exception as e:
        logger.warning(f"Security dashboard routes skipped: {e}")

    # Dashboard Summary
    try:
        from routes.dashboard_summary_routes import router as dashboard_summary_router
        app.include_router(dashboard_summary_router, tags=["Dashboard"])
        logger.info("Dashboard summary routes loaded")
    except Exception as e:
        logger.warning(f"Dashboard summary routes skipped: {e}")

    # Engagement Health
    try:
        from routes.engagement_health_routes import router as engagement_health_router
        app.include_router(engagement_health_router, tags=["Engagement Health"])
        logger.info("Engagement health routes loaded")
    except Exception as e:
        logger.warning(f"Engagement health routes skipped: {e}")

    # Form 1084
    try:
        from routes.form_1084_routes import router as form_1084_router
        app.include_router(form_1084_router, tags=["Form 1084"])
        logger.info("Form 1084 routes loaded")
    except Exception as e:
        logger.warning(f"Form 1084 routes skipped: {e}")

    # LO Availability
    try:
        from routes.lo_availability_routes import router as lo_availability_router
        app.include_router(lo_availability_router, tags=["LO Availability"])
        logger.info("LO availability routes loaded")
    except Exception as e:
        logger.warning(f"LO availability routes skipped: {e}")

    # Email Response Queue
    try:
        from routes.email_response_queue_routes import router as email_response_queue_router
        from routes.email_response_queue_routes import set_dependencies as set_email_queue_deps
        from database.models import User as _UserModelEQ
        set_email_queue_deps(_UserModelEQ, get_current_user, get_db)
        app.include_router(email_response_queue_router, tags=["Email Response Queue"])
        logger.info("Email response queue routes loaded")
    except Exception as e:
        logger.warning(f"Email response queue routes skipped: {e}")

    # Live Transfer
    try:
        from routes.live_transfer_routes import router as live_transfer_router
        app.include_router(live_transfer_router, tags=["Live Transfer"])
        logger.info("Live transfer routes loaded")
    except Exception as e:
        logger.warning(f"Live transfer routes skipped: {e}")

    # AMD Voicemail
    try:
        from routes.amd_voicemail_routes import router as amd_voicemail_router
        app.include_router(amd_voicemail_router, tags=["AMD Voicemail"])
        logger.info("AMD voicemail routes loaded")
    except Exception as e:
        logger.warning(f"AMD voicemail routes skipped: {e}")

    # Speed to Lead
    try:
        from routes.speed_to_lead_routes import router as speed_to_lead_router
        app.include_router(speed_to_lead_router, tags=["Speed to Lead"])
        logger.info("Speed to Lead routes loaded")
    except Exception as e:
        logger.warning(f"Speed to Lead routes skipped: {e}")

    # Speed to Lead Calls
    try:
        from routes.speed_to_lead_call_routes import router as speed_to_lead_call_router
        app.include_router(speed_to_lead_call_router, tags=["Speed to Lead"])
        logger.info("Speed to Lead call routes loaded")
    except Exception as e:
        logger.warning(f"Speed to Lead call routes skipped: {e}")

    # SMS Compliance
    try:
        from routes.sms_compliance_routes import router as sms_compliance_router
        app.include_router(sms_compliance_router, tags=["SMS Compliance"])
        logger.info("SMS compliance routes loaded")
    except Exception as e:
        logger.warning(f"SMS compliance routes skipped: {e}")

    # SMS AI Task routes
    try:
        from routes.sms_task_routes import router as sms_task_router
        app.include_router(sms_task_router, tags=["SMS Tasks"])
        logger.info("SMS task routes loaded")
    except Exception as e:
        logger.warning(f"SMS task routes skipped: {e}")

    # Lead Routing
    try:
        from routes.lead_routing_routes import router as lead_routing_router
        app.include_router(lead_routing_router, tags=["Lead Routing"])
        logger.info("Lead routing routes loaded")
    except Exception as e:
        logger.warning(f"Lead routing routes skipped: {e}")

    # Compliance Validation
    try:
        from routes.compliance_validation_routes import register_compliance_validation_routes
        register_compliance_validation_routes(
            app=app, get_db=get_db, get_current_user=get_current_user,
        )
        logger.info("Compliance validation routes loaded")
    except Exception as e:
        logger.warning(f"Compliance validation routes skipped: {e}")

    # Command Center
    try:
        from routes.command_center_routes import router as command_center_router
        from routes.command_center_routes import set_dependencies as set_command_center_deps
        from database.models import User as _UserModelCC, Lead as _LeadModelCC, Loan as _LoanModelCC
        from database.models.task import Task as _TaskModelCC
        from database.models.ai import AIAction as _AIActionModelCC
        set_command_center_deps(
            _UserModelCC, _TaskModelCC, _LeadModelCC, _LoanModelCC, _AIActionModelCC,
            get_current_user_flexible, get_db
        )
        app.include_router(command_center_router, tags=["Command Center"])
        logger.info("Command center routes loaded")
    except Exception as e:
        logger.warning(f"Command center routes skipped: {e}")

    # Meeting Routes
    try:
        from routes.meeting_routes import router as meeting_router
        from routes.meeting_routes import set_dependencies as set_meeting_deps
        set_meeting_deps(get_db, get_current_user, {})
        app.include_router(meeting_router, tags=["Meetings"])
        logger.info("Meeting routes loaded")
    except Exception as e:
        logger.warning(f"Meeting routes skipped: {e}")

    # Call Intelligence Review Queue
    try:
        from routes.call_intelligence_review_routes import router as ci_review_router
        app.include_router(ci_review_router, tags=["Call Intelligence Reviews"])
        logger.info("Call intelligence review routes loaded")
    except Exception as e:
        logger.warning(f"Call intelligence review routes skipped: {e}")

    # Call Intelligence Diagnostic
    try:
        from routes.ci_diagnostic_routes import router as ci_diag_router
        app.include_router(ci_diag_router, tags=["Call Intelligence Diagnostic"])
        logger.info("CI diagnostic routes loaded")
    except Exception as e:
        logger.warning(f"CI diagnostic routes skipped: {e}")

    # Rate Monitor
    try:
        from routes.rate_monitor_routes import router as rate_monitor_ios_router
        app.include_router(rate_monitor_ios_router, tags=["Rate Monitor"])
        logger.info("Rate monitor iOS routes loaded")
    except Exception as e:
        logger.warning(f"Rate monitor iOS routes skipped: {e}")

    # Rate Alerts
    try:
        from routes.rate_alerts_routes import router as rate_alerts_router
        app.include_router(rate_alerts_router, tags=["Rate Monitor"])
        logger.info("Rate alerts routes loaded")
    except Exception as e:
        logger.warning(f"Rate alerts routes skipped: {e}")

    # Rate Watch (market rate polling + refi opportunity detection)
    try:
        from routes.rate_watch_routes import router as rate_watch_router
        app.include_router(rate_watch_router, tags=["Rate Watch"])
        logger.info("Rate watch routes loaded")
    except Exception as e:
        logger.warning(f"Rate watch routes skipped: {e}")

    # Knowledge Graph (entity relationship graph)
    try:
        from routes.knowledge_graph_routes import router as kg_router
        app.include_router(kg_router, tags=["Knowledge Graph"])
        logger.info("Knowledge graph routes loaded")
    except Exception as e:
        logger.warning(f"Knowledge graph routes skipped: {e}")

    # Data Quality / Deduplication
    try:
        from routes.deduplication_routes import router as dedup_router
        app.include_router(dedup_router, tags=["Data Quality"])
        logger.info("Data quality / deduplication routes loaded")
    except Exception as e:
        logger.warning(f"Data quality routes skipped: {e}")

    # VCard routes
    try:
        from routes.vcard_routes import router as vcard_router, set_dependencies as vcard_set_deps
        vcard_set_deps(get_db=get_db)
        app.include_router(vcard_router, tags=["VCard"])
        logger.info("VCard routes loaded")
    except Exception as e:
        logger.warning(f"VCard routes skipped: {e}")

    # Contact Card routes
    try:
        from routes.contact_card_routes import router as cc_router
        app.include_router(cc_router, tags=["Contact Card"])
        logger.info("Contact card settings routes loaded")
    except Exception as e:
        logger.warning(f"Contact card routes skipped: {e}")

    # Lead Assignment Configuration routes
    try:
        from routes.lead_assignment_routes import router as lead_assignment_router, set_dependencies as set_lead_assign_deps
        from database.models import User as _UserModel
        set_lead_assign_deps(_UserModel, get_current_user, get_db)
        app.include_router(lead_assignment_router, tags=["Lead Assignment"])
        logger.info("Lead Assignment routes loaded")
    except Exception as e:
        logger.warning(f"Lead Assignment routes not loaded: {e}")

    # Morning Briefing routes
    try:
        from routes.briefing_routes import router as briefing_router, set_dependencies as set_briefing_deps
        set_briefing_deps(get_db)
        app.include_router(briefing_router, tags=["Morning Briefing"])
        logger.info("Morning Briefing routes loaded")
    except Exception as e:
        logger.warning(f"Morning Briefing routes not loaded: {e}")

    # Voice Workflow Monitoring routes
    try:
        from routes.voice_workflow_monitoring_routes import router as voice_workflow_router
        app.include_router(voice_workflow_router)
        logger.info("Voice Workflow Monitoring routes loaded")
    except Exception as e:
        logger.warning(f"Voice Workflow Monitoring routes not loaded: {e}")

    # Bulk SMS Campaign routes
    try:
        from routes.bulk_sms_routes import router as bulk_sms_router
        app.include_router(bulk_sms_router, tags=["Bulk SMS"])
        logger.info("Bulk SMS campaign routes loaded")
    except Exception as e:
        logger.warning(f"Bulk SMS campaign routes skipped: {e}")

    # SMS Conversation routes
    try:
        from routes.sms_conversation_routes import router as sms_conv_router, ws_router as sms_ws_router
        app.include_router(sms_conv_router, tags=["SMS Conversations"])
        app.include_router(sms_ws_router, tags=["SMS WebSocket"])
        logger.info("SMS conversation routes loaded (REST + WebSocket)")
    except Exception as e:
        logger.warning(f"SMS conversation routes skipped: {e}")

    # Workflow Graph (flowchart builder)
    try:
        from routes.workflow_graph_routes import router as workflow_graph_router
        app.include_router(workflow_graph_router)
        from database.models.workflow_flowchart import (
            WorkflowDefinition, WorkflowNode, WorkflowEdge,
            WorkflowLeadMovement, WorkflowAIAction,
        )
        from db import engine as _wf_engine
        for _wf_model in [WorkflowDefinition, WorkflowNode, WorkflowEdge, WorkflowLeadMovement, WorkflowAIAction]:
            _wf_model.__table__.create(_wf_engine, checkfirst=True)
        from sqlalchemy import text as _wf_text
        with _wf_engine.connect() as _wf_conn:
            for col, fk_table in [
                ("workflow_definition_id", "workflow_definitions"),
                ("workflow_node_id", "workflow_nodes"),
            ]:
                try:
                    _wf_conn.execute(_wf_text(
                        f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col} VARCHAR(36) "
                        f"REFERENCES {fk_table}(id) ON DELETE SET NULL"
                    ))
                except Exception:
                    pass
            _wf_conn.commit()
        logger.info("Workflow graph routes loaded (definitions, nodes, edges, live data, AI review)")
    except Exception as e:
        logger.warning(f"Workflow graph routes skipped: {e}")


def _register_late_routes(app, get_db, get_current_user, engine, SessionLocal):
    """Late-stage route registrations: mobile API, POS, integrations, table creation."""
    import os

    # Mobile API routes
    try:
        from routes.mobile_api_routes import register_mobile_api_routes
        register_mobile_api_routes(
            app=app, get_db=get_db, get_current_user=get_current_user
        )
        logger.info("Mobile API routes loaded (dashboard, pipeline, leads, notifications, quick-lead, rate-lock-alerts)")
    except Exception as e:
        logger.error(f"Mobile API routes failed to load: {e}")
        import traceback
        traceback.print_exc()

    # Admin memory staging routes
    try:
        from routes.admin.memory_staging_routes import router as memory_staging_router
        app.include_router(memory_staging_router)
        logger.info("Admin memory staging routes loaded")
    except Exception as e:
        logger.error(f"Admin memory staging routes failed to load: {e}")

    # POS 1003 routes
    _pos_routers = {
        "application": ("routes.pos.application", "router"),
        "calendar": ("routes.pos.calendar", "router"),
        "ai_qa": ("routes.pos.ai_qa", "router"),
        "documents": ("routes.pos.documents", "router"),
        "hydration": ("routes.pos.hydration", "router"),
        "messages": ("routes.pos.messages", "router"),
        "lo_profile": ("routes.pos.lo_profile", "router"),
        "resolve_lo": ("routes.pos.resolve_lo", "router"),
        "start": ("routes.pos.start", "router"),
        "tasks": ("routes.pos.tasks", "router"),
        "team": ("routes.pos.team", "router"),
        "upload": ("routes.pos.upload", "router"),
    }
    for _pos_name, (_pos_mod, _pos_attr) in _pos_routers.items():
        try:
            import importlib
            _mod = importlib.import_module(_pos_mod)
            app.include_router(getattr(_mod, _pos_attr), tags=[f"POS {_pos_name.title()}"])
        except Exception as e:
            logger.error(f"POS route '{_pos_name}' failed to load: {e}", exc_info=True)

    try:
        from routes.pos_settings_routes import router as pos_settings_router
        app.include_router(pos_settings_router, tags=["POS Settings"])
    except Exception as e:
        logger.error(f"POS settings route failed to load: {e}", exc_info=True)

    try:
        from database.models.pos import POSBorrowerMessage
        POSBorrowerMessage.__table__.create(engine, checkfirst=True)
    except Exception as _tbl_err:
        logger.warning(f"pos_borrower_messages table creation skipped: {_tbl_err}")

    try:
        from sqlalchemy import text as _sa_text
        with engine.connect() as _conn:
            _conn.execute(_sa_text(
                "ALTER TABLE pos_application_pii "
                "ADD COLUMN IF NOT EXISTS dob_encrypted VARCHAR"
            ))
            _conn.execute(_sa_text(
                "ALTER TABLE pos_application_pii "
                "ADD COLUMN IF NOT EXISTS co_dob_encrypted VARCHAR"
            ))
            _conn.commit()
    except Exception as _pii_err:
        logger.warning(f"pos_application_pii DOB columns note: {_pii_err}")

    # iMessage / BlueBubbles Integration
    try:
        from integrations.imessage import api_router as imessage_api_router
        from integrations.imessage import webhook_router as imessage_webhook_router
        from integrations.imessage import health_router as imessage_health_router
        app.include_router(imessage_api_router, tags=["iMessage"])
        app.include_router(imessage_webhook_router, tags=["iMessage Webhooks"])
        app.include_router(imessage_health_router, tags=["iMessage Health"])
        logger.warning("iMessage/BlueBubbles routes loaded")

        try:
            from integrations.imessage.models import (
                IMessageLine, IMessageThread, IMessageMessage,
                IMessageLookupCache, IMessageWebhookLog,
            )
            for _im_model in [IMessageLine, IMessageThread, IMessageMessage,
                              IMessageLookupCache, IMessageWebhookLog]:
                _im_model.__table__.create(engine, checkfirst=True)
        except Exception as _im_table_err:
            logger.warning(f"Could not auto-create iMessage tables: {_im_table_err}")

        try:
            from migrations.seed_imessage_line import run_seed
            run_seed()
        except Exception as _im_seed_err:
            logger.warning(f"iMessage line seed: {_im_seed_err}")

    except Exception as e:
        logger.warning(f"iMessage routes skipped: {e}")

    # Microsoft 365 Integration
    try:
        from integrations.microsoft365 import router as ms365_router
        app.include_router(ms365_router, prefix="/api/v1/microsoft", tags=["Microsoft 365"])
        logger.info("Microsoft 365 integration routes loaded")

        try:
            from integrations.microsoft365.models import (
                MSAccount, MSGraphSubscription, MSCalendarSyncMapping,
                MSEmailReconciliation, MSTeamsChatReconciliation,
            )
            for _ms_model in [MSAccount, MSGraphSubscription, MSCalendarSyncMapping,
                              MSEmailReconciliation, MSTeamsChatReconciliation]:
                _ms_model.__table__.create(engine, checkfirst=True)
            logger.info("Microsoft 365 tables verified/created (5 tables)")
        except Exception as _ms_table_err:
            logger.warning(f"Could not auto-create Microsoft 365 tables: {_ms_table_err}")

    except Exception as e:
        logger.warning(f"Microsoft 365 routes skipped: {e}")

    # Microsoft Graph Email
    try:
        from routes.microsoft_email_routes import register_microsoft_email_routes
        register_microsoft_email_routes(app)
        from database.models.microsoft_email import MicrosoftEmailToken
        MicrosoftEmailToken.__table__.create(engine, checkfirst=True)
        logger.info("Microsoft Graph email routes loaded, table verified")
    except Exception as e:
        logger.warning(f"Microsoft Graph email routes skipped: {e}")

    # Teams Inbound Call Notifications
    try:
        from routes.teams_call_routes import router as teams_call_router
        app.include_router(teams_call_router)
        logger.info("Teams inbound call notification routes loaded")
    except Exception as e:
        logger.warning(f"Teams call notification routes skipped: {e}")

    # Client File Aggregate Root + Team Chat Tables
    _setup_client_file_tables(engine)

    # GDPR Erasure Request Table
    try:
        from database.models.gdpr import ErasureRequest
        ErasureRequest.__table__.create(engine, checkfirst=True)
        logger.info("GDPR erasure_requests table verified/created")
    except Exception as _gdpr_err:
        logger.warning(f"GDPR erasure_requests table setup: {_gdpr_err}")

    # AI cost tracking routes
    try:
        from routes.ai_cost_routes import register_ai_cost_routes
        register_ai_cost_routes(app=app, get_db=get_db, get_current_user=get_current_user)
        logger.info("AI cost tracking routes loaded")
    except Exception as e:
        logger.warning(f"AI cost tracking routes skipped: {e}")

    # Admin webhook dead-letter queue
    try:
        from routes.admin_webhook_routes import router as admin_webhook_router
        app.include_router(admin_webhook_router)
        logger.info("Admin webhook DLQ routes loaded")
    except Exception as e:
        logger.warning(f"Admin webhook DLQ routes skipped: {e}")


def _setup_client_file_tables(engine):
    """Set up Client File Aggregate Root + Team Chat tables."""
    try:
        from database.models.client_file import ClientFile, ClientFileCollaborator
        from database.models.team_chat import (
            TeamChatChannel, TeamChatMessage, TeamChatReaction, TeamChatRead,
        )
        for _cf_model in [ClientFile, ClientFileCollaborator,
                          TeamChatChannel, TeamChatMessage,
                          TeamChatReaction, TeamChatRead]:
            _cf_model.__table__.create(engine, checkfirst=True)
        logger.info("Client File + Team Chat tables verified/created (6 tables)")

        # Contact Card Members table
        from database.models.contact_card import ContactCardMember
        ContactCardMember.__table__.create(engine, checkfirst=True)
        logger.info("Contact Card Members table verified/created")

        # Builder Application + Documents tables
        from database.models.builder_application import BuilderApplication as _BA, BuilderDocument as _BD
        _BA.__table__.create(engine, checkfirst=True)
        _BD.__table__.create(engine, checkfirst=True)
        logger.info("Builder Application tables verified/created")

        # Knowledge Graph tables
        from database.models.knowledge_graph import KnowledgeGraphNode as _KGN, KnowledgeGraphEdge as _KGE
        _KGN.__table__.create(engine, checkfirst=True)
        _KGE.__table__.create(engine, checkfirst=True)
        logger.info("Knowledge Graph tables verified/created")

        # Ensure all ClientFile columns exist
        try:
            from sqlalchemy import text as _sa_cf_text
            _cf_columns = [
                ("active_loan_program", "VARCHAR"),
                ("active_loan_purpose", "VARCHAR"),
                ("active_loan_amount", "NUMERIC(18,2)"),
                ("active_loan_fico", "INTEGER"),
                ("active_loan_ltv", "NUMERIC(8,4)"),
                ("active_loan_lock_expires_at", "TIMESTAMPTZ"),
                ("active_loan_projected_close_date", "TIMESTAMPTZ"),
                ("sticky_note", "TEXT"),
                ("preferred_channel", "VARCHAR"),
                ("assigned_underwriter_id", "INTEGER REFERENCES users(id)"),
                ("created_by_user_id", "INTEGER REFERENCES users(id)"),
                ("last_contact_at", "TIMESTAMPTZ"),
            ]
            # SAFETY: _col_name and _col_type come from the hardcoded list above
            with engine.connect() as _cf_col_conn:
                for _col_name, _col_type in _cf_columns:
                    _cf_col_conn.execute(_sa_cf_text(
                        f"ALTER TABLE client_files ADD COLUMN IF NOT EXISTS {_col_name} {_col_type}"
                    ))
                _cf_col_conn.commit()
            logger.info("Client File columns verified/added (%d columns)", len(_cf_columns))
        except Exception as _cf_col_err:
            logger.warning("Could not add client_file columns: %s", _cf_col_err)

        # Enable RLS on the 6 new tables
        _rls_expr = "organization_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::INTEGER"
        from sqlalchemy import text as _sa_text
        with engine.connect() as _rls_conn:
            for _tbl in ["client_files", "client_file_collaborators",
                         "team_chat_channels", "team_chat_messages",
                         "team_chat_reactions", "team_chat_reads"]:
                _rls_conn.execute(_sa_text(f"ALTER TABLE {_tbl} ENABLE ROW LEVEL SECURITY"))
                _rls_conn.execute(_sa_text(f"ALTER TABLE {_tbl} FORCE ROW LEVEL SECURITY"))
                _rls_conn.execute(_sa_text(
                    f"DO $$ BEGIN "
                    f"CREATE POLICY {_tbl}_org_isolation ON {_tbl} "
                    f"USING ({_rls_expr}) WITH CHECK ({_rls_expr}); "
                    f"EXCEPTION WHEN duplicate_object THEN NULL; END $$"
                ))
            _rls_conn.commit()
        logger.info("Client File + Team Chat RLS policies verified/created")

        # Create enum types if they don't exist
        try:
            from sqlalchemy import text as _sa_text2
            with engine.connect() as _enum_conn:
                _enum_conn.execute(_sa_text2(
                    "DO $$ BEGIN "
                    "CREATE TYPE team_chat_author_kind AS ENUM ('human', 'system'); "
                    "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
                ))
                _enum_conn.execute(_sa_text2(
                    "DO $$ BEGIN "
                    "CREATE TYPE team_chat_agent_slug AS ENUM "
                    "('cadence', 'aria', 'avery', 'insight', 'ops_manager', 'document', 'milestone', 'lifecycle'); "
                    "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
                ))
                _enum_conn.execute(_sa_text2(
                    "DO $$ BEGIN "
                    "CREATE TYPE team_chat_reaction_emoji AS ENUM "
                    "('thumbs_up', 'check', 'fire', 'question'); "
                    "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
                ))
                _enum_conn.commit()
            logger.info("Team Chat enum types verified/created")
        except Exception as _enum_err:
            logger.warning(f"Could not create team_chat enum types: {_enum_err}")

    except Exception as _cf_err:
        logger.warning(f"Client File + Team Chat table setup: {_cf_err}")
