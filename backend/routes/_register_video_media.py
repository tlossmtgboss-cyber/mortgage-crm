"""
Video & Media route registrations.

Routes: Video meetings, video clips, carousel builder, avatar, vidyard,
video OS, portal video, content marketing.
"""
import logging

logger = logging.getLogger(__name__)


def register_video_media_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register video and media routes."""
    from fastapi import Depends
    from database import engine
    from database.models import User

    pwd_context = kwargs.get('pwd_context')

    # Include Video Meeting routes (UVIP)
    _video_meeting_error = None
    try:
        from video_meeting_models import create_video_meeting_models
        from video_meeting_routes import router as video_meeting_router, set_dependencies as set_video_meeting_deps

        video_meeting_models = create_video_meeting_models(engine.__class__.__bases__[0].__subclasses__()[0].__bases__[0] if False else None)
        # Use Base from database module
        from database import Base
        video_meeting_models = create_video_meeting_models(Base)

        # Ensure video meeting tables exist
        try:
            for _vm_name, _vm_model in video_meeting_models.items():
                if hasattr(_vm_model, '__table__'):
                    _vm_model.__table__.create(engine, checkfirst=True)
            logger.info("Video meeting tables ensured")
        except Exception as _vm_tbl_err:
            logger.warning(f"Video meeting table creation: {_vm_tbl_err}")

        set_video_meeting_deps(get_db, get_current_user, video_meeting_models, pwd_context=pwd_context)
        app.include_router(video_meeting_router, tags=["Video Meetings"])
        logger.info("Video Meeting (UVIP) routes loaded")

        # Load Video Meeting WebRTC Signaling
        from video_meeting_signaling import router as video_signaling_router
        app.include_router(video_signaling_router, tags=["Video Meeting Signaling"])
        logger.info("Video Meeting Signaling (WebRTC) routes loaded")

        # Load Chime SDK meeting routes
        try:
            from chime_meeting_routes import router as chime_router, set_dependencies as set_chime_deps
            set_chime_deps(get_db, get_current_user, video_meeting_models)
            app.include_router(chime_router, tags=["Chime Video Meetings"])
            logger.info("Chime SDK meeting routes loaded")
        except Exception as chime_err:
            logger.warning(f"Chime meeting routes not loaded: {chime_err}")

        # Run Chime migration
        try:
            from migrations.migrate_video_to_chime import run_migration as run_chime_migration
            run_chime_migration()
        except Exception as chime_mig_err:
            logger.warning(f"Chime migration: {chime_mig_err}")
    except Exception as e:
        import traceback
        _video_meeting_error = f"{e}"
        logger.error(f"Could not load Video Meeting routes: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")

    # Debug endpoint for video meetings
    @app.get("/api/v1/debug/video-meetings-status", tags=["Debug"])
    async def debug_video_meetings_status(current_user=Depends(get_current_user)):
        """Check if video meeting routes loaded successfully"""
        if _video_meeting_error:
            return {"status": "failed"}
        return {"status": "loaded"}

    # Include Video Clip routes (UVIP - Async Video Messages)
    _video_clip_error = None
    try:
        from video_clip_models import create_video_clip_models
        from video_clip_routes import router as video_clip_router, set_dependencies as set_video_clip_deps
        from database import Base

        video_clip_models = create_video_clip_models(Base)
        set_video_clip_deps(get_db, get_current_user, video_clip_models)
        app.include_router(video_clip_router, tags=["Video Clips"])
        logger.info("Video Clip (UVIP Async) routes loaded")
    except Exception as e:
        import traceback
        _video_clip_error = f"{e}"
        logger.error(f"Could not load Video Clip routes: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")

    # Debug endpoint for video clips
    @app.get("/api/v1/debug/video-clips-status", tags=["Debug"])
    async def debug_video_clips_status(current_user=Depends(get_current_user)):
        """Check if video clip routes loaded successfully"""
        if _video_clip_error:
            return {"status": "failed"}
        return {"status": "loaded"}

    # Include Carousel Builder routes
    _carousel_routes_error = None
    try:
        from routes.carousel_builder_routes import router as carousel_builder_router, set_dependencies as set_carousel_deps
        set_carousel_deps(User, get_current_user)
        app.include_router(carousel_builder_router, tags=["Carousel Builder"])
        logger.info("Carousel Builder routes loaded")
    except Exception as e:
        import traceback
        _carousel_routes_error = f"{e}"
        logger.warning(f"Could not load Carousel Builder routes: {e}")
        logger.warning(f"Full traceback: {traceback.format_exc()}")

    @app.get("/api/v1/debug/carousel-routes-status", tags=["Debug"])
    async def debug_carousel_routes_status(current_user=Depends(get_current_user)):
        """Check if carousel builder routes loaded successfully"""
        if _carousel_routes_error:
            return {"status": "failed"}
        return {"status": "loaded"}

    # Video OS routes
    try:
        from routes.video_os_routes import router as video_os_router, set_dependencies as set_video_os_deps
        set_video_os_deps(get_db, get_current_user)
        app.include_router(video_os_router, tags=["Video OS"])
        logger.info("Video OS routes loaded")
    except Exception as e:
        logger.warning(f"Video OS routes not loaded: {e}")

    # Avatar routes (EXPERIMENTAL tier - gated)
    try:
        from feature_tiers import get_tier, FeatureTier
        if get_tier("avatar_studio") != FeatureTier.EXPERIMENTAL:
            from routes.avatar_routes import router as avatar_router, set_dependencies as set_avatar_deps
            set_avatar_deps(get_db, get_current_user)
            app.include_router(avatar_router, tags=["AI Avatars"])
            logger.info("Avatar routes loaded")
        else:
            logger.info("Avatar routes skipped (EXPERIMENTAL tier)")
    except Exception as e:
        logger.warning(f"Avatar routes not loaded: {e}")

    # Vidyard routes
    try:
        from routes.vidyard_routes import router as vidyard_router
        app.include_router(vidyard_router, tags=["Vidyard"])
        logger.info("Vidyard routes loaded")
    except Exception as e:
        logger.warning(f"Vidyard routes not loaded: {e}")

    # Portal Video routes
    try:
        from routes.portal_video_routes import router as portal_video_router
        app.include_router(portal_video_router, tags=["Portal Video"])
        logger.info("Portal Video routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Portal Video routes: {e}")

    # Content Marketing Automation routes
    try:
        from routes.content_marketing_routes import router as content_marketing_router
        app.include_router(content_marketing_router, tags=["Content Marketing"])
        logger.info("Content Marketing routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Content Marketing routes: {e}")

    # Recruiting Video routes (video recording for candidates)
    try:
        from routes.recruiting_video_routes import router as recruiting_video_router
        app.include_router(recruiting_video_router, tags=["Recruiting Video"])
        logger.info("Recruiting Video routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Recruiting Video routes: {e}")

    logger.info("Video & Media route group loaded")
