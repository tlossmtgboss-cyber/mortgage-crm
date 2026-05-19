"""
Video OS Routes
API endpoints for the internal video generation, hosting, and analytics system.
"""

import os
import logging
from typing import Optional, Callable, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, BackgroundTasks, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from utils.responses import success_response, error_response
from sqlalchemy.exc import SQLAlchemyError
from models.video_os_models import (
    VideoProjectCreate, VideoProjectUpdate, VideoProjectResponse,
    BrandTemplateCreate, BrandTemplateUpdate, BrandTemplateResponse,
    VoiceProfileCreate, VoiceProfileResponse,
    StoryboardSceneCreate, StoryboardSceneUpdate, StoryboardSceneResponse,
    RenderJobCreate, RenderJobResponse,
    VideoLibraryCreate, VideoLibraryUpdate, VideoLibraryResponse,
    CTAOverlayCreate, CTAOverlayResponse,
    AnalyticsEventCreate,
    GenerateScriptRequest, GenerateStoryboardRequest, GenerateVisualsRequest,
    StartRenderRequest, PublishVideoRequest,
    VideoFormat, VideoVisibility, RenderJobState,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/video-os", tags=["video-os"])

# Dependency injection placeholders
_get_db: Optional[Callable] = None
_get_current_user: Optional[Callable] = None


from db import get_db


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable):
    """Set dependencies at runtime from main.py."""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


from auth.dependencies import get_current_user  # dedup: was local wrapper
# Lazy service imports
def get_project_service():
    from services.video_project_service import video_project_service
    return video_project_service


def get_render_service():
    from services.video_render_service import video_render_service
    return video_render_service


def get_hosting_service():
    from services.video_hosting_service import video_hosting_service
    return video_hosting_service


# =============================================================================
# PROJECT ROUTES
# =============================================================================

@router.post("/projects", response_model=dict)
async def create_project(
    request: VideoProjectCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new video project from a thought/content."""
    try:
        service = get_project_service()
        project = service.create_project(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
            user_id=current_user.id,
            title=request.title,
            source_type=request.source_type.value,
            source_text=request.source_text,
            description=request.description,
            source_url=request.source_url,
            brand_template_id=request.brand_template_id,
            voice_profile_id=request.voice_profile_id,
            target_duration_seconds=request.target_duration_seconds,
            target_formats=[f.value for f in request.target_formats],
            tags=request.tags,
            category=request.category,
            lead_id=request.lead_id,
            loan_id=request.loan_id,
            campaign_id=request.campaign_id,
        )
        return success_response(data=project, message="Project created")
    except Exception as e:
        logger.exception("Failed to create project")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/projects", response_model=dict)
async def list_projects(
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List video projects."""
    try:
        service = get_project_service()
        projects, total = service.list_projects(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
            status=status,
            category=category,
            search=search,
            limit=limit,
            offset=offset,
        )
        return success_response(data={
            "projects": projects,
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        logger.exception("Failed to list projects")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/projects/{project_id}", response_model=dict)
async def get_project(
    project_id: int,
    include_scenes: bool = True,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a video project by ID."""
    try:
        service = get_project_service()
        project = service.get_project(db, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if include_scenes:
            scenes = service.get_storyboard_scenes(db, project_id)
            project["scenes"] = scenes

        return success_response(data=project)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get project")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/projects/{project_id}", response_model=dict)
async def update_project(
    project_id: int,
    request: VideoProjectUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a video project."""
    try:
        service = get_project_service()
        project = service.update_project(db, project_id, **request.model_dump(exclude_unset=True))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return success_response(data=project, message="Project updated")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update project")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/projects/{project_id}", response_model=dict)
async def delete_project(
    project_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Archive a video project."""
    try:
        service = get_project_service()
        service.archive_project(db, project_id)
        return success_response(message="Project archived")
    except SQLAlchemyError as e:
        logger.exception("Failed to delete project")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# CONTENT GENERATION ROUTES
# =============================================================================

@router.post("/projects/{project_id}/generate-script", response_model=dict)
async def generate_script(
    project_id: int,
    request: GenerateScriptRequest = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a video script from thought using LLM."""
    try:
        service = get_project_service()
        result = service.generate_script(
            db=db,
            project_id=project_id,
            thought=request.thought if request else None,
        )
        return success_response(data=result, message="Script generated")
    except Exception as e:
        logger.exception("Failed to generate script")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{project_id}/generate-blog", response_model=dict)
async def generate_blog(
    project_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a blog post from the video script."""
    try:
        service = get_project_service()
        result = service.generate_blog_from_script(db, project_id)
        return success_response(data=result, message="Blog post generated")
    except Exception as e:
        logger.exception("Failed to generate blog")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{project_id}/generate-storyboard", response_model=dict)
async def generate_storyboard(
    project_id: int,
    request: GenerateStoryboardRequest = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate storyboard scenes from the script."""
    try:
        service = get_project_service()
        scenes = service.generate_storyboard(
            db=db,
            project_id=project_id,
            visual_style=request.visual_style if request else "modern",
        )
        return success_response(data={"scenes": scenes}, message="Storyboard generated")
    except Exception as e:
        logger.exception("Failed to generate storyboard")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# STORYBOARD SCENE ROUTES
# =============================================================================

@router.get("/projects/{project_id}/scenes", response_model=dict)
async def list_scenes(
    project_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all storyboard scenes for a project."""
    try:
        service = get_project_service()
        scenes = service.get_storyboard_scenes(db, project_id)
        return success_response(data={"scenes": scenes})
    except Exception as e:
        logger.exception("Failed to list scenes")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/projects/{project_id}/scenes", response_model=dict)
async def create_scene(
    project_id: int,
    request: StoryboardSceneCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a new scene to the storyboard."""
    try:
        service = get_project_service()
        scene = service.create_scene(db, project_id, **request.model_dump())
        return success_response(data=scene, message="Scene created")
    except Exception as e:
        logger.exception("Failed to create scene")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/scenes/{scene_id}", response_model=dict)
async def update_scene(
    scene_id: int,
    request: StoryboardSceneUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a storyboard scene."""
    try:
        service = get_project_service()
        scene = service.update_scene(db, scene_id, **request.model_dump(exclude_unset=True))
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        return success_response(data=scene, message="Scene updated")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update scene")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/scenes/{scene_id}", response_model=dict)
async def delete_scene(
    scene_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a storyboard scene."""
    try:
        service = get_project_service()
        service.delete_scene(db, scene_id)
        return success_response(message="Scene deleted")
    except SQLAlchemyError as e:
        logger.exception("Failed to delete scene")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/scenes/reorder", response_model=dict)
async def reorder_scenes(
    scene_order: List[int],
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reorder storyboard scenes."""
    try:
        service = get_project_service()
        service.reorder_scenes(db, scene_order)
        return success_response(message="Scenes reordered")
    except Exception as e:
        logger.exception("Failed to reorder scenes")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# RENDER JOB ROUTES
# =============================================================================

@router.post("/render-jobs", response_model=dict)
async def start_render(
    request: StartRenderRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Queue a new render job for a project."""
    try:
        render_service = get_render_service()
        jobs = []

        for format in request.formats:
            job = render_service.create_render_job(
                db=db,
                project_id=request.project_id,
                format=format.value,
                priority=request.priority,
            )
            jobs.append(job)

        return success_response(
            data={"jobs": jobs},
            message=f"{len(jobs)} render job(s) queued"
        )
    except Exception as e:
        logger.exception("Failed to start render")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/render-jobs", response_model=dict)
async def list_render_jobs(
    project_id: Optional[int] = None,
    state: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List render jobs."""
    try:
        render_service = get_render_service()
        jobs, total = render_service.list_render_jobs(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
            project_id=project_id,
            state=state,
            limit=limit,
            offset=offset,
        )
        return success_response(data={
            "jobs": jobs,
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        logger.exception("Failed to list render jobs")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/render-jobs/{job_id}", response_model=dict)
async def get_render_job(
    job_id: str,
    include_artifacts: bool = True,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get render job status and details."""
    try:
        render_service = get_render_service()
        job = render_service.get_render_job(db, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Render job not found")

        if include_artifacts:
            artifacts = render_service.get_render_artifacts(db, job["id"])
            job["artifacts"] = artifacts

        return success_response(data=job)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get render job")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/render-jobs/{job_id}/cancel", response_model=dict)
async def cancel_render_job(
    job_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a pending or in-progress render job."""
    try:
        render_service = get_render_service()
        success = render_service.cancel_job(db, job_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot cancel job in current state")
        return success_response(message="Render job cancelled")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to cancel render job")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/render-jobs/{job_id}/retry", response_model=dict)
async def retry_render_job(
    job_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retry a failed render job."""
    try:
        render_service = get_render_service()
        success = render_service.retry_job(db, job_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot retry job in current state or max retries exceeded")
        return success_response(message="Render job queued for retry")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to retry render job")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# VIDEO LIBRARY ROUTES
# =============================================================================

@router.get("/library", response_model=dict)
async def list_videos(
    folder_path: Optional[str] = None,
    visibility: Optional[str] = None,
    search: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List videos in the library."""
    try:
        hosting_service = get_hosting_service()
        tag_list = tags.split(",") if tags else None
        videos, total = hosting_service.list_videos(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
            folder_path=folder_path,
            visibility=visibility,
            search=search,
            tags=tag_list,
            limit=limit,
            offset=offset,
        )
        return success_response(data={
            "videos": videos,
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        logger.exception("Failed to list videos")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/library", response_model=dict)
async def publish_video(
    request: PublishVideoRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Publish a rendered video to the library."""
    try:
        render_service = get_render_service()
        hosting_service = get_hosting_service()

        # Get render job to find the video file
        job = render_service.get_render_job_by_id(db, request.render_job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Render job not found")

        if job["state"] != "rendered" and job["state"] != "published":
            raise HTTPException(status_code=400, detail="Video is not ready for publishing")

        # Get the final video artifact
        artifacts = render_service.get_render_artifacts(db, job["id"])
        video_artifact = next((a for a in artifacts if a["artifact_type"] == "final_video"), None)
        if not video_artifact:
            raise HTTPException(status_code=400, detail="No video artifact found")

        # Create library entry
        video = hosting_service.create_video(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
            title=request.title or job.get("project_title", "Untitled Video"),
            description=request.description,
            project_id=job.get("project_id"),
            render_job_id=job["id"],
            video_url=video_artifact["file_url"],
            duration_seconds=video_artifact.get("duration_seconds"),
            file_size_bytes=video_artifact.get("file_size_bytes"),
            format=job.get("format"),
            resolution=job.get("resolution"),
            visibility=request.visibility.value,
            folder_path=request.folder_path,
            tags=request.tags,
        )

        # Update render job state to published
        from services.video_render_service import RenderState
        render_service.transition_state(db, job["id"], RenderState.PUBLISHED)

        return success_response(data=video, message="Video published to library")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to publish video")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/library/{video_id}", response_model=dict)
async def get_video(
    video_id: int,
    include_analytics: bool = False,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get video details."""
    try:
        hosting_service = get_hosting_service()
        video = hosting_service.get_video(db, video_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        if include_analytics:
            analytics = hosting_service.get_video_analytics(db, video_id)
            video["analytics"] = analytics

        return success_response(data=video)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get video")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/library/{video_id}", response_model=dict)
async def update_video(
    video_id: int,
    request: VideoLibraryUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update video metadata."""
    try:
        hosting_service = get_hosting_service()
        updates = request.model_dump(exclude_unset=True)
        if "visibility" in updates and updates["visibility"]:
            updates["visibility"] = updates["visibility"].value

        video = hosting_service.update_video(db, video_id, **updates)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        return success_response(data=video, message="Video updated")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update video")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/library/{video_id}", response_model=dict)
async def delete_video(
    video_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a video from the library."""
    try:
        hosting_service = get_hosting_service()
        hosting_service.delete_video(db, video_id)
        return success_response(message="Video deleted")
    except SQLAlchemyError as e:
        logger.exception("Failed to delete video")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/library/{video_id}/share", response_model=dict)
async def get_share_info(
    video_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get sharing information for a video."""
    try:
        hosting_service = get_hosting_service()
        video = hosting_service.get_video(db, video_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        share_url = hosting_service.get_share_url(db, video_id)
        embed_code = hosting_service.get_embed_code(db, video_id)

        return success_response(data={
            "share_url": share_url,
            "share_token": video.get("share_token"),
            "embed_code": embed_code,
            "visibility": video.get("visibility"),
            "allow_embed": video.get("allow_embed"),
            "allowed_domains": video.get("allowed_domains", []),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get share info")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/library/{video_id}/regenerate-token", response_model=dict)
async def regenerate_share_token(
    video_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Regenerate the share token for a video (invalidates old links)."""
    try:
        hosting_service = get_hosting_service()
        new_token = hosting_service.regenerate_share_token(db, video_id)
        return success_response(data={"share_token": new_token}, message="Share token regenerated")
    except Exception as e:
        logger.exception("Failed to regenerate token")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# ANALYTICS ROUTES
# =============================================================================

@router.get("/analytics/overview", response_model=dict)
async def get_analytics_overview(
    days: int = Query(30, ge=1, le=365),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get organization-wide video analytics overview."""
    try:
        hosting_service = get_hosting_service()
        stats = hosting_service.get_org_video_stats(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
            days=days,
        )
        return success_response(data=stats)
    except Exception as e:
        logger.exception("Failed to get analytics overview")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/videos/{video_id}", response_model=dict)
async def get_video_analytics(
    video_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed analytics for a specific video."""
    try:
        hosting_service = get_hosting_service()

        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None

        analytics = hosting_service.get_video_analytics(
            db=db,
            video_id=video_id,
            start_date=start_dt,
            end_date=end_dt,
        )
        return success_response(data=analytics)
    except Exception as e:
        logger.exception("Failed to get video analytics")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/videos/{video_id}/heatmap", response_model=dict)
async def get_video_heatmap(
    video_id: int,
    segments: int = Query(100, ge=10, le=1000),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get watch heatmap for a video."""
    try:
        hosting_service = get_hosting_service()
        heatmap = hosting_service.get_watch_heatmap(
            db=db,
            video_id=video_id,
            segment_count=segments,
        )
        return success_response(data=heatmap)
    except Exception as e:
        logger.exception("Failed to get heatmap")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/viewers", response_model=dict)
async def get_viewer_engagement(
    video_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    limit: int = Query(50, le=100),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get viewer engagement data."""
    try:
        hosting_service = get_hosting_service()
        engagement = hosting_service.get_viewer_engagement(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
            video_id=video_id,
            lead_id=lead_id,
            limit=limit,
        )
        return success_response(data={"viewers": engagement})
    except Exception as e:
        logger.exception("Failed to get viewer engagement")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# CTA OVERLAY ROUTES
# =============================================================================

@router.get("/cta-overlays", response_model=dict)
async def list_cta_overlays(
    cta_type: Optional[str] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List CTA overlay templates."""
    try:
        hosting_service = get_hosting_service()
        overlays = hosting_service.list_cta_overlays(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
            cta_type=cta_type,
        )
        return success_response(data={"overlays": overlays})
    except Exception as e:
        logger.exception("Failed to list CTA overlays")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/cta-overlays", response_model=dict)
async def create_cta_overlay(
    request: CTAOverlayCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new CTA overlay template."""
    try:
        hosting_service = get_hosting_service()
        overlay = hosting_service.create_cta_overlay(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
            name=request.name,
            cta_type=request.cta_type.value,
            **request.model_dump(exclude={"name", "cta_type"})
        )
        return success_response(data=overlay, message="CTA overlay created")
    except Exception as e:
        logger.exception("Failed to create CTA overlay")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/cta-overlays/{cta_id}", response_model=dict)
async def get_cta_overlay(
    cta_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a CTA overlay by ID."""
    try:
        hosting_service = get_hosting_service()
        overlay = hosting_service.get_cta_overlay(db, cta_id)
        if not overlay:
            raise HTTPException(status_code=404, detail="CTA overlay not found")
        return success_response(data=overlay)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get CTA overlay")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# BRAND TEMPLATE ROUTES
# =============================================================================

@router.get("/brand-templates", response_model=dict)
async def list_brand_templates(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List brand templates."""
    try:
        service = get_project_service()
        templates = service.list_brand_templates(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
        )
        return success_response(data={"templates": templates})
    except Exception as e:
        logger.exception("Failed to list brand templates")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/brand-templates", response_model=dict)
async def create_brand_template(
    request: BrandTemplateCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new brand template."""
    try:
        service = get_project_service()
        template = service.create_brand_template(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
            **request.model_dump()
        )
        return success_response(data=template, message="Brand template created")
    except Exception as e:
        logger.exception("Failed to create brand template")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/brand-templates/{template_id}", response_model=dict)
async def get_brand_template(
    template_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a brand template by ID."""
    try:
        service = get_project_service()
        template = service.get_brand_template(db, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Brand template not found")
        return success_response(data=template)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get brand template")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/brand-templates/{template_id}", response_model=dict)
async def update_brand_template(
    template_id: int,
    request: BrandTemplateUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a brand template."""
    try:
        service = get_project_service()
        template = service.update_brand_template(db, template_id, **request.model_dump(exclude_unset=True))
        if not template:
            raise HTTPException(status_code=404, detail="Brand template not found")
        return success_response(data=template, message="Brand template updated")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update brand template")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# VOICE PROFILE ROUTES
# =============================================================================

@router.get("/voice-profiles", response_model=dict)
async def list_voice_profiles(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List voice profiles."""
    try:
        service = get_project_service()
        profiles = service.list_voice_profiles(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
        )
        return success_response(data={"profiles": profiles})
    except Exception as e:
        logger.exception("Failed to list voice profiles")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/voice-profiles", response_model=dict)
async def create_voice_profile(
    request: VoiceProfileCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new voice profile."""
    try:
        service = get_project_service()
        profile = service.create_voice_profile(
            db=db,
            organization_id=getattr(current_user, "organization_id", None),
            user_id=current_user.id,
            **request.model_dump()
        )
        return success_response(data=profile, message="Voice profile created")
    except Exception as e:
        logger.exception("Failed to create voice profile")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/voice-profiles/{profile_id}", response_model=dict)
async def get_voice_profile(
    profile_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a voice profile by ID."""
    try:
        service = get_project_service()
        profile = service.get_voice_profile(db, profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Voice profile not found")
        return success_response(data=profile)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get voice profile")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# PUBLIC EMBED/PLAYER ROUTES (No Auth Required)
# =============================================================================

@router.get("/embed/{share_token}", response_class=HTMLResponse)
async def get_embed_player(
    share_token: str,
    autoplay: bool = False,
    muted: bool = False,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Get embeddable video player HTML."""
    try:
        hosting_service = get_hosting_service()

        referrer = request.headers.get("Referer") if request else None
        allowed, video = hosting_service.check_embed_access(db, share_token, referrer)

        if not allowed or not video:
            return HTMLResponse(
                content="<html><body><h1>Video not available</h1></body></html>",
                status_code=403
            )

        # Generate player HTML
        player_html = _generate_player_html(video, autoplay, muted)
        return HTMLResponse(content=player_html)
    except Exception as e:
        logger.exception("Failed to get embed player")
        return HTMLResponse(
            content="<html><body><h1>Error loading video</h1></body></html>",
            status_code=500
        )


@router.get("/watch/{share_token}", response_class=HTMLResponse)
async def get_watch_page(
    share_token: str,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Get public video watch page."""
    try:
        hosting_service = get_hosting_service()
        video = hosting_service.get_video_by_share_token(db, share_token)

        if not video:
            return HTMLResponse(
                content="<html><body><h1>Video not found</h1></body></html>",
                status_code=404
            )

        # Generate watch page HTML
        watch_html = _generate_watch_page_html(video)
        return HTMLResponse(content=watch_html)
    except Exception as e:
        logger.exception("Failed to get watch page")
        return HTMLResponse(
            content="<html><body><h1>Error loading video</h1></body></html>",
            status_code=500
        )


# =============================================================================
# PUBLIC ANALYTICS BEACON (No Auth Required)
# =============================================================================

@router.post("/beacon", response_model=dict)
async def track_analytics_beacon(
    events: List[AnalyticsEventCreate],
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Track analytics events from the video player (public endpoint)."""
    try:
        hosting_service = get_hosting_service()

        event_dicts = [
            {
                "video_id": e.video_id,
                "event_type": e.event_type.value,
                "session_id": e.session_id,
                "event_data": e.event_data,
                "video_time_seconds": e.video_time_seconds,
                "percent_watched": e.percent_watched,
                "client_timestamp": e.client_timestamp,
            }
            for e in events
        ]

        count = hosting_service.track_batch_events(db, event_dicts)
        return success_response(data={"tracked": count})
    except Exception as e:
        logger.exception("Failed to track beacon events")
        # Don't fail - analytics should be fire-and-forget
        return success_response(data={"tracked": 0})


@router.post("/sessions", response_model=dict)
async def create_viewer_session(
    video_id: int,
    viewer_id: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Create a new viewer session (public endpoint)."""
    try:
        hosting_service = get_hosting_service()

        session = hosting_service.create_viewer_session(
            db=db,
            video_id=video_id,
            viewer_id=viewer_id,
            user_agent=request.headers.get("User-Agent") if request else None,
            ip_address=request.client.host if request else None,
            referrer=request.headers.get("Referer") if request else None,
        )
        return success_response(data=session)
    except Exception as e:
        logger.exception("Failed to create viewer session")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/sessions/{session_id}/identify", response_model=dict)
async def identify_viewer(
    session_id: str,
    viewer_name: Optional[str] = None,
    viewer_email: Optional[str] = None,
    viewer_company: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Identify a viewer mid-session (e.g., after form submission)."""
    try:
        hosting_service = get_hosting_service()
        success = hosting_service.identify_viewer(
            db=db,
            session_id=session_id,
            viewer_name=viewer_name,
            viewer_email=viewer_email,
            viewer_company=viewer_company,
        )
        return success_response(data={"identified": success})
    except Exception as e:
        logger.exception("Failed to identify viewer")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/sessions/{session_id}/end", response_model=dict)
async def end_viewer_session(
    session_id: str,
    db: Session = Depends(get_db)
):
    """End a viewer session."""
    try:
        hosting_service = get_hosting_service()
        hosting_service.end_viewer_session(db, session_id)
        return success_response(message="Session ended")
    except SQLAlchemyError as e:
        logger.exception("Failed to end session")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _generate_player_html(video: dict, autoplay: bool, muted: bool) -> str:
    """Generate the video player HTML."""
    api_url = os.getenv("API_URL", "https://app.perenniaai.com")
    video_url = video.get("video_url", "")
    poster_url = video.get("poster_url") or video.get("thumbnail_url", "")

    autoplay_attr = "autoplay" if autoplay else ""
    muted_attr = "muted" if muted else ""

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{video.get("title", "Video")}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html, body {{ width: 100%; height: 100%; background: #000; }}
        video {{ width: 100%; height: 100%; object-fit: contain; }}
        .cta-overlay {{ display: none; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.85); padding: 2rem; border-radius: 12px; text-align: center; color: #fff; }}
        .cta-overlay.active {{ display: block; }}
        .cta-button {{ display: inline-block; margin-top: 1rem; padding: 0.75rem 2rem;
            background: #ed8936; color: #fff; text-decoration: none; border-radius: 6px; font-weight: 600; }}
    </style>
</head>
<body>
    <video id="player" poster="{poster_url}" {autoplay_attr} {muted_attr} playsinline controls>
        <source src="{video_url}" type="video/mp4">
        Your browser does not support the video tag.
    </video>

    <div id="ctaOverlay" class="cta-overlay">
        <h2 id="ctaHeadline"></h2>
        <p id="ctaDescription"></p>
        <a id="ctaButton" class="cta-button" href="#"></a>
    </div>

    <script>
        const videoId = {video.get("id", 0)};
        const apiUrl = "{api_url}";
        let sessionId = null;
        let lastReportedTime = 0;

        // Initialize session
        fetch(apiUrl + "/api/v1/video-os/sessions?video_id=" + videoId, {{ method: "POST" }})
            .then(r => r.json())
            .then(data => {{ sessionId = data.data?.session_id; }});

        const player = document.getElementById("player");

        function trackEvent(eventType, data = {{}}) {{
            if (!sessionId) return;
            const event = {{
                video_id: videoId,
                session_id: sessionId,
                event_type: eventType,
                video_time_seconds: player.currentTime,
                percent_watched: (player.currentTime / player.duration) * 100,
                event_data: data,
                client_timestamp: new Date().toISOString()
            }};
            fetch(apiUrl + "/api/v1/video-os/beacon", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify([event])
            }});
        }}

        player.addEventListener("play", () => trackEvent("play"));
        player.addEventListener("pause", () => trackEvent("pause"));
        player.addEventListener("ended", () => {{
            trackEvent("complete");
            fetch(apiUrl + "/api/v1/video-os/sessions/" + sessionId + "/end", {{ method: "POST" }});
        }});

        player.addEventListener("timeupdate", () => {{
            const percent = (player.currentTime / player.duration) * 100;
            if (percent >= 25 && lastReportedTime < 25) {{ trackEvent("quartile_25"); lastReportedTime = 25; }}
            if (percent >= 50 && lastReportedTime < 50) {{ trackEvent("quartile_50"); lastReportedTime = 50; }}
            if (percent >= 75 && lastReportedTime < 75) {{ trackEvent("quartile_75"); lastReportedTime = 75; }}
        }});
    </script>
</body>
</html>'''


def _generate_watch_page_html(video: dict) -> str:
    """Generate the public watch page HTML."""
    api_url = os.getenv("API_URL", "https://app.perenniaai.com")
    frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{video.get("title", "Video")} | Perennia</title>
    <meta property="og:title" content="{video.get("title", "Video")}">
    <meta property="og:type" content="video.other">
    <meta property="og:image" content="{video.get("thumbnail_url", "")}">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f0f; color: #fff; min-height: 100vh; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
        .video-wrapper {{ position: relative; width: 100%; padding-top: 56.25%; background: #000; border-radius: 12px; overflow: hidden; }}
        .video-wrapper iframe {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: 0; }}
        .video-info {{ margin-top: 1.5rem; }}
        .video-title {{ font-size: 1.5rem; font-weight: 600; margin-bottom: 0.5rem; }}
        .video-description {{ color: #a0a0a0; line-height: 1.6; }}
        .powered-by {{ margin-top: 2rem; text-align: center; color: #666; font-size: 0.875rem; }}
        .powered-by a {{ color: #ed8936; text-decoration: none; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="video-wrapper">
            <iframe src="{api_url}/api/v1/video-os/embed/{video.get("share_token")}" allowfullscreen></iframe>
        </div>
        <div class="video-info">
            <h1 class="video-title">{video.get("title", "")}</h1>
            <p class="video-description">{video.get("description", "")}</p>
        </div>
        <p class="powered-by">Powered by <a href="{frontend_url}">Perennia AI</a></p>
    </div>
</body>
</html>'''


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================

@router.get("/admin/run-migration")
async def run_video_os_migration(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
):
    """Run the Video OS migration (admin only)."""
    expected_key = os.getenv("ADMIN_API_KEY", "")

    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from migrations.add_video_os_tables import run_migration
        result = run_migration()
        return success_response(result, "Video OS migration completed successfully")
    except Exception as e:
        logger.error(f"Video OS migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
