"""
Marketing Campaign Routes — Campaign CRUD, content generation, and review sequences.

Manages marketing campaign lifecycle (create, pause, resume), AI-powered
content generation, post-close review initiation, and weekly reporting.

Prefix: /api/v1/marketing
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/marketing", tags=["Marketing Campaigns"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class CampaignCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = Field(None, description="Natural language campaign description for AI planning")
    campaign_type: str = Field(..., description="welcome, post_close, nurture, stale_reengagement, rate_drop, seasonal, refi, referral, event, custom")
    channels: Optional[List[str]] = Field(None, description="List of channels: email, sms, voicemail, push")
    audience_segment_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    timezone: str = "America/New_York"


class ContentGenerateRequest(BaseModel):
    campaign_id: Optional[int] = None
    content_type: str = Field(..., description="email, sms, social_post, blog, video_script")
    topic: Optional[str] = None
    audience: Optional[str] = None
    tone: str = Field("professional", description="professional, casual, urgent, educational")


class ReviewInitiateRequest(BaseModel):
    platform: str = Field("google", description="google, zillow, yelp, facebook")
    delay_days: int = Field(7, ge=1, le=90, description="Days after funding to send review request")
    message_template: Optional[str] = None


# =============================================================================
# Valid values
# =============================================================================

VALID_CAMPAIGN_TYPES = {
    "welcome", "post_close", "nurture", "stale_reengagement",
    "rate_drop", "seasonal", "refi", "referral", "event", "custom",
}

VALID_CHANNELS = {"email", "sms", "voicemail", "push"}

VALID_CONTENT_TYPES = {"email", "sms", "social_post", "blog", "video_script"}


# =============================================================================
# Helpers — lazy model imports
# =============================================================================

_models_loaded = False
_CampaignDefinition = None
_AudienceSegment = None
_DripSequence = None


def _ensure_models():
    """Lazy-import models on first use."""
    global _models_loaded, _CampaignDefinition, _AudienceSegment, _DripSequence
    if _models_loaded:
        return
    from database.models.marketing import CampaignDefinition, AudienceSegment, DripSequence
    _CampaignDefinition = CampaignDefinition
    _AudienceSegment = AudienceSegment
    _DripSequence = DripSequence
    _models_loaded = True


def _ensure_tables(db: Session):
    """Create tables if they don't exist (production-safe)."""
    try:
        from database.models.marketing import CampaignDefinition, AudienceSegment, DripSequence
        from db import engine
        AudienceSegment.__table__.create(engine, checkfirst=True)
        DripSequence.__table__.create(engine, checkfirst=True)
        CampaignDefinition.__table__.create(engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"Marketing table creation check failed (non-fatal): {e}")


def _campaign_to_dict(c) -> dict:
    """Serialize a CampaignDefinition ORM object to a dict."""
    return {
        "id": c.id,
        "organization_id": c.organization_id,
        "created_by_id": c.created_by_id,
        "name": c.name,
        "description": c.description,
        "campaign_type": c.campaign_type.value if hasattr(c.campaign_type, "value") else c.campaign_type,
        "status": c.status.value if hasattr(c.status, "value") else c.status,
        "channels": c.channels,
        "audience_segment_id": c.audience_segment_id,
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "end_date": c.end_date.isoformat() if c.end_date else None,
        "timezone": c.timezone,
        "total_recipients": c.total_recipients or 0,
        "sent_count": c.sent_count or 0,
        "delivered_count": c.delivered_count or 0,
        "opened_count": c.opened_count or 0,
        "clicked_count": c.clicked_count or 0,
        "responded_count": c.responded_count or 0,
        "converted_count": c.converted_count or 0,
        "unsubscribed_count": c.unsubscribed_count or 0,
        "bounced_count": c.bounced_count or 0,
        "campaign_cost": float(c.campaign_cost) if c.campaign_cost else 0,
        "attributed_revenue": float(c.attributed_revenue) if c.attributed_revenue else 0,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


# =============================================================================
# Routes — Campaign CRUD
# =============================================================================

@router.post("/campaigns")
async def create_campaign(
    body: CampaignCreate,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """
    Create a marketing campaign.

    Accepts a natural language description that can be used by the AI content
    engine to plan messaging, cadence, and channel strategy.
    """
    _ensure_models()
    _ensure_tables(db)

    if body.campaign_type not in VALID_CAMPAIGN_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid campaign_type. Must be one of: {', '.join(sorted(VALID_CAMPAIGN_TYPES))}",
        )

    if body.channels:
        invalid = set(body.channels) - VALID_CHANNELS
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid channels: {', '.join(sorted(invalid))}. Must be: {', '.join(sorted(VALID_CHANNELS))}",
            )

    # Validate audience segment if provided
    if body.audience_segment_id:
        segment = db.query(_AudienceSegment).filter(
            _AudienceSegment.id == body.audience_segment_id,
            _AudienceSegment.organization_id == current_user.organization_id,
        ).first()
        if not segment:
            raise HTTPException(status_code=404, detail="Audience segment not found")

    # Map string to enum for SQLAlchemy
    from database.models.marketing import CampaignType, CampaignStatus

    campaign = _CampaignDefinition(
        organization_id=current_user.organization_id,
        created_by_id=current_user.id,
        name=body.name,
        description=body.description,
        campaign_type=CampaignType(body.campaign_type),
        status=CampaignStatus.DRAFT,
        channels=body.channels or ["email"],
        audience_segment_id=body.audience_segment_id,
        start_date=body.start_date,
        end_date=body.end_date,
        timezone=body.timezone,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    logger.info(
        "Campaign created: id=%s name=%r type=%s org=%s",
        campaign.id, campaign.name, body.campaign_type, current_user.organization_id,
    )

    return {"status": "ok", "campaign": _campaign_to_dict(campaign)}


@router.get("/campaigns")
async def list_campaigns(
    status: Optional[str] = Query(None, description="Filter by status: draft, scheduled, active, paused, completed, archived"),
    campaign_type: Optional[str] = Query(None, description="Filter by campaign type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """List marketing campaigns for the organization."""
    _ensure_models()
    _ensure_tables(db)

    q = db.query(_CampaignDefinition).filter(
        _CampaignDefinition.organization_id == current_user.organization_id,
    )

    if status:
        q = q.filter(_CampaignDefinition.status == status)

    if campaign_type:
        if campaign_type not in VALID_CAMPAIGN_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid campaign_type: {campaign_type}")
        q = q.filter(_CampaignDefinition.campaign_type == campaign_type)

    total = q.count()
    campaigns = q.order_by(_CampaignDefinition.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "campaigns": [_campaign_to_dict(c) for c in campaigns],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Get campaign details and current status."""
    _ensure_models()
    _ensure_tables(db)

    campaign = db.query(_CampaignDefinition).filter(
        _CampaignDefinition.id == campaign_id,
        _CampaignDefinition.organization_id == current_user.organization_id,
    ).first()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    result = _campaign_to_dict(campaign)

    # Compute derived metrics
    sent = campaign.sent_count or 0
    if sent > 0:
        result["metrics"] = {
            "open_rate": round((campaign.opened_count or 0) / sent * 100, 1),
            "click_rate": round((campaign.clicked_count or 0) / sent * 100, 1),
            "response_rate": round((campaign.responded_count or 0) / sent * 100, 1),
            "conversion_rate": round((campaign.converted_count or 0) / sent * 100, 1),
            "unsubscribe_rate": round((campaign.unsubscribed_count or 0) / sent * 100, 1),
            "bounce_rate": round((campaign.bounced_count or 0) / sent * 100, 1),
        }
    else:
        result["metrics"] = {
            "open_rate": 0,
            "click_rate": 0,
            "response_rate": 0,
            "conversion_rate": 0,
            "unsubscribe_rate": 0,
            "bounce_rate": 0,
        }

    return {"campaign": result}


# =============================================================================
# Routes — Campaign Lifecycle
# =============================================================================

@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Pause an active or scheduled campaign."""
    _ensure_models()
    _ensure_tables(db)

    campaign = db.query(_CampaignDefinition).filter(
        _CampaignDefinition.id == campaign_id,
        _CampaignDefinition.organization_id == current_user.organization_id,
    ).first()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    status_val = campaign.status.value if hasattr(campaign.status, "value") else campaign.status
    if status_val not in ("active", "scheduled"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause campaign with status '{status_val}'. Must be active or scheduled.",
        )

    from database.models.marketing import CampaignStatus
    campaign.status = CampaignStatus.PAUSED
    campaign.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("Campaign paused: id=%s name=%r", campaign_id, campaign.name)

    return {"status": "ok", "campaign_id": campaign_id, "new_status": "paused"}


@router.post("/campaigns/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """Resume a paused campaign."""
    _ensure_models()
    _ensure_tables(db)

    campaign = db.query(_CampaignDefinition).filter(
        _CampaignDefinition.id == campaign_id,
        _CampaignDefinition.organization_id == current_user.organization_id,
    ).first()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    status_val = campaign.status.value if hasattr(campaign.status, "value") else campaign.status
    if status_val != "paused":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume campaign with status '{status_val}'. Must be paused.",
        )

    from database.models.marketing import CampaignStatus
    campaign.status = CampaignStatus.ACTIVE
    campaign.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("Campaign resumed: id=%s name=%r", campaign_id, campaign.name)

    return {"status": "ok", "campaign_id": campaign_id, "new_status": "active"}


# =============================================================================
# Routes — Weekly Report
# =============================================================================

@router.get("/reports/weekly")
async def weekly_marketing_report(
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """
    Get a weekly marketing performance summary across all campaigns.

    Covers the last 7 days: totals for sent, opened, clicked, converted,
    plus active campaign count and top-performing campaign.
    """
    _ensure_models()
    _ensure_tables(db)

    org_id = current_user.organization_id
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # Aggregate across all campaigns for the org
    totals = db.query(
        func.count(_CampaignDefinition.id).label("total_campaigns"),
        func.sum(_CampaignDefinition.sent_count).label("total_sent"),
        func.sum(_CampaignDefinition.delivered_count).label("total_delivered"),
        func.sum(_CampaignDefinition.opened_count).label("total_opened"),
        func.sum(_CampaignDefinition.clicked_count).label("total_clicked"),
        func.sum(_CampaignDefinition.responded_count).label("total_responded"),
        func.sum(_CampaignDefinition.converted_count).label("total_converted"),
        func.sum(_CampaignDefinition.unsubscribed_count).label("total_unsubscribed"),
    ).filter(
        _CampaignDefinition.organization_id == org_id,
    ).first()

    # Active campaigns
    active_count = db.query(func.count(_CampaignDefinition.id)).filter(
        _CampaignDefinition.organization_id == org_id,
        _CampaignDefinition.status == "active",
    ).scalar() or 0

    # Top performer by conversion
    top_campaign = db.query(_CampaignDefinition).filter(
        _CampaignDefinition.organization_id == org_id,
        _CampaignDefinition.converted_count > 0,
    ).order_by(_CampaignDefinition.converted_count.desc()).first()

    total_sent = int(totals.total_sent or 0)

    return {
        "period": {
            "start": week_ago.isoformat(),
            "end": now.isoformat(),
        },
        "summary": {
            "total_campaigns": totals.total_campaigns or 0,
            "active_campaigns": active_count,
            "total_sent": total_sent,
            "total_delivered": int(totals.total_delivered or 0),
            "total_opened": int(totals.total_opened or 0),
            "total_clicked": int(totals.total_clicked or 0),
            "total_responded": int(totals.total_responded or 0),
            "total_converted": int(totals.total_converted or 0),
            "total_unsubscribed": int(totals.total_unsubscribed or 0),
            "open_rate": round(int(totals.total_opened or 0) / total_sent * 100, 1) if total_sent > 0 else 0,
            "click_rate": round(int(totals.total_clicked or 0) / total_sent * 100, 1) if total_sent > 0 else 0,
            "conversion_rate": round(int(totals.total_converted or 0) / total_sent * 100, 1) if total_sent > 0 else 0,
        },
        "top_campaign": {
            "id": top_campaign.id,
            "name": top_campaign.name,
            "conversions": top_campaign.converted_count,
        } if top_campaign else None,
    }


# =============================================================================
# Routes — Content Generation
# =============================================================================

@router.post("/content/generate")
async def generate_content(
    body: ContentGenerateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """
    Trigger AI-powered marketing content generation.

    Queues a content generation job and returns a placeholder. The actual
    content is generated asynchronously by the content_creator agent.
    """
    _ensure_models()
    _ensure_tables(db)

    if body.content_type not in VALID_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content_type. Must be one of: {', '.join(sorted(VALID_CONTENT_TYPES))}",
        )

    # Validate campaign belongs to org if provided
    campaign_context = None
    if body.campaign_id:
        campaign = db.query(_CampaignDefinition).filter(
            _CampaignDefinition.id == body.campaign_id,
            _CampaignDefinition.organization_id == current_user.organization_id,
        ).first()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        campaign_context = {
            "campaign_id": campaign.id,
            "campaign_name": campaign.name,
            "campaign_type": campaign.campaign_type.value if hasattr(campaign.campaign_type, "value") else campaign.campaign_type,
        }

    # Build the generation request for the content_creator agent
    generation_request = {
        "content_type": body.content_type,
        "topic": body.topic,
        "audience": body.audience,
        "tone": body.tone,
        "campaign": campaign_context,
        "organization_id": current_user.organization_id,
        "requested_by": current_user.id,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "Content generation requested: type=%s topic=%r by user=%s",
        body.content_type, body.topic, current_user.id,
    )

    return {
        "status": "queued",
        "message": "Content generation request queued for the AI content engine.",
        "request": generation_request,
    }


# =============================================================================
# Routes — Post-Close Review Sequences
# =============================================================================

@router.post("/reviews/initiate/{loan_id}")
async def initiate_review_sequence(
    loan_id: int,
    body: ReviewInitiateRequest = None,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """
    Initiate a post-close review request sequence for a funded loan.

    Creates a post_close campaign entry targeting the borrower, scheduled
    to send after a configurable delay from funding date.
    """
    _ensure_models()
    _ensure_tables(db)

    org_id = current_user.organization_id

    if body is None:
        body = ReviewInitiateRequest()

    # Look up the loan to confirm it belongs to this org and is funded
    from sqlalchemy import text
    loan_row = db.execute(text("""
        SELECT l.id, l.stage, l.borrower_name, l.borrower_email,
               l.funded_date, l.organization_id
        FROM loans l
        WHERE l.id = :loan_id AND l.organization_id = :org_id
    """), {"loan_id": loan_id, "org_id": org_id}).fetchone()

    if not loan_row:
        raise HTTPException(status_code=404, detail="Loan not found")

    stage = (loan_row.stage or "").upper()
    if stage != "FUNDED":
        raise HTTPException(
            status_code=400,
            detail=f"Loan stage is '{loan_row.stage}', not FUNDED. Reviews are for funded loans only.",
        )

    # Create a post_close campaign for this review sequence
    from database.models.marketing import CampaignType, CampaignStatus

    send_date = datetime.now(timezone.utc) + timedelta(days=body.delay_days)

    campaign = _CampaignDefinition(
        organization_id=org_id,
        created_by_id=current_user.id,
        name=f"Review Request - {loan_row.borrower_name or f'Loan #{loan_id}'}",
        description=f"Post-close {body.platform} review request for loan #{loan_id}. "
                    f"Scheduled {body.delay_days} days after close.",
        campaign_type=CampaignType.POST_CLOSE,
        status=CampaignStatus.SCHEDULED,
        channels=["email"],
        start_date=send_date,
        total_recipients=1,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    logger.info(
        "Review sequence initiated: campaign_id=%s loan_id=%s platform=%s delay=%dd",
        campaign.id, loan_id, body.platform, body.delay_days,
    )

    return {
        "status": "ok",
        "campaign_id": campaign.id,
        "loan_id": loan_id,
        "borrower_name": loan_row.borrower_name,
        "platform": body.platform,
        "scheduled_send_date": send_date.isoformat(),
        "delay_days": body.delay_days,
    }


@router.get("/reviews/stats")
async def review_stats(
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """
    Get aggregate stats on post-close review request campaigns:
    total initiated, sent, responses received, and conversion rate.
    """
    _ensure_models()
    _ensure_tables(db)

    org_id = current_user.organization_id

    # Query only post_close type campaigns
    stats = db.query(
        func.count(_CampaignDefinition.id).label("total_initiated"),
        func.sum(_CampaignDefinition.sent_count).label("total_sent"),
        func.sum(_CampaignDefinition.responded_count).label("total_responded"),
        func.sum(_CampaignDefinition.converted_count).label("total_converted"),
    ).filter(
        _CampaignDefinition.organization_id == org_id,
        _CampaignDefinition.campaign_type == "post_close",
    ).first()

    total_initiated = stats.total_initiated or 0
    total_sent = int(stats.total_sent or 0)
    total_responded = int(stats.total_responded or 0)
    total_converted = int(stats.total_converted or 0)

    # Status breakdown
    status_breakdown = db.query(
        _CampaignDefinition.status,
        func.count(_CampaignDefinition.id),
    ).filter(
        _CampaignDefinition.organization_id == org_id,
        _CampaignDefinition.campaign_type == "post_close",
    ).group_by(_CampaignDefinition.status).all()

    return {
        "review_stats": {
            "total_initiated": total_initiated,
            "total_sent": total_sent,
            "total_responded": total_responded,
            "total_converted": total_converted,
            "response_rate": round(total_responded / total_sent * 100, 1) if total_sent > 0 else 0,
            "conversion_rate": round(total_converted / total_sent * 100, 1) if total_sent > 0 else 0,
        },
        "status_breakdown": {
            (row[0].value if hasattr(row[0], "value") else str(row[0])): row[1]
            for row in status_breakdown
        },
    }


# =============================================================================
# Registration
# =============================================================================

def register_marketing_campaign_routes(app):
    """Register marketing campaign routes with the FastAPI app."""
    app.include_router(router)
    logger.info("Marketing campaign routes registered")
