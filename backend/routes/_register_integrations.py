"""
Third-party integration route registrations.

Routes: Salesforce, HubSpot, Follow Up Boss, Microsoft, Google, Zoom, Slack,
DocuSign, OAuth, Gmail, Teams, Stripe, RETR webhooks.
"""
import logging

logger = logging.getLogger(__name__)


def register_integration_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register third-party integration routes."""
    from fastapi import Request
    from fastapi.responses import RedirectResponse

    scheduler = kwargs.get('scheduler')

    # OAuth routes (Microsoft, Google integrations)
    try:
        from oauth_routes import router as oauth_router
        app.include_router(oauth_router, prefix="/api", tags=["OAuth"])
        logger.info("OAuth routes loaded")
    except Exception as e:
        logger.warning(f"OAuth routes not loaded: {e}")

    # Salesforce Integration routes (OAuth, Webhooks, Sync)
    try:
        from routes.salesforce_routes import router as salesforce_router
        app.include_router(salesforce_router, prefix="/api/v1/salesforce", tags=["Salesforce Integration"])
        logger.info("Salesforce routes loaded")
    except Exception as e:
        logger.warning(f"Salesforce routes not loaded: {e}")

    # Salesforce Per-User Integration routes
    try:
        from routes.salesforce_integration_routes import router as salesforce_integration_router
        app.include_router(salesforce_integration_router, tags=["Salesforce User Integration"])
        logger.info("Salesforce user integration routes loaded")
    except Exception as e:
        logger.warning(f"Salesforce user integration routes not loaded: {e}")

    # Register Salesforce sync jobs with APScheduler
    if scheduler:
        try:
            from tasks.salesforce_sync_tasks import register_salesforce_sync_jobs
            register_salesforce_sync_jobs(scheduler)
            logger.info("Salesforce sync jobs registered")
        except Exception as e:
            logger.warning(f"Salesforce sync jobs not registered: {e}")

    # Microsoft Teams Integration routes
    try:
        from routes.teams_routes import router as teams_router
        app.include_router(teams_router, tags=["Teams Integration"])
        logger.info("Microsoft Teams Integration routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Teams routes: {e}")

    # HubSpot Integration routes
    try:
        from routes.hubspot_routes import router as hubspot_router, set_dependencies as set_hubspot_deps
        set_hubspot_deps(get_db, get_current_user)
        app.include_router(hubspot_router, tags=["HubSpot Integration"])
        logger.info("HubSpot routes loaded")
    except Exception as e:
        logger.warning(f"HubSpot routes not loaded: {e}")

    # Follow Up Boss Integration routes
    try:
        from routes.followupboss_routes import router as followupboss_router, set_dependencies as set_fub_deps
        from routes.followupboss_webhook_routes import router as followupboss_webhook_router
        set_fub_deps(get_db, get_current_user)
        app.include_router(followupboss_router, prefix="/api/v1", tags=["Follow Up Boss Integration"])
        app.include_router(followupboss_webhook_router, prefix="/api", tags=["Follow Up Boss Webhooks"])
        logger.info("Follow Up Boss routes loaded")
    except Exception as e:
        logger.warning(f"Follow Up Boss routes not loaded: {e}")

    # Zoom Integration routes
    try:
        from routes.zoom_routes import router as zoom_router, set_dependencies as set_zoom_deps
        set_zoom_deps(get_db, get_current_user)
        app.include_router(zoom_router, tags=["Zoom Integration"])
        logger.info("Zoom routes loaded")
    except Exception as e:
        logger.warning(f"Zoom routes not loaded: {e}")

    # Slack Integration routes
    try:
        from routes.slack_routes import router as slack_router, set_dependencies as set_slack_deps
        set_slack_deps(get_db, get_current_user)
        app.include_router(slack_router, tags=["Slack Integration"])
        logger.info("Slack routes loaded")
    except Exception as e:
        logger.warning(f"Slack routes not loaded: {e}")

    # DocuSign Integration routes
    try:
        from routes.docusign_routes import router as docusign_router, set_dependencies as set_docusign_deps
        set_docusign_deps(get_db, get_current_user)
        app.include_router(docusign_router, tags=["DocuSign Integration"])
        logger.info("DocuSign routes loaded")
    except Exception as e:
        logger.warning(f"DocuSign routes not loaded: {e}")

    # Microsoft Outlook Integration routes (Graph API operations)
    try:
        from routes.microsoft_routes import router as microsoft_router, set_dependencies as set_microsoft_deps
        set_microsoft_deps(get_db, get_current_user)
        app.include_router(microsoft_router, tags=["Microsoft Outlook Integration"])

        # Legacy OAuth callback path - redirect to new path
        @app.get("/oauth/microsoft/callback", tags=["Microsoft OAuth Legacy"])
        async def legacy_microsoft_callback(request: Request):
            """Legacy OAuth callback - redirects to new path with query params"""
            query_string = str(request.url.query)
            return RedirectResponse(url=f"/api/v1/microsoft/callback?{query_string}", status_code=307)

        logger.info("Microsoft Outlook routes loaded")
    except Exception as e:
        logger.warning(f"Microsoft Outlook routes not loaded: {e}")

    # Microsoft OAuth routes (frontend-driven popup flow, status, sync, config)
    try:
        from routes.microsoft_oauth_routes import router as microsoft_oauth_router
        app.include_router(microsoft_oauth_router, tags=["Microsoft 365 OAuth"])
        logger.info("Microsoft OAuth routes loaded")
    except Exception as e:
        logger.warning(f"Microsoft OAuth routes not loaded: {e}")

    # Register calendar providers (Google, Outlook) for outbound sync
    try:
        from services.calendar_providers import register_default_providers
        register_default_providers()
        logger.info("Calendar providers registered")
    except Exception as e:
        logger.warning(f"Calendar providers not registered: {e}")

    # Gmail Integration routes
    try:
        from gmail_routes import router as gmail_router
        app.include_router(gmail_router, tags=["Gmail Integration"])
    except Exception as e:
        logger.warning(f"Gmail Integration routes not loaded: {e}")

    # Email Drop routes (drag-and-drop email processing)
    try:
        from email_drop_routes import router as email_drop_router
        app.include_router(email_drop_router, tags=["Email Drop"])
    except Exception as e:
        logger.warning(f"Email Drop routes not loaded: {e}")

    # RETR Import Webhook routes
    try:
        from routes.webhook_routes import router as retr_webhook_router
        app.include_router(retr_webhook_router, tags=["RETR Webhooks"])
        logger.info("RETR webhook routes loaded")
    except Exception as e:
        logger.warning(f"RETR webhook routes not loaded: {e}")

    # Stripe Billing Webhook routes
    try:
        from routes.stripe_webhook_routes import router as stripe_webhook_router
        app.include_router(stripe_webhook_router, tags=["Stripe Billing"])
        logger.info("Stripe webhook routes loaded")
    except Exception as e:
        logger.warning(f"Stripe webhook routes not loaded: {e}")

    # Cache Management routes (for AI response caching)
    try:
        from api.cache_routes import router as cache_router
        app.include_router(cache_router, prefix="/api/v1", tags=["Cache Management"])
        logger.info("Cache Management routes loaded")
    except Exception as e:
        logger.warning(f"Cache Management routes not loaded: {e}")

    # Webhook routes (for cache invalidation from external systems)
    try:
        from api.webhooks import router as webhooks_router
        app.include_router(webhooks_router, prefix="/api/v1", tags=["Webhooks"])
        logger.info("Webhook routes loaded")
    except Exception as e:
        logger.warning(f"Webhook routes not loaded: {e}")

    # Monitoring routes (cache health and performance metrics)
    try:
        from api.monitoring import router as monitoring_router
        app.include_router(monitoring_router, prefix="/api/v1", tags=["Monitoring"])
        logger.info("Monitoring routes loaded")
    except Exception as e:
        logger.warning(f"Monitoring routes not loaded: {e}")

    logger.info("Integration route group loaded")
