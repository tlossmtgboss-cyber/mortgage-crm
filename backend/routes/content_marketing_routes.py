"""
Content Marketing Automation Routes

Vocable.ai-style content marketing API endpoints:
- Brand voice analysis and profiles
- Content calendars and briefs
- Team collaboration (comments, approvals)
- SEO keyword tracking
- Content publishing and scheduling
- CRM personalization
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, date, time
from database import get_db
from services.content_marketing import (
    ContentPersonalizationService,
    BrandVoiceAnalyzerService,
    ContentCalendarService,
    ContentCollaborationService,
    ContentPublisherService,
    SEOKeywordService,
)
from models.content_marketing import (
    ContentBrandVoice, ContentCalendar, ContentBrief,
    ContentComment, ContentApproval, SEOKeyword,
    ContentMarketingTemplate, PersonalizationToken, ContentPublishLog
)
ContentTemplate = ContentMarketingTemplate
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: CORE
# This module is in the core tier.
# See backend/feature_tiers.py for tier definitions.
# ============================================================================


# ============================================================================
# AUTH DEPENDENCY
# ============================================================================

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user -- delegates to canonical auth."""
    from auth.dependencies import get_current_user as _main_get_current_user
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _main_get_current_user(token=token, request=request, db=db)


router = APIRouter(
    prefix="/api/v1/content-marketing",
    tags=["content-marketing"],
    dependencies=[Depends(get_current_user)],
)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

# Brand Voice Models
class BrandVoiceCreate(BaseModel):
    name: str
    source_url: Optional[str] = None
    source_content: Optional[str] = None
    is_default: bool = False


class BrandVoiceUpdate(BaseModel):
    name: Optional[str] = None
    tone_formal_casual: Optional[float] = None
    tone_authoritative_friendly: Optional[float] = None
    tone_technical_simple: Optional[float] = None
    tone_serious_playful: Optional[float] = None
    vocabulary_level: Optional[str] = None
    key_phrases: Optional[List[str]] = None
    avoided_phrases: Optional[List[str]] = None
    brand_values: Optional[List[str]] = None
    target_audience: Optional[str] = None
    system_prompt: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


# Calendar Models
class CalendarCreate(BaseModel):
    name: str
    start_date: date
    end_date: Optional[date] = None
    brand_voice_id: Optional[str] = None
    channels: List[str] = ["blog", "linkedin", "facebook"]
    posts_per_week: int = 5
    auto_generate_briefs: bool = True
    primary_theme: Optional[str] = None
    target_keywords: List[str] = []


class CalendarUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    posts_per_week: Optional[int] = None
    channels: Optional[List[str]] = None
    brand_voice_id: Optional[str] = None
    primary_theme: Optional[str] = None
    target_keywords: Optional[List[str]] = None


# Brief Models
class BriefCreate(BaseModel):
    calendar_id: Optional[str] = None
    scheduled_date: date
    scheduled_time: Optional[str] = None  # "HH:MM" format
    channels: List[str] = ["blog"]
    topic: str
    archetype: str = "informative"
    primary_keyword: Optional[str] = None
    secondary_keywords: List[str] = []
    target_word_count: int = 800
    target_audience: Optional[str] = None
    key_points: List[str] = []
    call_to_action: Optional[str] = None
    personalization_type: str = "general"
    personalization_segment: Optional[str] = None


class BriefUpdate(BaseModel):
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[str] = None
    channels: Optional[List[str]] = None
    title: Optional[str] = None
    topic: Optional[str] = None
    archetype: Optional[str] = None
    primary_keyword: Optional[str] = None
    target_word_count: Optional[int] = None
    key_points: Optional[List[str]] = None
    call_to_action: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[int] = None
    generated_title: Optional[str] = None
    generated_content: Optional[str] = None


# Comment Models
class CommentCreate(BaseModel):
    content: str
    brief_id: Optional[str] = None
    content_item_id: Optional[str] = None
    comment_type: str = "general"
    parent_comment_id: Optional[str] = None
    highlighted_text: Optional[str] = None
    position_start: Optional[int] = None
    position_end: Optional[int] = None


# Approval Models
class ApprovalRequest(BaseModel):
    workflow_stage: str
    assigned_to: int
    brief_id: Optional[str] = None
    content_item_id: Optional[str] = None
    due_date: Optional[datetime] = None
    content_snapshot: Optional[str] = None


class ApprovalDecision(BaseModel):
    decision_notes: Optional[str] = None


class WorkflowStage(BaseModel):
    stage: str
    assigned_to: int
    due_date: Optional[datetime] = None


class WorkflowStart(BaseModel):
    stages: List[WorkflowStage]


# Keyword Models
class KeywordCreate(BaseModel):
    keyword: str
    category: Optional[str] = None
    search_volume: Optional[int] = None
    difficulty_score: Optional[float] = None
    target_ranking: int = 10
    priority: int = 3


class KeywordUpdate(BaseModel):
    target_ranking: Optional[int] = None
    priority: Optional[int] = None
    category: Optional[str] = None
    status: Optional[str] = None


class RankingUpdate(BaseModel):
    ranking: int
    url: Optional[str] = None


class BulkRankingUpdate(BaseModel):
    rankings: List[Dict[str, Any]]


# Personalization Models
class PersonalizationPreview(BaseModel):
    template_text: str
    personalization_type: str  # lead, loan, mum, general
    record_id: str
    extra_context: Optional[Dict[str, Any]] = None


class BatchPersonalization(BaseModel):
    template_text: str
    personalization_type: str
    record_ids: List[str]
    extra_context: Optional[Dict[str, Any]] = None


# Publishing Models
class PublishRequest(BaseModel):
    channels: Optional[List[str]] = None
    publish_now: bool = False


class ScheduleRequest(BaseModel):
    scheduled_datetime: datetime
    channels: Optional[List[str]] = None


# ============================================================================
# BRAND VOICE ENDPOINTS
# ============================================================================

@router.post("/brand-voice")
async def create_brand_voice(
    request: BrandVoiceCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new brand voice profile by analyzing a website or content."""
    user_id = current_user.id
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = BrandVoiceAnalyzerService(db)
    result = await service.create_voice_profile(
        name=request.name,
        source_url=request.source_url,
        source_content=request.source_content,
        user_id=user_id,
        organization_id=organization_id,
        is_default=request.is_default,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/brand-voice")
async def list_brand_voices(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    active_only: bool = True,
):
    """List all brand voice profiles."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = BrandVoiceAnalyzerService(db)
    profiles = service.list_voice_profiles(organization_id, active_only)
    return {
        "profiles": [
            {
                "id": p.id,
                "name": p.name,
                "source_url": p.source_url,
                "tone_formal_casual": p.tone_formal_casual,
                "tone_authoritative_friendly": p.tone_authoritative_friendly,
                "vocabulary_level": p.vocabulary_level,
                "is_default": p.is_default,
                "is_active": p.is_active,
                "analysis_confidence": p.analysis_confidence,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in profiles
        ]
    }


@router.get("/brand-voice/{profile_id}")
async def get_brand_voice(
    profile_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific brand voice profile."""
    service = BrandVoiceAnalyzerService(db)
    profile = service.get_voice_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return service.export_voice_profile(profile_id)


@router.put("/brand-voice/{profile_id}")
async def update_brand_voice(
    profile_id: str,
    request: BrandVoiceUpdate,
    db: Session = Depends(get_db),
):
    """Update a brand voice profile."""
    service = BrandVoiceAnalyzerService(db)
    profile = service.update_voice_profile(
        profile_id,
        request.model_dump(exclude_unset=True)
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"success": True, "profile_id": profile.id}


@router.delete("/brand-voice/{profile_id}")
async def delete_brand_voice(
    profile_id: str,
    db: Session = Depends(get_db),
):
    """Delete (deactivate) a brand voice profile."""
    service = BrandVoiceAnalyzerService(db)
    if not service.delete_voice_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"success": True}


@router.post("/brand-voice/analyze")
async def analyze_website(
    url: str = Query(..., description="Website URL to analyze"),
    db: Session = Depends(get_db),
):
    """Analyze a website's brand voice without creating a profile."""
    service = BrandVoiceAnalyzerService(db)
    fetch_result = await service.fetch_website_content(url)
    if not fetch_result.get("success"):
        raise HTTPException(status_code=400, detail=fetch_result.get("error"))

    analysis = await service.analyze_voice(
        fetch_result.get("text_content", ""),
        source_url=url
    )
    return analysis


# ============================================================================
# CALENDAR ENDPOINTS
# ============================================================================

@router.post("/calendars")
async def create_calendar(
    request: CalendarCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new content calendar."""
    user_id = current_user.id
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = ContentCalendarService(db)
    result = service.create_calendar(
        name=request.name,
        start_date=request.start_date,
        end_date=request.end_date,
        user_id=user_id,
        organization_id=organization_id,
        brand_voice_id=request.brand_voice_id,
        channels=request.channels,
        posts_per_week=request.posts_per_week,
        auto_generate_briefs=request.auto_generate_briefs,
        primary_theme=request.primary_theme,
        target_keywords=request.target_keywords,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/calendars")
async def list_calendars(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    status: Optional[str] = None,
    include_past: bool = False,
):
    """List content calendars."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = ContentCalendarService(db)
    calendars = service.list_calendars(organization_id, status, include_past)
    return {
        "calendars": [
            {
                "id": c.id,
                "name": c.name,
                "start_date": c.start_date.isoformat(),
                "end_date": c.end_date.isoformat(),
                "status": c.status,
                "channels": c.channels,
                "total_briefs": c.total_briefs,
                "published_count": c.published_count,
            }
            for c in calendars
        ]
    }


@router.get("/calendars/{calendar_id}")
async def get_calendar(
    calendar_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific calendar."""
    service = ContentCalendarService(db)
    calendar = service.get_calendar(calendar_id)
    if not calendar:
        raise HTTPException(status_code=404, detail="Calendar not found")

    return {
        "id": calendar.id,
        "name": calendar.name,
        "description": calendar.description,
        "start_date": calendar.start_date.isoformat(),
        "end_date": calendar.end_date.isoformat(),
        "status": calendar.status,
        "channels": calendar.channels,
        "brand_voice_id": calendar.brand_voice_id,
        "posts_per_week": calendar.posts_per_week,
        "primary_theme": calendar.primary_theme,
        "target_keywords": calendar.target_keywords,
        "total_briefs": calendar.total_briefs,
        "published_count": calendar.published_count,
    }


@router.get("/calendars/{calendar_id}/stats")
async def get_calendar_stats(
    calendar_id: str,
    db: Session = Depends(get_db),
):
    """Get calendar statistics."""
    service = ContentCalendarService(db)
    return service.get_calendar_stats(calendar_id)


@router.get("/calendars/{calendar_id}/weekly")
async def get_calendar_weekly_view(
    calendar_id: str,
    week_start: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Get weekly calendar view."""
    service = ContentCalendarService(db)
    return service.get_weekly_view(calendar_id, week_start)


@router.get("/calendars/{calendar_id}/monthly")
async def get_calendar_monthly_view(
    calendar_id: str,
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
):
    """Get monthly calendar view."""
    service = ContentCalendarService(db)
    return service.get_monthly_view(calendar_id, year, month)


@router.put("/calendars/{calendar_id}")
async def update_calendar(
    calendar_id: str,
    request: CalendarUpdate,
    db: Session = Depends(get_db),
):
    """Update a calendar."""
    service = ContentCalendarService(db)
    calendar = service.update_calendar(
        calendar_id,
        request.model_dump(exclude_unset=True)
    )
    if not calendar:
        raise HTTPException(status_code=404, detail="Calendar not found")
    return {"success": True, "calendar_id": calendar.id}


@router.post("/calendars/{calendar_id}/activate")
async def activate_calendar(
    calendar_id: str,
    db: Session = Depends(get_db),
):
    """Activate a calendar."""
    service = ContentCalendarService(db)
    if not service.activate_calendar(calendar_id):
        raise HTTPException(status_code=404, detail="Calendar not found")
    return {"success": True}


@router.post("/calendars/{calendar_id}/pause")
async def pause_calendar(
    calendar_id: str,
    db: Session = Depends(get_db),
):
    """Pause a calendar."""
    service = ContentCalendarService(db)
    if not service.pause_calendar(calendar_id):
        raise HTTPException(status_code=404, detail="Calendar not found")
    return {"success": True}


@router.post("/calendars/{calendar_id}/generate-briefs")
async def generate_calendar_briefs(
    calendar_id: str,
    regenerate: bool = False,
    db: Session = Depends(get_db),
):
    """Generate or regenerate briefs for a calendar."""
    service = ContentCalendarService(db)
    count = service.generate_calendar_briefs(calendar_id, regenerate)
    return {"success": True, "briefs_created": count}


@router.delete("/calendars/{calendar_id}")
async def delete_calendar(
    calendar_id: str,
    delete_briefs: bool = False,
    db: Session = Depends(get_db),
):
    """Delete a calendar."""
    service = ContentCalendarService(db)
    if not service.delete_calendar(calendar_id, delete_briefs):
        raise HTTPException(status_code=404, detail="Calendar not found")
    return {"success": True}


# ============================================================================
# BRIEF ENDPOINTS
# ============================================================================

@router.post("/briefs")
async def create_brief(
    request: BriefCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Create a new content brief."""
    user_id = current_user.id
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = ContentCalendarService(db)

    # Parse time if provided
    scheduled_time = None
    if request.scheduled_time:
        try:
            parts = request.scheduled_time.split(":")
            scheduled_time = time(int(parts[0]), int(parts[1]))
        except (ValueError, TypeError, IndexError):
            pass

    brief = ContentBrief(
        calendar_id=request.calendar_id,
        user_id=user_id,
        organization_id=organization_id,
        scheduled_date=request.scheduled_date,
        scheduled_time=scheduled_time,
        channels=request.channels,
        topic=request.topic,
        archetype=request.archetype,
        primary_keyword=request.primary_keyword,
        secondary_keywords=request.secondary_keywords,
        target_word_count=request.target_word_count,
        target_audience=request.target_audience,
        key_points=request.key_points,
        call_to_action=request.call_to_action,
        personalization_type=request.personalization_type,
        personalization_segment=request.personalization_segment,
        status="planned",
    )

    db.add(brief)
    db.commit()
    db.refresh(brief)

    return {"success": True, "brief_id": brief.id}


@router.get("/briefs")
async def list_briefs(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    calendar_id: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    channel: Optional[str] = None,
):
    """List content briefs."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = ContentCalendarService(db)
    briefs = service.list_briefs(
        calendar_id=calendar_id,
        organization_id=organization_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        channel=channel,
    )
    return {
        "briefs": [
            {
                "id": b.id,
                "calendar_id": b.calendar_id,
                "scheduled_date": b.scheduled_date.isoformat() if b.scheduled_date else None,
                "scheduled_time": b.scheduled_time.strftime("%H:%M") if b.scheduled_time else None,
                "channels": b.channels,
                "title": b.title or b.topic,
                "topic": b.topic,
                "archetype": b.archetype,
                "status": b.status,
                "primary_keyword": b.primary_keyword,
                "assigned_to": b.assigned_to,
            }
            for b in briefs
        ]
    }


@router.get("/briefs/upcoming")
async def get_upcoming_briefs(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    days_ahead: int = 7,
    status: Optional[str] = None,
):
    """Get upcoming briefs."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = ContentCalendarService(db)
    briefs = service.get_upcoming_briefs(organization_id, days_ahead, status)
    return {
        "briefs": [
            {
                "id": b.id,
                "scheduled_date": b.scheduled_date.isoformat() if b.scheduled_date else None,
                "scheduled_time": b.scheduled_time.strftime("%H:%M") if b.scheduled_time else None,
                "channels": b.channels,
                "title": b.title or b.topic,
                "status": b.status,
            }
            for b in briefs
        ]
    }


@router.get("/briefs/{brief_id}")
async def get_brief(
    brief_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific brief."""
    service = ContentCalendarService(db)
    brief = service.get_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")

    return {
        "id": brief.id,
        "calendar_id": brief.calendar_id,
        "scheduled_date": brief.scheduled_date.isoformat() if brief.scheduled_date else None,
        "scheduled_time": brief.scheduled_time.strftime("%H:%M") if brief.scheduled_time else None,
        "channels": brief.channels,
        "title": brief.title,
        "topic": brief.topic,
        "archetype": brief.archetype,
        "primary_keyword": brief.primary_keyword,
        "secondary_keywords": brief.secondary_keywords,
        "target_word_count": brief.target_word_count,
        "target_audience": brief.target_audience,
        "key_points": brief.key_points,
        "call_to_action": brief.call_to_action,
        "personalization_type": brief.personalization_type,
        "personalization_segment": brief.personalization_segment,
        "status": brief.status,
        "assigned_to": brief.assigned_to,
        "generated_title": brief.generated_title,
        "generated_content": brief.generated_content,
        "generated_at": brief.generated_at.isoformat() if brief.generated_at else None,
        "published_at": brief.published_at.isoformat() if brief.published_at else None,
    }


@router.put("/briefs/{brief_id}")
async def update_brief(
    brief_id: str,
    request: BriefUpdate,
    db: Session = Depends(get_db),
):
    """Update a brief."""
    service = ContentCalendarService(db)

    updates = request.model_dump(exclude_unset=True)

    # Parse time if provided
    if "scheduled_time" in updates and updates["scheduled_time"]:
        try:
            parts = updates["scheduled_time"].split(":")
            updates["scheduled_time"] = time(int(parts[0]), int(parts[1]))
        except (ValueError, TypeError, IndexError):
            del updates["scheduled_time"]

    brief = service.update_brief(brief_id, updates)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    return {"success": True, "brief_id": brief.id}


@router.delete("/briefs/{brief_id}")
async def delete_brief(
    brief_id: str,
    db: Session = Depends(get_db),
):
    """Delete a brief."""
    service = ContentCalendarService(db)
    if not service.delete_brief(brief_id):
        raise HTTPException(status_code=404, detail="Brief not found")
    return {"success": True}


# ============================================================================
# COMMENT ENDPOINTS
# ============================================================================

@router.post("/comments")
async def add_comment(
    request: CommentCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Add a comment to a brief or content item."""
    user_id = current_user.id
    service = ContentCollaborationService(db)
    result = service.add_comment(
        user_id=user_id,
        content=request.content,
        brief_id=request.brief_id,
        content_item_id=request.content_item_id,
        comment_type=request.comment_type,
        parent_comment_id=request.parent_comment_id,
        highlighted_text=request.highlighted_text,
        position_start=request.position_start,
        position_end=request.position_end,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/comments")
async def list_comments(
    db: Session = Depends(get_db),
    brief_id: Optional[str] = None,
    content_item_id: Optional[str] = None,
    include_resolved: bool = False,
):
    """List comments for a brief or content item."""
    service = ContentCollaborationService(db)
    comments = service.list_comments(
        brief_id=brief_id,
        content_item_id=content_item_id,
        include_resolved=include_resolved,
    )
    return {
        "comments": [
            {
                "id": c.id,
                "user_id": c.user_id,
                "content": c.content,
                "comment_type": c.comment_type,
                "highlighted_text": c.highlighted_text,
                "resolved": c.resolved,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in comments
        ]
    }


@router.get("/comments/{comment_id}/thread")
async def get_comment_thread(
    comment_id: str,
    db: Session = Depends(get_db),
):
    """Get a comment thread with all replies."""
    service = ContentCollaborationService(db)
    thread = service.get_comment_thread(comment_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Comment not found")
    return thread


@router.post("/comments/{comment_id}/resolve")
async def resolve_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Resolve a comment."""
    user_id = current_user.id
    service = ContentCollaborationService(db)
    if not service.resolve_comment(comment_id, user_id):
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"success": True}


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    db: Session = Depends(get_db),
):
    """Delete a comment."""
    service = ContentCollaborationService(db)
    if not service.delete_comment(comment_id):
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"success": True}


# ============================================================================
# APPROVAL ENDPOINTS
# ============================================================================

@router.post("/approvals")
async def request_approval(
    request: ApprovalRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Request an approval."""
    user_id = current_user.id
    service = ContentCollaborationService(db)
    result = service.request_approval(
        workflow_stage=request.workflow_stage,
        requested_by=user_id,
        assigned_to=request.assigned_to,
        brief_id=request.brief_id,
        content_item_id=request.content_item_id,
        due_date=request.due_date,
        content_snapshot=request.content_snapshot,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/approvals")
async def list_approvals(
    db: Session = Depends(get_db),
    brief_id: Optional[str] = None,
    assigned_to: Optional[int] = None,
    status: Optional[str] = None,
):
    """List approvals."""
    service = ContentCollaborationService(db)
    approvals = service.list_approvals(
        brief_id=brief_id,
        assigned_to=assigned_to,
        status=status,
    )
    return {
        "approvals": [
            {
                "id": a.id,
                "brief_id": a.brief_id,
                "workflow_stage": a.workflow_stage,
                "status": a.status,
                "assigned_to": a.assigned_to,
                "requested_by": a.requested_by,
                "decision_by": a.decision_by,
                "decision_at": a.decision_at.isoformat() if a.decision_at else None,
                "due_date": a.due_date.isoformat() if a.due_date else None,
            }
            for a in approvals
        ]
    }


@router.get("/approvals/pending")
async def get_pending_approvals(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get pending approvals for a user."""
    user_id = current_user.id
    service = ContentCollaborationService(db)
    approvals = service.get_pending_approvals(user_id)
    return {
        "approvals": [
            {
                "id": a.id,
                "brief_id": a.brief_id,
                "workflow_stage": a.workflow_stage,
                "due_date": a.due_date.isoformat() if a.due_date else None,
            }
            for a in approvals
        ]
    }


@router.post("/approvals/{approval_id}/approve")
async def approve_request(
    approval_id: str,
    request: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Approve a request."""
    user_id = current_user.id
    service = ContentCollaborationService(db)
    result = service.approve(approval_id, user_id, request.decision_notes)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/approvals/{approval_id}/reject")
async def reject_request(
    approval_id: str,
    request: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Reject a request."""
    user_id = current_user.id
    if not request.decision_notes:
        raise HTTPException(status_code=400, detail="Rejection requires notes")
    service = ContentCollaborationService(db)
    result = service.reject(approval_id, user_id, request.decision_notes)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/approvals/{approval_id}/request-changes")
async def request_changes(
    approval_id: str,
    request: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Request changes on a submission."""
    user_id = current_user.id
    if not request.decision_notes:
        raise HTTPException(status_code=400, detail="Change request requires notes")
    service = ContentCollaborationService(db)
    result = service.request_changes(approval_id, user_id, request.decision_notes)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/briefs/{brief_id}/workflow")
async def start_approval_workflow(
    brief_id: str,
    request: WorkflowStart,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Start an approval workflow for a brief."""
    user_id = current_user.id
    service = ContentCollaborationService(db)
    stages = [
        {"stage": s.stage, "assigned_to": s.assigned_to, "due_date": s.due_date}
        for s in request.stages
    ]
    result = service.start_approval_workflow(brief_id, user_id, stages)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/briefs/{brief_id}/workflow")
async def get_workflow_status(
    brief_id: str,
    db: Session = Depends(get_db),
):
    """Get workflow status for a brief."""
    service = ContentCollaborationService(db)
    return service.get_workflow_status(brief_id)


# ============================================================================
# KEYWORD ENDPOINTS
# ============================================================================

@router.post("/keywords")
async def add_keyword(
    request: KeywordCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Add a keyword to track."""
    user_id = current_user.id
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = SEOKeywordService(db)
    result = service.add_keyword(
        keyword=request.keyword,
        user_id=user_id,
        organization_id=organization_id,
        category=request.category,
        search_volume=request.search_volume,
        difficulty_score=request.difficulty_score,
        target_ranking=request.target_ranking,
        priority=request.priority,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/keywords")
async def list_keywords(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    category: Optional[str] = None,
    status: Optional[str] = None,
    min_volume: Optional[int] = None,
    sort_by: str = "priority",
):
    """List tracked keywords."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = SEOKeywordService(db)
    keywords = service.list_keywords(
        organization_id=organization_id,
        category=category,
        status=status,
        min_volume=min_volume,
        sort_by=sort_by,
    )
    return {
        "keywords": [
            {
                "id": k.id,
                "keyword": k.keyword,
                "search_volume": k.search_volume,
                "difficulty_score": k.difficulty_score,
                "current_ranking": k.current_ranking,
                "target_ranking": k.target_ranking,
                "best_ranking": k.best_ranking,
                "category": k.category,
                "intent": k.intent,
                "status": k.status,
                "priority": k.priority,
            }
            for k in keywords
        ]
    }


@router.get("/keywords/analytics")
async def get_keyword_analytics(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get keyword analytics."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = SEOKeywordService(db)
    return service.get_keyword_analytics(organization_id)


@router.get("/keywords/opportunities")
async def get_keyword_opportunities(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get keyword opportunities."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = SEOKeywordService(db)
    return service.get_keyword_opportunities(organization_id)


@router.get("/keywords/changes")
async def get_ranking_changes(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    days: int = 7,
):
    """Get ranking changes over a period."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = SEOKeywordService(db)
    return service.get_ranking_changes(organization_id, days)


@router.get("/keywords/suggest")
async def suggest_keywords(
    seed_keyword: str = Query(...),
    category: Optional[str] = None,
    count: int = 10,
    db: Session = Depends(get_db),
):
    """Get keyword suggestions."""
    service = SEOKeywordService(db)
    suggestions = await service.suggest_keywords(seed_keyword, category, count)
    return {"suggestions": suggestions}


@router.get("/keywords/{keyword_id}")
async def get_keyword(
    keyword_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific keyword."""
    service = SEOKeywordService(db)
    keyword = service.get_keyword(keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")
    return {
        "id": keyword.id,
        "keyword": keyword.keyword,
        "search_volume": keyword.search_volume,
        "difficulty_score": keyword.difficulty_score,
        "current_ranking": keyword.current_ranking,
        "target_ranking": keyword.target_ranking,
        "best_ranking": keyword.best_ranking,
        "category": keyword.category,
        "intent": keyword.intent,
        "status": keyword.status,
        "priority": keyword.priority,
        "ranking_history": keyword.ranking_history,
        "last_checked_at": keyword.last_checked_at.isoformat() if keyword.last_checked_at else None,
    }


@router.put("/keywords/{keyword_id}")
async def update_keyword(
    keyword_id: str,
    request: KeywordUpdate,
    db: Session = Depends(get_db),
):
    """Update a keyword."""
    service = SEOKeywordService(db)
    keyword = service.update_keyword(
        keyword_id,
        request.model_dump(exclude_unset=True)
    )
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")
    return {"success": True, "keyword_id": keyword.id}


@router.post("/keywords/{keyword_id}/ranking")
async def update_ranking(
    keyword_id: str,
    request: RankingUpdate,
    db: Session = Depends(get_db),
):
    """Update ranking for a keyword."""
    service = SEOKeywordService(db)
    result = service.update_ranking(keyword_id, request.ranking, request.url)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/keywords/rankings/bulk")
async def bulk_update_rankings(
    request: BulkRankingUpdate,
    db: Session = Depends(get_db),
):
    """Bulk update rankings."""
    service = SEOKeywordService(db)
    return service.bulk_update_rankings(request.rankings)


@router.delete("/keywords/{keyword_id}")
async def delete_keyword(
    keyword_id: str,
    db: Session = Depends(get_db),
):
    """Archive a keyword."""
    service = SEOKeywordService(db)
    if not service.delete_keyword(keyword_id):
        raise HTTPException(status_code=404, detail="Keyword not found")
    return {"success": True}


@router.post("/keywords/seed")
async def seed_keywords(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Seed database with mortgage industry keywords."""
    user_id = current_user.id
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = SEOKeywordService(db)
    return service.seed_mortgage_keywords(user_id, organization_id)


# ============================================================================
# PERSONALIZATION ENDPOINTS
# ============================================================================

@router.get("/personalization/tokens")
async def get_available_tokens(
    db: Session = Depends(get_db),
    personalization_type: Optional[str] = None,
):
    """Get available personalization tokens."""
    service = ContentPersonalizationService(db)
    tokens = service.get_available_tokens(personalization_type)
    return {"tokens": tokens}


@router.post("/personalization/preview")
async def preview_personalization(
    request: PersonalizationPreview,
    db: Session = Depends(get_db),
):
    """Preview personalized content."""
    service = ContentPersonalizationService(db)
    try:
        result = service.preview_personalization(
            template_text=request.template_text,
            personalization_type=request.personalization_type,
            record_id=request.record_id,
            extra_context=request.extra_context,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")


@router.post("/personalization/batch")
async def batch_personalize(
    request: BatchPersonalization,
    db: Session = Depends(get_db),
):
    """Batch personalize content for multiple records."""
    service = ContentPersonalizationService(db)
    results = service.batch_personalize(
        template_text=request.template_text,
        personalization_type=request.personalization_type,
        record_ids=request.record_ids,
        extra_context=request.extra_context,
    )
    return {"results": results}


@router.post("/personalization/validate")
async def validate_template(
    template_text: str = Body(..., embed=True),
    personalization_type: str = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    """Validate template tokens."""
    service = ContentPersonalizationService(db)
    return service.validate_template_tokens(template_text, personalization_type)


# ============================================================================
# PUBLISHING ENDPOINTS
# ============================================================================

@router.post("/briefs/{brief_id}/publish")
async def publish_brief(
    brief_id: str,
    request: PublishRequest,
    db: Session = Depends(get_db),
):
    """Publish a brief to specified channels."""
    service = ContentPublisherService(db)
    result = await service.publish_brief(
        brief_id=brief_id,
        channels=request.channels,
        publish_now=request.publish_now,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/briefs/{brief_id}/schedule")
async def schedule_brief(
    brief_id: str,
    request: ScheduleRequest,
    db: Session = Depends(get_db),
):
    """Schedule a brief for future publishing."""
    service = ContentPublisherService(db)
    result = await service.schedule_brief(
        brief_id=brief_id,
        scheduled_datetime=request.scheduled_datetime,
        channels=request.channels,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/publish/scheduled")
async def get_scheduled_content(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    """Get scheduled content."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = ContentPublisherService(db)
    logs = service.get_scheduled_content(organization_id, start_date, end_date)
    return {
        "scheduled": [
            {
                "id": l.id,
                "brief_id": l.brief_id,
                "channel": l.channel,
                "scheduled_at": l.scheduled_at.isoformat() if l.scheduled_at else None,
                "status": l.status,
            }
            for l in logs
        ]
    }


@router.post("/publish/process")
async def process_scheduled(
    db: Session = Depends(get_db),
):
    """Process all pending scheduled publications."""
    service = ContentPublisherService(db)
    return await service.process_scheduled_publications()


@router.get("/publish/analytics")
async def get_publishing_analytics(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    days: int = 30,
):
    """Get publishing analytics."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    service = ContentPublisherService(db)
    return service.get_publishing_analytics(organization_id, days)


@router.get("/briefs/{brief_id}/engagement")
async def get_brief_engagement(
    brief_id: str,
    db: Session = Depends(get_db),
):
    """Get engagement metrics for a published brief."""
    service = ContentPublisherService(db)
    return await service.fetch_engagement_metrics(brief_id)


@router.get("/publish/logs")
async def list_publish_logs(
    db: Session = Depends(get_db),
    brief_id: Optional[str] = None,
    channel: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    """List publish logs."""
    service = ContentPublisherService(db)
    logs = service.list_publish_logs(brief_id, channel, status, limit)
    return {
        "logs": [
            {
                "id": l.id,
                "brief_id": l.brief_id,
                "channel": l.channel,
                "status": l.status,
                "scheduled_at": l.scheduled_at.isoformat() if l.scheduled_at else None,
                "published_at": l.published_at.isoformat() if l.published_at else None,
                "external_post_id": l.external_post_id,
                "external_url": l.external_url,
                "error_message": l.error_message,
                "views": l.views,
                "likes": l.likes,
                "comments": l.comments,
                "shares": l.shares,
            }
            for l in logs
        ]
    }


@router.post("/publish/logs/{log_id}/retry")
async def retry_publication(
    log_id: str,
    db: Session = Depends(get_db),
):
    """Retry a failed publication."""
    service = ContentPublisherService(db)
    result = await service.retry_failed_publication(log_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/publish/logs/{log_id}/cancel")
async def cancel_scheduled(
    log_id: str,
    db: Session = Depends(get_db),
):
    """Cancel a scheduled publication."""
    service = ContentPublisherService(db)
    if not service.cancel_scheduled_publication(log_id):
        raise HTTPException(status_code=404, detail="Log not found or not scheduled")
    return {"success": True}


# ============================================================================
# TEMPLATES ENDPOINT
# ============================================================================

@router.get("/templates")
async def list_templates(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    category: Optional[str] = None,
    template_type: Optional[str] = None,
    active_only: bool = True,
):
    """List content templates."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    organization_id = org_id
    query = db.query(ContentTemplate).filter(
        ContentTemplate.organization_id == organization_id
    )

    if active_only:
        query = query.filter(ContentTemplate.is_active == True)
    if category:
        query = query.filter(ContentTemplate.category == category)
    if template_type:
        query = query.filter(ContentTemplate.template_type == template_type)

    templates = query.order_by(ContentTemplate.category, ContentTemplate.name).all()

    return {
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "template_type": t.template_type,
                "archetype": t.archetype,
                "available_tokens": t.available_tokens,
                "estimated_word_count": t.estimated_word_count,
                "is_system": t.is_system,
                "times_used": t.times_used,
            }
            for t in templates
        ]
    }


@router.get("/templates/{template_id}")
async def get_template(
    template_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific template."""
    template = db.query(ContentTemplate).filter(
        ContentTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "category": template.category,
        "template_type": template.template_type,
        "title_template": template.title_template,
        "body_template": template.body_template,
        "available_tokens": template.available_tokens,
        "required_tokens": template.required_tokens,
        "archetype": template.archetype,
        "default_keywords": template.default_keywords,
        "includes_disclosure": template.includes_disclosure,
        "disclosure_text": template.disclosure_text,
    }
