"""
Recruiting route registrations.

Routes: Recruiting engine, candidate grading, recruit assessment, DISC assessment,
recruiting workflow, recruiting dialer, recruit portal, social media, EEOC,
partner recruiting.
"""
import logging
from fastapi import Depends
from middleware.feature_gate import feature_tier_dependency

logger = logging.getLogger(__name__)

# Router-level dependency: all recruiting endpoints require the PREMIUM tier.
_recruiting_gate = Depends(feature_tier_dependency("recruiting"))


def register_recruiting_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register recruiting routes."""

    # Include Recruiting Engine routes
    try:
        from routes.recruiting_routes import router as recruiting_router
        app.include_router(recruiting_router, tags=["Recruiting"],
                           dependencies=[_recruiting_gate])
        logger.info("Recruiting Engine routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruiting routes: {e}")

    # Include Candidate Grading routes
    try:
        from routes.candidate_grading_routes import router as grading_router
        app.include_router(grading_router, tags=["Candidate Grading"],
                           dependencies=[_recruiting_gate])
        logger.info("Candidate Grading routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Candidate Grading routes: {e}")

    # Include Recruit Assessment routes (Quiz System + Calculator)
    try:
        from routes.recruit_assessment_routes import router as recruit_assessment_router
        app.include_router(recruit_assessment_router, tags=["Recruit Assessment"],
                           dependencies=[_recruiting_gate])
        logger.info("Recruit Assessment routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruit Assessment routes: {e}")

    # Include DISC + Motivators Assessment routes
    try:
        from routes.disc_assessment_routes import router as disc_assessment_router
        app.include_router(disc_assessment_router, tags=["DISC Assessment"],
                           dependencies=[_recruiting_gate])
        logger.info("DISC Assessment routes loaded")
    except Exception as e:
        logger.warning(f"Could not load DISC Assessment routes: {e}")

    # Include Recruiting Workflow routes
    try:
        from routes.recruiting_workflow_routes import router as recruiting_workflow_router
        app.include_router(recruiting_workflow_router, tags=["Recruiting Workflow"],
                           dependencies=[_recruiting_gate])
        logger.info("Recruiting Workflow routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruiting Workflow routes: {e}")

    # Include Recruiting Dialer routes (Click-to-Call)
    try:
        from routes.recruiting_dialer_routes import router as recruiting_dialer_router
        app.include_router(recruiting_dialer_router, tags=["Recruiting Dialer"],
                           dependencies=[_recruiting_gate])
        logger.info("Recruiting Dialer routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruiting Dialer routes: {e}")

    # Include Recruit Portal routes (public candidate portal)
    try:
        from routes.recruit_portal_routes import router as recruit_portal_router
        app.include_router(recruit_portal_router, tags=["Recruit Portal"],
                           dependencies=[_recruiting_gate])
        logger.info("Recruit Portal routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruit Portal routes: {e}")

    # Include Recruit Social Media routes
    try:
        from routes.recruit_social_routes import router as recruit_social_router
        app.include_router(recruit_social_router, tags=["Recruit Social"],
                           dependencies=[_recruiting_gate])
        logger.info("Recruit Social Media routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruit Social Media routes: {e}")

    # Include Partner Recruiting routes
    try:
        from routes.partner_recruiting_routes import router as partner_recruiting_router
        app.include_router(partner_recruiting_router, tags=["Partner Recruiting"],
                           dependencies=[_recruiting_gate])
        logger.info("Partner Recruiting routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Partner Recruiting routes: {e}")

    # Include EEOC compliance routes
    try:
        from routes.recruit_eeoc_routes import router as recruit_eeoc_router
        app.include_router(recruit_eeoc_router, tags=["Recruiting EEOC"],
                           dependencies=[_recruiting_gate])
        logger.info("Recruiting EEOC routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruiting EEOC routes: {e}")

    # Include Recruit Calendar routes (standalone recruiting scheduling platform)
    try:
        from routes.recruit_calendar import router as recruit_calendar_router, public_router as recruit_calendar_public_router
        app.include_router(recruit_calendar_router, tags=["Recruit Calendar"])
        app.include_router(recruit_calendar_public_router, tags=["Recruit Calendar"])
        logger.info("Recruit Calendar routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruit Calendar routes: {e}")

    logger.info("Recruiting route group loaded")
