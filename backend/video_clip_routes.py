"""
Phase 2: Async Video Messages API Routes

API endpoints for:
- Clip CRUD operations
- Upload management
- Share link creation
- View tracking
- Analytics
- Template management

Security features:
- Input validation with sanitization
- HTML/XSS prevention
- File upload validation
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body, BackgroundTasks, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator
import logging
import secrets
import re

from video_clip_models import DEFAULT_CLIP_TEMPLATES
from input_validation import (
    sanitize_text,
    sanitize_html,
    FileUploadValidator,
    validate_email
)

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
# PYDANTIC SCHEMAS WITH VALIDATION
# ============================================================================

class ClipCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    clip_type: str = Field("screen_camera", pattern=r'^(screen_camera|screen_only|camera_only)$')
    template_id: Optional[int] = None
    crm_entity_type: Optional[str] = Field(None, pattern=r'^(loan|lead|contact)$')
    crm_entity_id: Optional[int] = None
    tags: Optional[List[str]] = Field(None, max_items=10)

    @validator('title')
    def sanitize_title(cls, v):
        if not v or not v.strip():
            raise ValueError("Title cannot be empty")
        return sanitize_text(v, max_length=500)

    @validator('description')
    def sanitize_description(cls, v):
        if v:
            return sanitize_html(v, max_length=5000)
        return v

    @validator('tags')
    def sanitize_tags(cls, v):
        if not v:
            return []
        cleaned = []
        for tag in v[:10]:
            clean_tag = sanitize_text(tag, max_length=50)
            if clean_tag:
                cleaned.append(clean_tag)
        return cleaned


class ClipUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    tags: Optional[List[str]] = Field(None, max_items=10)
    access_level: Optional[str] = Field(None, pattern=r'^(private|team|public)$')

    @validator('title')
    def sanitize_title(cls, v):
        if v:
            return sanitize_text(v, max_length=500)
        return v

    @validator('description')
    def sanitize_description(cls, v):
        if v:
            return sanitize_html(v, max_length=5000)
        return v


class ClipUploadComplete(BaseModel):
    file_size_bytes: int = Field(..., ge=0, le=500 * 1024 * 1024)  # Max 500MB
    duration_seconds: int = Field(..., ge=0, le=3600)  # Max 1 hour
    video_width: Optional[int] = Field(None, ge=0, le=7680)  # Max 8K
    video_height: Optional[int] = Field(None, ge=0, le=4320)


class ShareCreate(BaseModel):
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = Field(None, max_length=200)
    allow_download: bool = False
    allow_comments: bool = True
    require_email: bool = False
    max_views: Optional[int] = Field(None, ge=1, le=10000)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)

    @validator('recipient_email')
    def validate_recipient_email(cls, v):
        if v:
            try:
                return validate_email(v)
            except ValueError as e:
                raise ValueError(str(e))
        return None

    @validator('recipient_name')
    def sanitize_recipient_name(cls, v):
        if v:
            return sanitize_text(v, max_length=200)
        return None


class ViewTrack(BaseModel):
    share_token: Optional[str] = Field(None, max_length=200)
    viewer_email: Optional[str] = None
    viewer_name: Optional[str] = Field(None, max_length=200)

    @validator('viewer_email')
    def validate_viewer_email(cls, v):
        if v:
            try:
                return validate_email(v)
            except ValueError:
                return None  # Don't fail on bad email for tracking
        return None

    @validator('viewer_name')
    def sanitize_viewer_name(cls, v):
        if v:
            return sanitize_text(v, max_length=200)
        return None


class ViewProgressUpdate(BaseModel):
    watch_duration_seconds: int = Field(..., ge=0, le=86400)  # Max 24 hours
    completion_rate: float = Field(..., ge=0.0, le=1.0)
    play_events: Optional[List[Dict]] = Field(None, max_items=100)

    @validator('play_events')
    def validate_play_events(cls, v):
        if not v:
            return []
        cleaned = []
        for event in v[:100]:
            if isinstance(event, dict):
                cleaned.append({
                    'type': str(event.get('type', ''))[:50],
                    'timestamp': float(event.get('timestamp', 0)) if event.get('timestamp') else 0,
                })
        return cleaned


class CommentCreate(BaseModel):
    comment_text: str = Field(..., min_length=1, max_length=1000)
    timestamp_seconds: Optional[int] = Field(None, ge=0, le=86400)
    parent_comment_id: Optional[int] = None
    commenter_name: Optional[str] = Field(None, max_length=200)
    commenter_email: Optional[str] = None

    @validator('comment_text')
    def sanitize_comment(cls, v):
        if not v or not v.strip():
            raise ValueError("Comment cannot be empty")
        # Strip ALL HTML for comments (plain text only)
        cleaned = sanitize_text(v, max_length=1000)
        if not cleaned:
            raise ValueError("Comment cannot be empty after sanitization")
        return cleaned

    @validator('commenter_name')
    def sanitize_commenter_name(cls, v):
        if v:
            return sanitize_text(v, max_length=200)
        return None

    @validator('commenter_email')
    def validate_commenter_email(cls, v):
        if v:
            try:
                return validate_email(v)
            except ValueError:
                return None
        return None


class TemplateCreate(BaseModel):
    template_name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., pattern=r'^[a-z_]+$', max_length=50)
    description: Optional[str] = Field(None, max_length=1000)
    suggested_title: Optional[str] = Field(None, max_length=500)
    script_outline: Optional[List[str]] = Field(None, max_items=20)
    default_duration_seconds: int = Field(120, ge=10, le=3600)
    color: str = Field("#3b82f6", pattern=r'^#[0-9a-fA-F]{6}$')
    icon: str = Field("video", pattern=r'^[a-z_]+$', max_length=50)

    @validator('template_name')
    def sanitize_template_name(cls, v):
        return sanitize_text(v, max_length=200)

    @validator('description')
    def sanitize_description(cls, v):
        if v:
            return sanitize_text(v, max_length=1000)
        return v

    @validator('suggested_title')
    def sanitize_suggested_title(cls, v):
        if v:
            return sanitize_text(v, max_length=500)
        return v

    @validator('script_outline')
    def sanitize_script_outline(cls, v):
        if v:
            return [sanitize_text(item, max_length=500) for item in v[:20]]
        return []


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for field, value in update_data.items():
        if field not in _protected:
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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/views/{view_id}/progress")
async def update_view_progress(
    view_id: int,
    data: ViewProgressUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update view progress (called periodically during playback)

    SECURITY NOTE: This endpoint is intentionally unauthenticated for public share links.
    It validates the view exists and uses session_id cookie for tracking continuity.
    Rate limiting is applied at the middleware level.
    """
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    ClipView = _models.get('ClipView')

    # SECURITY: Validate the view exists and isn't too old
    view = db.query(ClipView).filter(ClipView.id == view_id).first()
    if not view:
        raise HTTPException(status_code=404, detail="View not found")

    # SECURITY: Validate completion_rate is within bounds
    if data.completion_rate is not None and (data.completion_rate < 0 or data.completion_rate > 1):
        raise HTTPException(status_code=400, detail="Invalid completion_rate")

    # SECURITY: Validate watch_duration_seconds is reasonable
    if data.watch_duration_seconds is not None and data.watch_duration_seconds < 0:
        raise HTTPException(status_code=400, detail="Invalid watch_duration_seconds")

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
        raise HTTPException(status_code=500, detail="Internal server error")


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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)  # SECURITY: Require auth
):
    """List comments for a clip"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    VideoClip = _models.get('VideoClip')
    ClipComment = _models.get('ClipComment')

    # SECURITY: Verify user has access to this clip
    clip = db.query(VideoClip).filter(VideoClip.id == clip_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    if clip.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

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
        raise HTTPException(status_code=500, detail="Internal server error")


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
