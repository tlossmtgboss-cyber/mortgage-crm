"""
Acquisition Engine API Routes
Perennia AI - Client Acquisition Engine

Provides endpoints for:
- Campaign management (launch, pause, resume)
- Event ingestion
- Lead temperature retrieval
- Dashboard and attribution
- Speed-to-lead metrics
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import logging

from database import get_db

from models.acquisition_engine.campaign_models import (
    CampaignBlueprint,
    CampaignInstance,
    GoalType,
    CampaignStatus,
)
from models.acquisition_engine.event_models import AcquisitionEvent, EventType
from models.acquisition_engine.scoring_models import LeadTemperature, Temperature, CampaignAttribution

from services.acquisition_engine.event_service import EventService
from services.acquisition_engine.temperature_service import TemperatureService
from services.acquisition_engine.speed_to_lead_service import SpeedToLeadService, SpeedToLeadConfig
from services.acquisition_engine.conversion_orchestrator import ConversionOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/acquisition", tags=["acquisition-engine"])


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class CampaignLaunchRequest(BaseModel):
    """Request to launch a new campaign"""
    goal_type: str = Field(..., description="Campaign goal type: PURCHASE_BUYERS, REFI_PROSPECTS, etc.")
    budget_type: str = Field(default="DAILY", description="Budget period: DAILY, WEEKLY, MONTHLY, TOTAL")
    budget_amount: float = Field(..., description="Budget amount in dollars")
    market_geo: Dict[str, Any] = Field(..., description="Geographic targeting")
    product_focus: Optional[str] = Field(None, description="PURCHASE, REFINANCE, or BOTH")
    capacity_leads_per_week: Optional[int] = Field(None, description="Maximum leads per week")
    name: Optional[str] = Field(None, description="Campaign name (auto-generated if not provided)")
    blueprint_id: Optional[str] = Field(None, description="Specific blueprint ID to use")


class CampaignResponse(BaseModel):
    """Campaign instance response"""
    id: str
    name: Optional[str]
    goal_type: str
    status: str
    budget_type: str
    budget_amount: float
    market_geo: Dict[str, Any]
    created_at: datetime
    activated_at: Optional[datetime]
    leads_generated: int
    meetings_booked: int
    applications_started: int
    loans_closed: int
    total_spend: float
    revenue_attributed: float
    cost_per_lead: Optional[float]
    cost_per_funded_loan: Optional[float]
    roi_percentage: Optional[float]


class EventIngestRequest(BaseModel):
    """Request to ingest an event"""
    event_type: str = Field(..., description="Event type from EventType enum")
    event_payload: Optional[Dict[str, Any]] = Field(None, description="Event-specific data")
    lead_id: Optional[int] = Field(None, description="Lead ID if known")
    anonymous_visitor_id: Optional[str] = Field(None, description="Anonymous visitor ID")
    campaign_instance_id: Optional[str] = Field(None, description="Campaign that sourced this event")
    session_id: Optional[str] = Field(None, description="Browser session ID")
    source: Optional[str] = Field(None, description="Event source: funnel, sms, email, call")
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_term: Optional[str] = None
    utm_content: Optional[str] = None


class EventResponse(BaseModel):
    """Event response"""
    id: str
    event_type: str
    lead_id: Optional[int]
    anonymous_visitor_id: Optional[str]
    campaign_instance_id: Optional[str]
    temperature_impact: int
    is_hot_signal: bool
    event_timestamp: datetime


class TemperatureResponse(BaseModel):
    """Lead temperature response"""
    lead_id: int
    temperature: str
    score: int
    engagement_score: int
    intent_score: int
    recency_score: int
    frequency_score: int
    total_events: int
    total_sessions: int
    last_hot_signal: Optional[str]
    last_hot_signal_at: Optional[datetime]
    days_since_last_activity: int
    last_calculated_at: datetime


class DashboardResponse(BaseModel):
    """Campaign dashboard response"""
    total_campaigns: int
    active_campaigns: int
    total_spend: float
    total_leads: int
    total_meetings: int
    total_applications: int
    total_funded: int
    total_revenue: float
    overall_roi: float
    speed_to_lead_compliance: float
    temperature_distribution: Dict[str, int]
    campaigns: List[CampaignResponse]


class SpeedToLeadMetrics(BaseModel):
    """Speed-to-lead metrics response"""
    total_hot_leads: int
    within_sla: int
    missed_sla: int
    compliance_rate: float
    avg_response_time_seconds: int
    p50_response_time_seconds: int
    p90_response_time_seconds: int


class SpeedToLeadTriggerRequest(BaseModel):
    """Request to manually trigger speed-to-lead for a lead"""
    campaign_instance_id: Optional[str] = Field(None, description="Associated campaign")
    event_type: Optional[str] = Field(None, description="Triggering event type")
    priority: Optional[str] = Field("normal", description="Priority: urgent, high, normal, low")
    skip_sms: bool = Field(False, description="Skip SMS outreach")
    skip_email: bool = Field(False, description="Skip Email outreach")
    skip_dialer: bool = Field(False, description="Skip dialer queue")


class SpeedToLeadTriggerResponse(BaseModel):
    """Response from speed-to-lead trigger"""
    lead_id: int
    success: bool
    sla_met: bool
    response_time_seconds: float
    actions_taken: List[str]
    errors: List[str]
    next_actions: List[Dict[str, Any]]


class ConversionTrackRequest(BaseModel):
    """Request to track a conversion"""
    lead_id: int = Field(..., description="Lead ID")
    conversion_type: str = Field(..., description="lead, meeting, application, funded")
    campaign_instance_id: Optional[str] = Field(None, description="Associated campaign")
    loan_id: Optional[int] = Field(None, description="Loan ID if applicable")
    loan_amount: Optional[float] = Field(None, description="Loan amount for revenue tracking")
    estimated_revenue: Optional[float] = Field(None, description="Estimated revenue")
    attribution_type: Optional[str] = Field("first_touch", description="first_touch, last_touch, linear")


class ConversionTrackResponse(BaseModel):
    """Response from conversion tracking"""
    id: str
    lead_id: int
    conversion_type: str
    campaign_instance_id: Optional[str]
    attribution_credit: float
    conversion_date: datetime


class FunnelMetricsResponse(BaseModel):
    """Funnel metrics response"""
    period_days: int
    funnel: Dict[str, int]
    conversion_rates: Dict[str, float]
    by_campaign: Optional[List[Dict[str, Any]]] = None


# =============================================================================
# CAMPAIGN ENDPOINTS
# =============================================================================

@router.post("/campaigns/launch", response_model=CampaignResponse)
async def launch_campaign(
    request: CampaignLaunchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Launch a new acquisition campaign.

    This is the "one-button launch" endpoint that:
    1. Selects appropriate blueprint based on goal type
    2. Creates campaign instance
    3. Activates SMS/Email sequences
    4. Sets up dialer queue rules
    5. Starts event listeners
    6. Returns campaign with funnel URL
    """
    # Validate goal type
    try:
        goal_type = GoalType(request.goal_type)
    except ValueError:
        raise HTTPException(400, f"Invalid goal type: {request.goal_type}")

    # Get blueprint (use specific or default for goal type)
    if request.blueprint_id:
        blueprint = db.query(CampaignBlueprint).filter(
            CampaignBlueprint.id == uuid.UUID(request.blueprint_id)
        ).first()
    else:
        blueprint = db.query(CampaignBlueprint).filter(
            CampaignBlueprint.goal_type == goal_type.value,
            CampaignBlueprint.is_default == True,
            CampaignBlueprint.is_active == True,
        ).first()

    if not blueprint:
        raise HTTPException(404, f"No blueprint found for goal type: {goal_type.value}")

    # Generate campaign name if not provided
    campaign_name = request.name or f"{goal_type.value} Campaign - {datetime.now().strftime('%Y%m%d')}"

    # Create campaign instance
    campaign = CampaignInstance(
        id=uuid.uuid4(),
        organization_id=1,  # TODO: Get from auth context
        user_id=1,  # TODO: Get from auth context
        blueprint_id=blueprint.id,
        name=campaign_name,
        goal_type=goal_type.value,
        budget_type=request.budget_type,
        budget_amount=request.budget_amount,
        market_geo=request.market_geo,
        product_focus=request.product_focus,
        capacity_leads_per_week=request.capacity_leads_per_week,
        status=CampaignStatus.LAUNCHING.value,
        launched_at=datetime.utcnow(),
        # Copy config from blueprint
        speed_to_lead_config=blueprint.speed_to_lead_config,
        dialer_config=blueprint.dialer_rules,
        sms_sequences_active=blueprint.sms_sequence_ids,
        email_sequences_active=blueprint.email_sequence_ids,
    )

    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    # Activate campaign in background
    background_tasks.add_task(_activate_campaign, str(campaign.id))

    return CampaignResponse(
        id=str(campaign.id),
        name=campaign.name,
        goal_type=campaign.goal_type,
        status=campaign.status,
        budget_type=campaign.budget_type,
        budget_amount=float(campaign.budget_amount),
        market_geo=campaign.market_geo,
        created_at=campaign.created_at,
        activated_at=campaign.activated_at,
        leads_generated=campaign.leads_generated or 0,
        meetings_booked=campaign.meetings_booked or 0,
        applications_started=campaign.applications_started or 0,
        loans_closed=campaign.loans_closed or 0,
        total_spend=float(campaign.total_spend or 0),
        revenue_attributed=float(campaign.revenue_attributed or 0),
        cost_per_lead=float(campaign.cost_per_lead) if campaign.cost_per_lead else None,
        cost_per_funded_loan=float(campaign.cost_per_funded_loan) if campaign.cost_per_funded_loan else None,
        roi_percentage=float(campaign.roi_percentage) if campaign.roi_percentage else None,
    )


async def _activate_campaign(campaign_id: str):
    """Background task to activate campaign"""
    from database import get_session
    db = get_session()
    try:
        campaign = db.query(CampaignInstance).filter(
            CampaignInstance.id == uuid.UUID(campaign_id)
        ).first()

        if campaign:
            # TODO: Activate SMS sequences
            # TODO: Activate Email sequences
            # TODO: Set up dialer queue rules
            # TODO: Generate funnel URL

            campaign.status = CampaignStatus.ACTIVE.value
            campaign.activated_at = datetime.utcnow()
            db.commit()
            logger.info(f"Campaign {campaign_id} activated")
    except Exception as e:
        logger.error(f"Failed to activate campaign {campaign_id}: {e}")
        if campaign:
            campaign.status = CampaignStatus.ERROR.value
            campaign.last_error = str(e)
            campaign.error_count = (campaign.error_count or 0) + 1
            db.commit()
    finally:
        db.close()


@router.get("/campaigns", response_model=List[CampaignResponse])
async def list_campaigns(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, le=100),
    db: Session = Depends(get_db),
):
    """List all campaigns, optionally filtered by status"""
    query = db.query(CampaignInstance).order_by(CampaignInstance.created_at.desc())

    if status:
        query = query.filter(CampaignInstance.status == status)

    campaigns = query.limit(limit).all()

    return [
        CampaignResponse(
            id=str(c.id),
            name=c.name,
            goal_type=c.goal_type,
            status=c.status,
            budget_type=c.budget_type,
            budget_amount=float(c.budget_amount),
            market_geo=c.market_geo,
            created_at=c.created_at,
            activated_at=c.activated_at,
            leads_generated=c.leads_generated or 0,
            meetings_booked=c.meetings_booked or 0,
            applications_started=c.applications_started or 0,
            loans_closed=c.loans_closed or 0,
            total_spend=float(c.total_spend or 0),
            revenue_attributed=float(c.revenue_attributed or 0),
            cost_per_lead=float(c.cost_per_lead) if c.cost_per_lead else None,
            cost_per_funded_loan=float(c.cost_per_funded_loan) if c.cost_per_funded_loan else None,
            roi_percentage=float(c.roi_percentage) if c.roi_percentage else None,
        )
        for c in campaigns
    ]


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific campaign"""
    campaign = db.query(CampaignInstance).filter(
        CampaignInstance.id == uuid.UUID(campaign_id)
    ).first()

    if not campaign:
        raise HTTPException(404, "Campaign not found")

    return CampaignResponse(
        id=str(campaign.id),
        name=campaign.name,
        goal_type=campaign.goal_type,
        status=campaign.status,
        budget_type=campaign.budget_type,
        budget_amount=float(campaign.budget_amount),
        market_geo=campaign.market_geo,
        created_at=campaign.created_at,
        activated_at=campaign.activated_at,
        leads_generated=campaign.leads_generated or 0,
        meetings_booked=campaign.meetings_booked or 0,
        applications_started=campaign.applications_started or 0,
        loans_closed=campaign.loans_closed or 0,
        total_spend=float(campaign.total_spend or 0),
        revenue_attributed=float(campaign.revenue_attributed or 0),
        cost_per_lead=float(campaign.cost_per_lead) if campaign.cost_per_lead else None,
        cost_per_funded_loan=float(campaign.cost_per_funded_loan) if campaign.cost_per_funded_loan else None,
        roi_percentage=float(campaign.roi_percentage) if campaign.roi_percentage else None,
    )


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
):
    """Pause an active campaign"""
    campaign = db.query(CampaignInstance).filter(
        CampaignInstance.id == uuid.UUID(campaign_id)
    ).first()

    if not campaign:
        raise HTTPException(404, "Campaign not found")

    if campaign.status != CampaignStatus.ACTIVE.value:
        raise HTTPException(400, f"Cannot pause campaign in {campaign.status} status")

    campaign.status = CampaignStatus.PAUSED.value
    campaign.paused_at = datetime.utcnow()
    db.commit()

    return {"status": "paused", "paused_at": campaign.paused_at}


@router.post("/campaigns/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
):
    """Resume a paused campaign"""
    campaign = db.query(CampaignInstance).filter(
        CampaignInstance.id == uuid.UUID(campaign_id)
    ).first()

    if not campaign:
        raise HTTPException(404, "Campaign not found")

    if campaign.status != CampaignStatus.PAUSED.value:
        raise HTTPException(400, f"Cannot resume campaign in {campaign.status} status")

    campaign.status = CampaignStatus.ACTIVE.value
    campaign.paused_at = None
    db.commit()

    return {"status": "active", "resumed_at": datetime.utcnow()}


# =============================================================================
# EVENT ENDPOINTS
# =============================================================================

@router.post("/events", response_model=EventResponse)
async def ingest_event(
    request: EventIngestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Ingest a behavioral event.

    Events are used for:
    - Lead temperature calculation
    - Attribution tracking
    - Triggering speed-to-lead automation
    """
    event_service = EventService(db)

    utm_params = {
        "utm_source": request.utm_source,
        "utm_medium": request.utm_medium,
        "utm_campaign": request.utm_campaign,
        "utm_term": request.utm_term,
        "utm_content": request.utm_content,
    }

    event = event_service.ingest_event(
        organization_id=1,  # TODO: Get from auth context
        event_type=request.event_type,
        event_payload=request.event_payload,
        lead_id=request.lead_id,
        anonymous_visitor_id=request.anonymous_visitor_id,
        campaign_instance_id=request.campaign_instance_id,
        session_id=request.session_id,
        source=request.source,
        utm_params=utm_params,
    )

    # Recalculate temperature in background if lead is known
    if request.lead_id:
        background_tasks.add_task(
            _recalculate_temperature,
            request.lead_id,
            request.campaign_instance_id,
        )

    return EventResponse(
        id=str(event.id),
        event_type=event.event_type,
        lead_id=event.lead_id,
        anonymous_visitor_id=event.anonymous_visitor_id,
        campaign_instance_id=str(event.campaign_instance_id) if event.campaign_instance_id else None,
        temperature_impact=event.temperature_impact or 0,
        is_hot_signal=event.is_hot_signal,
        event_timestamp=event.event_timestamp,
    )


async def _recalculate_temperature(lead_id: int, campaign_instance_id: Optional[str]):
    """Background task to recalculate temperature"""
    from database import get_session
    db = get_session()
    try:
        temp_service = TemperatureService(db)
        temp_service.calculate_temperature(lead_id, campaign_instance_id)
    except Exception as e:
        logger.error(f"Failed to recalculate temperature for lead {lead_id}: {e}")
    finally:
        db.close()


@router.get("/events/{lead_id}", response_model=List[EventResponse])
async def get_lead_events(
    lead_id: int,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """Get events for a specific lead"""
    event_service = EventService(db)
    events = event_service.get_lead_events(lead_id, limit=limit)

    return [
        EventResponse(
            id=str(e.id),
            event_type=e.event_type,
            lead_id=e.lead_id,
            anonymous_visitor_id=e.anonymous_visitor_id,
            campaign_instance_id=str(e.campaign_instance_id) if e.campaign_instance_id else None,
            temperature_impact=e.temperature_impact or 0,
            is_hot_signal=e.is_hot_signal,
            event_timestamp=e.event_timestamp,
        )
        for e in events
    ]


# =============================================================================
# TEMPERATURE ENDPOINTS
# =============================================================================

@router.get("/temperature/{lead_id}", response_model=TemperatureResponse)
async def get_lead_temperature(
    lead_id: int,
    db: Session = Depends(get_db),
):
    """Get temperature for a specific lead"""
    temp_service = TemperatureService(db)
    temp = temp_service.get_temperature(lead_id)

    if not temp:
        raise HTTPException(404, "Temperature record not found for lead")

    return TemperatureResponse(
        lead_id=temp.lead_id,
        temperature=temp.temperature,
        score=temp.score or 0,
        engagement_score=temp.engagement_score or 0,
        intent_score=temp.intent_score or 0,
        recency_score=temp.recency_score or 0,
        frequency_score=temp.frequency_score or 0,
        total_events=temp.total_events or 0,
        total_sessions=temp.total_sessions or 0,
        last_hot_signal=temp.last_hot_signal,
        last_hot_signal_at=temp.last_hot_signal_at,
        days_since_last_activity=temp.days_since_last_activity or 0,
        last_calculated_at=temp.last_calculated_at,
    )


@router.get("/temperature/hot", response_model=List[TemperatureResponse])
async def get_hot_leads(
    campaign_id: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    db: Session = Depends(get_db),
):
    """Get all hot leads"""
    temp_service = TemperatureService(db)
    temps = temp_service.get_hot_leads(campaign_instance_id=campaign_id, limit=limit)

    return [
        TemperatureResponse(
            lead_id=t.lead_id,
            temperature=t.temperature,
            score=t.score or 0,
            engagement_score=t.engagement_score or 0,
            intent_score=t.intent_score or 0,
            recency_score=t.recency_score or 0,
            frequency_score=t.frequency_score or 0,
            total_events=t.total_events or 0,
            total_sessions=t.total_sessions or 0,
            last_hot_signal=t.last_hot_signal,
            last_hot_signal_at=t.last_hot_signal_at,
            days_since_last_activity=t.days_since_last_activity or 0,
            last_calculated_at=t.last_calculated_at,
        )
        for t in temps
    ]


# =============================================================================
# DASHBOARD ENDPOINTS
# =============================================================================

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    db: Session = Depends(get_db),
):
    """Get acquisition engine dashboard"""
    # Get campaign stats
    campaigns = db.query(CampaignInstance).all()

    total_spend = sum(float(c.total_spend or 0) for c in campaigns)
    total_revenue = sum(float(c.revenue_attributed or 0) for c in campaigns)
    total_leads = sum(c.leads_generated or 0 for c in campaigns)
    total_meetings = sum(c.meetings_booked or 0 for c in campaigns)
    total_applications = sum(c.applications_started or 0 for c in campaigns)
    total_funded = sum(c.loans_closed or 0 for c in campaigns)

    active_count = len([c for c in campaigns if c.status == CampaignStatus.ACTIVE.value])
    overall_roi = ((total_revenue - total_spend) / total_spend * 100) if total_spend > 0 else 0

    # Get temperature distribution
    temp_service = TemperatureService(db)
    temp_summary = temp_service.get_temperature_summary()

    # Get speed-to-lead compliance
    hot_within_sla = sum(c.hot_leads_within_sla or 0 for c in campaigns)
    hot_missed_sla = sum(c.hot_leads_missed_sla or 0 for c in campaigns)
    total_hot = hot_within_sla + hot_missed_sla
    stl_compliance = (hot_within_sla / total_hot * 100) if total_hot > 0 else 100

    campaign_responses = [
        CampaignResponse(
            id=str(c.id),
            name=c.name,
            goal_type=c.goal_type,
            status=c.status,
            budget_type=c.budget_type,
            budget_amount=float(c.budget_amount),
            market_geo=c.market_geo,
            created_at=c.created_at,
            activated_at=c.activated_at,
            leads_generated=c.leads_generated or 0,
            meetings_booked=c.meetings_booked or 0,
            applications_started=c.applications_started or 0,
            loans_closed=c.loans_closed or 0,
            total_spend=float(c.total_spend or 0),
            revenue_attributed=float(c.revenue_attributed or 0),
            cost_per_lead=float(c.cost_per_lead) if c.cost_per_lead else None,
            cost_per_funded_loan=float(c.cost_per_funded_loan) if c.cost_per_funded_loan else None,
            roi_percentage=float(c.roi_percentage) if c.roi_percentage else None,
        )
        for c in campaigns
    ]

    return DashboardResponse(
        total_campaigns=len(campaigns),
        active_campaigns=active_count,
        total_spend=total_spend,
        total_leads=total_leads,
        total_meetings=total_meetings,
        total_applications=total_applications,
        total_funded=total_funded,
        total_revenue=total_revenue,
        overall_roi=round(overall_roi, 2),
        speed_to_lead_compliance=round(stl_compliance, 2),
        temperature_distribution={
            temp: data["count"]
            for temp, data in temp_summary.get("by_temperature", {}).items()
        },
        campaigns=campaign_responses,
    )


@router.get("/speed-to-lead", response_model=SpeedToLeadMetrics)
async def get_speed_to_lead_metrics(
    campaign_id: Optional[str] = Query(None),
    days: int = Query(30, le=90),
    db: Session = Depends(get_db),
):
    """Get speed-to-lead performance metrics"""
    # Query campaigns
    query = db.query(CampaignInstance)
    if campaign_id:
        query = query.filter(CampaignInstance.id == uuid.UUID(campaign_id))

    campaigns = query.all()

    total_hot = sum((c.hot_leads_within_sla or 0) + (c.hot_leads_missed_sla or 0) for c in campaigns)
    within_sla = sum(c.hot_leads_within_sla or 0 for c in campaigns)
    missed_sla = sum(c.hot_leads_missed_sla or 0 for c in campaigns)
    compliance = (within_sla / total_hot * 100) if total_hot > 0 else 100

    # Average response time
    avg_times = [c.avg_speed_to_first_contact_seconds for c in campaigns if c.avg_speed_to_first_contact_seconds]
    avg_response = int(sum(avg_times) / len(avg_times)) if avg_times else 0

    return SpeedToLeadMetrics(
        total_hot_leads=total_hot,
        within_sla=within_sla,
        missed_sla=missed_sla,
        compliance_rate=round(compliance, 2),
        avg_response_time_seconds=avg_response,
        p50_response_time_seconds=avg_response,  # TODO: Calculate actual percentiles
        p90_response_time_seconds=avg_response * 2,  # TODO: Calculate actual percentiles
    )


@router.post("/speed-to-lead/{lead_id}/trigger", response_model=SpeedToLeadTriggerResponse)
async def trigger_speed_to_lead(
    lead_id: int,
    request: SpeedToLeadTriggerRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Manually trigger speed-to-lead for a specific lead.

    Use this to:
    - Re-engage a hot lead that wasn't contacted in time
    - Trigger outreach for a lead that just became hot
    - Override automatic triggering with manual control
    """
    # Get lead info
    lead = db.execute(text("""
        SELECT id, first_name, last_name, email, phone, assigned_to
        FROM leads WHERE id = :lead_id
    """), {"lead_id": lead_id}).fetchone()

    if not lead:
        raise HTTPException(404, f"Lead {lead_id} not found")

    # Create synthetic event if needed
    event = None
    if request.event_type:
        event_service = EventService(db)
        event = event_service.ingest_event(
            organization_id=1,
            event_type=request.event_type,
            lead_id=lead_id,
            campaign_instance_id=request.campaign_instance_id,
            source="manual_trigger",
        )

    # Build config
    config = SpeedToLeadConfig(
        sla_seconds=300,  # 5 minutes
        enable_sms=not request.skip_sms,
        enable_email=not request.skip_email,
        enable_dialer=not request.skip_dialer,
    )

    # Trigger speed-to-lead
    stl_service = SpeedToLeadService(db)

    try:
        result = await stl_service.process_hot_lead(
            lead_id=lead_id,
            event=event,
            campaign_instance_id=request.campaign_instance_id,
            config=config,
        )

        return SpeedToLeadTriggerResponse(
            lead_id=lead_id,
            success=result.success,
            sla_met=result.sla_met,
            response_time_seconds=result.response_time_seconds,
            actions_taken=[a.value for a in result.actions_taken],
            errors=result.errors,
            next_actions=result.next_scheduled_actions,
        )
    except Exception as e:
        logger.error(f"Speed-to-lead trigger failed for lead {lead_id}: {e}")
        return SpeedToLeadTriggerResponse(
            lead_id=lead_id,
            success=False,
            sla_met=False,
            response_time_seconds=0,
            actions_taken=[],
            errors=[str(e)],
            next_actions=[],
        )


@router.get("/speed-to-lead/{campaign_id}/detailed")
async def get_speed_to_lead_detailed(
    campaign_id: str,
    days: int = Query(7, le=30),
    db: Session = Depends(get_db),
):
    """
    Get detailed speed-to-lead metrics for a campaign.

    Includes per-action breakdown and SLA compliance details.
    """
    stl_service = SpeedToLeadService(db)
    metrics = stl_service.get_sla_metrics(campaign_id, days=days)

    return metrics


# =============================================================================
# CONVERSION TRACKING ENDPOINTS
# =============================================================================

@router.post("/conversions", response_model=ConversionTrackResponse)
async def track_conversion(
    request: ConversionTrackRequest,
    db: Session = Depends(get_db),
):
    """
    Track a conversion event.

    Conversions are key milestones:
    - lead: New lead created
    - meeting: Meeting booked/completed
    - application: Application started/submitted
    - funded: Loan funded (final conversion)

    Attribution tracks which campaign gets credit for the conversion.
    """
    orchestrator = ConversionOrchestrator(db)

    try:
        attribution = orchestrator.track_conversion(
            lead_id=request.lead_id,
            conversion_type=request.conversion_type,
            campaign_instance_id=request.campaign_instance_id,
            loan_id=request.loan_id,
            loan_amount=request.loan_amount,
            estimated_revenue=request.estimated_revenue,
            attribution_type=request.attribution_type or "first_touch",
        )

        return ConversionTrackResponse(
            id=str(attribution.id),
            lead_id=attribution.lead_id,
            conversion_type=attribution.conversion_type,
            campaign_instance_id=str(attribution.campaign_instance_id) if attribution.campaign_instance_id else None,
            attribution_credit=float(attribution.attribution_credit or 1.0),
            conversion_date=attribution.conversion_date,
        )
    except Exception as e:
        logger.error(f"Conversion tracking failed: {e}")
        raise HTTPException(500, f"Failed to track conversion: {e}")


@router.get("/conversions/{lead_id}")
async def get_lead_conversions(
    lead_id: int,
    db: Session = Depends(get_db),
):
    """Get all conversions for a lead"""
    attributions = db.query(CampaignAttribution).filter(
        CampaignAttribution.lead_id == lead_id
    ).order_by(CampaignAttribution.conversion_date.desc()).all()

    return [
        {
            "id": str(a.id),
            "conversion_type": a.conversion_type,
            "campaign_instance_id": str(a.campaign_instance_id) if a.campaign_instance_id else None,
            "loan_id": a.loan_id,
            "loan_amount": float(a.loan_amount) if a.loan_amount else None,
            "estimated_revenue": float(a.estimated_revenue) if a.estimated_revenue else None,
            "attribution_type": a.attribution_type,
            "attribution_credit": float(a.attribution_credit) if a.attribution_credit else 1.0,
            "conversion_date": a.conversion_date.isoformat() if a.conversion_date else None,
        }
        for a in attributions
    ]


# =============================================================================
# FUNNEL METRICS ENDPOINTS
# =============================================================================

@router.get("/funnel", response_model=FunnelMetricsResponse)
async def get_funnel_metrics(
    campaign_id: Optional[str] = Query(None, description="Filter by campaign"),
    days: int = Query(30, le=90),
    db: Session = Depends(get_db),
):
    """
    Get funnel conversion metrics.

    Shows conversion rates through the acquisition funnel:
    - Leads → Meetings
    - Meetings → Applications
    - Applications → Funded

    Optionally filtered by campaign.
    """
    orchestrator = ConversionOrchestrator(db)
    metrics = orchestrator.get_funnel_metrics(
        campaign_instance_id=campaign_id,
        days=days,
    )

    return FunnelMetricsResponse(
        period_days=days,
        funnel=metrics.get("funnel", {}),
        conversion_rates=metrics.get("conversion_rates", {}),
        by_campaign=metrics.get("by_campaign"),
    )


@router.get("/funnel/{campaign_id}")
async def get_campaign_funnel(
    campaign_id: str,
    days: int = Query(30, le=90),
    db: Session = Depends(get_db),
):
    """Get detailed funnel for a specific campaign"""
    orchestrator = ConversionOrchestrator(db)
    metrics = orchestrator.get_funnel_metrics(
        campaign_instance_id=campaign_id,
        days=days,
    )

    # Get campaign info
    campaign = db.query(CampaignInstance).filter(
        CampaignInstance.id == uuid.UUID(campaign_id)
    ).first()

    if not campaign:
        raise HTTPException(404, "Campaign not found")

    return {
        "campaign": {
            "id": str(campaign.id),
            "name": campaign.name,
            "goal_type": campaign.goal_type,
            "status": campaign.status,
        },
        "period_days": days,
        "funnel": metrics.get("funnel", {}),
        "conversion_rates": metrics.get("conversion_rates", {}),
        "cost_metrics": {
            "total_spend": float(campaign.total_spend or 0),
            "cost_per_lead": float(campaign.cost_per_lead) if campaign.cost_per_lead else None,
            "cost_per_meeting": None,  # TODO: Calculate
            "cost_per_application": None,  # TODO: Calculate
            "cost_per_funded": float(campaign.cost_per_funded_loan) if campaign.cost_per_funded_loan else None,
        },
        "revenue_metrics": {
            "total_revenue": float(campaign.revenue_attributed or 0),
            "roi_percentage": float(campaign.roi_percentage) if campaign.roi_percentage else None,
        },
    }


# =============================================================================
# ATTRIBUTION ENDPOINTS
# =============================================================================

@router.get("/attribution")
async def get_attribution_report(
    campaign_id: Optional[str] = Query(None),
    days: int = Query(30, le=90),
    db: Session = Depends(get_db),
):
    """
    Get attribution report showing which campaigns drove conversions.

    Shows revenue attribution back to campaigns for ROI calculation.
    """
    query = db.query(CampaignAttribution)

    if campaign_id:
        query = query.filter(
            CampaignAttribution.campaign_instance_id == uuid.UUID(campaign_id)
        )

    query = query.filter(
        CampaignAttribution.conversion_date >= datetime.utcnow() - timedelta(days=days)
    )

    attributions = query.all()

    # Aggregate by campaign
    by_campaign = {}
    for a in attributions:
        cid = str(a.campaign_instance_id) if a.campaign_instance_id else "unattributed"
        if cid not in by_campaign:
            by_campaign[cid] = {
                "leads": 0,
                "meetings": 0,
                "applications": 0,
                "funded": 0,
                "total_loan_amount": 0,
                "total_revenue": 0,
            }

        ct = a.conversion_type
        if ct == "lead":
            by_campaign[cid]["leads"] += 1
        elif ct == "meeting":
            by_campaign[cid]["meetings"] += 1
        elif ct == "application":
            by_campaign[cid]["applications"] += 1
        elif ct == "funded":
            by_campaign[cid]["funded"] += 1
            by_campaign[cid]["total_loan_amount"] += float(a.loan_amount or 0)
            by_campaign[cid]["total_revenue"] += float(a.estimated_revenue or 0)

    # Get campaign names
    campaign_ids = [uuid.UUID(cid) for cid in by_campaign.keys() if cid != "unattributed"]
    campaigns = {
        str(c.id): c.name
        for c in db.query(CampaignInstance).filter(
            CampaignInstance.id.in_(campaign_ids)
        ).all()
    } if campaign_ids else {}

    return {
        "period_days": days,
        "total_attributions": len(attributions),
        "by_campaign": [
            {
                "campaign_id": cid,
                "campaign_name": campaigns.get(cid, "Unattributed"),
                **data,
            }
            for cid, data in by_campaign.items()
        ],
        "totals": {
            "leads": sum(d["leads"] for d in by_campaign.values()),
            "meetings": sum(d["meetings"] for d in by_campaign.values()),
            "applications": sum(d["applications"] for d in by_campaign.values()),
            "funded": sum(d["funded"] for d in by_campaign.values()),
            "total_loan_amount": sum(d["total_loan_amount"] for d in by_campaign.values()),
            "total_revenue": sum(d["total_revenue"] for d in by_campaign.values()),
        },
    }


# =============================================================================
# BLUEPRINT ENDPOINTS
# =============================================================================

@router.get("/blueprints")
async def list_blueprints(
    goal_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List available campaign blueprints"""
    query = db.query(CampaignBlueprint).filter(CampaignBlueprint.is_active == True)

    if goal_type:
        query = query.filter(CampaignBlueprint.goal_type == goal_type)

    blueprints = query.all()

    return [
        {
            "id": str(b.id),
            "name": b.name,
            "description": b.description,
            "version": b.version,
            "goal_type": b.goal_type,
            "is_default": b.is_default,
            "min_budget": float(b.min_budget) if b.min_budget else None,
            "max_budget": float(b.max_budget) if b.max_budget else None,
            "recommended_budget": float(b.recommended_budget) if b.recommended_budget else None,
        }
        for b in blueprints
    ]
