"""
Phase 2: Async Video Messages API Routes

API endpoints for:
- Clip CRUD operations
- Upload management
- Share link creation
- View tracking
- Analytics
- Template management
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import logging
import secrets

from video_clip_models import DEFAULT_CLIP_TEMPLATES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/clips", tags=["Video Clips"])

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user = None
_models = None


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies from main.py"""
    global _get_db, _get_current_user, _models
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _models = models_dict


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user is None:
        raise RuntimeError("Dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class ClipCreate(BaseModel):
    title: str
    description: Optional[str] = None
    clip_type: str = "screen_camera"
    template_id: Optional[int] = None
    crm_entity_type: Optional[str] = None
    crm_entity_id: Optional[int] = None
    tags: Optional[List[str]] = None


class ClipUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    access_level: Optional[str] = None


class ClipUploadComplete(BaseModel):
    file_size_bytes: int
    duration_seconds: int
    video_width: Optional[int] = None
    video_height: Optional[int] = None


class ShareCreate(BaseModel):
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None
    allow_download: bool = False
    allow_comments: bool = True
    require_email: bool = False
    max_views: Optional[int] = None
    expires_in_days: Optional[int] = None


class ViewTrack(BaseModel):
    share_token: Optional[str] = None
    viewer_email: Optional[str] = None
    viewer_name: Optional[str] = None


class ViewProgressUpdate(BaseModel):
    watch_duration_seconds: int
    completion_rate: float
    play_events: Optional[List[Dict]] = None


class CommentCreate(BaseModel):
    comment_text: str
    timestamp_seconds: Optional[int] = None
    parent_comment_id: Optional[int] = None
    commenter_name: Optional[str] = None
    commenter_email: Optional[str] = None


class TemplateCreate(BaseModel):
    template_name: str
    category: str
    description: Optional[str] = None
    suggested_title: Optional[str] = None
    script_outline: Optional[List[str]] = None
    default_duration_seconds: int = 120
    color: str = "#3b82f6"
    icon: str = "video"


# ============================================================================
# CLIP CRUD ENDPOINTS
# ============================================================================

@router.post("/")
async def create_clip(
    data: ClipCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new clip and get upload URL"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    try:
        from uvip.clip_service import get_clip_service
        clip_service = get_clip_service()

        result = await clip_service.create_clip(
            user_id=current_user.id,
            title=data.title,
            description=data.description,
            clip_type=data.clip_type,
            template_id=data.template_id,
            crm_entity_type=data.crm_entity_type,
            crm_entity_id=data.crm_entity_id,
            tags=data.tags,
            organization_id=getattr(current_user, 'organization_id', None),
            db=db,
            models=_models
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        logger.error(f"Error creating clip: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{clip_id}/upload-complete")
async def complete_upload(
    clip_id: int,
    data: ClipUploadComplete,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Mark upload as complete and start processing"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoClip = _models.get('VideoClip')

    # Verify ownership
    clip = db.query(VideoClip).filter(
        VideoClip.id == clip_id,
        VideoClip.user_id == current_user.id
    ).first()

    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    try:
        from uvip.clip_service import get_clip_service
        clip_service = get_clip_service()

        result = await clip_service.complete_upload(
            clip_id=clip_id,
            file_size_bytes=data.file_size_bytes,
            duration_seconds=data.duration_seconds,
            video_width=data.video_width,
            video_height=data.video_height,
            db=db,
            models=_models
        )

        # Trigger processing in background
        background_tasks.add_task(
            process_clip_background,
            clip_id
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        logger.error(f"Error completing upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_clips(
    status: Optional[str] = None,
    crm_entity_type: Optional[str] = None,
    crm_entity_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List clips for current user"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    try:
        from uvip.clip_service import get_clip_service
        clip_service = get_clip_service()

        result = await clip_service.get_user_clips(
            user_id=current_user.id,
            status=status,
            crm_entity_type=crm_entity_type,
            crm_entity_id=crm_entity_id,
            search=search,
            limit=limit,
            offset=offset,
            db=db,
            models=_models
        )

        return result

    except Exception as e:
        logger.error(f"Error listing clips: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{clip_id}")
async def get_clip(
    clip_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get clip details"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoClip = _models.get('VideoClip')

    clip = db.query(VideoClip).filter(
        VideoClip.id == clip_id,
        VideoClip.deleted_at == None
    ).first()

    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    # Check access
    if clip.user_id != current_user.id and clip.access_level == 'private':
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "id": clip.id,
        "title": clip.title,
        "description": clip.description,
        "clip_type": clip.clip_type,
        "duration_seconds": clip.duration_seconds,
        "file_size_bytes": clip.file_size_bytes,
        "status": clip.status,
        "video_url": clip.video_url,
        "thumbnail_path": clip.thumbnail_path,
        "share_token": clip.share_token,
        "access_level": clip.access_level,
        "has_transcript": clip.has_transcript,
        "transcript_text": clip.transcript_text if clip.has_transcript else None,
        "view_count": clip.view_count,
        "unique_view_count": clip.unique_view_count,
        "average_completion_rate": clip.average_completion_rate,
        "crm_entity_type": clip.crm_entity_type,
        "crm_entity_id": clip.crm_entity_id,
        "tags": clip.tags,
        "created_at": clip.created_at.isoformat() if clip.created_at else None,
        "is_owner": clip.user_id == current_user.id
    }


@router.put("/{clip_id}")
async def update_clip(
    clip_id: int,
    data: ClipUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update clip details"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoClip = _models.get('VideoClip')

    clip = db.query(VideoClip).filter(
        VideoClip.id == clip_id,
        VideoClip.user_id == current_user.id
    ).first()

    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(clip, field, value)

    clip.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "clip_id": clip.id}


@router.delete("/{clip_id}")
async def delete_clip(
    clip_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete a clip (soft delete)"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    try:
        from uvip.clip_service import get_clip_service
        clip_service = get_clip_service()

        success = await clip_service.delete_clip(
            clip_id=clip_id,
            user_id=current_user.id,
            db=db,
            models=_models
        )

        if not success:
            raise HTTPException(status_code=404, detail="Clip not found")

        return {"success": True, "message": "Clip deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting clip: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SHARE ENDPOINTS
# ============================================================================

@router.post("/{clip_id}/shares")
async def create_share(
    clip_id: int,
    data: ShareCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create shareable link for clip"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoClip = _models.get('VideoClip')

    clip = db.query(VideoClip).filter(
        VideoClip.id == clip_id,
        VideoClip.user_id == current_user.id
    ).first()

    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    try:
        from uvip.clip_service import get_clip_service
        clip_service = get_clip_service()

        result = await clip_service.create_share(
            clip_id=clip_id,
            created_by_id=current_user.id,
            recipient_email=data.recipient_email,
            recipient_name=data.recipient_name,
            allow_download=data.allow_download,
            allow_comments=data.allow_comments,
            require_email=data.require_email,
            max_views=data.max_views,
            expires_in_days=data.expires_in_days,
            db=db,
            models=_models
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        logger.error(f"Error creating share: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{clip_id}/shares")
async def list_shares(
    clip_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all shares for a clip"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoClip = _models.get('VideoClip')
    ClipShare = _models.get('ClipShare')

    clip = db.query(VideoClip).filter(
        VideoClip.id == clip_id,
        VideoClip.user_id == current_user.id
    ).first()

    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    shares = db.query(ClipShare).filter(
        ClipShare.clip_id == clip_id,
        ClipShare.is_active == True
    ).all()

    return {
        "shares": [
            {
                "id": s.id,
                "share_token": s.share_token,
                "share_url": s.share_url,
                "recipient_email": s.recipient_email,
                "recipient_name": s.recipient_name,
                "view_count": s.view_count,
                "max_views": s.max_views,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "last_viewed_at": s.last_viewed_at.isoformat() if s.last_viewed_at else None,
                "created_at": s.created_at.isoformat() if s.created_at else None
            }
            for s in shares
        ]
    }


@router.delete("/shares/{share_id}")
async def delete_share(
    share_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Deactivate a share link"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    ClipShare = _models.get('ClipShare')

    share = db.query(ClipShare).filter(
        ClipShare.id == share_id,
        ClipShare.created_by_id == current_user.id
    ).first()

    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    share.is_active = False
    db.commit()

    return {"success": True, "message": "Share deactivated"}


# ============================================================================
# PUBLIC WATCH ENDPOINTS (No auth required)
# ============================================================================

@router.get("/watch/{share_token}")
async def get_clip_for_watch(
    share_token: str,
    db: Session = Depends(get_db)
):
    """Get clip data for public viewing via share token"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoClip = _models.get('VideoClip')
    ClipShare = _models.get('ClipShare')

    # Try share link first
    share = db.query(ClipShare).filter(
        ClipShare.share_token == share_token,
        ClipShare.is_active == True
    ).first()

    if share:
        # Check expiration
        if share.expires_at and share.expires_at < datetime.utcnow():
            raise HTTPException(status_code=410, detail="Share link has expired")

        # Check max views
        if share.max_views and share.view_count >= share.max_views:
            raise HTTPException(status_code=410, detail="Maximum views reached")

        clip = db.query(VideoClip).filter(VideoClip.id == share.clip_id).first()
        share_id = share.id
    else:
        # Try clip's direct share token
        clip = db.query(VideoClip).filter(
            VideoClip.share_token == share_token,
            VideoClip.access_level.in_(['link', 'public'])
        ).first()
        share_id = None

    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    if clip.status != 'ready':
        raise HTTPException(status_code=400, detail="Clip is not ready for viewing")

    return {
        "clip_id": clip.id,
        "share_id": share_id,
        "title": clip.title,
        "description": clip.description,
        "duration_seconds": clip.duration_seconds,
        "video_url": clip.video_url,
        "thumbnail_path": clip.thumbnail_path,
        "has_transcript": clip.has_transcript,
        "transcript_text": clip.transcript_text if clip.has_transcript else None,
        "allow_comments": share.allow_comments if share else True,
        "allow_download": share.allow_download if share else False,
        "require_email": share.require_email if share else False,
        "creator_branding": clip.custom_branding or {}
    }


@router.post("/watch/{share_token}/view")
async def track_view(
    share_token: str,
    data: ViewTrack,
    request: Request,
    db: Session = Depends(get_db)
):
    """Track when someone starts watching a clip"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoClip = _models.get('VideoClip')
    ClipShare = _models.get('ClipShare')

    # Find clip by share token
    share = db.query(ClipShare).filter(
        ClipShare.share_token == share_token,
        ClipShare.is_active == True
    ).first()

    if share:
        clip_id = share.clip_id
        share_id = share.id
    else:
        clip = db.query(VideoClip).filter(
            VideoClip.share_token == share_token
        ).first()
        if not clip:
            raise HTTPException(status_code=404, detail="Clip not found")
        clip_id = clip.id
        share_id = None

    try:
        from uvip.clip_service import get_clip_service
        clip_service = get_clip_service()

        result = await clip_service.track_view(
            clip_id=clip_id,
            share_id=share_id,
            viewer_email=data.viewer_email,
            viewer_name=data.viewer_name,
            session_id=request.cookies.get('session_id'),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get('user-agent'),
            referrer=request.headers.get('referer'),
            db=db,
            models=_models
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        logger.error(f"Error tracking view: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/views/{view_id}/progress")
async def update_view_progress(
    view_id: int,
    data: ViewProgressUpdate,
    db: Session = Depends(get_db)
):
    """Update view progress (called periodically during playback)"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    try:
        from uvip.clip_service import get_clip_service
        clip_service = get_clip_service()

        result = await clip_service.update_view_progress(
            view_id=view_id,
            watch_duration_seconds=data.watch_duration_seconds,
            completion_rate=data.completion_rate,
            play_events=data.play_events,
            db=db,
            models=_models
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        logger.error(f"Error updating view progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# COMMENT ENDPOINTS
# ============================================================================

@router.post("/{clip_id}/comments")
async def add_comment(
    clip_id: int,
    data: CommentCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add comment to a clip"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoClip = _models.get('VideoClip')
    ClipComment = _models.get('ClipComment')

    clip = db.query(VideoClip).filter(VideoClip.id == clip_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    comment = ClipComment(
        clip_id=clip_id,
        user_id=current_user.id,
        comment_text=data.comment_text,
        timestamp_seconds=data.timestamp_seconds,
        parent_comment_id=data.parent_comment_id
    )

    db.add(comment)
    db.commit()
    db.refresh(comment)

    return {
        "success": True,
        "comment_id": comment.id
    }


@router.get("/{clip_id}/comments")
async def list_comments(
    clip_id: int,
    db: Session = Depends(get_db)
):
    """List comments for a clip"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    ClipComment = _models.get('ClipComment')

    comments = db.query(ClipComment).filter(
        ClipComment.clip_id == clip_id,
        ClipComment.deleted_at == None,
        ClipComment.parent_comment_id == None  # Top-level only
    ).order_by(ClipComment.timestamp_seconds, ClipComment.created_at).all()

    def format_comment(c):
        replies = db.query(ClipComment).filter(
            ClipComment.parent_comment_id == c.id,
            ClipComment.deleted_at == None
        ).all()

        return {
            "id": c.id,
            "comment_text": c.comment_text,
            "timestamp_seconds": c.timestamp_seconds,
            "commenter_name": c.commenter_name,
            "user_id": c.user_id,
            "emoji_reaction": c.emoji_reaction,
            "is_resolved": c.is_resolved,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "replies": [format_comment(r) for r in replies]
        }

    return {
        "comments": [format_comment(c) for c in comments]
    }


# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/{clip_id}/analytics")
async def get_clip_analytics(
    clip_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get comprehensive analytics for a clip"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoClip = _models.get('VideoClip')

    clip = db.query(VideoClip).filter(
        VideoClip.id == clip_id,
        VideoClip.user_id == current_user.id
    ).first()

    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    try:
        from uvip.clip_service import get_clip_service
        clip_service = get_clip_service()

        result = await clip_service.get_clip_analytics(
            clip_id=clip_id,
            db=db,
            models=_models
        )

        return result

    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/summary")
async def get_clips_summary(
    days: int = Query(30, le=365),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get summary analytics across all clips"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoClip = _models.get('VideoClip')
    ClipView = _models.get('ClipView')

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Get user's clips
    clips = db.query(VideoClip).filter(
        VideoClip.user_id == current_user.id,
        VideoClip.deleted_at == None
    ).all()

    clip_ids = [c.id for c in clips]

    # Aggregate stats
    total_clips = len(clips)
    total_views = sum(c.view_count for c in clips)
    total_watch_time = sum(c.total_watch_time_seconds for c in clips)

    # Views in period
    recent_views = db.query(ClipView).filter(
        ClipView.clip_id.in_(clip_ids),
        ClipView.started_at >= cutoff_date
    ).count() if clip_ids else 0

    # Top performing clips
    top_clips = sorted(clips, key=lambda c: c.view_count, reverse=True)[:5]

    # Average completion rate
    clips_with_views = [c for c in clips if c.view_count > 0]
    avg_completion = (
        sum(c.average_completion_rate for c in clips_with_views) / len(clips_with_views)
        if clips_with_views else 0
    )

    return {
        "period_days": days,
        "summary": {
            "total_clips": total_clips,
            "total_views": total_views,
            "views_in_period": recent_views,
            "total_watch_time_seconds": total_watch_time,
            "average_completion_rate": round(avg_completion, 3)
        },
        "top_clips": [
            {
                "id": c.id,
                "title": c.title,
                "view_count": c.view_count,
                "average_completion_rate": c.average_completion_rate
            }
            for c in top_clips
        ]
    }


# ============================================================================
# TEMPLATE ENDPOINTS
# ============================================================================

@router.get("/templates")
async def list_templates(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List available clip templates"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    ClipTemplate = _models.get('ClipTemplate')
    if not ClipTemplate:
        return {"templates": DEFAULT_CLIP_TEMPLATES}

    templates = db.query(ClipTemplate).filter(
        or_(
            ClipTemplate.is_system_template == True,
            ClipTemplate.organization_id == getattr(current_user, 'organization_id', None),
            ClipTemplate.user_id == current_user.id
        ),
        ClipTemplate.is_active == True
    ).all()

    return {
        "templates": [
            {
                "id": t.id,
                "template_key": t.template_key,
                "template_name": t.template_name,
                "category": t.category,
                "description": t.description,
                "suggested_title": t.suggested_title,
                "script_outline": t.script_outline,
                "default_duration_seconds": t.default_duration_seconds,
                "color": t.color,
                "icon": t.icon,
                "is_system_template": t.is_system_template,
                "usage_count": t.usage_count
            }
            for t in templates
        ]
    }


@router.post("/templates/seed-defaults")
async def seed_default_templates(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Seed default clip templates"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    ClipTemplate = _models.get('ClipTemplate')
    if not ClipTemplate:
        raise HTTPException(status_code=500, detail="ClipTemplate model not found")

    created = 0
    for template_data in DEFAULT_CLIP_TEMPLATES:
        existing = db.query(ClipTemplate).filter(
            ClipTemplate.template_key == template_data['template_key']
        ).first()

        if not existing:
            template = ClipTemplate(
                template_key=template_data['template_key'],
                template_name=template_data['template_name'],
                category=template_data['category'],
                description=template_data['description'],
                suggested_title=template_data['suggested_title'],
                script_outline=template_data['script_outline'],
                default_duration_seconds=template_data['default_duration_seconds'],
                color=template_data['color'],
                icon=template_data['icon'],
                is_system_template=True,
                is_active=True
            )
            db.add(template)
            created += 1

    db.commit()

    return {"success": True, "message": f"Seeded {created} default templates"}


@router.post("/templates")
async def create_template(
    data: TemplateCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a custom clip template"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    ClipTemplate = _models.get('ClipTemplate')

    template_key = f"custom_{current_user.id}_{secrets.token_hex(4)}"

    template = ClipTemplate(
        template_key=template_key,
        template_name=data.template_name,
        category=data.category,
        description=data.description,
        suggested_title=data.suggested_title,
        script_outline=data.script_outline,
        default_duration_seconds=data.default_duration_seconds,
        color=data.color,
        icon=data.icon,
        user_id=current_user.id,
        organization_id=getattr(current_user, 'organization_id', None),
        is_system_template=False,
        is_active=True
    )

    db.add(template)
    db.commit()
    db.refresh(template)

    return {
        "success": True,
        "template_id": template.id,
        "template_key": template.template_key
    }


# ============================================================================
# CRM INTEGRATION ENDPOINTS
# ============================================================================

@router.get("/crm/{entity_type}/{entity_id}")
async def get_entity_clips(
    entity_type: str,
    entity_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get clips linked to a CRM entity"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    if entity_type not in ['loan', 'lead', 'contact']:
        raise HTTPException(status_code=400, detail="Invalid entity type")

    VideoClip = _models.get('VideoClip')

    clips = db.query(VideoClip).filter(
        VideoClip.crm_entity_type == entity_type,
        VideoClip.crm_entity_id == entity_id,
        VideoClip.deleted_at == None
    ).order_by(VideoClip.created_at.desc()).all()

    return {
        "clips": [
            {
                "id": c.id,
                "title": c.title,
                "duration_seconds": c.duration_seconds,
                "status": c.status,
                "thumbnail_path": c.thumbnail_path,
                "view_count": c.view_count,
                "share_token": c.share_token,
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in clips
        ],
        "total": len(clips)
    }


@router.post("/{clip_id}/link-crm")
async def link_clip_to_crm(
    clip_id: int,
    entity_type: str = Body(...),
    entity_id: int = Body(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Link a clip to a CRM entity"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    if entity_type not in ['loan', 'lead', 'contact']:
        raise HTTPException(status_code=400, detail="Invalid entity type")

    VideoClip = _models.get('VideoClip')

    clip = db.query(VideoClip).filter(
        VideoClip.id == clip_id,
        VideoClip.user_id == current_user.id
    ).first()

    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    clip.crm_entity_type = entity_type
    clip.crm_entity_id = entity_id
    db.commit()

    return {"success": True, "linked_to": f"{entity_type}:{entity_id}"}


# ============================================================================
# BACKGROUND TASK
# ============================================================================

async def process_clip_background(clip_id: int):
    """Background task to process clip"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        from uvip.clip_service import get_clip_service
        clip_service = get_clip_service()

        await clip_service.process_clip(
            clip_id=clip_id,
            db=db,
            models=_models
        )

        logger.info(f"Clip {clip_id} processed successfully")

    except Exception as e:
        logger.error(f"Error processing clip {clip_id}: {e}")
    finally:
        db.close()
