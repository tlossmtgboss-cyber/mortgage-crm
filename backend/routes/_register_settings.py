"""
Settings & Configuration route registrations.

Routes: User settings, profile settings, email integration settings, lead capture settings,
client portal settings, communication preferences, integration settings, API keys settings,
company branding, application slides settings.
"""
import logging

logger = logging.getLogger(__name__)


def register_settings_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register settings and configuration routes."""
    from database.models import User

    pwd_context = kwargs.get('pwd_context')

    # Include User Settings routes
    try:
        from routes.user_settings_routes import router as user_settings_router
        app.include_router(user_settings_router, tags=["User Settings"])
        logger.info("User Settings routes loaded")
    except Exception as e:
        logger.warning(f"Could not load User Settings routes: {e}")

    # Email Integration Settings routes
    try:
        from routes.email_integration_settings_routes import router as email_integration_settings_router
        app.include_router(email_integration_settings_router, tags=["Email Integration Settings"])
        logger.info("Email Integration Settings routes loaded")
    except Exception as e:
        logger.warning(f"Email Integration Settings routes not loaded: {e}")

    # User Profile Settings routes
    try:
        from routes.user_profile_settings_routes import router as user_profile_settings_router, users_router as users_me_router, set_dependencies as set_user_profile_deps
        set_user_profile_deps(User, get_current_user, pwd_context)
        app.include_router(user_profile_settings_router, tags=["User Profile Settings"])
        app.include_router(users_me_router, tags=["Users"])
        logger.info("User Profile Settings routes loaded")
    except Exception as e:
        logger.warning(f"User Profile Settings routes not loaded: {e}")

    # Lead Capture Settings routes
    try:
        from routes.lead_capture_settings_routes import router as lead_capture_settings_router, set_dependencies as set_lead_capture_deps
        set_lead_capture_deps(User, get_current_user, get_db)
        app.include_router(lead_capture_settings_router, tags=["Lead Capture Settings"])
        logger.info("Lead Capture Settings routes loaded")
    except Exception as e:
        logger.warning(f"Lead Capture Settings routes not loaded: {e}")

    # Client Portal Settings routes
    try:
        from routes.client_portal_settings_routes import router as client_portal_settings_router, set_dependencies as set_client_portal_deps
        set_client_portal_deps(User, get_current_user, get_db)
        app.include_router(client_portal_settings_router, tags=["Client Portal Settings"])
        logger.info("Client Portal Settings routes loaded")
    except Exception as e:
        logger.warning(f"Client Portal Settings routes not loaded: {e}")

    # Communication Preferences routes
    try:
        from routes.communication_preferences_routes import router as communication_preferences_router, set_dependencies as set_communication_deps
        set_communication_deps(User, get_current_user, get_db)
        app.include_router(communication_preferences_router, tags=["Communication Preferences"])
        logger.info("Communication Preferences routes loaded")
    except Exception as e:
        logger.warning(f"Communication Preferences routes not loaded: {e}")

    # Integration Settings routes
    try:
        from routes.integration_settings_routes import router as integration_settings_router, set_dependencies as set_integration_deps
        set_integration_deps(User, get_current_user, get_db)
        app.include_router(integration_settings_router, tags=["Integration Settings"])
        logger.info("Integration Settings routes loaded")
    except Exception as e:
        logger.warning(f"Integration Settings routes not loaded: {e}")

    # API Keys Settings routes
    try:
        from routes.api_keys_settings_routes import router as api_keys_settings_router, set_dependencies as set_api_keys_deps
        set_api_keys_deps(User, get_current_user, get_db)
        app.include_router(api_keys_settings_router, tags=["API Keys Settings"])
        logger.info("API Keys Settings routes loaded")
    except Exception as e:
        logger.warning(f"API Keys Settings routes not loaded: {e}")

    # Company Branding Settings routes
    try:
        from routes.company_branding_routes import router as company_branding_router, set_dependencies as set_company_branding_deps
        set_company_branding_deps(User, get_current_user, get_db)
        app.include_router(company_branding_router, tags=["Company & Branding"])
        logger.info("Company Branding Settings routes loaded")
    except Exception as e:
        logger.warning(f"Company Branding Settings routes not loaded: {e}")

    # Application Slides Settings routes
    try:
        from routes.application_slides_settings_routes import router as application_slides_router, set_dependencies as set_app_slides_deps
        set_app_slides_deps(User, get_current_user, get_db)
        app.include_router(application_slides_router, tags=["Application Slides Settings"])
        logger.info("Application Slides Settings routes loaded")
    except Exception as e:
        logger.warning(f"Application Slides Settings routes not loaded: {e}")

    # Lead Assignment Configuration routes
    try:
        from routes.lead_assignment_routes import router as lead_assignment_router, set_dependencies as set_lead_assign_deps
        set_lead_assign_deps(User, get_current_user, get_db)
        app.include_router(lead_assignment_router, tags=["Lead Assignment"])
        logger.info("Lead Assignment routes loaded")
    except Exception as e:
        logger.warning(f"Lead Assignment routes not loaded: {e}")

    # Pre-Approval Letter Settings routes
    pre_approval_letter_settings_error = None
    try:
        from routes.pre_approval_letter_settings_routes import router as pre_approval_letter_settings_router, PreApprovalLetterSettings
        from database import engine
        app.include_router(pre_approval_letter_settings_router, tags=["Pre-Approval Letter Settings"])
        PreApprovalLetterSettings.__table__.create(bind=engine, checkfirst=True)
        logger.info("Pre-Approval Letter Settings routes loaded")
    except Exception as e:
        pre_approval_letter_settings_error = str(e)
        import traceback
        pre_approval_letter_settings_error = traceback.format_exc()
        logger.warning(f"Pre-Approval Letter Settings routes not loaded: {e}")

    logger.info("Settings route group loaded")
