"""
Auth & Security route registrations.

Routes: CSRF, public, organization, auth, MFA, SSO, borrower auth, secure auth.
"""
import logging

logger = logging.getLogger(__name__)


def register_auth_security_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register authentication and security routes."""
    from fastapi import Depends
    from database import engine

    oauth2_scheme = kwargs.get('oauth2_scheme')

    # Well-known routes (no auth required — Apple/Google verification)
    try:
        from routes.well_known_routes import router as well_known_router
        app.include_router(well_known_router)
        logger.info("Well-known routes loaded (AASA, assetlinks)")
    except Exception as e:
        logger.warning(f"Well-known routes not loaded: {e}")

    # Privacy and legal pages (no auth required — App Store requirement)
    try:
        from routes.privacy_routes import router as privacy_router
        app.include_router(privacy_router)
        logger.info("Privacy/legal routes loaded")
    except Exception as e:
        logger.warning(f"Privacy routes not loaded: {e}")

    # SECURITY: Include CSRF token routes
    try:
        from middleware.csrf_protection import create_csrf_routes
        csrf_router = create_csrf_routes()
        app.include_router(csrf_router, prefix="/api/v1", tags=["Security"])
        logger.info("CSRF token routes loaded")
    except Exception as e:
        logger.warning(f"Could not load CSRF routes: {e}")

    # Include public routes
    try:
        from public_routes import router as public_router
        app.include_router(public_router, tags=["Public"])
    except Exception as e:
        logger.warning(f"Public routes not loaded: {e}")

    # Include organization (multi-tenant) management routes
    try:
        from routes.organization_routes import router as organization_router
        app.include_router(organization_router, prefix="/api/v1", tags=["Organizations"])
        logger.info("Organization management routes loaded")
    except Exception as e:
        logger.warning(f"Could not load organization routes: {e}")

    # Include borrower authentication routes (social login for applicants)
    try:
        from borrower_auth_routes import router as borrower_auth_router
        app.include_router(borrower_auth_router, tags=["Borrower Auth"])
    except Exception as e:
        logger.warning(f"Borrower Auth routes not loaded: {e}")

    # Include secure auth routes (token refresh, logout, introspection)
    try:
        from auth import auth_router
        app.include_router(auth_router, prefix="/api/v1", tags=["Auth - Token Management"])
        logger.info("Secure auth routes loaded (RS256 support)")
    except Exception as e:
        logger.warning(f"Secure auth routes not loaded: {e}")

    # Include main authentication routes (/token, /token/refresh, password reset, registration)
    try:
        from routes.auth_routes import router as auth_routes_router, setup_auth_routes
        app.include_router(auth_routes_router, tags=["Authentication"])
        try:
            from database.models.device_token import DeviceToken
        except ImportError:
            DeviceToken = None
        setup_auth_routes(app, oauth2_scheme, get_current_user, DeviceToken=DeviceToken)
        logger.info("Authentication routes loaded (/token, password reset, registration)")
    except Exception as e:
        logger.warning(f"Authentication routes not loaded: {e}")

    # Include push notification trigger routes
    try:
        from routes.push_notification_routes import router as push_router, setup_push_routes
        app.include_router(push_router)
        setup_push_routes(app, get_current_user)
        logger.info("Push notification routes loaded")
    except Exception as e:
        logger.warning(f"Push notification routes not loaded: {e}")

    # Include MFA routes (TOTP setup, verify, disable, status)
    try:
        from routes.mfa_routes import router as mfa_router
        app.include_router(mfa_router, tags=["MFA - Multi-Factor Authentication"])
        logger.info("MFA routes loaded (/api/v1/auth/mfa)")
    except Exception as e:
        logger.warning(f"MFA routes not loaded: {e}")

    # Include SSO routes (SAML 2.0 + OIDC + admin config)
    try:
        from routes.sso_routes import router as sso_router
        app.include_router(sso_router, tags=["SSO - Single Sign-On"])
        try:
            from database.models.sso import SSOConfig
            SSOConfig.__table__.create(engine, checkfirst=True)
        except Exception as _tbl_err:
            logger.debug(f"SSO table creation skipped (may already exist): {_tbl_err}")
        logger.info("SSO routes loaded (SAML + OIDC)")
    except Exception as e:
        logger.warning(f"SSO routes not loaded: {e}")

    # Include Permission System routes
    try:
        from routes.permission_system_routes import router as permission_system_router
        app.include_router(permission_system_router, tags=["Permission System"])
        logger.info("Permission System routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Permission System routes: {e}")

    # Include Permission Core routes (user permission endpoints)
    try:
        from routes.permission_core_routes import router as permission_core_router
        app.include_router(permission_core_router, tags=["Permission Core"])
        logger.info("Permission Core routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Permission Core routes: {e}")

    # Include Page Permissions routes
    try:
        from routes.page_permissions_routes import router as page_permissions_router, set_dependencies as set_page_permissions_deps
        from database.models import User
        set_page_permissions_deps(get_db, get_current_user, User)
        app.include_router(page_permissions_router, tags=["Page Permissions"])
        logger.info("Page Permissions routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Page Permissions routes: {e}")

    # Include User Roles routes (Multi-role user system)
    try:
        from routes.user_roles_routes import router as user_roles_router
        app.include_router(user_roles_router, tags=["User Roles"])
        logger.info("User Roles routes loaded")
    except Exception as e:
        logger.warning(f"Could not load User Roles routes: {e}")

    # Include Security Monitoring routes (Admin Dashboard Security Tab)
    try:
        from routes.security_monitoring_routes import router as security_monitoring_router, set_dependencies as set_security_monitoring_deps
        set_security_monitoring_deps(get_current_user)
        app.include_router(security_monitoring_router, tags=["Security Monitoring"])
        logger.info("Security Monitoring routes loaded")
    except Exception as e:
        logger.warning(f"Security Monitoring routes not loaded: {e}")

    # Include Workflow Role routes
    try:
        from routes.workflow_role_routes import router as workflow_role_router
        app.include_router(workflow_role_router, tags=["Workflow Roles"])
        logger.info("Workflow Role routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Workflow Role routes: {e}")

    logger.info("Auth & Security route group loaded")
